"""Score Solo License on τ-bench — a standard, public customer-service benchmark.

Downloads the pinned τ-bench retail data (once, into data/taubench/), replays
every database write that GPT-4o and Claude 3.5 Sonnet made in the recorded
trajectories, and compares five autonomy policies. No API key, fully seeded.

    python -m scripts.taubench_eval            # -> artifacts/taubench.{json,md}
    python -m scripts.taubench_eval --orders 50

See sololicense/bench/taubench.py for the method and its assumptions.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sololicense.bench import taubench as tb

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "taubench"
ARTIFACTS = ROOT / "artifacts"
LABELS = {
    "full_auto": "Agent acts alone",
    "approve_all": "Person approves every write",
    "fixed_ladder": "Fixed ladder (3 clean in a row)",
    "guards_only": "Policy guards only",
    "solo_license": "Solo License",
}
INCIDENT_SWEEP = (1, 2, 5, 10, 20, 50, 120, 300, 1000)


def _mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 2)


def _sd(values: list[float]) -> float:
    return round(statistics.pstdev(values), 2)


def evaluate(episodes, costs: tb.Costs, *, orders: int, confidence: float, audit_rate: float) -> dict:
    results = {}
    for policy in tb.POLICIES:
        runs = [
            tb.simulate(policy, tb.stream(episodes, seed), costs=costs,
                        confidence=confidence, audit_rate=audit_rate, seed=seed).as_dict(costs)
            for seed in range(orders)
        ]
        results[policy] = {
            key: _mean([r[key] for r in runs]) for key in runs[0]
        } | {
            "harmful_sd": _sd([r["harmful"] for r in runs]),
            "cost_sd": _sd([r["cost"] for r in runs]),
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--orders", type=int, default=30, help="random arrival orders to average over")
    parser.add_argument("--confidence", type=float, default=0.9)
    parser.add_argument("--audit-rate", type=float, default=0.1)
    args = parser.parse_args()

    paths = tb.fetch(DATA)
    costs = tb.Costs()
    report = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "benchmark": "τ-bench retail (Sierra Research, MIT)",
            "repo": "https://github.com/sierra-research/tau-bench",
            "commit": tb.TAU_BENCH_COMMIT,
            "sha256": {name: tb.sha256_of(path) for name, path in paths.items()},
        },
        "settings": {
            "arrival_orders": args.orders,
            "confidence": args.confidence,
            "audit_rate": args.audit_rate,
            "costs": vars(costs),
        },
        "models": {},
    }
    for filename, model in tb.MODELS.items():
        episodes = tb.load_episodes(paths[filename], paths["orders.json"])
        writes = [w for e in episodes for w in e.writes]
        guard_hits = [w for w in writes if w.guards]
        report["models"][model] = {
            "episodes": len(episodes),
            "tasks": len({e.task_id for e in episodes}),
            "pass_hat_k": {k: round(tb.pass_hat_k(episodes, k), 4) for k in (1, 2, 4, 8)
                           if k <= max(e.trial for e in episodes) + 1},
            "writes": len(writes),
            "wrong_writes": sum(not w.correct for w in writes),
            "guards": {
                "held": len(guard_hits),
                "held_wrong": sum(not w.correct for w in guard_hits),
            },
            "job_types": tb.class_table(episodes, costs, args.confidence),
            "policies": evaluate(episodes, costs, orders=args.orders,
                                 confidence=args.confidence, audit_rate=args.audit_rate),
            "incident_sweep": {
                str(cost): {
                    policy: values["cost"]
                    for policy, values in evaluate(
                        episodes, replace(costs, incident=float(cost)), orders=max(5, args.orders // 3),
                        confidence=args.confidence, audit_rate=args.audit_rate,
                    ).items()
                }
                for cost in INCIDENT_SWEEP
            },
            "licensed_job_types": {
                str(cost): [
                    row["job_type"]
                    for row in tb.class_table(episodes, replace(costs, incident=float(cost)), args.confidence)
                    if row["earns_autonomy"]
                ]
                for cost in INCIDENT_SWEEP
            },
        }
        sweep = report["models"][model]["incident_sweep"]
        report["models"][model]["worst_case_regret"] = {
            policy: round(max(row[policy] - min(row.values()) for row in sweep.values()), 2)
            for policy in tb.POLICIES
        }

    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "taubench.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ARTIFACTS / "taubench.md").write_text(render(report), encoding="utf-8")
    print(f"Wrote {ARTIFACTS / 'taubench.md'}")


def render(report: dict) -> str:
    s = report["settings"]
    lines = [
        "# Solo License on τ-bench (retail)",
        "",
        f"_Generated {report['generated']} · τ-bench commit `{report['source']['commit'][:10]}` · "
        f"{s['arrival_orders']} random arrival orders · confidence {s['confidence']} · "
        f"audit rate {s['audit_rate']:.0%}_",
        "",
        "Every database write from τ-bench's recorded GPT-4o and Claude 3.5 Sonnet runs, "
        "replayed through five autonomy policies. A write is *wrong* when the benchmark's "
        "expected database says it should not have happened. Costs: "
        f"${s['costs']['review']:.2f} per human review, ${s['costs']['autonomous']:.3f} per unattended write, "
        f"${s['costs']['incident']:.0f} per wrong change reaching a customer (cfo/model.py).",
        "",
        "Reproduce: `python -m scripts.taubench_eval`",
        "",
    ]
    for model, m in report["models"].items():
        passes = " · ".join(f"pass^{k} {v:.0%}" for k, v in m["pass_hat_k"].items())
        lines += [
            f"## {model}",
            "",
            f"{m['tasks']} tasks × {m['episodes'] // m['tasks']} trials · {passes} · "
            f"**{m['wrong_writes']} of {m['writes']} database writes were wrong "
            f"({m['wrong_writes'] / m['writes']:.0%})**",
            "",
            "| Policy | Wrong writes reaching customers | Writes automated | Human reviews | Total cost |",
            "|---|---|---|---|---|",
        ]
        for policy, v in m["policies"].items():
            name = f"**{LABELS[policy]}**" if policy == "solo_license" else LABELS[policy]
            lines.append(
                f"| {name} | {v['harmful']:.1f} ± {v['harmful_sd']:.1f} | {v['automation_rate']:.0%} | "
                f"{v['reviews'] + v['audits']:.0f} | ${v['cost']:,.0f} |"
            )
        lines += [
            "",
            "Measured reliability per job type (what each licence is learned from):",
            "",
            "| Job type | Writes | Wrong | Error rate | 90% upper bound | Break-even | Earns autonomy at these costs |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in m["job_types"]:
            lines.append(
                f"| `{row['job_type']}` | {row['writes']} | {row['wrong']} | {row['error_rate']:.0%} | "
                f"{row['upper_bound']:.0%} | {row['break_even']:.1%} | {'yes' if row['earns_autonomy'] else 'no'} |"
            )
        lines += [
            "",
            "Total cost by incident cost (lower is better):",
            "",
            "| Incident cost | " + " | ".join(LABELS[p] for p in tb.POLICIES) + " |",
            "|---" * (len(tb.POLICIES) + 1) + "|",
        ]
        for cost, row in m["incident_sweep"].items():
            best = min(row.values())
            cells = [f"**${row[p]:,.0f}**" if row[p] == best else f"${row[p]:,.0f}" for p in tb.POLICIES]
            lines.append(f"| ${int(cost):,} | " + " | ".join(cells) + " |")
        regret = m["worst_case_regret"]
        lines.append("| **Worst-case regret** | " + " | ".join(
            f"**${regret[p]:,.0f}**" if regret[p] == min(regret.values()) else f"${regret[p]:,.0f}"
            for p in tb.POLICIES) + " |")
        lines += [
            "",
            "_Worst-case regret: the most a policy ever costs above the best policy for that incident cost._",
            "",
            "Job types Solo License licenses to act alone, by incident cost:",
            "",
            "| Incident cost | Licensed job types |",
            "|---|---|",
        ]
        for cost, types in m["licensed_job_types"].items():
            lines.append(f"| ${int(cost):,} | {', '.join(f'`{t}`' for t in types) or '— (every write reviewed)'} |")
        lines.append("")
    lines += [
        "## Method and limits",
        "",
        "- Labels come from τ-bench itself: a write is correct when its episode reached the expected "
        "database (reward 1) or when it matches a write in the task's reference solution.",
        "- Writes the tool rejected (`Error: …`) changed nothing and are excluded.",
        "- The replay is counterfactual per write: holding a write does not rewrite the rest of the recorded "
        "conversation. Reviewers and auditors are assumed to judge a write correctly.",
        "- Policy guards are deterministic checks of the τ-bench retail policy: the customer was identified and "
        "owns the order, the last customer turn confirmed the action, every id was shown by a tool first, and "
        "one-shot actions are not repeated.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
