# LIFE LLM — Aman Agrawal

**One goal:** a single intelligence that holds every aspect of one life — business,
personal, investments, cover, assets and liabilities — so that information flows to
Aman without being fetched, and from Aman without being re-explained.

**Owner:** Aman Agrawal · **Started:** April 2026 · **This folder added:** 11 Aug 2026 · **Last revised:** 17 Aug 2026

---

## Read these in order

| File | What it answers |
|---|---|
| **[STATUS.md](STATUS.md)** | What is done, what is pending, what is blocked and on whom. Start here after time away. |
| **[GUIDE.md](GUIDE.md)** | How to actually build this — the two-way flow, and how code/Cowork/chat sessions become memory. |
| **[sharecfo/](sharecfo/README.md)** | The capital organ, and the runbook that moves it under this umbrella. |
| **[domains/](domains/)** | One register per life domain. The blind side lives here — insurance, LIC, vehicles, liabilities. |

---

## The correction this folder makes

Two things were upside down before today.

**1. sharecfo was the parent.** On the VPS the tree literally reads
`/docker/sharecfo/mdo-platform` — the capital service is the parent directory and the
whole Life LLM is a subfolder of it. That is backwards. sharecfo is *one organ*: it
holds broker sessions for four accounts. It is not the thing that contains a life.
The runbook in [sharecfo/README.md](sharecfo/README.md) inverts it.

**2. "Life" meant "business".** The map had seven domains and six of them were
companies. Car insurance, LIC, health cover, the vehicles, the loans, the EMIs and the
personal guarantees appeared nowhere in the code, the database or the checks registry.
The system could tell you the liquid book to the rupee and could not tell you whether
your car was insured. [domains/personal-assets-liabilities.md](domains/personal-assets-liabilities.md)
is the register that closes that, and five new checks now report the gap every month
until it is filled.

---

## The organs

The Life LLM is not one program. It is a set of organs that share a memory.

| Organ | What it is | Where it lives | State |
|---|---|---|---|
| **Memory** | SQLite — entities, filings, tenders, messages, intel, reports, the map | `mdo-data` volume on the VPS | live |
| **Body** | MDO backend (FastAPI) + web app — the 14 modules, the surfaces | this repo | live |
| **Capital organ** | sharecfo — authenticated broker sessions, 4 accounts | separate stack, same VPS | live |
| **Senses** | WhatsApp bridges (×2), vision pipeline, Yahoo RSS, Grok search | this repo | live |
| **Site senses** | VPN sidecars into the Hotel and Vedanta LANs | `vpn/` in this repo | code done, never switched on |
| **Reflexes** | `mdo_agent.py` — hourly and daily checks on VPS cron | this repo | live |
| **Judgement** | MDO Brain — Claude with tools over the whole backend, exposed as MCP | `mdo_brain.py` | live |
| **Playbooks** | `skills/` — codified decision rules | this repo | 1 of ~35 written |
| **Voice** | WhatsApp alerts, Daily Briefing, Agent Reports, the app | this repo | live |

**The rule that keeps it honest:** every domain names its sources, every source has a
connector, every connector feeds an engine, every engine runs checks, every check
reaches a surface. A domain with no source is flying blind — and the system must *say
so* rather than fill the silence. That is why blocked checks exist and why they are
never quietly dropped.

---

## Conceptual hierarchy vs. what is on disk

Worth being precise, because confusing these has already cost a directory layout.

- **Conceptually**, Life LLM is the top. MDO is its body. sharecfo is its capital organ.
  Everything in this folder describes that.
- **On disk in this repo**, the application code stays where it is (`mdo_server.py`,
  `mdo-app/`, `vpn/`). Moving it into a subfolder would break the Dockerfile, the
  compose build contexts and every deploy command for no gain. `LIFE_LLM/` is the
  doctrine and registry layer that sits alongside it.
- **On the VPS**, the tree does get rearranged — `/docker/life-llm/{mdo-platform,sharecfo}` —
  because there the parent/child relationship is a lie that misleads every human and
  agent who reads a path. That migration is a runbook, not a code change.
