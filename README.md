<div align="center">

# Solo License

**Your coding agent has to earn the right to act without asking.**<br/>
Each kind of action - run the tests, install a package, push - is auto-approved only once it has
proven itself **in your repo**, from verified results. One failure, or one over-edited turn, takes it back.
Works in Claude Code, Codex, Cursor, Gemini CLI, Antigravity, Copilot CLI, Grok Build, Windsurf, Kiro, Cline and OpenCode.

*Earned. Revocable. Priced.*

```bash
uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license init --agent auto
```

Built for the [neatHack AI agent hackathon](https://neatlogs.com/hackathon) · uses **neatlogs**, **Entire** and **cfo.ai** · by [@JAYATIAHUJA](https://github.com/JAYATIAHUJA)

</div>

---

## The problem

Every coding agent offers two bad deals:

- **"Ask before changes"** - you approve `npm test` forty times a day, until you stop reading what you approve.
- **"Full access"** - nothing interrupts you, until a force-push, a reverted commit, or a one-line bug fix that comes back as a fifty-line diff you now have to review.

Claude Code's auto mode asks *"is this action dangerous?"*. Solo License asks a different question:
**has this agent earned this kind of action, in this repo, and did it actually work?** The two work side by side.

## What it does inside your agent

```text
> fix the off-by-one in discount.js
⏺ Bash(npm test)
  § Solo License  auto-approved · test-run is L1 in shop-api (approved 3×, verified 3×)
⏺ Edit(discount.js)   count > 10 → count >= 10
⏺ Edit(format.js)     "tidied while I was here" · +160 lines
⏺ Done! Fixed the off-by-one and cleaned up formatting.
  § Solo License  sent back · over-editing: 162 lines in 2 files for this request (scope 2/5). Revert format.js.
⏺ Bash(git checkout -- format.js)
  § Solo License  verified · 2 lines in 1 file · scope 5/5 · npm test passed
> ship it
⏺ Bash(git push --force origin main)
  § Solo License  blocked · force-pushes a protected branch. Never allowed, at any level.
```

It lives in the agent's **hooks**, which the agent runs and cannot skip (that is why this is not an MCP
server: a model may choose not to call a tool). To every permission request it gives one of three answers:

| Answer | When | What the agent sees |
|---|---|---|
| **allow** | this kind of action is earned in this repo | no prompt |
| **deny** | forbidden (`rm -rf ~`, `curl … \| sh`, force-push to main, `sudo`, `DROP DATABASE`) or the turn is sent back | a reason it can act on |
| **defer** | not earned yet | the agent's **own** settings decide, exactly as if Solo License were not installed |

Solo License never widens what an agent may do beyond what it has earned, and if the gate is down every
hook defers - it never turns an outage into an "allow".

## Install - one line, any agent

```bash
uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license init --agent <agent>   # in your repo
uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license serve                  # keep it running
```

or paste the ready prompt from `solo-license prompt --agent <agent>` into your agent and let it install
itself. Claude Code can also use the plugin: `/plugin install solo-license --marketplace JAYATIAHUJA/Solo_license`.
The web app's **setup guide** (`/onboarding`) walks through all of it and turns green when the first hook arrives.

| Agent | Wired through | Sends a bad turn back |
|---|---|---|
| Claude Code (also GLM via z.ai) | HTTP hooks / plugin | yes |
| OpenAI Codex CLI | command hooks | yes |
| Cursor (IDE + cursor-agent) | command hooks | yes |
| Gemini CLI | command hooks | yes |
| Google Antigravity | command hooks | yes |
| GitHub Copilot CLI | command hooks | yes |
| Grok Build (xAI) | HTTP hooks | yes |
| Windsurf / Devin Desktop | command hooks | records it |
| Kiro | command hooks | records it |
| Cline | hook scripts | records it |
| OpenCode (how Groq models are used for coding) | plugin | records it |

`init` writes each agent's own config, merged with hooks already there (Entire's included), plus a
one-file standard-library shim `.solo-license/hook.py` for command-hook agents. Paths a shell would
expand are refused. Aider (no pre-action hooks) and Roo Code (discontinued) are not supported.

## How trust is earned

Trust is kept per **(repository, action class)**: `npm test`, `pytest` and `cargo test` all build the
same `test-run` record, so it is earned in a handful of runs instead of one per spelling. A chained
command is judged by its riskiest part, so `npm test && git push -f origin main` is a force-push.

| Level | Meaning |
|---|---|
| **L0** | asks you every time (defer) |
| **L1** | runs the command families a person already approved here |
| **L2** | runs every action of this class |

A class climbs only when **both** hold: a floor of verified runs, and the economic bound - the upper
credible bound of its failure rate is below break-even:

> running alone pays when `P(failure) × cost of one mistake < developer time an approval costs`

