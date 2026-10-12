# How Solo License uses Entire

Entire is used in two ways: as the **audit trail of the product** (every change to what the agent
may do is a git commit) and as the **record of how the product was built** (checkpoints of the AI
coding sessions, and Trails that gate every pull request).

## 1 · Every permission change is a commit

The coding gate writes each promote / demote / restore / flag to
[`ledger/license_ledger.jsonl`](../ledger/license_ledger.jsonl) and commits it with the reason, the
run id and the neatlogs trace id. Entire can explain any of them.

```bash
git log --oneline -- ledger/license_ledger.jsonl    # every permission change, both eras
git show <sha> -- ledger/license_ledger.jsonl       # the reason, run and trace behind one change
entire checkpoint explain <sha>                     # the session behind it, when one is linked
```

The earliest entries are the v1 payments agent (the same trust engine, first domain); current
entries are the coding gate, e.g. `license(test-run@<repo>): promote L0 -> L1`.

## 2 · Checkpoints of the build sessions

Commits made with Entire's git hooks carry an `Entire-Checkpoint:` trailer that links the code to
the AI session (prompts, transcript, files) that produced it. Much of this repository was built
that way during the hackathon.

```bash
entire checkpoint list                              # the sessions behind the code
entire checkpoint explain <sha>                     # one commit's session
entire why sololicense/coding/gate.py               # provenance of the gate
```

Some earlier commits on these branches have no trailer: Entire's `prepare-commit-msg` hook stalled
when commits were made from Git Bash on Windows, and the commits were completed without it.
Commits made from PowerShell carry the trailer.

## 3 · Trails gate every pull request

Runners and Trails are enabled on the repository. Each pull request gets an **Entire Gates** check
(approvals, CI checks, agent findings, up to date). Every v3 pull request - the coding gate, the
plugin, budget guardrails, MCP tool classes, onboarding - went through the same gates, and several
carried review findings that were fixed before merging (injection in hook paths, trust credited
from an agent's own settings, regressions hidden by a cached verdict).

| Pull request (v1 era) | Trail |
|---|---|
| #8 Score autonomy policies on τ-bench retail | [trail 2](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/2) |
| #9 Ticket agent with recovery, Stripe/CSV connectors, inbox and earned trust | [trail 3](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/3) |
| #10 Evidence pack: before/after recovery with paired neatlogs traces | [trail 4](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/4) |

### Capturing evaluated Trail evidence

For judge evidence, capture a Trail only **after** its Entire Gates have evaluated the pushed
commit. A useful screenshot shows the Trail title and branch, the commit or diff, and populated
Gates for findings, checks, and up-to-date status. A Trail that was merged before evaluation may
show `Not checked`; that is audit history, but not runner evidence.

```bash
entire trail list --status any
entire trail create                 # create a Trail for the current evidence branch
git push origin <branch>            # runners trigger from the push
```

Wait for the Trail page to report the runner outcomes before merging. The expected clean result
for a documentation-only change is no findings, rather than an empty, unevaluated Gates panel.

## 4 · Entire Graph: what the trust engine touches

`entire graph` (plugin v0.4.0) indexes the repository and answers structural questions before a
change. The single most load-bearing function in the product is the one that changes a license
level, `Gate._change` in `sololicense/coding/gate.py`; the commands below map what it touches:

```bash
entire graph search --repo . --query "change a license level" --profile full
entire graph impact --repo . --symbol _change
python -m pytest tests/test_coding_gate.py -q       # the covering tests graph search suggests
```

Run them in a checkout with the Entire CLI installed; `graph impact` reports callers, callees,
type consumers and co-change coupling for `_change`, and the pytest command above is the suite
that covers every promote / demote / restore path the function implements.
