"""Run the prompt-injection suite and write evidence/benchmarks/injection.{md,json}."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from sololicense.bench.injection import markdown, run_suite, summarize

_ARTIFACTS = Path(__file__).resolve().parents[1] / "evidence" / "benchmarks"


def main() -> None:
    results = run_suite()
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = {"summary": summarize(results), "results": [asdict(r) for r in results]}
    (_ARTIFACTS / "injection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (_ARTIFACTS / "injection.md").write_text(markdown(results), encoding="utf-8")
    print(f"Wrote {_ARTIFACTS / 'injection.md'}: {report['summary']}")


if __name__ == "__main__":
    main()
