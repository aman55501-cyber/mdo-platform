# Cowork prompt — Aman's pending clicks (drafted 2026-10-10)

Paste everything inside the code block into a new Cowork session (laptop, Chrome connected). It does the browser
and file work; it stops for you at every login, one-time code, key, payment and signature.

```
You are helping Aman Agrawal clear a list of setup clicks, one at a time, in order. Work slowly and show me what
you see before each action.

HARD RULES
- Never type, read aloud, copy, store or screenshot a password, one-time code, API key, API secret or token. When a
  page needs one, STOP and tell me "your turn: <what>". I type it. You continue when I say "done".
- Never pay, subscribe to a paid plan, book, sign, submit a regulator filing, or send an email or message. Free
  plans only. If a step would cost money or needs a signature, stop and tell me.
- If a page looks different from my description, stop and tell me what you see. Do not improvise.
- After EACH task, write one line: "TASK n: DONE / BLOCKED because ... / SKIPPED by Aman". At the very end, give
  me a table of all tasks with that status and nothing else.

TASK 1 — UptimeRobot (free monitor that alerts me if my server dies)
1. Open https://uptimerobot.com. If I have no account, click Register; use aman.55501@gmail.com; pause for me to
   set the password and verify the email.
2. Dashboard -> "+ New monitor". Type: Keyword. Friendly name: MDO fleet.
   URL: https://amanagrawal.cloud/api/health/public
   Keyword: "ok":true  (with the quotes)  — alert when the keyword DOES NOT EXIST.
   Interval: 5 minutes. Alert contacts: email ticked.
3. Create monitor. Wait up to 2 minutes. Success = status shows "Up". Tell me if it shows "Down".
4. Tell me to install the UptimeRobot phone app and log in (I do that on my phone).

TASK 2 — HDFC Securities API keys for four accounts, one at a time
Accounts in order: Aman (4016900), Ashok, Sudha, Aditi. For each:
1. Open https://developer.hdfcsec.com. Pause: I log in as that account (password and OTP are mine).
2. Create an app. Name: mdo. Redirect URL: https://amanagrawal.cloud
3. Show me the API key and API secret ON SCREEN ONLY. Do not copy them anywhere.
4. Open https://hpanel.hostinger.com -> my VPS -> Terminal. Pause for me to log in if asked.
5. Type this line WITHOUT pressing Enter, with N = 1 for Aman, 2 Ashok, 3 Sudha, 4 Aditi, and leave the two
   CAPITAL placeholders for me to type myself:
   cd /docker/sharecfo/mdo-platform && printf '\nHDFC_HDFCN_API_KEY=APIKEY\nHDFC_HDFCN_API_SECRET=APISECRET\n' >> .env && echo saved
   (For accounts 2-4 use the variable names the .env.example in that folder shows for account N; if you cannot
   tell, stop and ask me.)
6. I replace the placeholders and press Enter. It must print "saved". Then next account.
At the end run in the terminal:  docker compose restart sharescfo   and tell me which of the four said "saved".

TASK 3 — Angel One holdings file (for the Share Master Portfolio tab)
1. Open Angel One's web app. Pause for me to log in.
2. Find Holdings (or Reports -> Holdings / DP Transaction cum Holding Statement). Download the holdings file
   (CSV or PDF) to my Downloads folder. Tell me its file name.
3. Open https://amanagrawal.cloud -> Morning -> Share Master -> "Import holdings". Holder: pick the Angel One
   account holder I tell you. Upload the file. Report the import result line it shows. If asked for a PDF password
   (my PAN), pause for me.

TASK 4 — Move my laptop memory and finance folders to my server's vault (one-time)
1. Do NOT run anything until I say "go". First show me: the two laptop folders you found
   (C:\Users\Owner\Desktop\BUSINESSES\_memory and C:\Users\Owner\claude master\finance — tell me if either is
   missing) and how many files each holds.
2. On "go": in PowerShell run these two (the server password or key is mine to type when it asks):
   scp -r "C:\Users\Owner\Desktop\BUSINESSES\_memory" root@72.60.97.133:/docker/sharecfo/mdo-platform/vault-import/memory
   scp -r "C:\Users\Owner\claude master\finance" root@72.60.97.133:/docker/sharecfo/mdo-platform/vault-import/finance
3. In the Hostinger terminal run:  cd /docker/sharecfo/mdo-platform && sudo bash vault_import.sh
   Report the two "files now in vault" lines it prints. Do not delete or rename anything on my laptop.

TASK 5 — Notion: mark four old pages retired (ask me first)
Ask me: "Stamp these 4 Notion pages 'Retired 2026-10-09: the VPS fleet is the CoS'? (CoS Board, Grok Desks manual,
Claude CoS Handoff, Grok->Claude relay) yes/no". Only on "yes": add that sentence as the first line of each page.
Change nothing else. Report the four page links.

TASK 6 — Claude settings I asked for earlier (connectors and skills)
Open claude.ai Settings. Show me the list of enabled plugin packs and skills. Do not change anything. Tell me which
plugin packs I have enabled that I could switch off to cut clutter (e.g. ones for sales, marketing, HR, legal that
I do not use), and wait for me to say which to turn off before you click anything.

NOT FOR YOU (do not attempt): Las Vegas flight/hotel booking, anything involving money, the battery counterparty
research, the Grok subscription decision.
```
