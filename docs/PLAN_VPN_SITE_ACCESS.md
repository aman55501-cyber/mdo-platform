# Plan: Reach the Hotel and Vedanta site networks from the MDO VPS over OpenVPN

**One-line goal:** the MDO backend on the Hostinger VPS can query servers inside the Hotel ANS site network (and later the Vedanta site network) on its own, with the owner's laptop switched off, and without the VPS ever losing its own internet connectivity.

## Classification

Track: **Integration** — the end state is a working connection to systems the MDO codebase does not own. Parked secondary asks: *reading hotel PMS data into `hotel_daily`* (cannot be specified until Phase 3 identifies what software runs there); *Vedanta ERP integration* (same reason, plus its VPN profile is not yet available).

## Interview Ledger

- Q1 VPN terminates on VPS or on-prem collector → **VPS**, isolate in container (accepted)
- Q2 which VPN client → **OpenVPN Connect, two `.ovpn` profiles** (user)
- Q3 paste `ipconfig`/`route` → superseded by profile upload (not answered, not needed)
- Q4 upload profile directives → hotel profile received, full file including private key
- Q5 upload Vedanta profile → same hotel file re-uploaded; Vedanta deferred to Phase 6
- Q6 approve plan → this document

Questions spent: 6 of 14.

## Goal & Success Criteria

- G1. From inside the `mdo-platform-backend-1` container, `curl` against a host on the hotel LAN returns an HTTP response, with the VPS's own public services unaffected.
- G2. `https://amanagrawal.cloud` and SSH to `72.60.97.133` remain reachable throughout and after tunnel establishment — verified by an external check, not from the SSH session itself.
- G3. The tunnel re-establishes automatically after `docker restart` and after a full VPS reboot, with no human action.
- G4. A written inventory exists of every reachable host, open port and identified service on the hotel LAN.
- G5. When the tunnel is down for more than 10 minutes, a 🔴 alert reaches the owner's WhatsApp through the existing alert path.

## Current State