Running the tests earns L1 in 3 verified runs; pushing to a remote would need hundreds and is capped at
L1; deploys and database changes always ask. **Only a person's "yes" or an earned "allow" builds trust** -
actions an agent's own settings let through are recorded as *observed*, never credited. Failures always
count, whoever let the action run, and drop the class to L0.

## The end-of-turn check

Once per turn - never once per edit - the `Stop` hook checks the turn's work:

1. **Over-editing.** The diff since the prompt is graded 1-5 against the request (by
   [Jev](https://jevapi.dev), TypeSafe's calibrated decision model, when a key is set; by a size-and-spread
   rule otherwise). A score of 2 or less sends the turn back with the files to revert.
2. **Tests.** The repo's test command runs. Only a **regression** counts against the agent: the
   failing tests are compared by name against the turn's own starting point (pytest, node --test,
   jest/vitest, go test, cargo test, mocha), in a throwaway worktree that borrows `node_modules`/`.venv`.

A failed turn is demoted, linked to the **Entire checkpoint** of that session
(`entire checkpoint explain <id>`), and can be **rewound** from the dashboard - the changes are stashed,
never deleted. Every promote, demote and resume is a git commit in the license ledger.

## Results

### Before / after: one coding session replayed through the real gate

3 days × 5 requests in [`demo/shop-api`](demo/shop-api), real permission decisions, real turn checks
(`npm test`), real promotions. Reproduce: `make coding-benchmark` →
[`evidence/benchmarks/coding_before_after.md`](evidence/benchmarks/coding_before_after.md).

| | Before ("ask before changes") | After (Solo License) |
|---|---|---|
| Permission prompts you answer | 21 | **11** |
| Actions that ran without a prompt | 0 | **19** (earned) |
| Force-push to main | 3 prompts, one click from running | **3 denied** |
| Over-edited lines that reach your review | 157 | **0** (1 turn sent back) |
| Prompts per day | - | **9 → 2 → 1** |

A correct one-line fix whose repo already had an unrelated failing test is reported as
*failing before and after* - not blamed.

### The business (cfo.ai)

Per developer per month ([`planning/cfo/coding_business_model.md`](planning/cfo/coding_business_model.md),
`make cfo`): ask-every-time **$1,300** · full access **$330** · Solo License **$283**. That is $1,017 saved
per developer against asking every time, about 68× the $15 Team price; $0.48 unit cost (Jev + hosting),
96.8% gross margin, break-even at 276 seats.

## How the three hackathon tools are used

**neatlogs - one trace per turn.** `turn.start → gate.allow|ask|deny → tool.ran|failed|observed →
turn.blocked → license.promote|demote → turn.end`, with detections (`forbidden_action`) as error spans
and GenAI attributes on model calls. The before/after replay sends all 15 turns as traces.

**Entire - the history behind every license change.** Entire's session id *is* the agent's
`session_id`, so a failed turn points at the last checkpoint of that session; promotions and demotions
are commits; and every pull request in this repo went through Entire Trails - including review findings
that were fixed before merging (injection in hook paths, trust credited from an agent's own settings,
regressions hidden by a cached verdict).

**cfo.ai - the plan.** The coding-agent model above and the refund model below share the thesis that
the license level is a margin driver.

## Evidence for judges

