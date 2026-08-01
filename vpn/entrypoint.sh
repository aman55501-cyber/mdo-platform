#!/bin/sh
# Start the proxies, then hand the process over to OpenVPN.
#
# The pull-filter lines are the safety rail: whatever the site gateway pushes,
# this client refuses a default route and refuses to rewrite DNS. Without them
# a route push would blackhole the container's own traffic.
set -e

CONFIG=${VPN_CONFIG:-/etc/openvpn/client.ovpn}

if [ ! -f "$CONFIG" ]; then
  echo "FATAL: no profile at $CONFIG — mount the site's client.ovpn there" >&2
  exit 2
fi

# Existence is not enough. A half-finished paste leaves an empty or truncated file,
# and OpenVPN's complaint about that is obscure ("TLS key negotiation failed") and
# sends you hunting for a network fault that isn't there. Say what is actually wrong.
if [ ! -s "$CONFIG" ]; then
  echo "FATAL: $CONFIG is empty — the profile did not transfer." >&2
  echo "       Expected ~3.9 KB starting with 'client' and ending with '</key>'." >&2
  exit 2
fi
for marker in '^remote ' '<ca>' '<cert>' '<key>' '</key>'; do
  if ! grep -q "$marker" "$CONFIG"; then
    echo "FATAL: $CONFIG looks truncated — no '$marker' found." >&2
    echo "       Size is $(wc -c < "$CONFIG") bytes; a complete profile is ~3.9 KB." >&2
    exit 2
  fi
done
echo "[vpn] profile looks complete ($(wc -c < "$CONFIG") bytes)"

echo "[vpn] starting tinyproxy on :8888"
tinyproxy -c /etc/tinyproxy/tinyproxy.conf

# ── Raw TCP forwards ───────────────────────────────────────────────────────
# An HTTP proxy only carries HTTP. The hotel runs IDS Next FortuneNext, which is
# a SQL Server application — its data is on 1433, not behind a web endpoint. So
# the sidecar can also publish plain TCP forwards into the tunnel.
#
#   TCP_FORWARDS="1433:10.0.0.5:1433,3306:10.0.0.6:3306"
#                 ^listen  ^host inside the site LAN
#
# The listening side is bound inside the container network only (never published
# to the VPS host), so the exposure is the same as the HTTP proxy's: reachable by
# the backend container, by nothing else.
if [ -n "$TCP_FORWARDS" ]; then
  echo "$TCP_FORWARDS" | tr ',' '\n' | while IFS= read -r rule; do
    rule=$(echo "$rule" | tr -d ' ')
    [ -z "$rule" ] && continue
    LPORT=$(echo "$rule" | cut -d: -f1)
    RHOST=$(echo "$rule" | cut -d: -f2)
    RPORT=$(echo "$rule" | cut -d: -f3)
    if [ -z "$LPORT" ] || [ -z "$RHOST" ] || [ -z "$RPORT" ]; then
      echo "[vpn] skipping malformed TCP_FORWARDS entry: '$rule' (want listen:host:port)" >&2
      continue
    fi
    echo "[vpn] tcp forward :$LPORT -> $RHOST:$RPORT"
    socat TCP-LISTEN:"$LPORT",fork,reuseaddr TCP:"$RHOST":"$RPORT" &
  done
fi

echo "[vpn] connecting: $(grep -m1 '^remote ' "$CONFIG" || echo 'no remote line found')"

# --data-ciphers-fallback: these profiles specify AES-128-CBC, which OpenVPN 2.6
#   will not negotiate unless it is named explicitly.
# --script-security 1: no user scripts from the profile are executed.
exec openvpn \
  --config "$CONFIG" \
  --data-ciphers-fallback AES-128-CBC \
  --data-ciphers 'AES-256-GCM:AES-128-GCM:AES-128-CBC' \
  --pull-filter ignore "redirect-gateway" \
  --pull-filter ignore "dhcp-option DNS" \
  --script-security 1 \
  --verb 3
