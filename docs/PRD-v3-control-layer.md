# Solo License v3 - PRD and implementation plan
## The control layer for coding agents

*12 Oct 2026 · supersedes the product sections of `docs/HANDOVER.md` · inputs: the judge call
("Zero Trust Code Access"), the mentor call (11 Oct), a research pass on agent hooks, model/cost
controls, MCP gateways, credentials and loop detection (sources in §12)*

---

## 0. Decisions (read this first)

| # | Decision | Why |
|---|---|---|
| D1 | **Scrap the payments/refund agent completely** - code, DB tables, UI, cfo model, benchmarks | Judge and mentor both: support/refund is generic and hard to package. It dilutes the story. |
| D2 | **Product = the control layer for coding agents**: earned autonomy + guardrails + live remediation + cost control | Judge: "you become the control layer for everything… pitch it as time and money". |
| D3 | **Enforcement stays in hooks; decisions stay outside the agent** (our local gate) | Research: skills are advisory ("every tool remains callable"); hooks are deterministic and fire before permission modes. |
| D4 | **Packaging first: Claude Code plugin + Codex hooks + one-line CLI**; desktop/tray app later | Judge: "packaging is the most important"; team plan: small plugin for Codex and Claude. |
| D5 | **Every demotion talks back to the agent** ("this is why, revert X") the moment it happens | Judge: "next message from your end goes to Claude… powerful". Research: PostToolUse `decision:block` + `additionalContext` reaches the model mid-turn. |
| D6 | **Subagents get their own trust and a lower ceiling** | Judge: "people use sub agents… restrict access, earn it back". Claude Code payloads carry `agent_id`/`agent_type`. |
| D7 | **Jev judges with session context, never a lone span** | Judge: "Zev has a context problem". Jev takes 32k of state; we send a structured session digest. |
| D8 | **Natural-language rules compile to the policy file, never decide at runtime** | Research: NL→Cedar/Rego works only with validate → test → human preview → activate. |
| D9 | Cost/model control and credential brokering are **phase 2-3**, built on stable hooks (`PreModelSwitch`, `availableModels`, statusline cost, `credential_process`) | Big value, but the core must be solid first (judge: "start from the first part"). |

---

## 1. What the judge said, and what we do with it

| Judge idea | Verdict | Where in this PRD |
|---|---|---|
| Zero trust → earn → lose on failure or user flag | **Have it**; add *user flag* | F6 |
| Interface where a wrong decision is flagged and the access level visibly drops | **Build now** - it is the viral demo | F6, F12 |
| On demote, message the agent directly to revert | **Build now** | F3 |
| Apply it to subagents | **Build now** (Claude Code), partial (Codex/Cursor) | F4 |
| "Can a skill file do this without hooks?" | **Answered: no** (§3.4); ship a skill *as well* for good behaviour | F10 |
| Zev context problem | **Build now**: session digest | F5 |
| Packaging: plugin / desktop / MCP / UI | Plugin + CLI **now**, tray app **later**, no MCP gate | F10 |
| Middleware for all tools with NL role rules (admin/member/viewer) | **Phase 2**: roles + MCP tool classes; NL rules compile to policy | F7 |
| Revoke access right away (e.g. delete the AWS token) | **Phase 3**: credential broker that stops minting | F8 |
| Real-time remediation while the agent runs (loops, useless failing steps) | **Phase 1-2**: loop/stuck detection + guidance | F5, F9 |
| Cost: past a budget, no high-tier models | **Phase 2**: budget policy + `PreModelSwitch` + Agent(model) gating | F11 |
| Pitch on time and money | **Now** | §9 |
| Refund / support use case | **Drop** | F1 |
| PR merge bot | **Drop** (crowded) | - |

---

## 2. Product definition

**One line:** *Solo License is the control layer for coding agents: they earn autonomy from verified
results, lose it the moment they misbehave, get told why and what to fix, and never exceed the team's
policy or budget.*

