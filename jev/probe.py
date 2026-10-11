#!/usr/bin/env python3
"""Fire the Solo License decision payloads at the Jev (TypeSafe System One) API.

Jev is a discriminative model: it returns calibrated probability
distributions, not prose. That is exactly the shape of Solo License's
gate decisions (risk class, change type, intent) - this script exists to
answer one question: *is Jev good enough to power those gates?*

Usage:
    TYPESAFE_API_KEY=ts_... python3 jev/probe.py            # official API
    JEV_API_KEY=... JEV_ENDPOINT=https://jev-ai.pro/api/v1/systemone \
        python3 jev/probe.py                                  # playground API

Without a key it prints one ready-to-paste curl per payload, so every
input can also be tested by hand in the playground at jev-ai.pro.
The key is read from the environment only; it is never logged or echoed.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).parent
INPUTS = HERE / "inputs"
OFFICIAL_ENDPOINT = "https://api.typesafe.ai/v1/systemone"


def endpoint_and_key() -> tuple[str, str]:
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY", "")
    url = os.environ.get("JEV_ENDPOINT", OFFICIAL_ENDPOINT)
    return url, key


def payloads() -> list[pathlib.Path]:
    return sorted(INPUTS.rglob("*.json"))


def run(url: str, key: str, path: pathlib.Path) -> dict:
    body = path.read_bytes()
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def show(path: pathlib.Path, answers: dict) -> None:
    print(f"\n=== {path.relative_to(INPUTS)} ===")
    for name, answer in answers.items():
        kind = answer.get("type")
        if kind == "choice":
            print(f"  {name}: {answer.get('choice')!r}"
                  f"  confidence={answer.get('confidence')}"
                  f"  p={answer.get('probabilities')}")
        elif kind == "score":
            print(f"  {name}: {answer.get('score')}"
                  f"  confidence={answer.get('confidence')}")
        elif kind == "noul":
            print(f"  {name}: {answer.get('noul')}")
        else:
            print(f"  {name}: {answer}")


def curl_for(path: pathlib.Path, url: str) -> None:
    print(f"\n=== {path.relative_to(INPUTS)} ===\n"
          f"curl -X POST {url} \\\n"
          f"  -H 'Authorization: Bearer $TYPESAFE_API_KEY' \\\n"
          f"  -H 'Content-Type: application/json' \\\n"
          f"  -d @{path}")


def main() -> int:
    url, key = endpoint_and_key()
    files = payloads()
    if not files:
        print("no payloads found under", INPUTS, file=sys.stderr)
        return 1
    if not key:
        print(f"No API key set - printing paste-ready curls against {url}")
        for path in files:
            curl_for(path, url)
        return 0
    failures = 0
    for path in files:
        try:
            report = run(url, key, path)
            show(path, report.get("answers", report))
        except urllib.error.HTTPError as error:
            failures += 1
            detail = error.read(300).decode("utf-8", "replace")
            print(f"\n=== {path.relative_to(INPUTS)} === HTTP {error.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as error:
            failures += 1
            print(f"\n=== {path.relative_to(INPUTS)} === unreachable: {error}")
    print(f"\n{len(files) - failures}/{len(files)} payloads answered")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
