#!/bin/sh
# Start the HTTP proxy, then hand the process over to OpenVPN.
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

echo "[vpn] starting tinyproxy on :8888"
tinyproxy -c /etc/tinyproxy/tinyproxy.conf

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
