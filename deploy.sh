#!/usr/bin/env bash
# One-command deploy for the merged MDO + Shares CFO stack.
#
#   ./deploy.sh              # check, migrate, deploy, verify
#   ./deploy.sh --check      # check only, change nothing
#
# Written to be run repeatedly. Every step checks whether it is already done, so a
# re-run after fixing one problem does not redo the rest.
#
# What it will NOT do without you: overwrite an existing .env, delete a volume, or
# start anything while the old stack still holds ports 80/443.

set -uo pipefail

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
ok()   { echo "  ${GRN}OK${OFF}    $*"; }
warn() { echo "  ${YEL}WARN${OFF}  $*"; }
bad()  { echo "  ${RED}FAIL${OFF}  $*"; FAILED=1; }
step() { echo; echo "${DIM}── $* ─────────────────────────────────────────${OFF}"; }

FAILED=0
cd "$(dirname "$0")" || exit 1

step "1. Preconditions"

command -v docker >/dev/null || { bad "docker not found"; exit 1; }
ok "docker present"
docker compose version >/dev/null 2>&1 || { bad "docker compose v2 not available"; exit 1; }
ok "docker compose available"
[ -f docker-compose.yml ] || { bad "run this from the repo root"; exit 1; }
ok "in the repo root ($(pwd))"

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
echo "        branch: $BRANCH  commit: $(git rev-parse --short HEAD 2>/dev/null || echo '?')"

step "2. Environment file"

if [ ! -f .env ]; then
  bad ".env missing — copy .env.example and fill it in, then re-run"
  echo "        cp .env.example .env && nano .env"
  exit 1
fi
ok ".env present"

# Never silently clobber it.
BACKUP=".env.backup-$(date +%F-%H%M)"
if [ "$CHECK_ONLY" = "0" ]; then
  cp .env "$BACKUP" && ok "backed up .env -> $BACKUP"
fi

# Keys that must carry a real value for the merged stack to work at all.
need_key() {
  local key="$1" why="$2"
  local val
  val=$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ')
  if [ -z "$val" ]; then
    bad "$key is empty — $why"
  elif echo "$val" | grep -qiE 'your_|make_up_|REPLACE|example\.com|yourdomain'; then
    bad "$key still holds a placeholder ($val) — $why"
  else
    ok "$key set"
  fi
}
want_key() {
  local key="$1" why="$2"
  local val
  val=$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ')
  [ -z "$val" ] && warn "$key is empty — $why" || ok "$key set"
}

need_key CFO_API_TOKEN     "Shares CFO requires it and the backend presents it; one value, both halves"
need_key DOMAIN            "Caddy needs it for TLS, and HDFC's registered redirect points at it"
need_key ANTHROPIC_API_KEY "the Brain and the agents run on it"
want_key MDO_APP_URL       "without it a push has no one-tap link"
want_key CFO_NTFY_TOPIC    "no phone push channel configured — the feed will be silent"
want_key MDO_AUTH_TOKEN    "the app and API are unprotected without it"
want_key ALERT_WHATSAPP_TO "WhatsApp alerts disabled"

# The single-hostname routing only works if these agree.
DOM=$(grep -E '^DOMAIN=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ')
for k in MDO_APP_URL CFO_PUBLIC_URL NEXT_PUBLIC_API_URL; do
  v=$(grep -E "^${k}=" .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ')
  if [ -n "$v" ] && [ -n "$DOM" ] && ! echo "$v" | grep -q "$DOM"; then
    warn "$k ($v) does not contain DOMAIN ($DOM) — deep links or the OAuth handoff may miss"
  fi
done

step "3. VPN profiles (optional — site data only)"

for site in hotel vedanta; do
  f="vpn/$site/client.ovpn"
  if [ ! -f "$f" ]; then
    warn "$f missing — $site site data unavailable (everything else still works)"
  elif [ ! -s "$f" ]; then
    bad "$f is EMPTY — the transfer did not complete"
  elif ! grep -q '</key>' "$f" || ! grep -q '^remote ' "$f"; then
    bad "$f looks truncated ($(wc -c < "$f") bytes; expected ~3.9 KB)"
  else
    ok "$f complete ($(wc -c < "$f") bytes)"
  fi
done

step "4. Shares CFO data volumes"

# Docker prefixes volume names with the project directory. Coming from the old
# split stacks, the merged project creates EMPTY volumes and the uploaded Screener
# and MProfit exports look deleted. Copy them across before first start.
PROJECT=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')
for vol in sharescfo_state sharescfo_screener sharescfo_mprofit; do
  NEW="${PROJECT}_${vol}"
  if docker volume inspect "$NEW" >/dev/null 2>&1; then
    ok "$NEW exists"
    continue
  fi
  OLD=$(docker volume ls -q | grep -E "_${vol}$" | grep -v "^${PROJECT}_" | head -1)
  if [ -z "$OLD" ]; then
    echo "        ${DIM}$NEW will be created empty (no prior volume found)${OFF}"
    continue
  fi
  if [ "$CHECK_ONLY" = "1" ]; then
    warn "would copy $OLD -> $NEW"
    continue
  fi
  echo "        copying $OLD -> $NEW ..."
  if docker run --rm -v "$OLD":/from -v "$NEW":/to alpine \
       sh -c "cd /from && cp -a . /to" >/dev/null 2>&1; then
    ok "migrated $OLD -> $NEW"
  else
    bad "could not copy $OLD -> $NEW (re-upload Screener/MProfit exports, or retry)"
  fi
done

step "5. Port conflicts"

for p in 80 443; do
  HOLDER=$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E ":${p}->" | grep -v "^${PROJECT}-" | awk '{print $1}' | head -1)
  if [ -n "$HOLDER" ]; then
    if [ "$CHECK_ONLY" = "1" ]; then
      warn "port $p held by '$HOLDER' (the old stack) — it must be stopped"
    else
      echo "        port $p held by '$HOLDER' — stopping that stack"
      OLDDIR=$(docker inspect "$HOLDER" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null)
      if [ -n "$OLDDIR" ] && [ -d "$OLDDIR" ] && [ "$OLDDIR" != "$(pwd)" ]; then
        (cd "$OLDDIR" && docker compose down) && ok "stopped the stack in $OLDDIR"
      else
        docker stop "$HOLDER" >/dev/null && ok "stopped container $HOLDER"
      fi
    fi
  else
    ok "port $p free"
  fi
