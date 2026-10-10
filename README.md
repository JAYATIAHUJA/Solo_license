# 🎚️ Solo License

**An operations agent that earns the right to act unattended — task class by
task class — from a measured reliability track record, and loses it the instant
a detection fires.**

Built for the [neatHack AI agent hackathon](https://neatlogs.com/hackathon).

A visible **autonomy dial** (per task class) rises after consecutive clean runs
proven by traces, and crashes immediately when a detection fires. A human
reviews **one evidence packet** (trace + checkpoint context) to restore
permissions. Recovery is a judgement, not a blind retry. The system **verifies
actual side effects in SQLite** and never trusts a tool's response.

```
refund request ─▶ license check ─▶ execute or suggest ─▶ verify side effect in SQLite ─▶ update dial
                                                                │
                                              detection fires ──┘─▶ auto-demote to L0 ─▶ evidence packet ─▶ human restore
```

---

## The autonomy ladder

| Level | Meaning | Who acts |
|---|---|---|
| **L0** | Suggest only | Human does everything |
| **L1** | Draft + human approve | Agent drafts, human clicks |
| **L2** | Auto under a dollar ceiling | Agent acts, human spot-checks |
| **L3** | Full auto, post-hoc audit | Agent acts, audit samples |

- **Promote:** after *N* consecutive verified-clean runs (default 3) the dial
  climbs one rung — automatically, because the track record earned it.
- **Demote:** the instant a detection fires, the class crashes to **L0** and is
  **quarantined** (it can only suggest, and earns no credit) until a human acts.
- **Restore:** a human reads the evidence packet and lifts the quarantine to a
  chosen level. Every promote / demote / restore is a **git commit**.

## Three custom detections (these drive demotion)

| Rule | Fires when | Demo fault |
|---|---|---|
| `state_mismatch` | the verified change in SQLite ≠ what the agent intended | quiet failure |
| `policy_breach` | the agent executed beyond what the license authorised | policy violation |
| `missing_verification` | an execution completed without reading SQLite back | guardrail |

---

## Setup

**Requirements:** Python 3.11+ and git. No external services are required for
the core demo (an LLM key and a neatlogs key are optional — see below).

```bash
pip install -r requirements.txt     # 1. dependencies
cp .env.example .env                # 2. optional config (runs fine empty)
python -m sololicense.db.seed       # 3. seed the demo database
streamlit run app/streamlit_app.py  # 4. launch the live UI
```

With `make`: `make install && make run`. On Windows PowerShell, use the four
raw commands above (`copy .env.example .env` for step 2).

### Optional keys (the demo is fully functional without them)

- **neatlogs** — set `NEATLOGS_API_KEY` to ship real traces + detections. Left
  empty, spans are mirrored into SQLite and the evidence packet still works.
- **LLM** — set `LLM_PROVIDER=anthropic` (or `openai`) with the matching key to
  have the model author each plan's rationale. Left as `deterministic`, a
  rule-based planner is used. **Authority always comes from the license, never
  the model**, so safety is identical either way.

---

## Run the demo (what to click)

Everything is on one screen; the sidebar holds the controls.

1. **Trigger a refund** on an under-ceiling order (e.g. `ORD-1001`, $25). It
   auto-executes, verifies in SQLite, and the dial earns a clean run. Do it a
   few times to **watch the dial climb L2 → L3**.
2. **Inject a fault** → *Quiet failure* → **Arm fault**, then run a refund. The
   tool reports success but SQLite never moved → `state_mismatch` fires → the
   **dial crashes to L0 + quarantine**.
3. **Open the evidence packet** (right panel) — before/after numbers, the
   detection, the trace spans, and the git-backed license history.
4. **Restore the license** → pick `L2` → **Restore license**. Quarantine lifts;
   a git commit records the restore.

To show `policy_breach` instead: arm *Policy violation* and run an
**above-ceiling** order (`ORD-1004`, $120). The agent attempts an auto-execute
the license does not authorise → demotion.

## Generate the before/after evidence artifact

```bash
python -m scripts.generate_evidence                      # quiet-failure
python -m scripts.generate_evidence --fault policy_violation
```

Writes `artifacts/evidence_report.md` (+ `.json`): two comparable runs with
trace ids, the verified `refunded_amount` before/after, the detections that
fired, and the dial transition. Ready to drop into a **#neatHack** post.

## Inspect the git-backed license ledger (for Entire)

Every autonomy change is one scoped commit of `ledger/license_ledger.jsonl`:

```bash
git log --oneline -- ledger/license_ledger.jsonl
# license(refund): promote L2 -> L3 ...
# license(refund): demote L3 -> L0 ...
# license(refund): restore L0 -> L2 ...
```

Point **Entire**'s graph / explain at these commits to walk how the task class
earned and lost its license. See [`ledger/README.md`](ledger/README.md).

## See the cfo.ai model

```bash
python -m cfo.model        # structured numbers, grounded in real runs when present
```

Narrative plan: [`cfo/business_model.md`](cfo/business_model.md).

---

## 3-minute demo script

> Covers **architecture, implementation, runtime, reasoning, result** for each
> of the three tools. Timings are a guide.

**[0:00–0:20] The idea.** "Solo License is an ops agent that starts at
near-zero autonomy and *earns* the right to act unattended, per task class, from
its measured track record — and loses it the instant something goes wrong."

**[0:20–1:10] neatlogs — the trust signal.**
- *Architecture:* every refund run opens a trace; steps (plan → execute →
  verify) are spans; three custom rules emit detections.
- *Implementation:* `sololicense/observability/` — tracer + `detect_state_mismatch`,
  `detect_policy_breach`, `detect_missing_verification`.
- *Runtime:* trigger two refunds under the ceiling; the dial climbs L2 → L3 on
  clean traces. Then arm *Quiet failure* and run one.
- *Reasoning:* the tool returned success, but the verifier read SQLite back and
  the delta was $0 — `state_mismatch` fires.
- *Result:* the dial crashes to L0. Show the before/after numbers in the
  evidence packet (and the neatlogs trace link if a key is set).

**[1:10–2:00] Entire — the audit trail.**
- *Architecture:* every license change is a scoped git commit of the ledger file.
- *Implementation:* `sololicense/services/git_ledger.py` + `license_service.py`.
- *Runtime:* `git log --oneline -- ledger/license_ledger.jsonl` — promote,
  demote, restore, each with the reason, run id, and trace id.
- *Reasoning:* this is the checkpoint history Entire graphs/explains — the agent
  can reconstruct exactly when and why its own permissions changed.
- *Result:* a human opens the one evidence packet and restores to L2 — another
  commit. Recovery with judgement, not blind retry.

**[2:00–2:45] cfo.ai — the margin story.**
- *Architecture / implementation:* `cfo/model.py` turns stated assumptions into
  a supervision-cost curve, an over-promotion risk model, and a P&L.
- *Runtime:* `python -m cfo.model`.
- *Reasoning:* climbing L0 → L2 saves **$41,250/month** in supervision; but
  running a rung you haven't earned adds **~$18,000/month** in incidents.
- *Result:* earned-L2 runs at **+20.3% margin**; blind full-auto runs at
  **−73.4%** with a 15-month runway. The license level *is* the margin driver.

**[2:45–3:00] Close.** "Graduated autonomy isn't new. What's here is autonomy
driven by detections, restored from one evidence packet, and priced as a margin
lever — an agent you'd actually trust to run without you watching."

---

## Scoring evidence checklist

- [x] **Real end-to-end task** — refund worker: plan → license check → execute →
  verify in SQLite → recover. (`sololicense/agent/worker.py`)
- [x] **Two traces with compared numbers** — `scripts/generate_evidence.py`.
- [x] **neatlogs detections surfaced as incidents** — `observability/detections.py`,
  shown in the UI and evidence packet.
- [x] **Clear failure-recovery run** — inject fault → demote → evidence → restore.
- [x] **Entire-compatible checkpoints** — git commits of every license change
  (`ledger/license_ledger.jsonl`).
- [x] **cfo.ai business model** — pricing, costs, revenue, runway
  (`cfo/business_model.md`, `cfo/model.py`).
- [x] **Side effects verified, never trusted** — `services/verification.py`.
- [x] **Seeded data** — `sololicense/db/seed.py` (runs immediately).
- [x] **Tests** — `pytest` (domain, detections, end-to-end worker).

## Honest differentiator

Graduated autonomy / earned-permission ladders already exist in public
literature (AWS "graduated autonomy," research papers, practitioner posts). This
project does not claim that framing as novel. What is specific and
judge-visible here is:

1. **Demotion driven by detections** — reliability signals, not a fixed policy,
   move the dial down.
2. **A single human-reviewable evidence packet** (trace + checkpoint context) to
   restore a license.
3. **The license level treated as a cfo.ai margin driver** — supervision cost vs
   autonomy, with the cost of over-promotion made explicit.

## Architecture

Dependencies point inward; `domain` has no third-party imports and is purely
unit-tested.

```
app/ · scripts/            UI and CLI (Streamlit, evidence generator)
   │
sololicense/agent/         worker loop + planner + refund tool
sololicense/services/      license service, verification, git ledger, evidence
   │
sololicense/observability/ neatlogs tracer + custom detections
   │
sololicense/domain/ · db/  pure license state machine · SQLite + repositories
cfo/                       financial model + plan
```

| Concern | Module |
|---|---|
| Autonomy state machine (pure) | `sololicense/domain/license.py` |
| Permission authority | `sololicense/domain/license.py::decide` |
| Side-effect truth | `sololicense/services/verification.py` |
| Detections | `sololicense/observability/detections.py` |
| Dial transitions + git | `sololicense/services/license_service.py` |
| Fault injection | `sololicense/faults/injector.py` |
| Composition root | `sololicense/bootstrap.py` |

## Tests

```bash
pytest        # 26 tests: state machine, detections, end-to-end worker
```
