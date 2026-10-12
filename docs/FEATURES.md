# Solo License - every feature, and where to find it

Solo License is the control layer for coding agents: each kind of action is auto-approved only once it has
proven itself in your repository, and taken back the moment it fails. This page lists everything the product
does today, and where you see it: the **CLI**, the **dashboard**, the **Claude Code plugin**, or the **API**.

**Status key:** ✅ tested and run end to end · 🧪 tested against the agent's documented payloads (not yet run
live with that agent).

---

## 1. Setup

| Feature | What it does | Where | Status |
|---|---|---|---|
| **One-command onboarding** | `solo-license onboard` finds your agents, previews and writes their hooks, makes this machine's admin token and settings key (macOS Keychain, or a file only you can read), starts the gate, checks it with a harmless read, and opens the dashboard already signed in at the setup guide | CLI | ✅ |
| Per-repo or machine-wide hooks | `init --agent <x>` for one repo; `init --global` for every repo; `--dry-run` previews, `--remove` uninstalls | CLI | ✅ |
| Background gate | `serve --background`, `status`, `stop` (Windows, macOS, Linux) | CLI | ✅ |
| Health check | `doctor`: is the gate up, which agents are wired here | CLI | ✅ |
| Self-install prompt | `prompt --agent <x>` prints a prompt your agent can follow to install Solo License itself | CLI | ✅ |
| Setup guide | Pick your agent, copy its install command, optionally connect neatlogs, Jev and Entire (each with a Test), and watch the first hook arrive | Dashboard `/onboarding` | ✅ |
| Claude Code plugin | `/plugin marketplace add JAYATIAHUJA/Solo_license`, then `/plugin install solo-license@solo-license`; `/solo-license:trust` shows the licenses | Plugin | ✅ |
| Dashboard on the gate's port | the gate serves the built dashboard itself, so onboarding needs no second server | API | ✅ |

## 2. Earned autonomy (the engine)

| Feature | What it does | Where | Status |
|---|---|---|---|
| Licenses per (repo, action class) | `test-run`, `file-edit`, `install-dep`, `git-remote`, `deploy`, ... ; `npm test`, `pytest` and `cargo test` build the same record | Dashboard (Coding) | ✅ |
| Three levels | L0 asks every time · L1 runs the commands a person already approved here · L2 runs the whole class | Dashboard | ✅ |
| **Promotion** priced by economics | a class climbs only when a floor of verified runs is met **and** the upper credible bound of its failure rate is below break-even (approval time saved vs. cost of one mistake) | Engine, ledger | ✅ |
| **Demotion** | one failure, one over-edited turn, a forbidden attempt or a person's flag drops the class to L0 | Engine, ledger | ✅ |
| Only real yeses build trust | a person's approval or an earned allow is credited; what an agent's own settings let through is *observed*, never credited | Engine | ✅ |
| Hard denies | `rm -rf ~`, `curl … \| sh`, force-push to main, `sudo`, `DROP DATABASE` are never allowed, at any level | Engine | ✅ |
| Chained commands | judged by their riskiest part (`npm test && git push -f` is a force-push) | Engine | ✅ |
| Never fails open | if the gate is down, every hook defers to the agent's own settings | Hooks | ✅ |
| Resume | a person resumes a paused class at the level they choose | Dashboard | ✅ |

## 3. The end-of-turn check

| Feature | What it does | Where | Status |
|---|---|---|---|
| Over-editing | the turn's diff is graded 1-5 against the request (Jev when a key is set, size-and-spread rules otherwise); 2 or less sends the turn back with the files to revert | Agent, dashboard | ✅ |
| Tests, regression only | the repo's tests run in a throwaway worktree; failing tests are compared by name against the turn's own start, so pre-existing failures are not blamed | Agent, dashboard | ✅ |
| Rewind | a failed turn's changes are stashed (never deleted) and the tree returns to the turn's start | Dashboard (Rewind button) | ✅ |

## 4. The control layer

