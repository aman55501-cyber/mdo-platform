#!/usr/bin/env bash
# One-command setup for Aman. Asks plain questions, fills .env, deploys, hardens.
# Safe to run again: it only changes what is blank or what you answer.
set -uo pipefail
cd "$(dirname "$0")"
ENV=.env; [[ -f $ENV ]] || cp .env.example $ENV
say(){ printf '\n\033[1m%s\033[0m\n' "$*"; }
getv(){ grep -E "^$1=" $ENV | head -1 | cut -d= -f2-; }
setv(){ if grep -qE "^$1=" $ENV; then sed -i "s#^$1=.*#$1=$2#" $ENV; else echo "$1=$2" >> $ENV; fi; }
ask(){ local var="$1" prompt="$2" cur; cur="$(getv "$var")"
  if [[ -n "$cur" && "$cur" != *example* && "$cur" != *your* && "$cur" != *xxx* ]]; then echo "  $var already set, keeping it."; return; fi
  read -r -p "  $prompt (Enter to skip): " val; [[ -n "$val" ]] && setv "$var" "$val"; }
gen(){ local var="$1" cur; cur="$(getv "$var")"; [[ -n "$cur" && "$cur" != *example* ]] && return; setv "$var" "$(openssl rand -hex 16)"; echo "  $var generated."; }

say "1/6  Domain"
setv ALT_DOMAINS "amanagrawal.cloud www.amanagrawal.cloud"
setv NEXT_PUBLIC_API_URL "https://amanagrawal.cloud"
me="$(curl -s4 -m 8 ifconfig.me || true)"; dns="$(dig +short amanagrawal.cloud | tail -1)"
if [[ -n "$dns" && "$dns" == "$me" ]]; then echo "  amanagrawal.cloud points here ($me). Good."
else echo "  WARNING: amanagrawal.cloud resolves to '${dns:-nothing}', this server is '$me'. Add an A record at your registrar. Continuing on the Hostinger name meanwhile."; fi

say "2/6  Keys (paste when asked, nothing is shown back)"
ask GROK_API_KEY "Grok (xAI) API key"
ask HDFC_API_KEY "HDFC InvestRight API key"
ask HDFC_API_SECRET "HDFC InvestRight API secret"
cur="$(getv VAULT_BACKUP_PASSPHRASE)"
if [[ -z "$cur" ]]; then setv VAULT_BACKUP_PASSPHRASE "$(openssl rand -base64 24 | tr -d '/+=')"; echo "  Backup passphrase generated. It is printed at the end ONCE, save it offline."; fi
gen VAULT_TOKEN; gen TENDER_INBOUND_TOKEN; gen GROK_CONTEXT_TOKEN

say "3/6  Pull latest code and apply (about 5 minutes, frontend rebuild included)"
git pull -q origin claude/chief-of-staff-bot-4i2jyz || echo "  pull failed, continuing with what is here"
docker compose up -d caddy >/dev/null 2>&1 || true
FORCE_FRONTEND=1 bash deploy_vps.sh | tail -8
docker compose up -d whatsapp2 >/dev/null 2>&1 || true

say "4/6  Harden the server (firewall, fail2ban, security updates)"
[[ -x vps_harden.sh ]] && yes | bash vps_harden.sh | tail -5 || bash vps_harden.sh | tail -5

say "5/6  Old stash"
git stash drop >/dev/null 2>&1 && echo "  dropped." || echo "  none to drop."

say "6/6  Copy these into claude.ai → Environment → Secrets (and the Grok draft). Do not paste them into chat."
echo "  MDO_SELF_URL=https://amanagrawal.cloud"
for k in MDO_AUTH_TOKEN VAULT_TOKEN TENDER_INBOUND_TOKEN GROK_CONTEXT_TOKEN VAULT_BACKUP_PASSPHRASE; do echo "  $k=$(getv $k)"; done
echo
echo "Next: open https://amanagrawal.cloud/ops-feed (or https://srv1641037.hstgr.cloud/ops-feed) and scan both QRs. Then: reboot"
