#!/usr/bin/env bash
# Machine-check every claim in evidence/claims.json. Prints PASS/FAIL per
# claim and exits nonzero if any claim fails. CI runs this on every push.
#
#   bash scripts/verify.sh            # uses .venv if present, else python3
#   PYTHON=python3 bash scripts/verify.sh
#
# No network, no secrets, no special privileges required.

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

# Read the claims with the interpreter we will use to test them, so the
# checker itself cannot drift from the environment it checks.
mapfile -t IDS < <("$PYTHON" -c '
import json, sys
for c in json.load(open(sys.argv[1]))["claims"]:
    print(c["id"])
' "$CLAIMS")

pass=0
fail=0
failed_ids=()

for id in "${IDS[@]}"; do
  cmd=$("$PYTHON" -c '
import json, sys
claims = json.load(open(sys.argv[1]))["claims"]
c = next(c for c in claims if c["id"] == sys.argv[2])
print(c["command"])
' "$CLAIMS" "$id")

  if bash -c "$cmd" > /tmp/solo-verify-"$id".log 2>&1; then
    echo "PASS  $id"
    pass=$((pass + 1))
  else
    echo "FAIL  $id   (last output: $(tail -c 200 /tmp/solo-verify-"$id".log | tr "\n" " "))"
    fail=$((fail + 1))
    failed_ids+=("$id")
  fi
done

echo
echo "$pass passed, $fail failed"
if [ "$fail" -gt 0 ]; then
  echo "failed claims: ${failed_ids[*]}"
  exit 1
fi
