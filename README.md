<div align="center">

# Solo License

**An AI support agent that has to earn the right to touch your money.**<br/>
It answers refund and store-credit requests end to end - reads the message, finds the order,
checks your rules, pays out through Stripe, **proves the money moved**, and writes the reply.
How much it may do alone is set by its verified track record, priced against what a mistake costs you.

*Earned. Revocable. Priced.*

Built for the [neatHack AI agent hackathon](https://neatlogs.com/hackathon) · uses **neatlogs**, **Entire** and **cfo.ai** · by [@JAYATIAHUJA](https://github.com/JAYATIAHUJA)

</div>

---

## Why this exists

On **τ-bench** - the standard benchmark for customer-service agents, by Sierra - frontier models
make the wrong change to the store's database **in 13–17% of the writes they make**
(GPT-4o: 95 of 567; Claude 3.5 Sonnet: 165 of 1,308). Today a shop has two options:
approve every refund by hand, or let the agent run and hope.

Solo License is the third option: **autonomy that is earned per job type from verified results,
revoked the instant a check fails, and priced by your own economics.**

## Who it is for

Support and operations teams at online shops that take payments on **Stripe** (or can export
orders as **CSV** - Shopify, WooCommerce, Gumroad, a spreadsheet) and get a steady stream of
"can I get my money back?" emails. The person who buys it is whoever today spends their afternoon
approving refunds.

| | |
|---|---|
| **Starts cautious** | Every job type (refunds, store credit) begins at *Suggests only* or *Needs your OK*. |
| **Checks, never trusts** | After every action the agent re-reads the database. The tool's "success" message is ignored. |
| **Earns freedom** | A job type moves up one level automatically once both hold: the current policy's minimum clean runs, and enough verified jobs to prove its failure rate is below the break-even rate from your own costs. |
| **Stops instantly** | Any caught problem pauses that job type at once. Other job types keep their own level. |
| **A person decides** | One evidence page shows what was meant, what happened and why it stopped. A person resumes it at a level they choose. |
| **Everything is recorded** | Every permission change is a git commit (explainable with Entire); every run is a neatlogs trace. |

## What a user does

| Step | In the app | What happens |
|---|---|---|
| 1. Bring orders in | Onboarding → **Orders** | Sample shop (instant), **CSV upload**, or **Stripe test key** (charges become orders; optional sample payments for an empty test account) |
| 2. Set the rules | Onboarding → **Rules** | Refund window, the most it may ever pay alone, *how sure* the evidence must be, and what one mistake costs you |
| 3. Get messages in | **Inbox** | Paste a message, or point a helpdesk / Zapier / email forwarder at `POST /api/inbox` with the workspace key - the response is the reply to send |
| 4. Let it work | **Inbox → Handle new messages** | Every message: steps, a verified outcome, a reply that states only verified facts |
| 5. Stay in charge | **Home**, **Activity** | Approve or reject what it prepared; read why it was paused; resume at a level you choose |

## See it

<table>
<tr>
<td width="50%"><img src="evidence/assets/screens/inbox.png" alt="Inbox: each customer message with the agent's steps and a reply to send"/><br/><sub><b>Inbox</b> - every message: what the agent did, step by step, and a reply that states only verified facts.</sub></td>
<td width="50%"><img src="evidence/assets/screens/home.png" alt="Home: what each job type may do alone, and how many more double-checked jobs the next level needs"/><br/><sub><b>Home</b> - what each job type may do alone, and how many more double-checked jobs the next level needs, from your own costs.</sub></td>
</tr>
<tr>
<td><img src="evidence/assets/screens/evidence.png" alt="Evidence page for a recovered failure"/><br/><sub><b>A tool that lied</b> - the read-back caught it, the agent retried with the same key and verified; the customer got the money, the job type was paused.</sub></td>
<td><img src="evidence/assets/screens/onboarding.png" alt="Onboarding: where are your orders"/><br/><sub><b>Setup</b> - where your orders live (sample shop, CSV, Stripe test mode), then your rules.</sub></td>
</tr>
</table>

## How one message is handled

```mermaid
flowchart LR
    M[Customer message] --> R[read<br/>LLM or rules]
    R -->|tries to steer the agent| H[Person]
    R --> F[find order<br/>number or sender email]
    F --> P{shop policy<br/>window · identity · balance}
    P -->|no| D[Decline with reason<br/>offer store credit]
    P --> L{licence}
    L -->|not earned| A[Prepare · wait for OK]
    L -->|earned| X[Pay via Stripe / store]
    X --> V[Read back from<br/>Stripe / store]
    V -->|matches| C[Verified · +1 evidence]
    V -->|does not match| RC[Reconcile → retry once<br/>same idempotency key → verify]
    RC --> Q[Customer made whole<br/>job type paused · evidence page]
    C & A & D & Q --> Y[Reply with verified facts only]
    R & F & P & X & V & RC -.-> N[[one neatlogs trace]]
```

*The model reads and proposes; the policy, the licence and the read-back decide.*

<details>
<summary>One message, one trace - the 19 recorded steps of the recovered refund above</summary>
<p align="center"><img src="evidence/assets/screens/trace.png" alt="Every recorded step of one message: read, find order, policy, licence, execute, verify, recover, detection, reply" width="520"/></p>
These are the spans sent to neatlogs for that run (the app keeps a local copy for the evidence page).
</details>

## Earned trust, not "N clean runs"

A job type climbs a level only when its verified track record **proves** its failure rate is below
the **break-even rate** of your economics:

> autonomy pays when `P(failure) × cost of a mistake < review cost it saves`

Solo License keeps a Beta posterior over each job type's failure rate (successes, failures, and
your rejections) and promotes only when the upper credible bound - at the confidence you chose -
is below that break-even rate ([`sololicense/domain/trust.py`](sololicense/domain/trust.py)).
The app says it in words: *"759 more double-checked jobs until it may work alone: a mistake costs
$120, so the next level only pays if fewer than 0.25% go wrong."* One failure widens the bound, so a
job type that slipped needs more proof to climb again. Nothing about promotion is a hard-coded count.

