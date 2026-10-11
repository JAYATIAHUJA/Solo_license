"""HTTP adapter for the Solo License application services.

The React client talks only to this file. Domain, worker, verification, SQLite,
and the git-backed ledger remain the implementation in ``sololicense``.
"""

from __future__ import annotations

import os
import re
import secrets
from contextlib import asynccontextmanager
from dataclasses import replace
from hashlib import sha256
from threading import RLock

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from sololicense.agent.intake import complete, parse_message
from sololicense.bootstrap import AppContext, build_app
from sololicense.config import PROVIDERS
from sololicense.connectors import ConnectorError
from sololicense.connectors.csv_import import orders_to_csv, parse_orders_csv
from sololicense.db.repositories import tickets as tickets_repo
from sololicense.db.repositories import events as events_repo
from sololicense.db.repositories import license as license_repo
from sololicense.db.repositories import orders as orders_repo
from sololicense.db.repositories import runs as runs_repo
from sololicense.db.repositories import settings as settings_repo
from sololicense.db.seed import SEED_ORDERS, install_sample_store, seed
from sololicense.domain.license import LicenseLevel, LicenseState
from sololicense.domain.models import FaultMode, RefundRequest, RunStatus
from sololicense.domain.task_classes import DEFAULT_TASK_CLASS, TASK_CLASSES
from sololicense.observability.neatlogs_probe import response_for, run_doctor_probe
from sololicense.security import Actor, Role, TokenAuthenticator, permits
from sololicense.services import economics
from sololicense.services.alerts import AlertNotifier, valid_webhook_url
from sololicense.services.evidence import build_packet

SECRET_KEYS = tuple(sorted(settings_repo.SECRET_KEYS))
ECON_KEYS = tuple(economics.SETTING_DEFAULTS)
SETTING_KEYS = (
    "business_name", "llm_provider",
    *(spec.model_field for spec in PROVIDERS.values() if spec.model_field),
    "compat_base_url",
    "trust_confidence", "refund_window_days", "orders_source",
    "l2_auto_refund_ceiling", "l2_auto_credit_ceiling",
    "neatlogs_project", *ECON_KEYS, *SECRET_KEYS,
)
_NUMERIC_KEYS = ("trust_confidence", "refund_window_days", "l2_auto_refund_ceiling", "l2_auto_credit_ceiling", *ECON_KEYS)
ORDER_SOURCES = ("sample", "csv", "stripe")

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("SOLO_ALLOWED_ORIGINS", "http://localhost:5174").split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- payloads -------------------------------------------------------------

def _task_class_field():
    return Field(default=DEFAULT_TASK_CLASS, max_length=40)


class RefundPayload(BaseModel):
    order_id: str
    amount: float | None = Field(default=None, ge=0)
    reason: str = "customer request"
    task_class: str = _task_class_field()
    idempotency_key: str | None = Field(default=None, max_length=120)


class IntakePayload(BaseModel):
    message: str = Field(min_length=3, max_length=4000)
    sender: str | None = Field(default=None, max_length=200)
    run: bool = True


class InboxPayload(BaseModel):
    """What a helpdesk or email forwarder posts. Common field names are accepted."""

    body: str = Field(default="", max_length=4000)
    text: str = Field(default="", max_length=4000)
    message: str = Field(default="", max_length=4000)
    sender: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=200)
    subject: str = Field(default="", max_length=300)

    @property
    def content(self) -> str:
        return (self.body or self.text or self.message).strip()

    @property
    def from_address(self) -> str:
        return (self.sender or self.email).strip()


class CsvPayload(BaseModel):
    csv: str = Field(min_length=1, max_length=5_000_000)


class StripeSamplePayload(BaseModel):
    confirm_test_mode: bool = False


class FaultPayload(BaseModel):
    mode: FaultMode
    task_class: str = _task_class_field()


class RestorePayload(BaseModel):
    level: int
    reason: str = "Human restored after evidence review."
    task_class: str = _task_class_field()


class OrderPayload(BaseModel):
    order_id: str = Field(min_length=3, max_length=32)
    customer: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0, le=1_000_000)


class SettingsPayload(BaseModel):
    values: dict[str, str | int | float | None]


class OnboardingPayload(BaseModel):
    business_name: str = ""
    starting_level: int = 0
    starting_levels: dict[str, int] = {}
    load_sample_orders: bool = True
    orders: list[OrderPayload] = []
    orders_csv: str | None = Field(default=None, max_length=5_000_000)
    values: dict[str, str | int | float | None] = {}


