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

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from sololicense.agent.intake import complete, parse_message
from sololicense.bootstrap import AppContext, build_app
from sololicense.config import PROVIDERS
from sololicense.connectors import ConnectorError
from sololicense.connectors.csv_import import orders_to_csv, parse_orders_csv
from sololicense.db.repositories import agent as agent_repo
from sololicense.db.repositories import tickets as tickets_repo
from sololicense.db.repositories import events as events_repo
from sololicense.db.repositories import license as license_repo
from sololicense.db.repositories import orders as orders_repo
from sololicense.db.repositories import policies as policy_repo
from sololicense.db.repositories import runs as runs_repo
from sololicense.db.repositories import settings as settings_repo
from sololicense.db.seed import SEED_ORDERS, install_sample_store, seed
from sololicense.domain.license import LicenseLevel, LicenseState
from sololicense.domain.models import FaultMode, RefundRequest, RunStatus
from sololicense.domain.policy import PolicyImpact, PolicyRule, PolicyVersion
from sololicense.domain.task_classes import DEFAULT_TASK_CLASS, TASK_CLASSES
from sololicense.coding.actions import ACTION_CLASSES
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
    "neatlogs_project", "jev_endpoint", *ECON_KEYS, *SECRET_KEYS,
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


class PolicyRulePayload(BaseModel):
    task_class: str = Field(min_length=1, max_length=40)
    allowed_tool: str = Field(min_length=1, max_length=80)
    requires_approval_at_or_above: int = Field(ge=0, le=3)
    l2_ceiling: float = Field(ge=0, le=1_000_000)
    evaluation_window: int = Field(ge=1, le=10_000)
    minimum_samples: int = Field(ge=1, le=10_000)
    minimum_verified_pass_rate: float = Field(ge=0, le=1)


class PolicyPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=1_000)
    rules: list[PolicyRulePayload] = Field(min_length=1, max_length=20)


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
        "jev_enabled": bool(cfg.typesafe_api_key),
        "jev_endpoint": cfg.jev_endpoint,
        "active_policy_version": context.policy_service.active().version,
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


def serialize_policy(policy: PolicyVersion) -> dict:
    """Public policy representation; never includes a permit or secret."""
    return {
        "id": policy.id,
        "version": policy.version,
        "name": policy.name,
        "status": policy.status,
        "summary": policy.summary,
        "created_by": policy.created_by,
        "created_at": policy.created_at,
        "rules": [
            {
                "task_class": rule.task_class,
                "allowed_tool": rule.allowed_tool,
                "requires_approval_at_or_above": rule.requires_approval_at_or_above,
                "l2_ceiling": rule.l2_ceiling,
                "evaluation_window": rule.evaluation_window,
                "minimum_samples": rule.minimum_samples,
                "minimum_verified_pass_rate": rule.minimum_verified_pass_rate,
            }
            for rule in policy.rules
        ],
    }


def serialize_evaluation(context: AppContext, policy: PolicyVersion) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for task_class in TASK_CLASSES:
        progress = context.policy_service.evaluation_for(task_class, policy=policy)
        state = context.license_service.get_or_create(task_class)
        economic = context.license_service.progress(state)
        economics_met = economic["next_level"] is not None and economic["runs_needed"] == 0
        out[task_class] = {
            "sample_size": progress.sample_size,
            "clean_runs": progress.clean_runs,
            "pass_rate": progress.pass_rate,
            "required_samples": progress.required_samples,
            "required_pass_rate": progress.required_pass_rate,
            "eligible": progress.eligible,
            "economic_runs_needed": economic["runs_needed"],
            "economic_upper_bound": economic["upper_bound"],
            "economic_target_rate": economic["target_rate"],
            "ready_to_promote": progress.eligible and economics_met and not state.quarantined,
        }
    return out


def serialize_impact(impact: PolicyImpact) -> dict:
    return {
        "task_class": impact.task_class,
        "previous_version": impact.previous_version,
        "next_version": impact.next_version,
        "action": impact.action,
        "reason": impact.reason,
        "evaluation": {
            "sample_size": impact.evaluation.sample_size,
            "clean_runs": impact.evaluation.clean_runs,
            "pass_rate": impact.evaluation.pass_rate,
            "required_samples": impact.evaluation.required_samples,
            "required_pass_rate": impact.evaluation.required_pass_rate,
            "eligible": impact.evaluation.eligible,
        },
    }


