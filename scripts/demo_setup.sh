#!/usr/bin/env bash
# Demo stage builder: run this BEFORE recording. Idempotent - run it again
# before every take and the demo starts from a clean slate.
#
#   bash scripts/demo_setup.sh
#
# What it does:
#   0. loads keys from .demo-keys.env (paste your neatlogs key there once)
#   1. stops every running Solo License gate
#   2. creates a FRESH demo database (trust starts at zero: the earn is live)
#      with your neatlogs + Jev keys pre-connected (the wizard opens green)
#   3. starts the gate detached on 127.0.0.1:8000 serving the dashboard
#   4. rebuilds ~/Desktop/solo-license-demo from demo/shop-api (git init,
#      NO hooks - the on-camera wizard writes them)
#   5. prints the ready state
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
DEMO_REPO="$HOME/Desktop/solo-license-demo"
DEMO_DB="data/demo.db"

# 0. keys (this file is gitignored; it is yours, on this machine only)
if [ ! -f .demo-keys.env ]; then
  cat > .demo-keys.env <<'EOF'
# Paste your keys here once; demo_setup.sh seeds them into the demo gate.
TYPESAFE_API_KEY=
NEATLOGS_API_KEY=
NEATLOGS_PROJECT=solo-license-demo
EOF
  echo "Created .demo-keys.env - paste NEATLOGS_API_KEY into it (TYPESAFE too if empty), then rerun."
  exit 1
fi
set -a; . ./.demo-keys.env; set +a
if [ -z "${NEATLOGS_API_KEY:-}" ] || [ -z "${TYPESAFE_API_KEY:-}" ]; then
  echo "Fill BOTH keys in .demo-keys.env first (neatlogs + Jev), then rerun."
  exit 1
fi

# 1. stop everything
"$PY" -m sololicense.cli stop >/dev/null 2>&1 || true
pkill -f "sololicense.cli serve" >/dev/null 2>&1 || true
pkill -f "uvicorn sololicense.api.app" >/dev/null 2>&1 || true
sleep 1

# 2. fresh demo database with the keys pre-connected
rm -f "$DEMO_DB" "$DEMO_DB-wal" "$DEMO_DB-shm"
"$PY" - <<EOF
from sololicense import credentials
creds, _ = credentials.ensure()
from sololicense.db.database import init_db
from sololicense.db.repositories import settings as srep
from sololicense.config import load_config
from dataclasses import replace
import os
config = replace(load_config(), db_path=__import__('pathlib').Path("$DEMO_DB"), demo_mode=True)
conn = init_db(config.db_path)
protected = srep.protect_secret_values({
    "neatlogs_api_key": "${NEATLOGS_API_KEY}",
    "typesafe_api_key": "${TYPESAFE_API_KEY}",
    "neatlogs_project": "${NEATLOGS_PROJECT:-solo-license-demo}",
}, creds["settings_encryption_key"])
srep.set_many(conn, protected)
conn.commit()
conn.close()
print("demo db ready, keys connected")
EOF

# 3. start the gate detached with the demo database
credentials_applied=1 SOLO_DEMO_MODE=1 SOLO_LICENSE_DB="$DEMO_DB" \
  "$PY" -m sololicense.cli serve --background --host 127.0.0.1 --port 8000 >/dev/null 2>&1 || true
for i in $(seq 1 20); do
  curl -sf http://127.0.0.1:8000/api/session >/dev/null 2>&1 && break
  sleep 1
done
curl -sf http://127.0.0.1:8000/api/session >/dev/null || { echo "gate did not start; see ~/.solo-license/gate.log"; exit 1; }

# 4. the demo repository: fresh, versioned, no hooks yet
rm -rf "$DEMO_REPO"
mkdir -p "$DEMO_REPO"
cp -R demo/shop-api/. "$DEMO_REPO/"
cd "$DEMO_REPO"
git init -q
git add -A
git commit -q -m "demo shop: two bugs and a test suite"
echo "demo repo ready: $DEMO_REPO"

# 5. ready state
echo
echo "=========================================="
echo " STAGE READY"
echo " gate       http://127.0.0.1:8000  (fresh trust, keys connected)"
echo " dashboard  http://127.0.0.1:8000/onboarding"
echo " demo repo  $DEMO_REPO (no hooks yet)"
echo " command for the recording:"
echo "   cd $DEMO_REPO"
echo "   uvx --python 3.13 --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license onboard"
echo "=========================================="
