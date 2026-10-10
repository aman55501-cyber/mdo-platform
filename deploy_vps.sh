#!/usr/bin/env bash
# deploy_vps.sh — one command deploys MDO on the VPS; `--auto` keeps it current.
#
#   sudo bash deploy_vps.sh          first deploy / re-deploy by hand (idempotent)
#   sudo bash deploy_vps.sh --auto   cron, every 10 min: pull + test + rebuild
#                                    only when origin/<branch> is ahead of HEAD;
#                                    logs to /var/log/mdo-deploy.log and files a
#                                    heartbeat to /api/agent/report every run
#
# Env overrides: MDO_DIR (repo dir), MDO_BRANCH (branch to track).
# Secrets are read from .env only and never printed.
#
# Everything lives in functions and main() is the last line, so a `git pull`
# that rewrites this very file cannot disturb the run already in progress.
set -euo pipefail
# bash ≥5.2 treats `&` in a ${var//pat/repl} replacement as the matched text;
# the cron prefix contains `&&`, so turn that off (no-op on older bash).
shopt -u patsub_replacement 2>/dev/null || true

MDO_DIR="${MDO_DIR:-/docker/sharecfo/mdo-platform}"
MDO_BRANCH="${MDO_BRANCH:-claude/chief-of-staff-bot-4i2jyz}"
API_URL="${MDO_API_URL:-http://localhost:8501}"
CRON_FILE=/etc/cron.d/mdo-fleet
LOG_FILE=/var/log/mdo-deploy.log
LOCK_FILE=/var/lock/mdo-deploy.lock
DOC_FILE=DEPLOY_HOSTINGER.md
DEFAULT_DIR_IN_DOC=/docker/sharecfo/mdo-platform

AUTO=0
STEP="start"
STATUS="error"
SUMMARY=""
HEARTBEAT_SENT=0
PREV_SHA=""
SHORT_SHA="unknown"
DEPLOYED_FILE=/var/lib/mdo/deployed_sha   # commit the running containers were built from
FAILED_FILE=/var/lib/mdo/failed_sha       # commit whose gate failed; not retried until HEAD moves
SERVICES_UP="none"
CRON_RESULT="skipped"
ALERT_RESULT="skipped"
TOKEN=""

# ── helpers ──────────────────────────────────────────────────────────────────
say()  { printf '[deploy %s] %s\n' "$(date '+%F %T')" "$*"; }
step() { STEP="$1"; say "── $1"; }
die()  { SUMMARY="failed at ${STEP}: $*"; say "ABORT: $*"; exit 1; }

read_env_value() {           # read_env_value KEY → value from $MDO_DIR/.env (never exported, never printed)
    local key="$1" line
    line="$(grep -E "^${key}=" "$MDO_DIR/.env" 2>/dev/null | tail -1 || true)"
    line="${line#*=}"
    line="${line%\"}"; line="${line#\"}"
    line="${line%\'}"; line="${line#\'}"
    printf '%s' "$line"
}

json_escape() {              # minimal JSON string escaping for the heartbeat
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/ }"
    s="${s//$'\t'/ }"
    printf '%s' "$s"
}

post_heartbeat() {           # ALWAYS called on exit (trap) — CHIEF_OF_STAFF.md Directive 5
    [[ "$HEARTBEAT_SENT" == 1 ]] && return 0
    HEARTBEAT_SENT=1
    local body resp
    body=$(printf '{"bot":"deploy","cadence":"daily","heartbeat":true,"status":"%s","summary":"%s","checks_run":[]}' \
        "$STATUS" "$(json_escape "$SUMMARY")")
    if [[ -z "$TOKEN" ]]; then
        say "heartbeat NOT sent: MDO_AUTH_TOKEN empty in .env (status=${STATUS}: ${SUMMARY})"
        return 0
    fi
    resp="$(curl -s -m 15 -X POST "${API_URL}/api/agent/report" \
        -H "Content-Type: application/json" -H "X-MDO-Key: ${TOKEN}" \
        --data "$body" 2>&1 || true)"
    if [[ "$resp" == *'"stored"'* ]]; then
        say "heartbeat filed: status=${STATUS} — ${SUMMARY}"
    else
        say "heartbeat NOT delivered (backend down?): status=${STATUS} — ${SUMMARY} — response: ${resp:0:200}"
    fi
}

