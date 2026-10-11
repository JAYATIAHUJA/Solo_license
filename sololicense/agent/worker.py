"""The refund worker - the end-to-end task loop.

One run does exactly this, in order, tracing every step:

    1. read the license for the task class;
    2. decide what is *authorised* (pure license logic);
    3. plan around that decision;
    4. execute only what is authorised (a fault may push it beyond - on
       purpose, to be caught);
    5. verify the side effect by reading it back from the system of record
       (Stripe or the local store) - never trusting the tool's response;
    6. recover when verification disagrees: reconcile (read again), then retry
       once with the *same* idempotency key, then verify again;
    7. run the detections; any hit demotes - even when recovery saved the
       customer, because the tool lied or a step was skipped - otherwise a clean
       executed run adds verified evidence;
    8. persist the run, its spans, its detections, and the dial change.

Authority lives in :func:`sololicense.domain.license.decide`; truth lives in
the verifier. The worker only wires them together.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from sololicense.agent.planner import Plan, Planner
from sololicense.config import Config
from sololicense.connectors import ConnectorError, Connectors
from sololicense.db.repositories import detections as detections_repo
from sololicense.db.repositories import orders as orders_repo
from sololicense.db.repositories import runs as runs_repo
from sololicense.db.repositories.runs import NewRun, insert_run
from sololicense.domain.license import Decision, LicenseLevel, decide
from sololicense.domain.models import BlockedPermit, ExecutionPermit, FaultMode, RefundRequest, RunStatus
from sololicense.domain.task_classes import get_spec
from sololicense.faults.injector import FaultInjector, effects_for
from sololicense.observability import detections as rules
from sololicense.observability.detections import Detection
from sololicense.observability.tracer import Tracer
from sololicense.services import verification
from sololicense.security import Actor
from sololicense.services.license_service import LicenseService, SYSTEM_ACTOR, Transition
from sololicense.services.policy_gate import PolicyGate
from sololicense.services.policy_service import PolicyService

_EXECUTING = (Decision.AUTO_EXECUTE, Decision.AUTO_EXECUTE_AUDITED)

# Why recovery changed course after a failed read-back: (reason_code, note).
_REPLANS = {
    "no_change": ("no_change", "Re-planned: the tool reported success but the read-back showed no change, "
                               "so the agent retried once with the same idempotency key."),
    "landed_late": ("landed_late", "Re-planned: the first read-back disagreed, but reconciling showed the "
                                   "change had landed, so no retry was needed."),
    "partial_change": ("partial_change", "Re-planned: only part of the change landed, so the agent stopped "
                                         "and handed it to a person instead of retrying."),
}


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
    recovered: bool = False          # verification failed, recovery fixed it
    error: str | None = None         # the system of record refused the action
    reference: str | None = None     # e.g. Stripe refund id
    recovery_reason: str | None = None  # no_change | landed_late | partial_change
    recovery_note: str | None = None    # why the agent changed course, in plain words

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
        policy_service: PolicyService,
        fault_injector: FaultInjector,
        planner: Planner,
        connectors: Connectors | None = None,
    ) -> None:
        self._conn = conn
        self._config = config
        self._tracer = tracer
        self._licenses = license_service
        self._policy_service = policy_service
        self._faults = fault_injector
        self._planner = planner
        self._connectors = connectors or Connectors(conn, config)
        # Off reproduces v1 behaviour (catch and stop, no retry); used by the
        # before/after benchmark so the improvement is measured, not claimed.
        self.recovery_enabled = True

    def run_refund(
        self,
        request: RefundRequest,
        *,
        task_class: str = "refund",
        approved: bool = False,
        idempotency_key: str | None = None,
        actor: Actor = SYSTEM_ACTOR,
        trace=None,
        ticket_id: int | None = None,
    ) -> RunResult:
        """Work one request. Pass ``trace`` to record into a caller's trace (the
        ticket agent's); the caller then flushes it. Otherwise the worker owns
        and flushes its own trace."""
        get_spec(task_class)  # fail fast on an unknown class
        owns_trace = trace is None
        if owns_trace:
            trace = self._tracer.start_trace(
                task_class, order_id=request.order_id, amount=request.amount,
                actor=actor.actor_id,
            )
        try:
            result = self._run_refund(
                request,
                task_class=task_class,
                approved=approved,
                idempotency_key=idempotency_key,
                actor=actor,
                trace=trace,
                ticket_id=ticket_id,
            )
        except Exception as error:
            trace.span("run.error", status="error", error_type=type(error).__name__)
            if owns_trace:
                trace.close()
            raise
        if owns_trace:
            trace.flush(self._conn, result.run_id)
            self._conn.commit()
        return result

    def _run_refund(
        self,
        request: RefundRequest,
        *,
        task_class: str,
        approved: bool,
        idempotency_key: str | None,
        actor: Actor,
        trace,
        ticket_id: int | None = None,
    ) -> RunResult:
        state = self._licenses.get_or_create(task_class)
        column = get_spec(task_class).effect_column
        # Peek, don't consume: an armed fault only bends a run that actually
        # executes, so a draft or suggestion leaves it armed for the next one.
        armed_effects = effects_for(self._faults.peek(task_class))
        trace.span(
            "license.check",
            level=state.effective_level.name,
            quarantined=state.quarantined,
            fault=armed_effects.mode.value,
        )

        policy = self._policy_service.active()
        authorized = self._authorize(state, request, approved, policy)
        attempted = self._attempt(authorized, state, armed_effects)
        plan = self._planner.plan(request, authorized, state)
        trace.span("plan", source=plan.source, rationale=plan.rationale)

        order = orders_repo.get_order(self._conn, request.order_id)
        if order is None:
            raise KeyError(f"unknown order_id: {request.order_id!r}")
        connector = self._connectors.for_order(order)
        before = self._read(connector, task_class, order, column)
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
        permit: ExecutionPermit | None = None
        if will_execute:
            candidate = PolicyGate(self._conn).issue(
                policy=policy,
                task_class=task_class,
                tool=task_class,
                order_id=request.order_id,
                amount=request.amount,
                authorized=authorized,
                attempted=attempted,
                license_level=int(state.effective_level),
                approved=approved,
                actor=actor,
            )
            if isinstance(candidate, BlockedPermit):
                trace.span("policy.blocked", status="error", reason=candidate.reason)
                will_execute = False
            else:
                permit = candidate
        intended_delta = request.amount if will_execute else 0.0
        key = idempotency_key or f"run:{trace.trace_id}"

        error: str | None = None
        reference: str | None = None
        if will_execute:
            try:
                reference = self._do_execute(trace, connector, request, order, effects, task_class, key, permit)
            except ConnectorError as refusal:
                error = str(refusal)
                trace.span("tool.error", status="error", message=error[:200])
        else:
            trace.span("execute.skipped", reason=attempted.name)
        if error is not None:
            intended_delta = 0.0  # an honest refusal: nothing should have moved

        if will_execute and error is None and effects.skip_verification:
            first = verification.unverified(before=before, intended_delta=intended_delta)
        else:
            first = verification.verify(
                before=before,
                after=self._read(connector, task_class, order, column),
                intended_delta=intended_delta,
            )
        trace.span(
            "verify.readback",
            source=connector.name,
            before=first.before,
            after=first.after,
            actual_delta=first.actual_delta,
            intended_delta=first.intended_delta,
            matched=first.matched,
            verified=first.verified,
        )

        result, recovered, replan = first, False, None
        authorised_execution = authorized in _EXECUTING
        if (self.recovery_enabled and will_execute and error is None and authorised_execution
                and not (first.verified and first.matched)):
            result, recovered, replan = self._recover(
                trace, connector, request, order, task_class, column, key, before, intended_delta,
                policy, state, authorized, attempted, approved, actor,
            )

        # Detections judge the first attempt: a tool that lied, or a skipped
        # check, costs the licence even when recovery saved the customer.
        found = self._run_detections(
            authorized=authorized,
            attempted=attempted,
            intended_delta=intended_delta,
            result=first,
            duplicate=duplicate,
        )
        for d in found:
            trace.span(f"detection.{d.rule}", status="error", severity=d.severity,
                       message=d.message)

        status = (
            RunStatus.FAILED if error is not None and not found
            else self._status(found, will_execute, authorized)
        )
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
            recovered=recovered,
            ticket_id=ticket_id,
            policy_version=policy.version,
        )

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
            task_class, status, found, run_id, trace.trace_id, actor, policy
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
            recovered=recovered,
            error=error,
            reference=reference,
            recovery_reason=replan[0] if replan else None,
            recovery_note=replan[1] if replan else None,
        )

    # --- helpers ---------------------------------------------------------

    def _authorize(
        self, state, request: RefundRequest, approved: bool, policy
    ) -> Decision:
        """What the license authorises. A human approval grants execution at
        the level's audit posture (L3 keeps the audited variant)."""
        if approved and not state.quarantined:
            return (
                Decision.AUTO_EXECUTE_AUDITED
                if state.level is LicenseLevel.L3
                else Decision.AUTO_EXECUTE
            )
        decision = decide(
            state, request.amount,
            l2_ceiling=policy.rule_for(state.task_class).l2_ceiling,
        )
        rule = policy.rule_for(state.task_class)
        # The approval boundary is the first license level that may execute
        # without a human approval. L0 stays a suggestion; L1's existing
        # draft behavior is preserved. A stricter policy can hold L2 until L3.
        if (
            decision in _EXECUTING
            and state.effective_level < rule.requires_approval_at_or_above
        ):
            return Decision.DRAFT_FOR_APPROVAL
        return decision

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

    def _read(self, connector, task_class: str, order, column: str) -> float:
        """Authoritative amount from the system of record. An external value is
        cached on the order so the app shows what Stripe shows."""
        value = connector.read_effect(task_class, order)
        if connector.name != "local":
            orders_repo.set_effect_amount(self._conn, order["order_id"], column, value)
        return value

    def _do_execute(
        self, trace, connector, request: RefundRequest, order, effects, task_class: str,
        key: str, permit: ExecutionPermit | None,
    ) -> str | None:
        if permit is None:
            raise ConnectorError("Execution permit missing for tool call.")
        trace.span(
            f"tool.execute_{task_class}",
            connector=connector.name,
            order_id=request.order_id,
            amount=request.amount,
            idempotency_key=key,
            suppress_write=effects.suppress_write,
            **{"policy.version": permit.policy_version, "permit.id": permit.id},
        )
        tool_result = connector.apply(
            task_class, order, request.amount, idempotency_key=key, suppress_write=effects.suppress_write,
            permit=permit,
        )
        # The tool's claim is recorded but explicitly marked untrusted.
        trace.span(
            "tool.result", ok=tool_result.ok, message=tool_result.message,
            reference=tool_result.reference, trusted=False,
        )
        return tool_result.reference

    def _recover(
        self, trace, connector, request: RefundRequest, order, task_class: str, column: str,
        key: str, before: float, intended_delta: float, policy, state, authorized,
        attempted, approved: bool, actor: Actor,
    ) -> tuple[verification.VerificationResult, bool, tuple[str, str]]:
        """Verification disagreed with the tool. Reconcile first, retry once
        with the same idempotency key only when nothing moved, verify again.

        Retrying is safe because the key makes the write idempotent: if the
        first call did land after all, the system of record returns it instead
        of paying twice. A partial or excess change is never retried.

        Returns the result, whether it recovered, and the re-plan as
        ``(reason_code, note)``."""
        trace.span("recover.start", reason="read-back did not match the intended change")
        after = self._read(connector, task_class, order, column)
        result = verification.verify(before=before, after=after, intended_delta=intended_delta)
        trace.span("recover.reconcile", after=after, actual_delta=result.actual_delta, matched=result.matched)
        if result.matched:
            replan = _REPLANS["landed_late"]
            trace.span("recover.replan", reason_code="landed_late", next_action="accept_reconciled", note=replan[1])
            trace.span("recover.done", recovered=True, how="reconciled: the change had landed")
            return result, True, replan
        if abs(result.actual_delta) >= 0.005:
            replan = _REPLANS["partial_change"]
            trace.span("recover.replan", status="error", reason_code="partial_change",
                       next_action="hand_to_person", note=replan[1])
            trace.span("recover.done", status="error", recovered=False,
                       how="partial change; left for a person")
            return result, False, replan
        replan = _REPLANS["no_change"]
        trace.span("recover.replan", reason_code="no_change", next_action="retry_same_key", note=replan[1])
        try:
            trace.span("recover.retry", idempotency_key=key)
            retry_permit = PolicyGate(self._conn).issue(
                policy=policy,
                task_class=task_class,
                tool=task_class,
                order_id=request.order_id,
                amount=request.amount,
                authorized=authorized,
                attempted=attempted,
                license_level=int(state.effective_level),
                approved=approved,
                actor=actor,
            )
            if isinstance(retry_permit, BlockedPermit):
                raise ConnectorError(f"Recovery execution blocked: {retry_permit.reason}")
            tool_result = connector.apply(
                task_class, order, request.amount, idempotency_key=key, permit=retry_permit,
            )
            trace.span("tool.result", ok=tool_result.ok, message=tool_result.message,
                       reference=tool_result.reference, trusted=False, attempt=2)
        except ConnectorError as refusal:
            trace.span("recover.done", status="error", recovered=False, how=str(refusal)[:200])
            return result, False, replan
        after = self._read(connector, task_class, order, column)
        result = verification.verify(before=before, after=after, intended_delta=intended_delta)
        trace.span("verify.readback", source=connector.name, before=before, after=after,
                   actual_delta=result.actual_delta, intended_delta=intended_delta,
                   matched=result.matched, verified=True, attempt=2)
        trace.span("recover.done", status="ok" if result.matched else "error",
                   recovered=result.matched, how="retried with the same idempotency key")
        return result, result.matched, replan

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
        result, idempotency_key, actor, effects, trace, plan, policy_version,
        recovered=False, ticket_id=None,
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
                executed=executed and status not in (RunStatus.SUGGESTED, RunStatus.FAILED),
                before_refunded=result.before,
                after_refunded=result.after,
                idempotency_key=idempotency_key,
                actor_id=actor.actor_id,
                actor_role=actor.role.value,
                policy_version=policy_version,
                fault_mode=effects.mode.value,
                trace_id=trace.trace_id,
                notes=plan.rationale,
                recovered=recovered,
                ticket_id=ticket_id,
            ),
        )

    def _update_dial(
        self, task_class, status, found, run_id, trace_id, actor, policy
    ) -> Transition:
        if status is RunStatus.DEMOTED:
            reason = "; ".join(d.message for d in found)
            return self._licenses.apply_detection(
                task_class, run_id=run_id, trace_id=trace_id, reason=reason, actor=actor
            )
        if status is RunStatus.CLEAN:
            evaluation = self._policy_service.evaluation_for(
                task_class, policy=policy
            )
            return self._licenses.apply_clean_run(
                task_class,
                run_id=run_id,
                trace_id=trace_id,
                actor=actor,
                evaluation=evaluation,
            )
        # Suggestions and pending approvals do not move the dial.
        state = self._licenses.get_or_create(task_class)
        return Transition(old=state, new=state, kind="noop", git_sha=None)
