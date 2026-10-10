# Before / after: trusting the tool vs. verifying the side effect

_Generated 2026-10-10T22:26:40.422352+00:00 · 50 runs · seed 42 · fault rate 20% · deterministic planner_

| Metric | Before — trust the tool | After — Solo License |
|---|---|---|
| Runs that executed | 50 | 50 |
| Reported as success | 50 | 40 |
| False successes reaching the customer | **10** | **0** |
| Verified success rate | 80.0% | 100.0% |
| Faults caught by a detection | 0 | 10 |
| Autonomy demotions | 0 (keeps acting) | 10 |
| Mean / p95 latency per run | — | 83.4 ms / 279.0 ms |

14 faults were injected (quiet failures + policy violations), all labelled in the run records; 10 of them would have produced a false success (a policy-violation fault on a class already at L3 is within its license, so it is harmless). After each demotion the script restored the class to L2 as the human reviewer would, so the batch could continue.

Sample traces of caught faults: `4f4aafe188fd90e4f1b5fadb5e45c9d6`, `cca22fb0c2be074a4c0a667a4af4ee02`, `baf2973d0d28156045feb7fb4737b0e1`, `aeae16471a599753800a23ebc11c1414`, `685c936401425f2026f41f55a3795650`

neatlogs export: on — these traces are in your neatlogs project.

Reproduce: `python -m scripts.benchmark --runs 50 --seed 42 --fault-rate 0.2`
