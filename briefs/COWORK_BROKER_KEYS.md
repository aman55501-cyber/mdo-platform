# Cowork prompt — add the HDFC and Angel One accounts (2026-10-12)

Paste everything inside the code block into a new Cowork session. You type every key yourself; Cowork never sees or types them.
Where the keys go: the Shares CFO "Add account" box (opened from the Daily logins card on your Today page). It stores them on your server and never shows them again. You do NOT need to edit the server's .env file for this.

```
You are helping Aman Agrawal connect his broker accounts in his own Shares CFO page. Go slowly, say what you see before each action.

HARD RULES
- Never type, read aloud, copy, paste or screenshot an API key, API secret, authenticator (TOTP) secret, PIN, password, one-time code or access key. When a field needs one: stop and say "your turn: <field name>". I type it and say "done".
- Do not open any other site, do not change any setting other than adding the accounts, do not click anything that trades, pays or sends.
- If a page looks different from my description, stop and tell me what you see.
- After each account write one line: "ACCOUNT <name>: CONNECTED / LOGGED IN / BLOCKED because ...". At the end give a table of all accounts and nothing else.

STEPS
1. Open https://amanagrawal.cloud/today . If it asks for an access key: "your turn: access key". Wait for "done".
2. Find the card "Daily logins". Tell me which accounts it lists and whether each says logged in, not logged in or needs keys.
3. Tap "Log in to all accounts". A page titled "Shares CFO - accounts & login" opens. Tell me what is listed.
4. Scroll to the "Add account" box. For each account I name, one at a time:
   a) Ask me for the account name (examples: HDFC1, HDFC2, HDFC3, HDFC4, ANGEL1) and which family member it belongs to. Type only the account name into the name field.
   b) For each remaining field (API key, API secret, client code; for Angel One also authenticator secret and PIN): say "your turn: <field>". Wait for "done". Do not look at the field.
   c) Click Connect. Read me only the message shown (for example "connected"). If it shows an error, read me the error text, not any field.
5. After all accounts are added, go back to the list. For each HDFC account click "Log in". HDFC opens its own login: say "your turn: HDFC login and code" and wait for "done". Angel One logs in by itself; tell me what it shows.
6. Reload the Today page and read me the Daily logins card: how many accounts are in.
```

## What you need in hand before starting
- HDFC: API key and API secret for each of the 4 accounts, and which family member each belongs to.
- Angel One: API key, client code, authenticator (TOTP) secret and PIN.
- Your phone for the HDFC login code (a fresh code every day, so this step repeats daily).
- Your access key for the Today page.

## Risk and reward
- Reward: the server reads your holdings live, the 71 holdings with no cost price get one, and the daily login becomes one tap per day.
- Risk: these keys can read your accounts and, if you ever allow it, place orders. The Add account box keeps them on your server only; never paste them in chat, email or WhatsApp.
