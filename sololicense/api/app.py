"""HTTP adapter for Solo License.

The React client and the coding agents' hooks talk only to this file. The
coding gate, SQLite and the git-backed ledger remain the implementation in
``sololicense``.
"""

from __future__ import annotations

import os
import re
import secrets
from contextlib import asynccontextmanager
from dataclasses import replace
from hashlib import sha256
from threading import RLock

from typing import Annotated

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sololicense.bootstrap import AppContext, build_app
from sololicense.db.repositories import agent as agent_repo
from sololicense.db.repositories import settings as settings_repo
from sololicense.coding.actions import ACTION_CLASSES, MCP_PREFIX
from sololicense.observability.links import event_payload, neatlogs_link
from sololicense.observability.neatlogs_probe import response_for, run_doctor_probe
from sololicense.security import Actor, Role, TokenAuthenticator, permits

SECRET_KEYS = tuple(sorted(settings_repo.SECRET_KEYS))
SETTING_KEYS = ("neatlogs_project", "jev_endpoint", "trust_confidence", *SECRET_KEYS)
_NUMERIC_KEYS = ("trust_confidence",)

_context: AppContext | None = None
_authenticator: TokenAuthenticator | None = None
_demo_sessions: dict[str, Actor] = {}
_lock = RLock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    # Flush remote traces when the long-running API process exits.
    if _context is not None:
        _context.neatlogs.shutdown()


app = FastAPI(title="Solo License API", lifespan=lifespan)


