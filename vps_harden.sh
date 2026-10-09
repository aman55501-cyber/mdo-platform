#!/usr/bin/env bash
# vps_harden.sh — baseline hardening for the MDO Hostinger VPS (Ubuntu, run as root).
#
# Idempotent: run it as often as you like; it only changes what differs.
#   sudo bash vps_harden.sh
#
# What it does (DEPLOY_HOSTINGER.md §10):
#   1. ufw: allow 22, 80, 443/tcp; enable only after you answer y (skipped if active)
#   2. fail2ban: sshd jail on
#   3. unattended-upgrades: security pocket only, no automatic reboot
#   4. journald: SystemMaxUse=500M
#   5. docker: prune dangling images + build cache older than 7 days
#   6. one-screen summary
#
# What it never does: touch /etc/ssh/sshd_config, disable password auth, open or
# close any port other than the three above, restart the compose stack.
#
# Note on Docker and ufw: Docker publishes ports with its own iptables chain
# that runs BEFORE ufw, so a `ports:` line in docker-compose.yml is reachable
# whatever ufw says. That is why sharescfo binds 127.0.0.1:8000 in compose and
# why the Hostinger panel firewall (which sits in front of the VM) stays the
# place to close 3000/8501 once the domain is live.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive

changed=()
note() { printf '  %s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

# write_if_differs <path> <content>  — returns 0 when the file was (re)written
write_if_differs() {
    local path="$1" content="$2"
    if [[ -f "$path" ]] && [[ "$(cat "$path")" == "$content" ]]; then
        return 1
    fi
    install -d -m 0755 "$(dirname "$path")"
    printf '%s\n' "$content" > "$path"
    return 0
}

apt_have() { dpkg -s "$1" >/dev/null 2>&1; }
apt_need() {
    local missing=()
    for p in "$@"; do apt_have "$p" || missing+=("$p"); done
    if ((${#missing[@]})); then
        note "installing: ${missing[*]}"
        apt-get update -qq
        apt-get install -y -qq --no-install-recommends "${missing[@]}"
        changed+=("installed ${missing[*]}")
    fi
}

# ── 1. ufw ────────────────────────────────────────────────────────────────────
step "ufw — 22, 80, 443 only"
apt_need ufw
for port in 22 80 443; do
    out="$(ufw allow "${port}/tcp" 2>&1 || true)"
    if [[ "$out" == *"Skipping"* ]]; then
        note "allow ${port}/tcp: already present"
    else
        note "allow ${port}/tcp: added"
        changed+=("ufw allow ${port}/tcp")
    fi
done
if ufw status 2>/dev/null | grep -q '^Status: active'; then
    note "ufw already active — not touching it"
else
    if [[ -t 0 ]]; then
        read -r -p "  ufw is inactive. Enable it now? Only 22/80/443 stay open (Docker-published ports are unaffected). [y/N] " ans
    else
        ans="n"; note "no terminal to ask on — leaving ufw inactive (run interactively to enable)"
    fi
    if [[ "${ans,,}" == "y" ]]; then
        ufw --force enable
        changed+=("ufw enabled")
        note "ufw enabled"
    else
        note "ufw left inactive (rules are saved; enable later with: ufw enable)"
    fi
fi

# ── 2. fail2ban: sshd jail ────────────────────────────────────────────────────
step "fail2ban — sshd jail"
apt_need fail2ban
if write_if_differs /etc/fail2ban/jail.d/mdo-sshd.local "$(cat <<'JAIL'
# written by vps_harden.sh — sshd jail for the MDO VPS
[sshd]
enabled  = true
backend  = systemd
maxretry = 5
findtime = 10m
bantime  = 1h
JAIL
)"; then
    changed+=("fail2ban sshd jail written")
    note "jail written"
else
    note "jail unchanged"
fi
systemctl enable --now fail2ban >/dev/null 2>&1 || true
if [[ " ${changed[*]} " == *"fail2ban sshd jail written"* ]]; then
    systemctl restart fail2ban
    note "fail2ban restarted"
fi

# ── 3. unattended-upgrades: security only, never reboots on its own ──────────
step "unattended-upgrades — security pocket only"
apt_need unattended-upgrades
auto_changed=0
write_if_differs /etc/apt/apt.conf.d/20auto-upgrades "$(cat <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
)" && auto_changed=1
write_if_differs /etc/apt/apt.conf.d/52mdo-security-only "$(cat <<'CONF'
// written by vps_harden.sh — only the security pocket, never a reboot
#clear Unattended-Upgrade::Allowed-Origins;
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
CONF
)" && auto_changed=1
if ((auto_changed)); then
    changed+=("unattended-upgrades configured")
    note "configuration written"
else
    note "configuration unchanged"
fi
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

# ── 4. journald cap ───────────────────────────────────────────────────────────
step "journald — SystemMaxUse=500M"
if write_if_differs /etc/systemd/journald.conf.d/mdo.conf "$(cat <<'CONF'
# written by vps_harden.sh
[Journal]
SystemMaxUse=500M
CONF
)"; then
    systemctl restart systemd-journald
    changed+=("journald capped at 500M")
    note "cap written, journald restarted"
else
    note "cap already in place"
fi

# ── 5. docker: dangling images + build cache older than 7 days ───────────────
step "docker — prune dangling images and build cache older than 7 days"
if command -v docker >/dev/null 2>&1; then
    # image prune without -a removes only dangling (untagged) images; the
    # until= filter keeps anything younger than a week. Stopped containers and
    # the compose volumes are never touched (that is what `docker system prune`
    # would also reap — deliberately not used here).
    note "$(docker image prune -f --filter 'until=168h' 2>&1 | tail -n 1)"
    note "$(docker builder prune -f --filter 'until=168h' 2>&1 | tail -n 1)"
else
    note "docker not installed — skipped"
fi

# ── 6. summary ────────────────────────────────────────────────────────────────
step "summary"
printf '  %-22s %s\n' "ufw"        "$(ufw status 2>/dev/null | head -n 1 | sed 's/Status: //') · $(ufw status 2>/dev/null | grep -cE '^(22|80|443)/tcp' || true) of 3 rules present"
printf '  %-22s %s\n' "fail2ban sshd"  "$(fail2ban-client status sshd 2>/dev/null | awk -F'\t' '/Currently banned/{b=$2} /Total banned/{t=$2} END{printf "active · banned now %s · total %s", b+0, t+0}' || echo "not running")"
printf '  %-22s %s\n' "unattended-upgrades" "$(systemctl is-active unattended-upgrades 2>/dev/null || echo inactive) · security pocket only · no auto-reboot"
printf '  %-22s %s\n' "journald"   "$(journalctl --disk-usage 2>/dev/null | sed 's/Archived and active journals take up //; s/ in the file system.//') (cap 500M)"
if command -v docker >/dev/null 2>&1; then
    printf '  %-22s %s\n' "docker images" "$(docker system df --format '{{.Type}}: {{.Size}} ({{.Reclaimable}} reclaimable)' 2>/dev/null | head -n 1)"
fi
printf '  %-22s %s\n' "disk /"     "$(df -h / | awk 'NR==2{print $4" free of "$2" ("$5" used)"}')"
printf '  %-22s %s\n' "sshd_config" "untouched (this script never edits it)"
if ((${#changed[@]})); then
    printf '\n  changed this run: %s\n' "$(IFS='; '; echo "${changed[*]}")"
else
    printf '\n  nothing to change — already hardened\n'
fi
