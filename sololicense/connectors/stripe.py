"""Stripe connector - real refunds and store credit, verified against Stripe.

* Orders are Stripe charges. The order number is ``metadata.order_id`` when the
  shop sets one, otherwise a short id derived from the charge.
* A refund is ``POST /v1/refunds``; verification re-reads the charge's
  ``amount_refunded`` from Stripe - never the refund call's response.
* Store credit is a customer balance credit (``POST /v1/customers/{id}/
  balance_transactions``); verification sums the credits tagged with the order.
* Every write carries an ``Idempotency-Key``, so a retry after a lost response
  cannot pay twice - Stripe returns the first result instead.

Only test-mode keys are accepted unless ``allow_live`` is set explicitly.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

import httpx

from sololicense.connectors.base import ConnectorError, OrderRecord, ToolResult
from sololicense.domain.models import ExecutionPermit
from sololicense.services.policy_gate import PolicyGate, PermitRejected

_KEY_RE = re.compile(r"^(sk|rk)_(test|live)_[A-Za-z0-9]+$")


def key_mode(key: str) -> str | None:
    """``"test"``, ``"live"`` or ``None`` for something that is not a Stripe secret key."""
    match = _KEY_RE.match(key.strip())
    return match.group(2) if match else None


def _cents(amount: float) -> int:
    return int(round(amount * 100))


def order_id_for(charge: dict) -> str:
    """A readable order number: the shop's own when present, else from the charge id."""
    own = (charge.get("metadata") or {}).get("order_id", "").strip().upper()
    if re.fullmatch(r"[A-Z0-9][A-Z0-9-]{2,31}", own):
        return own
    return "ST-" + re.sub(r"[^A-Za-z0-9]", "", charge["id"])[-10:].upper()


