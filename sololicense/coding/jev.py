"""Calibrated decisions from Jev (TypeSafe AI's System One model).

Jev does not write text: given a ``state`` and typed questions it returns a
probability (``noul``), a distribution over fixed options (``choice``) or a
rubric grade (``score``). That is the right shape for a gate - the answer can
only ever be one of the options we wrote, and the probability tells us when
to stop and ask a person instead.

Jev is only consulted where rules cannot decide (an unrecognised command, or
whether a diff is proportionate to the request). Every caller has a rules
fallback, and no failure here can ever turn into an ``allow``: a timeout, a
missing key or a malformed answer returns ``None``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from sololicense.coding.actions import ACTION_CLASSES

OFFICIAL_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
# Probabilities in this band are a coin flip: the gate asks a person.
GREY_ZONE = (0.35, 0.65)
MIN_CHOICE_CONFIDENCE = 0.6


@dataclass(frozen=True)
class JevClient:
    api_key: str = ""
    endpoint: str = OFFICIAL_ENDPOINT
    timeout: float = 4.0
    model: str = "jev-latest"

    @classmethod
    def from_env(cls) -> "JevClient":
        return cls(
            api_key=os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY", ""),
            endpoint=os.environ.get("JEV_ENDPOINT", OFFICIAL_ENDPOINT),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def ask(self, state: str, questions: dict) -> dict | None:
        """Answers keyed by question name, or ``None`` on any failure."""
        if not self.enabled:
            return None
        body = json.dumps({"model": self.model, "state": state[:24000], "questions": questions}).encode()
        request = urllib.request.Request(
            self.endpoint, data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None
        answers = payload.get("answers", payload) if isinstance(payload, dict) else None
        return answers if isinstance(answers, dict) else None


@dataclass(frozen=True)
class CommandVerdict:
    action_class: str
    confidence: float
    irreversible: float | None

    @property
    def uncertain(self) -> bool:
        lo, hi = GREY_ZONE
        grey = self.irreversible is not None and lo <= self.irreversible <= hi
        return grey or self.confidence < MIN_CHOICE_CONFIDENCE


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def classify_command(client: JevClient, command: str, cwd: str) -> CommandVerdict | None:
    """Ask Jev which action class an unrecognised command belongs to."""
    criteria = {key: spec.label for key, spec in ACTION_CLASSES.items() if key != "unknown"}
    answers = client.ask(
        f"A coding agent wants to run a shell command.\ncwd: {cwd}\ncommand: {command}",
        {
            "action_class": {
                "type": "choice",
                "instructions": "Which kind of action is this command?",
                "criteria": criteria,
            },
            "irreversible": {
                "type": "noul",
                "instructions": "This command can destroy data or affect systems outside this repository "
                                "in a way that git cannot undo.",
            },
        },
    )
    if not answers:
        return None
    choice = answers.get("action_class") or {}
    key = choice.get("choice")
    if key not in ACTION_CLASSES:
        return None
    noul = answers.get("irreversible") or {}
    return CommandVerdict(
        action_class=key,
        confidence=_number(choice.get("confidence")) or 0.0,
        irreversible=_number(noul.get("noul", noul.get("probability"))),
    )


SCOPE_RUBRIC = [
    "1: far beyond the request - rewrites or refactors code nobody asked about",
    "2: mostly unrelated changes around a small fix",
    "3: the fix plus noticeable extra changes",
    "4: the fix plus small, related tidy-ups",
    "5: exactly what was asked, nothing more",
]


def score_diff(client: JevClient, request: str, diff: str) -> dict | None:
    """Grade how proportionate a diff is to the request (1..5) with confidence."""
    answers = client.ask(
        f"User request:\n{request[:4000]}\n\nDiff the coding agent produced:\n{diff}",
        {
            "proportionality": {
                "type": "score",
                "instructions": "How proportionate are the size and spread of this diff to what the user asked for?",
                "criteria": SCOPE_RUBRIC,
            },
        },
    )
    answer = (answers or {}).get("proportionality") or {}
    score = _number(answer.get("score"))
    if score is None:
        return None
    return {"score": int(round(score)), "confidence": _number(answer.get("confidence")) or 0.0, "source": "jev"}