| Feature | What it does | Where | Status |
|---|---|---|---|
| Remediation | every denial and failure tells the agent what to undo (`git checkout -- package.json package-lock.json`, the checkpoint to rewind to), in the agent's own hook format | Agent | ✅ |
| **"This was wrong"** | flag any decision or turn: its class drops to L0 and the agent hears it on its next prompt | Dashboard | ✅ |
| Live levels + kill switch | levels animate as they change; **Freeze all** makes every action ask | Dashboard | ✅ |
| Subagents | the main agent and each subagent type keep their own license; subagents start capped at `[subagents] max`, can be denied by type, and are checked at their own stop | Engine | ✅ |
| Loop detection | 3 identical calls get guidance, 5 are denied, the same failure 3 times says "stop retrying", a file edited 4 times in a turn is sent back; a new prompt starts the count again | Agent | ✅ |
| Session digest | Jev judges a risky command against the session's goal and the policy (a bounded digest, never the raw transcript) and asks a person when unsure | Engine | ✅ |
| MCP tool classes | each MCP server is its own class (`mcp:github`); reads can earn L2, writes L1, merge / delete / deploy always ask; the policy can forbid or cap a tool | Engine, dashboard | ✅ |
| Policy as code | `.solo-license/policy.toml`, committed with the repo, can only make the agent ask more; `policy init` writes a starter | CLI, dashboard (Settings) | ✅ |

## 5. Money

| Feature | What it does | Where | Status |
|---|---|---|---|
| Budget caps | `[budget]` caps USD per session and per day, from the agent's own reported cost or an estimate from its transcript's tokens; past a cap only reading is allowed | Engine | ✅ |
| Budget page | today's spend per repo against the cap, recent sessions, who is stopped, **Resume** | Dashboard (Budget) | ✅ |
| `solo-license budget` | the same in the terminal | CLI | ✅ |
| Savings | prompts you did not answer, developer time and $ saved by earned autonomy | Dashboard | ✅ |

## 6. Evidence: neatlogs, Entire, cfo.ai

| Feature | What it does | Where | Status |
|---|---|---|---|
| **neatlogs traces** | one trace per turn: `turn.start → gate.allow/ask/deny → tool.ran/failed → remediation.sent → license.promote/demote → turn.end`; denials, demotions, loops and budget stops are error spans, so they show as incidents | neatlogs, dashboard links | ✅ with a key |
| Local trace mirror | without a key, every span is kept in the local database | CLI `explain` | ✅ |
| **Trace links** | each turn and decision in the dashboard and each change in the history links to its neatlogs trace | Dashboard | ✅ |
| **`solo-license explain [turn]`** | one turn's whole story: decisions, what the agent was told, license changes with ledger commits, the trace timeline, the Entire checkpoint, how to rewind | CLI | ✅ |
| **Entire checkpoints** | a failed turn is linked to the agent's last Entire checkpoint (`entire checkpoint explain <id>`) | Dashboard, CLI | ✅ with the Entire CLI |
| **License ledger** | every promote, demote, flag, resume and budget stop is a git commit: `git log -- ledger/license_ledger.jsonl` | git, Entire | ✅ |
| Entire Trails + Gates | every pull request in this repository went through Entire Trails and the Entire Gates check | Entire | ✅ |
| **cfo.ai model** | per-developer cost of asking every time vs. full access vs. Solo License, pricing, unit economics, runway: `make cfo` | `planning/cfo/` | ✅ |

## 7. Agents

| Agent | Wired through | Earns trust from a person's yes | Sends a bad turn back |
|---|---|---|---|
| Claude Code (also GLM via z.ai) | HTTP hooks / plugin | ✅ PermissionRequest | ✅ |
| OpenAI Codex CLI | command hooks | ✅ PermissionRequest | ✅ |
| **OpenCode** (Groq, GLM, free models) | plugin | 🧪 `permission.ask` | records it |
| Cursor | command hooks | observed | ✅ |
| Gemini CLI, Antigravity, Copilot CLI, Grok Build | command / HTTP hooks | observed | ✅ |
| Windsurf, Kiro, Cline | command hooks / scripts | observed | records it |

Every agent loses trust on a failure. "Observed" means the agent's hook fires on every call, so Solo License
cannot tell a person's yes from the agent's own settings; it never credits those calls.

## 8. Security

| Feature | What it does |
|---|---|
| Roles | `operator` < `approver` < `admin`; flags, resumes and rewinds need an approver |
| Local admin | made by `onboard`; the sign-in link carries the token in the URL hash only, and the dashboard removes it |
| Encrypted keys | neatlogs and Jev keys are stored encrypted; never shown back in full |
| Hook paths | paths a shell would expand are refused; hooks from other machines need `X-Solo-Hook-Key` |
| Background stop | never stops a process it cannot confirm is the gate (pid reuse) |
