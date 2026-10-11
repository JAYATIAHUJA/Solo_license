"""Value objects that travel through the refund loop.

These are plain, immutable carriers of data - no behaviour, no I/O. They give
the rest of the system a shared vocabulary (a ``RefundRequest`` means the same
thing to the agent, the verifier, and the UI)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RunStatus(str, Enum):
    """Terminal status of a single refund run, from the agent's point of view."""

    SUGGESTED = "suggested"            # L0 / quarantined: advice only
    PENDING_APPROVAL = "pending_approval"  # L1 or over-ceiling: awaits a human
    CLEAN = "clean"                    # executed and verified against SQLite
    DEMOTED = "demoted"                # a detection fired; license crashed
    APPROVED = "approved"              # superseded by a human-approved run
    REJECTED = "rejected"              # a person said the proposal was wrong
    FAILED = "failed"                  # the system of record refused; nothing moved


class FaultMode(str, Enum):
    """Deterministic faults the injector can arm for the next run."""

    NONE = "none"
    QUIET_FAILURE = "quiet_failure"      # tool reports success, DB unchanged
    POLICY_VIOLATION = "policy_violation"  # action exceeds the current license
    SKIP_VERIFICATION = "skip_verification"  # execute, then skip read-back


@dataclass(frozen=True)
class RefundRequest:
    """A customer refund to be worked by the agent."""

    order_id: str
    customer: str
    amount: float
    reason: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("refund amount cannot be negative")
        if not self.order_id:
            raise ValueError("order_id is required")


@dataclass(frozen=True)
class ExecutionPermit:
    """A short-lived capability for exactly one approved side effect."""

    token: str
    policy_version: int
    task_class: str
    tool: str
    order_id: str
    amount: float
    expires_at: datetime
    # Row id of the stored digest: safe to export, unlike ``token``.
    id: int | None = None


@dataclass(frozen=True)
class BlockedPermit:
    """An auditable refusal to turn an attempted action into a tool call."""

    reason: str
