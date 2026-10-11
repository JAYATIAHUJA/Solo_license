"""Outbound alerts for license changes.

When a detection demotes a task class, the people who own that workflow should
hear about it without watching a dashboard. The operator configures one
incoming-webhook URL (Slack, Discord, Teams via a workflow, or any endpoint);
the payload carries both ``text`` (Slack) and ``content`` (Discord) so either
renders it. Delivery is best-effort on a background thread: an alert must
never block or fail an agent run.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

_ICONS = {"demote": "🚨", "restore": "🛠️", "promote": "⬆️"}


def valid_webhook_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


def format_alert(
    *, business: str, task_class: str, kind: str, from_level: int,
    to_level: int, reason: str, run_id: int | None, git_sha: str | None,
) -> str:
    icon = _ICONS.get(kind, "•")
    lines = [
        f"{icon} *{business or 'Solo License'}* - `{task_class}` {kind} "
        f"L{from_level} → L{to_level}",
        reason,
    ]
    refs = []
    if run_id is not None:
        refs.append(f"run #{run_id}")
    if git_sha:
        refs.append(f"ledger {git_sha}")
    if kind == "demote":
        refs.append("quarantined until a human reviews the evidence packet")
    if refs:
        lines.append(" · ".join(refs))
    return "\n".join(lines)


@dataclass
class AlertNotifier:
    url: str
    business: str = ""
    kinds: tuple[str, ...] = ("demote", "restore", "promote")
    timeout_seconds: float = 5.0

    @property
    def enabled(self) -> bool:
        return valid_webhook_url(self.url)

    def notify(self, **event) -> None:
        if not self.enabled or event.get("kind") not in self.kinds:
            return
        text = format_alert(business=self.business, **event)
        threading.Thread(target=self.send, args=(text,), daemon=True).start()

    def send(self, text: str) -> tuple[bool, str]:
        """POST one message. Returns (ok, short status) and never raises."""
        body = json.dumps({"text": text, "content": text}).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "solo-license"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as resp:
                return True, f"HTTP {resp.status}"
        except Exception as error:  # network, 4xx/5xx, timeout
            return False, type(error).__name__
