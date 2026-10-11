# How Solo License uses Entire

Entire is used in two ways: as the **audit trail of the product** (every change to what the agent
may do is a git commit) and as the **record of how the product was built** (checkpoints of the AI
coding sessions, and Trails that gate every pull request).

## 1 · Every permission change is a commit

The licence service writes each promote / pause / resume to
[`ledger/license_ledger.jsonl`](../ledger/license_ledger.jsonl) and commits it with the reason, the
run id and the neatlogs trace id. Entire can explain any of them.

```bash
git log --oneline -- ledger/license_ledger.jsonl    # 31 commits at the time of writing
git show <sha> -- ledger/license_ledger.jsonl       # the reason, run and trace behind one change
entire checkpoint explain <sha>                     # the session behind it, when one is linked
```

## 2 · Checkpoints of the build sessions

Commits made with Entire's git hooks carry an `Entire-Checkpoint:` trailer that links the code to
the AI session (prompts, transcript, files) that produced it.

| Commit | Checkpoint |
|---|---|
| `87ab58d` fix(app): evidence page tells the recovery story; screenshots for the README | `01M4N1QZY7KGEB08SN5PEKZR1C` |

```bash
entire checkpoint list
entire checkpoint explain 87ab58d
entire why sololicense/agent/worker.py:351      # provenance of one line
```

Some earlier commits on these branches have no trailer: Entire's `prepare-commit-msg` hook stalled
when commits were made from Git Bash on Windows, and the commits were completed without it.
Commits made from PowerShell carry the trailer.

## 3 · Trails gate every pull request

Runners and Trails are enabled on the repository. Each pull request gets an **Entire Gates** check
(approvals, CI checks, agent findings, up to date):

| Pull request | Trail |
|---|---|
| #8 Score autonomy policies on τ-bench retail | [trail 2](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/2) |
| #9 Ticket agent with recovery, Stripe/CSV connectors, inbox and earned trust | [trail 3](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/3) |
| #10 Evidence pack: before/after recovery with paired neatlogs traces | [trail 4](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/4) |
