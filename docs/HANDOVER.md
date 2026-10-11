# Solo License - Handover PRD

*12 Oct 2026 · neatHack submission window: **Mon 12 Oct, 7:00-11:55 PM IST** · state of `main` after PR #38*

This is the single document to pick the project up from: what the product is, what is built and
merged, how to run and demo it, what is verified and what is not, and what to do next.

---

## 1. Product in one paragraph

**Solo License makes a coding agent earn the right to act without asking.** It sits in the
agent's hooks (Claude Code, Codex, Cursor, Gemini CLI, Antigravity, Copilot CLI, Grok Build,
Windsurf, Kiro, Cline, OpenCode). Each kind of action - run the tests, install a package, push -
is auto-approved only once it has proven itself **in that repository**, from verified results.
One failure, an over-edited turn, or a forbidden action takes it back. A team decides how far it
may ever go through a policy file committed with the code. Every change of trust is a git commit.

*Earned. Revocable. Priced.*

### Positioning
- **Problem:** developers choose between "ask before every change" (approval fatigue, rubber-stamping)
  and "full access" (force-pushes, reverted commits, 50-line diffs for 1-line bugs).
- **vs Claude Code auto mode:** auto mode asks *"is this action dangerous?"* per call. Solo License
  asks *"has this agent earned this kind of action in this repo, and did it work?"* - outcome-based,
  revocable, auditable, works across agents. Complementary, not a replacement.
