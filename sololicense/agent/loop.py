"""The ticket agent — one customer message, handled from start to finish.

Each step reads the result of the one before it and decides what to do next:

    read        understand the message (LLM or rules); stop if it tries to steer the agent
    find_order  by order number, or by the sender's email when none is given
    policy      the shop's own rules (refund window, identity, what is left to pay)
    act         the licensed worker: licence check → execute → verify → recover
    reply       a reply for the customer that states only verified facts

The model reads and proposes; the policy, the licence and the read-back decide.
Every step is a span in the same neatlogs trace as the money movement.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from sololicense.agent import policy as policy_rules
from sololicense.agent.intake import Intake, parse_message
from sololicense.agent.worker import RefundWorker, RunResult
from sololicense.config import Config
from sololicense.db.repositories import orders as orders_repo
from sololicense.domain.models import RefundRequest, RunStatus
from sololicense.domain.task_classes import get_spec
from sololicense.observability.tracer import Tracer
from sololicense.security import Actor
from sololicense.services.license_service import SYSTEM_ACTOR

# Ticket outcomes, as the inbox shows them.
DONE, WAITING, DECLINED, NEEDS_INFO, NEEDS_HUMAN = "done", "waiting", "declined", "needs_info", "needs_human"


@dataclass
class Step:
    name: str
    status: str          # ok | stop | error
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class TicketOutcome:
    status: str
    summary: str
    reply: str
    steps: list[Step] = field(default_factory=list)
    intake: Intake | None = None
    order_id: str | None = None
    amount: float | None = None
    task_class: str | None = None
    run: RunResult | None = None
    trace_id: str | None = None

    @property
    def run_id(self) -> int | None:
        return self.run.run_id if self.run else None

    def steps_json(self) -> str:
        return json.dumps([s.as_dict() for s in self.steps])


def _money(value: float) -> str:
    return f"${value:,.2f}"


class TicketAgent:
    def __init__(self, conn: sqlite3.Connection, config: Config, *, tracer: Tracer, worker: RefundWorker) -> None:
        self._conn = conn
        self._config = config
        self._tracer = tracer
        self._worker = worker

    def handle(
        self,
        message: str,
        *,
        sender: str | None = None,
        ticket_id: int | None = None,
        idempotency_key: str | None = None,
        actor: Actor = SYSTEM_ACTOR,
    ) -> TicketOutcome:
        trace = self._tracer.start_trace("ticket", ticket_id=ticket_id, sender=sender or "", actor=actor.actor_id)
        try:
            outcome = self._handle(message, sender, ticket_id, idempotency_key, actor, trace)
        except Exception as error:
            trace.span("ticket.error", status="error", error_type=type(error).__name__)
            trace.flush(self._conn, None)
            raise
        trace.span("ticket.done", status="ok" if outcome.status in (DONE, WAITING) else "error",
                   outcome=outcome.status, summary=outcome.summary)
        trace.flush(self._conn, outcome.run_id)
        self._conn.commit()
        outcome.trace_id = trace.trace_id
        return outcome

    # --- steps ---------------------------------------------------------------

    def _handle(self, message, sender, ticket_id, idempotency_key, actor, trace) -> TicketOutcome:
        steps: list[Step] = []

        def step(name: str, status: str, detail: str, **attrs) -> None:
            steps.append(Step(name, status, detail))
            trace.span(f"agent.{name}", status="error" if status == "error" else "ok", detail=detail, **attrs)

        # 1. read -------------------------------------------------------------
        intake = parse_message(message, self._config, self._conn)
        spec = get_spec(intake.task_class)
        step("read", "ok",
             f"Asks for {spec.label.lower()}" + (f" on {intake.order_id}" if intake.order_id else "")
             + (f", {_money(intake.amount)}" if intake.amount is not None else "") + " · read by " + (intake.source.removeprefix("llm:") if intake.source.startswith("llm:") else "built-in rules"),
             source=intake.source, task_class=intake.task_class, confidence=intake.confidence)
        if intake.note:
            step("read", "ok", intake.note)
        if intake.suspicious:
            step("read", "stop", "Sent to a person: the message tries to change how the agent works.")
            return TicketOutcome(
                NEEDS_HUMAN, "Flagged for a person: the message tries to steer the agent.",
                self._reply_needs_human(), steps, intake,
            )

        # 2. find the order -----------------------------------------------------
        order, why = self._find_order(intake, sender)
        if order is None:
            step("find_order", "stop", why)
            return TicketOutcome(NEEDS_INFO, why, self._reply_ask_order(), steps, intake)
        step("find_order", "ok", why, order_id=order["order_id"], source=order["source"])

        # 3. policy ---------------------------------------------------------------
        verdict = policy_rules.check(
            order, task_class=intake.task_class, amount=intake.amount, sender=sender,
            refund_window_days=self._config.refund_window_days,
        )
        for note in verdict.notes:
            step("policy", "ok", note)
        if not verdict.allowed:
            step("policy", "stop", " ".join(verdict.reasons), escalate=verdict.escalate)
            status = NEEDS_HUMAN if verdict.escalate else DECLINED
            reply = self._reply_needs_human() if verdict.escalate else self._reply_declined(order, verdict.reasons)
            return TicketOutcome(status, verdict.reasons[0], reply, steps, intake, order["order_id"],
                                 task_class=intake.task_class)
        step("policy", "ok", f"Within policy: {_money(verdict.amount)} {spec.label.lower()} on {order['order_id']}.",
             amount=verdict.amount)

        # 4. act through the licence --------------------------------------------------
        run = self._worker.run_refund(
            RefundRequest(order["order_id"], order["customer"], verdict.amount, intake.reason),
            task_class=intake.task_class,
            idempotency_key=idempotency_key,
            actor=actor,
            trace=trace,
            ticket_id=ticket_id,
        )
        step("act", "ok" if run.status in (RunStatus.CLEAN, RunStatus.PENDING_APPROVAL, RunStatus.SUGGESTED) else "error",
             self._act_detail(run, spec.label.lower()), run_status=run.status.value)
        return self._finish(run, order, verdict.amount, intake, steps, step)

    def _find_order(self, intake: Intake, sender: str | None):
        if intake.order_id:
            order = orders_repo.get_order(self._conn, intake.order_id)
            if order is not None:
                return order, f"Found {order['order_id']} ({order['customer']}, {_money(order['amount'])})."
            if not sender:
                return None, f"No order {intake.order_id} in this store."
        if sender:
            candidates = [o for o in orders_repo.find_by_email(self._conn, sender)
                          if orders_repo.remaining_balance(o) > 0]
            if intake.amount is not None:
                exact = [o for o in candidates if abs(float(o["amount"]) - intake.amount) < 0.005]
                candidates = exact or candidates
            if len(candidates) == 1:
                order = candidates[0]
                return order, f"No order number given; {sender} has one open order, {order['order_id']}."
            if candidates:
                ids = ", ".join(o["order_id"] for o in candidates[:5])
                return None, f"{sender} has {len(candidates)} open orders ({ids}); asked which one."
            return None, f"No open order found for {sender}."
        return None, "No order number in the message and no sender email to look it up."

    @staticmethod
    def _act_detail(run: RunResult, label: str) -> str:
        if run.error:
            return f"The payment system refused: {run.error}"
        if run.status is RunStatus.CLEAN:
            return f"{label.capitalize()} done and verified: {_money(run.actual_delta)} moved."
        if run.status is RunStatus.PENDING_APPROVAL:
            return "Prepared; waiting for a person to approve (licence level or amount limit)."
        if run.status is RunStatus.SUGGESTED:
            return "Suggested to a person; this job type may not act alone right now."
        if run.recovered:
            return "The first attempt did not land; the agent retried safely and verified it. Licence paused for review."
        return "A safety check failed; nothing was confirmed. Licence paused and sent to a person."

    def _finish(self, run: RunResult, order, amount, intake, steps, step) -> TicketOutcome:
        spec = get_spec(run.task_class)
        args = dict(intake=intake, order_id=order["order_id"], amount=amount, task_class=run.task_class, run=run)
        if run.error:
            step("reply", "stop", "Escalated: the payment system refused the action.")
            return TicketOutcome(NEEDS_HUMAN, f"Payment system refused: {run.error}", self._reply_needs_human(), steps, **args)
        if run.status is RunStatus.CLEAN or run.recovered:
            verified = run.actual_delta
            reply = self._reply_done(order, spec.key, verified)
            how = " after a safe retry" if run.recovered else ""
            step("reply", "ok", f"Told the customer {_money(verified)} is on its way (verified{how}).")
            return TicketOutcome(DONE, f"{spec.label} of {_money(verified)} verified on {order['order_id']}{how}.",
                                 reply, steps, **args)
        if run.status in (RunStatus.PENDING_APPROVAL, RunStatus.SUGGESTED):
            step("reply", "ok", "Told the customer a teammate will confirm.")
            return TicketOutcome(WAITING, f"{spec.label} of {_money(amount)} on {order['order_id']} waits for approval.",
                                 self._reply_waiting(order, spec.key, amount), steps, **args)
        step("reply", "stop", "Escalated: the result could not be verified.")
        return TicketOutcome(NEEDS_HUMAN, "Safety check failed; licence paused.", self._reply_needs_human(), steps, **args)

    # --- replies: only verified facts ------------------------------------------------

    def _shop(self) -> str:
        row = self._conn.execute("SELECT value FROM settings WHERE key = 'business_name'").fetchone()
        return (row["value"] if row else "") or "our team"

    def _reply_done(self, order, task_class: str, amount: float) -> str:
        if task_class == "store_credit":
            what = f"{_money(amount)} in store credit has been added to your account"
        else:
            what = f"a refund of {_money(amount)} has been issued to your original payment method"
        return (f"Hi {order['customer'].split()[0]}, thanks for getting in touch. For order {order['order_id']}, "
                f"{what}. Card refunds usually show within 5–10 business days. — {self._shop()}")

    def _reply_waiting(self, order, task_class: str, amount: float) -> str:
        what = "store credit" if task_class == "store_credit" else "refund"
        return (f"Hi {order['customer'].split()[0]}, thanks for reaching out about order {order['order_id']}. "
                f"We've prepared a {what} of {_money(amount)} and a teammate will confirm it shortly. — {self._shop()}")

    def _reply_declined(self, order, reasons: list[str]) -> str:
        return (f"Hi {order['customer'].split()[0]}, thanks for your message about order {order['order_id']}. "
                f"{' '.join(reasons)} Reply here if you'd like us to arrange that. — {self._shop()}")

    def _reply_ask_order(self) -> str:
        return (f"Thanks for getting in touch! Could you send the order number (it's in your receipt email) "
                f"so we can sort this out right away? — {self._shop()}")

    def _reply_needs_human(self) -> str:
        return f"Thanks for your message. A member of our team will look at this personally and reply soon. — {self._shop()}"
