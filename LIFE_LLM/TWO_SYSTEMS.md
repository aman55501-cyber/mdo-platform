# Two Systems, One Life — Reconciliation

**Written 17 Aug 2026**, on receiving the *MD's Office — Operating Map* (dated 18 Jul 2026).
**This document supersedes several conclusions in [STATUS.md](STATUS.md) and [GUIDE.md](GUIDE.md).**

> ## ✅ DECIDED 17 Aug 2026 — see "Decisions" below
>
> Aman answered three of the four contradictions and corrected the fourth's premise.
> The banner below is kept for the record of how this document was first written.
> **Read the Decisions section first — it overrides the recommendations in the body.**

---

## Decisions — Aman, 17 Aug 2026

**1. Broker accounts — the premise was wrong, and reality is bigger than either
system.** Not 3, not 4. **Six broker accounts across five holders, plus three more
platforms:**

| Holder | Platform | Wired to sharecfo? |
|---|---|---|
| Aman | HDFC Securities (#4016900) | yes — HDFC1 |
| Ashok | HDFC Securities | yes — HDFC2 *(assumed; confirm it is Ashok not Sudha)* |
| Sudha | HDFC Securities | **no** |
| Aditi *(the person)* | HDFC Securities | **no** — MDO never knew this existed |
| Jahnavi | HDFC Securities | **no** — MDO never knew this existed |
| Aditi Investments *(firm)* | Angel One (#A1504046) | yes — ANGEL1 |
| Aman | INDmoney (US equity) | **no** |
| Aman | SunCrypto (crypto) | **no** |
| Aman | "Infinity" | **no** — *ambiguous, see below* |

Consequence: **any net-worth figure covers 3 of 9 accounts.** This is now enforced
in code rather than left as a caveat — `broker_accounts` carries a `wired` flag and
`/networth` reports "3 of 9" with the missing accounts named. A partial book can no
longer be mistaken for a total.

Two open items: which physical account `HDFC2` actually is, and **what "Infinity"
is** — Aman listed it among his platforms, but "Infinity" is also the hotel/weighbridge
software in the MD's Office map. It is seeded as `asset_class='unknown'` and flagged
until confirmed.

**2. Morning surface — RESOLVED, and neither option won.** Aman: *"forget morning
report, first report I want is at 8:30 am giving market roundup of previous day."*
So the 06:30-vs-06:57 argument is moot. Built: a new `premarket` cadence at **08:30
IST**, before the 09:15 open and before the Singhvi window — previous Indian close,
overnight global, crude, currency, flows, news. It always reports (a briefing, not
an exception alert) and uses live web search, because MDO has no feed whatsoever for
crude, DXY or global closes.

**3. MDO briefing — DEMOTED.** Approved. The operational daily brief stays at 06:57
as a secondary; the 08:30 roundup is the day's first surface.

**4. Site access — TAILSCALE.** Approved. The OpenVPN sidecars are superseded. They
remain committed and in `docker-compose.yml` for now; retiring them is a separate,
reversible step, and the isolation reasoning in `docs/PLAN_VPN_SITE_ACCESS.md`
carries over to Tailscale unchanged.

**5. Memory — DESIGN FIRST.** Aman: set it up, but not until he reviews it. Design
is at [MEMORY_DESIGN.md](MEMORY_DESIGN.md); **nothing built**.

**6. Personal registers — DEFERRED** in favour of the combined trade book. The
registers stay in the repo and their five checks stay `blocked`; they are simply not
the current priority.

**7. ITR — FILED** for all individuals and Aditi Investments. Removed from the
ledger. *Still unconfirmed: ANS Group HUF, which is not an individual and was not
named.*

**Still open — contradiction 4 of the original four:** where financial truth lives.
MDO still seeds April figures into SQLite while `PNL_FY2021-26_MASTER.xlsx` and
MProfit are the real records. Unresolved.

---

> ## ⚠️ ORIGINAL BANNER — ANALYSIS ONLY (superseded by the Decisions above)
>
> Aman asked to analyse before changing. So this document is committed as a **record of
> findings**, and nothing in it has been acted on:
>
> - No code, config, check or seed was changed for it.
> - The four contradictions in §"The contradictions that need your decision" are **open**.
>   The recommendations under each are arguments, not decisions.
> - `STATUS.md` and `GUIDE.md` still carry the four claims corrected below. They are
>   **deliberately not yet edited** — read this file alongside them until Aman decides.
> - The `vpn/` sidecars remain committed and in `docker-compose.yml`. Nothing was retired.
>
> It is committed rather than left as a working file only because this session runs in an
> ephemeral container: uncommitted work is destroyed when the container is reclaimed.

---

## The finding

There are **two Life LLMs**, built in parallel, and they share no memory.

| | **MDO Platform** (this repo) | **MD's Office** (Cowork/Claude Code) |
|---|---|---|
| Substrate | FastAPI + Next.js + SQLite on Hostinger VPS | Files (xlsx/md) + Supabase + `_memory/` |
| Senses | WhatsApp ×2 (Baileys), vision on photos, Yahoo RSS, Grok | Gmail, Drive, MProfit, bank/broker exports, CV drive |
| Reflexes | `mdo_agent.py` hourly + daily, 16-check registry | 9 named automations on schedule |
| Memory | **none** — 21 tables, no decision store | **`_memory/`** — registry, areas, topics, log |
| Morning surface | Daily Briefing + auto homepage brief (~06:57 IST) | `md-morning-brief` 06:30 — *"THE surface"* |
| Site access plan | OpenVPN sidecars (`vpn/`, built, never raised) | Tailscale (planned, for Infinity forensics) |
| Capital feed | sharecfo → `/api/capital/summary` | ShareCFO read-only MCP + MProfit cloud |

I verified the disconnection by grep: this repo contains **no reference** to MProfit,
`_memory/`, `md-morning-brief`, Eureka, Tailscale, Infinity, `PNL_FY`, `Bank_Flow`,
`HDFC2` or `ANGEL1`. Supabase appears only as a parked "candidate addition".

Neither system knows the other exists. That is the single largest structural problem in
the Life LLM — larger than any individual blocked check.

---

## Corrections to what I told you on 11 Aug

I assessed the system from this repo alone. Four of those conclusions were wrong or
too strong, and the errors all ran the same direction — I under-credited you.

**1. "It cannot remember anything you tell it." — Wrong at the whole-system level.**
`_memory/` exists with a registry, areas, topics and a log, plus `weekly-memory-sync`
every Sunday 07:33. Memory *does* exist. What's true is narrower: **the MDO platform
cannot reach it.** The Brain's 22 tools query SQLite, and none of them touch `_memory/`.
So my recommendation changes from *build a memory store* to *connect MDO to the one that
already exists* — much cheaper, and it avoids creating a third source of truth.

**2. "It cannot tell you your net worth." — Wrong.** `daily-networth-tracker` runs at
07:00 daily. Net worth is tracked. The accurate statement: **MDO** cannot state it, and
the `networth_rollup` check I added is blocked on Pools C/D — but that check should now
read from the existing tracker rather than waiting on a fresh valuation exercise.

**3. "No bank visibility." — Too strong.** `Bank_Flow_Analysis.xlsx` holds cash flows.
The real gap is coverage, and your own map states it precisely: **27 registry bank
accounts with no statements**. That is a coverage gap, not an absence — and it is a
sharper, more actionable framing than mine.

**4. "1 of ~35 skills written." — True but misleading.** The MDO `skills/` folder has
one file. The CFO Package, the missing-docs checklist, the hiring shortlist with a
proposed outreach order, and the *"money / signature / regulator = Aman's click"* rule
are all codified judgement. That last line is a better-expressed escalation policy than
the ⚠️-marked thresholds in `escalation-routing.md`. It should be lifted into that skill
verbatim.

**What survives unchanged** — and is now confirmed twice over:

- **Insurance, LIC, mediclaim and vehicles appear in neither system.** Your map has no
  insurance domain at all. The blind side is real and total.
- **Liabilities are genuinely unknown**, and your map proves it better than my register
  did: *"Identify ₹4,36,760/mo ACH (which loan?)"* — a ₹52.4L/year outflow whose
  counterparty you cannot name. That is exactly what `liabilities_emi` is for.
- **Eureka: ₹26.5L out in FY25-26 with no P&L counterpart located.** Money left and
  nothing records where it went.
- Tender247 credentials unconfirmed in both systems.
- VWLR and Veda Steel: zero financial documents on disk — consistent with the 26 Jul
  request to Giri ji.

---

## The contradictions that need your decision

These are places where the two systems assert different facts. Each needs one answer,
not a merge.

**1. Three broker accounts or four?** MDO_VISION and `/api/capital/summary` describe
four (Aman, Sudha, Ashok on HDFC; Aditi on Angel). Your map says ShareCFO exposes
HDFC1 / HDFC2 / ANGEL1 — three. Either one HDFC account is unwired, or MDO is
describing an account ShareCFO does not actually serve. **Until this is settled, every
portfolio total either system reports is suspect.**

**2. Which morning brief is the surface?** Your map is unambiguous — `md-morning-brief`
06:30 is *"THE surface"*. MDO also generates a briefing and files a daily agent report
around 06:57, and pushes 🔴 alerts to WhatsApp independently. **Two systems are
competing for the same 30 minutes of your attention**, from different data, with no
cross-checking. One must become the surface and consume the other's output.

My recommendation: keep `md-morning-brief` 06:30 as the surface, because it already has
that role and reads the financial truth files. Make MDO a *feed into it* — MDO owns the
things only it can see (WhatsApp ops, photographed weighbridge slips, site alerts) and
publishes them where the 06:30 brief can pick them up. MDO keeps its own 🔴 WhatsApp
push for genuine same-hour escalations, because a 06:30 brief cannot tell you a rake has
been idle since 04:00.

**3. VPN sidecars or Tailscale?** Both target the same problem — reaching the hotel and
site networks. `vpn/` is committed with a full six-phase plan and two certificates
awaiting rotation; Tailscale is queued for the Infinity weighbridge forensics across
laptop, siding PC and hotel server. **You are about to solve remote site access twice.**

My recommendation: **Tailscale, and retire the VPN sidecars.** Reasons: it needs no
certificate rotation (the OpenVPN blocker that has held Phases 1–6 since 31 July), it
handles the laptop and siding PC which the sidecar design does not address at all, and
it avoids the 1024-bit RSA / AES-128-CBC weakness recorded in the VPN plan's own risk
section. The sidecar work is not wasted — the isolation reasoning in
`docs/PLAN_VPN_SITE_ACCESS.md` (never touch the host routing table) applies to Tailscale
too. If you disagree, the counter-argument is that the hotel Omada gateway is already
configured for OpenVPN and Tailscale needs software installed on machines you may not
control.

**4. Where does financial truth live?** MDO seeds portfolio and entity figures into
SQLite from April 2026 documents. Your map names the real sources: `PNL_FY2021-26_MASTER.xlsx`
(realized, verified), `Bank_Flow_Analysis.xlsx`, MProfit cloud for live values. **MDO's
numbers are a stale copy of a system of record it cannot see.** MDO should either read
those files or stop reporting the figures — a stale number presented in a clean UI is
worse than a blank field, and this violates the staleness rule both systems otherwise
follow.

---

## What this means for the Life LLM

The umbrella was the right instinct and I placed it one level too low. `LIFE_LLM/` sits
inside the MDO repo, but MDO is **one of two organs**, not the body.

```
LIFE LLM (the umbrella — doctrine, memory, surfaces)
├── _memory/              ← the memory. Already exists. Nothing else has one.
├── MD's Office           ← files, financial truth, 9 automations, the 06:30 surface
│   └── MASTER/, ANS Group CFO Package/, investment-pnl/
├── mdo-platform          ← this repo: WhatsApp, vision, site ops, checks, 🔴 push
└── sharecfo              ← the capital organ (read-only broker sessions)
```

The `/docker/life-llm/{mdo-platform, sharecfo}` migration in
[sharecfo/README.md](sharecfo/README.md) is still correct — it just isn't sufficient.
The deployment tree and the doctrine tree now agree on the same shape.

**The order that follows from this:**

1. **Settle the four contradictions above.** They are four answers, not four projects,
   and until they are settled both systems report numbers that may be wrong.
2. **Give MDO a `_memory/` reader** — one Brain tool. This is the single highest-value
   connection available: it turns two amnesiac halves into one system that remembers,
   and it is smaller than the memory table I proposed yesterday.
3. **Demote MDO's briefing to a feed** into the 06:30 brief. Keep only the 🔴 same-hour
   WhatsApp push as an independent surface.
4. **Lift *"money / signature / regulator = Aman's click"*** into `escalation-routing.md`
   as the L2/L3 boundary, replacing the unset ⚠️ thresholds.
5. **Then** the personal registers, which remain the one thing neither system covers.

---

## Staleness note

The operating map is dated **18 Jul 2026** — a month old, and its "Active work" lists
have partly moved on. Known since:

- *"Send widened Vimal mail (delete old Aditi-only draft)"* — **done 26 Jul**, and
  widened again on 11 Aug into the compliance reconciliation now sitting in Gmail drafts.
- Jahnavi is the review gate before anything reaches CA Vimal (established 26 Jul,
  reconfirmed 11 Aug). Worth adding to the map explicitly — she also runs the Hotel ANS
  *Candidate Master — LIVE* sheet, so she is an operating node, not only a reviewer.
- The 31 Jul ITR deadline passed while Aman was away; three returns are unconfirmed.
- The VPN sidecars were committed 31 Jul, after this map was written — which is how the
  duplicate site-access approach arose in the first place.

**Neither system tracks the other's progress**, which is why a 3½-week-old map is the
best available picture of half the estate. Whichever surface wins contradiction #2 should
own this map and regenerate it on a schedule.
