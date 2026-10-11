"""Render the README charts as static SVGs from real project data.

* ``docs/assets/benchmark.svg`` — the before/after benchmark
  (``artifacts/benchmark.json``, produced by ``python -m scripts.benchmark``).
* ``docs/assets/supervision.svg`` — monthly supervision cost per autonomy
  level, from the stated assumptions in :mod:`cfo.model`.

Plain SVG with a white card background so it reads the same in GitHub's light
and dark themes. Re-run after a new benchmark:  python -m scripts.readme_charts
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from cfo import model as cfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
INK, MUTED, LINE, RED, GREEN, BG = "#0e0e0d", "#76746e", "#e6e3dc", "#d8341f", "#1f7a4d", "#ffffff"
FONT = "Inter, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"


def _svg(width: int, height: int, body: list[str], title: str) -> str:
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" font-family="{FONT}">',
        f'<rect width="{width}" height="{height}" rx="12" fill="{BG}" stroke="{LINE}"/>',
        *body,
        "</svg>",
    ])


def _text(x, y, s, size=14, fill=INK, weight=400, anchor="start") -> str:
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}">{escape(str(s))}</text>')


def benchmark_chart(report: dict) -> str:
    w, h = 760, 380
    b, a = report["before"], report["after"]
    rows = [
        ("False successes reaching a customer", b["false_success"], a["false_success_leaked"]),
        ("Faults caught by a safety check", 0, a["caught"]),
        ("Times the agent was paused", 0, a["license_events"].get("demote", 0)),
    ]
    top = max(1, max(max(r[1], r[2]) for r in rows))
    body = [
        _text(32, 44, "Trusting the tool vs. checking the result", 20, weight=600),
        _text(32, 68, f"{report['runs']} real runs · {report['faults_injected']} injected faults · seed {report['seed']}", 13, MUTED),
        f'<rect x="32" y="84" width="12" height="12" fill="{RED}"/>', _text(50, 95, "Trust the tool (before)", 13, MUTED),
        f'<rect x="230" y="84" width="12" height="12" fill="{INK}"/>', _text(248, 95, "Solo License (after)", 13, MUTED),
    ]
    x0, bar_max, y = 300, 400, 122
    for label, before, after in rows:
        body.append(_text(32, y + 20, label, 14))
        for i, (value, color) in enumerate(((before, RED), (after, INK))):
            yy = y + i * 26
            width = 0 if value == 0 else max(4, value / top * bar_max)
            body.append(f'<rect x="{x0}" y="{yy}" width="{bar_max}" height="20" fill="#f3f1ec"/>')
            if width:
                body.append(f'<rect x="{x0}" y="{yy}" width="{width:.1f}" height="20" fill="{color}"/>')
            body.append(_text(x0 + width + 8 if width < bar_max - 40 else x0 + width - 8, yy + 15, value,
                              13, INK if width < bar_max - 40 else BG, 600,
                              "start" if width < bar_max - 40 else "end"))
        y += 78
    body.append(_text(32, h - 22, f"Verified success rate: {b['verified_success_rate']:.0%} → {a['verified_success_rate']:.0%}", 14, GREEN, 600))
    return _svg(w, h, body, "Benchmark: trusting the tool versus Solo License")


def supervision_chart() -> str:
    w, h = 760, 330
    points = cfo.supervision_curve()
    names = {0: "Suggests only", 1: "Needs your OK", 2: "Works alone up to a limit", 3: "Works alone"}
    top = max(p.monthly_supervision_cost for p in points)
    body = [
        _text(32, 44, "Human review cost per month, by autonomy level", 20, weight=600),
        _text(32, 68, f"{cfo.REFUNDS_PER_MONTH:,} actions/month · ${cfo.LOADED_HUMAN_COST_PER_HOUR:.0f}/h loaded cost · stated assumptions (cfo/model.py)", 13, MUTED),
    ]
    x0, bar_max, y = 260, 290, 100
    for p in points:
        width = max(4, p.monthly_supervision_cost / top * bar_max)
        body.append(_text(32, y + 15, f"L{p.level} · {names[p.level]}", 14))
        body.append(f'<rect x="{x0}" y="{y}" width="{width:.1f}" height="22" fill="{INK if p.level < 2 else GREEN}"/>')
        body.append(_text(x0 + width + 10, y + 16, f"${p.monthly_supervision_cost:,.0f}  ({p.minutes_per_run:g} min each)", 13, MUTED))
        y += 44
    saved = cfo.autonomy_savings(0, 2)
    body.append(_text(32, h - 50, f"Earning L2 saves ${saved:,.0f}/month in review time.", 14, GREEN, 600))
    body.append(_text(32, h - 26, f"Running a level it has not earned adds ~${cfo.overpromotion_incident_cost():,.0f}/month in incidents.", 14, RED, 600))
    return _svg(w, h, body, "Supervision cost by autonomy level")


TAU_POLICIES = (
    ("full_auto", "Agent acts alone"),
    ("fixed_ladder", "Fixed ladder (3 clean)"),
    ("guards_only", "Policy guards only"),
    ("approve_all", "Person approves all"),
    ("solo_license", "Solo License"),
)


def taubench_chart(report: dict) -> str:
    """Wrong writes reaching customers on τ-bench, plus worst-case regret."""
    models = list(report["models"].items())
    w, h = 760, 150 + 150 * len(models)
    incident = report["settings"]["costs"]["incident"]
    body = [
        _text(32, 44, "τ-bench retail: wrong database writes that reach a customer", 20, weight=600),
        _text(32, 68, f"Recorded GPT-4o and Claude runs replayed through five policies · ${incident:.0f} per incident · "
                      f"{report['settings']['arrival_orders']} arrival orders", 13, MUTED),
    ]
    y = 96
    for model, m in models:
        top = max(v["harmful"] for v in m["policies"].values()) or 1
        body.append(_text(32, y + 14, f"{model} — {m['wrong_writes']} of {m['writes']} writes wrong", 14, INK, 600))
        y += 24
        for key, label in TAU_POLICIES:
            v = m["policies"][key]
            solo = key == "solo_license"
            color = GREEN if solo else (RED if v["harmful"] > 0 else INK)
            width = 0 if v["harmful"] == 0 else max(4, v["harmful"] / top * 250)
            body.append(_text(32, y + 13, label, 13, INK, 600 if solo else 400))
            body.append(f'<rect x="210" y="{y}" width="250" height="16" fill="#f3f1ec"/>')
            if width:
                body.append(f'<rect x="210" y="{y}" width="{width:.1f}" height="16" fill="{color}"/>')
            body.append(_text(210 + width + 8, y + 13, f"{v['harmful']:.0f}", 13, color, 600))
            body.append(_text(728, y + 13, f"{v['automation_rate']:.0%} automated · regret ${m['worst_case_regret'][key]:,.0f}",
                              12, MUTED, 400, "end"))
            y += 22
        y += 18
    body.append(_text(32, h - 20, "Regret = most a policy ever costs above the best one, across incident costs $1–$1,000.", 13, GREEN, 600))
    return _svg(w, h, body, "Solo License on tau-bench")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads((ROOT / "artifacts" / "benchmark.json").read_text(encoding="utf-8"))
    (OUT / "benchmark.svg").write_text(benchmark_chart(report), encoding="utf-8")
    (OUT / "supervision.svg").write_text(supervision_chart(), encoding="utf-8")
    tau = ROOT / "artifacts" / "taubench.json"
    if tau.exists():
        (OUT / "taubench.svg").write_text(
            taubench_chart(json.loads(tau.read_text(encoding="utf-8"))), encoding="utf-8"
        )
    print(f"Wrote charts to {OUT}")


if __name__ == "__main__":
    main()