**Who:** developers on Claude Code / Codex / Cursor who today choose between approval fatigue and
full access; then engineering leads who must let a team use agents without "full access" risk.

**Jobs it does:**
1. Stop asking me for things the agent has proven it does right *here* (time).
2. Stop the agent from things it must never do here (risk).
3. When it goes wrong, tell the agent to fix it and tell me what happened (remediation).
4. Keep spend and model use inside a budget (money).
5. Give me one place to see and change all of it, with an audit trail (control).

**Not in scope:** customer support, refunds, a PR review bot, an MCP server as the gate, a cloud SaaS
(phase 4 at the earliest).

---

## 3. Research findings that shape the design

### 3.1 Identifying subagents
- **Claude Code:** every hook payload inside a subagent carries `agent_id` and `agent_type`
  (PreToolUse/PostToolUse explicitly; PermissionRequest gets common fields - verify by logging).
  `SubagentStart` can inject `additionalContext` (cannot block); `SubagentStop` can `block` with a
  reason the subagent receives. Spawning can be gated with PreToolUse on the `Agent` tool or rules like
  `Agent(model:opus)`. The Agent tool's PostToolUse response carries `usage`, `resolvedModel`, `modelsUsed`.
- **Codex:** `SubagentStart/Stop` carry `agent_id`; tool hooks do **not** (subagents share `session_id`).
- **Cursor:** `subagentStart` can **deny** (has `subagent_type`, `subagent_model`); `subagentStop` has
  `loop_count`, `modified_files`, `followup_message`.

### 3.2 Talking back to the agent (Claude Code)
| Moment | Mechanism |
|---|---|
| Before an action | PreToolUse deny `permissionDecisionReason` / PermissionRequest deny `message` (`interrupt:true` stops it) |
| Right after a bad action | PostToolUse `{"decision":"block","reason":…,"hookSpecificOutput":{"additionalContext":…}}` - delivered mid-turn |
| End of turn | Stop / SubagentStop `{"decision":"block","reason":…}` - becomes the next instruction (cap 8) |
| Next prompt | UserPromptSubmit `additionalContext` |
| Background check | command hook with `asyncRewake: true`, exit 2 wakes Claude with stderr |
`systemMessage` is shown to the **user**, not the model.

### 3.3 Cost and models
- Hooks get **no cost fields**. The statusline JSON has `cost.total_cost_usd`, token counts and `model`
  → a statusline script can persist it per `session_id` for the gate to read. Transcript JSONL has
  per-message `usage` (undocumented schema).
- `availableModels` (+ `enforceAvailableModels`) restricts models; `deniedModels` (managed, 2.1.283+).
- **`PreModelSwitch` hook** (2.1.251+) can block a switch (`from_model`, `to_model`, pricing, cache
  cost). Automatic fallbacks only reach `PostModelSwitch` (cannot block).
- Hard enforcement option: LiteLLM proxy (`ANTHROPIC_BASE_URL`) with per-key `max_budget`,
  `budget_duration`, model allowlists (needs Postgres).

### 3.4 Skills vs hooks (the judge's question)
- Skills are **advisory**: `allowed-tools` pre-approves but "every tool remains callable"; a skill
  cannot stop a tool call. Hooks are deterministic, fire before permission modes, and a deny holds
  even in `bypassPermissions`. Permission rules are "enforced by Claude Code, not by the model".
- **So Claude cannot do this itself with a skill.** We keep the skill only to make the agent cooperate
  (read reasons, prefer small diffs) - enforcement is the hooks.
- PermissionRequest can return `updatedPermissions` (`addRules` with destination `session`). We **do
  not** use it to grant autonomy: a rule written into Claude's settings cannot be revoked by us the
  instant the agent fails. The gate stays the single source of truth.

### 3.5 Tools, roles and natural-language rules
- MCP tools appear as `mcp__<server>__<tool>` (input also has `mcp_server`); a PreToolUse hook can
  deny by any rule we hold; static fallback `permissions.deny: ["mcp__github__delete_*"]`.
