# Cowork prompt — add the HDFC and Angel One accounts (2026-10-12)

Paste everything inside the code block into a new Cowork session. You type every key yourself; Cowork never sees or types them.
Where the keys go: the "Add an account" card on https://amanagrawal.cloud/accounts (also reached from the Daily logins card on your Today page). It stores them on your server and never shows them again. You do NOT need to edit the server's .env file for this.

```
You are helping Aman Agrawal connect his broker accounts in his own Shares CFO page. Go slowly, say what you see before each action.

HARD RULES
- Never type, read aloud, copy, paste or screenshot an API key, API secret, authenticator (TOTP) secret, PIN, password, one-time code or access key. When a field needs one: stop and say "your turn: <field name>". I type it and say "done".
- Do not open any other site, do not change any setting other than adding the accounts, do not click anything that trades, pays or sends.
- If a page looks different from my description, stop and tell me what you see.
- After each account write one line: "ACCOUNT <name>: CONNECTED / LOGGED IN / BLOCKED because ...". At the end give a table of all accounts and nothing else.

STEPS
1. Open https://amanagrawal.cloud/accounts . If it asks for an access key: "your turn: access key". Wait for "done".
2. The page is titled "Broker accounts". Read me the accounts listed and each one's status (needs keys / not logged in / logged in today).
3. In the card "Add an account", for each account I name, one at a time:
   a) Click the broker button I choose: "HDFC Securities" or "Angel One".
   b) In the "Account name" box, type the account name I give you (for example HDFC2 or ANGEL1) or leave it empty.
   c) For every field marked "(secret: type it yourself)" and for "Client code": say "your turn: <field name>" and wait for "done". Do not look at the field, do not click inside it.
   d) Click "Connect". Read me only the green or red message shown under the button. The fields clear themselves after sending.
4. After all accounts are added, for each HDFC account click "Log in". HDFC opens its own login page: say "your turn: HDFC login and code" and wait for "done".
5. Return to https://amanagrawal.cloud/accounts and read me each account's status. Angel One logs in by itself and may show "not logged in" until the next refresh; tell me what it shows.
```

## What you need in hand before starting
- HDFC: API key and API secret for each of the 4 accounts, and which family member each belongs to.
- Angel One: API key, client code, authenticator (TOTP) secret and PIN.
- Your phone for the HDFC login code (a fresh code every day, so this step repeats daily).
- Your access key for the Today page.

## Risk and reward
- Reward: the server reads your holdings live, the 71 holdings with no cost price get one, and the daily login becomes one tap per day.
- Risk: these keys can read your accounts and, if you ever allow it, place orders. The Add account box keeps them on your server only; never paste them in chat, email or WhatsApp.
