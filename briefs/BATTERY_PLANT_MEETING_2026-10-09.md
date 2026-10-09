# Battery plant — first-meeting brief
**For:** Aman Agrawal · **Date:** 2026-10-09 · **Prepared by:** Chief of Staff
**Purpose:** You have never been in batteries. This tells you what the words mean, which of three businesses the other side is likely pitching, what the law requires, where the money is made or lost, what to ask, and what not to sign today. Every number carries a source and date. Where I could not source one, it says **[UNVERIFIED]**. Nothing here is an objective; it is context for a meeting.

---

## 1. Twelve terms you must know

| Term | One line |
|---|---|
| **Ah (ampere-hour)** | How much charge a cell holds. A "100 Ah" cell can give 100 A for one hour. |
| **Wh / kWh / GWh** | Energy = Ah × voltage. 1 kWh = 1,000 Wh; 1 GWh = 1,000,000 kWh. A 2-wheeler pack is ~2–3 kWh; a grid container is ~3–5 MWh. |
| **C-rate** | How fast you charge or discharge. 1C = full in one hour; 0.5C = two hours. Higher C = more heat, shorter life. |
| **Cycle life** | Number of full charge–discharge cycles before capacity falls to ~80%. LFP: typically 3,000–6,000+; NMC: typically 1,000–2,000 [UNVERIFIED ranges, textbook figures]. |
| **LFP vs NMC** | Two lithium-ion chemistries. LFP (lithium iron phosphate): cheaper, safer, longer life, heavier; dominant in BESS, 3W, buses. NMC (nickel manganese cobalt): lighter, costlier, used where range per kg matters. |
| **Cell → module → pack** | Cell = the basic unit (like one coal lump). Module = cells bundled. Pack = modules + BMS + casing + cooling = what the customer buys. |
| **BMS** | Battery management system: the electronics that stop over-charge, over-heat, imbalance. Pack safety lives here. |
| **Cathode / anode** | The two electrodes. Cathode (LFP or NMC powder) is most of the cell's cost; anode is usually graphite. Both are imported into India today. |
| **Black mass** | The dark powder left after shredding spent lithium cells. Contains Li, Ni, Co, Mn. It is the "ore" of battery recycling. |
| **GWh capacity** | Plant size = GWh of cells or packs per year. "1 GWh" ≈ 400,000 2-wheeler packs or ~200 grid containers. |
| **Yield** | % of cells that pass QC. Cell plants lose money below ~90%; new plants start far lower. |
| **Warranty years** | Packs are sold with 3–8 year / cycle warranties. The seller carries that liability on its balance sheet. |

---

## 2. The three plant types — which one are they pitching?

