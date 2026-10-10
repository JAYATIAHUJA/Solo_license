# License ledger

`license_ledger.jsonl` is written and committed **by the running app** — one
line and one git commit per autonomy change (promote / demote / restore).

That commit history is the Entire-compatible checkpoint trail: each commit
message names the task class, the `L<from> -> L<to>` transition, the reason,
and the originating run + trace id. Point Entire's graph/explain at these
commits to walk how a task class earned and lost its license.

Inspect the trail directly with:

```bash
git log --oneline -- ledger/license_ledger.jsonl
```
