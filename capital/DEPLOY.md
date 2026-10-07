# Capital desk — deploy and switch on

What you get: a private phone page. Opens on the Desk (gainers, losers, ideas, Bantu's calls). Net worth is a
separate tab behind a PIN. The web app only reads; it cannot move money or send messages.

## 0. Already done (live in Supabase `aman-control-room`)
Tables and views from `capital/migrations/0001_capital_c0_up.sql` are applied. To undo: `0001_capital_c0_down.sql`.

## 1. Put these in the server's `.env` (names only here; you type the values)
| Name | What |
|---|---|
| `DATABASE_URL` | Supabase -> Connect -> **Session pooler** URI, with your real DB password in it |
| `CAPITAL_USER`, `CAPITAL_PASSWORD` | the login for the page (long password) |
| `CAPITAL_PIN` | 4-8 digits for the Net worth tab |
| `CAPITAL_COOKIE_SECRET` | any random 32+ characters |
| `CAPITAL_CFO_URL`, `CFO_API_TOKEN` | for the **Daily login** tab: the shares_cfo server address and its existing token |

## 2. Run the web app (HTTPS is required: the login and PIN must never travel over plain http)
VPS (recommended): build `Dockerfile.capital`, run it on port 8700 beside the existing Caddy, and add to the Caddyfile
`capital.<your-domain> { reverse_proxy capital:8700 }`. Railway also works: service from `Dockerfile.capital`, set the variables above.

Check: `/healthz` returns `ok`; `/` asks for the login; `/networth` shows a PIN box.

## 3. Turn on the two jobs (server cron; the existing `mdo-run` wrapper reports failures to Telegram)
Server time is UTC; the market is 03:45-10:00 UTC, Mon-Fri.
```
*/10 * * * *      cd /opt/capital && /opt/mdo-server/bin/mdo-run bantu_calls python3 -m capital.jobs.parse_calls
*/5 3-10 * * 1-5  cd /opt/capital && /opt/mdo-server/bin/mdo-run quote_poll python3 -m capital.jobs.quote_poll
```
**quote_poll has not been run against the live Angel API yet.** Run it once by hand and read the output first:
`cd /opt/capital && python3 -m capital.jobs.quote_poll --force`. It needs these names in `.env`:
`ANGEL_ADITI_API_KEY`, `ANGEL_ADITI_CLIENT_ID`, `ANGEL_ADITI_PIN`, `ANGEL_ADITI_TOTP_SECRET`
(or set `CAPITAL_ANGEL_PREFIX` to match the names you already use). Missing names are reported by name only.

When both run cleanly, let the health monitor watch them:
`update wb.job_schedule set active = true where job in ('bantu_calls','quote_poll');`

## 4. What will look empty or old until you act
- **Bantu's feed** is only as fresh as the wa1 WhatsApp session. It has been disconnected since 26 Sep: re-link it (QR scan).
- **Gainers/losers** show the last completed move until quote_poll is running in market hours.
- **"Already held"** sees only the Angel account today. Give me the HDFC holdings (or the HDFC export) and the check covers
  Aman, Sudha and Ashok too. Until then you can list them in `wb.manual_holdings`.
- **Net worth** is partial by design and lists every gap on the page.


## 4. Bantu's calls (already filled once)
On 7 Oct the 10 calls found in the real WhatsApp messages (22-25 Sep) were loaded into `wb.calls`. They carry
`needs_review = true` because the ticker list could not be fetched from the build sandbox. The first run of
`parse_calls` on the server fetches it, matches names to tickers (KSCL etc.), and clears the flag for the clear ones.
Company names such as "Bandhan Bank" stay unmatched until you confirm them; nothing is guessed.

## 5. Daily login tab
Shows one row per demat. HDFC rows have a **Log in** button that sends you to HDFC's own page; Angel signs in by itself.
The page never sees your password or OTP.
