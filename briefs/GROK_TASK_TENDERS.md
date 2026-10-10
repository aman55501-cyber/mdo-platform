# Grok task — daily tender sweep (replaces the Tender247-only block of "Grok tasks v2")

Paste into Grok → Tasks → new scheduled task, **daily 08:30 IST**. Log in to Tender247 once in Grok's browser
(your credentials stay inside Grok; they are never shared with the fleet, the repo or chat).
Replace `<TOKEN>` with GROK_CONTEXT_TOKEN from the VPS `.env`.

```
Daily tender sweep for Aman Agrawal (VWLR coal washery / RCR / coal handling, Raigarh-Korba-Talcher belt).

1. Open https://amanagrawal.cloud/api/grok/context?k=<TOKEN> first. It lists the objectives, the buyers of
   interest and what is ALREADY KNOWN. Do not re-report anything already known.
2. Search these, newest first, last 3 days of publication, for: washery, coal washing, beneficiation, RCR,
   road cum rail, coal transportation, coal loading, rake loading, siding, surface transport, crushing,
   overburden:
   - Tender247 (logged-in session): saved searches and keyword search
   - GeM bids: https://bidplus.gem.gov.in/all-bids
   - Coal India and subsidiaries (SECL, WCL, MCL, NCL, CCL, BCCL, ECL): https://coalindiatenders.nic.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page and each subsidiary's tender page
   - NTPC: https://ntpctender.ntpc.co.in/
   - Central portal: https://eprocure.gov.in/eprocure/app?page=FrontEndLatestActiveTenders&service=page
   - Chhattisgarh state e-procurement [UNVERIFIED address — search for "CG eProcurement"]
3. Email aman.55501@gmail.com. Subject exactly: [GROK-TENDER] <today's date>
   Body: ONLY a pipe-separated table, header row first, one row per tender:
   buyer|title|tender id|category|publish|closing|value|EMD|eligibility|location|URL
   Dates YYYY-MM-DD. A value the source does not state stays blank. A URL on every row.
   If nothing qualifies, the body is exactly: NONE FOUND
Rules: read only. Never submit a bid, pay, register, or download a paid document. Never invent a row.
```

What happens next (no clicks, no Claude credits): the VPS mail reader picks the email up within 30 minutes,
files each row into the tender pipeline (source `grok`, duplicates ignored), sends ONE WhatsApp line when there
are new rows, and the daily heartbeat says "grok N" even on a NONE FOUND day. If no [GROK-TENDER] email
arrives for a day, that shows as a gap in the mail-reader heartbeat.
