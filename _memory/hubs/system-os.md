# SYSTEM OS hub (append only, newest first)

## 2026-10-12 · feeds-list verification vs LIFE_LLM_TREE.md (checkout claude/determined-einstein-hmp597 only)
Method: Glob/Grep/Read on working tree. No Bash/git and no Agent tool in this run, so remote branches (claude/nifty-darwin-j8xylv, claude/shares-cfo-hdfc-setup-wrlqaj) were NOT read. No helpers spawned.

| system | verdict | path / evidence |
|---|---|---|
| tender pipeline | EXISTS (partial) | /home/user/mdo-platform/vega/vedanta/tender_watch.py (Grok poller); Tender247 only as config/seed strings in mdo_server.py. NIT eligibility, tender-radar: NOT FOUND in tree. VPS tender_candidates DB is outside repo [UNVERIFIED] |
| VWLR daily report | UNCLEAR | mdo-app/app/vwlr/page.tsx, mdo_server.py briefing routes; no dedicated report job located |
| VPN sidecars | EXISTS | /home/user/mdo-platform/vpn/ (Dockerfile, entrypoint.sh, tinyproxy.conf, vedanta/ and hotel/ only .gitkeep); docker-compose.yml services vpn-hotel, vpn-vedanta. FOIS: only strings in mdo_server.py, no sidecar dir. Tunnel validation unverified |
| WhatsApp bridge | EXISTS | /home/user/mdo-platform/whatsapp_bridge/ (index.js, server.js); docker-compose services whatsapp x2. LIFE_LLM_MAP says Chromium bridge is parked |
| Shares CFO | NOT FOUND on this checkout | only CFO_API_URL=http://sharescfo:8000 in docker-compose.yml. Session index says it lives on branch claude/shares-cfo-hdfc-setup-wrlqaj [UNVERIFIED, branch unread] |
| capital service | NOT FOUND on this checkout | no match; likely same branch [UNVERIFIED] |
| CFO MCP server | NOT FOUND on this checkout | session index: branch claude/mcp-setup-config-xxopjm (bc54e65), not one of the two named branches [UNVERIFIED] |
| Share Master bot | UNCLEAR | no "share master" string in tree. vega/telegram_bot/ exists (bot.py, handlers.py) and may be it; not confirmed |
| Staah | UNCLEAR | UI link/seed only: mdo-app/app/hotel/page.tsx, mdo_server.py. No connector; LIFE_LLM_MAP says token still missing (manual entry) |
| compliance calendar | EXISTS | mdo_server.py /api/compliance/filings (lines ~1124-1136), mdo-app/app/compliance/page.tsx |
| librarian | EXISTS | /home/user/mdo-platform/.claude/agents/librarian.md; output _memory/session-index.md (last sweep 2026-10-12) |
| memory | EXISTS (thin) | /home/user/mdo-platform/_memory/ holds session-index, LIFE_LLM_TREE, LIFE_LLM_SESSION_MAP, a Market_Desk xlsx. entity-registry.md, _log.md missing. Notion/reminders not in repo |
Also: Mausaji parser, Yahoo prices (vega/data/external_feeds.py has feed code, unchecked), HDFC (vega/broker/*, scripts/test_hdfc_auth.py) partially present. Agents chief-of-staff and orchestrator: no files here; session index points to branches claude/chief-of-staff-bot-4i2jyz, claude/orchestrator-skeleton-setup-bsM0V.
Feed heartbeat: no feed in the repo reports "0 new" that I could find.
