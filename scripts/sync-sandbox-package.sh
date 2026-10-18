#!/usr/bin/env bash
# Pull lv.proc.it_agreement.monitoring from the private ProcessGit repo
# (in-perimeter) and (re)deploy it as a flat .uapf to the OpenLegal uapf-engine.
set -euo pipefail
ROOT="/home/rihards/OpenLegal-work"
cd "$ROOT"
set -a; . ./.env; set +a
: "${PROCESSGIT_TOKEN:?PROCESSGIT_TOKEN not set in .env}"
GITEA="${PROCESSGIT_INTERNAL_URL:-http://localhost:18080}"
HOST="${GITEA#http://}"; HOST="${HOST#https://}"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
git clone -q "http://oauth2:${PROCESSGIT_TOKEN}@${HOST}/sandbox/agreement-monitoring.git" "$TMP/repo"
python3 - "$TMP/repo" "$ROOT/uapf-packages/lv.proc.it_agreement.monitoring.uapf" <<'PY'
import sys, os, zipfile
src, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(src):
        if ".git" in root.split(os.sep): continue
        for f in files:
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, src))
print("built", out, "from ProcessGit sandbox/agreement-monitoring")
PY
docker restart openlegal-uapf-engine >/dev/null
echo "engine restarting; package redeployed from ProcessGit"