- MDO runs on a Hostinger VPS at `72.60.97.133`, Ubuntu 24.04, Docker Compose, four services: `backend`, `frontend`, `whatsapp`, `whatsapp2` (verified: `docker compose up` output this session).
- Project directory on the VPS is `/docker/sharecfo/mdo-platform`, git remote `aman55501-cyber/mdo-platform`, deploys by `git pull origin master && docker compose up -d --build` (verified: this session's deploy commands).
- Backend container name is `mdo-platform-backend-1` (verified: `docker compose up` output).
- Secrets live in `/docker/sharecfo/mdo-platform/.env`, which is gitignored (verified: `.gitignore` contains `.env`).
- A precedent exists for reading another service over a shared Docker network: `_cfo_get()` reads the `sharecfo` stack via `CFO_API_URL`/`CFO_API_TOKEN`, joined with `docker network connect sharecfo_default mdo-platform-backend-1` (verified: `mdo_server.py`, and the network-connect command run this session).
- A working outbound alert path exists: `POST /api/alerts/test` → WhatsApp bridge → owner's phone, confirmed delivered (verified: `{"sent":true,...,"jid":"917000512030@s.whatsapp.net"}` this session).
- Hotel VPN profile facts, all read from the uploaded `.ovpn` (verified: file contents + `openssl`):
  - `client`, `dev tun`, `proto udp`, `remote 182.65.204.86 1194`
  - `cipher AES-128-CBC`, `comp-lzo no`, `remote-cert-tls server`, `persist-key`, `float`, `nobind`, `explicit-exit-notify`, `resolv-retry infinite`
  - **No `auth-user-pass`, no `static-challenge`** → certificate-only authentication, so no interactive login and no one-time password
  - **No `route`, no `redirect-gateway`, no `tls-auth`, no `tls-crypt`** → all routes arrive by server push; no extra HMAC channel protection
  - Gateway is a TP-Link Omada device (certificate subject `O = TP-Link, OU = SMB-OMADA`), client CN `client_server0`
  - Client key is **1024-bit RSA**, certificate valid `2026-07-30` → `2036-07-27`
- The Vedanta VPN profile has not been provided; three uploads were the same hotel file (verified: identical md5 `1e264a47caca93e89a82eac35b8a0033`).
- What runs inside the hotel LAN is unknown — no host addresses, no software names, no credentials. Phase 3 discovers this.

## Scope (v1)

Establish an isolated, self-healing OpenVPN tunnel from the VPS to the hotel site network; prove the MDO backend can reach hosts inside it; produce an inventory of what is there; add tunnel-down alerting. Vedanta is added by cloning the same pattern once its profile exists.

## Out of Scope & Parked Items

- **Reading hotel PMS data into `hotel_daily`** — cannot be designed before Phase 3 names the software and its data access method. Becomes its own plan.
- **Vedanta ERP data integration** — same reason; Phase 6 only establishes connectivity.
- **Writing anything to site systems** — v1 is read-only. Any write capability is a separate decision with its own risk review.
- **Replacing the WhatsApp/vision-based hotel occupancy path** — it keeps running; the server feed supplements it until proven more reliable.
- **Site-to-site VPN or reconfiguring the Omada gateway** — the client-profile approach needs no changes at the hotel end.

## Approach

Run OpenVPN inside a dedicated Docker container with `NET_ADMIN`, never on the VPS host. A small HTTP proxy runs inside that same container; the MDO backend reaches hotel hosts by sending requests to `http://vpn-hotel:8888` as a proxy. The host's routing table is never modified, so a misconfigured or hostile route push cannot take the VPS off the internet — the worst case is that one container is broken while SSH, the website, the WhatsApp bridges and the agents keep running.

This mirrors the existing `sharecfo` bridge pattern (verified: `mdo_server.py` `_cfo_get`): a separate stack, joined by Docker networking, read through a narrow, configured URL. Executor's choice: container base image, proxy software, and internal file layout.

Why not the host: an OpenVPN client on the host applies pushed routes to the host routing table. The uploaded profile carries no `redirect-gateway`, but the server pushes routes at connect time and those are not visible until connection. A default-route push on the host would sever SSH mid-session with no way back in except the provider's console.

## Requirements

- **R1.** WHEN the `vpn-hotel` container starts, THE SYSTEM SHALL establish an OpenVPN connection to `182.65.204.86:1194` using certificate authentication with no interactive input.
  *Acceptance:* `docker logs vpn-hotel` contains `Initialization Sequence Completed`.
- **R2.** WHEN the tunnel is established, THE SYSTEM SHALL leave the VPS host routing table unchanged.
  *Acceptance:* `ip route` on the host, captured before and after, is identical (`diff` returns empty).
- **R3.** WHEN the tunnel is established, THE SYSTEM SHALL keep `https://amanagrawal.cloud` and SSH on `72.60.97.133` reachable from outside the VPS.
  *Acceptance:* an HTTP request from a machine other than the VPS returns 200, and a new SSH session opens.
- **R4.** WHEN the OpenVPN server pushes a default route, THE SYSTEM SHALL ignore it and route only site subnets through the tunnel.
  *Acceptance:* `docker exec vpn-hotel ip route` shows no `default` via the tun interface.
- **R5.** WHEN the MDO backend issues a request to a hotel LAN address through the proxy, THE SYSTEM SHALL return the site host's response.
  *Acceptance:* `docker exec mdo-platform-backend-1 curl -s -x http://vpn-hotel:8888 http://<site-host>/ -o /dev/null -w "%{http_code}"` prints a non-zero HTTP status.
- **R6.** WHEN the container or the VPS restarts, THE SYSTEM SHALL re-establish the tunnel without human action.
  *Acceptance:* after `reboot`, R1's check passes with no commands run in between.
- **R7.** WHEN the tunnel has been down for more than 10 minutes, THE SYSTEM SHALL deliver a 🔴 alert to the owner's WhatsApp.
  *Acceptance:* stopping the container causes an alert message to arrive within 15 minutes.
- **R8.** THE SYSTEM SHALL store VPN credentials outside version control.
  *Acceptance:* `git status` is clean after setup, and `git check-ignore -v vpn/` confirms the directory is ignored.
- **R9.** THE SYSTEM SHALL NOT write to, modify, or authenticate against site systems during v1.
  *Acceptance:* the discovery script issues only TCP connects and HTTP GETs, verifiable by reading it.

## Key Decisions

- Tunnel runs in a container, not on the host — [assumed: container isolation prevents host route changes — if wrong: R2's before/after `ip route` diff catches it in Phase 2 and the container is stopped] [A1]
- Backend reaches sites via HTTP proxy rather than shared routes — (verified: the `sharecfo` bridge already reads another stack through a configured URL, `mdo_server.py`)
- One container per site, not one holding both tunnels — (user: two separate `.ovpn` profiles) plus overlapping private subnets between two sites would be unresolvable in a single namespace
- Certificate-only auth, no credential prompts — (verified: uploaded `.ovpn` has no `auth-user-pass`)
- `pull-filter ignore "redirect-gateway"` guards against a default-route push — [assumed: `pull-filter` is available in the OpenVPN 2.x client — if wrong: use `route-nopull` plus explicit `route` lines for the subnets found in Phase 3] [A2]
- Client certificate is rotated before use — (user: original key was transmitted in chat; a fresh profile is required)
- v1 is read-only discovery — no site system is written to until its software is identified

## Data & State Changes

No schema changes in v1. The discovery inventory is written to `docs/SITE_INVENTORY_HOTEL.md` in the repo as plain text — no secrets, no personal data, host addresses and service banners only. Rollback is deleting the file. Storing site data in the MDO database begins in the parked follow-up plan, not here.

## Interfaces, Integrations & Credentials

- **New container** `vpn-hotel`: OpenVPN client plus HTTP proxy listening on port `8888` inside the compose network. No published host ports.
- **New backend environment variables** in `.env` (gitignored): `HOTEL_PROXY_URL=http://vpn-hotel:8888`, and later `VEDANTA_PROXY_URL=http://vpn-vedanta:8888`.
- **Credential files**: `vpn/hotel/client.ovpn` on the VPS only, mode `600`, added to `.gitignore`. Never committed, never pasted into chat.
- **External endpoint consumed**: `182.65.204.86:1194/udp` (verified: `remote` line in the profile).
- **Fixed contract not to break**: the existing `sharecfo_default` network join on `mdo-platform-backend-1` (verified: this session) must survive; adding networks must not remove it.
- Site system APIs: **unknown** — deliberately, because Phase 3 discovers them. No API shape is assumed anywhere in this plan.

## Edge Cases & Failure Handling

- OpenVPN server unreachable → container retries with backoff; backend proxy calls fail with a clear connection error, and MDO's other functions are unaffected.
- Server pushes a default route → ignored by R4's filter; logged.
- Site subnet overlaps the Docker bridge range → the container's own networking breaks and the proxy stops answering; detected in Phase 2, resolved by moving Docker's address pool, not by changing the site.
- Certificate expires or is revoked → tunnel fails to establish, R7's alert fires, log shows a TLS error.
- Proxy reachable but site host down → backend receives a proxy error distinguishable from a tunnel failure, because tunnel state is checked separately by the healthcheck.
- Tunnel up but no route to the target host → `ip route` inside the container is the diagnostic; the inventory records what was reachable when.
- Default posture: fail loudly. No silent fallbacks, no cached-stale answers presented as live.

## Risks, Landmines & Adaptations

- **A default-route push would sever the VPS** → the entire architecture puts the tunnel in a container so host routing is untouched (R2), and Phase 2 verifies the before/after routing table diff *before* anything depends on the tunnel.
- **Losing SSH access mid-change** → every phase is executed in a way that survives disconnection, and Phase 2 requires an external reachability check rather than trusting the current session. Rollback for any phase is `docker compose stop vpn-hotel`, which cannot fail from lack of connectivity because the host was never reconfigured.
- **The private key was transmitted in plain text** (verified: the uploaded files contain a full `<key>` block) → Phase 1 rotates the client certificate before the VPS uses it, and the exposed profile is never deployed.
- **1024-bit RSA and AES-128-CBC without `tls-auth`** (verified: `openssl` output and the profile) → recorded as a residual weakness of the site gateway; mitigated by rotating to a stronger key if the Omada controller offers it, otherwise accepted and noted, since changing the gateway's crypto is out of scope.
- **Site systems may hold guest personal data** → v1 reads nothing but service banners; any later data pull states what personal data it touches before it is built.
- **Scanning a live production network can disturb fragile devices** → Phase 3 uses a slow, connect-only scan of a limited port set, never a full-range or aggressive scan.
- **Residual risk: the Vedanta profile may differ materially** (different gateway vendor, or user-password auth) → Phase 6 re-verifies its directives before cloning, and the plan does not assume it matches.

## Assumptions Ledger

| ID | Assumption | Basis | Blast radius if wrong | Check |
|----|-----------|-------|----------------------|-------|
| A1 | A `NET_ADMIN` container cannot alter host routes | container isolation model | Host could lose connectivity — the worst outcome in this plan | Phase 2 diffs `ip route` before/after |
| A2 | `pull-filter ignore` is supported by the installed OpenVPN client | OpenVPN 2.x option set | A pushed default route reaches the container | Phase 2 checks `docker exec vpn-hotel ip route` for a default via tun |
| A3 | An OpenVPN client Docker image is available for linux/amd64 | container registries carry maintained OpenVPN images | Phase 2 stalls | Phase 2 step 1 pulls it and prints its version; fallback is a 6-line Dockerfile on `debian:stable-slim` installing `openvpn` |
| A4 | The Omada server pushes routes for the hotel LAN | typical OpenVPN server configuration | No route to site hosts; nothing is reachable | Phase 3 reads `ip route` inside the container; fallback is adding explicit `route` lines once the subnet is known |
| A5 | Hotel site hosts speak HTTP on a common port | site servers are usually web-administered | The HTTP proxy is the wrong access shape | Phase 3's scan records actual open ports; if the target speaks a database or SMB protocol, replace the HTTP proxy with a TCP forwarder in Phase 4 |
| A6 | The site subnet does not collide with Docker's `172.17–172.31` range | Docker's default pool | Container networking breaks on connect | Phase 3 compares the pushed subnet against `docker network inspect` output |
| A7 | The Omada controller can issue a replacement client certificate | the profile was generated by that controller (verified: certificate subject) | Rotation is impossible; the exposed key stays live | Phase 1 does this first; fallback is accepting the risk in writing and restricting the gateway by source IP |
| A8 | The VPS can reach `182.65.204.86:1194/udp` outbound | no egress restriction was observed on this VPS this session | Nothing connects | Phase 2 step 2 tests connectivity before building anything on top |

## Open Items (none blocking)

- Vedanta `.ovpn` profile — proceed with hotel-only; Phase 6 adds Vedanta unchanged if its directives match, or re-plans that phase if they differ.
- What the hotel server actually runs — proceed with discovery in Phase 3; the follow-up integration plan is written from its findings.
- Whether hotel data should replace or supplement the WhatsApp-derived occupancy figures — proceed with supplement, decided in the follow-up plan.

## Verification

Run these on the VPS unless stated otherwise. Substitute `<site-host>` with an address found in Phase 3.

```
# R1 tunnel established
docker logs vpn-hotel 2>&1 | grep -c "Initialization Sequence Completed"

# R2 host routing unchanged (compare against the file saved in Phase 2 step 1)
ip route > /tmp/route.after && diff /tmp/route.before /tmp/route.after && echo "ROUTES UNCHANGED"

# R4 no default route inside the container
docker exec vpn-hotel ip route | grep -c "^default.*tun" # expect 0

# R5 backend reaches a site host through the proxy
docker exec mdo-platform-backend-1 curl -s -o /dev/null -w "%{http_code}\n" \
  -x http://vpn-hotel:8888 http://<site-host>/

# R6 survives reboot (run after `reboot`, from a fresh session)
docker ps --filter name=vpn-hotel --format "{{.Status}}"

# R8 no secrets committed
git status --short && git check-ignore -v vpn/
```

**From a machine that is not the VPS** (R3 — this is the check that matters most):

```
curl -s -o /dev/null -w "%{http_code}\n" https://amanagrawal.cloud
ssh root@72.60.97.133 "echo reachable"
```

**How the owner personally confirms done:** open `https://amanagrawal.cloud` on a phone and see it load normally, then read `docs/SITE_INVENTORY_HOTEL.md` and recognise the machines listed as the hotel's own.

## Build Phases

- [ ] Phase 1: Rotate the exposed client certificate and place the new profile on the VPS
      Done when: `/docker/sharecfo/mdo-platform/vpn/hotel/client.ovpn` exists with mode `600`, contains a `<cert>` whose serial differs from the exposed one, and `git status --short` shows nothing.
      Steps:
      - In the TP-Link Omada controller, revoke client `client_server0` and create a replacement client profile; download it. [A7]
      - On the VPS: `mkdir -p /docker/sharecfo/mdo-platform/vpn/hotel && chmod 700 /docker/sharecfo/mdo-platform/vpn`.
      - Transfer the new `.ovpn` to `vpn/hotel/client.ovpn` (`scp` from the laptop), then `chmod 600` it.
      - Append `vpn/` to `.gitignore`, commit that one-line change.
      - Confirm the new certificate differs: `openssl x509 -in <(sed -n '/<cert>/,/<\/cert>/p' vpn/hotel/client.ovpn | sed '1d;$d') -noout -serial`.
      Covers: R8; checks: A7

- [ ] Phase 2: Bring up the isolated tunnel and prove the host is untouched
      Done when: R1, R2, R3 and R4 checks all pass, including the external reachability check run from a non-VPS machine.
      Steps:
      - `ip route > /tmp/route.before` on the host, and confirm outbound UDP reachability: `nc -uzv 182.65.204.86 1194` (a timeout here is inconclusive for UDP; proceed and let the tunnel be the real test). [A8]
      - Add a `vpn-hotel` service to `docker-compose.yml`: an OpenVPN client image [A3], `cap_add: [NET_ADMIN]`, `devices: [/dev/net/tun]`, `restart: unless-stopped`, mounting `./vpn/hotel/client.ovpn` read-only, with `pull-filter ignore "redirect-gateway"` supplied as a client argument [A2], plus an HTTP proxy process bound to `0.0.0.0:8888` inside the same container.
      - `docker compose up -d vpn-hotel`, then check the log for `Initialization Sequence Completed`.
      - Run the R2 route diff and the R4 in-container default-route check.
      - **From a different machine**, run the R3 external checks. If either fails, immediately `docker compose stop vpn-hotel` — the host was never modified, so this restores normal service.
      Covers: R1, R2, R3, R4; checks: A1, A2, A3, A8

- [ ] Phase 3: Discover what is reachable on the hotel network
      Done when: `docs/SITE_INVENTORY_HOTEL.md` lists every responding host with its open ports and any identified service, and names at least one host worth integrating.
      Steps:
      - `docker exec vpn-hotel ip route` — record the pushed subnets. If none appear, add explicit routes for the subnet the owner names. [A4]
      - Compare those subnets against `docker network inspect bridge` to rule out address collision. [A6]
      - From inside the container, sweep the subnet with a slow connect-only scan limited to common management and database ports; never a full-range or aggressive scan.
      - For each responding host, capture the HTTP title or service banner only — no authentication attempts, no writes. [A5, R9]
      - Write the inventory file and commit it (it contains no credentials).
      Covers: R9, G4; checks: A4, A5, A6

- [ ] Phase 4: Make the site reachable from the MDO backend
      Done when: the R5 check prints a non-zero HTTP status from a host identified in Phase 3.
      Steps:
      - Add `HOTEL_PROXY_URL=http://vpn-hotel:8888` to `.env` and pass it into the `backend` service environment in `docker-compose.yml`.
      - Ensure `backend` and `vpn-hotel` share a Docker network without disturbing the existing `sharecfo_default` join (verify with `docker inspect mdo-platform-backend-1` before and after).
      - `docker compose up -d backend`, then run the R5 check.
      - If the target speaks a non-HTTP protocol, replace the HTTP proxy with a TCP forwarder for that port and re-run. [A5]
      Covers: R5; checks: A5

- [ ] Phase 5: Survive restarts and alert when the tunnel drops
      Done when: after a full `reboot`, the R1 and R6 checks pass with no manual commands, and stopping the container produces a WhatsApp alert within 15 minutes.
      Steps:
      - Confirm `restart: unless-stopped` on `vpn-hotel`, and add a container healthcheck that pings a site host through the tunnel.
      - Add an hourly cron entry alongside the existing agent entries that checks tunnel health and, on failure, posts to the existing alert path (`POST /api/alerts/test` demonstrates the mechanism; use a tunnel-specific message).
      - `reboot` the VPS, wait, then re-run R1, R3 and R5 from a fresh session.
      - Stop the container deliberately and confirm the alert arrives; restart it.
      Covers: R6, R7; checks: A1

- [ ] Phase 6: Clone the pattern for Vedanta
      Done when: a `vpn-vedanta` container passes the same R1–R5 checks against the Vedanta network, and `docs/SITE_INVENTORY_VEDANTA.md` exists.
      Steps:
      - Obtain the Vedanta `.ovpn` and read its directives **before** copying anything — if it uses `auth-user-pass` or `static-challenge`, stop and re-plan this phase, because credential or one-time-code prompts break unattended operation.
      - Repeat Phases 1 through 4 with `vpn-vedanta`, `VEDANTA_PROXY_URL`, and its own credential directory.
      - Verify the two site subnets do not overlap; if they do, confirm the separate containers keep them isolated by testing a known host on each.
      Covers: R1–R5 for the second site; checks: A2, A4, A5, A6

**Note for the executor:** this plan stops at connectivity and inventory. Turning site data into MDO records is a separate plan, written from Phase 3's findings — do not design it speculatively.
