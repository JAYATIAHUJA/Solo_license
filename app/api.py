"""HTTP adapter for the Solo License application services.

The React client talks only to this file. Domain, worker, verification, SQLite,
and the git-backed ledger remain the implementation in ``sololicense``.
"""

from __future__ import annotations

import re
from dataclasses import replace
from threading import RLock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sololicense.agent.intake import complete, parse_message
from sololicense.bootstrap import AppContext, build_app
from sololicense.db.repositories import events as events_repo
from sololicense.db.repositories import license as license_repo
from sololicense.db.repositories import orders as orders_repo
from sololicense.db.repositories import runs as runs_repo
from sololicense.db.repositories import settings as settings_repo
from sololicense.db.seed import SEED_ORDERS, seed
from sololicense.domain.license import LicenseLevel, LicenseState
from sololicense.domain.models import FaultMode, RefundRequest
from sololicense.services.evidence import build_packet

TASK_CLASS = "refund"
SECRET_KEYS = ("anthropic_api_key", "openai_api_key", "neatlogs_api_key")
SETTING_KEYS = (
    "business_name", "llm_provider", "anthropic_model", "openai_model",
    "promotion_clean_runs", "l2_auto_refund_ceiling", "neatlogs_project",
    *SECRET_KEYS,
)

app = FastAPI(title="Solo License API")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

_context: AppContext | None = None
_lock = RLock()


# --- payloads -------------------------------------------------------------

class RefundPayload(BaseModel):
    order_id: str
    amount: float | None = Field(default=None, ge=0)
    reason: str = "customer refund"


class IntakePayload(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    run: bool = True


class FaultPayload(BaseModel):
    mode: FaultMode


class RestorePayload(BaseModel):
    level: int
    reason: str = "Human restored after evidence review."


class OrderPayload(BaseModel):
    order_id: str = Field(min_length=3, max_length=32)
    customer: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0, le=1_000_000)


class SettingsPayload(BaseModel):
    values: dict[str, str | int | float | None]


class OnboardingPayload(BaseModel):
    business_name: str = ""
    starting_level: int = 0
    load_sample_orders: bool = True
    values: dict[str, str | int | float | None] = {}


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


def _mask(value: str) -> str:
    return f"••••{value[-4:]}" if len(value) > 4 else ("••••" if value else "")


def serialize_settings(context: AppContext) -> dict:
    stored = settings_repo.get_all(context.conn)
    cfg = context.config
    return {
        "onboarded": stored.get("onboarded") == "1",
        "business_name": stored.get("business_name", ""),
        "llm_provider": cfg.llm_provider,
        "llm_enabled": cfg.llm_enabled,
        "anthropic_model": cfg.anthropic_model,
        "openai_model": cfg.openai_model,
        "promotion_clean_runs": cfg.promotion_clean_runs,
        "l2_auto_refund_ceiling": cfg.l2_auto_refund_ceiling,
        "neatlogs_project": cfg.neatlogs_project,
        "neatlogs_enabled": cfg.neatlogs_enabled,
        "has_anthropic_key": bool(cfg.anthropic_api_key),
        "has_openai_key": bool(cfg.openai_api_key),
        "anthropic_key_hint": _mask(cfg.anthropic_api_key),
        "openai_key_hint": _mask(cfg.openai_api_key),
        "neatlogs_key_hint": _mask(cfg.neatlogs_api_key),
    }


