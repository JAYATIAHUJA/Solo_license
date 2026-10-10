# Artifacts

Judge-verifiable evidence produced by the real system.

| File | How to regenerate | What it shows |
|---|---|---|
| `benchmark.md` / `benchmark.json` | `python -m scripts.benchmark` | 50 seeded runs with injected faults, scored as "trust the tool" vs. Solo License |
| `evidence_report.md` / `.json` (git-ignored) | `python -m scripts.generate_evidence [--fault policy_violation]` | One clean run and one faulted run side by side, with trace ids and the dial change |

After a new benchmark, redraw the README charts with `python -m scripts.readme_charts`.
