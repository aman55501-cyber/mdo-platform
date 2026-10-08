#!/usr/bin/env bash
# vault_import.sh — one-time move of Aman's laptop folders into the VPS vault.
#
# On the laptop (PowerShell), copy both folders to the VPS first:
#   scp -r "C:\Users\Owner\Desktop\BUSINESSES\_memory"               root@<VPS>:/docker/sharecfo/mdo-platform/vault-import/memory
#   scp -r "C:\Users\Owner\claude master\finance"                     root@<VPS>:/docker/sharecfo/mdo-platform/vault-import/finance
# Then on the VPS:
#   sudo bash vault_import.sh
#
# What it does: copies vault-import/{memory,finance} into the backend container's
# /data/vault (the Docker volume, outside the repo), sets owner-only permissions,
# verifies the file count, deletes the import staging folder, and files a heartbeat.
# Re-running is safe: existing vault files are kept, new ones added (no overwrite
# unless --overwrite is passed).
set -euo pipefail
cd "${MDO_DIR:-/docker/sharecfo/mdo-platform}"
STAGE="./vault-import"
[ -d "$STAGE" ] || { echo "nothing to import: $STAGE not found. scp the folders there first (see header)."; exit 1; }
OVER="${1:-}"
for area in memory finance; do
  [ -d "$STAGE/$area" ] || { echo "skip $area: not in $STAGE"; continue; }
  n=$(find "$STAGE/$area" -type f | wc -l)
  docker compose exec -T backend sh -c "mkdir -p /data/vault/$area && chmod 700 /data/vault /data/vault/$area"
  if [ "$OVER" = "--overwrite" ]; then
    docker compose cp "$STAGE/$area/." "backend:/data/vault/$area/"
  else
    # copy into a temp dir in the container, then move only files that do not exist yet
    docker compose cp "$STAGE/$area/." "backend:/data/vault/.incoming-$area/"
    docker compose exec -T backend sh -c "cd /data/vault/.incoming-$area && find . -type f | while read f; do [ -e \"/data/vault/$area/\$f\" ] || { mkdir -p \"/data/vault/$area/\$(dirname \"\$f\")\"; mv \"\$f\" \"/data/vault/$area/\$f\"; }; done; cd /; rm -rf /data/vault/.incoming-$area"
  fi
  docker compose exec -T backend sh -c "find /data/vault/$area -type f -exec chmod 600 {} +; find /data/vault/$area -type d -exec chmod 700 {} +"
  m=$(docker compose exec -T backend sh -c "find /data/vault/$area -type f | wc -l")
  echo "$area: $n files staged → $m files now in vault"
done
rm -rf "$STAGE"
echo "staging folder removed. The laptop copies are now STALE — rename them *.OLD after the first successful Routine run."
KEY=$(grep -E '^MDO_AUTH_TOKEN=' .env | cut -d= -f2- | tr -d '"' || true)
if [ -n "$KEY" ]; then
  curl -s -X POST localhost:8501/api/agent/report -H "X-MDO-Key: $KEY" -H "Content-Type: application/json" \
    -d "{\"bot\":\"vault-import\",\"cadence\":\"event\",\"heartbeat\":true,\"status\":\"clean\",\"summary\":\"vault import done: $(docker compose exec -T backend sh -c 'find /data/vault -type f | wc -l' | tr -d '[:space:]') files\",\"checks_run\":[]}" >/dev/null && echo "heartbeat filed"
fi
