# Cowork prompt: collect the source reports (copy everything inside the box)

```
ROLE
You are collecting official reports from my own financial accounts so that a private
app can later read them. You only DOWNLOAD. You never change anything.

HARD RULES (breaking any of these = stop and tell me)
1. Credentials: never type, guess, store or read back a username, password, PIN, OTP,
   TOTP or security answer. When a login page appears, STOP and say "Ready for your
   login on <site>". I will type it myself. Continue only after I say "done".
2. Read-only: never click anything that buys, sells, transfers, pays, adds a payee,
   changes a limit, a mandate, a password, a nominee, an e-mail or a phone number, or
   that "approves" or "authorises" anything. Only open reports and download.
3. No numbers from memory: never type, edit, round or retype figures. Save files
   exactly as the site produces them. Do not rename the contents, only the file name.
4. If a screen differs from what I describe, a report is missing, or a site shows an
   error: stop on that item, write it in the manifest as BLOCKED with the exact message,
   and go to the next item. Do not improvise or try other menus for long.
5. Privacy: save files ONLY in the folder below. Do not upload, e-mail, message or
   paste any file or figure anywhere. Do not summarise balances or holdings in chat;
   just say what was downloaded.
6. If a PDF asks for a password, do not try to guess it. Mark it NEEDS_PASSWORD.
7. Stop after 3 failed attempts on any one site and move on.

REPORTING WINDOW
Everything starts on 1 April 2026 (01-Apr-2026) and runs to today. Where a site asks for
a date range, use From 01-Apr-2026, To today. Where a report is a snapshot (holdings,
balance), get TWO: one as of 31-Mar-2026 (the opening position) and one as of the latest
date. If a site cannot give a snapshot for 31-Mar-2026, mark it BLOCKED and say so. Do not
download anything older than 01-Apr-2026 unless I ask, except the 31-Mar-2026 snapshots.

FOLDER
Create  ~/Documents/capital-intake/<today YYYY-MM-DD>/  and one sub-folder per source
(hdfc-sec-aman, hdfc-sec-sudha, hdfc-sec-ashok, angel-aditi, cdsl, nsdl, mf-cams,
mf-kfintech, bank-<last4>, loans, cards, fd, other).

FILE NAMES
<source>_<account or client code>_<report type>_asof-<YYYY-MM-DD>_got-<today>.<ext>
Keep the original extension (CSV or XLSX preferred; PDF if that is all there is).

TASKS (do them in this order; ask me to log in before each site)
A. HDFC Securities, three separate logins: Aman (HDFC1), Sudha (HDFC2), Ashok (HDFC3).
   For each: 1) Holdings / Demat holdings: as of 31-Mar-2026 and as of the latest date, CSV or Excel.
   2) Tradebook / order & trade history, 01-Apr-2026 to today.
   3) Realised P&L / Capital gains for financial year 2026-27 (01-Apr-2026 onward).
   4) Ledger / funds statement, 01-Apr-2026 to today (with the opening balance line).
   5) Contract notes, 01-Apr-2026 to today, only if the site lists them.
B. Angel One, client A1504046 (Aditi Investments): holdings (31-Mar-2026 and latest),
   tradebook, P&L / capital gains for FY 2026-27, ledger, all from 01-Apr-2026 to today.
C. Depository statements: CDSL e-CAS and NSDL e-CAS, the consolidated statement for
   the period 01-Apr-2026 to today, plus the one as of 31-Mar-2026, for each PAN I name when we get there (Aman, Sudha, Ashok, Aditi Investments).
D. Mutual funds: CAMS and KFintech consolidated statement (detailed, all folios)
   for 01-Apr-2026 to today, plus the closing-unit statement as of 31-Mar-2026, for each PAN. These come by e-mail: request them only to the address
   the site pre-fills, then tell me to approve the mail myself.
E. Banks: for EACH of these accounts, the statement from 01-Apr-2026 to today as CSV or
   Excel (PDF only if nothing else). It must show the OPENING balance on 01-Apr-2026 and
   the latest closing balance: 2484, 1128, 6710,
   2231, 5555. Ask me which bank and which login each one belongs to. Record in the
   manifest the account holder name exactly as the bank shows it (this settles ownership).
F. Liabilities: loan account statements and sanction/schedule pages for every loan,
   and every credit card statement from April 2026 onward. Ask me for each lender.
G. Fixed deposits and other holdings: the FD list or certificates from each bank, and
   PMS, PPF, EPF, NPS statements only if I say I want them.

AFTER EACH ITEM
Add one row to  MANIFEST.csv  in today's folder with these columns:
source, account_or_client, report_type, as_of_date, period_from, period_to,
file_name, status (OK / BLOCKED / NEEDS_PASSWORD / SKIPPED), note
Never put any figure, password or personal number other than the last 4 digits of an
account in the manifest.

WHEN FINISHED
List the files and the manifest rows with status other than OK, and which reports I
still have to supply by hand. Do not interpret the data. Then stop and wait for me.
```

After it finishes: put the whole dated folder in the private Drive folder "Capital Intake"
(or the server drop folder) and tell Claude Code. Do not paste any file into a chat or group.
