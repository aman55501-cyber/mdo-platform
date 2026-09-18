# LIFEOS — deploy to Railway

One surface, running 24/7 independent of your laptop. ~20 minutes end to end.

## 1. Create the service
- New Railway service from this repo.
- **Settings → Config-as-code**: point at `lifeos/railway.toml` (it builds
  `Dockerfile.lifeos`). Or set Build → Dockerfile Path = `Dockerfile.lifeos`.
- **Add a Volume** mounted at `/data` (the run history + tokens live here; without it
  the runs table resets on every redeploy).
- Health check path is already `/healthz`.

## 2. Set environment variables (Variables tab — never in code)

**Required to boot** (the app refuses to start without these):
| Var | What |
|---|---|
| `LIFEOS_USER` | any username you'll type once on your phone |
| `LIFEOS_PASSWORD` | a long random password — this is the only lock on the whole surface |

**Sources** (each missing one just makes that panel say UNREACHABLE — add them as you go):
| Var | How to get it |
|---|---|
| `NOTION_TOKEN` | notion.so/my-integrations → new internal integration → copy the token. Then open each of the 5 databases → `···` → Connections → add the integration. |
| `SUPABASE_URL` | Supabase project `sysicrpylpnzpcuvpvjc` → Settings → API → Project URL |
| `SUPABASE_KEY` | same page → `anon` (or a read-only `service_role`) key |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API keys (powers the ask bar) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Cloud → OAuth client (Desktop) |
| `GOOGLE_REFRESH_TOKEN` | OAuth Playground (gear → use your own client id/secret) with scopes `gmail.readonly`, `gmail.compose`, `calendar.readonly` → Authorize → Exchange → copy the refresh token |

**Sales / ERP exports (Google Drive)**:
| Var | What |
|---|---|
| `LIFEOS_GDRIVE_FOLDER_ID` | the id of the Drive folder `LIFEOS Sales Exports` (from its URL) |
| `GOOGLE_SERVICE_ACCOUNT` | a service-account JSON (one line) with read access to that folder — share the folder with the service account's email |
| `LIFEOS_ERP_DIR` | leave unset (defaults under the app); or `/data/erp_drop` to keep on the volume |

Create the Drive folder with **one subfolder per entity** (`VWLR/`, `Dadu Developers/`,
`Rukmani/`, …) and drop each ERP's CSV/XLSX inside. Each entity shows `OWED → MAP? →
LIVE`; when a real file first lands, send me its headers and I commit that entity's
`lifeos/mappings/<slug>.yaml`.

**Broker logins (Phase 5, optional, off by default)**: `LIFEOS_BROKER_LOGINS=1`
needs `shares_cfo` in the image and its `CFO_ACCOUNTS` / `HDFC_*` / `ANGEL_*` creds on
a shared token volume — a follow-up when you want it. Leave unset for the first deploy.

## 3. First boot checks
- `GET /healthz` → `ok` (Railway health check; no auth).
- Open the service URL in your phone browser → it prompts for the Basic auth you set →
  the console renders. Add it to your home screen.
- Force a run now: `POST /run` (with the same auth) → returns `{sources_ok, …}`.
- `GET /runs.json` → the run history; a row with `finished_at: null` means a run died.

## 4. Steady state
- The scheduler fires the full run at **06:30 IST daily**. The page is a snapshot from
  that run; the ask bar is the only live call.
- `capture:` / `remind:` in the ask bar file to your Notion Inbox; the next morning's
  run files them and drafts nudges for any gaps.

## Acceptance (all verified in tests; re-check on the live URL)
1. Break `NOTION_TOKEN` → Notion panels say UNREACHABLE, run still completes.
2. A day with no mail/events/tenders → every panel says so in words.
3. Kill the service mid-run → `/runs.json` shows a started row with no finish; next
   page shows the "previous run did not complete" banner.
4. Open at 390px → no horizontal scroll; ask bar reachable by thumb.
5. Force dark mode → every colour resolves.
6. `grep -rE "(sk-|ghp_|AIza|password\s*=|token\s*=)" --include=*.py lifeos/` → only
   `os.environ` reads.
7. Run twice → the served page is the second run's; the Archive gets one line per run.
