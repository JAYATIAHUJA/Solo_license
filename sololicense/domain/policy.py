"""Immutable autonomy policies and their evidence-based evaluations.

Policies define the conditions under which a task class may earn additional
autonomy. They deliberately contain no persistence or side effects, so the
same policy evaluation can be used by the worker, API preview, and audit view.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class PolicyRule:
    """One task class's allowed tool and promotion evidence requirements."""

    task_class: str
    allowed_tool: str
    requires_approval_at_or_above: int
    l2_ceiling: float
    evaluation_window: int
    minimum_samples: int
    minimum_verified_pass_rate: float

    def __post_init__(self) -> None:
        validate_rule(self)


@dataclass(frozen=True)
class PolicyVersion:
    """An immutable, workspace-local policy version and its rules."""

    id: int
    version: int
    name: str
    status: str
    summary: str
    created_by: str
    created_at: str
    rules: tuple[PolicyRule, ...]

    def rule_for(self, task_class: str) -> PolicyRule:
        for rule in self.rules:
            if rule.task_class == task_class:
                return rule
        raise KeyError(f"Policy v{self.version} has no rule for '{task_class}'.")


@dataclass(frozen=True)
class EvaluationProgress:
    """A policy-scoped summary of whether a task class has earned promotion."""

    sample_size: int
    clean_runs: int
    pass_rate: float
    required_samples: int
    required_pass_rate: float
    eligible: bool


@dataclass(frozen=True)
class PolicyImpact:
    """The review consequence of activating a policy version for one class."""

    task_class: str
    previous_version: int | None
    next_version: int
    evaluation: EvaluationProgress
    action: str
    reason: str


def validate_rule(rule: PolicyRule) -> None:
    """Reject policy settings that could not safely govern a real run."""
    if not rule.task_class.strip():
        raise ValueError("task class is required")
    if not rule.allowed_tool.strip():
        raise ValueError("allowed tool is required")
    if rule.requires_approval_at_or_above < 0 or rule.requires_approval_at_or_above > 3:
        raise ValueError("approval level must be between 0 and 3")
    if rule.l2_ceiling < 0:
        raise ValueError("L2 ceiling cannot be negative")
    if rule.evaluation_window < 1:
        raise ValueError("evaluation window must be at least 1")
    if rule.minimum_samples < 1 or rule.minimum_samples > rule.evaluation_window:
        raise ValueError("minimum samples must be within the evaluation window")
    if not 0 <= rule.minimum_verified_pass_rate <= 1:
        raise ValueError("pass rate must be between 0 and 1")


def evaluate_runs(outcomes: Sequence[bool], rule: PolicyRule) -> EvaluationProgress:
    """Evaluate only the most recent outcomes allowed by ``rule``.

    ``outcomes`` is newest first, matching the database query used by the
    policy service. A pass rate only becomes meaningful after the rule's
    minimum sample is present.
    """
    window = tuple(outcomes[: rule.evaluation_window])
    sample_size = len(window)
    clean_runs = sum(window)
    pass_rate = clean_runs / sample_size if sample_size else 0.0
    eligible = (
        sample_size >= rule.minimum_samples
        and pass_rate >= rule.minimum_verified_pass_rate
    )
    return EvaluationProgress(
        sample_size=sample_size,
        clean_runs=clean_runs,
        pass_rate=pass_rate,
        required_samples=rule.minimum_samples,
        required_pass_rate=rule.minimum_verified_pass_rate,
        eligible=eligible,
    )
