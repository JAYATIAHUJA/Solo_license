"""When a coding agent has earned the next level for an action class.

Two conditions, both required:

* a **floor** of verified successes at the current level, so nothing is ever
  promoted on one lucky run; and
* the **economic bound**: the upper credible bound of the class's failure rate
  is below the break-even rate, where the saving is the developer time an
  approval prompt costs and the risk is what one unattended mistake of this
  class costs. Cheap, reversible classes (run the tests) earn quickly; costly
  ones (push to a remote) need far more evidence, and some never auto-run.
"""

from __future__ import annotations

from dataclasses import dataclass

from sololicense.coding.actions import ACTION_CLASSES
from sololicense.domain.trust import TrustLadder

# Developer time per action at L0 (an interruption: stop, read, approve),
# L1 (glance at an auto-allowed line) and L2 (nothing).
MINUTES_BY_LEVEL = (1.0, 0.25, 0.0)
DEVELOPER_HOURLY_COST = 75.0
# Verified successes needed at the current level before a promotion.
MIN_SUCCESSES = {0: 3, 1: 5}


@dataclass(frozen=True)
class CodingLadder:
    hourly_cost: float = DEVELOPER_HOURLY_COST
    confidence: float = 0.9

    def ladder(self, action_class: str) -> TrustLadder:
        return TrustLadder(
            minutes_by_level=MINUTES_BY_LEVEL,
            hourly_cost=self.hourly_cost,
            incident_cost=ACTION_CLASSES[action_class].incident_cost,
            confidence=self.confidence,
        )

    def next_level(self, action_class: str, level: int, successes: int, failures: int,
                   successes_at_level: int, ceiling: int | None = None) -> int | None:
        """The level to promote to now, or ``None``. ``ceiling`` is the
        policy's limit for this class in this repo (never above the built-in one)."""
        top = ACTION_CLASSES[action_class].max_level if ceiling is None else min(ceiling, ACTION_CLASSES[action_class].max_level)
        if level >= top:
            return None
        if successes_at_level < MIN_SUCCESSES.get(level, 0):
            return None
        if not self.ladder(action_class).step(level).earned(successes, failures):
            return None
        return level + 1

    def progress(self, action_class: str, level: int, successes: int, failures: int,
                 successes_at_level: int, ceiling: int | None = None) -> dict:
        """What the dashboard shows: how far the next level is."""
        spec = ACTION_CLASSES[action_class]
        top = spec.max_level if ceiling is None else min(ceiling, spec.max_level)
        if level >= top:
            return {"next_level": None, "runs_needed": 0,
                    "ceiling": top, "always_asks": top == 0, "capped_by_policy": top < spec.max_level}
        economic = self.ladder(action_class).step(level).runs_needed(successes, failures)
        floor = max(0, MIN_SUCCESSES.get(level, 0) - successes_at_level)
        needed = None if economic is None else max(economic, floor)
        return {"next_level": level + 1, "runs_needed": needed,
                "ceiling": top, "always_asks": False, "capped_by_policy": top < spec.max_level}
