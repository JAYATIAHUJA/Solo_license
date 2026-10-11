"""Task-class registry.

A *task class* is one kind of side effect the agent can be licensed for. Each
class earns and loses autonomy on its own ladder, and each names the single
``orders`` column that is the authority on whether its side effect landed -
the verifier reads exactly that column back after every execution.

Adding a class means adding one entry here (plus the column in the schema);
the worker, verifier, API and UI all read this registry instead of assuming
"refund".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskClassSpec:
    key: str
    label: str            # "Refund"
    verb: str             # "refund" - used in sentences ("refund $25 on ORD-1")
    description: str      # what the action does, for prompts and the UI
    effect_column: str    # orders.<column> that proves the side effect
    keywords: tuple[str, ...] = ()  # deterministic intake hints


TASK_CLASSES: dict[str, TaskClassSpec] = {
    "refund": TaskClassSpec(
        key="refund",
        label="Refund",
        verb="refund",
        description="return money to the customer's original payment method",
        effect_column="refunded_amount",
        keywords=("refund", "money back", "chargeback", "return"),
    ),
    "store_credit": TaskClassSpec(
        key="store_credit",
        label="Store credit",
        verb="issue store credit of",
        description="issue store credit the customer can spend on a future order",
        effect_column="credit_issued",
        keywords=("store credit", "credit", "voucher", "gift card", "coupon"),
    ),
}

DEFAULT_TASK_CLASS = "refund"


def get_spec(task_class: str) -> TaskClassSpec:
    try:
        return TASK_CLASSES[task_class]
    except KeyError as error:
        raise ValueError(f"Unknown task class: {task_class!r}") from error


def classify_text(message: str) -> str:
    """Deterministic fallback: pick the class whose keywords appear first.

    Store credit wins over refund when both appear ("refund as store credit"),
    because it is the more specific request."""
    text = message.lower()
    for key in ("store_credit", "refund"):
        if any(word in text for word in TASK_CLASSES[key].keywords):
            return key
    return DEFAULT_TASK_CLASS
