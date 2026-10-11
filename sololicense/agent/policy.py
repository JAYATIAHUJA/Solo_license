"""Refund policy - checked before the licence is even consulted.

The licence answers "may the agent act alone?"; the policy answers "should this
happen at all?". Every rule comes from the workspace's settings, so a shop
changes its refund window or limits without touching code. The checks are
deterministic and explainable: each one returns a sentence a customer or an
auditor can read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sololicense.db.repositories import orders as orders_repo


@dataclass(frozen=True)
class PolicyResult:
    allowed: bool
    amount: float                 # what may be paid out (possibly capped)
    task_class: str
    reasons: list[str] = field(default_factory=list)   # why it was refused
    notes: list[str] = field(default_factory=list)     # adjustments made
    escalate: bool = False        # a person must look, rather than a "no"


def check(
    order,
    *,
    task_class: str,
    amount: float | None,
    sender: str | None,
    refund_window_days: int,
    today: date | None = None,
) -> PolicyResult:
    """Apply the shop's policy to one request against one order."""
    today = today or date.today()
    remaining = orders_repo.remaining_balance(order)
    reasons: list[str] = []
    notes: list[str] = []

    # Identity: the person asking must be the buyer, when both are known.
    email = (order["email"] or "").strip().lower()
    if sender and email and sender.strip().lower() != email:
        return PolicyResult(
            False, 0.0, task_class,
            [f"The request came from {sender}, but {order['order_id']} belongs to a different customer."],
            escalate=True,
        )

    if remaining <= 0:
        return PolicyResult(False, 0.0, task_class, [f"{order['order_id']} has already been fully paid back."])

    value = remaining if amount is None else round(float(amount), 2)
    if value <= 0:
        return PolicyResult(False, 0.0, task_class, ["The amount asked for is zero."])
    if value > remaining + 0.005:
        notes.append(f"Asked for ${value:.2f}; only ${remaining:.2f} is left on {order['order_id']}, so that is the most offered.")
        value = remaining

    # Refund window: refunds only inside it; store credit is the fallback offer.
    if task_class == "refund" and refund_window_days > 0 and order["ordered_at"]:
        try:
            age = (today - date.fromisoformat(order["ordered_at"][:10])).days
        except ValueError:
            age = None
        if age is not None and age > refund_window_days:
            reasons.append(
                f"{order['order_id']} was paid {age} days ago; refunds are possible for "
                f"{refund_window_days} days. Store credit is still possible."
            )

    if task_class == "store_credit" and order["source"] == "stripe" and not order["customer_ref"]:
        reasons.append("Store credit needs a Stripe customer on the payment, and this one has none.")

    return PolicyResult(not reasons, value if not reasons else 0.0, task_class, reasons, notes)
