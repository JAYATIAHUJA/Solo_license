"""Intake agent — turns a free-text customer message into a structured refund
request. With an LLM configured the model does the extraction; without one a
deterministic parser keeps the product fully usable. Either way the result is
only a *request*: what may actually happen is still decided by the license."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

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
    note: str = ""


def complete(config: Config, prompt: str, *, max_tokens: int = 300) -> str:
    """One-shot completion against the configured provider. Raises on failure."""
    if config.llm_provider == "anthropic" and config.anthropic_api_key:
        import anthropic

        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        msg = client.messages.create(
            model=config.anthropic_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()
    if config.llm_provider == "openai" and config.openai_api_key:
        import openai

        client = openai.OpenAI(api_key=config.openai_api_key)
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
    return Intake(order_id, amount, reason, "deterministic")


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
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception:
        return None
    order_id = (data.get("order_id") or "").strip().upper() or None
    amount = data.get("amount")
    amount = float(amount) if isinstance(amount, (int, float)) else None
    if amount is None and order_id:
        row = orders_repo.get_order(conn, order_id)
        amount = float(row["amount"]) if row is not None else None
    model = (
        config.anthropic_model if config.llm_provider == "anthropic"
        else config.openai_model
    )
    return Intake(order_id, amount, str(data.get("reason") or "customer refund")[:140],
                  f"llm:{model}")


def parse_message(message: str, config: Config, conn: sqlite3.Connection) -> Intake:
    if config.llm_enabled:
        parsed = _llm(message, config, conn)
        if parsed is not None:
            return parsed
    return _deterministic(message, conn)