class DemoSessionPayload(BaseModel):
    name: str = Field(default="", max_length=40)


class TopUpPayload(BaseModel):
    task_class: str = _task_class_field()
    count: int = Field(default=4, ge=1, le=12)


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


def _task_class(value: str) -> str:
    key = value.strip().lower()
    if key not in TASK_CLASSES:
        raise HTTPException(status_code=422, detail=f"Unknown task class '{value}'.")
    return key


# --- serialization ----------------------------------------------------------

def _mask(value: str) -> str:
    return f"••••{value[-4:]}" if len(value) > 4 else ("••••" if value else "")


def serialize_providers() -> list[dict]:
    return [
        {
            "key": key,
            "label": spec.label,
            "needs_key": spec.key_field is not None,
            "key_field": spec.key_field,
            "model_field": spec.model_field,
            "default_model": spec.default_model,
            "needs_base_url": spec.needs_base_url,
        }
        for key, spec in PROVIDERS.items()
    ]


def serialize_task_classes(context: AppContext) -> list[dict]:
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "verb": spec.verb,
            "description": spec.description,
            "effect_column": spec.effect_column,
            "ceiling": context.config.ceiling_for(spec.key),
        }
        for spec in TASK_CLASSES.values()
    ]


def serialize_settings(context: AppContext) -> dict:
    stored = settings_repo.get_all(context.conn)
    cfg = context.config
    out = {
        "onboarded": stored.get("onboarded") == "1",
        "business_name": stored.get("business_name", ""),
        "llm_provider": cfg.llm_provider,
        "llm_enabled": cfg.llm_enabled,
        "llm_model": cfg.llm_model,
        "compat_base_url": cfg.compat_base_url,
        "trust_confidence": cfg.trust_confidence,
        "refund_window_days": cfg.refund_window_days,
        "orders_source": stored.get("orders_source", ""),
        "stripe_connected": bool(cfg.stripe_secret_key),
        "inbox_path": "/api/inbox",
        "l2_auto_refund_ceiling": cfg.l2_auto_refund_ceiling,
        "l2_auto_credit_ceiling": cfg.l2_auto_credit_ceiling,
        "neatlogs_project": cfg.neatlogs_project,
        "neatlogs_enabled": cfg.neatlogs_enabled,
        "alerts_enabled": valid_webhook_url(cfg.alert_webhook_url),
        "demo_mode": cfg.demo_mode,
    }
    for spec in PROVIDERS.values():
        if spec.model_field:
            out[spec.model_field] = getattr(cfg, spec.model_field)
    for key in SECRET_KEYS:
        value = getattr(cfg, key, "")
        out[f"has_{key}"] = bool(value)
        out[f"{key}_hint"] = _mask(value)
    assumptions = economics.Assumptions.from_settings(stored)
    for key in ECON_KEYS:
        out[key] = getattr(assumptions, key.removeprefix("econ_"))
    return out


def serialize_state(state: LicenseState, progress: dict | None = None) -> dict:
    return {
        "task_class": state.task_class,
        "level": int(state.level),
        "effective_level": int(state.effective_level),
        "clean_runs": state.consecutive_clean_runs,
        "successes": state.successes,
        "failures": state.failures,
        "progress": progress or {},
        "quarantined": state.quarantined,
        "demoted_from": int(state.demoted_from) if state.demoted_from is not None else None,
    }


def serialize_packet(context: AppContext, run_id: int | None) -> dict | None:
    if run_id is None:
        return None
    packet = build_packet(context.conn, run_id, context.config)
    if packet is None:
        return None
    return {
        "run": packet.run,
        "order": packet.order,
        "detections": packet.detections,
        "spans": packet.spans,
        "license_history": packet.license_history,
        "neatlogs_link": packet.neatlogs_link,
        "before_refunded": packet.before_refunded,
        "after_refunded": packet.after_refunded,
        "intended_delta": packet.intended_delta,
        "actual_delta": packet.actual_delta,
    }


_STATS_SQL = """
    SELECT COUNT(*) AS total,
           SUM(status = 'clean') AS clean,
           SUM(status = 'demoted') AS demoted,
           SUM(status = 'pending_approval') AS pending,
           SUM(status = 'suggested') AS suggested,
           SUM(executed) AS executed,
           SUM(fault_mode != 'none') AS faulted,
           COALESCE(SUM(CASE WHEN status = 'clean'
                             THEN after_refunded - before_refunded END), 0) AS paid
      FROM runs
"""