def _allowed_origins() -> list[str]:
    """Demo mode serves a public dashboard with no cookies or secrets, so any
    browser origin may call it; deployments list theirs in SOLO_ALLOWED_ORIGINS."""
    if os.environ.get("SOLO_DEMO_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}:
        return ["*"]
    return [
        origin.strip()
        for origin in os.environ.get("SOLO_ALLOWED_ORIGINS", "http://localhost:5174").split(",")
        if origin.strip()
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- payloads -------------------------------------------------------------

class SettingsPayload(BaseModel):
    values: dict[str, str | int | float | None]


class DemoSessionPayload(BaseModel):
    name: str = Field(default="", max_length=40)


# --- context --------------------------------------------------------------

def get_context() -> AppContext:
    global _context
    if _context is None:
        _context = build_app(check_same_thread=False)
    return _context


def reset_context() -> None:
    """Drop the wired app so the next request rebuilds it with new settings."""
    global _context
    if _context is not None:
        try:
            _context.conn.close()
        except Exception:  # pragma: no cover
            pass
    _context = None


def _token_auth_configured() -> bool:
    return bool(os.environ.get("SOLO_API_TOKENS", "").strip())


def get_authenticator() -> TokenAuthenticator:
    """Load deployment-owned API tokens once, never from SQLite settings."""
    global _authenticator
    if _authenticator is None:
        raw_tokens = os.environ.get("SOLO_API_TOKENS", "").strip()
        if not raw_tokens:
            raise HTTPException(status_code=503, detail="API authentication is not configured.")
        try:
            _authenticator = TokenAuthenticator.from_json(raw_tokens)
        except ValueError as error:
            raise HTTPException(status_code=503, detail="API authentication is misconfigured.") from error
    return _authenticator


def current_actor(authorization: str | None = Header(default=None)) -> Actor:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Bearer authentication is required.")
    for issued, actor in _demo_sessions.items():
        if secrets.compare_digest(issued, token):
            return actor
    remembered = _remembered_demo_actor(token)
    if remembered is not None:
        return remembered
    if not _token_auth_configured():
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    actor = get_authenticator().authenticate(token)
    if actor is None:
        raise HTTPException(status_code=401, detail="Invalid API token.")
    return actor


_DEMO_PREFIX = "demo_session:"


def _token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _remembered_demo_actor(token: str) -> Actor | None:
    """Demo sessions survive an API restart: only a hash of the token is kept
    in the local settings table, and only while demo mode is on."""
    with _lock:
        context = get_context()
        if not context.config.demo_mode:
            return None
        row = context.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (_DEMO_PREFIX + _token_digest(token),)
        ).fetchone()
    if row is None:
        return None
    actor = Actor(actor_id=row["value"], role=Role.ADMIN)
    _demo_sessions[token] = actor
    return actor


def require_role(required: Role):
    def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        if not permits(actor, required):
            raise HTTPException(status_code=403, detail="This role is not allowed to perform that action.")
        return actor

    return dependency


# --- serialization ----------------------------------------------------------

def _mask(value: str) -> str:
    return f"••••{value[-4:]}" if len(value) > 4 else ("••••" if value else "")


def serialize_settings(context: AppContext) -> dict:
    stored = settings_repo.get_all(context.conn)
    cfg = context.config
    out = {
        "onboarded": stored.get("onboarded") == "1",
        "trust_confidence": cfg.trust_confidence,
        "neatlogs_project": cfg.neatlogs_project,
        "neatlogs_enabled": cfg.neatlogs_enabled,
        "demo_mode": cfg.demo_mode,
        "jev_enabled": bool(cfg.typesafe_api_key),
        "jev_endpoint": cfg.jev_endpoint,
    }
    for key in SECRET_KEYS:
        value = getattr(cfg, key, "")
        out[f"has_{key}"] = bool(value)
        out[f"{key}_hint"] = _mask(value)
    return out


def _observability(context: AppContext) -> dict:
    cfg = context.config
    ledger = context.conn.execute(
        "SELECT COUNT(*) AS n, COUNT(git_sha) AS committed FROM agent_events"
    ).fetchone()
    return {
        "neatlogs": {
            "enabled": cfg.neatlogs_enabled,
            "project": cfg.neatlogs_project,
            "app_url": cfg.neatlogs_app_url,
        },
        "ledger": {
            "repo": str(cfg.ledger_repo),
            "events": ledger["n"] or 0,
            "commits": ledger["committed"] or 0,
        },
    }


def dashboard_payload(context: AppContext) -> dict:
    """The workspace view: settings, the license history and where it is kept."""
    events = [{**event_payload(e, context.config), "id": f"agent-{e['id']}",
               "task_class": f"{e['action_class']}@{e['repo']}"}
              for e in agent_repo.list_events(context.conn, limit=60)]
    return {
        "settings": serialize_settings(context),
        "events": events,
        "observability": _observability(context),
    }


# --- session ----------------------------------------------------------------

@app.get("/api/session")
def session_info() -> dict:
    """Public: which sign-in paths this deployment offers."""
    with _lock:
        demo = get_context().config.demo_mode
    return {"demo_enabled": demo, "token_auth": _token_auth_configured()}


@app.post("/api/session/demo")
def start_demo_session(payload: DemoSessionPayload) -> dict:
    """Local demo only (SOLO_DEMO_MODE=1): issue a short-lived admin session so
    a judge can try the product without a deployment token. The name is
    recorded as the actor on every license change."""
    with _lock:
        context = get_context()
        if not context.config.demo_mode:
            raise HTTPException(status_code=404, detail="Demo sessions are disabled.")
        slug = re.sub(r"[^a-z0-9]+", "-", payload.name.strip().lower()).strip("-")[:24]
        actor = Actor(actor_id=f"demo:{slug or 'guest'}", role=Role.ADMIN)
        token = secrets.token_urlsafe(32)
        if len(_demo_sessions) > 200:
            _demo_sessions.clear()
        _demo_sessions[token] = actor
        settings_repo.set_many(context.conn, {_DEMO_PREFIX + _token_digest(token): actor.actor_id})
        context.conn.commit()
        return {"token": token, "actor": {"id": actor.actor_id, "role": actor.role.value}}


@app.get("/api/session/me")
def whoami(actor: Actor = Depends(current_actor)) -> dict:
    return {"id": actor.actor_id, "role": actor.role.value}


# --- read -----------------------------------------------------------------

@app.get("/api/dashboard")
def get_dashboard(actor: Actor = Depends(require_role(Role.OPERATOR))) -> dict:
    with _lock:
        return dashboard_payload(get_context())


@app.get("/api/settings")
def get_settings(actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    with _lock:
        return serialize_settings(get_context())


# --- settings ---------------------------------------------------------------

def _clean_values(values: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in values.items():
        if key not in SETTING_KEYS or value is None:
            continue
        text = str(value).strip()
        if key in SECRET_KEYS and (not text or text.startswith("••")):
            continue  # blank / masked -> keep the stored secret
        out[key] = text
    if "trust_confidence" in out:
        try:
            valid = 0.5 <= float(out["trust_confidence"]) <= 0.999
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(status_code=422, detail="Invalid numeric setting.")
    return out


def _save_settings(context: AppContext, values: dict[str, str]) -> None:
    try:
        protected = settings_repo.protect_secret_values(
            values, context.config.settings_encryption_key
        )
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    settings_repo.set_many(context.conn, protected)
    context.conn.commit()


@app.put("/api/settings")
def update_settings(
    payload: SettingsPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    with _lock:
        context = get_context()
        _save_settings(context, _clean_values(payload.values))
        reset_context()
        return dashboard_payload(get_context())


def _config_with_form(context: AppContext, cleaned: dict[str, str]):
    """The saved config with unsaved form values overlaid (for tests)."""
    changes = {
        key: value for key, value in cleaned.items()
        if key in context.config.__dataclass_fields__ and key not in _NUMERIC_KEYS
    }
    return replace(context.config, **changes)


@app.post("/api/settings/test-neatlogs")
def test_neatlogs(
    payload: SettingsPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    """Doctor-probe neatlogs from an isolated child process.

    The live tracer in this process stays untouched (re-initialising it is
    what the SDK refuses); the probe runs out of process with the unsaved
    key passed through the child's environment, and the answer is a safe,
    structured result the frontend can explain.
    """
    with _lock:
        context = get_context()
        cfg = _config_with_form(context, _clean_values(payload.values))
    if not cfg.neatlogs_api_key:
        return {
            "ok": False,
            "code": "CREDENTIAL_MISSING",
            "message": "Add a neatlogs API key first.",
        }
    report = run_doctor_probe(cfg.neatlogs_api_key, cfg.neatlogs_endpoint)
    return response_for(report, secret=cfg.neatlogs_api_key)


# --- coding agents: Claude Code hooks ------------------------------------------

_HOOK_EVENTS = {
    "user-prompt": "UserPromptSubmit",
    "pre-tool": "PreToolUse",
    "permission": "PermissionRequest",
    "post-tool": "PostToolUse",
    "post-tool-failure": "PostToolUseFailure",
    "stop": "Stop",
    "subagent-start": "SubagentStart",
    "subagent-stop": "SubagentStop",
}


def _client_fields(body: dict) -> dict:
    """Drop gate-internal keys (``_agent``, ``_prompt_only``, ...) a caller
    might send: who an event came from is decided by the route, never the body."""
    return {k: v for k, v in body.items() if not str(k).startswith("_")}


def _hook_secret(context: AppContext) -> str:
    """Shared secret for hook calls that do not come from this machine."""
    stored = settings_repo.get_all(context.conn).get("hook_secret_hint")
    if stored:
        return stored
    secret = "hook_" + secrets.token_urlsafe(18)
    settings_repo.set_many(context.conn, {"hook_secret_hint": secret})
    context.conn.commit()
    return secret


def _hook_allowed(context: AppContext, request: Request, given: str | None) -> bool:
    # Claude Code runs on the developer's machine and calls the local API.
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return True
    return bool(given) and secrets.compare_digest(given, _hook_secret(context))


@app.post("/api/hooks/{event}")
def coding_hook(
    event: str,
    request: Request,
    body: dict = Body(default_factory=dict),
    x_solo_hook_key: str | None = Header(default=None),
) -> dict:
    """One endpoint per Claude Code hook. The response is the hook's JSON
    output: a PermissionRequest decision, or a Stop block with the reason the
    turn's checks failed. Unknown or failing calls answer ``{}``, which leaves
    Claude Code's own behaviour unchanged (it asks the person)."""
    if event not in _HOOK_EVENTS:
        raise HTTPException(status_code=404, detail="Unknown hook event.")
    with _lock:
        context = get_context()
        if not _hook_allowed(context, request, x_solo_hook_key):
            raise HTTPException(status_code=401, detail="Invalid hook key.")
        gate = context.coding_gate
        if gate is None:
            return {}
        # This route is Claude Code's: its PermissionRequest fires only when a
        # person would be asked. Every other agent uses /api/hooks/{agent}/...
        # Server-set keys always replace anything the caller sent.
        body = {**_client_fields(body), "_agent": "claude-code", "_prompt_only": True}
        if event == "user-prompt":
            return gate.user_prompt(body)
        if event == "subagent-start":
            return gate.subagent_start(body)
        if event == "pre-tool":
            return gate.pre_tool(body)
        if event == "permission":
            return gate.permission(body)
        if event == "stop":
            return gate.stop(body)
        if event == "subagent-stop":
            return gate.subagent_stop(body)
        return gate.tool_result(body, failed=event == "post-tool-failure")


@app.get("/api/hooks/secret")
def hook_secret(actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    with _lock:
        return {"header": "X-Solo-Hook-Key", "secret": _hook_secret(get_context())}


def coding_savings(context: AppContext, repo: str | None = None) -> dict:
    """What the gate did, in developer time: every auto-allowed action is a
    prompt nobody had to answer (the L0 minutes of the coding ladder)."""
    from sololicense.coding.ladder import DEVELOPER_HOURLY_COST, MINUTES_BY_LEVEL

    where, args = ("WHERE repo = ?", (repo,)) if repo else ("", ())
    d = context.conn.execute(
        f"""SELECT COALESCE(SUM(decision = 'allow'), 0) AS allowed,
                   COALESCE(SUM(decision = 'deny'), 0) AS denied,
                   COALESCE(SUM(decision = 'ask'), 0) AS asked
              FROM agent_decisions {where}""", args).fetchone()
    verified = context.conn.execute(
        f"SELECT COUNT(*) AS n FROM agent_turns {where} {'AND' if repo else 'WHERE'} status = 'verified'", args,
    ).fetchone()["n"]
    # A turn sent back once leaves a turn.blocked span on its trace.
    sent_back = context.conn.execute(
        "SELECT COUNT(DISTINCT trace_id) AS n FROM spans WHERE name = 'turn.blocked'"
        + (" AND trace_id IN (SELECT trace_id FROM agent_turns WHERE repo = ?)" if repo else ""), args,
    ).fetchone()["n"]
    minutes = int(d["allowed"]) * (MINUTES_BY_LEVEL[0] - MINUTES_BY_LEVEL[2])
    return {
        "auto_allowed": int(d["allowed"]),
        "asked": int(d["asked"]),
        "blocked": int(d["denied"]),
        "sent_back": int(sent_back),
        "verified_turns": int(verified),
        "minutes_saved": round(minutes, 1),
        "usd_saved": round(minutes / 60.0 * DEVELOPER_HOURLY_COST, 2),
    }


def coding_payload(context: AppContext, repo: str | None = None) -> dict:
    """Everything the agent dashboard shows: licenses, decisions, turns."""
    gate = context.coding_gate
    licenses = []
    for row in agent_repo.list_licenses(context.conn, repo):
        spec = ACTION_CLASSES.get(row["action_class"])
        if spec is None:
            continue
        principal = str(row["principal"] or "main")
        ceiling = gate.ceiling_for(row["repo"], spec.key, principal) if gate else spec.max_level
        progress = gate.ladder.progress(spec.key, row["level"], row["successes"], row["failures"],
                                        row["successes_at_level"], ceiling=ceiling) if gate else {}
        licenses.append({
            "repo": row["repo"], "principal": principal, "action_class": spec.key, "label": spec.label,
            "level": row["level"], "max_level": spec.max_level, "ceiling": ceiling,
            "successes": row["successes"], "failures": row["failures"],
            "mcp_server": spec.key[len(MCP_PREFIX):] if spec.key.startswith(MCP_PREFIX) else None,
            "demoted_from": row["demoted_from"], "updated_at": row["updated_at"], **progress,
        })
    config = getattr(context, "config", None)
    decisions = [{**dict(r), "neatlogs_link": neatlogs_link(config, r["trace_id"])}
                 for r in agent_repo.recent_decisions(context.conn, 60) if repo is None or r["repo"] == repo]
    turns = [{**dict(r), "neatlogs_link": neatlogs_link(config, r["trace_id"])}
             for r in agent_repo.recent_turns(context.conn, 30) if repo is None or r["repo"] == repo]
    counts = {k: sum(1 for d in decisions if d["decision"] == k) for k in ("allow", "ask", "deny")}
    savings = coding_savings(context, repo)
    from sololicense.coding import policy as policy_mod

    repos = [dict(r) for r in context.conn.execute("SELECT repo, path, test_command FROM agent_repos")]
    for r in repos:
        rules = policy_mod.effective(context.conn, r["repo"], r["path"])
        r["frozen"], r["policy"], r["policy_source"] = rules.freeze, rules.digest, rules.source
    return {
        "repos": repos,
        "licenses": licenses,
        "decisions": decisions,
        "turns": turns,
        "events": [event_payload(r, getattr(context, "config", None))
                   for r in agent_repo.list_events(context.conn, repo, 60)],
        "remediations": [dict(r) for r in agent_repo.recent_remediations(context.conn, 30, repo)],
        "loops": agent_repo.loop_events(context.conn, repo, 30),
        "flags": [dict(r) for r in agent_repo.list_flags(context.conn, 30)],
        "counts": counts,
        "savings": savings,
        "agents": [dict(r) for r in agent_repo.agents_seen(context.conn)],
        "jev_enabled": bool(gate and gate.jev_client.enabled),
        "classes": [{"key": c.key, "label": c.label, "max_level": c.max_level, "incident_cost": c.incident_cost}
                    for c in ACTION_CLASSES.values()],
    }


@app.get("/api/coding")
def coding_dashboard(
    request: Request,
    repo: str | None = Query(default=None, max_length=200),
    authorization: str | None = Header(default=None),
) -> dict:
    """Licenses, decisions and turns of the coding agent. Read-only; served to
    this machine (the plugin's /trust command) and to signed-in users."""
    with _lock:
        context = get_context()
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            current_actor(authorization)
        return coding_payload(context, repo)


class TestCommandPayload(BaseModel):
    repo: str = Field(min_length=1, max_length=200)
    test_command: str = Field(default="", max_length=400)


@app.post("/api/coding/test-command")
def set_coding_test_command(
    payload: TestCommandPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    """The command that verifies a turn in this repository (blank: detect)."""
    with _lock:
        context = get_context()
        agent_repo.set_test_command(context.conn, payload.repo, payload.test_command.strip() or None)
        context.conn.commit()
        return coding_payload(context)


def turn_story(context: AppContext, turn_id: int) -> dict | None:
    """One turn's whole story: what was asked, every decision, what the agent was
    told, the license changes it caused, its trace (neatlogs link and the local
    span timeline) and its Entire checkpoint, with how to rewind it."""
    import json as _json

    turn = agent_repo.get_turn(context.conn, turn_id)
    if turn is None:
        return None
    config = getattr(context, "config", None)
    trace_id = turn["trace_id"]
    spans = [] if not trace_id else [
        {"name": r["name"], "status": r["status"], "at": r["created_at"],
         "reason": (_json.loads(r["attributes"] or "{}").get("reason") or "")[:200]}
        for r in context.conn.execute("SELECT name, status, attributes, created_at FROM spans "
                                      "WHERE trace_id = ? ORDER BY id LIMIT 200", (trace_id,))]
    events = [] if not trace_id else [event_payload(r, config) for r in context.conn.execute(
        "SELECT * FROM agent_events WHERE trace_id = ? ORDER BY id", (trace_id,))]
    told = [dict(r) for r in context.conn.execute(
        "SELECT kind, text, delivered_at FROM agent_remediations WHERE turn_id = ? ORDER BY id", (turn_id,))]
    checkpoint = (turn["entire_checkpoint"] or "")[:12]
    can_rewind = turn["status"] in ("failed", "blocked")
    return {
        "turn": {**dict(turn), "neatlogs_link": neatlogs_link(config, trace_id)},
        "decisions": [dict(r) for r in agent_repo.decisions_for_turn(context.conn, turn_id)],
        "told": told,
        "events": events,
        "spans": spans,
        "entire": {"checkpoint": checkpoint or None,
                   "explain": f"entire checkpoint explain {checkpoint}" if checkpoint else None},
        "rewind": {"available": can_rewind,
                   "how": (f"Press Rewind on this turn in the dashboard (or POST /api/coding/turns/{turn_id}/rewind): "
                           "the turn's changes are stashed with git stash, never deleted.") if can_rewind else None},
    }


@app.get("/api/coding/turns/{turn_id}/explain")
def explain_coding_turn(
    turn_id: int, request: Request, authorization: str | None = Header(default=None),
) -> dict:
    """Read-only; served to this machine (``solo-license explain``) and to signed-in users."""
    with _lock:
        context = get_context()
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            current_actor(authorization)
        story = turn_story(context, turn_id)
        if story is None:
            raise HTTPException(status_code=404, detail="No such turn.")
        return story


@app.post("/api/coding/turns/{turn_id}/rewind")
def rewind_coding_turn(turn_id: int, actor: Actor = Depends(require_role(Role.APPROVER))) -> dict:
    """A person puts the repository back to how it was before a failed turn.
    The turn's changes are stashed, never deleted."""
    from sololicense.coding import entire

    with _lock:
        context = get_context()
        turn = agent_repo.get_turn(context.conn, turn_id)
        if turn is None:
            raise HTTPException(status_code=404, detail="No such turn.")
        result = entire.rewind(turn["cwd"], turn["base_ref"], f"solo-license: rewind turn {turn_id}")
        if not result["ok"]:
            raise HTTPException(status_code=409, detail=result.get("error") or "Could not rewind.")
        agent_repo.close_turn(context.conn, turn_id, status="rewound",
                              reason=f"Rewound by {actor.actor_id}; changes kept in `git stash list`.")
        context.conn.commit()
        return {"rewind": result, **coding_payload(context)}


class CodingRestorePayload(BaseModel):
    repo: str = Field(min_length=1, max_length=200)
    action_class: str = Field(min_length=1, max_length=40)
    principal: str = Field(default="main", min_length=1, max_length=120,
                           pattern=r"^(main|subagent:[A-Za-z0-9_.:-]+)$")
    level: int = Field(ge=0, le=2)
    reason: str = Field(default="Reviewed and resumed.", max_length=300)


@app.post("/api/coding/licenses/restore")
def restore_coding_license(
    payload: CodingRestorePayload, actor: Actor = Depends(require_role(Role.APPROVER))
) -> dict:
    """A person resumes a paused action class at a level they choose."""
    with _lock:
        context = get_context()
        if payload.action_class not in ACTION_CLASSES or context.coding_gate is None:
            raise HTTPException(status_code=422, detail="Unknown action class.")
        context.coding_gate.restore(payload.repo, payload.action_class, payload.level,
                                    actor_id=actor.actor_id, reason=payload.reason,
                                    principal=payload.principal)
        return coding_payload(context)


class CodingFlagPayload(BaseModel):
    decision_id: int | None = Field(default=None, ge=1)
    turn_id: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=1, max_length=500)


@app.post("/api/coding/flags")
def flag_coding_decision(
    payload: CodingFlagPayload, actor: Actor = Depends(require_role(Role.APPROVER))
) -> dict:
    """A person marks one decision or one turn as wrong: its classes go back
    to L0 and the agent's next prompt is told what to revert."""
    if (payload.decision_id is None) == (payload.turn_id is None):
        raise HTTPException(status_code=422, detail="Flag exactly one decision_id or one turn_id.")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Say what was wrong.")
    with _lock:
        context = get_context()
        if context.coding_gate is None:
            raise HTTPException(status_code=422, detail="The coding gate is not running.")
        try:
            context.coding_gate.flag(decision_id=payload.decision_id, turn_id=payload.turn_id,
                                     actor_id=actor.actor_id, reason=reason)
        except LookupError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return coding_payload(context)


def budget_payload(context: AppContext) -> dict:
    """Spend per session and per repo today, the caps, and what earned autonomy saved."""
    from sololicense.coding import agents, budget
    from sololicense.coding import policy as policy_mod

    repos = [dict(r) for r in context.conn.execute("SELECT repo, path FROM agent_repos")]
    out = budget.payload(context.conn, repos,
                         lambda r: policy_mod.effective(context.conn, r["repo"], r["path"]).budget,
                         {a.key: a.label for a in agents.AGENTS.values()})
    out["savings"] = coding_savings(context)
    return out


@app.get("/api/coding/budget")
def coding_budget(request: Request, authorization: str | None = Header(default=None)) -> dict:
    """What the coding agents spent, against the caps in the policy. Read-only;
    served to this machine (``solo-license budget``) and to signed-in users."""
    with _lock:
        context = get_context()
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            current_actor(authorization)
        return budget_payload(context)


class BudgetResumePayload(BaseModel):
    repo: str = Field(min_length=1, max_length=200)
    session_id: str | None = Field(default=None, min_length=1, max_length=200)


@app.post("/api/coding/budget/resume")
def resume_coding_budget(
    payload: BudgetResumePayload, actor: Actor = Depends(require_role(Role.APPROVER))
) -> dict:
    """A person lets the agent continue past a reached cap (the session, and the repo today)."""
    with _lock:
        context = get_context()
        if context.coding_gate is None:
            raise HTTPException(status_code=422, detail="The coding gate is not running.")
        context.coding_gate.resume_budget(payload.repo, payload.session_id, actor_id=actor.actor_id)
        return budget_payload(context)


@app.post("/api/coding/jev/test")
def test_jev(actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    """Ask Jev to classify one command with the saved key: proves the key works."""
    from sololicense.coding import jev

    with _lock:
        gate = get_context().coding_gate
        if gate is None or not gate.jev_client.enabled:
            raise HTTPException(status_code=422, detail="No TypeSafe API key saved yet.")
        verdict = jev.classify_command(gate.jev_client, "npm run build && npm test", ".")
        if verdict is None:
            raise HTTPException(status_code=502, detail="Jev did not answer. Check the key and the endpoint.")
        return {"ok": True, "action_class": verdict.action_class, "confidence": verdict.confidence,
                "irreversible": verdict.irreversible}


@app.post("/api/hooks/{agent}/{native_event}")
def agent_hook(
    agent: Annotated[str, Path(max_length=40, pattern=r"^[a-z0-9-]+$")],
    native_event: Annotated[str, Path(max_length=60, pattern=r"^[A-Za-z][A-Za-z0-9_.]*$")],
    request: Request,
    body: dict = Body(default_factory=dict),
    envelope: bool = Query(default=False),
    x_solo_hook_key: str | None = Header(default=None),
) -> dict:
    """Any coding agent's native hook event. The payload is translated to the
    gate's common event and the answer back into that agent's own format.
    ``envelope=1`` (used by the command shim) wraps it as body + exit code."""
    from sololicense.coding import agents

    try:
        spec = agents.resolve(agent)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    with _lock:
        context = get_context()
        if not _hook_allowed(context, request, x_solo_hook_key):
            raise HTTPException(status_code=401, detail="Invalid hook key.")
        gate = context.coding_gate
        translated = agents.normalize(spec.key, native_event, body)
        if gate is None or translated is None:
            native = agents.Native()
        else:
            event, payload = translated
            payload = _client_fields(payload)
            payload["_agent"] = spec.key
            # Only a hook that fires when a person would be prompted can stand
            # for that person's yes: Claude Code's and Codex's PermissionRequest.
            payload["_prompt_only"] = native_event == "PermissionRequest" and spec.key in ("claude-code", "codex")
            if event == "user-prompt":
                answer = gate.user_prompt(payload)
            elif event == "subagent-start":
                answer = gate.subagent_start(payload)
            elif event == "pre-tool":
                answer = gate.pre_tool(payload)
            elif event == "permission":
                answer = gate.permission(payload)
            elif event == "stop":
                answer = gate.stop(payload)
            elif event == "subagent-stop":
                answer = gate.subagent_stop(payload)
            elif event == "person-asked":
                answer = gate.person_asked(payload)
            else:
                answer = gate.tool_result(payload, failed=event == "post-tool-failure")
            native = agents.render(spec.key, native_event, answer)
        if envelope:
            return native.envelope()
        return native.body or {}


@app.get("/api/coding/agents")
def coding_agents() -> dict:
    """Supported agents and how each one is installed (public: no data)."""
    from sololicense.coding import agents

    return {"agents": [
        {"key": a.key, "label": a.label, "transport": a.transport, "config_path": a.config_path,
         "can_send_back": a.can_send_back, "notes": a.notes, "docs": a.docs,
         "install": f"solo-license init --agent {a.key}"}
        for a in agents.AGENTS.values()
    ], "unsupported": agents.UNSUPPORTED}


@app.get("/api/coding/install")
def coding_install(agent: str = Query(default="auto", max_length=40, pattern=r"^[a-z0-9-]+$")) -> dict:
    """Everything a person needs to wire one agent: the one-liner, the
    command to keep the gate running, and a prompt their agent can follow."""
    from sololicense.cli import GLOBAL_ONE_LINER, GLOBAL_STEPS, INSTALL_ONE_LINER, REPO_URL, agent_prompt

    return {
        "agent": agent,
        "global_one_liner": GLOBAL_ONE_LINER,
        "global_steps": [*GLOBAL_STEPS, "solo-license doctor"],
        "one_liner": INSTALL_ONE_LINER.replace("--agent auto", f"--agent {agent}"),
        "persistent": f"uv tool install git+{REPO_URL}",
        "init": f"solo-license init --agent {agent}",
        "serve": "solo-license serve",
        "doctor": "solo-license doctor",
        "prompt": agent_prompt(agent),
        "claude_plugin": ["/plugin marketplace add JAYATIAHUJA/Solo_license",
                          "/plugin install solo-license@solo-license"],
    }



# --- coding policy: who decides how far an agent may go ----------------------------

class CodingPolicyPayload(BaseModel):
    repo: str = Field(min_length=1, max_length=200, pattern=r"^[^/\\]+$")   # a repo name, or "*" for all
    classes: dict[str, int] = Field(default_factory=dict)
    deny_commands: list[str] = Field(default_factory=list, max_length=50)
    deny_paths: list[str] = Field(default_factory=list, max_length=50)
    freeze: bool = False
    tools: dict[str, dict] = Field(default_factory=dict)   # glob on the tool name -> {risk, ceiling, forbidden}


class FreezePayload(BaseModel):
    repo: str = Field(default="*", min_length=1, max_length=200, pattern=r"^[^/\\]+$")
    enabled: bool


def coding_policy_payload(context: AppContext, repo: str) -> dict:
    from sololicense.coding import policy as policy_mod

    row = context.conn.execute("SELECT path FROM agent_repos WHERE repo = ?", (repo,)).fetchone()
    path = row["path"] if row else None
    file_policy = policy_mod.from_file(path) if path else None
    all_repos = policy_mod.local(context.conn, policy_mod.ALL_REPOS)
    this_repo = policy_mod.local(context.conn, repo) if repo != policy_mod.ALL_REPOS else None
    effective = policy_mod.merge(file_policy, all_repos, this_repo)
    return {
        "repo": repo,
        "path": path,
        "file": file_policy.to_json() if file_policy else None,
        "file_path": policy_mod.POLICY_FILE.as_posix(),
        "local_all": all_repos.to_json() if all_repos else None,
        "local": this_repo.to_json() if this_repo else None,
        "effective": {**effective.to_json(), "digest": effective.digest},
        "built_in": {k: c.max_level for k, c in ACTION_CLASSES.items()},
        "tool_defaults": dict(policy_mod.TOOL_CEILINGS),
        "starter": policy_mod.STARTER,
    }


@app.get("/api/coding/policy")
def get_coding_policy(
    request: Request,
    repo: str = Query(default="*", max_length=200),
    authorization: str | None = Header(default=None),
) -> dict:
    with _lock:
        context = get_context()
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            current_actor(authorization)
        return coding_policy_payload(context, repo)


def _policy_summary(before: dict | None, after) -> str:
    parts = []
    if after.freeze:
        parts.append("freeze on")
    elif before and before.get("freeze"):
        parts.append("freeze off")
    if after.ceilings:
        parts.append("ceilings " + ", ".join(f"{k}<=L{v}" for k, v in sorted(after.ceilings.items())))
    if after.deny_commands:
        parts.append(f"{len(after.deny_commands)} denied command(s)")
    if after.deny_paths:
        parts.append(f"{len(after.deny_paths)} denied path(s)")
    if after.tools:
        parts.append(f"{len(after.tools)} tool rule(s)")
    return "; ".join(parts) or "no extra rules"


@app.put("/api/coding/policy")
def put_coding_policy(payload: CodingPolicyPayload, actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    """This machine's policy for one repo (or all). It can only tighten."""
    from sololicense.coding import policy as policy_mod

    with _lock:
        context = get_context()
        before = policy_mod.local(context.conn, payload.repo)
        try:
            saved = policy_mod.save_local(context.conn, payload.repo, {
                "classes": {k: {"max": v} for k, v in payload.classes.items()},
                "deny": {"commands": payload.deny_commands, "paths": payload.deny_paths},
                "freeze": {"enabled": payload.freeze},
                "tools": payload.tools,
            })
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if context.coding_gate is not None:
            context.coding_gate.record_policy(payload.repo, _policy_summary(before.to_json() if before else None, saved),
                                              actor.actor_id)
        context.conn.commit()
        return coding_policy_payload(context, payload.repo)


@app.post("/api/coding/freeze")
def freeze_coding(payload: FreezePayload, actor: Actor = Depends(require_role(Role.APPROVER))) -> dict:
    """The kill switch: every action asks, for one repo or all of them."""
    from sololicense.coding import policy as policy_mod

    with _lock:
        context = get_context()
        current = policy_mod.local(context.conn, payload.repo) or policy_mod.Policy()
        raw = {**current.to_raw(), "freeze": {"enabled": payload.enabled}}
        policy_mod.save_local(context.conn, payload.repo, raw)
        if context.coding_gate is not None:
            where = "all repositories" if payload.repo == policy_mod.ALL_REPOS else payload.repo
            context.coding_gate.record_policy(
                payload.repo, f"{'freeze on' if payload.enabled else 'freeze off'} for {where}", actor.actor_id)
        context.conn.commit()
        return coding_payload(context)


# --- the dashboard, served by the gate itself when it has been built -------------------

def dashboard_dir() -> Path | None:
    """``SOLO_DASHBOARD_DIR``, else ``frontend/dist`` next to this checkout (``npm run build``)."""
    from pathlib import Path as _Path

    configured = os.environ.get("SOLO_DASHBOARD_DIR", "").strip()
    candidates = [_Path(configured)] if configured else []
    candidates.append(_Path(__file__).resolve().parents[2] / "frontend" / "dist")
    return next((c for c in candidates if (c / "index.html").is_file()), None)


from starlette.exceptions import HTTPException as _StarletteHTTPException  # noqa: E402
from fastapi.exception_handlers import http_exception_handler as _default_http_handler  # noqa: E402


@app.exception_handler(_StarletteHTTPException)
async def dashboard_or_error(request: Request, exc: _StarletteHTTPException):
    """The built dashboard (landing, setup guide, app) on the gate's own port, so
    ``solo-license onboard`` can open it without a separate web server. Only a
    GET that no API route answered gets it; everything else keeps its error."""
    from fastapi.responses import FileResponse

    root = dashboard_dir()
    path = request.url.path.lstrip("/")
    if exc.status_code != 404 or request.method != "GET" or root is None or path.startswith("api/"):
        return await _default_http_handler(request, exc)
    target = (root / path).resolve()
    if path and target.is_file() and target.is_relative_to(root.resolve()):
        return FileResponse(target)
    return FileResponse(root / "index.html")
