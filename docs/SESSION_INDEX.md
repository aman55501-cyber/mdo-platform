# Claude session index (arranged 14 Oct 2026)

Source: the session list (titles, tags, post-turn summaries, usage fields). "Cost" is the API-equivalent `cost_usd` field, not a bill.
Total across the 16 sessions listed: about $598. Three Opus/Fable sessions = 75% of it. The share-lane sessions = 21%.

## mdo-build (platform)
| Session (date, branch) | State | Cost | Next action |
|---|---|---|---|
| 07 Oct chief-of-staff bot (`claude/chief-of-staff-bot-4i2jyz`) | FAILED: out of usage credits mid-build | $327 | Review what was pushed before re-running anything. 55% of all spend sits here. |
| 11 Oct Librarian sweep (`claude/determined-einstein-hmp597`) | Review-ready; offered Syncthing notes, cron file, run wrapper, `/today` endpoint | $5 | Say go; you run the commands in the Hostinger browser terminal |
| 12 Oct Work sequencing and model selection (`claude/friendly-wright-x9x4nj`) | Done: Sonnet default, Opus only to plan, deterministic work as scripts/cron | $0.3 | Adopted in agents/MODEL_ROUTING.md |
| 08 Oct housekeeping test (`claude/ecstatic-mccarthy-u50za9`) | `tests/test_housekeeping.py` left uncommitted | $1.9 | Commit or delete |
| 01 Aug ShareCFO + Life LLM merge (`claude/sharecfo-life-llm-merge-8www96`) | Review-ready export | $16.6 | Keep as reference |
| 24 Jul Life LLM system map (`claude/life-llm-map-build-3oifuz`) | BLOCKED: needs two `ip route` outputs from the VPS | $54.6 | Run step 3 on the VPS, paste output (also unblocks the hotel VPN) |
| 24 Jul CFO MCP server (`claude/mcp-setup-config-xxopjm`) | Committed; PR decision pending | $3.5 | Decide: PR or leave |
| 23 Jul Business OS (`claude/business-os-extraction-qhtyke`) | BLOCKED: heartbeat never built. Its question "confirm Rashi Steel status" is answered: sold before 2020. | $4.2 | Superseded by mdo-heartbeat |
| 14 Jul Memory folder + reminders (`claude/elegant-lovelace-7s2tim`) | Review-ready: Notion maintenance + compliance DB, 16 calendar reminders armed | $6.5 | Verify the reminders still match reality |
| 03 May / 02 May orchestrator, plan, five-agent build | Stale (Railway pending, push blocked) | n/a | Archive after you confirm nothing needed |

## family-finance
| 11 Aug Life LLM progress (`claude/life-llm-aman-progress-ekpl8a`) | BLOCKED: 5 answers pending: broker registers, `_memory/` path on VPS, source-of-truth rule (MDO vs MProfit vs Excel), 5 design questions, ITR follow-up for ANS Group HUF | $10.9 | Answer (broker registers = share lane, Grok) |
| 23 Jul Life OS extracted (`claude/life-os-extraction-w73wq5`) | BLOCKED: subfolder or own repo? | $3.6 | One-word decision |

## vwlr (tenders)
| 08 Jul tender refresh (`claude/vwlr-tender-map-flutter-ah6zxy`) | Awaiting "apply v1.2" (reject categories, re-score); 21 live candidates, 6 junk | $24.3 | Decide, or retire the daily sync |
| 08 Jul coal tender map APKs (`claude/gifted-cannon-obw66r`) | Done | $13.1 | None |
| 02 Mar tender intelligence system | Done | n/a | None |

## investing: SHARE LANE, Grok's now (tagged `lane:grok`)
| 10 Oct Mausaji 128-stock list | Completed | $64.7 | Hand to Grok. Its last turn also holds travel advice: no live 21 Oct fare found, book a 17:00-19:00 non-stop up to about Rs 8,500; check hotels 21-25 Oct directly. That covers the expo trip (22-24 Oct, Greater Noida): confirm it is booked. |
| 12 Jul five-demat holdings coverage | Needs input (GO_LIVE.md question) | $57.8 | Grok |

## Limit position (from session records)
Weekly (7-day) limit shows `allowed_warning` and resets about 17 Oct 09:30 IST. Earlier sessions hit `rejected` (10-12 Oct) and one was in overage.