- Gateways (Docker: Cedar, deny-by-default; Runlayer: role policies; Permit.io: trust level + tool
  risk) confirm the model: **identity × tool risk × trust → decision**.
- NL→policy works as: LLM emits a constrained DSL → schema validation → generated test cases → human
  preview ("would have blocked these 12 past calls") → activate (AWS NL2Cedar, AutoCedar, Prose2Policy).

### 3.6 Credentials
- AWS `credential_process` re-runs a helper before expiry; non-zero exit = no credentials → the gate
  can **stop minting** (soft revoke at next refresh, STS 15-min minimum). Hard revoke: deny policy on
  the role with `aws:TokenIssueTime` (AWSRevokeOlderSessions).
- GitHub App installation tokens (1 h) per session; revoke with `DELETE /installation/token`.
- `CLAUDE_ENV_FILE` (SessionStart/CwdChanged/FileChanged) injects env for Bash only, not MCP servers.

### 3.7 Loops
Fingerprint each call (tool + normalised args), sliding window (~20), warn at 3 identical, block on
recurrence; also same-command-same-failure, A-B-A-B alternation, edit thrash on the same file/old_string.
Injected text can be ignored - an **execution halt** cannot.

### 3.8 Jev limits
64k tokens per request, **32k for state + the longest question**; choice ≤255 options, score 2-10
levels; 70-500 ms; state works best as an **object** with named parts; several questions per call cost
almost nothing extra.

---

## 4. Architecture v3

```
                  ┌──────────── Agents ─────────────┐
                  │ Claude Code · Codex · Cursor …  │  hooks (deterministic)
                  └──────┬───────────────▲──────────┘
     PreToolUse / PermissionRequest      │  allow / deny / defer
     PostToolUse / Stop / Subagent*      │  + reason / additionalContext (remediation)
     PreModelSwitch / statusline         │
                  ┌──────▼───────────────┴──────────┐
                  │        Solo License gate        │  local, per machine (team server later)
                  │  identity (repo, agent, subagent, role)
                  │  classify → policy → trust → decide
                  │  watchers: loops · cost · scope · tests
                  │  remediation composer
                  │  context digest → Jev (optional)
                  └──┬─────────┬──────────┬─────────┘
           SQLite    │  git ledger (Entire)│ neatlogs traces
   licenses/turns/   │  every change       │ one trace per turn,
   decisions/costs   │  = a commit         │ detections as spans
                  ┌──▼──────────────────────────────┐
                  │ Dashboard: live access levels,   │
                  │ flag a decision, policy, budget, │
                  │ kill switch                      │
                  └──────────────────────────────────┘
   Optional enforcers: credential_process broker (AWS/GitHub) · LiteLLM proxy (hard budgets)
```

Identity key extends from `(repo, action_class)` to **(repo, principal, action_class)** where
principal = `main` or `subagent:<agent_type>`; the repo-level record stays the default every principal
inherits from (with a ceiling).

---

## 5. Feature specifications

Each feature: **what**, **design**, **acceptance**, **effort** (S ≤ ½ day, M ≤ 1½ days, L > 1½ days).

