# Go-live: fix every dead or empty state (7 Oct 2026)

Legend: DONE = already fixed. YOU = needs you or the server. Do them in this order.

## DONE (by Claude, verified)
- Bantu's calls panel: 10 calls loaded into `wb.calls` from the real messages. They show on the Desk now.
- Held stocks are marked "you hold this", never removed.
- Daily login tab built and tested.
- Parser fixed for Bantu's real message styles; 100 tests pass.

## 1. Deploy the app (YOU, ~15 min) - nothing else works for you until this is done
See `capital/DEPLOY.md` sections 1-2. Needs the Supabase **Session pooler** address with your DB password,
the login, PIN, cookie secret, and `CAPITAL_CFO_URL` + `CFO_API_TOKEN` for the Daily login tab.

## 2. Live prices (YOU, on the server)
1. `cd /opt/capital && python3 -m capital.jobs.quote_poll --force`   (not yet run against the live Angel API - read the output)
2. If it says a name is missing, add that name to `.env` and run again.
3. Add the two cron lines in DEPLOY.md section 3.
4. `update wb.job_schedule set active = true where job in ('bantu_calls','quote_poll');`
Until then the Desk says "No live quotes right now", which is honest.

## 3. Tickers for Bantu's calls (automatic once step 2 is done)
The first `parse_calls` run on the server matches names like KSCL. Company names (Bandhan Bank, RBL Bank,
India Glycols, Adani Power, APL Apollo) stay "needs review" - tell me the tickers and I will set them.

## 4. Telegram alerts (YOU, ~10 min)
1. @BotFather -> /mybots -> your bot -> Bot Settings -> Group Privacy -> **Turn off**.
2. Remove the bot from "AMAN Control Room", add it back as admin.
3. Post `hi` in each of the 7 topics.
4. On the server, in `claude`: "run getUpdates and fill wb.channel_map with the chat id and the 7 topic ids".
The 61 failed alert rows stop by themselves once channel_map is filled.

## 5. WhatsApp wa1 (YOU, 2 min)
Re-scan the QR for wa1. Bantu's feed has been silent since 26 Sep (about 11 days) and no new calls arrive until you do.

## 6. Backend crash (YOU, on the server)
`mdo_brain.py` is not in this repo, so I could not change or test it. On the server, in the checkout where it lives:
set the `mcp` line of the requirements file that image uses to `mcp>=1.10.0,<2`, rebuild, and check the container
stops restarting. This is a likely fix, not a verified one.

## 7. Data only you have
- HDFC holdings (Aman, Sudha, Ashok): send the export, or I put them in `wb.manual_holdings`. Until then the held-marker
  and net worth cannot see them.
- Balances for accounts 1128 and 6710, liabilities, other assets.
- Plan levels / targets (old `levels.yaml` is stale; not imported).
- Two questions: is the Aditi account personal or company? Who owns HDFC 2231 and 5555?
- The two old ideas (STLNETWORK, VAML): keep or close?

## 8. Every morning
Open the Daily login tab. Angel is automatic. Tap Log in for each HDFC row; HDFC's own page asks for your password.
