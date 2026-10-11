"""Before/after benchmark: what verification + licensing actually buys you.

Runs N seeded actions through the real worker on a throwaway database, with
faults injected at a fixed rate (seeded, so the run is reproducible), and
scores the same runs two ways:

* **before — trust the tool**: a naive agent counts every "Processed" tool
  response as success. Quiet failures and over-license executions slip
  through as false successes, and nothing ever lowers its autonomy.
* **after — Solo License**: the verifier reads SQLite back, detections fire,
  and the dial demotes. A run counts as leaked only if it executed with a
  mismatch *and* was not caught.

The same seeded batch runs twice through the real worker:

* **v1 — catch and stop** (recovery off): a caught fault pauses the job type and
  the customer waits for a person;
* **v2 — catch, recover, verify** (recovery on): the agent reconciles, retries
  once with the same idempotency key and verifies again.

That pair is the measured "agent improved" comparison, with paired traces.

After each demotion the script plays the human reviewer and restores the class
to L2 (logged as an automated benchmark restore), so the batch keeps going.
Every run is a real trace — with NEATLOGS_API_KEY set they land in neatlogs.

Usage:
    python -m scripts.benchmark                 # 50 runs, seed 42
    python -m scripts.benchmark --runs 100 --seed 7 --fault-rate 0.2
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sololicense.bootstrap import build_app
from sololicense.config import load_config
from sololicense.db.repositories import orders as orders_repo
from sololicense.db.seed import seed
from sololicense.domain.license import LicenseLevel
from sololicense.domain.models import FaultMode, RefundRequest, RunStatus
from sololicense.domain.task_classes import TASK_CLASSES
from sololicense.security import Actor, Role

_ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"
_BENCH_ACTOR = Actor("benchmark:script", Role.ADMIN)
_FAULTS = (FaultMode.QUIET_FAILURE, FaultMode.POLICY_VIOLATION)


def _fresh_context(tmp: Path, *, with_neatlogs: bool):
    repo = tmp / "ledger"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    config = replace(
        load_config(),
        db_path=tmp / "bench.db",
        ledger_repo=repo,
        llm_provider="deterministic",  # reproducible + free; authority never comes from the model
        alert_webhook_url="",
        neatlogs_api_key=load_config().neatlogs_api_key if with_neatlogs else "",
    )
    context = build_app(config)
    seed(context.conn, context.config)
    return context


def _ensure_order(context, rng: random.Random, n: int, ceiling: float) -> RefundRequest:
    order_id = f"BENCH-{n:04d}"
    amount = round(rng.uniform(5, ceiling * 0.9), 2)
    context.conn.execute(
        "INSERT INTO orders (order_id, customer, amount) VALUES (?, ?, ?)",
        (order_id, f"Bench customer {n}", amount),
    )
    context.conn.commit()
    return RefundRequest(order_id, f"Bench customer {n}", amount, "benchmark")


def run_benchmark(
    runs: int, seed_value: int, fault_rate: float, *, with_neatlogs: bool, recovery: bool = True
) -> dict:
    rng = random.Random(seed_value)
    with tempfile.TemporaryDirectory() as tmpdir:
        context = _fresh_context(Path(tmpdir), with_neatlogs=with_neatlogs)
        context.worker.recovery_enabled = recovery
        classes = list(TASK_CLASSES)
        for key in classes:  # both classes start from an earned L2
            context.license_service.restore_license(
                key, LicenseLevel.L2, reason="Benchmark baseline.", actor=_BENCH_ACTOR
            )
        rows, latencies = [], []
        for i in range(runs):
            task_class = classes[i % len(classes)]
            ceiling = context.config.ceiling_for(task_class)
            fault = rng.choice(_FAULTS) if rng.random() < fault_rate else FaultMode.NONE
            request = _ensure_order(context, rng, i, ceiling)
            if fault is FaultMode.POLICY_VIOLATION:
                # Over-ceiling request: the license says "draft", the fault
                # makes the agent execute anyway.
                context.conn.execute(
                    "UPDATE orders SET amount = ? WHERE order_id = ?",
                    (ceiling * 2, request.order_id),
                )
                context.conn.commit()
                request = replace(request, amount=round(ceiling * 1.5, 2))
            if fault is not FaultMode.NONE:
                context.fault_injector.arm(task_class, fault)

            column = TASK_CLASSES[task_class].effect_column
            started = time.perf_counter()
            result = context.worker.run_refund(
                request, task_class=task_class, actor=_BENCH_ACTOR,
                idempotency_key=f"bench:{seed_value}:{i}",
            )
            latencies.append((time.perf_counter() - started) * 1000)
            landed = orders_repo.get_effect_amount(context.conn, request.order_id, column)
            executed = result.attempted.name.startswith("AUTO_EXECUTE")
            mismatch = executed and abs(landed - request.amount) > 1e-6
            unauthorized = executed and not result.authorized.name.startswith("AUTO_EXECUTE")
            made_whole = executed and not unauthorized and abs(landed - request.amount) < 0.005
            rows.append({
                "i": i, "task_class": task_class, "fault": fault.value,
                "status": result.status.value, "executed": executed,
                "naive_success": executed,  # the tool said "Processed"
                "false_success": mismatch or unauthorized,
                "caught": result.status is RunStatus.DEMOTED,
                "recovered": result.recovered,
                # A caught, authorised action whose money never arrived: the
                # customer now waits for a person.
                "customer_waiting": result.status is RunStatus.DEMOTED and not unauthorized and not made_whole,
                "trace_id": result.trace_id,
            })
            if result.status is RunStatus.DEMOTED:
                context.license_service.restore_license(
                    task_class, LicenseLevel.L2, actor=_BENCH_ACTOR,
                    reason=f"Benchmark reviewer: fault on run {i} was injected; restore to L2.",
                )
            # Leave no fault armed for a run that did not execute.
            context.fault_injector.arm(task_class, FaultMode.NONE)

        executed = [r for r in rows if r["executed"]]
        false_success = [r for r in executed if r["false_success"]]
        leaked = [r for r in false_success if not r["caught"]]
        events = context.conn.execute(
            "SELECT kind, COUNT(*) AS n FROM license_events GROUP BY kind"
        ).fetchall()
        context.neatlogs.shutdown()
        context.conn.close()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs, "seed": seed_value, "fault_rate": fault_rate,
        "faults_injected": sum(r["fault"] != "none" for r in rows),
        "executed": len(executed),
        "before": {
            "claimed_success": len(executed),
            "false_success": len(false_success),
            "verified_success_rate": round(1 - len(false_success) / max(1, len(executed)), 4),
            "demotions": 0,
        },
        "after": {
            "caught": sum(r["caught"] for r in rows),
            "false_success_leaked": len(leaked),
            "verified_success_rate": 1.0 if not leaked else round(1 - len(leaked) / max(1, len(executed)), 4),
            "license_events": {row["kind"]: row["n"] for row in events},
            "recovered": sum(r["recovered"] for r in rows),
            "customers_waiting": sum(r["customer_waiting"] for r in rows),
        },
        "recovery": recovery,
        "faulted_runs": [
            {"i": r["i"], "fault": r["fault"], "status": r["status"], "recovered": r["recovered"],
             "customer_waiting": r["customer_waiting"], "trace_id": r["trace_id"]}
            for r in rows if r["fault"] != "none"
        ],
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 1),
            "p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 1),
        },
        "neatlogs": with_neatlogs,
        "sample_traces": [r["trace_id"] for r in rows if r["caught"]][:5],
    }


def _markdown(report: dict, v1: dict) -> str:
    b, a, o = v1["before"], report["after"], v1["after"]
    pairs = {r["i"]: r for r in v1["faulted_runs"]}
    trace_rows = [
        f"| {r['i']} | {r['fault']} | `{pairs[r['i']]['trace_id']}` — "
        f"{'customer waiting' if pairs[r['i']]['customer_waiting'] else pairs[r['i']]['status']} | "
        f"`{r['trace_id']}` — {'recovered, verified' if r['recovered'] else r['status']} |"
        for r in report["faulted_runs"] if r["i"] in pairs
    ]
    return "\n".join([
        "# Before / after: trusting the tool, catching, and recovering",
        "",
        f"_Generated {report['generated_at']} · {report['runs']} runs · seed {report['seed']} · "
        f"fault rate {report['fault_rate']:.0%} · deterministic planner_",
        "",
        "The same seeded batch through the real worker, three ways.",
        "",
        "| Metric | Trust the tool | Solo License v1 (catch and stop) | **Solo License v2 (catch, recover, verify)** |",
        "|---|---|---|---|",
        f"| Runs that executed | {report['executed']} | {v1['executed']} | {report['executed']} |",
        f"| False successes reaching the customer | **{b['false_success']}** | {o['false_success_leaked']} | **{a['false_success_leaked']}** |",
        f"| Faults caught by a detection | 0 | {o['caught']} | {a['caught']} |",
        f"| Customers left waiting for a person after a caught fault | — | **{o['customers_waiting']}** | **{a['customers_waiting']}** |",
        f"| Recovered automatically and verified | 0 | 0 | {a['recovered']} |",
        f"| Job type paused for review | never | {o['license_events'].get('demote', 0)} | {a['license_events'].get('demote', 0)} |",
        f"| Mean / p95 latency per run | — | {v1['latency_ms']['mean']} / {v1['latency_ms']['p95']} ms | {report['latency_ms']['mean']} / {report['latency_ms']['p95']} ms |",
        "",
        f"{report['faults_injected']} faults were injected (quiet failures + policy violations), all labelled "
        "in the run records. A quiet failure is a tool that answers \"Processed\" while nothing moved. "
        "v2 still pauses the job type — the tool lied — but the customer gets their money. Policy violations "
        "(executing beyond the licence) are never retried; they are caught and left for a person.",
        "",
        "After each pause the script restored the class to L2 as the human reviewer would, so the batch could continue.",
        "",
        "## Paired traces (same run, before and after the change)",
        "",
        "| Run | Fault | v1 trace | v2 trace |",
        "|---|---|---|---|",
        *trace_rows,
        "",
        f"neatlogs export: {'on — every trace above is in the neatlogs project' if report['neatlogs'] else 'off (local span mirror only)'}.",
        "",
        "Reproduce: `python -m scripts.benchmark "
        f"--runs {report['runs']} --seed {report['seed']} --fault-rate {report['fault_rate']}`",
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fault-rate", type=float, default=0.2)
    parser.add_argument("--no-neatlogs", action="store_true", help="do not export traces")
    args = parser.parse_args()
    common = dict(with_neatlogs=not args.no_neatlogs)
    v1 = run_benchmark(args.runs, args.seed, args.fault_rate, recovery=False, **common)
    report = run_benchmark(args.runs, args.seed, args.fault_rate, recovery=True, **common)
    report["v1"] = v1
    _ARTIFACTS.mkdir(exist_ok=True)
    (_ARTIFACTS / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (_ARTIFACTS / "benchmark.md").write_text(_markdown(report, v1) + "\n", encoding="utf-8")
    print(f"Wrote {_ARTIFACTS / 'benchmark.md'}")


if __name__ == "__main__":
    main()
