#!/usr/bin/env bash
# Machine-check every claim in evidence/claims.json. Prints PASS/FAIL per
# claim and exits nonzero if any claim fails. The CI claims job runs this
# on every push.
#
#   bash scripts/verify.sh            # uses .venv if present, else python3
#   PYTHON=python3 bash scripts/verify.sh
#
# Read-only with respect to committed files: claims run tests and builds
# (gitignored artifacts only). No network, no secrets.

set -u
cd "$(dirname "$0")/.."

if [ -z "${PYTHON:-}" ]; then
  if [ -x ".venv/bin/python" ]; then
    PYTHON=.venv/bin/python
  else
    PYTHON=python3
  fi
fi
export PYTHON

CLAIMS="${1:-evidence/claims.json}"
if [ ! -f "$CLAIMS" ]; then
  echo "claims file not found: $CLAIMS" >&2
  exit 2
fi

LOGDIR=$(mktemp -d "${TMPDIR:-/tmp}solo-verify.XXXXXX") || exit 2
trap 'rm -rf "$LOGDIR"' EXIT

# One interpreter spawn reads the whole file and emits `id<TAB>command`
# lines, so adding claims costs nothing at startup.
pass=0
fail=0
failed_ids=""

while IFS=$'\t' read -r id cmd; do
  [ -n "$id" ] || continue
  if bash -c "$cmd" > "$LOGDIR/$id.log" 2>&1; then
    echo "PASS  $id"
    pass=$((pass + 1))
  else
    echo "FAIL  $id   (last output: $(tail -c 200 "$LOGDIR/$id.log" | tr "\n" " "))"
    fail=$((fail + 1))
    failed_ids="$failed_ids $id"
  fi
done < <("$PYTHON" -c '
import json, sys
for c in json.load(open(sys.argv[1]))["claims"]:
    print(c["id"] + "\t" + c["command"])
' "$CLAIMS")

echo
echo "$pass passed, $fail failed"
if [ "$fail" -gt 0 ]; then
  echo "failed claims:$failed_ids"
  exit 1
fi