on_exit() {
    local rc=$?
    if [[ $rc -ne 0 && "$STATUS" != "clean" && "$STATUS" != "stale" ]]; then
        STATUS="error"
        [[ -n "$SUMMARY" ]] || SUMMARY="failed at ${STEP} (exit ${rc})"
    fi
    post_heartbeat
    say "exit ${rc}"
}

need_root() {
    local flag=""
    [[ "$AUTO" == 1 ]] && flag=" --auto"
    [[ "${EUID}" -eq 0 ]] || die "run as root: sudo bash deploy_vps.sh${flag}"
}

# ── a. repo + branch ─────────────────────────────────────────────────────────
step_repo() {
    step "a. repo: ${MDO_DIR} @ ${MDO_BRANCH}"
    [[ -d "$MDO_DIR/.git" ]] || die "${MDO_DIR} is not a git checkout (set MDO_DIR?)"
    cd "$MDO_DIR"
    if ! git config --global --get-all safe.directory 2>/dev/null | grep -qx "$MDO_DIR"; then
        git config --global --add safe.directory "$MDO_DIR" >/dev/null 2>&1 || true
    fi
    git fetch --quiet origin "$MDO_BRANCH" || die "git fetch origin ${MDO_BRANCH} failed"

    local current
    current="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo detached)"
    if [[ "$current" != "$MDO_BRANCH" ]]; then
        git checkout --quiet "$MDO_BRANCH" 2>/dev/null \
            || git checkout --quiet -b "$MDO_BRANCH" --track "origin/$MDO_BRANCH" \
            || die "cannot check out ${MDO_BRANCH}"
        say "switched ${current} → ${MDO_BRANCH}"
    fi

    local behind head live failed
    behind="$(git rev-list --count "HEAD..origin/${MDO_BRANCH}" 2>/dev/null || echo 0)"
    head="$(git rev-parse HEAD)"
    # "Up to date" means the RUNNING containers were built from HEAD, not merely that
    # HEAD matches origin: a pull whose tests failed leaves HEAD ahead of what runs.
    # (2026-10-10: date-bound tests failed after midnight and every run since said
    # "up to date" while yesterday's build never went live — silence that looked alive.)
    live="$(cat "$DEPLOYED_FILE" 2>/dev/null || true)"
    failed="$(cat "$FAILED_FILE" 2>/dev/null || true)"
    if [[ "$AUTO" == 1 && "$behind" == 0 ]]; then
        SHORT_SHA="$(git rev-parse --short HEAD)"
        if [[ "$live" == "$head" ]]; then
            STATUS="clean"; SUMMARY="up to date"
            say "up to date at ${SHORT_SHA} — nothing to do"
            exit 0
        fi
        if [[ -n "$failed" && "$failed" == "$head" ]]; then
            # The 💀 went to the phone on the first failure; repeats file "stale" (ledger and
            # fleet page, no WhatsApp) so a broken gate is visible without a message every 10 min.
            STATUS="stale"
            SUMMARY="NOT LIVE: ${SHORT_SHA} failed its gate; still running ${live:0:7}. A fix pushed to the branch deploys on the next slot"
            say "$SUMMARY"; exit 1
        fi
        say "HEAD ${SHORT_SHA} is not what runs (${live:0:7}) — deploying it"
    fi
    PREV_SHA="${live:-$head}"
    # No record of what runs (first run with this marker): rebuild the frontend too, once.
    [[ -n "$live" ]] || FORCE_FRONTEND=1
    if ! git pull --quiet --ff-only origin "$MDO_BRANCH"; then
        die "git pull --ff-only failed (local edits or diverged history on the VPS? run: git status)"
    fi
    SHORT_SHA="$(git rev-parse --short HEAD)"
    say "HEAD ${SHORT_SHA} (${behind} new commit(s) pulled)"
}

