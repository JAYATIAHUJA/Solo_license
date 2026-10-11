"""License service - the one orchestrator allowed to change the dial.

It composes the pure state machine (:mod:`sololicense.domain.license`) with
persistence, the event ledger, and the git ledger. Every transition it makes
is: compute new state → persist state + event (SQLite) → commit a git ledger
entry → back-link the git sha to the event.

Only three things move the dial, and they map one-to-one onto the ladder's
rules:
    * a verified-clean run adds evidence and may *promote* once the evidence
      proves the job type is reliable enough to be worth it (see
      :mod:`sololicense.domain.trust`);
    * a detection *demotes* (crash to L0 + quarantine);
    * a human *restores* after reading the evidence packet.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from typing import Callable

from sololicense.db.repositories import events as events_repo
from sololicense.db.repositories import license as license_repo
from sololicense.domain.license import (
    LicenseLevel,
    LicenseState,
    demote_on_detection,
    record_clean_run,
    record_rejection,
    restore,
)
from sololicense.domain.trust import TrustLadder
from sololicense.domain.policy import EvaluationProgress
from sololicense.services.git_ledger import GitLedger, LedgerEntry
from sololicense.security import Actor, Role


SYSTEM_ACTOR = Actor("system:license-service", Role.ADMIN)


@dataclass(frozen=True)
class Transition:
    """Result of a dial change, surfaced to the worker and UI."""

    old: LicenseState
    new: LicenseState
    kind: str            # promote | demote | restore | noop
    git_sha: str | None


class LicenseService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        ledger: GitLedger,
        *,
        ladder: TrustLadder,
        on_transition: Callable[..., None] | None = None,
    ) -> None:
        self._conn = conn
        self._ledger = ledger
        self._ladder = ladder
        self._on_transition = on_transition

    @property
    def ladder(self) -> TrustLadder:
        return self._ladder

    def progress(self, state: LicenseState) -> dict:
        """Evidence so far and how many verified jobs the next rung needs."""
        return self._ladder.progress(int(state.level), state.successes, state.failures)

    def get_or_create(self, task_class: str) -> LicenseState:
        """Return the task class's state, seeding a fresh L0 row if absent."""
        state = license_repo.get_state(self._conn, task_class)
        if state is None:
            state = LicenseState(task_class=task_class)
            license_repo.upsert_state(self._conn, state)
            self._conn.commit()
        return state

    def apply_clean_run(
        self,
        task_class: str,
        *,
        run_id: int | None,
        trace_id: str | None,
        actor: Actor = SYSTEM_ACTOR,
        evaluation: EvaluationProgress | None = None,
    ) -> Transition:
        """Credit a verified-clean run; optionally use policy-scoped evidence.

        Older callers retain the workspace threshold behavior. Worker calls
        provide an evaluation snapshot computed after the run was recorded,
        so only outcomes collected under this exact policy version can earn a
        promotion.
        """
        old = self.get_or_create(task_class)
        if evaluation is None:
            new = record_clean_run(old, ladder=self._ladder)
            promotion_reason = (
                "Verified evidence crossed the economic confidence threshold; earned "
                "{level} ({label})."
            )
        elif old.quarantined:
            new = old
            promotion_reason = ""
        else:
            # Evidence that predates this policy must never earn autonomy under
            # the new rules. Keep the lifetime audit tally, but only the policy
            # version's evaluation window determines a promotion.
            new = replace(
                old,
                successes=old.successes + 1,
                consecutive_clean_runs=evaluation.clean_runs,
                demoted_from=None,
            )
            if evaluation.eligible and old.level < LicenseLevel.L3:
                new = replace(
                    new,
                    level=LicenseLevel(old.level + 1),
                    consecutive_clean_runs=0,
                    demoted_from=None,
                )
            promotion_reason = (
                f"Policy evaluation met {evaluation.required_samples} clean-run "
                f"sample and {evaluation.required_pass_rate:.0%} verified pass-rate "
                "requirements; earned {level} ({label})."
            )
        if new.level > old.level:
            return self._persist(
                old,
                new,
                kind="promote",
                reason=promotion_reason.format(level=new.level.name, label=new.level.label),
                run_id=run_id,
                trace_id=trace_id,
                actor=actor,
            )
        # No rung change: persist the updated tally without a git event.
        license_repo.upsert_state(self._conn, new)
        self._conn.commit()
        return Transition(old=old, new=new, kind="noop", git_sha=None)

    def apply_rejection(self, task_class: str) -> LicenseState:
        """A person rejected the agent's proposal: record it as a failure."""
        new = record_rejection(self.get_or_create(task_class))
        license_repo.upsert_state(self._conn, new)
        self._conn.commit()
        return new

    def apply_detection(
        self,
        task_class: str,
        *,
        run_id: int | None,
        trace_id: str | None,
        reason: str,
        actor: Actor = SYSTEM_ACTOR,
    ) -> Transition:
        """Crash the dial to L0 and quarantine on a detection."""
        old = self.get_or_create(task_class)
        new = demote_on_detection(old)
        return self._persist(
            old,
            new,
            kind="demote",
            reason=reason,
            run_id=run_id,
            trace_id=trace_id,
            actor=actor,
        )

    def restore_license(
        self,
        task_class: str,
        target: LicenseLevel,
        *,
        reason: str,
        actor: Actor = SYSTEM_ACTOR,
    ) -> Transition:
        """Lift quarantine to a human-chosen level after evidence review."""
        old = self.get_or_create(task_class)
        new = restore(old, target)
        return self._persist(
            old,
            new,
            kind="restore",
            reason=reason,
            run_id=None,
            trace_id=None,
            actor=actor,
        )

    def _persist(
        self,
        old: LicenseState,
        new: LicenseState,
        *,
        kind: str,
        reason: str,
        run_id: int | None,
        trace_id: str | None,
        actor: Actor,
    ) -> Transition:
        """Persist state + event, then commit a git ledger entry and link it."""
        license_repo.upsert_state(self._conn, new)
        event_id = events_repo.insert_event(
            self._conn,
            task_class=new.task_class,
            kind=kind,
            from_level=int(old.level),
            to_level=int(new.level),
            reason=reason,
            run_id=run_id,
            actor_id=actor.actor_id,
            actor_role=actor.role.value,
        )
        self._conn.commit()

        git_sha = self._ledger.record(
            LedgerEntry(
                task_class=new.task_class,
                kind=kind,
                from_level=int(old.level),
                to_level=int(new.level),
                reason=reason,
                run_id=run_id,
                trace_id=trace_id,
            )
        )
        if git_sha:
            events_repo.set_git_sha(self._conn, event_id, git_sha)
            self._conn.commit()

        if self._on_transition is not None:
            try:
                self._on_transition(
                    task_class=new.task_class, kind=kind,
                    from_level=int(old.level), to_level=int(new.level),
                    reason=reason, run_id=run_id, git_sha=git_sha,
                )
            except Exception:  # alerts are best-effort; the dial already moved
                pass

        return Transition(old=old, new=new, kind=kind, git_sha=git_sha)