def serialize_state(context: AppContext) -> dict:
    state = context.license_service.get_or_create(TASK_CLASS)
    return {
        "task_class": state.task_class,
        "level": int(state.level),
        "effective_level": int(state.effective_level),
        "clean_runs": state.consecutive_clean_runs,
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


def _stats(context: AppContext) -> dict:
    row = context.conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(status = 'clean') AS clean,
               SUM(status = 'demoted') AS demoted,
               SUM(status = 'pending_approval') AS pending,
               COALESCE(SUM(after_refunded - before_refunded), 0) AS refunded
          FROM runs
        """
    ).fetchone()
    return {
        "total_runs": row["total"] or 0,
        "clean_runs": row["clean"] or 0,
        "demotions": row["demoted"] or 0,
        "pending_approval": row["pending"] or 0,
        "refunded_total": round(row["refunded"] or 0, 2),
    }


def dashboard_payload(context: AppContext, selected_run_id: int | None = None) -> dict:
    runs = [dict(row) for row in runs_repo.list_recent(context.conn, limit=50)]
    selected = selected_run_id or (runs[0]["id"] if runs else None)
    intakes = [
        dict(r) for r in context.conn.execute(
            "SELECT * FROM intakes ORDER BY id DESC LIMIT 20"
        ).fetchall()
    ]
    return {
        "settings": serialize_settings(context),
        "license": serialize_state(context),
        "config": {
            "promotion_clean_runs": context.config.promotion_clean_runs,
            "l2_auto_refund_ceiling": context.config.l2_auto_refund_ceiling,
        },
        "stats": _stats(context),
        "orders": [dict(row) for row in orders_repo.list_orders(context.conn)],
        "runs": runs,
        "intakes": intakes,
        "events": [dict(e) for e in events_repo.list_events(context.conn, TASK_CLASS, limit=30)],
        "armed_fault": context.fault_injector.peek(TASK_CLASS).value,
        "packet": serialize_packet(context, selected),
    }


def _run(context: AppContext, order_id: str, amount: float | None, reason: str,
         *, approved: bool = False):
    order = orders_repo.get_order(context.conn, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")
    value = float(order["amount"]) if amount is None else float(amount)
    remaining = float(order["amount"]) - float(order["refunded_amount"])
    if value > remaining + 1e-9:
        raise HTTPException(
            status_code=422,
            detail=f"Refund ${value:.2f} exceeds the ${remaining:.2f} still refundable on {order_id}.",
        )
    return context.worker.run_refund(
        RefundRequest(order["order_id"], order["customer"], value, reason),
        task_class=TASK_CLASS,
        approved=approved,
    )


# --- read -----------------------------------------------------------------

@app.get("/api/dashboard")
def get_dashboard(run_id: int | None = None) -> dict:
    with _lock:
        return dashboard_payload(get_context(), run_id)


@app.get("/api/settings")
def get_settings() -> dict:
    with _lock:
        return serialize_settings(get_context())


# --- agent ----------------------------------------------------------------

@app.post("/api/refunds")
def run_refund(payload: RefundPayload) -> dict:
    with _lock:
        context = get_context()
        result = _run(context, payload.order_id.strip().upper(), payload.amount, payload.reason)
        return dashboard_payload(context, result.run_id)


@app.post("/api/intake")
def intake(payload: IntakePayload) -> dict:
    """Free-text customer message -> structured request -> licensed run."""
    with _lock:
        context = get_context()
        parsed = parse_message(payload.message, context.config, context.conn)
        run_id = None
        error = None
        if payload.run:
            if not parsed.order_id or parsed.amount is None:
                error = "Could not find an order id and amount in that message."
            else:
                try:
                    result = _run(context, parsed.order_id, parsed.amount, parsed.reason)
                    run_id = result.run_id
                except HTTPException as exc:
                    error = str(exc.detail)
        context.conn.execute(
            "INSERT INTO intakes (message, order_id, amount, reason, source, run_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (payload.message, parsed.order_id, parsed.amount, parsed.reason, parsed.source, run_id),
        )
        context.conn.commit()
        body = dashboard_payload(context, run_id)
        body["intake"] = {
            "order_id": parsed.order_id, "amount": parsed.amount,
            "reason": parsed.reason, "source": parsed.source,
            "run_id": run_id, "error": error,
        }
        return body


@app.post("/api/runs/{run_id}/approve")
def approve_run(run_id: int) -> dict:
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
        if context.license_service.get_or_create(TASK_CLASS).quarantined:
            raise HTTPException(status_code=409, detail="The class is quarantined. Restore it before approving runs.")
        result = _run(context, run["order_id"], run["requested_amount"],
                      "approved by human", approved=True)
        context.conn.execute(
            "UPDATE runs SET status = 'approved' WHERE id = ?", (run_id,)
        )
        context.conn.commit()
        return dashboard_payload(context, result.run_id)


@app.post("/api/faults")
def arm_fault(payload: FaultPayload) -> dict:
    with _lock:
        context = get_context()
        context.fault_injector.arm(TASK_CLASS, payload.mode)
        return dashboard_payload(context)


@app.post("/api/restore")
def restore_license(payload: RestorePayload) -> dict:
    with _lock:
        context = get_context()
        try:
            target = LicenseLevel(payload.level)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Unknown license level.") from error
        context.license_service.restore_license(TASK_CLASS, target, reason=payload.reason)
        return dashboard_payload(context)


# --- orders ---------------------------------------------------------------

@app.post("/api/orders")
def add_order(payload: OrderPayload) -> dict:
    with _lock:
        context = get_context()
        order_id = payload.order_id.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{2,31}", order_id):
            raise HTTPException(status_code=422, detail="Order id may use letters, digits and dashes.")
        if orders_repo.get_order(context.conn, order_id) is not None:
            raise HTTPException(status_code=409, detail=f"{order_id} already exists.")
        context.conn.execute(
            "INSERT INTO orders (order_id, customer, amount) VALUES (?, ?, ?)",
            (order_id, payload.customer.strip(), round(payload.amount, 2)),
        )
        context.conn.commit()
        return dashboard_payload(context)


@app.delete("/api/orders/{order_id}")
def delete_order(order_id: str) -> dict:
    with _lock:
        context = get_context()
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
    if "llm_provider" in out and out["llm_provider"] not in ("deterministic", "anthropic", "openai"):
        raise HTTPException(status_code=422, detail="Unknown LLM provider.")
    try:
        if "promotion_clean_runs" in out and int(out["promotion_clean_runs"]) < 1:
            raise ValueError
        if "l2_auto_refund_ceiling" in out and float(out["l2_auto_refund_ceiling"]) < 0:
            raise ValueError
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid numeric setting.") from error
    return out


def _save_settings(context: AppContext, values: dict[str, str]) -> None:
    settings_repo.set_many(context.conn, values)
    context.conn.commit()


@app.put("/api/settings")
def update_settings(payload: SettingsPayload) -> dict:
    with _lock:
        context = get_context()
        _save_settings(context, _clean_values(payload.values))
        reset_context()
        return dashboard_payload(get_context())


@app.post("/api/settings/test-llm")
def test_llm(payload: SettingsPayload) -> dict:
    """Try a provider/key (from the form, before saving) with a tiny call."""
    with _lock:
        context = get_context()
        cleaned = _clean_values(payload.values)
        cfg = context.config
        provider = cleaned.get("llm_provider", cfg.llm_provider)
        cfg = replace(
            cfg,
            llm_provider=provider,
            anthropic_api_key=cleaned.get("anthropic_api_key", cfg.anthropic_api_key),
            openai_api_key=cleaned.get("openai_api_key", cfg.openai_api_key),
            anthropic_model=cleaned.get("anthropic_model", cfg.anthropic_model),
            openai_model=cleaned.get("openai_model", cfg.openai_model),
        )
        if provider == "deterministic":
            return {"ok": True, "message": "Deterministic mode needs no key."}
        if not cfg.llm_enabled:
            return {"ok": False, "message": "Add an API key for this provider first."}
        try:
            reply = complete(cfg, "Reply with the single word: ready", max_tokens=10)
            return {"ok": True, "message": f"Connected. Model replied: {reply[:40]}"}
        except Exception as error:  # surfaced to the operator; key never echoed
            return {"ok": False, "message": f"{type(error).__name__}: {str(error)[:200]}"}


@app.post("/api/onboarding/complete")
def complete_onboarding(payload: OnboardingPayload) -> dict:
    with _lock:
        context = get_context()
        values = _clean_values(payload.values)
        values["business_name"] = payload.business_name.strip()
        values["onboarded"] = "1"
        _save_settings(context, values)
        reset_context()
        context = get_context()
        if payload.load_sample_orders and not orders_repo.list_orders(context.conn):
            context.conn.executemany(
                "INSERT INTO orders (order_id, customer, amount) VALUES (?, ?, ?)",
                [(o.order_id, o.customer, o.amount) for o in SEED_ORDERS],
            )
        try:
            level = LicenseLevel(payload.starting_level)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Unknown license level.") from error
        license_repo.upsert_state(context.conn, LicenseState(task_class=TASK_CLASS, level=level))
        context.conn.commit()
        return dashboard_payload(context)


@app.post("/api/reseed")
def reseed_demo() -> dict:
    """Reset runs/ledger and reinstall the sample orders (keeps settings)."""
    with _lock:
        context = get_context()
        seed(context.conn, context.config)
        return dashboard_payload(context)
