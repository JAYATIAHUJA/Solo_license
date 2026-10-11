"""Fault injector.

Translates an armed :class:`FaultMode` into concrete, deterministic effects on
a single run. Two faults, two failure signatures the detections are built to
catch:

    QUIET_FAILURE    -> suppress the DB write; the execute tool still "succeeds".
                        Verification then measures a zero delta → state_mismatch.
    POLICY_VIOLATION -> force the agent to attempt an auto-execution its license
                        does not permit → policy_breach.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sololicense.db.repositories import faults as faults_repo
from sololicense.domain.models import FaultMode


@dataclass(frozen=True)
class FaultEffects:
    """How an armed fault bends the next run."""

    mode: FaultMode
    suppress_write: bool      # tool claims success but SQLite is untouched
    force_auto_execute: bool  # attempt auto-exec regardless of the license
    skip_verification: bool   # execute but do not read SQLite back

    @property
    def active(self) -> bool:
        return self.mode is not FaultMode.NONE


def effects_for(mode: FaultMode) -> FaultEffects:
    """Pure mapping from an armed mode to its effects."""
    return FaultEffects(
        mode=mode,
        suppress_write=mode is FaultMode.QUIET_FAILURE,
        force_auto_execute=mode is FaultMode.POLICY_VIOLATION,
        skip_verification=mode is FaultMode.SKIP_VERIFICATION,
    )


class FaultInjector:
    """Thin service over the armed-faults repository."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def arm(self, task_class: str, mode: FaultMode) -> None:
        faults_repo.arm(self._conn, task_class, mode)
        self._conn.commit()

    def peek(self, task_class: str) -> FaultMode:
        return faults_repo.peek(self._conn, task_class)

    def consume_effects(self, task_class: str) -> FaultEffects:
        """Read and clear the armed fault, returning its effects."""
        mode = faults_repo.consume(self._conn, task_class)
        self._conn.commit()
        return effects_for(mode)
