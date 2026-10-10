"""Intake agent — turns a free-text customer message into a structured refund
request. With an LLM configured the model does the extraction; without one a
deterministic parser keeps the product fully usable. Either way the result is
only a *request*: what may actually happen is still decided by the license."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from sololicense.config import Config
from sololicense.db.repositories import orders as orders_repo

_ORDER_RE = re.compile(r"\b([A-Z]{2,5}-\d{2,8})\b", re.IGNORECASE)
_MONEY_RE = re.compile(r"(?:\$|usd\s*|rs\.?\s*|₹)\s*(\d+(?:\.\d{1,2})?)", re.IGNORECASE)


@dataclass(frozen=True)
class Intake:
    order_id: str | None
    amount: float | None
    reason: str
    source: str            # deterministic | llm:<model>
    confidence: float = 0.0
    needs_human: bool = False
    note: str = ""


class _LLMIntake(BaseModel):
    order_id: str | None = None
    amount: float | None = Field(default=None, ge=0)
    reason: str = Field(default="customer refund", max_length=140)
    confidence: float = Field(default=0.0, ge=0, le=1)
    needs_human: bool = False


def complete(config: Config, prompt: str, *, max_tokens: int = 300) -> str:
    """One-shot completion against the configured provider. Raises on failure."""
    if config.llm_provider == "anthropic" and config.anthropic_api_key:
        import anthropic

        client = anthropic.Anthropic(
            api_key=config.anthropic_api_key,
            timeout=config.llm_timeout_seconds,
            max_retries=config.llm_max_retries,
        )
        msg = client.messages.create(
            model=config.anthropic_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()
    if config.llm_provider == "openai" and config.openai_api_key:
        import openai

        client = openai.OpenAI(
            api_key=config.openai_api_key,
            timeout=config.llm_timeout_seconds,
            max_retries=config.llm_max_retries,
        )
        resp = client.chat.completions.create(
            model=config.openai_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return (resp.choices[0].message.content or "").strip()
    raise RuntimeError("No LLM provider configured.")


def _deterministic(message: str, conn: sqlite3.Connection) -> Intake:
    order = _ORDER_RE.search(message)
    order_id = order.group(1).upper() if order else None
    money = _MONEY_RE.search(message)
    amount = float(money.group(1)) if money else None
    if amount is None and order_id:
        row = orders_repo.get_order(conn, order_id)
        if row is not None:
            amount = float(row["amount"])
    reason = re.sub(r"\s+", " ", message).strip()[:140]
    confidence = 0.85 if order_id and amount is not None else 0.35
    return Intake(
        order_id, amount, reason, "deterministic",
        confidence=confidence,
        needs_human=confidence < 0.5,
    )


def parse_llm_response(text: str, *, model: str) -> Intake | None:
    try:
        data = json.loads(text)
        parsed = _LLMIntake(**data)
    except (TypeError, ValueError, ValidationError):
        return None

    order_id = parsed.order_id.strip().upper() if parsed.order_id else None
    return Intake(
        order_id=order_id or None,
        amount=float(parsed.amount) if parsed.amount is not None else None,
        reason=parsed.reason.strip()[:140] or "customer refund",
        source=f"llm:{model}",
        confidence=float(parsed.confidence),
        needs_human=bool(parsed.needs_human),
    )


def _llm(message: str, config: Config, conn: sqlite3.Connection) -> Intake | None:
    known = ", ".join(r["order_id"] for r in orders_repo.list_orders(conn)[:50])
    prompt = (
        "Extract a refund request from this customer message. Reply with ONLY "
        'JSON: {"order_id": string|null, "amount": number|null, "reason": '
        'string (max 12 words)}. Known order ids: '
        f"{known or 'none'}.\n\nMessage:\n{message}"
    )
    try:
        text = complete(config, prompt, max_tokens=200)
    except Exception:
        return None
    model = (
        config.anthropic_model if config.llm_provider == "anthropic"
        else config.openai_model
    )
    parsed = parse_llm_response(text, model=model)
    if parsed is None:
        return None
    order_id = parsed.order_id
    amount = parsed.amount
    if amount is None and order_id:
        row = orders_repo.get_order(conn, order_id)
        amount = float(row["amount"]) if row is not None else None
    return Intake(
        order_id, amount, parsed.reason, parsed.source,
        confidence=parsed.confidence,
        needs_human=parsed.needs_human or parsed.confidence < 0.5,
    )


def parse_message(message: str, config: Config, conn: sqlite3.Connection) -> Intake:
    if config.llm_enabled:
        parsed = _llm(message, config, conn)
        if parsed is not None:
            return parsed
    return _deterministic(message, conn)