class StripeConnector:
    name = "stripe"

    def __init__(
        self,
        secret_key: str,
        *,
        api_base: str = "https://api.stripe.com",
        allow_live: bool = False,
        conn: sqlite3.Connection | None = None,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
    ) -> None:
        mode = key_mode(secret_key)
        if mode is None:
            raise ConnectorError("That does not look like a Stripe secret key (sk_test_…).")
        if mode == "live" and not allow_live:
            raise ConnectorError("Live Stripe keys are disabled. Use a test-mode key (sk_test_…).")
        self.mode = mode
        self._client = client or httpx.Client(timeout=timeout)
        self._base = api_base.rstrip("/")
        self._headers = {"Authorization": f"Bearer {secret_key.strip()}", "Stripe-Version": "2024-06-20"}
        self._conn = conn

    # --- HTTP ------------------------------------------------------------

    def _request(self, method: str, path: str, *, data: dict | None = None,
                 params: dict | None = None, idempotency_key: str | None = None) -> dict:
        headers = dict(self._headers)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = self._client.request(method, f"{self._base}{path}", data=data, params=params, headers=headers)
        except httpx.HTTPError as error:
            raise ConnectorError(f"Stripe could not be reached: {type(error).__name__}") from error
        body = response.json() if response.content else {}
        if response.status_code >= 400:
            message = (body.get("error") or {}).get("message") or f"HTTP {response.status_code}"
            raise ConnectorError(f"Stripe: {message[:200]}")
        return body

    def check(self) -> str:
        """Cheap authenticated call; returns a short human description."""
        self._request("GET", "/v1/balance")
        return f"Connected to Stripe ({self.mode} mode)."

    # --- orders ------------------------------------------------------------

    def list_orders(self, limit: int = 100) -> list[OrderRecord]:
        body = self._request("GET", "/v1/charges", params={"limit": min(100, limit), "expand[]": "data.customer"})
        records = []
        for charge in body.get("data", []):
            if not charge.get("paid") or charge.get("status") != "succeeded":
                continue
            details = charge.get("billing_details") or {}
            customer = charge.get("customer")
            customer = customer if isinstance(customer, dict) else {"id": customer} if customer else {}
            email = charge.get("receipt_email") or details.get("email") or customer.get("email")
            records.append(OrderRecord(
                order_id=order_id_for(charge),
                customer=details.get("name") or customer.get("name") or email or "Stripe customer",
                amount=charge["amount"] / 100,
                email=email,
                ordered_at=datetime.fromtimestamp(charge["created"], tz=timezone.utc).date().isoformat(),
                currency=charge.get("currency", "usd"),
                refunded_amount=charge.get("amount_refunded", 0) / 100,
                source="stripe",
                external_id=charge["id"],
                customer_ref=customer.get("id"),
            ))
        return records

    # --- side effects -----------------------------------------------------

    def apply(
        self, task_class: str, order: dict, amount: float, *, idempotency_key: str,
        suppress_write: bool = False, permit: ExecutionPermit | None = None,
    ) -> ToolResult:
        if suppress_write:
            # Fault switch: pretend the call worked without calling Stripe.
            return ToolResult(ok=True, message="Processed (reported).")
        if permit is None or self._conn is None:
            raise ConnectorError("A server-issued execution permit is required for Stripe writes.")
        try:
            PolicyGate(self._conn).consume_for_write(permit)
        except PermitRejected as error:
            raise ConnectorError(str(error)) from error
        metadata = {"metadata[order_id]": order["order_id"], "metadata[source]": "solo-license"}
        if task_class == "refund":
            refund = self._request(
                "POST", "/v1/refunds",
                data={"charge": order["external_id"], "amount": _cents(amount), **metadata},
                idempotency_key=idempotency_key,
            )
            return ToolResult(ok=refund.get("status") in ("succeeded", "pending"),
                              message=f"Stripe refund {refund.get('status')}.", reference=refund.get("id"))
        if task_class == "store_credit":
            customer = order.get("customer_ref")
            if not customer:
                raise ConnectorError("This Stripe payment has no customer, so store credit cannot be issued.")
            txn = self._request(
                "POST", f"/v1/customers/{customer}/balance_transactions",
                data={"amount": -_cents(amount), "currency": order.get("currency") or "usd",
                      "description": f"Store credit for {order['order_id']}", **metadata},
                idempotency_key=idempotency_key,
            )
            return ToolResult(ok=True, message="Stripe credit added.", reference=txn.get("id"))
        raise ConnectorError(f"Stripe cannot perform {task_class!r}.")

    def read_effect(self, task_class: str, order: dict) -> float:
        if task_class == "refund":
            charge = self._request("GET", f"/v1/charges/{order['external_id']}")
            return charge.get("amount_refunded", 0) / 100
        if task_class == "store_credit":
            customer = order.get("customer_ref")
            if not customer:
                return 0.0
            body = self._request("GET", f"/v1/customers/{customer}/balance_transactions", params={"limit": 100})
            credited = sum(
                -txn["amount"] for txn in body.get("data", [])
                if (txn.get("metadata") or {}).get("order_id") == order["order_id"] and txn["amount"] < 0
            )
            return credited / 100
        raise ConnectorError(f"Stripe cannot read {task_class!r}.")

    # --- sample data (test mode only) -------------------------------------------

    def create_sample_orders(self, samples: list[dict]) -> int:
        """Create paid test charges so a fresh test account has something to work on."""
        if self.mode != "test":
            raise ConnectorError("Sample orders can only be created in test mode.")
        created = 0
        for sample in samples:
            key = f"solo-sample-{sample['order_id']}"
            customer = self._request(
                "POST", "/v1/customers",
                data={"name": sample["customer"], "email": sample["email"]},
                idempotency_key=f"{key}-customer",
            )
            self._request(
                "POST", "/v1/payment_intents",
                data={
                    "amount": _cents(sample["amount"]), "currency": "usd", "customer": customer["id"],
                    "payment_method": "pm_card_visa", "confirm": "true",
                    "automatic_payment_methods[enabled]": "true",
                    "automatic_payment_methods[allow_redirects]": "never",
                    "receipt_email": sample["email"],
                    "metadata[order_id]": sample["order_id"],
                    "description": sample.get("item", "Sample order"),
                },
                idempotency_key=f"{key}-payment",
            )
            created += 1
        return created
