# Model routing: spend the subscription where judgement matters

Evidence (docs/SESSION_INDEX.md): the three most expensive sessions were long Opus/Fable builds with 350M+ cache-read tokens each; one died on credits.
The backend brain (`mdo_brain.py`) answers every chat with `claude-opus-5`. That is the largest avoidable cost once WhatsApp becomes the front end.

| Work | Model tier | Why |
|---|---|---|
| Classify a WhatsApp message (domain, urgency, is it a report), parse hotel night reports, tag photos | Haiku-class | high volume, no judgement |
| Photo reading: weighbridge slips, tallies, registers | Sonnet-class | accuracy on messy photos; the code already uses Sonnet |
| Daily routine, civil QC checks, reconciliation drafts, tender shortlist, WhatsApp replies | Sonnet-class (default) | the bulk of the work |
| Contract and legal reading, structural-flag judgement, capital/restructuring plans, anything over Rs 25 L | Opus-class, one focused session | rare, high stakes |
| Fixed arithmetic, dedupe, scheduling, polling | No model: scripts and cron | free and repeatable |

Rules
1. Default Sonnet. Escalate to Opus only for the third row, and say why in the first line.
2. New task = new short session. Do not carry a 500k-token context across topics: that is how $327 happened.
3. Anything that repeats becomes a script or a routine that runs on a schedule.
4. Isolation ("no contamination"): one agent = one folder = one entity's data. An agent reads only its folder plus ground-truth files by pointer. No cross-entity paste. Share lane stays in Grok's sessions.
5. A mod cannot switch the Claude model by itself. Switching is set per session (`/model`), per subagent, and per routine (`model` field). The `mdo-rules` mod carries rule 1-3 as text.
6. Backend: make `mdo_brain.py` read the model from an env var (default today `claude-opus-5`; set to Sonnet, escalate on request). Not changed yet; one-line edit, awaiting your yes.
7. Check `/usage` before starting anything large. Heavy builds go in the first days after a limit reset, not the last.
