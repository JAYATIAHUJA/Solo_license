"""Planning for the refund worker.

The planner explains *how* it will handle a request and in what order. It does
**not** decide what is permitted - that authority belongs to
:func:`sololicense.domain.license.decide`, and the plan is built around the
decision it is handed. When an LLM key is configured the rationale is authored
by the model; otherwise a deterministic template is used. Either way the plan
is advisory text wrapped around a fixed, safe control flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sololicense.agent.intake import complete
from sololicense.config import Config
from sololicense.domain.license import Decision, LicenseState
from sololicense.domain.models import RefundRequest
from sololicense.domain.task_classes import TaskClassSpec, get_spec

def _decision_steps(decision: Decision, spec: TaskClassSpec) -> list[str]:
    verify = f"Read orders.{spec.effect_column} back to verify the side effect."
    return {
        Decision.SUGGEST: [
            "Draft a recommendation for a human to act on.",
            "Do not touch the orders ledger.",
        ],
        Decision.DRAFT_FOR_APPROVAL: [
            f"Prepare the {spec.label.lower()} as a draft.",
            "Hold for human approval before any write.",
        ],
        Decision.AUTO_EXECUTE: [
            f"Execute the {spec.label.lower()} within the license ceiling.",
            verify,
            "Update the track record only if verification matches.",
        ],
        Decision.AUTO_EXECUTE_AUDITED: [
            f"Execute the {spec.label.lower()} under full autonomy.",
            verify,
            "Flag the run for post-hoc audit and update the track record.",
        ],
    }[decision]


@dataclass(frozen=True)
class Plan:
    rationale: str
    steps: list[str] = field(default_factory=list)
    source: str = "deterministic"


class Planner:
    def __init__(self, config: Config) -> None:
        self._config = config

    def plan(
        self, request: RefundRequest, decision: Decision, state: LicenseState
    ) -> Plan:
        return self._build_plan(request, decision, state)

    def _build_plan(
        self, request: RefundRequest, decision: Decision, state: LicenseState
    ) -> Plan:
        spec = get_spec(state.task_class)
        steps = _decision_steps(decision, spec)
        template = (
            f"Order {request.order_id}: ${request.amount:.2f} "
            f"{spec.label.lower()} requested "
            f"('{request.reason}'). Effective license "
            f"{state.effective_level.name} authorises {decision.name}."
        )
        if self._config.llm_enabled:
            llm_text = self._llm_rationale(request, decision, state)
            if llm_text:
                return Plan(
                    rationale=llm_text,
                    steps=steps,
                    source=f"llm:{self._model_name()}",
                )
        return Plan(rationale=template, steps=steps, source="deterministic")

    def _model_name(self) -> str:
        return self._config.llm_model

    def _llm_rationale(
        self, request: RefundRequest, decision: Decision, state: LicenseState
    ) -> str | None:
        """Ask the model for a one-paragraph rationale. Never raises; returns
        ``None`` on any error so the deterministic template takes over."""
        prompt = (
            f"You are an operations agent working a {get_spec(state.task_class).label.lower()} "
            "request under a graduated "
            "autonomy license. State the plan in 2-3 sentences. You MUST "
            f"respect the authorised action: {decision.name}.\n"
            f"Order: {request.order_id}\nAmount: ${request.amount:.2f}\n"
            f"Reason: {request.reason}\n"
            f"Effective license: {state.effective_level.name} "
            f"({state.effective_level.label})."
        )
        try:
            return complete(self._config, prompt, max_tokens=700)
        except Exception:  # pragma: no cover - network/credential issues
            return None
