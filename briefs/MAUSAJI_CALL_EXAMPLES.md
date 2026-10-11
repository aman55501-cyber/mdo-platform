# Mausaji call examples — format study (Aman, chat 2026-10-11)
Source: pasted by Aman in chat as examples of the calls; sender assumed Bantu Mausaji [UNVERIFIED - Aman did not name the sender]. Stored verbatim; nothing here is an order. Rules that apply: never book a loss, ideas only above 80% conviction, Aman approves each order, holder column on every share list.

## Verbatim
1. Research note: "We are studying Neogen chemicals which is a bet on lithium battery chemicals ... battery unit ... Rs 19 crore revenue in Q1 FY27, up from Rs 5 crore a year ago ... Rs 2,500-2,950 crore peak revenue by FY29 ... Rs 600 crore fund raise ... Will keep updated."
2. Short calls in Hinglish: "added tega and beml - slowly and slowly" · "hearing v strong earnings from Acutaas (AMI)" · "Guj heavi chemical" · "Har girte bhav me sip karo 20-20 lo jyada nahi to" · "Birlashoft by this time & waiting" · "Reliance 1170 par mil raha hain buy zone 1140-1180" · "Invest in pricol @660 and sleep for 1 year" · "Hind zinc by 540/- 550/-" · "Shell 590/- 620/-" · "Jsw infra 330/- by" · "Shelling 370/- & again by 330/-"
3. Forwarded tip format: "DARK HORSE ... LOOKING VERY GOOD *BUY # MMWL @ 20.40-20.50* (MEDIA MATRIX WORLDWIDE LTD) POSITIONAL CALL" · "*BUY # SHANTI GOLD* @ 380-381"

## What the parser should read from them (to be confirmed by Aman)
| Text | Ticker | Action | Price / zone | Horizon | Confidence in reading |
|---|---|---|---|---|---|
| Neogen Chemicals note | NEOGEN | watch (no action) | - | - | clear: research, not a call |
| added tega and beml | TEGA, BEML | bought (Mausaji's own) | none | slow accumulation | clear |
| Acutaas (AMI) | ACUTAAS | watch (earnings expected strong) | - | - | clear |
| Reliance 1170, zone 1140-1180 | RELIANCE | buy zone | 1140-1180 | - | clear |
| Pricol @660 | PRICOL | buy | 660 | 1 year | clear |
| Hind zinc by 540/550 | HINDZINC | buy ("by" = buy) | 540-550 | - | likely |
| Shell 590/620 | ? (Shell?) | unclear | 590-620 | - | UNCLEAR - ticker and action |
| Jsw infra 330 by | JSWINFRA | buy | 330 | - | likely, message looks cut |
| Shelling 370 & again by 330 | ? | sell at 370, buy again at 330 | 370 / 330 | - | likely: "Shelling" = selling; ticker missing (probably JSW Infra, line above) |
| Birlasoft by this time & waiting | BSOFT | buy, waiting | none | - | unclear |
| Gujarat Heavy Chemicals | GHCL? | watch | - | - | unclear: heavy chemical or GHCL |
| "Har girte bhav me SIP karo 20-20" | - | general advice: buy 20-20 on every fall, not more | - | - | rule of thumb, not a call |
| MMWL @ 20.40-20.50 | MMWL | buy, positional | 20.40-20.50 | positional | clear; penny stock |
| Shanti Gold @ 380-381 | SHANTIGOLD | buy, positional | 380-381 | positional | clear |

## Questions for Aman (answer one at a time)
1. Is the sender always Mausaji, or are the "DARK HORSE" and "POSITIONAL CALL" forms forwarded from a tips group?
2. "by" means buy? "Shelling" means selling?
3. Does a line without a price (like "Birlasoft by this time & waiting") count as a call, or only as a watch?
4. Which of these do you already hold? (Holder column comes from your holdings, so this is a check only.)

## Observations
- MMWL at about 20 rupees is a penny stock; with the 80%-conviction rule it should not become a trade idea without evidence (volume, delivery, fundamentals).
- Three message styles exist (research essay, shorthand Hinglish, formatted tips). The Mausaji parser (mdo_share_master.parse_mausaji_calls) reads model JSON, so the extraction prompt, not the code, needs these styles added.
- The Bantu Mausaji chat has 0 stored messages on the server (2026-10-11): the WhatsApp watcher has not captured it. Confirm that the chat name matches exactly "Bantu Mausaji" in WhatsApp.