done

if [ "$FAILED" = "1" ]; then
  echo
  echo "${RED}Stopping — fix the FAIL lines above and run again.${OFF}"
  echo "Nothing was started."
  exit 1
fi

if [ "$CHECK_ONLY" = "1" ]; then
  echo
  echo "${GRN}Checks passed.${OFF} Run ./deploy.sh to deploy."
  exit 0
fi

step "6. Build and start"

docker compose up -d --build || { echo "${RED}compose up failed${OFF}"; exit 1; }
echo
docker compose ps

step "7. Verify"

echo "        waiting for the backend to answer ..."
for i in $(seq 1 30); do
  curl -sf localhost:8501/api/health >/dev/null 2>&1 && break
  sleep 3
done

probe() {
  local label="$1" url="$2" want="$3"
  local body; body=$(curl -sf --max-time 12 "$url" 2>/dev/null)
  if [ -z "$body" ]; then
    bad "$label — no response from $url"
  elif [ -n "$want" ] && ! echo "$body" | grep -q "$want"; then
    warn "$label — responded, but '$want' not found: $(echo "$body" | head -c 160)"
  else
    ok "$label"
  fi
}

probe "backend health"      "localhost:8501/api/health"        ""
probe "decision feed"       "localhost:8501/api/feed"          "counts"
probe "site links"          "localhost:8501/api/sites"         "tunnels"
probe "Shares CFO health"   "localhost:8000/healthz"           ""

CAP=$(curl -sf --max-time 20 localhost:8501/api/capital/summary 2>/dev/null)
if echo "$CAP" | grep -q '"connected": *true'; then
  ok "capital bridge live — the two halves are talking"
elif echo "$CAP" | grep -qi 'not authenticated\|logged out'; then
  warn "capital bridge reachable but brokers are logged out — run the HDFC login"
else
  warn "capital bridge not returning data: $(echo "$CAP" | head -c 160)"
fi

step "8. What to do next"

cat <<'NEXT'
  1. Prove push reaches your phone:
       curl -X POST localhost:8501/api/alerts/test

  2. Prove the whole loop — publish, tap, approve:
       curl -s -X POST localhost:8501/api/feed/publish \
         -H 'Content-Type: application/json' -d '{
         "key":"test.golive","title":"Test finding","severity":"critical",
         "domain":"vwlr","body":"Tap this and approve it.",
         "action_type":"add_task",
         "action_payload":{"title":"Delete me - go-live test","priority":"low"}}'
     Phone buzzes -> tap -> Approve & run -> the task lands on your Task Board.

  3. If the VPN profiles are in place, discover the site networks:
       docker compose logs vpn-hotel | tail -20        # want "Initialization Sequence Completed"
       docker compose exec vpn-hotel sh -c '
         ip route
         ip route | grep -v default | grep -oE "^[0-9.]+/[0-9]+" | while read n; do
           echo "-- $n"; nmap -p 80,443,8080,8000,1433,3306 --open -oG - "$n" | grep -v "^#"
         done'

  4. Broker sessions expire daily. Check any time:
       curl -s -X POST localhost:8501/api/feed/check-sessions
NEXT

echo
echo "${GRN}Deploy finished.${OFF}  App: https://${DOM:-<DOMAIN>}   Shares CFO: http://<VPS_IP>:8000"