def serialize_impacts(context: AppContext, *, version: int | None = None) -> list[dict]:
    query = "SELECT * FROM policy_impacts"
    values: tuple[object, ...] = ()
    if version is not None:
        query += " WHERE next_version = ?"
        values = (version,)
    query += " ORDER BY id DESC"
    return [dict(row) for row in context.conn.execute(query, values).fetchall()]


def policy_rules_from_payload(payload: PolicyPayload) -> tuple[PolicyRule, ...]:
    try:
        rules = tuple(
            PolicyRule(
                task_class=_task_class(rule.task_class),
                allowed_tool=rule.allowed_tool.strip().lower(),
                requires_approval_at_or_above=rule.requires_approval_at_or_above,
                l2_ceiling=rule.l2_ceiling,
                evaluation_window=rule.evaluation_window,
                minimum_samples=rule.minimum_samples,
                minimum_verified_pass_rate=rule.minimum_verified_pass_rate,
            )
            for rule in payload.rules
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return rules


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
        # Every injected fault that executed was caught (it demoted) - the
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
    active_policy = context.policy_service.active()
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
        "policy": serialize_policy(active_policy),
        "policy_evaluations": serialize_evaluation(context, active_policy),
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


@app.get("/api/policies")
def list_policies(actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    """List immutable policy versions and the active version's evidence."""
    with _lock:
        context = get_context()
        active = context.policy_service.active()
        return {
            "active": serialize_policy(active),
            "versions": [serialize_policy(policy) for policy in policy_repo.list_versions(context.conn)],
            "evaluations": serialize_evaluation(context, active),
        }


@app.post("/api/policies/preview")
def preview_policy(
    payload: PolicyPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    """Calculate policy-change impact without mutating policy or autonomy."""
    with _lock:
        context = get_context()
        rules = policy_rules_from_payload(payload)
        try:
            impacts = context.policy_service.preview_activation(rules)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"impacts": [serialize_impact(impact) for impact in impacts]}


@app.post("/api/policies")
def activate_policy(
    payload: PolicyPayload, actor: Actor = Depends(require_role(Role.ADMIN))
) -> dict:
    """Activate one immutable policy version after explicit admin approval."""
    with _lock:
        context = get_context()
        rules = policy_rules_from_payload(payload)
        try:
            policy = context.policy_service.activate(
                name=payload.name, summary=payload.summary, rules=rules, actor=actor
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "policy": serialize_policy(policy),
            "impacts": serialize_impacts(context, version=policy.version),
        }


@app.get("/api/policy-impacts")
def list_policy_impacts(actor: Actor = Depends(require_role(Role.ADMIN))) -> dict:
    with _lock:
        return {"impacts": serialize_impacts(get_context())}


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
        "follows_ticket_id": outcome.follows_ticket_id,
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
    earns track-record credit - that is how a class climbs off L0."""
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
    """Every run with its verified numbers - for an accountant or an audit."""
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


# --- coding agents: Claude Code hooks ------------------------------------------

_HOOK_EVENTS = {
    "user-prompt": "UserPromptSubmit",
    "permission": "PermissionRequest",
    "post-tool": "PostToolUse",
    "post-tool-failure": "PostToolUseFailure",
    "stop": "Stop",
}


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
    agent: str = Query(default="claude-code", max_length=40, pattern=r"^[a-z0-9-]+$"),
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
        body = {**body, "_agent": agent}
        if event == "user-prompt":
            return gate.user_prompt(body)
        if event == "permission":
            return gate.permission(body)
        if event == "stop":
            return gate.stop(body)
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
        progress = gate.ladder.progress(spec.key, row["level"], row["successes"], row["failures"],
                                        row["successes_at_level"]) if gate else {}
        licenses.append({
            "repo": row["repo"], "action_class": spec.key, "label": spec.label, "level": row["level"],
            "max_level": spec.max_level, "successes": row["successes"], "failures": row["failures"],
            "demoted_from": row["demoted_from"], "updated_at": row["updated_at"], **progress,
        })
    decisions = [dict(r) for r in agent_repo.recent_decisions(context.conn, 60)
                 if repo is None or r["repo"] == repo]
    turns = [dict(r) for r in agent_repo.recent_turns(context.conn, 30) if repo is None or r["repo"] == repo]
    counts = {k: sum(1 for d in decisions if d["decision"] == k) for k in ("allow", "ask", "deny")}
    savings = coding_savings(context, repo)
    return {
        "repos": [dict(r) for r in context.conn.execute("SELECT repo, path, test_command FROM agent_repos")],
        "licenses": licenses,
        "decisions": decisions,
        "turns": turns,
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
                                    actor_id=actor.actor_id, reason=payload.reason)
        return coding_payload(context)


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
