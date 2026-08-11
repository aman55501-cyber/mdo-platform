# Personal Register — Cover, Assets & Liabilities

**Status:** empty — this is the blind side described in [../STATUS.md](../STATUS.md) §4.
**Owner:** Aman · **Cadence:** review monthly, reconcile quarterly

Five checks in the registry read this file's existence as their unblock condition:
`insurance_cover`, `lic_policies`, `vehicle_fleet`, `liabilities_emi`, `networth_rollup`.
They stay `blocked` — and say so in the monthly report — until the sections below hold
real rows.

**How to fill it without it becoming a project.** Do not type this out. Put every
policy schedule, RC, sanction letter and premium receipt into one Drive folder, then
photograph the rest. The vision pipeline already reads documents — the same one that
reads weighbridge slips. Then ask the Brain: *"read the policy folder and fill the
registers in LIFE_LLM/domains/personal-assets-liabilities.md."* One evening with a
folder of papers, not a data-entry exercise.

**Do not put account numbers, policy PDFs or credentials in this file.** It is in git.
Identifiers are fine (a policy number is not a credential); scans and statements are
not — those live in Drive.

---

## §1 — General Insurance

Every asset that would hurt to lose, and whether it is actually covered.

| Asset | Type | Insurer | Policy no. | Sum insured | Premium | Renewal date | Verified |
|---|---|---|---|---|---|---|---|
| | health / fire / marine / plant / liability | | | | | | |

Fill for at least: family health floater · washery plant & machinery · hotel building
and contents · stock in transit · any public/product liability cover.

**What the check looks for:** 🔴 a policy lapsed, or renewing inside 7 days · 🔴 an
asset in the register carrying no cover at all · 🟡 renewing in 8–30 days.

> The 🔴 that matters most is the third: an *uninsured* asset never generates a renewal
> reminder, so it is invisible to every calendar-based system. Only a register catches it.

## §2 — Life Cover / LIC

| Policy | Insurer | Policy no. | Sum assured | Premium | Frequency | Due date | Maturity | Nominee |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

**Also record, once:** total cover across all policies, and the actual need — the
honest version being roughly (dependants' annual need × years to independence) + all
outstanding liabilities from §4 − liquid assets. With a newborn, the years-to-
independence term is at its maximum, and this is the moment the number is largest.

**What the check looks for:** 🔴 premium due inside 7 days or a policy lapsed · 🟡 total
cover below the need calculation.

> A lapsed policy is unrecoverable value — not a late fee. Revival costs medicals and
> may be refused. This is the highest-consequence, lowest-effort item in the file.

**Nominees:** confirm each one is current. A nominee set before marriage or before the
child is a live problem hiding in a settled document.

## §3 — Vehicles

Personal cars **and** the commercial fleet — VWLR tippers, loaders, the hotel vehicles.
A commercial vehicle running with expired insurance or fitness is an operational and
criminal exposure, not an admin lapse.

| Vehicle | Reg no. | Owner entity | Insurance expiry | PUC | Fitness | Permit | Road tax |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

Vahan (`parivahan.gov.in`) is the authoritative source for everything except insurance
premium terms, and needs no login for a status lookup.

**What the check looks for:** 🔴 any vehicle uninsured or with an expired document
while in use · 🟡 anything expiring inside 30 days.

## §4 — Liabilities

| Lender | Entity | Facility | Sanctioned | Outstanding | Rate | EMI | Next due | Security | Guarantor |
|---|---|---|---|---|---|---|---|---|---|
| | term / OD / CC / vehicle / personal | | | | | | | | |

**Then, separately, list every personal guarantee you have signed** — lender, entity,
amount, date. Across 26 entities this is the single largest undocumented exposure in
the group: a guarantee signed years ago for a dormant company is still enforceable
against you personally, and nothing in the current system would surface it.

**What the check looks for:** 🔴 an EMI or interest servicing missed, or OD utilisation
above 90% · 🟡 a personal guarantee with no matching asset cover.

**Unblocks with:** bank statements. The same Gmail-MCP channel that unblocks
`bank_balances` gives EMI debits and OD utilisation here — one connector, two checks.

## §5 — Illiquid Assets (Pools C & D)

Sized "TBD" since April. Until these have numbers, the system can state the liquid book
to the rupee and cannot state your net worth.

| Asset | Type | Held by | Acquired | Cost | Current value | Basis of valuation | Encumbered? |
|---|---|---|---|---|---|---|---|
| | property / unlisted equity / plant / receivable | | | | | | |

"Basis of valuation" matters more than the number — a circle rate, a broker quote and a
last-round valuation are not comparable, and a net worth built from mixed bases is
false precision. Record the basis, and the check will carry it through rather than
flattening everything into one total.

**What the check looks for:** 🔴 net worth cannot be stated because a pool has no
number · 🟡 Pools C/D still TBD.

---

## Where this connects

- **Pools** — §5 fills Pool C (strategic illiquid) and Pool D (freedom capital) in the
  ANS Wealth OS. Pool B is already live through the sharecfo bridge.
- **Legacy** — §2 nominees, §5 ownership and the HUF/trust structure are the same
  question asked three ways. The Tier 4 skill `newborn-legacy-structure` starts here.
- **Compliance** — §4 guarantees and §5 encumbrances change which of the 26 entities
  actually carry risk, and should feed the CA reconciliation.
- **Net worth** — §5 assets minus §4 liabilities plus the live liquid book is the first
  time the system could answer *"what am I worth"* honestly.
