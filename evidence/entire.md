# How Solo License uses Entire

Entire is used in two ways: as the **audit trail of the product** (every change to what an agent may do
is a git commit, and a failed turn points at the agent's Entire checkpoint) and as the **record of how the
product was built** (checkpoints of the AI coding sessions, and Trails with Gates on every pull request).

## 1 · Every license change is a commit

The gate appends each promote, demote, flag, resume and budget stop to `ledger/license_ledger.jsonl` in
the ledger repository (`SOLO_LEDGER_REPO`) and commits it, with the reason and the neatlogs trace id.
The before/after replay's ledger is committed as evidence:
[`benchmarks/coding_ledger.jsonl`](benchmarks/coding_ledger.jsonl) and
[`benchmarks/coding_ledger_commits.txt`](benchmarks/coding_ledger_commits.txt), e.g.

```
15b0848 license(test-run@shop-api): promote L0 -> L1
553b8cf license(test-run@shop-api): promote L1 -> L2
```

On your machine:

```bash
git -C ~/.solo-license/ledger log --oneline -- ledger/license_ledger.jsonl
```

## 2 · A failed turn points at its Entire checkpoint

When a turn fails its end-of-turn check, the gate looks up the agent's last Entire checkpoint for that
session (`entire checkpoint list --json`, [`sololicense/coding/entire.py`](../sololicense/coding/entire.py))
and keeps it on the turn. The dashboard shows it next to **Rewind**, and the CLI prints it:

```bash
solo-license explain            # ... Entire checkpoint: entire checkpoint explain <id>
entire checkpoint explain <id>  # the prompts, transcript and files behind that turn
```

## 3 · Checkpoints of the build sessions

Commits made with Entire's git hooks carry an `Entire-Checkpoint:` trailer that links the code to the AI
session that produced it. For example, `408592b` (MCP tool classes, PR #59) carries
`Entire-Checkpoint: 01M4R1TMHGFAAGTADDEE7AX76V`.

```bash
git log --format='%h %s%n  %(trailers:key=Entire-Checkpoint,valueonly)' -5
entire checkpoint list
```

Some commits made from Git Bash on Windows have no trailer: Entire's `prepare-commit-msg` hook stalled
there, and those commits were completed without it.

## 4 · Trails and Gates on every pull request

Each pull request gets an **Entire Gates** check: approvals, CI checks, agent review findings, up to date.
Review findings were fixed before merging, for example a fail-open in the Windows background stop (a
process whose command line could not be read was treated as the gate; it is now left alone).

| Pull request | Trail |
|---|---|
| #54 Remediations on main and fixes from the live check | [trail 48](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/48) |
| #64 Hero shows the gate at work | [trail 58](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/58) |
| #65 `solo-license budget` | [trail 59](https://entire.io/gh/JAYATIAHUJA/Solo_license/trails/59) |

## 5 · Entire Graph: what a demotion touches

```bash
entire graph impact --repo . --symbol _fail
```

```
Impact: CodingGate._fail (sololicense/coding/gate.py:562) def=562 span=562-573 [method in CodingGate]
Blast radius: 8 callers (4 direct, 4 transitive), 6 callees, 2 type consumers, 2 data flows, ...
Callers: CodingGate.permission, CodingGate.tool_result, CodingGate.stop, CodingGate.subagent_stop, ...
Callees: effective_license, forget_patterns, CodingGate._change, _subagent_ceiling, _checkpoint_for, ...
```

Every path that takes trust away (a forbidden attempt, a failed tool, a failed turn, a subagent's stop)
goes through `_fail`, which is why one demotion rule holds for all eleven agents.