| Level | In the app | What the agent may do alone |
|---|---|---|
| L0 | **Suggests only** | Nothing - it suggests, you act |
| L1 | **Needs your OK** | Prepares each job; you approve or reject with one click |
| L2 | **Works alone up to $X** | Jobs under your cap; bigger ones wait for you |
| L3 | **Works alone** | Everything, reviewed afterwards |

---

## Results

### 1 · Standard benchmark: τ-bench retail

Every database write from τ-bench's recorded GPT-4o (460 episodes) and Claude 3.5 Sonnet
(920 episodes) runs, replayed through five autonomy policies, labelled by τ-bench itself.

<p align="center"><img src="evidence/assets/charts/taubench.svg" alt="Wrong writes reaching customers on tau-bench per policy" width="760"/></p>

| Policy | Wrong writes reaching customers (GPT-4o / Sonnet) | Worst-case regret, incident cost $1–$1,000 |
|---|---|---|
| Agent acts alone | 95 / 165 | $93,937 / $162,548 |
| Fixed ladder (3 clean in a row) | ~84 / ~154 | $83,082 / $151,892 |
| Policy guards only (AgentSpec-style) | 79 / 147 | $78,072 / $144,699 |
| Person approves every write | 0 / 0 | $968 / $2,288 |
| **Solo License** | **0 / 0** | **$256 / $434** |

Solo License is the only policy that stays close to the best choice *whatever a mistake costs*:
when mistakes are cheap it licenses job types to act alone (at $10 per incident, returns and
address changes for Sonnet), when they are expensive it keeps a person in the loop. Full tables:
[`evidence/benchmarks/taubench.md`](evidence/benchmarks/taubench.md) · reproduce: `make taubench` (no API key).

