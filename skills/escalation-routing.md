# Skill: escalation-routing

**Tier 1 — Operator-to-Architect handoff. This is the skill that lets a COO
exist.** Today every decision reaches Aman because nobody knows which ones
shouldn't. This document draws that line.

**Owner:** Aman Agrawal → transfers to COO on hire
**Applies to:** VWLR washery + siding, Hotel ANS, group entities
**Status:** v1 — thresholds marked ⚠️ need Aman's confirmation before this is binding

---

## 1. The principle

An escalation is a **transfer of decision rights**, not a status update. Before
escalating, the sender must have already: established the facts, formed a
recommendation, and identified what they need (a decision, money, or authority).

"Sir, the loader is down" is a status update.
"Loader MC7 down since 06:20, alternator fault, spare not in store, Vedanta rake
placement at 14:00 at risk. Recommend hiring the Sendoz loader for one shift at
₹X. Need approval to commit spend." — that is an escalation.

**Anything that does not name a decision goes in the group, not to a person.**

---

## 2. Levels

| Level | Meaning | Route to | Response expected | Channel |
|---|---|---|---|---|
| **L0** | Handle it. Log it. | Shift in-charge | — | Group message |
| **L1** | Department head decides | Site head / GM Hotel / Accounts head | Same shift | Group + direct |
| **L2** | Owner-level decision needed | COO (Aman until hired) | Within 4 working hours | Direct call + WhatsApp |
| **L3** | Stop-the-line. Money, safety, legal, or reputation at risk. | Aman directly, any hour | Immediately | Phone call — not a message |

**The default is L0.** If nobody can name which decision is being asked for,
it is L0.

---

## 3. What lands where — VWLR

| Situation | Level | Note |
|---|---|---|
| Machine breakdown, spare in store, <2h downtime | L0 | Log in Machine Update group |
| Breakdown >4h ⚠️, or spare not available | L1 | Names the hire/repair option and cost |
| Rake placed and no dispatch movement >6h ⚠️ | L2 | Demurrage exposure begins |
| Weighbridge dispute with a transporter | L1 | L2 if the party refuses to accept |
| Any injury, however minor | **L3** | Non-negotiable. Call, don't message. |
| Fire, electrocution risk, structural failure | **L3** | Stop work first, call second |
| Vedanta/client complaint in writing | L2 | Relationship risk |
| Statutory inspection or notice at gate | **L3** | Nothing signed without Aman |
| Dispatch below ⚠️ __ MT for the day | L2 | *Threshold to be set — see §7* |
| Coal quality rejection at destination | L2 | Money already at stake |
| Theft or pilferage suspected | **L3** | Also triggers security review |

## 4. What lands where — Hotel ANS

| Situation | Level | Note |
|---|---|---|
| Guest complaint resolved on the spot | L0 | Log in Daily Sales Report |
| Guest complaint requiring refund/comp | L1 | GM decides up to ⚠️ ₹__ |
| Occupancy below ⚠️ __% for 3 consecutive days | L2 | Pattern, not an incident |
| OTA/Staah rate parity broken | L1 | Fix same day, report |
| Food safety incident, guest illness | **L3** | Immediate |
| Police/excise/municipal visit | **L3** | Nothing signed |
| Booking system or payment gateway down | L1 | L2 beyond 4 hours |

## 5. What lands where — Money & compliance

| Situation | Level | Note |
|---|---|---|
| Payment due to a routine vendor within limits | L0 | Accounts processes |
| New vendor, or spend above ⚠️ ₹__ | L2 | Aman approves counterparties |
| Bank balance below the working-capital floor ⚠️ ₹__ | L2 | Same day |
| Cheque bounce — ours or theirs | **L3** | Reputational and legal |
| GST/TDS/ROC deadline within 7 days unfiled | L2 | CA Vimal + Aman |
| Any statutory notice, summons, or court date | **L3** | Ozone §454 and Rashi 3616/2026 are live examples |
| Tender closing within 72h, bid not decided | L2 | Decision has a deadline |
| F&O position beyond the risk limit | **L3** | Capital preservation outranks everything |

---

## 6. How to escalate — the four-line format

Anyone escalating uses exactly this. It fits in a WhatsApp message and forces
thinking before sending:

```
WHAT:     one line — what happened, with the number
IMPACT:   what it costs / risks, in ₹ or hours or relationship
OPTIONS:  what can be done, with cost of each
NEED:     the specific decision, and by when
```

An escalation missing the NEED line gets sent back. That single rule is what
converts "informing the boss" into "asking for a decision".

---

## 7. Thresholds Aman must set ⚠️

This skill is not binding until these are filled in. Every ⚠️ above maps to one:

1. Machine downtime that becomes L1: ____ hours
2. Rake idle time that becomes L2: ____ hours
3. **A bad day at the washery**: below ____ MT dispatched, or below ____ rakes
4. Hotel occupancy that becomes L2: below ____% for ____ days
5. GM Hotel's discretionary comp limit: ₹ ____
6. Spend requiring Aman's approval: above ₹ ____
7. Working-capital floor per entity: ₹ ____
8. F&O risk limit: ____% of capital per position, ____% daily loss

Items 3 and 6 are the highest-value: dispatch defines operational normal, and
the spend limit is most of what a COO would otherwise ask about.

---

## 8. How MDO enforces this

The thresholds above are the same numbers the `checks` registry uses. Once set:

- MDO's hourly agent applies §3–§5 automatically to WhatsApp traffic and flags
  anything meeting L2/L3 as 🔴, which pushes to Aman's phone unprompted.
- L0/L1 items stay in the app and are never pushed — that is the point.
- Escalations arriving without a NEED line can be detected and returned.

So this document is not just a policy — it is the specification the agents run
on. Filling in §7 configures both the humans and the machine.

---

## 9. Review

Monthly, in the first-week CA/ops review: which escalations arrived at the wrong
level? Adjust the thresholds, don't blame the sender. A rule that is routinely
bypassed is a wrong rule.
