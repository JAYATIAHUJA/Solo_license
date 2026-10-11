# Before / after: trusting the tool, catching, and recovering

_Generated 2026-10-11T08:15:48.528595+00:00 · 50 runs · seed 42 · fault rate 20% · deterministic planner_

The same seeded batch through the real worker, three ways.

| Metric | Trust the tool | Solo License v1 (catch and stop) | **Solo License v2 (catch, recover, verify)** |
|---|---|---|---|
| Runs that executed | 50 | 50 | 50 |
| False successes reaching the customer | **14** | 0 | **0** |
| Faults caught by a detection | 0 | 14 | 14 |
| Customers left waiting for a person after a caught fault | — | **4** | **0** |
| Recovered automatically and verified | 0 | 0 | 4 |
| Job type paused for review | never | 14 | 14 |
| Mean / p95 latency per run | — | 86.4 / 287.9 ms | 81.1 / 286.2 ms |

14 faults were injected (quiet failures + policy violations), all labelled in the run records. A quiet failure is a tool that answers "Processed" while nothing moved. v2 still pauses the job type — the tool lied — but the customer gets their money. Policy violations (executing beyond the licence) are never retried; they are caught and left for a person.

After each pause the script restored the class to L2 as the human reviewer would, so the batch could continue.

## Paired traces (same run, before and after the change)

| Run | Fault | v1 trace | v2 trace |
|---|---|---|---|
| 6 | quiet_failure | `3a1e5ebbbeaf865d4cf7e7ea0b179488` — customer waiting | `758a8b1af98d67d8b65049e5ad867187` — recovered, verified |
| 10 | policy_violation | `6170f78557299bbbaa6b657b0d4e5944` — demoted | `5223de8c432957791544588234cbaff2` — demoted |
| 11 | policy_violation | `34569bc5aa91a071a53eb6f467630355` — demoted | `d957c05c4d34a1587e038ce1b9082548` — demoted |
| 14 | policy_violation | `747a6de209c276191851adba379dabac` — demoted | `17a61c705cef0ba2cfa5f5f1a337c488` — demoted |
| 19 | quiet_failure | `905dca1425b293e1bf82d8393cc5d290` — customer waiting | `dc58a5ad5f53dae1b336f358ab419ad4` — recovered, verified |
| 23 | policy_violation | `9fd67e2110562c805bffd51021e2262e` — demoted | `fd9c1aff1d052002ae0f2c704e1fdeb8` — demoted |
| 26 | quiet_failure | `cccec9d1c85f5246adb3489558a85b71` — customer waiting | `501d02409621fe5f41d6e6aa5a1ce46d` — recovered, verified |
| 31 | policy_violation | `a756309b0f6fcc07e96fc745d4c7a93b` — demoted | `3e67a2b8679f17b53e7e76686b69d78d` — demoted |
| 32 | policy_violation | `55eff029499a21063a96a2d0da33c1f5` — demoted | `1d59d0192b0c3a389ac6d826da57bf6b` — demoted |
| 35 | policy_violation | `067d058df5c0613b1b5db514837c4cb5` — demoted | `336f11f011738dfbd0daf407de9cbfe6` — demoted |
| 38 | policy_violation | `496d824c396cb43fb32fcf8ebedb2914` — demoted | `9524211f9fd40285a21c425423d9c85b` — demoted |
| 39 | quiet_failure | `b3292003f8edda08d917c37ece0dd2bb` — customer waiting | `95412ae05692c1e0ee5624b445a3ed67` — recovered, verified |
| 40 | policy_violation | `2c4168a09fd3d11734e1b88a5b9e2e7d` — demoted | `ac8bc5418fa08433fa88dfe9202544d0` — demoted |
| 48 | policy_violation | `52203b7eaed63da69d0952bb0521fb1e` — demoted | `b1e755691962b52577ed5ce9b7e6feae` — demoted |

neatlogs export: on — every trace above is in the neatlogs project.

Reproduce: `python -m scripts.benchmark --runs 50 --seed 42 --fault-rate 0.2`
