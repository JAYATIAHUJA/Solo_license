# License ledger

The running app appends one line to `license_ledger.jsonl` **and makes one git commit** for every autonomy
change: promote, demote, flag, resume, budget stop. Commit messages name the action class and repo, the
`L<from> -> L<to>` transition and the reason; each line carries the neatlogs trace id.

Where it is written: the repository named by `SOLO_LEDGER_REPO` (`solo-license serve` uses
`~/.solo-license/ledger`; `.env.example` suggests `.` so a demo commits into this project).

```bash
git -C ~/.solo-license/ledger log --oneline -- ledger/license_ledger.jsonl
```

The ledger of the before/after replay is committed as evidence:
[`evidence/benchmarks/coding_ledger.jsonl`](../evidence/benchmarks/coding_ledger.jsonl) and its commits,
[`evidence/benchmarks/coding_ledger_commits.txt`](../evidence/benchmarks/coding_ledger_commits.txt).

The history of v1 (the refund agent that was removed in v3) is kept, unchanged, in
[`evidence/history/v1-refund-ledger.jsonl`](../evidence/history/v1-refund-ledger.jsonl).
