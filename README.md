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
uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license onboard
```

`onboard` does the whole setup in one go: it finds the agents you use (Claude Code, Codex, Cursor, OpenCode, ...),
shows the hook changes and writes them, makes this machine's admin token and settings key (macOS Keychain, or
`~/.solo-license/credentials.json` readable only by you - no `SOLO_API_TOKENS` to write), starts the gate in the
background, checks it with a harmless read, and opens the dashboard already signed in at the setup guide, where
neatlogs, Jev and Entire are optional one-step connections. Or step by step:

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
| OpenCode (Groq, GLM, free models) | plugin, earns from `permission.ask` | records it |

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
count, whoever let the action run, and drop the class to L0. A person's yes is seen through Claude Code's and
Codex's `PermissionRequest`, and through OpenCode's `permission.ask` (so OpenCode with any model - Groq, GLM or a
free one - earns and loses trust the same way; once a call is earned, the plugin answers OpenCode's prompt itself).

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

## The control layer

Earning trust is the engine. Around it sit the controls a team needs while agents run unattended.

| Control | What happens |
|---|---|
| **Every denial tells the agent what to undo** | A failed or sent-back turn gets a message it can act on (`git checkout -- <files>`, the Entire checkpoint to rewind to), delivered in the agent's own hook format. Repeated forbidden attempts interrupt the agent. |
| **"This was wrong"** | One click on any decision or turn in the dashboard drops that class to L0 and queues a note the agent sees on its next prompt ("your last turn was flagged by the user: ..."). Levels animate as they change; a kill switch freezes every class. |
| **Per-principal licenses and subagents** | The main agent and each subagent type keep their own evidence. Subagents start capped at `[subagents] max` (default L1), can be denied by type, and are checked at their own stop. |
| **Loop detection** | Three identical calls get guidance, five are denied, the same failure three times says "stop retrying", and a file edited four times in a turn is sent back. A loop is a halt, not a demotion. |
| **Session digest** | Jev judges a risky command against the session's goal, the turn so far and the policy (a bounded digest, never the raw transcript), and asks a person when it is not confident. |
| **MCP tool classes** | `mcp__github__merge_pull_request` is its own class, `mcp:github`. Reads can earn L2, writes L1 once you approved that tool, destructive verbs (merge, delete, deploy) always ask; `[tools."mcp__aws__*"]` in the policy file can forbid or cap a tool. |
| **Budget guardrails** | `[budget]` caps USD per session and per day, read from the agent's own transcript where it reports cost. Past a cap only reading is allowed until a person raises it. |
| **Policy as code** | `.solo-license/policy.toml` is committed with the repo and can only make the agent ask *more*. `solo-license policy init` writes a starter file. |

Everything above is stored in the repo's own SQLite file and shows up as neatlogs spans, so a decision
can be explained after the fact.

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
turn.blocked → license.promote|demote → turn.end`, with detections (`forbidden_action`, loops) as error
spans and GenAI attributes on model calls. The before/after replay sends all 15 turns as traces.