- **Why hooks, not MCP:** an MCP tool is optional for the model; hooks are run by the agent harness
  and cannot be skipped. (Mentor's advice in the 11 Oct meeting.)
- **Side feature:** the original refund agent ("Payments agent") - same engine, earns the right to
  refund customers from Stripe read-backs. Kept, but not the story.

---

## 2. How it works

### Three answers, everywhere
| Answer | When | Effect |
|---|---|---|
| allow | class earned in this repo | no prompt |
| deny | hard-deny list, repo policy deny, or turn sent back | agent gets a reason; class drops to L0 |
| defer | not earned yet | the agent's **own** settings decide (as if Solo License were not installed) |

The gate never widens what an agent may do beyond what it earned. If the gate is down every hook
defers - an outage never becomes an "allow".

### Trust model (`sololicense/coding/`)
- Key: **(repository, action class)** - `read`, `test-run`, `lint-format`, `build`, `file-edit`,
  `git-local`, `install-dep`, `network-fetch`, `git-remote`, `file-delete`, `deploy`, `db-migrate`,
  `unknown` (`actions.py`). A chain is judged by its riskiest part.
- Levels: **L0** asks · **L1** runs command families a person approved here · **L2** whole class.
- Promotion needs **both** a floor of verified runs and the economic bound
  `P(failure) × cost of a mistake < developer time an approval costs` (`ladder.py` + `domain/trust.py`).
- **Only a person's yes (Claude Code / Codex permission prompt) or an earned allow builds trust.**
  Actions an agent's own settings let through are `observed`, never credited. Failures always count.

### Decision flow
```
agent hook → POST /api/hooks/{agent}/{native_event}     (Claude Code: /api/hooks/{event})
  → agents.normalize → gate.permission:
      classify (rules; Jev only for unknown commands)
      → hard-deny? → repo policy deny? → frozen? → effective level vs ceiling → allow / deny / defer
  → agents.render (the agent's own JSON / exit code)
Stop hook → gate.stop → verify.check_turn:
      diff vs request (Jev or size rule; ≤2/5 = over-editing, sent back)
      tests (regression only, test by test vs the turn's own start, in a worktree with deps)
  → verified evidence → maybe promote   |   failed → demote + Entire checkpoint + rewindable
```

### Who decides privileges (policy, `policy.py`) - strictest wins
1. Built-in ceilings + hard-deny list (code).
2. Team file `.solo-license/policy.toml`, committed (ceilings, deny commands/paths, freeze).
   `solo-license policy init` writes a starter. A broken file **freezes** the repo.
3. This machine (Settings → Coding policy), per repo or all; can only tighten. Kill switch on the dashboard.
Every policy change is a ledger commit; every decision records the policy digest.

### Where things are stored
| What | Where |
|---|---|
| Hook wiring | each agent's config in the repo (`init` writes it) + `.solo-license/hook.py` shim |
| Licenses, decisions, turns, settings, encrypted keys | SQLite (`~/.solo-license/solo_license.db` with `solo-license serve`) |
| Promote / demote / resume / policy changes | git ledger (`~/.solo-license/ledger`, or `SOLO_LEDGER_REPO`) |
| Team policy | `.solo-license/policy.toml` in the repo |

---

## 3. What is built and merged (this hackathon)

| PR | What |
|---|---|
| #24 | Coding gate: earn/lose autonomy per action class through Claude Code hooks |
| #25 | End-of-turn check: over-editing + tests before changes count |
| #26 | Claude Code plugin, installer, coding dashboard API |
| #27 | Entire: failed turn → checkpoint; person can rewind (changes stashed) |
| #28 | Web app opens on the coding agent: licenses, turns, decisions, resume, rewind |
| #29 | Landing page tells the coding-agent story |
| #30 | cfo.ai business plan + model for the coding product |
| #31 | Tests: only regressions count (baseline per turn, test-by-test, deps linked) |
| #32 | **One gate for 11 agents**, `solo-license` CLI, one-line install, Jev key in Settings |
| #33 | Coding-first setup guide (`/onboarding`), landing terminal scene + install section |
| #34 | Claude route cannot pose as another agent |
| #35 | Demo repo `demo/shop-api` + before/after replay benchmark |
| #36 | README rewritten coding-first |
| #37 | Policy controls: team file, machine settings that only tighten, kill switch |
| #38 | Deny paths in commands matched as paths (not substrings) + this handover |

Earlier (#1-#22): the payments/refund agent, τ-bench scoring, recovery benchmark, neatlogs depth, CI.

Every PR went through **CI (backend + frontend) and Entire Gates** (approvals + AI review findings)
before merge. Review findings fixed along the way: injection via install paths / gate URL, SQL column
names, route validation, trust credited from an agent's own settings, spoofing via the Claude route,
regressions hidden by a cached verdict, missing deps in the baseline worktree, path traversal in policy.

**Tests:** 310 backend (`python -m pytest`), 11 frontend, `vite build` green.

---

## 4. Run it

```bash
# one line, any agent (works from GitHub main)
uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license init --agent auto
uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license serve

# from a clone
pip install -r requirements.txt
uvicorn sololicense.api.app:app --port 8000
npm --prefix frontend install && npm --prefix frontend run dev     # http://127.0.0.1:5174
make coding-demo        # ../shop-api-demo with hooks installed
make coding-benchmark   # evidence/benchmarks/coding_before_after.md
make cfo                # financial models
```

Optional keys (Settings or setup guide): `TYPESAFE_API_KEY` (Jev), `NEATLOGS_API_KEY`.

---

## 5. Demo script (2:30-3:00, live)

| Time | Show | Say |
|---|---|---|
| 0:00 | "Ask before changes" vs "Full access" | Two bad options |
| 0:20 | Landing (002) terminal scene | Auto mode asks *is this dangerous*; we ask *has it earned this, here, and did it work* |
| 0:35 | `/onboarding`: pick agent, copy one-liner | One line, any agent |
| 0:50 | Claude Code in `shop-api-demo`: "run the tests" ×3 → 4th runs without a prompt | Earned per action class |
| 1:20 | "fix the bug in cart.js" → agent also rewrites `format.js` → sent back → reverted → verified | Over-editing is a trust signal |
| 1:50 | "ship it" → force-push denied; Settings → policy `.env` deny; Freeze all | Hard limits + team policy + kill switch |
| 2:20 | Dashboard + Permission history (ledger commits) + benchmark table | 21 → 11 prompts, 157 → 0 over-edited lines, 3 force-pushes denied |
| 2:45 | cfo.ai plan | $1,017 saved per dev/month vs ask-every-time |

---

## 6. Evidence for judges (rubric)

| Criterion (weight) | Evidence |
|---|---|
| The agent (30) | Gate plans/gates/verifies/recovers per turn: `sololicense/coding/`; live Claude Code run |
| neatlogs + Entire + cfo.ai (25) | one neatlogs trace per turn (benchmark traces); Entire Trails on every PR + checkpoints on failed turns + ledger commits; `planning/cfo/coding_business_model.md` |
| Demo video (20) | script above |
| Building in public (15) | posts with #neatHack (team) |
| Usefulness & originality (10) | outcome-based trust across 11 agents; over-editing as a trust signal |

Required items: before/after (`evidence/benchmarks/coding_before_after.md`), a failure and recovery
(over-edit sent back → reverted → verified; force-push denied → class demoted), commits during the
hackathon (`git log --since=2026-10-10`).

---

## 7. Known limits (state them plainly)

- **Only Claude Code has been run end to end with a live agent.** The other 10 agents are wired from
  their docs and tested with their documented payloads; not yet tried in the real tools.
- Unverified in vendor docs: Grok's HTTP response format, Gemini "ask", OpenCode plugin field names,
  Antigravity `Stop` config shape, whether Copilot accepts plain-http localhost (we use command hooks).
- Agents whose hooks fire on every action (all but Claude Code / Codex) can only **lose** trust
  through Solo License; earning happens through a person's approval in Claude Code / Codex (trust is per
  repo, so it is shared).
- Windsurf, Kiro, Cline, OpenCode cannot send a turn back - those turns are recorded and shown only.
- Jev is optional and early access; without a key, rules decide. Its score format was inferred.
- The gate is local per machine; there is no shared team server yet.
- Payments agent: τ-bench is a counterfactual replay; the Stripe connector is tested against a mock.

---

## 8. Next steps (priority order)

1. **Record the demo** on a clean machine using `make coding-demo` + Claude Code (section 5).
2. Try Codex and Cursor live with `solo-license init --agent codex|cursor`; fix any payload mismatch
   in `agents.py` (one place).
3. `solo-license init --global` (user-level hooks for every repo) and `serve --background` / autostart.
4. Shared team gate (Team plan): one URL + hook key, shared ledger and policy.
5. Screenshots of the new dashboard / setup guide for the README (`evidence/assets/screens/`).
6. Post the before/after numbers and the terminal scene clip with #neatHack.

---

## 9. Working rules for this repo

- One branch + PR per change; merge only after **CI and Entire Gates** are green (approvals + findings).
- Commits authored by the repo owner; no AI co-author trailers.
- Paste Entire findings into the session; fix on the branch, push, re-run the gate.
