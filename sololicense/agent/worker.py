"""The refund worker — the end-to-end task loop.

One run does exactly this, in order, tracing every step:

    1. read the license for the task class;
    2. decide what is *authorised* (pure license logic);
    3. plan around that decision;
    4. execute only what is authorised (a fault may push it beyond — on
       purpose, to be caught);
    5. verify the side effect by reading SQLite back — never trusting the tool;
    6. run the detections; any hit demotes, otherwise a clean executed run
       earns track-record credit;
    7. persist the run, its spans, its detections, and the dial change.

Authority lives in :func:`sololicense.domain.license.decide`; truth lives in
the verifier. The worker only wires them together.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from sololicense.agent.planner import Plan, Planner
from sololicense.agent.tools import execute_refund
from sololicense.config import Config
from sololicense.db.repositories import detections as detections_repo
from sololicense.db.repositories import runs as runs_repo
from sololicense.db.repositories.runs import NewRun, insert_run
from sololicense.domain.license import Decision, LicenseLevel, decide
from sololicense.domain.models import FaultMode, RefundRequest, RunStatus
from sololicense.faults.injector import FaultInjector, effects_for
from sololicense.observability import detections as rules
from sololicense.observability.detections import Detection
from sololicense.observability.tracer import Tracer
from sololicense.services import verification
from sololicense.security import Actor
from sololicense.services.license_service import LicenseService, SYSTEM_ACTOR, Transition

_EXECUTING = (Decision.AUTO_EXECUTE, Decision.AUTO_EXECUTE_AUDITED)


@dataclass(frozen=True)
class RunResult:
    """Everything the UI needs to render one completed run."""

    run_id: int
    task_class: str
    status: RunStatus
    authorized: Decision
    attempted: Decision
    before_refunded: float
    after_refunded: float
    trace_id: str
    plan: Plan
    transition: Transition
    detections: list[Detection] = field(default_factory=list)

    @property
    def actual_delta(self) -> float:
        return round(self.after_refunded - self.before_refunded, 2)


class RefundWorker:
    def __init__(
        self,
        conn: sqlite3.Connection,
        config: Config,
        *,
        tracer: Tracer,
        license_service: LicenseService,
        fault_injector: FaultInjector,
        planner: Planner,
    ) -> None:
        self._conn = conn
        self._config = config
        self._tracer = tracer
        self._licenses = license_service
        self._faults = fault_injector
        self._planner = planner

    def run_refund(
        self,
        request: RefundRequest,
        *,
        task_class: str = "refund",
        approved: bool = False,
        idempotency_key: str | None = None,
        actor: Actor = SYSTEM_ACTOR,
    ) -> RunResult:
        state = self._licenses.get_or_create(task_class)
        # Peek, don't consume: an armed fault only bends a run that actually
        # executes, so a draft or suggestion leaves it armed for the next one.
        armed_effects = effects_for(self._faults.peek(task_class))
        trace = self._tracer.start_trace("refund")
        trace.span(
            "license.check",
            level=state.effective_level.name,
            quarantined=state.quarantined,
            fault=armed_effects.mode.value,
        )

        authorized = self._authorize(state, request, approved)
        attempted = self._attempt(authorized, state, armed_effects)
        plan = self._planner.plan(request, authorized, state)
        trace.span("plan", source=plan.source, rationale=plan.rationale)

        before = verification.read_refunded(self._conn, request.order_id)
        will_execute = attempted in _EXECUTING
        duplicate = (
            bool(idempotency_key)
            and will_execute
            and runs_repo.get_executed_by_idempotency_key(
                self._conn, idempotency_key or ""
            )
            is not None
        )
        if duplicate:
            will_execute = False
        effects = effects_for(FaultMode.NONE)
        if will_execute and armed_effects.active:
            effects = self._faults.consume_effects(task_class)
        intended_delta = request.amount if will_execute else 0.0

        if will_execute:
            self._do_execute(trace, request, effects)
        else:
            trace.span("execute.skipped", reason=attempted.name)

        if will_execute and effects.skip_verification:
            result = verification.missing_refund_verification(
                before=before,
                intended_delta=intended_delta,
            )
        else:
            result = verification.verify_refund(
                self._conn,
                order_id=request.order_id,
                before=before,
                intended_delta=intended_delta,
            )
        trace.span(
            "verify.readback",
            before=result.before,
            after=result.after,
            actual_delta=result.actual_delta,
            intended_delta=intended_delta,
            matched=result.matched,
            verified=result.verified,
        )

        found = self._run_detections(
            authorized=authorized,
            attempted=attempted,
            intended_delta=intended_delta,
            result=result,
            duplicate=duplicate,
        )
        for d in found:
            trace.span(f"detection.{d.rule}", status="error", severity=d.severity,
                       message=d.message)

        status = self._status(found, will_execute, authorized)
        run_id = self._persist_run(
            request=request,
            task_class=task_class,
            state_level=state.effective_level,
            authorized=authorized,
            status=status,
            executed=will_execute,
            result=result,
            idempotency_key=idempotency_key,
            actor=actor,
            effects=effects,
            trace=trace,
            plan=plan,
        )
        trace.flush(self._conn, run_id)

        for d in found:
            detections_repo.insert_detection(
                self._conn,
                run_id=run_id,
                rule=d.rule,
                severity=d.severity,
                message=d.message,
                trace_id=trace.trace_id,
            )

        transition = self._update_dial(
            task_class, status, found, run_id, trace.trace_id, actor
        )
        self._conn.commit()

        return RunResult(
            run_id=run_id,
            task_class=task_class,
            status=status,
            authorized=authorized,
            attempted=attempted,
            before_refunded=result.before,
            after_refunded=result.after,
            trace_id=trace.trace_id,
            plan=plan,
            transition=transition,
            detections=found,
        )

    # --- helpers ---------------------------------------------------------

    def _authorize(
        self, state, request: RefundRequest, approved: bool
    ) -> Decision:
        """What the license authorises. A human approval grants execution at
        the level's audit posture (L3 keeps the audited variant)."""
        if approved and not state.quarantined:
            return (
                Decision.AUTO_EXECUTE_AUDITED
                if state.level is LicenseLevel.L3
                else Decision.AUTO_EXECUTE
            )
        return decide(
            state, request.amount, l2_ceiling=self._config.l2_auto_refund_ceiling
        )

    def _attempt(self, authorized: Decision, state, effects) -> Decision:
        """What the agent actually attempts. The policy-violation fault pushes
        it to auto-execute even when that is not authorised."""
        if effects.force_auto_execute:
            return (
                Decision.AUTO_EXECUTE_AUDITED
                if state.level is LicenseLevel.L3
                else Decision.AUTO_EXECUTE
            )
        return authorized

    def _do_execute(self, trace, request: RefundRequest, effects) -> None:
        trace.span(
            "tool.execute_refund",
            order_id=request.order_id,
            amount=request.amount,
            suppress_write=effects.suppress_write,
        )
        tool_result = execute_refund(
            self._conn,
            order_id=request.order_id,
            amount=request.amount,
            suppress_write=effects.suppress_write,
        )
        # The tool's claim is recorded but explicitly marked untrusted.
        trace.span(
            "tool.result", ok=tool_result.ok, message=tool_result.message,
            trusted=False,
        )

    def _run_detections(
        self, *, authorized, attempted, intended_delta, result, duplicate
    ) -> list[Detection]:
        candidates = [
            rules.detect_policy_breach(authorized=authorized, attempted=attempted),
            rules.detect_duplicate_action(duplicate=duplicate),
            rules.detect_state_mismatch(
                intended_delta=intended_delta,
                actual_delta=result.actual_delta,
                verified=result.verified,
            ),
            rules.detect_missing_verification(verified=result.verified),
        ]
        return [d for d in candidates if d is not None]

    def _status(self, found, will_execute, authorized) -> RunStatus:
        if found:
            return RunStatus.DEMOTED
        if will_execute:
            return RunStatus.CLEAN
        if authorized is Decision.DRAFT_FOR_APPROVAL:
            return RunStatus.PENDING_APPROVAL
        return RunStatus.SUGGESTED

    def _persist_run(
        self, *, request, task_class, state_level, authorized, status, executed,
        result, idempotency_key, actor, effects, trace, plan,
    ) -> int:
        return insert_run(
            self._conn,
            NewRun(
                task_class=task_class,
                order_id=request.order_id,
                requested_amount=request.amount,
                level_at_run=int(state_level),
                decision=authorized.name,
                status=status.value,
                executed=executed and status is not RunStatus.SUGGESTED,
                before_refunded=result.before,
                after_refunded=result.after,
                idempotency_key=idempotency_key,
                actor_id=actor.actor_id,
                actor_role=actor.role.value,
                fault_mode=effects.mode.value,
                trace_id=trace.trace_id,
                notes=plan.rationale,
            ),
        )

    def _update_dial(
        self, task_class, status, found, run_id, trace_id, actor
    ) -> Transition:
        if status is RunStatus.DEMOTED:
            reason = "; ".join(d.message for d in found)
            return self._licenses.apply_detection(
                task_class, run_id=run_id, trace_id=trace_id, reason=reason, actor=actor
            )
        if status is RunStatus.CLEAN:
            return self._licenses.apply_clean_run(
                task_class, run_id=run_id, trace_id=trace_id, actor=actor
            )
        # Suggestions and pending approvals do not move the dial.
        state = self._licenses.get_or_create(task_class)
        return Transition(old=state, new=state, kind="noop", git_sha=None)