def _stats_row(row) -> dict:
    return {
        "total_runs": row["total"] or 0,
        "clean_runs": row["clean"] or 0,
        "demotions": row["demoted"] or 0,
        "pending_approval": row["pending"] or 0,
        "suggested": row["suggested"] or 0,
        "executed": row["executed"] or 0,
        "faults_injected": row["faulted"] or 0,
        # Every injected fault that executed was caught (it demoted) — the
        # false-success count that reached the customer is the difference.
        "paid_out": round(row["paid"] or 0, 2),
    }


def _stats(context: AppContext) -> dict:
    overall = _stats_row(context.conn.execute(_STATS_SQL).fetchone())
    overall["refunded_total"] = overall["paid_out"]  # legacy key
    overall["by_class"] = {
        key: _stats_row(context.conn.execute(_STATS_SQL + " WHERE task_class = ?", (key,)).fetchone())
        for key in TASK_CLASSES
    }
    return overall


def _licenses(context: AppContext) -> dict[str, LicenseState]:
    return {key: context.license_service.get_or_create(key) for key in TASK_CLASSES}


def _observability(context: AppContext) -> dict:
    cfg = context.config
    ledger = context.conn.execute(
        "SELECT COUNT(*) AS n, SUM(git_sha IS NOT NULL) AS committed FROM license_events"
    ).fetchone()
    return {
        "neatlogs": {
            "enabled": cfg.neatlogs_enabled,
            "project": cfg.neatlogs_project,
            "app_url": cfg.neatlogs_app_url,
        },
        "llm": {
            "provider": cfg.llm_provider,
            "label": PROVIDERS.get(cfg.llm_provider, PROVIDERS["deterministic"]).label,
            "model": cfg.llm_model,
            "enabled": cfg.llm_enabled,
        },
        "ledger": {
            "repo": str(cfg.ledger_repo),
            "events": ledger["n"] or 0,
            "commits": ledger["committed"] or 0,
        },
        "alerts": {"enabled": valid_webhook_url(cfg.alert_webhook_url)},
    }


def dashboard_payload(context: AppContext, selected_run_id: int | None = None) -> dict:
    runs = [dict(row) for row in runs_repo.list_recent(context.conn, limit=100)]
    if runs:
        marks = ",".join("?" * len(runs))
        rules: dict[int, list[str]] = {}
        for row in context.conn.execute(
            f"SELECT run_id, rule FROM detections WHERE run_id IN ({marks}) ORDER BY id",
            [r["id"] for r in runs],
        ):
            rules.setdefault(row["run_id"], []).append(row["rule"])
        for r in runs:
            r["problems"] = rules.get(r["id"], [])
    selected = selected_run_id or (runs[0]["id"] if runs else None)
    intakes = [
        dict(r) for r in context.conn.execute(
            "SELECT * FROM intakes ORDER BY id DESC LIMIT 20"
        ).fetchall()
    ]
    licenses = _licenses(context)
    stored = settings_repo.get_all(context.conn)
    orders = []
    for row in orders_repo.list_orders(context.conn):
        order = dict(row)
        order["remaining"] = orders_repo.remaining_balance(row)
        orders.append(order)
    events = [
        dict(e) for e in context.conn.execute(
            "SELECT * FROM license_events ORDER BY id DESC LIMIT 60"
        ).fetchall()
    ]
    armed = {key: context.fault_injector.peek(key).value for key in TASK_CLASSES}
    return {
        "settings": serialize_settings(context),
        "warnings": list(context.warnings),
        "providers": serialize_providers(),
        "task_classes": serialize_task_classes(context),
        "licenses": {
            key: serialize_state(state, context.license_service.progress(state))
            for key, state in licenses.items()
        },
        "license": serialize_state(
            licenses[DEFAULT_TASK_CLASS], context.license_service.progress(licenses[DEFAULT_TASK_CLASS])
        ),
        "trust": {
            "confidence": context.config.trust_confidence,
            "incident_cost": context.license_service.ladder.incident_cost,
            "hourly_cost": context.license_service.ladder.hourly_cost,
            "break_even": {
                str(level): round(context.license_service.ladder.step(level).target_rate, 4)
                for level in range(context.license_service.ladder.top)
            },
        },
        "config": {
            "l2_auto_refund_ceiling": context.config.l2_auto_refund_ceiling,
            "ceilings": {key: context.config.ceiling_for(key) for key in TASK_CLASSES},
        },
        "stats": _stats(context),
        "economics": economics.workspace_economics(
            context.conn,
            {key: int(state.effective_level) for key, state in licenses.items()},
            stored,
        ),
        "observability": _observability(context),
        "orders": orders,
        "runs": runs,
        "intakes": intakes,
        "tickets": tickets_repo.list_recent(context.conn, limit=60),
        "events": events,
        "armed_faults": armed,
        "armed_fault": armed[DEFAULT_TASK_CLASS],
        "packet": serialize_packet(context, selected),
    }