### F1 - Scrap the payments agent (D1) · M
**Remove:**
- `sololicense/agent/`, `connectors/`, `bench/`, `faults/`
- `services/`: `license_service.py`, `policy_service.py`, `policy_gate.py`, `verification.py`, `evidence.py`, `alerts.py`, and the refund parts of `economics.py`
- `domain/`: `license.py`, `models.py`, `policy.py`, `task_classes.py`
- `db/repositories/`: orders, tickets, runs, permits, policies, license, faults, detections
- Refund tables in `schema.sql`
- `planning/cfo/model.py` + `business_model.md`
- `scripts/`: benchmark, taubench_eval, injection_suite, generate_evidence, readme_charts
- Refund tests (integration/*, test_policy*, test_neatlogs_depth refund parts, unit/test_intake, test_license_state_machine, test_economics refund parts)
- `evidence/benchmarks/{benchmark,taubench,injection}.*` + charts
- Frontend: `Overview`, `Inbox`, `AgentDesk`, `Orders`, `Runs`, `Reports`, `autopilot/`, `components/mission/`, `onboarding/` (payments wizard), `PolicyEditor`, `IntegrationFields` (Stripe/inbox parts), `/onboarding/payments` route, sidebar "Payments agent"
- Landing FAQ item and footer link; README "Same engine, on payments"

**Keep:** `domain/trust.py`, `services/git_ledger.py`, `observability/*`, `security.py`, `config.py` (drop
LLM-provider/Stripe fields), `db/database.py`, `repositories/{agent,events,spans,settings}.py`, the
whole `sololicense/coding/`, `planning/cfo/coding_model.py`.

**Data migration:**
- `license_events.run_id` has a foreign key to `runs`. Create `agent_events` (repo, principal, class, kind, from, to, reason, actor, git_sha, created_at).
- Move rows where `task_class LIKE '%@%'`, point `Ledger.jsx` at it, then drop the refund tables.
- Old SQLite files keep working because `apply_schema` only creates.
- A one-shot `migrate_v3()` copies the events, and refund tables are ignored, not dropped, for one release.

**Acceptance:**
- `grep -ri "refund\|stripe\|order_id" sololicense frontend/src` returns nothing outside the changelog.
- Tests pass; the app boots with an empty DB; the dashboard, history and settings work.
- **Each removal is its own PR:** backend, frontend, data, docs. All four green.

### F2 - Identity model: repo × principal × class · M
- Parse `agent_id`/`agent_type` (Claude), `subagent_type` (Cursor), Codex none → `main`.
- `agent_licenses` gains `principal` (default `main`). Lookup: principal row if present, else repo row
  capped by `policy.subagents.max` (default 1).
- Every decision, turn and event records principal.
- **Acceptance:** a subagent at L0 is asked while the main agent at L2 runs; a subagent failure demotes the
  subagent row and (configurable) the repo row.

### F3 - Remediation that talks back (D5) · M
- **On deny:** the reason says what to do instead (already). Add `interrupt:true` for repeated forbidden attempts (3 in a turn).
- **On a failure after the fact:** PostToolUse returns `decision:block` + `additionalContext`. Example: *"Solo License: `npm install left-pad` failed and `install-dep` is back to asking. Undo the partial install (`git checkout package.json package-lock.json`) and continue without it."* Cursor: `additional_context`; Codex: block.
- **On demotion at turn end:** the Stop block reason includes the revert instruction, the Entire checkpoint id, and `git stash`/`git checkout` commands.
- **On a person's flag (F6):** the next UserPromptSubmit injects *"Your last turn was flagged by the user: <reason>. Revert … before continuing."*
- Composer: one function builds the message from (event, class, policy rule, diff summary, checkpoint) so every agent gets the same content in its own format.
- **Acceptance:** live Claude Code - a failing install is followed by the agent reverting the lockfile within the same turn; a flagged turn is reverted on the next prompt.

### F4 - Subagents (D6) · M
- SubagentStart: inject its license summary (`additionalContext`: what it may do alone, what always asks).
- PreToolUse on `Agent`: deny spawning if policy forbids the type or model (`Agent(model:opus)` while over budget, F11).
- SubagentStop: run the turn check on the subagent's changes (`modified_files` / diff) and `block` with remediation.
- Policy: `[subagents] max = 1`, `deny_types = ["…"]`.
- **Acceptance:** an Explore subagent cannot `git push`; a subagent that over-edits is sent back at its own stop.

### F5 - Context-aware judging and live guidance (D7) · M
- **Session digest** (kept by the gate per session, ≤ 20k tokens):
  ```json
  {"goal": "<first prompt of the turn>", "turn": {"files_touched": [], "diff_stat": "", "failures": []},
   "recent_calls": [{"tool": "", "args_digest": "", "outcome": ""}],
   "trust": {"class": "", "level": 0, "streak": 0},
   "policy_excerpt": [], "current_call": {"tool": "", "input": {}, "principal": ""}}
  ```
- Jev called once per decision that needs it, with several questions:
  - `noul` "violates the user's goal or policy"
  - `choice` risk tier
  - `score` relevance to the goal (1-5)
  - Low confidence → defer to a person.
- Also used at Stop for scope grading (exists) with the goal + diff hunks, not the whole diff.
- **Acceptance:** the same command judged differently with two different goals in a fixture test; requests stay < 32k tokens (asserted).

### F6 - Flag a decision; watch access drop live · S-M
- Dashboard: every decision/turn has **"This was wrong"** → the class (and principal) is demoted, a ledger commit `flag(...)` is written, and F3 queues a remediation message for that session's next prompt.
- **Live view:** a per-repo strip of classes with levels animating up/down as events stream (SSE or 2 s poll). Ready for a screen recording.
- **Acceptance:** flag in UI → level drops in < 2 s → the agent's next prompt carries the remediation.

### F7 - Tools, MCP and roles (phase 2) · L
- **MCP tools become action classes:** `mcp:<server>` by default, with risk from policy:
  ```toml
  [tools."mcp__github__*"]    risk = "write"
  [tools."mcp__aws__delete_*"] risk = "destructive"   # always asks / deny
  ```
- **Roles:** principal → role via policy (`[roles] "dev@acme.com" = "member"`; default from `git config user.email`). Per-role ceilings and denies (`[role.viewer] max = 0, tools.deny = ["mcp__*"]`).
- **Natural-language rules:** the dashboard textbox goes to an LLM, which emits our TOML DSL, then:
  1. schema validation;
  2. generated allow/deny examples;
  3. a **preview against the last 500 decisions** ("would have blocked 12");
  4. the human approves, and it is saved as a policy PR or local policy.

  It never runs at decision time.
- **Acceptance:** the "viewers cannot use the AWS MCP" rule written in English compiles, previews and enforces.

### F8 - Credential broker (phase 3) · L
- `solo-license creds aws --class deploy` as `credential_process`: it mints STS creds (15 min, session policy) **only if** the class is not frozen or demoted. Demotion means no new creds, plus an optional hard revoke (`aws:TokenIssueTime` deny).
- GitHub: an App installation token per session through `SessionStart` + `CLAUDE_ENV_FILE`; revoked on demotion.
- **Acceptance:** after a destructive AWS attempt, the next `aws` call fails for lack of credentials and the agent is told why.

### F9 - Loop and stuck detection · S
- Fingerprint every call in the gate (already sees every PermissionRequest/PostToolUse).
- Three thresholds:
  - 3 identical → guidance via additionalContext;
  - 5 → deny with `interrupt`;
  - same failing command 3× → *"this keeps failing for the same reason: <stderr head>; stop retrying, try X"*.
- Edit thrash on the same file/hunk → turn sent back.
- Not a demotion by itself; it counts toward the session's remediation history.
- **Acceptance:** a fixture session that loops is stopped by the 5th repeat.

### F10 - Packaging (D4) · M
- **Claude Code plugin** (exists): add the `PreToolUse` deny path for non-prompting modes, `SubagentStart/Stop`, `PreModelSwitch`, a statusline script for cost (opt-in), and the skill.
- **Codex:** a `hooks.json` "plugin" folder + a `/solo-license` slash prompt; `init --agent codex` (exists).
- **CLI:**
  - `init --global` (user-level hooks for every repo);
  - `serve --background` (Windows: scheduled task; macOS: launchd; Linux: systemd user unit);
  - `doctor` checks versions (`PreModelSwitch` needs Claude Code ≥ 2.1.251).
- **Later:** a tray app wrapping `serve` + dashboard; then a team server (shared ledger and policy, hook key).
- **Acceptance:** a fresh machine goes from one command to the first gated prompt in < 2 minutes, measured.

### F11 - Cost and model control (phase 2) · M
- The statusline script writes `{session_id, cost_usd, tokens, model}` to `~/.solo-license/cost/<session>.json`, and the gate reads it.
- **Policy:**
  ```toml
  [budget]
  session_usd = 5
  day_usd = 25
  expensive_models = ["opus"]
  ```
- **Over budget:**
  1. Deny `PreModelSwitch` to an expensive model.
  2. Deny `Agent(model:opus)`.
  3. Send a remediation note *"budget reached, continue with sonnet"*.
  4. At hard cap, `continue:false`.
- **Teams:** `solo-license init --managed` emits managed settings with `availableModels`/`deniedModels`. Hard caps through an optional LiteLLM proxy key per developer.
- Dashboard: spend per session/day, and saved approvals expressed in $ next to it (time *and* money).
- **Acceptance:** past `session_usd`, switching to opus is blocked with a message; the dashboard shows the spend.

### F12 - Dashboard v3 · M
Pages:
- **Live** (levels animating, flags, kill switch)
- **Sessions** (turns, digest, remediation sent)
- **Policy** (team file, local, NL rules)
- **Budget**
- **History** (ledger)
- **Setup**

The payments pages are gone (F1).

---

## 6. Data model changes

| Table | Change |
|---|---|
| `agent_licenses` | + `principal TEXT NOT NULL DEFAULT 'main'`; PK (repo, principal, action_class) |
| `agent_decisions`, `agent_turns` | + `principal`, + `role` |
| `agent_events` (new) | replaces `license_events` for coding (no FK to runs) |
| `agent_sessions` (new) | session_id, agent, repo, started, cost_usd, model, digest JSON |
| `agent_flags` (new) | decision/turn id, actor, reason, delivered_at |
| `agent_fingerprints` (new, rolling) | session, fingerprint, count, last_outcome |
| refund tables | ignored for one release, then dropped |

---

## 7. Implementation plan

### Phase 0 - finish what is open (today)
- PR #38 (command-path parsing + handover) green and merged.
- Record the demo on the current build if the submission needs it now (see §9).

### Phase 1 - "control layer core" (≈ 4-5 days, in this order)
| # | PR | Effort | Depends on |
|---|---|---|---|
| 1 | F1a backend scrap + `agent_events` migration | M | - |
| 2 | F1b frontend scrap + nav | S | 1 |
| 3 | F1c docs/landing/README scrap | S | 2 |
| 4 | F3 remediation composer + PostToolUse/Stop/UserPromptSubmit wiring | M | - |
| 5 | F6 flag + live view | M | 4 |
| 6 | F2 + F4 principals and subagents | M | 1 |
| 7 | F9 loop detection | S | 4 |
| 8 | F5 session digest + Jev multi-question | M | 6 |
| 9 | F10 `init --global`, `serve --background`, plugin additions | M | 6 |

### Phase 2 - "money and roles" (≈ 1 week)
- F11 cost/model control
- F7 MCP tool classes + roles + NL rules
- Dashboard Budget and Policy pages

### Phase 3 - "pull the plug"
- F8 credential broker (AWS, GitHub)
- Team server

### Phase 4 - product
- Tray app
- Hosted team server
- Pricing: Team $15/dev, Enterprise (from the cfo model)

**Working rules:** one PR per row; CI + Entire Gates green; each PR ships tests and, where it changes
behaviour, a live Claude Code check.

---

## 8. Success metrics

| Metric | Target |
|---|---|
| Prompts a developer answers per day (replay benchmark) | −50% vs ask-before-changes (today: 21 → 11) |
| Over-edited lines reaching review | 0 in benchmark |
| Forbidden actions executed | 0 |
| Time from demotion to agent's corrective action | same turn (F3) |
| Install → first gated prompt | < 2 min |
| Gate latency (no Jev / with Jev) | < 20 ms / < 600 ms p95 |
| Session spend over budget | 0 with F11 on |

---

## 9. Pitch and demo

**Pitch (time and money):**
1. Teams give coding agents full access because approving every command wastes hours.
2. Full access costs money: regressions, destructive commands, runaway spend.
3. Solo License is the control layer:
   - autonomy earned per repo, per action, per subagent;
   - revoked the instant something goes wrong, with the agent told how to fix it;
   - capped by the team's policy and budget;
   - every change auditable in git.

Numbers: 21 → 11 prompts, 157 → 0 over-edited lines, $1,017/dev/month saved vs ask-every-time.

**Demo (3 min):**
1. Earn: `npm test` ×3 → runs alone.
2. Over-edit → sent back → reverted.
3. Subagent tries `git push` → denied, told why.
4. **Flag a turn in the dashboard → level drops live → the agent reverts on its own.**
5. Over budget → switching to opus is blocked.
6. History = git commits.

Step 4 is the moment the judge said could go viral.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Hook schemas change between agent versions | All mapping in `agents.py`; `doctor` checks versions; contract tests per agent payload |
| Codex/Cursor tool hooks lack subagent ids | Treat as `main`; use their SubagentStart/Stop for start-context and end checks |
| Remediation text ignored by the model | Escalate to execution halts (deny, `interrupt`, Stop block) - text is guidance, halts are guarantees |
| Jev unavailable / slow | Rules decide; Jev only in grey zones; timeout → defer, never allow |
| NL rule compiles to something unintended | Preview on past decisions + human approval + versioned file |
| Credential broker misconfigured locks the dev out | Opt-in per class; `doctor` dry-run; manual override in dashboard with ledger record |
| Statusline cost is an estimate | Label it as estimate; hard caps via proxy for teams |
| Scope creep before submission | Phase 0 only tonight; everything else is post-hackathon |

---

## 11. Open questions

1. When a subagent fails, should the parent's repo-level license also drop? Proposal: **yes for destructive classes, no for others**, configurable in policy.
2. Should a user flag count as one failure (Bayesian evidence) or a hard reset to L0? Proposal: **hard reset**, matching the "driving license" story.
3. Where do roles come from for solo developers? Proposal: everyone is `admin` until a team policy defines roles.
4. Tray app stack: Tauri (small) vs Electron. Proposal: Tauri, later.

---

## 12. Sources

- Claude Code hooks: https://code.claude.com/docs/en/hooks · guide: https://code.claude.com/docs/en/hooks-guide
- Permissions: https://code.claude.com/docs/en/permissions · skills: https://code.claude.com/docs/en/skills
- Settings (availableModels, deniedModels, modelPricing): https://code.claude.com/docs/en/settings-reference · statusline: https://code.claude.com/docs/en/statusline
- Codex hooks: https://learn.chatgpt.com/docs/hooks · Cursor hooks: https://cursor.com/docs/agent/hooks
- LiteLLM budgets: https://docs.litellm.ai/docs/proxy/users · Claude Code via LiteLLM: https://docs.litellm.ai/docs/proxy/client_setup/claude_code
- Docker MCP policies (Cedar): https://docs.docker.com/ai/sandboxes/governance/access-controls/mcp/ · Runlayer: https://docs.runlayer.com/platform-policies.md · Permit MCP Gateway: https://docs.permit.io/permit-mcp-gateway/architecture/
- NL→policy: AWS NL2Cedar https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-natural-language.html · AutoCedar (arXiv 2607.03656) · Cedar autoformalization (arXiv 2606.26649) · Prose2Policy (arXiv 2603.15799)
- AWS credential_process: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sourcing-external.html · revoke sessions: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html
- Loop detection: https://docs.praison.ai/docs/features/doom-loop-detection · https://openrouter.ai/docs/agent-sdk/call-model/doom-loop-detection · arXiv 2603.05344
- Jev: https://jevapi.dev/ · https://docs.typesafe.ai/api · https://docs.typesafe.ai/models.md · https://docs.typesafe.ai/concepts/state.md

Items marked unverified in research (log real payloads before relying on them):
- `agent_id` on PermissionRequest
- unset via `CLAUDE_ENV_FILE`
- `--max-budget-usd`
- LiteLLM key-block endpoint names
- transcript usage schema
