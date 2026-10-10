"""Generate the before/after evidence artifact.

Runs two comparable refunds through the real system — a clean one and a
fault-injected one — and writes a side-by-side report with the numbers,
detections, dial transitions, trace ids, and git shas. This is the
judge-verifiable artifact referenced in the README and in #neatHack posts.

Usage:
    python -m scripts.generate_evidence            # uses the configured db
    python -m scripts.generate_evidence --fault policy_violation
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sololicense.agent.worker import RunResult
from sololicense.bootstrap import build_app
from sololicense.db.seed import seed
from sololicense.domain.models import FaultMode, RefundRequest

_ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
_CLEAN_ORDER = RefundRequest("ORD-1001", "Ada Lovelace", 25.00, "defective item")
_FAULT_ORDERS = {
    FaultMode.QUIET_FAILURE: RefundRequest(
        "ORD-1002", "Grace Hopper", 40.00, "late delivery"
    ),
    FaultMode.POLICY_VIOLATION: RefundRequest(
        "ORD-1004", "Katherine Johnson", 120.00, "disputed charge"
    ),
}


def _run_snapshot(result: RunResult) -> dict:
    return {
        "trace_id": result.trace_id,
        "status": result.status.value,
        "authorized": result.authorized.name,
        "attempted": result.attempted.name,
        "before_refunded": result.before_refunded,
        "after_refunded": result.after_refunded,
        "actual_delta": result.actual_delta,
        "detections": [
            {"rule": d.rule, "severity": d.severity, "message": d.message}
            for d in result.detections
        ],
        "dial": {
            "from": result.transition.old.level.name,
            "to": result.transition.new.level.name,
            "kind": result.transition.kind,
            "git_sha": result.transition.git_sha,
        },
        "plan_source": result.plan.source,
    }


def _markdown(before: dict, after: dict, fault: FaultMode) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Solo License — before / after evidence",
        "",
        f"_Generated {stamp}. Fault injected on the second run: "
        f"`{fault.value}`._",
        "",
        "| Field | Before (clean) | After (faulted) |",
        "|---|---|---|",
        f"| Trace id | `{before['trace_id']}` | `{after['trace_id']}` |",
        f"| Status | {before['status']} | {after['status']} |",
        f"| Authorized | {before['authorized']} | {after['authorized']} |",
        f"| Attempted | {before['attempted']} | {after['attempted']} |",
        f"| refunded_amount before | ${before['before_refunded']:.2f} | "
        f"${after['before_refunded']:.2f} |",
        f"| refunded_amount after | ${before['after_refunded']:.2f} | "
        f"${after['after_refunded']:.2f} |",
        f"| Verified delta | ${before['actual_delta']:.2f} | "
        f"${after['actual_delta']:.2f} |",
        f"| Detections | {len(before['detections'])} | "
        f"{len(after['detections'])} |",
        f"| Dial | {before['dial']['from']} -> {before['dial']['to']} "
        f"({before['dial']['kind']}) | {after['dial']['from']} -> "
        f"{after['dial']['to']} ({after['dial']['kind']}) |",
        "",
    ]
    if after["detections"]:
        lines.append("## Detections that fired on the faulted run")
        lines.append("")
        for d in after["detections"]:
            lines.append(f"- **{d['rule']}** ({d['severity']}): {d['message']}")
        lines.append("")
    if after["dial"]["git_sha"]:
        lines.append(
            f"Demotion committed to the git ledger as "
            f"`{after['dial']['git_sha']}`."
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    # Windows consoles default to cp1252; print UTF-8 regardless.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

    parser = argparse.ArgumentParser(description="Generate before/after evidence.")
    parser.add_argument(
        "--fault",
        choices=[FaultMode.QUIET_FAILURE.value, FaultMode.POLICY_VIOLATION.value],
        default=FaultMode.QUIET_FAILURE.value,
    )
    args = parser.parse_args()
    fault = FaultMode(args.fault)

    app = build_app()
    seed(app.conn, app.config)  # deterministic starting point

    before = _run_snapshot(app.worker.run_refund(_CLEAN_ORDER))

    app.fault_injector.arm("refund", fault)
    after = _run_snapshot(app.worker.run_refund(_FAULT_ORDERS[fault]))

    _ARTIFACTS.mkdir(exist_ok=True)
    report = {"fault": fault.value, "before": before, "after": after}
    (_ARTIFACTS / "evidence_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    md = _markdown(before, after, fault)
    (_ARTIFACTS / "evidence_report.md").write_text(md, encoding="utf-8")

    print(md)
    print(f"Wrote artifacts/evidence_report.md and .json")


if __name__ == "__main__":
    main()