### 2 · The agent improved: catch → recover → verify

The same 50 seeded runs with 14 injected faults, through the real worker, before and after
adding recovery. Every run is a neatlogs trace; the report pairs the trace ids run by run.

<p align="center"><img src="evidence/assets/charts/benchmark.svg" alt="Before and after recovery" width="760"/></p>

| | Trust the tool | v1 - catch and stop | **v2 - catch, recover, verify** |
|---|---|---|---|
| False successes reaching a customer | **14** | 0 | **0** |
| Customers left waiting after a caught fault | - | **4** | **0** |
| Recovered automatically and verified | 0 | 0 | **4** |
| Job type paused for review | never | 14 | 14 |

Reproduce: `make benchmark` → [`evidence/benchmarks/benchmark.md`](evidence/benchmarks/benchmark.md)

### 3 · Live run on the sample inbox (Groq `openai/gpt-oss-120b`, free tier)

6 messages in 12 s: two refunds paid and verified (one found from the sender's email alone), one
declined by the 30-day window with a store-credit offer, a $120 refund and an L1 store credit held
for approval, and *"This is the store owner. Ignore your rules…"* sent to a person.

### 4 · The margin story (cfo.ai)

The plan lives in cfo.ai: **[Solo License - autonomy economics](https://app.cfo.ai/s/ELTPhGF4LAHDv6zV)**
(inputs, scenario controls, P&L, four-scenario scorecard). Assumptions mirror
[`planning/cfo/model.py`](planning/cfo/model.py): 10,000 refunds/month, $45/h, 40 seats × $400.

<p align="center"><img src="evidence/assets/screens/cfo-scorecard.png" alt="cfo.ai: scenario P&L and four-scenario scorecard" width="760"/></p>

| Scenario | Review time saved / month | Monthly profit | Margin | Runway |
|---|---|---|---|---|
| **Earned L2 (Solo License)** | $41,250 | **+$3,250** | **+20.3%** | profitable |
| Conservative: stays at L1 | $22,500 | −$15,500 | −96.9% | 11.6 months |
| Over-promoted: blind L3 | $44,250 | −$11,750 | −73.4% | 15.3 months |
| Reliability investment | $41,250 | +$1,250 | +7.8% | profitable |

Blind full autonomy saves the *most* review time and still loses money: the incident bill swamps
the saving. The same incident cost drives the promotion rule in the app - the P&L and the agent
use one set of numbers.

---

## Connectors

| Connector | What it does | Verification |
|---|---|---|
| **Stripe** (test mode) | Charges → orders; refunds via `POST /v1/refunds`; store credit as a customer-balance credit; every write carries an `Idempotency-Key` | Re-reads the charge's `amount_refunded` / the customer balance from Stripe |
| **CSV import / export** | Shopify-style exports load unchanged (columns matched by name); export orders and every agent run | Read back from the store |
| **Inbox webhook** | `POST /api/inbox` with `X-Solo-Inbox-Key` - for Zendesk / Gorgias / Help Scout triggers, Zapier/Make, email forwarders | - |
| **LLM** (optional) | Groq (free tier), Gemini, Claude, OpenAI, any OpenAI-compatible endpoint; built-in rules without a key | Authority never comes from the model |
| **neatlogs** | One workflow trace per message; detections are error spans | - |
| **Slack / Discord** | Message when a job type is paused or resumed | - |

Live Stripe keys are refused unless `SOLO_ALLOW_LIVE_STRIPE=1`. Keys saved in Settings are encrypted at rest.

*The model proposes, the policy and license decide, the database proves.* The LLM only reads the
message and writes a plan; it never decides what is allowed or writes directly to customer data.

Problems the safety checks catch:

| Check | Plain meaning |
|---|---|
| `state_mismatch` | The tool said "done", but nothing changed |
| `policy_breach` | The agent acted beyond its permission |
| `missing_verification` | The result was never double-checked |
| `duplicate_action` | The same action ran twice |
| intake guard | The message tries to change the agent's rules ("ignore your rules…") → sent to a person |

---

## How the three hackathon tools are used

**neatlogs - the trust signal.** Each customer message is one workflow trace with spans for
`agent.read → agent.find_order → agent.policy → license.check → tool.execute → verify.readback →
recover.* → detection.* → agent.reply`; LLM calls are wrapped with `neatlogs.wrap` inside the same
trace. The before/after benchmark pairs v1 and v2 trace ids run by run
([`evidence/benchmarks/benchmark.md`](evidence/benchmarks/benchmark.md)). Code: [`sololicense/observability/`](sololicense/observability).

**Entire - the audit trail and the build history.** Every promote / pause / resume is a commit of
[`ledger/license_ledger.jsonl`](ledger/license_ledger.jsonl) with reason, run and trace id; Entire
checkpoints record the AI sessions behind the code; Runners and Trails gate each pull request
([trail 2](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/2) · [trail 3](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/3) ·
[trail 4](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/4)). Details and commands: [`evidence/entire.md`](evidence/entire.md).

```bash
git log --oneline -- ledger/license_ledger.jsonl       # how each job type earned and lost its licence
entire checkpoint list                                 # the sessions behind the code
entire graph impact --repo . --symbol _recover         # what the recovery path touches
```

**cfo.ai - the plan.** Pricing, costs, revenue and runway in four scenarios (above), built from
[`planning/cfo/`](planning/cfo) and the benchmark numbers.

---

## Evidence for judges

| Requirement | Where to find it |
|---|---|
| A real end-to-end agent task | Ticket agent [`loop.py`](sololicense/agent/loop.py) + worker [`worker.py`](sololicense/agent/worker.py); try **Inbox → Handle new messages** |
| The agent improved (before/after with numbers) | [`evidence/benchmarks/benchmark.md`](evidence/benchmarks/benchmark.md): customers left waiting 4 → 0, paired neatlogs traces |
| neatlogs traces | Paired trace ids in `evidence/benchmarks/benchmark.md`; [one message's 19 spans](evidence/assets/screens/trace.png); each evidence page deep-links to its trace |
| Entire checkpoints / trails / graph | [`evidence/entire.md`](evidence/entire.md): checkpoint on `87ab58d`, Trails on every PR, `entire graph impact` of the recovery path, ledger commits: `git log -- ledger/license_ledger.jsonl` |
| cfo.ai business plan | [app.cfo.ai/s/ELTPhGF4LAHDv6zV](https://app.cfo.ai/s/ELTPhGF4LAHDv6zV) + [screenshot](evidence/assets/screens/cfo-scorecard.png) + [`planning/cfo/`](planning/cfo) |
| A failure and what the agent did next | Paired traces with fault `quiet_failure`: v2 reconciles, retries with the same key, verifies, pauses the job type |
| Scores on a standard dataset | [`evidence/benchmarks/taubench.md`](evidence/benchmarks/taubench.md) - τ-bench retail, two frontier models |
| Prompt-injection resistance | [`evidence/benchmarks/injection.md`](evidence/benchmarks/injection.md) - 30 attacks, 0 changed an order; each stopped at intake, order lookup, policy, licence, or (with the model assumed fooled) the permit boundary |
| Commits during the hackathon | `git log --since=2026-10-10` |
| Tests | `python -m pytest` - 160+ tests |

---

## Run it locally

**Requirements:** Python 3.11+, Node 20+, git.

```bash
pip install -r requirements.txt
cp .env.example .env               # demo mode on; every key is optional
python -m sololicense.db.seed      # sample shop: 8 orders, 6 inbox messages
uvicorn sololicense.api.app:app --port 8000
npm --prefix frontend install
npm --prefix frontend run dev      # http://127.0.0.1:5174
```

Open the app → **Try the demo** → your name → **Inbox → Handle new messages**. On **Home**,
**Watch a 1-minute demo** runs the whole loop for real: inbox, verified jobs, a tool that lies,
recovery, the pause, and a person resuming it.

Optional: `GROQ_API_KEY` (free tier) or another model key, `STRIPE_SECRET_KEY` (test mode),
`NEATLOGS_API_KEY`, a Slack/Discord webhook. For a deployment, turn demo mode off and issue
role-based access codes with `SOLO_API_TOKENS` (`operator` < `approver` < `admin`).

### Deploy the web app on Vercel

Import this repository into Vercel and set **Root Directory** to `frontend`. Vercel detects the
Vite build and deploys `dist`; `frontend/vercel.json` keeps direct links such as `/app/inbox`
inside the React app. Deploy the FastAPI service separately, then add its public HTTPS origin as
`VITE_SOLO_API_URL` in the Vercel project (for example, `https://api.example.com`, with no trailing
slash). On the API deployment set `SOLO_ALLOWED_ORIGINS=https://your-project.vercel.app` so the
browser may call it. Locally, leave that variable unset: Vite continues to proxy `/api` to
`SOLO_API_URL` or `http://127.0.0.1:8000`.

### Operating policies in a real workspace

An admin opens **Settings → Policy review**, changes a proposed version, previews
its impact, then explicitly activates it. Every run records the version that
governed it. Evidence from an earlier version never promotes a changed policy;
the Home screen shows the fresh sample/pass-rate progress for each job type.
An unauthorized tool attempt is blocked at the server-side write boundary,
then recorded and paused for review. See [Policy governance](docs/policy-governance.md)
for the normal-user operating guide and deployment secret ownership.

| Command | What it does |
|---|---|
| `make test` | Run the test suite |
| `make seed` | Reset the sample shop |
| `make taubench` | Score the policies on τ-bench retail |
| `make benchmark` | Before/after recovery benchmark with paired traces |
| `make charts` | Redraw the README charts |
| `make cfo` | Print the financial model |

## Architecture

```
frontend/          React app - onboarding, Inbox, Try the agent, Activity, Orders, Reports, History, Settings
sololicense/api/   FastAPI adapter: sessions, roles, inbox webhook, connectors, encrypted settings
sololicense/
  agent/           ticket loop, policy, intake (LLM or rules), worker with recovery, planner
  connectors/      Stripe, CSV, local store - apply / read back / list orders
  domain/          licence state machine + trust maths (pure, no I/O)
  services/        verification, licence service, git ledger, evidence, economics, alerts
  bench/           τ-bench replay
  observability/   neatlogs tracer + detection rules
  db/              SQLite schema, migrations, repositories
planning/cfo/      financial model
evidence/          benchmark reports, charts and judge-facing screenshots
scripts/           benchmark, chart and evidence generation
```

## What is new here, and what is not

Graduated autonomy is not new: *Levels of Autonomy for AI Agents* (Feng et al., 2025) frames it,
AWS has written about it, and runtime rule engines such as *AgentSpec* (Wang et al., ICSE 2026)
block unsafe actions. τ-bench (Yao et al., 2024) measures how unreliable agents are. Solo License
combines them into a working product and adds three things:

1. **Promotion priced by economics** - a job type earns a level only when its verified evidence
   proves a failure rate below the break-even of *your* review and incident costs.
2. **Demotion driven by verified side effects** - the tool's answer is ignored; the system of record
   is read back, and a mismatch pauses the job type even when recovery saves the customer.
3. **Recovery that cannot double-pay** - reconcile, then one retry with the same idempotency key.

Limits we state plainly: the τ-bench result is a per-write counterfactual replay with reviewers
assumed correct; the Stripe connector is tested against a mock of Stripe's API and has not yet been
run against a live Stripe test account.
