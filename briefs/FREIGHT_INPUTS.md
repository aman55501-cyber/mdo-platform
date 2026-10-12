# Freight and landed cost — what the calculator needs from you (2026-10-12)
Built and tested (mdo_freight.py). It never guesses a rate. Tell it the rates once; it keeps each with its source and date, and every tender then gets a landed cost per tonne by rail and by road against the plant's ceiling price, with BID / THIN / SKIP.

## How it works
Landed cost per tonne at the plant = coal cost at the source gate + transit loss + freight (rail, road, or rail then road) + loading and unloading + sampling + GST on freight (unless you take credit).
For washed coal: give the ROM cost, the washery yield and the wash cost per tonne of feed; it converts to cost per tonne of washed coal first.

## What I found in your WhatsApp groups (real lanes, no rates yet)
- **Inward by rail to VWLR:** MCL (BOCM, IB Valley, Sardega sidings) and SECL Korba (KMKA, SLCC silos, Kanika siding); rakes of 58-59 boxes, RR numbers on every dispatch (for example RR 161010491, 4,043 MT, grade G11, 10 Oct).
- **Outward by road from VWLR to RKM Power:** AS Transport, Ajuni Transport, Jaanu Agr., Vaibhav Transport, Bansal Transport (trips and MT in the Vedanta Daily Report).
- **One freight figure only:** "Baroud Railway Freight Rs 13,50,132" (Vedanta Payment Status, 6 May 2026) with no tonnage, so no per-tonne rate can be read from it.
The rates themselves are not in the chats.

## Send these (one line each, on WhatsApp is fine; the CoS saves them as lanes)
1. Rail freight per tonne, all in (railway freight, busy-season surcharge, terminal charges): KMKA to VWLR; SLCC to VWLR; BOCM / IB Valley / Sardega to VWLR. The RR bill gives it: freight / MT.
2. Road rate per tonne (or per tonne-km) from each transporter: VWLR to RKM Power; VWLR to any other plant you bid for; mine or siding to VWLR by road.
3. Loading per tonne; unloading per tonne; sampling or weighbridge per tonne.
4. Transit loss or shortage you actually see, in percent, rail and road.
5. GST on freight: do you take input credit, yes or no.
6. Your minimum margin to bid, in percent of the ceiling price.
7. For washed-coal tenders: washery yield %, wash cost per tonne of feed, and what you get for rejects or middlings per tonne of feed.
Example: "Save lane: VWLR to RKM road, Rs 180 per tonne, Ajuni Transport quote today."

## Then, for any tender
Say: "Landed cost: coal Rs 3,200 at the gate, plant ceiling Rs 4,000, 10,000 tonnes, VWLR to RKM road and KMKA to VWLR rail." The reply is one line per mode, the cheaper mode and the saving per tonne and in total, and the verdict. Until a rate is saved, it names the missing rate instead of answering.

## Risk and reward
Reward: every tender gets a freight-based go or no-go in seconds, and the saving of rail over road (or the reverse) is shown in rupees.
Risk: a stale rate gives a wrong verdict, so each lane shows its source and date; replace it when a quote changes.