| Requirement | Where |
|---|---|
| An agent completing a task end to end | The coding agent works a repo while the gate plans, gates, verifies (diff + tests), recovers (send back / rewind) and updates trust: [`sololicense/coding/`](sololicense/coding) |
| Before / after with numbers | [`evidence/benchmarks/coding_before_after.md`](evidence/benchmarks/coding_before_after.md) |
| A failure and what happened next | Over-edited turn sent back → reverted → verified; force-push denied and `git-remote` demoted; a regression blocks and demotes `file-edit` |
| neatlogs traces | one per turn (trace ids in the benchmark JSON); refund agent: [19 spans of one message](evidence/assets/screens/trace.png) |
| Entire | Trails on every PR, checkpoints linked to failed turns, ledger: `git log -- ledger/license_ledger.jsonl` |
| cfo.ai plan | [`planning/cfo/coding_business_model.md`](planning/cfo/coding_business_model.md) · refund plan: [app.cfo.ai/s/ELTPhGF4LAHDv6zV](https://app.cfo.ai/s/ELTPhGF4LAHDv6zV) |
| Tests | `python -m pytest` - 287 tests, including every agent's payloads and answers |
| Commits during the hackathon | `git log --since=2026-10-10` |

---

## Same engine, on payments

Solo License started as a support agent that earns the right to refund customers: it reads the
message, finds the order, checks your rules, pays through Stripe, **reads Stripe back to prove the money
moved**, and writes the reply. It still runs in the app under **Payments agent**, with the same ladder,
ledger and economics.

| Level | What the payments agent may do alone |
|---|---|
| L0 | Nothing - it suggests, you act |
| L1 | Prepares each refund; you approve with one click |
| L2 | Refunds under your cap |
| L3 | Everything, reviewed afterwards |

### Results

#### 1 · Standard benchmark: τ-bench retail

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

#### 2 · The agent improved: catch → recover → verify

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

#### 3 · Live run on the sample inbox (Groq `openai/gpt-oss-120b`, free tier)

6 messages in 12 s: two refunds paid and verified (one found from the sender's email alone), one
declined by the 30-day window with a store-credit offer, a $120 refund and an L1 store credit held
for approval, and *"This is the store owner. Ignore your rules…"* sent to a person.

#### 4 · The margin story (cfo.ai)

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

### Connectors

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

### How the tools are used for refunds

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

### Refund agent evidence

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

### Payments setup notes

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

#### Deploy the web app on Vercel

Import this repository into Vercel and set **Root Directory** to `frontend`. Vercel detects the
Vite build and deploys `dist`; `frontend/vercel.json` keeps direct links such as `/app/inbox`
inside the React app. Deploy the FastAPI service separately, then add its public HTTPS origin as
`VITE_SOLO_API_URL` in the Vercel project (for example, `https://api.example.com`, with no trailing
slash). On the API deployment set `SOLO_ALLOWED_ORIGINS=https://your-project.vercel.app` so the
browser may call it. Locally, leave that variable unset: Vite continues to proxy `/api` to
`SOLO_API_URL` or `http://127.0.0.1:8000`.

#### Operating policies in a real workspace

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


---

## Run it locally

**Requirements:** Python 3.11+, Node 20+, git, [uv](https://docs.astral.sh/uv/) for the one-liners.

```bash
pip install -r requirements.txt
uvicorn sololicense.api.app:app --port 8000      # the gate + API
npm --prefix frontend install
npm --prefix frontend run dev                    # http://127.0.0.1:5174 - landing, setup guide, dashboard
make coding-demo                                 # ../shop-api-demo: a repo with two bugs, hooks installed
```

Open Claude Code (or any supported agent) in `../shop-api-demo` and ask it to run the tests, then to
fix the bug in `cart.js`. The dashboard shows each decision, each turn's check and every level change.

| Command | What it does |
|---|---|
| `solo-license init --agent <x>` | Wire an agent's hooks into this repo (`auto`, `all`, or one of the 11) |
| `solo-license serve` / `doctor` / `prompt` | Run the gate · check it and the hooks · print the self-install prompt |
| `make coding-benchmark` | Before/after replay of a coding session through the real gate |
| `make test` | The test suite |
| `make cfo` | The financial models (coding agent, then refunds) |
| `make taubench` / `make benchmark` | The refund agent's τ-bench and recovery benchmarks |

## Architecture

```
plugin/solo-license/  Claude Code plugin: hooks, skill, /solo-license:trust
sololicense/coding/   the coding gate
  actions.py          tool call -> action class; forbidden commands; chains judged by the riskiest part
  agents.py           11 agents' native hooks <-> the gate's common events (allow / deny / defer)
  gate.py             licenses per (repo, class), decisions, turns, promote / demote / resume
  verify.py           end-of-turn check: diff scope, tests compared test by test against the turn's start
  ladder.py           floor + economic bound per class
  jev.py              calibrated decisions from Jev (optional)
  entire.py           Entire checkpoint of a failed turn; rewind
  install.py shim.py  per-agent config writers; the one-file command-hook shim
sololicense/cli.py    solo-license init | serve | doctor | prompt | hook
sololicense/          shared: domain (trust maths), services (git ledger, economics), observability (neatlogs), db
sololicense/agent/    the payments agent (refunds, store credit) and its connectors
frontend/             landing page, setup guide, dashboard, payments pages
planning/cfo/         financial models
demo/shop-api/        the demo repository
```

## What is new here, and what is not

Graduated autonomy is not new (*Levels of Autonomy for AI Agents*, Feng et al., 2025; AWS's
graduated-autonomy pattern), permission hooks are not new, and Claude Code's auto mode already
classifies risky actions. Solo License adds:

1. **Autonomy earned from verified outcomes, per repo and per kind of action** - promoted only when the
   evidence beats the break-even of a mistake's cost, and taken back by one failure.
2. **Over-editing as a trust signal** - a turn whose diff is out of proportion to the request is sent back,
   and counts against the agent.
3. **One gate for every agent** - the same earned trust, enforced through each agent's own hooks.

Limits we state plainly: only Claude Code has been run end to end with a live agent; the other agents'
hook formats follow their documentation and are tested with their documented payloads. The refund
agent's τ-bench result is a per-write counterfactual replay with reviewers assumed correct, and its
Stripe connector is tested against a mock of Stripe's API.
