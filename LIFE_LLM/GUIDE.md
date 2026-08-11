# How to build the Life LLM

*Written 11 Aug 2026, against the system as it actually stands.*

---

## 1. Stop thinking of it as an LLM

The instinct is that somewhere there is one model that has read everything about your
life and answers accordingly. That is not achievable and not what you want. Context
windows are finite, models are stateless between calls, and a model that has "read
everything" has also read everything stale.

What you are actually building is **a memory with senses, reflexes, judgement and
playbooks.** The model is only the judgement layer — the smallest and most replaceable
part. You have already built most of the rest, which is why the system works at all.

```
senses → memory → reflexes → judgement → surfaces
   ↑                                          ↓
   └────────────── you ───────────────────────┘
```

The loop is the whole design. **You are inside it, not outside it.** Everything below
is about making both arrows cheap.

---

## 2. The two directions, honestly assessed

### Inbound (world → you): strong

WhatsApp ×2, the vision pipeline, market feeds, news, the broker bridge — signal
arrives without you fetching it, gets classified 🔴/🟡/🟢, and 🔴 reaches your phone
unprompted. The hourly agent defaults to silence, which is the single most important
design decision in the system: **an assistant that reports routine noise trains you to
ignore it.** Keep that discipline as you add domains.

The gaps are named in [STATUS.md](STATUS.md): no bank feed, no site systems (VPN built
but off), nothing personal.

### Outbound (you → system): near zero

This is the weak arrow, and it is why the system does not yet feel like it knows you.

Concretely, today: the database has 21 tables and **not one of them stores a decision,
a preference, a constraint or a piece of reasoning.** The Brain has 22 tools — 20 read
the system, 2 write to it (`add_task`, `add_intel_item`). You can ask it anything and
teach it almost nothing.

So every session starts from the documents, and everything you worked out in
conversation last week is gone. You have felt this: re-explaining context you know you
have already explained.

**Fixing this direction is the highest-leverage work available**, and it is smaller than
anything else on the roadmap.

---

## 3. Make the outbound arrow cheap

The rule: **capture must be a byproduct of work you were doing anyway.** Any scheme
that requires you to stop and file something will be abandoned in a fortnight — the
`[EDIT]` markers still sitting in `MDO_VISION.md` §3 since April are the proof.

### 3a. A memory table, and one tool that writes to it

Add a `memory` table (decision, preference, constraint, fact, person) with the text,
the domain, who said it, when, and what it supersedes. Then give the Brain a
`remember` tool and one instruction in its system prompt: *when Aman states a decision,
a preference, a constraint or a fact about his life that is not already in the
database, call `remember` — do not ask permission, and tell him afterwards what you
stored.*

That is roughly a day's work and it converts every conversation into accumulated
memory. Retrieval then goes into the same prompt assembly the Brain already does.

Two things to get right:

- **Supersession, not accumulation.** A memory store that only appends becomes a pile
  of contradictions — the April portfolio number and the August one both "true". Every
  memory carries `supersedes`, and retrieval prefers the newest for any given subject.
  The Aditi broker-mapping correction on 31 July is exactly this case: the old fact was
  not deleted, it was *corrected*, and the system needs to represent that difference.
- **Provenance on every row.** "Aman said, in chat, on 11 Aug" is a different weight of
  evidence from "parsed from a WhatsApp group" or "read off a policy PDF". The existing
  discipline of reporting staleness rather than hiding it extends directly here.

### 3b. Close the loop on your own decisions

You already produce a decision log — in `MDO_VISION.md` §17, by hand, and it stops in
April. Have the Brain write it instead, at the moment you decide, from the
conversation. The Tier 5 skill `decision-log` is already named on the roadmap; this is
what it means in practice.

### 3c. The registers are outbound too

[domains/personal-assets-liabilities.md](domains/personal-assets-liabilities.md) is
outbound flow at its cheapest: photograph a folder of papers, and the vision pipeline
that already reads weighbridge slips reads them into the registers. No typing, no API,
no vendor.

---

## 4. "Include all code, Cowork and chat sessions"

These are three different problems and only one of them is solved.

### Code — solved, keep it that way