def make_idempotency_key(namespace: str, *parts: object) -> str:
    normalized = "\x1f".join(str(part).strip().lower() for part in parts)
    return f"{namespace}:{sha256(normalized.encode('utf-8')).hexdigest()[:32]}"


def _run(context: AppContext, order_id: str, amount: float | None, reason: str,
         *, task_class: str = DEFAULT_TASK_CLASS, approved: bool = False,
         idempotency_key: str | None = None, actor: Actor):
    order = orders_repo.get_order(context.conn, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")
    remaining = orders_repo.remaining_balance(order)
    value = remaining if amount is None else float(amount)
    if value <= 0:
        raise HTTPException(status_code=422, detail=f"{order_id} has nothing left to pay out.")
    if value > remaining + 1e-9:
        raise HTTPException(
            status_code=422,
            detail=f"${value:.2f} exceeds the ${remaining:.2f} still payable on {order_id}.",
        )
    return context.worker.run_refund(
        RefundRequest(order["order_id"], order["customer"], value, reason),
        task_class=task_class,
        approved=approved,
        idempotency_key=idempotency_key,
        actor=actor,
    )


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
    recorded as the actor on every run and license change."""
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
def get_dashboard(
    run_id: int | None = None,
    actor: Actor = Depends(require_role(Role.OPERATOR)),
) -> dict:
    with _lock:
        return dashboard_payload(get_context(), run_id)


@app.get("/api/settings")
def get_settings(actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    with _lock:
        return serialize_settings(get_context())


# --- agent ----------------------------------------------------------------

@app.post("/api/refunds")
@app.post("/api/runs")
def run_action(
    payload: RefundPayload, actor: Actor = Depends(require_role(Role.OPERATOR))
) -> dict:
    with _lock:
        context = get_context()
        task_class = _task_class(payload.task_class)
        order_id = payload.order_id.strip().upper()
        key = payload.idempotency_key or make_idempotency_key(
            "manual", task_class, order_id, payload.amount or "", payload.reason
        )
        result = _run(context, order_id, payload.amount, payload.reason,
                      task_class=task_class, idempotency_key=key, actor=actor)
        return dashboard_payload(context, result.run_id)


def _handle_ticket(context: AppContext, ticket_id: int, actor: Actor) -> dict:
    ticket = tickets_repo.get(context.conn, ticket_id)
    outcome = context.agent.handle(
        ticket["body"],
        sender=ticket["sender"],
        ticket_id=ticket_id,
        idempotency_key=make_idempotency_key("ticket", ticket_id),
        actor=actor,
    )
    tickets_repo.record_outcome(context.conn, ticket_id, outcome)
    intake = outcome.intake
    context.conn.execute(
        "INSERT INTO intakes (message, order_id, amount, reason, source, run_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (ticket["body"], outcome.order_id, outcome.amount,
         intake.reason if intake else None, intake.source if intake else "agent", outcome.run_id),
    )
    context.conn.commit()
    return {
        "ticket_id": ticket_id,
        "status": outcome.status,
        "summary": outcome.summary,
        "reply": outcome.reply,
        "steps": [s.as_dict() for s in outcome.steps],
        "order_id": outcome.order_id,
        "amount": outcome.amount,
        "task_class": outcome.task_class,
        "run_id": outcome.run_id,
        "trace_id": outcome.trace_id,
        "source": intake.source if intake else None,
        "confidence": intake.confidence if intake else None,
        "note": intake.note if intake else "",
    }


@app.post("/api/intake")
def intake(
    payload: IntakePayload, actor: Actor = Depends(require_role(Role.OPERATOR))
) -> dict:
    """A pasted customer message, handled end to end by the ticket agent."""
    with _lock:
        context = get_context()
        if not payload.run:
            parsed = parse_message(payload.message, context.config, context.conn)
            body = dashboard_payload(context)
            body["intake"] = {"order_id": parsed.order_id, "amount": parsed.amount,
                              "task_class": parsed.task_class, "source": parsed.source,
                              "needs_human": parsed.needs_human, "note": parsed.note}
            return body
        ticket_id = tickets_repo.insert(context.conn, source="paste", sender=payload.sender, body=payload.message)
        result = _handle_ticket(context, ticket_id, actor)
        body = dashboard_payload(context, result["run_id"])
        body["intake"] = result
        return body


@app.post("/api/tickets/{ticket_id}/handle")
def handle_ticket(ticket_id: int, actor: Actor = Depends(require_role(Role.OPERATOR))) -> dict:
    with _lock:
        context = get_context()
        ticket = tickets_repo.get(context.conn, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Message not found.")
        if ticket["status"] != "new":
            # Re-running would flag a duplicate action and demote the license
            # for a double-submit that was never a fresh customer request.
            raise HTTPException(status_code=409, detail="This message was already handled.")
        result = _handle_ticket(context, ticket_id, actor)
        body = dashboard_payload(context, result["run_id"])
        body["intake"] = result
        return body


@app.post("/api/tickets/handle-new")
def handle_new_tickets(actor: Actor = Depends(require_role(Role.OPERATOR))) -> dict:
    """Let the agent work through every unhandled message in the inbox."""
    with _lock:
        context = get_context()
        handled = [_handle_ticket(context, t["id"], actor) for t in tickets_repo.list_new(context.conn)]
        body = dashboard_payload(context)
        body["handled"] = handled
        return body


def _inbox_secret(context: AppContext) -> str:
    """The shared secret for the inbox webhook, created on first use."""
    if context.config.inbox_secret:
        return context.config.inbox_secret
    stored = settings_repo.get_all(context.conn).get("inbox_secret_hint")
    if stored:
        return stored
    secret = "inb_" + secrets.token_urlsafe(18)
    settings_repo.set_many(context.conn, {"inbox_secret_hint": secret})
    context.conn.commit()
    return secret


@app.get("/api/inbox/secret")
def inbox_secret(actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    """The webhook URL path and secret a helpdesk or email forwarder posts to."""
    with _lock:
        context = get_context()
        return {"path": "/api/inbox", "secret": _inbox_secret(context)}


@app.post("/api/inbox")
def inbox_webhook(
    payload: InboxPayload,
    key: str | None = Query(default=None),
    x_solo_inbox_key: str | None = Header(default=None),
) -> dict:
    """Public webhook: a helpdesk trigger, Zapier/Make step or email forwarder
    posts a customer message here; the agent handles it at once and returns
    the reply to send. Authenticated by the workspace's inbox secret."""
    with _lock:
        context = get_context()
        given = x_solo_inbox_key or key or ""
        if not given or not secrets.compare_digest(given, _inbox_secret(context)):
            raise HTTPException(status_code=401, detail="Invalid inbox key.")
        if len(payload.content) < 3:
            raise HTTPException(status_code=422, detail="The message is empty.")
        ticket_id = tickets_repo.insert(
            context.conn, source="webhook", sender=payload.from_address or None,
            subject=payload.subject or None, body=payload.content,
        )
        actor = Actor(actor_id="inbox:webhook", role=Role.OPERATOR)
        result = _handle_ticket(context, ticket_id, actor)
        return {k: result[k] for k in ("ticket_id", "status", "summary", "reply", "run_id", "trace_id")}


@app.post("/api/runs/{run_id}/reject")
def reject_run(run_id: int, actor: Actor = Depends(require_role(Role.APPROVER))) -> dict:
    """A person says the agent's proposal was wrong. Counted as a failure in
    the job type's evidence, so it needs more successes to climb."""
    with _lock:
        context = get_context()
        run = runs_repo.get_run(context.conn, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        if run["status"] not in ("pending_approval", "suggested"):
            raise HTTPException(status_code=409, detail="Run is not awaiting approval.")
        context.license_service.apply_rejection(run["task_class"])
        context.conn.execute("UPDATE runs SET status = ? WHERE id = ?", (RunStatus.REJECTED.value, run_id))
        context.conn.commit()
        return dashboard_payload(context, run_id)


@app.post("/api/runs/{run_id}/approve")
def approve_run(
    run_id: int, actor: Actor = Depends(require_role(Role.APPROVER))
) -> dict:
    """Human approves a draft (L1 / over the L2 ceiling) or acts on an L0
    suggestion. The approved execution is still verified and, when clean,
    earns track-record credit — that is how a class climbs off L0."""
    with _lock:
        context = get_context()
        run = runs_repo.get_run(context.conn, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        if run["status"] not in ("pending_approval", "suggested"):
            raise HTTPException(status_code=409, detail="Run is not awaiting approval.")
        task_class = run["task_class"]
        if context.license_service.get_or_create(task_class).quarantined:
            raise HTTPException(status_code=409, detail="The class is quarantined. Restore it before approving runs.")
        result = _run(context, run["order_id"], run["requested_amount"],
                      "approved by human", task_class=task_class, approved=True,
                      idempotency_key=make_idempotency_key("approval", run_id),
                      actor=actor)
        context.conn.execute(
            "UPDATE runs SET status = ? WHERE id = ?",
            (RunStatus.APPROVED.value, run_id),
        )
        context.conn.commit()
        return dashboard_payload(context, result.run_id)


@app.post("/api/faults")
def arm_fault(
    payload: FaultPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    with _lock:
        context = get_context()
        context.fault_injector.arm(_task_class(payload.task_class), payload.mode)
        return dashboard_payload(context)


@app.post("/api/restore")
def restore_license(
    payload: RestorePayload, actor: Actor = Depends(require_role(Role.APPROVER))
) -> dict:
    with _lock:
        context = get_context()
        try:
            target = LicenseLevel(payload.level)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Unknown license level.") from error
        context.license_service.restore_license(
            _task_class(payload.task_class), target, reason=payload.reason, actor=actor
        )
        return dashboard_payload(context)


# --- orders ---------------------------------------------------------------

def _insert_order(context: AppContext, payload: OrderPayload) -> None:
    order_id = payload.order_id.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{2,31}", order_id):
        raise HTTPException(status_code=422, detail="Order id may use letters, digits and dashes.")
    if orders_repo.get_order(context.conn, order_id) is not None:
        raise HTTPException(status_code=409, detail=f"{order_id} already exists.")
    context.conn.execute(
        "INSERT INTO orders (order_id, customer, amount) VALUES (?, ?, ?)",
        (order_id, payload.customer.strip(), round(payload.amount, 2)),
    )


@app.post("/api/orders")
def add_order(
    payload: OrderPayload, actor: Actor = Depends(require_role(Role.OPERATOR))
) -> dict:
    with _lock:
        context = get_context()
        _insert_order(context, payload)
        context.conn.commit()
        return dashboard_payload(context)


@app.post("/api/orders/import")
def import_orders(payload: CsvPayload, actor: Actor = Depends(require_role(Role.OPERATOR))) -> dict:
    """Load orders from a CSV export (Shopify, WooCommerce, a spreadsheet …)."""
    with _lock:
        context = get_context()
        records, problems = parse_orders_csv(payload.csv)
        if not records:
            raise HTTPException(status_code=422, detail=" ".join(problems) or "No orders found in the file.")
        added, updated = orders_repo.upsert_orders(context.conn, records)
        context.conn.commit()
        body = dashboard_payload(context)
        body["import"] = {"added": added, "updated": updated, "problems": problems[:20]}
        return body


@app.get("/api/orders/export", response_class=PlainTextResponse)
def export_orders(actor: Actor = Depends(require_role(Role.OPERATOR))) -> str:
    with _lock:
        context = get_context()
        return orders_to_csv([dict(r) for r in orders_repo.list_orders(context.conn)])


@app.get("/api/runs/export", response_class=PlainTextResponse)
def export_runs(actor: Actor = Depends(require_role(Role.OPERATOR))) -> str:
    """Every run with its verified numbers — for an accountant or an audit."""
    import csv
    import io

    with _lock:
        context = get_context()
        rows = [dict(r) for r in context.conn.execute("SELECT * FROM runs ORDER BY id").fetchall()]
    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out.getvalue()


def _stripe(context: AppContext):
    try:
        return context.connectors.stripe()
    except ConnectorError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/connectors/stripe/test")
def test_stripe(payload: SettingsPayload, actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    """Try a Stripe key from the form before saving it."""
    from sololicense.connectors.stripe import StripeConnector

    key = str(payload.values.get("stripe_secret_key") or "").strip()
    with _lock:
        context = get_context()
        if not key or key.startswith("••"):
            key = context.config.stripe_secret_key
        api_base = context.config.stripe_api_base
    if not key:
        return {"ok": False, "message": "Paste a Stripe secret key first (Developers → API keys)."}
    try:
        connector = StripeConnector(key, api_base=api_base, allow_live=os.environ.get("SOLO_ALLOW_LIVE_STRIPE") == "1")
        return {"ok": True, "message": connector.check()}
    except ConnectorError as error:
        return {"ok": False, "message": str(error)}


@app.post("/api/connectors/stripe/sync")
def sync_stripe(actor: Actor = Depends(require_role(Role.OPERATOR))) -> dict:
    """Import recent paid Stripe charges as orders (refunds as Stripe reports them)."""
    with _lock:
        context = get_context()
        try:
            records = _stripe(context).list_orders()
        except ConnectorError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        added, updated = orders_repo.upsert_orders(context.conn, records)
        context.conn.commit()
        body = dashboard_payload(context)
        body["import"] = {"added": added, "updated": updated, "problems": []}
        return body


@app.post("/api/connectors/stripe/sample")
def stripe_sample_orders(
    payload: StripeSamplePayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    """Create the sample orders as paid charges in a Stripe *test* account, then sync."""
    if not payload.confirm_test_mode:
        raise HTTPException(status_code=422, detail="Confirm that this is a Stripe test account.")
    with _lock:
        context = get_context()
        samples = [{"order_id": o.order_id, "customer": o.customer, "email": o.email, "amount": o.amount}
                   for o in SEED_ORDERS]
        try:
            stripe = _stripe(context)
            stripe.create_sample_orders(samples)
            records = stripe.list_orders()
        except ConnectorError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        added, updated = orders_repo.upsert_orders(context.conn, records)
        context.conn.commit()
        body = dashboard_payload(context)
        body["import"] = {"added": added, "updated": updated, "problems": []}
        return body


@app.delete("/api/orders/{order_id}")
def delete_order(
    order_id: str, actor: Actor = Depends(require_role(Role.OPERATOR))
) -> dict:
    with _lock:
        context = get_context()
        order_id = order_id.strip().upper()
        used = context.conn.execute(
            "SELECT 1 FROM runs WHERE order_id = ? LIMIT 1", (order_id,)
        ).fetchone()
        if used:
            raise HTTPException(status_code=409, detail="Order has runs on record and cannot be deleted.")
        context.conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
        context.conn.commit()
        return dashboard_payload(context)


# --- settings & onboarding ------------------------------------------------

def _clean_values(values: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in values.items():
        if key not in SETTING_KEYS or value is None:
            continue
        text = str(value).strip()
        if key in SECRET_KEYS and (not text or text.startswith("••")):
            continue  # blank / masked -> keep the stored secret
        out[key] = text
    if "llm_provider" in out and out["llm_provider"] not in PROVIDERS:
        raise HTTPException(status_code=422, detail="Unknown LLM provider.")
    if out.get("compat_base_url") and not out["compat_base_url"].startswith("https://"):
        raise HTTPException(status_code=422, detail="The OpenAI-compatible base URL must use https://.")
    if out.get("orders_source") and out["orders_source"] not in ORDER_SOURCES:
        raise HTTPException(status_code=422, detail="Unknown orders source.")
    if out.get("stripe_secret_key"):
        from sololicense.connectors.stripe import key_mode

        mode = key_mode(out["stripe_secret_key"])
        if mode is None:
            raise HTTPException(status_code=422, detail="That does not look like a Stripe secret key (sk_test_…).")
        if mode == "live" and os.environ.get("SOLO_ALLOW_LIVE_STRIPE") != "1":
            raise HTTPException(status_code=422, detail="Use a Stripe test-mode key (sk_test_…).")
    if out.get("alert_webhook_url") and not valid_webhook_url(out["alert_webhook_url"]):
        raise HTTPException(status_code=422, detail="The alert webhook must be an https:// URL.")
    try:
        for key in _NUMERIC_KEYS:
            if key in out and float(out[key]) < 0:
                raise ValueError
        if "trust_confidence" in out and not 0.5 <= float(out["trust_confidence"]) <= 0.999:
            raise ValueError
        if "refund_window_days" in out:
            out["refund_window_days"] = str(int(float(out["refund_window_days"])))
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid numeric setting.") from error
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


@app.post("/api/settings/test-llm")
def test_llm(
    payload: SettingsPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    """Try a provider/key (from the form, before saving) with a tiny call."""
    with _lock:
        context = get_context()
        cfg = _config_with_form(context, _clean_values(payload.values))
    if cfg.llm_provider == "deterministic":
        return {"ok": True, "message": "Built-in rules need no key."}
    if not cfg.llm_enabled:
        return {"ok": False, "message": "Add an API key (and base URL) for this provider first."}
    try:
        reply = complete(cfg, "Reply with the single word: ready", max_tokens=256)
        return {"ok": True, "message": f"Connected to {cfg.llm_model}. Model replied: {reply[:40]}"}
    except Exception as error:  # surfaced to the operator; key never echoed
        return {"ok": False, "message": f"{type(error).__name__}: {str(error)[:200]}"}


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


@app.post("/api/settings/test-alert")
def test_alert(
    payload: SettingsPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    with _lock:
        context = get_context()
        cfg = _config_with_form(context, _clean_values(payload.values))
        business = settings_repo.get_all(context.conn).get("business_name", "")
    notifier = AlertNotifier(url=cfg.alert_webhook_url, business=business)
    if not notifier.enabled:
        return {"ok": False, "message": "Add an https:// webhook URL first."}
    ok, status = notifier.send(
        f"✅ {business or 'Solo License'} alerts are connected. You'll hear here when an agent loses its license."
    )
    return {"ok": ok, "message": f"Delivered ({status})." if ok else f"Delivery failed ({status})."}


@app.post("/api/onboarding/complete")
def complete_onboarding(
    payload: OnboardingPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    with _lock:
        context = get_context()
        # Validate everything before writing anything, so a bad request can
        # never leave a half-onboarded workspace behind.
        values = _clean_values(payload.values)
        levels: dict[str, LicenseLevel] = {}
        try:
            for key in TASK_CLASSES:
                levels[key] = LicenseLevel(payload.starting_levels.get(key, payload.starting_level))
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Unknown license level.") from error
        for key in payload.starting_levels:
            _task_class(key)
        # Validate the payloads that become writes BEFORE the onboarded flag
        # is persisted: a rejected CSV or order id must leave the workspace
        # exactly as it was, not flagged as set up.
        csv_records: list = []
        if payload.orders_csv:
            csv_records, csv_problems = parse_orders_csv(payload.orders_csv)
            if not csv_records:
                raise HTTPException(
                    status_code=422,
                    detail=" ".join(csv_problems) or "No orders found in the file. Check the column headers.",
                )
        for order in payload.orders:
            order_id = order.order_id.strip().upper()
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{2,31}", order_id):
                raise HTTPException(status_code=422, detail=f"Order id {order_id!r} may use letters, digits and dashes.")

        values["business_name"] = payload.business_name.strip()
        values["onboarded"] = "1"
        _save_settings(context, values)
        reset_context()
        context = get_context()
        if csv_records:
            orders_repo.upsert_orders(context.conn, csv_records)
        if payload.load_sample_orders and not orders_repo.list_orders(context.conn):
            install_sample_store(context.conn)
        for order in payload.orders:
            if orders_repo.get_order(context.conn, order.order_id.strip().upper()) is None:
                _insert_order(context, order)
        for key, level in levels.items():
            license_repo.upsert_state(context.conn, LicenseState(task_class=key, level=level))
        context.conn.commit()
        return dashboard_payload(context)


@app.post("/api/reseed")
def reseed_demo(actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    """Reset runs/ledger and reinstall the sample orders (keeps settings)."""
    with _lock:
        context = get_context()
        seed(context.conn, context.config)
        return dashboard_payload(context)


@app.post("/api/demo/top-up")
def top_up_demo_orders(
    payload: TopUpPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    """Add fresh under-ceiling orders so the guided demo always has work to do."""
    with _lock:
        context = get_context()
        ceiling = context.config.ceiling_for(_task_class(payload.task_class))
        base = context.conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"]
        amounts = [round(max(1.0, ceiling * f), 2) for f in (0.3, 0.5, 0.4, 0.6, 0.2, 0.7)]
        added = 0
        n = base
        while added < payload.count:
            n += 1
            order_id = f"DEMO-{2000 + n}"
            if orders_repo.get_order(context.conn, order_id) is not None:
                continue
            context.conn.execute(
                "INSERT INTO orders (order_id, customer, amount, email, ordered_at, source)"
                " VALUES (?, ?, ?, ?, date('now'), 'sample')",
                (order_id, f"Demo customer {n}", amounts[added % len(amounts)], f"customer{n}@example.com"),
            )
            added += 1
        context.conn.commit()
        return dashboard_payload(context)
