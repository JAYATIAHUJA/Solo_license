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

## 4 · Entire Graph: what the recovery path touches

`entire graph` (plugin v0.4.0) indexes the repository and answers structural questions before a
change. Searching in plain words finds the recovery path first, with its covering tests:

```bash
entire graph search --repo . --query "recover a failed refund" --profile full
```

Top result: `RefundWorker._recover` (`sololicense/agent/worker.py:351`), then its caller
`RefundWorker._run_refund`; suggested check:
`python -m pytest tests/integration/test_agent_loop.py -k test_quiet_failure_is_recovered_and_the_customer_still_gets_a_true_reply`
(2 more covering tests: `test_worker_recovers_a_lost_stripe_refund`,
`test_quiet_failure_is_caught_recovered_and_still_demotes`).

```bash
entire graph impact --repo . --symbol _recover
```

```
Impact: RefundWorker._recover (sololicense/agent/worker.py:351) def=351 span=351-387 [method in RefundWorker]
Blast radius: 3 callers (2 direct, 1 transitive), 2 callees, 2 type consumers, 1 data flow, 25 co-change files, 12 siblings.
Callers (2 direct, 1 transitive; who breaks if behavior changes):
- RefundWorker._run_refund (sololicense/agent/worker.py:223, def :137)
- RefundWorker.run_refund (sololicense/agent/worker.py:118, def :96) [via RefundWorker._run_refund]
Callees (2; what it depends on):
- sololicense.services.verify
- RefundWorker._read (sololicense/agent/worker.py:322)
Type consumers: -> RefundRequest (sololicense/domain/models.py:35) [PARAM_TYPE, USES_TYPE]
Co-change coupling: sololicense/api/app.py (6 recent commits before the restructure), db/schema.sql (4), db/database.py (4), …
```

The blast radius is small and every caller goes through `run_refund`, which is why recovery could
be added — and switched off for the before/after benchmark with `worker.recovery_enabled` —
without touching the API, the licence service or the connectors.