The repo is the code and git is its history. Claude Code sessions already run against
it with full context. The one thing worth adding: when a session changes how the system
*thinks* (a new skill, a changed threshold, a corrected fact), that belongs in the
memory store too, not only in a commit message. A commit says *what changed*; memory
needs *why you chose it*.

### Chat sessions — the real gap

Conversations are where your reasoning actually lives, and they currently evaporate.
Do **not** try to archive raw transcripts and retrieve over them: transcripts are mostly
throat-clearing, they contain superseded reasoning, and a retrieval system that surfaces
the discarded half of a conversation is worse than no retrieval at all.

Instead, **distil at the end of a session**: three to eight durable statements — what
was decided, what was learned, what changed, what is now blocked — written to `memory`
with provenance. The rest can go. If the distillation is done by the model at session
end, it costs you nothing.

### Cowork sessions — capture the artefact and the reasoning

Cowork produces documents and plans. `docs/PLAN_VPN_SITE_ACCESS.md` is the model to
follow: an assumption ledger, per-phase acceptance checks, an interview record of what
was asked and answered. That document will still be usable in a year, and its
*assumptions* are as valuable as its conclusions.

The rule: **every Cowork session ends with a committed artefact in the repo**, not a
scroll of chat. If a session produced nothing worth committing, it produced nothing.

### The thing to avoid

Do not build a vector database over everything you have ever written, at least not
first. It is the intuitive answer and it produces a system that confidently retrieves
your April opinions in August. Structured memory with explicit supersession beats
semantic search over an undifferentiated pile — especially for a life, where almost
every fact has a valid-from date. Add embeddings later, over the *distilled* memory,
once there is enough of it to be worth searching.

---

## 5. Where the system already gets it right — keep these

Four decisions in the existing build are load-bearing. Preserve them as you extend:

1. **Blocked checks report their gap.** A check with no data source says so every cycle
   rather than being quietly dropped. This is why the personal-risk gap became visible
   the moment it was registered, instead of remaining an absence nobody could see.
2. **Silence is the healthy state.** The hourly agent's default answer is "nothing".
3. **Staleness is surfaced, never hidden.** `_stale_hours()` on the broker bridge; the
   compliance check flagging its own April seed dates as untrustworthy.
4. **Never invent a number.** Written into the agent's rules and into `MDO_VISION.md`
   §19. For a system that will eventually inform real money decisions, this is the
   property that makes it usable at all.

Any new domain must arrive with all four, or it degrades the whole.

---

## 6. Build order

**Now — closes the loop (days, not weeks)**
1. `memory` table + `remember` tool + retrieval into the Brain's prompt. §3a.
2. Fill the personal registers from a folder of photographs. Unblocks four checks.
3. Send the CA briefing email; engage the advocate. Four months old, has a clock.

**Next — makes it decide, not just report**
4. Two more Tier 1 skills (`weekly-operating-review`, `tender-go-no-go`). Agents load
   them as prompts, humans read them as SOPs. This is the operator→architect path.
5. Fill the ⚠️ thresholds in `escalation-routing`, and the names in `MDO_VISION.md` §3.
   The skill routes to roles that currently have no people in them.
6. Bank statements via Gmail MCP — one connector clears `bank_balances` *and*
   `liabilities_emi`.

**Then — extends the senses**
7. VPN Phase 1 (rotate both certificates), then Phases 2–6. Everything is written and
   waiting behind the rotation.
8. Singhvi live test. The RAM blocker disappeared when you left Railway.
9. Staah token.

**Ongoing**
10. One skill a week. Thirty-four remain; at one a week the library is complete inside
    a year, and each one makes both the agents and any future COO sharper.

---

## 7. How you will know it is working

Not by feature count. By these:

- You stop re-explaining context you have already explained. *(memory works)*
- You open the app to confirm something you were already told, not to discover it.
  *(inbound works)*
- A decision made in conversation on Monday shows up in Friday's briefing without you
  carrying it there. *(the loop closes)*
- Someone who is not you can run a shift from the playbooks. *(the COO becomes possible)*
- The system tells you something about your own affairs that you had forgotten — a
  premium due, a guarantee outstanding, a policy nobody has looked at in three years.
  *(it is a Life LLM, not a business dashboard)*