**Entire - the history behind every license change.** Entire's session id *is* the agent's
`session_id`, so a failed turn points at the last checkpoint of that session; promotions and demotions
are commits; and every pull request in this repo went through Entire Trails and the Entire Gates check -
including review findings that were fixed before merging (injection in hook paths, trust credited from
an agent's own settings, regressions hidden by a cached verdict). Details: [`evidence/entire.md`](evidence/entire.md).

```bash
git log --oneline -- ledger/license_ledger.jsonl       # how each action class earned and lost its license
entire checkpoint list                                 # the sessions behind the code
```

**cfo.ai - the plan.** The license level is a margin driver: review time saved by earned autonomy
against the incident bill of blind autonomy. Model and plan: [`planning/cfo/`](planning/cfo).

## Evidence for judges

| Requirement | Where |
|---|---|
| An agent completing a task end to end | The coding agent works a repo while the gate plans, gates, verifies (diff + tests), recovers (send back / rewind) and updates trust: [`sololicense/coding/`](sololicense/coding) |
| Before / after with numbers | [`evidence/benchmarks/coding_before_after.md`](evidence/benchmarks/coding_before_after.md) |
| A failure and what happened next | Over-edited turn sent back → reverted → verified; force-push denied and `git-remote` demoted; a regression blocks and demotes `file-edit`; a flagged decision drops the class and tells the agent |
| neatlogs traces | one per turn (trace ids in the benchmark JSON), deep-linked from each history row in the dashboard |
| Entire | Trails and Entire Gates on every PR, checkpoints linked to failed turns, ledger: `git log -- ledger/license_ledger.jsonl` |
| cfo.ai plan | [`planning/cfo/coding_business_model.md`](planning/cfo/coding_business_model.md) · [screenshot](evidence/assets/screens/cfo-scorecard.png) |
| Tests | `make test` (backend, pytest) and `npm --prefix frontend test`; CI runs both plus the frontend build on every PR |
| Commits during the hackathon | `git log --since=2026-10-10` |

---

## Run it locally

**Requirements:** Python 3.11+, Node 20+, git, [uv](https://docs.astral.sh/uv/) for the one-liners.

```bash
pip install -r requirements.txt
cp .env.example .env                             # sets SOLO_DEMO_MODE=1: "Try the demo" works without a token
uvicorn sololicense.api.app:app --port 8000      # the gate + API
npm --prefix frontend install
npm --prefix frontend run dev                    # http://127.0.0.1:5174 - landing, setup guide, dashboard
make coding-demo                                 # ../shop-api-demo: a repo with two bugs, hooks installed
```

On Windows PowerShell use `Copy-Item .env.example .env`. Without `SOLO_DEMO_MODE=1` (or `SOLO_API_TOKENS`)
the dashboard answers 401 and shows no data: open the app, choose **Try the demo**, enter your name.

Open Claude Code (or any supported agent) in `../shop-api-demo` and ask it to run the tests, then to
fix the bug in `cart.js`. The dashboard shows each decision, each turn's check and every level change.

For a machine-wide install, `solo-license init --global` writes the user-level hook config of every
agent that has one, and `solo-license serve --background` keeps the gate running (`status` / `stop`
manage it, `doctor` checks the gate and the hooks).

| Command | What it does |
|---|---|
| `solo-license init --agent <x>` | Wire an agent's hooks into this repo (`auto`, `all`, or one of the 11); `--global` for user-level, `--dry-run` to preview, `--remove` to uninstall |
| `solo-license serve [--background]` | Run the gate and dashboard · `status` / `stop` for the background gate |
| `solo-license doctor` | Check the gate and this repository's hooks |
| `solo-license policy init` | Write a starter `.solo-license/policy.toml` |
| `solo-license prompt --agent <x>` | Print the self-install prompt |
| `make coding-benchmark` | Before/after replay of a coding session through the real gate |
| `make test` | The backend test suite |
| `make cfo` | The financial model |

Set a Jev key for model-graded turns (rules run without one), `NEATLOGS_API_KEY` for traces, and
`SOLO_API_TOKENS` (`operator` < `approver` < `admin`) to lock the API when deployed.

## Architecture

```
plugin/solo-license/  Claude Code plugin: hooks, skill, /solo-license:trust
sololicense/coding/   the coding gate
  actions.py          tool call -> action class (incl. mcp:<server>); forbidden commands; chains judged by the riskiest part
  agents.py           11 agents' native hooks <-> the gate's common events (allow / deny / defer)
  gate.py             licenses per (repo, principal, class), decisions, turns, promote / demote / flag / resume
  policy.py           built-in ceilings + committed policy.toml + this machine's rules; subagents, budget, tools
  remediation.py      what the agent is told to undo; queued notes for the next prompt
  loops.py            repeated-call fingerprints: guidance, deny, halt
  digest.py jev.py    bounded session digest and calibrated decisions from Jev (optional)
  budget.py           spend caps read from the agent's transcript
  verify.py           end-of-turn check: diff scope, tests compared test by test against the turn's start
  ladder.py           floor + economic bound per class
  entire.py           Entire checkpoint of a failed turn; rewind
  install.py shim.py global_install.py   per-agent config writers; the one-file command-hook shim
sololicense/cli.py    solo-license init | serve | status | stop | doctor | policy | prompt | hook
sololicense/          shared: domain (trust maths), services (git ledger, economics), observability (neatlogs), db
frontend/             landing page, setup guide, dashboard (Coding, History, Settings)
planning/cfo/         financial model and plan
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
3. **One gate for every agent** - the same earned trust, enforced through each agent's own hooks, per
   principal (main agent and each subagent type) and per MCP server.
4. **A control layer a person can steer live** - flag a decision and the agent hears about it on its next prompt.

Limits we state plainly: only Claude Code has been run end to end with a live agent; the other agents'
hook formats follow their documentation and are tested with their documented payloads. The demo
benchmark is a scripted session replayed through the real gate, not a field study.

*History: Solo License began as a support agent that earned the right to issue refunds. That product
was removed in v3 so the repository tells one story; the trust engine, ledger and economics carried over.*
