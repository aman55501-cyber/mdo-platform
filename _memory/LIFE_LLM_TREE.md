# Life LLM — chain of command (2026-10-12, confirmed by Aman)

```
LIFE LLM  (Aman)
│
├── BUSINESS OS ── operating income
│   ├── VWLR ── Operations · Sales · Tenders
│   ├── Hotel ANS ── Renovation · Hotel management contract
│   ├── Real estate ── Dadu Developers · Dadu Builders · Raigarh Land Venture · Rukmani
│   └── Compliance (business entities)
│
├── WEALTH OS ── money and capital
│   ├── Capital · Banking
│   ├── Investments ── Share Master · Mausaji list · demats · F&O · trade ideas
│   ├── Aditi Investments
│   └── Compliance (personal + investment)
│
├── LIFE OS ── Family · Legacy · Personal and health
│
└── SYSTEM OS ── every system; each one FEEDS a domain, none owns one
    ├── feeds BUSINESS OS: tender pipeline (Tender247, NIT eligibility, tender-radar) · VWLR daily report ·
    │                      site VPN sidecars (Vedanta, FOIS) · Staah (hotel occupancy) · WhatsApp bridge
    ├── feeds WEALTH OS:   Shares CFO + capital service · CFO MCP server · broker feeds (HDFC, Angel One) ·
    │                      Share Master daily bot · Yahoo prices · Mausaji parser
    ├── feeds LIFE OS:     Life OS extraction · memory (Notion, reminders, calendar)
    └── feeds ALL:         MDO app + Decision Feed · agents (chief-of-staff, orchestrator) · MCP connectors ·
                           compliance calendar · librarian (session index) · memory folder
```

Rules
- A system has exactly one home in SYSTEM OS and names the domain(s) it feeds.
- A domain never imports data directly; it reads what its feeds deliver.
- Compliance follows the entity: business filings under BUSINESS OS, personal/investment under WEALTH OS.
- Every feed reports every run, including "0 new".

Source for system names: LIFE_LLM_MAP.md, repo directories, 12 Oct session sweep. Items not yet verified live: [UNVERIFIED].