| | **(1) Li-ion cell manufacturing** | **(2) Pack / module assembly** | **(3) Recycling (lead-acid or Li-ion)** |
|---|---|---|---|
| **What it is** | Make cells from imported cathode/anode powder, foil, electrolyte. Dry rooms, coating, formation. | Buy finished cells (China), assemble into packs with BMS for 2W/3W, telecom towers, BESS. | Lead-acid: smelt old batteries into lead ingots. Li-ion: shred to black mass, then hydrometallurgy to metal salts. |
| **Capex** | ₹600–650 cr per GWh (Amara Raja management range, [Autocar Pro, Mar 2024](https://autocarpro.in/news/amara-raja-to-invest-around-rs-3000-crore-in-2-years--120830)); first 1 GWh line incl. lab ₹2,400 cr ([The Machine Maker](https://themachinemaker.com/news/amara-raja-to-infuse-%e2%82%b91200-crore-more-into-1-gwh-lithium-cell-project/)); Waaree ₹10,000 cr for 20 GWh cell+pack ([ICN, Jan 2026](https://www.indianchemicalnews.com/battery/lite/waaree-energy-secures-rs-1003-crore-to-build-20-gwh-gigafactory-for-lithium-ion-cells-and-battery-pack-28800)). China benchmark $55–72 m/GWh ([ORF](https://www.orfonline.org/index.php/research/powering-ahead-the-future-of-ev-battery-manufacturing-in-india)). | Nexcharge: ₹250 cr for 1.5 GWh, 6 lines ≈ ₹17 lakh/MWh ([ETN](https://etn.news/iesa-contacts-menu/5037-nexcharge-lithium-ion-battery-production-india-prantij-facility)). Endurance: ₹47 cr for ~35,000 packs/month ([EVreporter](https://evreporter.com/endurance-tech-to-invest-%e2%82%b9473-million-in-li-ion-battery-plant/)). Cygni: >₹300 cr for 40,000 packs/yr. A single semi-automatic line: **[UNVERIFIED]**, vendors quote ₹5–25 cr. | Lead-acid: Gravita Mundra Ph-I ₹32 cr for 19,500 tpa ([TND India, 2021](https://www.tndindia.com/gravita-indias-mundra-battery-recycling-plant-starts-operations/amp/)); Amara Raja ₹280 cr for 100,000 tpa ([Business Standard, 2021](https://www.business-standard.com/article/markets/amara-raja-batteries-dips-8-on-disappointing-operational-performance-in-q3-121021500372_1.html)). Li-ion hydromet: Lico plans ₹250 cr ([Battery Industry](https://batteryindustry.net/?p=40067)); Attero ₹300 cr to reach 11,000 tpa ([Udayavani, 2021](https://udayavani.com/?p=1182262)). |
| **Minimum viable scale** | Realistically 1 GWh+ (≈ ₹1,000–2,500 cr all-in). PLI ACC applicants bid 5–20 GWh. | 100–500 MWh/yr is a real business (₹30–100 cr). | Lead: 20,000 tpa. Li-ion: 5,000–10,000 tpa scrap in-feed. |
| **Land / power / water** | Exide: 80 acres for 12 GWh ([Mercom](https://mercomindia.com/exide-to-procure-80-acres-of-land-in-bengaluru-to-set-up-lithium-ion-gigafactory)); NSure: 80 acres for 1 GWh ([EVreporter](https://evreporter.com/nsure-reliable-power-solutions-to-invest-inr-1050-crores-to-produce-lfp-cells-in-india/)); Waaree: 300 acres for 16 GWh ([SolarQuarter, Feb 2026](https://solarquarter.com/2026/02/19/waaree-energies-to-set-up-indias-largest-16-gwh-battery-gigafactory-in-andhra-pradesh)). ~6 MW per GWh/yr ([HSSMI, non-India](https://www.hssmi.org/?p=15199)); water 28–67 L per kWh produced ([academic, non-India](https://dea.lib.unideb.hu/server/api/core/bitstreams/e2dfdc6e-6c32-418e-a083-9ab5fc8d008c/content)). India-specific figures: **[UNVERIFIED]**. | 2–10 acres, LT/HT grid connection, modest water. **[UNVERIFIED]** | Lead: pollution-category red, needs buffer zone. Li-ion hydromet: effluent treatment, ZLD. Specific figures **[UNVERIFIED]**. |
| **Skills needed** | Electrochemists, process engineers from Korea/China/Japan, dry-room operations. Scarce in India. | Electrical/electronics engineers, BMS firmware, welding/QC technicians. Available in India. | Metallurgy, chemical process, environmental compliance. Closest to what you already run. |
| **Time to revenue** | 3–5 years. PLI awardees of 2022 had commissioned 1.4 GWh of 50 GWh by Oct 2025 ([pv-magazine, Jan 2026](https://www.pv-magazine-india.com/2026/01/22/indias-pli-scheme-achieves-just-2-8-of-targeted-50-gwh-battery-manufacturing-capacity-so-far)). | 9–18 months incl. certification. | Lead: 12–18 months incl. consents. Li-ion hydromet: 2–3 years. |
| **Customers** | EV OEMs, BESS integrators, pack makers. They demand qualification runs of 12–24 months before volume. | 2W/3W OEMs, telecom tower cos, solar+storage EPCs, e-rickshaw dealers, BESS integrators. | Lead: Exide, Amara Raja, Luminous (buy refined lead). Li-ion: cathode makers, Lohum, exporters of black mass. |
| **Main risk** | Capital intensity + yield + Chinese price. Chinese LFP cells sell at $42–60/kWh ([SNE](https://sneresearch.com/en/business/report_view/256/page/0); [ESS News, Apr 2026](https://www.ess-news.com/2026/04/22/chinas-314-ah-storage-cell-prices-climb-more-than-20-in-six-months/)). A new Indian cell plant cannot match that for years. | Thin margin, warranty claims, cell supply dependence on China, and OEMs can build packs in-house. | Feedstock collection (informal sector), metal-price swings, environmental enforcement. LFP black mass has low value. |

**Alternative (one line):** a **stationary BESS project** — own and operate a grid battery, not make it. Govt VGF tranche 2: ₹5,400 cr for 30 GWh, ₹18 lakh/MWh support, 18-month build ([pv-magazine, Jun 2025](https://www.pv-magazine-india.com/2025/06/10/power-ministry-announces-inr-5400-crore-viability-gap-funding-to-support-30-gwh-bess-development)); 2025 L1 tariffs ₹1.48 lakh/MW/month (2-hr) and ₹2.85 lakh/MW/month (4-hr) ([Indian Infrastructure, Jul 2026](https://indianinfrastructure.com/2026/07/03/growing-pipeline-battery-storage-market-moves-towards-larger-scale-deployment/)). This is an infra/PPA business, closer to your logistics contracts than to manufacturing.

---

## 3. Indian regulatory checklist

| Item | What it is | Applies to | Source |
|---|---|---|---|
| **PLI ACC** | ₹18,100 cr scheme for 50 GWh of cells. All capacity allocated (Ola 20, Reliance 15, Rajesh Exports 5 + waitlist). Only 1 GWh commissioned by Mar 2026; penalties ₹5–12.5 lakh/day levied from Jan 2025; Ola's window extended to CY2031 in Aug 2026. **No open tranche for a new entrant.** | Type 1 only | [Renewable Watch, Sep 2024](https://renewablewatch.in/2024/09/09/reliance-industries-awarded-10-gwh-capacity-under-pli-acc-scheme/) · [Vision IAS/ET, Mar 2025](https://visionias.in/current-affairs/upsc-daily-news-summary/article/2025-03-04/the-economic-times/economy/battery-pli-beneficiaries-asked-to-pay-penalty-for-missing-targets) · [pv-magazine, Mar 2026](https://www.pv-magazine-india.com/?p=14658) · [ETV Bharat, Aug 2026](https://www.etvbharat.com/en/business/govt-revises-acc-pli-timelines-for-ola-electric-enn26081202046) |
| **BIS IS 16046 (CRS)** | Compulsory registration for portable Li-ion cells (Pt 2) and packs (Pt 1). Test at BIS-recognised NABL lab, then register. New rated-capacity test rule: deadline 30 Apr 2027. | Portable/consumer packs; cells you import for them | [BIS](https://services.bis.gov.in/php/BIS_2.0/bisconnect/knowyourstandards/Indian_standards/isdetails/MjMzMzY=) · [Mercom, Feb 2026](https://mercomindia.com/bis-mandates-rated-capacity-verification-guidelines-for-lithium-batteries) |
| **AIS-156 (Amd 3)** | EV traction battery safety test via ARAI/ICAT. Phase 2 in force since 31 Mar 2023. Each pack model needs its own certificate. | Type 2 (2W/3W packs) | [ACMA circular](https://www.acma.in/uploads/ciculer-attachement/EV%20Battery%20Testing%20amendments.pdf) |
| **IS 17855:2022** | Performance standard for EV packs. Voluntary as of search date; no QCO found. | Type 2 | [Business Standard, Jun 2022](https://www.business-standard.com/article/economy-policy/bis-formulates-standard-for-ev-batteries-following-spate-of-fire-incidents-122062401168_1.html) |
| **Battery Waste Mgmt Rules 2022** | EPR. Producers (incl. pack assemblers and importers) register on CPCB portal (Form 1A), file EPR plan by 30 June yearly, meet collection targets or pay environmental compensation. Recyclers register, must hit recovery %. Recycled-content mandate: 35% for automotive/industrial batteries 2024–26, 40% from 2026–27. QR-code labelling allowed since Feb 2025. | All three | [Corpseed](https://www.corpseed.com/knowledge-centre/epr-for-battery-waste-management-rules-2022) · [IMPRI](https://www.impriindia.com/insights/battery-waste-management-rules/) · [Mondaq, 2025](https://webiis08.mondaq.com/india/waste-management/1622840/battery-waste-management-amendment-rules-2025) |
| **CPCB / SPCB consents** | CTE then CTO. Lead smelting is red category. Li-ion hydromet needs hazardous-waste authorisation and effluent/ZLD. | Types 1 and 3 mainly | [IMARC case study](https://www.imarcengineering.com/case-study/grid-scale-battery-energy-storage-systems-manufacturing-facility) |
| **PESO** | Listed among approvals for a cell/BESS plant; threshold and whether finished-pack storage needs a licence: **[UNVERIFIED]**. Ask PESO regional office. | Types 1, 2 | [IMARC](https://www.imarcengineering.com/blog/how-to-set-up-a-battery-energy-storage-system-manufacturing-plant-in-india) |
| **GST** | 18% on all batteries (HSN 8507) since 22 Sep 2025 (was 28% for non-Li). Cathode coating and separators stay at 28%. Traction battery is 5% only when sold fitted in the EV (single source). | All | [pv-magazine, Sep 2025](https://www.pv-magazine-india.com/2025/09/08/india-energy-storage-alliance-iesa-welcomes-the-new-tax-regime-under-gst-2-0) · [Chemindigest](https://chemindigest.com/gst-2-0-reforms-for-energy-storage-and-battery-innovation/) · [TaxClue](https://taxclue.in/guide/gst-on-batteries) |
| **Customs** | BCD nil on 35 capital-goods lines for EV-battery plants (Budget 2025-26), extended to BESS cell plants to Mar 2028 (Budget 2026-27). Li-ion scrap and critical minerals BCD nil. **BCD on imported finished cells: [UNVERIFIED]** — check CBIC tariff for HS 8507.60 before pricing. | All | [Autocar Pro, Feb 2025](https://autocarpro.in/news/budget-2025-showers-benefits-on-li-ion-battery-ev-manufacturers-124711) · [ICN, Feb 2026](https://www.indianchemicalnews.com/policy/budget-202627-capital-goods-for-li-ion-and-sodium-antimonate-exempted-from-bcd-29135) |
| **Chhattisgarh incentives** | EV Policy 2022: 25% capital subsidy on plant & machinery for EV, component and **battery** manufacturing; SGST reimbursement; 500–1,000 acre EV park. Valid 5 years from 1 Apr 2022 (ends 31 Mar 2027 unless extended). Industrial Policy 2024-30: general capital/interest subsidy, stamp and electricity duty exemption; no battery-specific line found. Caps and current status: **[UNVERIFIED]** — pull the gazette. | All | [EVreporter](https://evreporter.com/chattisgarh-ev-policy/) · [Drishti, Nov 2024](https://www.drishtiias.com/state-pcs-current-affairs/new-industrial-policy-2024-30/print_manually) |

---

## 4. Unit economics skeleton

**Cell plant (Type 1).** Revenue = GWh sold × ₹/kWh. Chinese LFP cells: $42–60/kWh in 2025–26 ([SNE](https://sneresearch.com/en/business/report_view/256/page/0); [ESS News, May 2026](https://www.ess-news.com/2026/05/12/ceecs-7-gwh-battery-storage-cell-procurement-sees-low-end-prices-at-47-kwh/)); BNEF global average cell $74/kWh, Dec 2025 ([pv-magazine](https://www.pv-magazine-india.com/2025/12/10/global-lithium-ion-battery-pack-prices-fall-to-108-kwh-says-bnef)). Cost = imported cathode/anode (~60–70% of cell cost [UNVERIFIED]) + power + yield loss + depreciation on ₹600+ cr/GWh. Margin drivers: yield, scale, power tariff, rupee. Without PLI money or a captive buyer the arithmetic does not close today. **Ask for:** their landed-cost-per-kWh model vs Chinese import, yield ramp curve, offtake letters.

**Pack assembly (Type 2).** Revenue = packs × ₹/kWh. BNEF LFP pack average $81/kWh, NMC $128/kWh (Dec 2025, same source). Indian 2W/3W packs sell for more because of certification, BMS and warranty. Cost = cells (70–80% of pack cost [UNVERIFIED]) + BMS + enclosure + labour + certification + **warranty reserve**. Gross margin typically 10–20% [UNVERIFIED]. Margin drivers: cell purchase price and payment terms, pack design ownership, OEM contract length, warranty claim rate. **Ask for:** cell supplier LOI with price band, warranty claim history, OEM contracts (not MoUs), BMS source code ownership.

**Recycling (Type 3).** Revenue = tonnes × metal price × payable %. China NMC black mass ~76,550 RMB/t (high grade, 21 Sep 2026); LFP black mass 14,100–26,030 RMB/t (27 Aug 2026) ([Mysteel](https://www.mysteel.net/news/5141997-flash-china-daily-lithium-ion-battery-black-mass-price-20260921)). Refining cost $1,500–1,800/t black mass ([Fastmarkets, 2023](https://fastmarkets.com/insights/six-key-trends-battery-recycling-market)). India produces only 400–500 t black mass/month, Lohum ~70% ([Fastmarkets](https://fastmarkets.com/insights/indias-ev-battery-gigafactory-plans-could-spur-black-mass-imports-and-cut-exports)). Margin drivers: feedstock cost and chemistry (cobalt-rich is worth money, LFP is not), recovery %, EPR certificate income, metal price. **Ask for:** feedstock supply agreements, chemistry mix, recovery % test results, EPR certificate price assumptions.

---

## 5. Twenty questions for the counterparty

**Their proposal**
1. Which of the three is it: cells, packs, or recycling? What chemistry? What annual capacity in GWh or tonnes?
2. What exactly do they want from you: land, money, power, the coal-logistics cash flow, or a Chhattisgarh licence?
3. Who holds the technology, and who has run a plant like this before? Name the plant and the person.
4. What is the total project cost, phase by phase, and what is your share in each phase?
5. What are the three things that must be true for this to make money, in their own words?

**Technology and supply chain**
6. Who supplies cells (Type 2) or cathode/anode (Type 1), on what price formula, and for how many years?
7. What happens to the plant if China restricts exports of cells or precursors?
8. What yield do they assume in year 1, 2, 3, and from which plant does that curve come?
9. Who owns the BMS software and pack design? Can you sell to other OEMs with it?
10. Which certifications (AIS-156, IS 16046, CPCB EPR) does their design already hold, and for which exact models?

**Money**
11. Capex per GWh or per tonne, with vendor quotes, not estimates. What is imported, and under which BCD line?
12. Working-capital cycle: cell purchase terms vs OEM payment terms. Who finances the gap?
13. What incentive (PLI, state subsidy, VGF) is assumed, and is it sanctioned or merely applied for?
14. Who carries warranty liability, and what reserve % do they book?
15. What is the exit value if the plant fails after two years: land, sheds, and what else?

**Regulatory**
16. Which consents are in hand, which are applied for, and which have not been started?
17. Who is the registered "producer" under the Battery Waste Rules, and who pays the environmental compensation if targets are missed?
18. Has any related company ever been penalised by CPCB, PESO, or MHI?

**Exit**
19. Who buys you out if you want out in year 3, and at what formula?
20. What are the lock-in, non-compete, and personal-guarantee terms they expect from you?

---

## 6. Red flags

- "PLI will fund it." No tranche is open; every awardee is behind and being fined ([pv-magazine, Jan 2026](https://www.pv-magazine-india.com/2026/01/22/indias-pli-scheme-achieves-just-2-8-of-targeted-50-gwh-battery-manufacturing-capacity-so-far)).
- A cell plant pitched below ₹500 cr/GWh, or a pack line pitched as "cell manufacturing".
- Capex quoted without a vendor name. Equipment is 50–65% of cell-plant capex ([IMARC](https://www.imarcengineering.com/blog/ev-battery-manufacturing-plant-in-india)); if they cannot name the line supplier, there is no plan.
- Revenue projections priced above landed Chinese cells with no customs or quality reason.
- MoUs with OEMs instead of purchase orders. MoUs are free.
- No named technologist who has actually run yield at a plant.
- Warranty risk not mentioned, or placed on "the SPV".
- You are asked for a personal guarantee, land transfer, or non-refundable deposit before a DPR exists.
- Chhattisgarh EV-policy subsidy counted as cash in the model; the policy window ends 31 Mar 2027 unless extended ([EVreporter](https://evreporter.com/chattisgarh-ev-policy/)).
- Any pressure to decide today.

---

## 7. What a sensible first commitment looks like

**Sign nothing today except, at most, a mutual NDA** (two-way, no exclusivity, no non-compete, no deposit, 12 months).

**Do not sign today:** a term sheet, an LOI with exclusivity, a land MoU, any guarantee, any cheque, any "expression of interest" letter they could show a bank or a state department with your name on it.

**What to ask for before a second meeting:** (a) a written one-page summary of their proposal answering questions 1–5; (b) their DPR or feasibility study, even if draft; (c) names of three references who have worked with them; (d) which of the three plant types it is, in writing.

**What you can offer, at zero cost:** a site visit to Kharsia/Raigarh to look at land and power; an introduction to your CA; a second meeting in 2–3 weeks after your side has read the DPR.

**Recommended next step for the CoS (needs your "ok"):** commission a 1-week desk check of the counterparty (ROC filings, litigation, past projects) and of the specific plant type once they name it. Nothing will be sent to anyone.

---

### Numbers marked [UNVERIFIED] in this brief
Cycle-life ranges by chemistry · single semi-automatic pack-line cost · pack-plant land/power/water · recycling-plant land/power/water · India-specific cell-plant power and water per GWh · PESO threshold for cell/pack storage · BCD rate on imported finished Li-ion cells · Chhattisgarh subsidy caps and whether the EV policy is extended · cathode/anode share of cell cost · cell share of pack cost · pack gross-margin band.
