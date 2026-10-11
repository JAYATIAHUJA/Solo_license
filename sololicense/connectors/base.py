"""Connector contract — where orders come from and where money actually moves.

A connector does three things and nothing else:

* ``apply``        performs a side effect (refund, store credit) and returns what
                   it *claims* happened — a claim, never evidence;
* ``read_effect``  reads the authoritative amount back from the system of record
                   (Stripe, or the local store), which is what verification trusts;
* ``list_orders``  imports the orders the agent may work on.

The worker never talks to Stripe or SQLite directly; it talks to a connector.
Adding Shopify or a payments API later means one new class here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from sololicense.domain.models import ExecutionPermit


class ConnectorError(RuntimeError):
    """The system of record refused or could not be reached."""


@dataclass(frozen=True)
class OrderRecord:
    """An order as a connector reports it (amounts in major units, e.g. dollars)."""

    order_id: str
    customer: str
    amount: float
    email: str | None = None
    ordered_at: str | None = None      # ISO date
    currency: str = "usd"
    refunded_amount: float = 0.0
    credit_issued: float = 0.0
    source: str = "manual"
    external_id: str | None = None     # e.g. Stripe charge id
    customer_ref: str | None = None    # e.g. Stripe customer id


@dataclass(frozen=True)
class ToolResult:
    """What a connector says happened. Recorded, never trusted."""

    ok: bool
    message: str
    reference: str | None = None       # e.g. Stripe refund id


class Connector(Protocol):
    name: str

    def apply(
        self, task_class: str, order: dict, amount: float, *, idempotency_key: str,
        suppress_write: bool = False, permit: ExecutionPermit | None = None
    ) -> ToolResult: ...

    def read_effect(self, task_class: str, order: dict) -> float: ...

    def list_orders(self) -> list[OrderRecord]: ...
