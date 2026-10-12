# Evidence

Everything here is produced by the real system and can be regenerated.

| File | How to regenerate | What it shows |
|---|---|---|
| [`benchmarks/coding_before_after.md`](benchmarks/coding_before_after.md) / [`.json`](benchmarks/coding_before_after.json) | `make coding-benchmark` (or `python -m scripts.coding_demo benchmark`) | One scripted coding session (3 days x 5 requests in [`demo/shop-api`](../demo/shop-api)) replayed through the real gate: prompts answered, actions earned, force-pushes denied, over-edits sent back |
| [`benchmarks/coding_ledger.jsonl`](benchmarks/coding_ledger.jsonl) | same command | The license ledger that replay wrote: one line per promotion or demotion |
| [`benchmarks/coding_ledger_commits.txt`](benchmarks/coding_ledger_commits.txt) | same command | The git commits of that ledger (`git log -- ledger/license_ledger.jsonl` in the replay's ledger repo) |
| [`entire.md`](entire.md) | - | How Entire is used: ledger commits, checkpoints of failed turns and of the build, Trails and Gates on every PR, Entire Graph |
| [`assets/screens/`](assets/screens) | screenshots | The app and the cfo.ai scorecard |
| [`history/v1-refund-ledger.jsonl`](history/v1-refund-ledger.jsonl) | - | The ledger of v1 (the refund agent removed in v3), kept unchanged as history |

Traces: with `NEATLOGS_API_KEY` set, every turn of the replay is sent to neatlogs; without it they are kept in
the local database, and the report says so.

Checks that pin the security behaviour: [`tests/test_security_regressions.py`](../tests/test_security_regressions.py)
(redirects into files are edits, writes to credentials are denied, every way to force-push main is denied,
three approved runs earn `npm test`, a gate that is down never allows).