# ── b. .env ──────────────────────────────────────────────────────────────────
step_env() {
    step "b. .env"
    if [[ ! -f .env ]]; then
        cp .env.example .env
        chmod 600 .env
        say "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        say "!!  .env did not exist — copied from .env.example. EVERY KEY IS A      !!"
        say "!!  PLACEHOLDER. Fill ANTHROPIC_API_KEY, MDO_AUTH_TOKEN, MDO_MCP_SECRET, !!"
        say "!!  CFO_API_TOKEN, NEXT_PUBLIC_API_URL in ${MDO_DIR}/.env               !!"
        say "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    fi
    # Append any var from the "Chief of Staff" block of .env.example that .env
    # lacks, with its example default. Existing values are never touched.
    # Nothing is generated here: a token that only Aman can paste elsewhere
    # (GROK_CONTEXT_TOKEN into the Grok task, VAULT_TOKEN into a Routine) is
    # appended EMPTY — empty means the door answers 403 — and listed by
    # placeholder_keys in the summary until he fills it.
    local in_block=0 added=() line key
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" =~ ^#\ ──\ Chief\ of\ Staff ]]; then in_block=1; continue; fi
        if [[ $in_block == 1 && "$line" =~ ^#\ ── ]]; then break; fi
        [[ $in_block == 1 ]] || continue
        [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)= ]] || continue
        key="${BASH_REMATCH[1]}"
        if ! grep -qE "^${key}=" .env; then
            if [[ -s .env && -n "$(tail -c1 .env)" ]]; then echo >> .env; fi
            printf '%s\n' "$line" >> .env
            added+=("$key")
        fi
    done < .env.example
    if (( ${#added[@]} )); then
        say "added ${#added[@]} missing Chief of Staff var(s) with example defaults: ${added[*]}"
    else
        say "all Chief of Staff vars present — nothing added"
    fi
    TOKEN="$(read_env_value MDO_AUTH_TOKEN)"
    [[ -n "$TOKEN" ]] || say "WARNING: MDO_AUTH_TOKEN is empty — API is unprotected and heartbeats cannot authenticate"
    # CALENDAR_TOKEN is the one token the script DOES generate: nobody pastes it
    # anywhere but a calendar subscription URL, and the summary prints that URL.
    # An existing value is never touched (blank it in .env to rotate).
    if [[ -z "$(read_env_value CALENDAR_TOKEN)" ]]; then
        local cal
        cal="$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
        if grep -qE '^CALENDAR_TOKEN=' .env; then
            sed -i "s|^CALENDAR_TOKEN=.*|CALENDAR_TOKEN=${cal}|" .env
        else
            if [[ -s .env && -n "$(tail -c1 .env)" ]]; then echo >> .env; fi
            printf 'CALENDAR_TOKEN=%s\n' "$cal" >> .env
        fi
        say "generated CALENDAR_TOKEN (calendar feed door) — the feed URL is on the summary"
    fi
}

# ── c. tests in a throwaway container ────────────────────────────────────────
step_tests() {
    step "c. unit tests (throwaway container)"
    # The test container must run the NEW code, so the image is built first.
    # Building does not touch the running containers; only `up` in step d does.
    # A failed test therefore leaves the live services exactly as they were.
    docker compose build backend || die "docker compose build backend failed"
    # Run on the bare image with `docker run`, NOT `docker compose run`: compose would
    # mount the live data volume at /data, and the image's VEGA_DB_PATH points there —
    # a test that wipes a table would wipe production. Scratch paths only, no volumes.
    # tests/test_core.py belongs to the Shares CFO service (its own container) and is
    # skipped here; CI runs it from the full checkout.
    local img=""
    # Image name = <compose project>-backend. Every lookup below may fail on older
    # compose versions, so each is wrapped; the fallback is the project directory name.
    img="$( { docker compose config --images 2>/dev/null || true; } | grep -m1 -- '-backend' || true)"
    [[ -n "$img" ]] || img="$( { docker compose ps --format '{{.Image}}' backend 2>/dev/null || true; } | head -1 || true)"
    [[ -n "$img" ]] || img="$(basename "$PWD")-backend"
    say "test image: $img"
    if ! docker run --rm --network none \
            -e VEGA_DB_PATH=/tmp/t/vega.db -e VEDANTA_DB_PATH=/tmp/t/vedanta.db \
            -e VAULT_DIR=/tmp/t/vault -e MDO_AUTH_TOKEN= -e MDO_MCP_SECRET= \
            -e ANTHROPIC_API_KEY= -e GROK_API_KEY= -e WA_BRIDGE_URL= -e ALERT_WHATSAPP_TO= \
            "$img" sh -c "mkdir -p /tmp/t/vault && python -m pytest -q tests/ --ignore=tests/test_core.py"; then
        git rev-parse HEAD > "$FAILED_FILE" 2>/dev/null || true
        die "unit tests FAILED — live services left untouched, nothing deployed"
    fi
    say "tests passed (backend suite, scratch DB, no volumes)"
}

# ── d. bring services up ─────────────────────────────────────────────────────
step_up() {
    step "d. docker compose up"
    local services=(backend whatsapp)
    if docker compose config --services 2>/dev/null | grep -qx whatsapp2; then
        services+=(whatsapp2)
    fi
    # The Next.js build takes ~4 min, so the frontend is rebuilt only when the app
    # changed in what was just pulled (or when FORCE_FRONTEND=1).
    if [[ "${FORCE_FRONTEND:-0}" == 1 ]] || { [[ -n "${PREV_SHA:-}" ]] && git diff --name-only "$PREV_SHA" HEAD -- mdo-app/ | grep -q .; }; then
        services+=(frontend)
    fi
    docker compose up -d --build "${services[@]}" || { git rev-parse HEAD > "$FAILED_FILE" 2>/dev/null || true; die "docker compose up failed"; }
    git rev-parse HEAD > "$DEPLOYED_FILE"
    rm -f "$FAILED_FILE"
    SERVICES_UP="${services[*]}"
    say "up: ${SERVICES_UP}"
}

# ── e+f. cron ────────────────────────────────────────────────────────────────
render_cron() {              # the §8 block of DEPLOY_HOSTINGER.md, $MDO expanded, + self-update line
    local block mdo="" line comment m h dom mon dow cmd
    block="$(awk '/^# MDO fleet/{f=1} f&&/^```/{exit} f' "$DOC_FILE")"
    [[ -n "$block" ]] || die "cron block not found in ${DOC_FILE} §8"
    printf '# /etc/cron.d/mdo-fleet — written by deploy_vps.sh from %s §8. Do not hand-edit; re-run the script.\n' "$DOC_FILE"
    printf 'SHELL=/bin/bash\n'
    printf 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n'
    printf 'MAILTO=""\n\n'
    while IFS= read -r line; do
        [[ -z "${line// }" ]] && continue
        if [[ "$line" =~ ^# ]]; then printf '%s\n' "$line"; continue; fi
        if [[ "$line" =~ ^MDO=(.*)$ ]]; then
            mdo="${BASH_REMATCH[1]}"
            mdo="${mdo//$DEFAULT_DIR_IN_DOC/$MDO_DIR}"
            continue
        fi
        comment=""
        if [[ "$line" == *"#"* ]]; then comment="${line#*#}"; line="${line%%#*}"; fi
        read -r m h dom mon dow cmd <<<"$line"
        [[ -n "${cmd:-}" ]] || continue
        cmd="${cmd//\$MDO/$mdo}"
        cmd="${cmd%"${cmd##*[![:space:]]}"}"
        if [[ -n "$comment" ]]; then printf '#%s\n' "$comment"; fi
        printf '%s %s %s %s %s root %s\n' "$m" "$h" "$dom" "$mon" "$dow" "$cmd"
    done <<<"$block"
    printf '\n# self-update: pull + test + rebuild when origin/%s is ahead; heartbeat every run\n' "$MDO_BRANCH"
    printf '*/10 * * * * root MDO_DIR=%q MDO_BRANCH=%q /bin/bash %q/deploy_vps.sh --auto >> %s 2>&1\n' \
        "$MDO_DIR" "$MDO_BRANCH" "$MDO_DIR" "$LOG_FILE"
}

step_cron() {
    step "e+f. cron: ${CRON_FILE}"
    local tmp
    tmp="$(mktemp)"
    render_cron > "$tmp"
    if [[ -f "$CRON_FILE" ]] && cmp -s "$tmp" "$CRON_FILE"; then
        CRON_RESULT="unchanged ($(grep -c '^[0-9*]' "$CRON_FILE") jobs)"
        say "cron unchanged"
    else
        install -o root -g root -m 0644 "$tmp" "$CRON_FILE"
        CRON_RESULT="installed ($(grep -c '^[0-9*]' "$CRON_FILE") jobs incl. self-update every 10 min)"
        say "cron ${CRON_RESULT}"
    fi
    rm -f "$tmp"
    touch "$LOG_FILE" /var/log/mdo-agent.log

    # Old per-user crontab lines (the pre-cron.d way) would double-run the bots.
    local users="root" u before after n_before n_after
    if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then users="root $SUDO_USER"; fi
    for u in $users; do
        before="$(crontab -u "$u" -l 2>/dev/null || true)"
        [[ -n "$before" ]] || { say "no crontab for ${u} — nothing to clean"; continue; }
        after="$(printf '%s\n' "$before" | grep -v -e 'mdo_agent' -e 'mdo_housekeeping' -e 'savelog .*mdo-agent' -e '^MDO=' || true)"
        n_before="$(printf '%s\n' "$before" | grep -c . || true)"
        n_after="$(printf '%s\n' "$after" | grep -c . || true)"
        if (( n_before > n_after )); then
            if [[ -n "${after// }" ]]; then printf '%s\n' "$after" | crontab -u "$u" -; else crontab -u "$u" -r; fi
            say "removed $(( n_before - n_after )) old mdo_agent line(s) from ${u}'s crontab"
        else
            say "no old mdo_agent lines in ${u}'s crontab"
        fi
    done
}

# ── g. prove the alert channel ───────────────────────────────────────────────
wait_backend() {
    local i
    for i in $(seq 1 45); do
        if curl -s -m 3 -o /dev/null -w '%{http_code}' -H "X-MDO-Key: ${TOKEN}" "${API_URL}/api/status" 2>/dev/null | grep -q '^200$'; then
            return 0
        fi
        sleep 2
    done
    return 1
}

step_alert() {
    step "g. test alert → WhatsApp"
    if ! wait_backend; then
        ALERT_RESULT="backend not answering on ${API_URL} after 90s — check: docker compose logs backend"
        say "$ALERT_RESULT"
        return 0
    fi
    ALERT_RESULT="$(curl -s -m 20 -X POST "${API_URL}/api/alerts/test" -H "X-MDO-Key: ${TOKEN}" || echo '{"sent":false,"reason":"curl failed"}')"
    say "alert test: ${ALERT_RESULT}"
}

# ── h. summary ───────────────────────────────────────────────────────────────
placeholder_keys() {         # keys in .env still at example / empty values that only Aman can fill
    local key val out=()
    for key in ANTHROPIC_API_KEY MDO_AUTH_TOKEN MDO_MCP_SECRET CFO_API_TOKEN NEXT_PUBLIC_API_URL GROK_API_KEY GROK_CONTEXT_TOKEN HDFC_API_KEY HDFC_API_SECRET; do
        val="$(read_env_value "$key")"
        if [[ -z "$val" || "$val" == your_* || "$val" == *YOUR_VPS_IP* ]]; then out+=("$key"); fi
    done
    printf '%s' "${out[*]:-none}"
}

calendar_feed_url() {        # the subscription URL for Google Calendar → Other calendars → From URL (DEPLOY_HOSTINGER.md §8b)
    local tok dom
    tok="$(read_env_value CALENDAR_TOKEN)"
    dom="$(read_env_value ALT_DOMAINS)"; dom="${dom%% *}"
    [[ -n "$dom" ]] || dom="$(read_env_value DOMAIN)"
    [[ -n "$dom" ]] || dom="<DOMAIN in .env>"
    if [[ -n "$tok" ]]; then echo "https://${dom}/api/calendar.ics?token=${tok}"; else echo "not generated (CALENDAR_TOKEN empty)"; fi
}

bridge_state() {
    local resp
    resp="$(curl -s -m 8 -H "X-MDO-Key: ${TOKEN}" "${API_URL}/api/whatsapp/qr" 2>/dev/null || true)"
    if [[ "$resp" == *'"connected": true'* || "$resp" == *'"connected":true'* ]]; then
        echo "connected"
    elif [[ -z "$resp" ]]; then
        echo "unknown (backend not reachable)"
    else
        echo "DISCONNECTED — scan the QR on the app's VWLR Ops Feed page"
    fi
}

step_summary() {
    step "h. summary"
    local cap ALT_DOMAIN_FIRST
    cap="$(read_env_value SPEND_CAP_INR_MONTH)"
    ALT_DOMAIN_FIRST="$(read_env_value ALT_DOMAINS)"; ALT_DOMAIN_FIRST="${ALT_DOMAIN_FIRST%% *}"
    cat <<EOF

══════════════════════════ MDO deploy summary ══════════════════════════
 branch        : ${MDO_BRANCH}
 commit        : ${SHORT_SHA}
 services up   : ${SERVICES_UP}
 cron          : ${CRON_RESULT}  (${CRON_FILE})
 self-update   : every 10 min via deploy_vps.sh --auto → ${LOG_FILE}
 test alert    : ${ALERT_RESULT}
 calendar feed : $(calendar_feed_url)
 watchdog      : UptimeRobot keyword monitor on https://${ALT_DOMAIN_FIRST:-$(read_env_value DOMAIN)}/api/health/public, keyword "ok":true (§8a)

 Only Aman can do these three:
  1. Fill the keys in ${MDO_DIR}/.env still at example/empty values:
       $(placeholder_keys)
     then: docker compose up -d backend whatsapp
  2. Set the spend cap: SPEND_CAP_INR_MONTH in .env (now: ${cap:-empty}; agenda.yaml says Aman decides).
  3. WhatsApp bridge: $(bridge_state)
═════════════════════════════════════════════════════════════════════════
EOF
}

# ── main ─────────────────────────────────────────────────────────────────────
main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
        sed -n '2,14p' "$0"; exit 0
    fi
    if [[ "${1:-}" == "--auto" ]]; then AUTO=1; fi
    need_root
    mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$LOCK_FILE")" "$(dirname "$DEPLOYED_FILE")"

    if [[ "$AUTO" == 1 ]]; then
        exec >> "$LOG_FILE" 2>&1
        say "auto run start"
    fi
    # TOKEN is read as early as possible so even an early failure heartbeats.
    TOKEN="$(read_env_value MDO_AUTH_TOKEN)"
    trap on_exit EXIT

    # One deploy at a time. --auto gives up immediately (next slot retries);
    # a manual run waits for a running auto deploy to finish.
    exec 9>"$LOCK_FILE"
    if [[ "$AUTO" == 1 ]]; then
        if ! flock -n 9; then
            STATUS="clean"; SUMMARY="skipped: previous deploy still running"
            say "$SUMMARY"; exit 0
        fi
    else
        flock -w 900 9 || die "another deploy has held the lock for 15 min"
    fi

    step_repo
    step_env
    step_tests
    step_up
    STATUS="clean"; SUMMARY="deployed ${SHORT_SHA} — tests passed"
    if [[ "$AUTO" == 0 ]]; then
        step_cron
        step_alert
        step_summary
    else
        say "auto: deployed ${SHORT_SHA} — tests passed"
    fi
}

main "$@"
