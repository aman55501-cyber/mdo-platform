# MDO Memory — Design for Review

> ## ⚠️ PROPOSAL ONLY — NOT BUILT, NOT APPLIED
>
> Aman asked to set up MDO memory but to hold until he reviews it. So this is a
> design document: **no table was created, no tool added, no prompt changed.**
> Nothing in the running system is affected by this file existing.
>
> When you approve it, the build is roughly a day. Say "build the memory" and I
> will implement exactly what is below, or the amended version you mark up.

---

## The problem, stated precisely

MDO has 21 tables and **not one stores a decision, a preference, a constraint or a
piece of reasoning.** The Brain has 22 tools: 20 read, 2 write (`add_task`,
`add_intel_item`). You can ask it anything and teach it nothing, so every session
restarts from the documents and you re-explain context you know you have already
explained.

## The thing NOT to do

Do not build a second memory store. **`_memory/` already exists** in MD's Office —
registry, areas, topics, log, with `weekly-memory-sync` on Sundays. A fresh MDO
memory table would be a *third* source of truth after the files and `_memory/`, and
the whole problem in [TWO_SYSTEMS.md](TWO_SYSTEMS.md) is that truth is already
split.

So the design is deliberately in two stages, and stage 1 is the smaller one.

---

## Stage 1 — MDO reads `_memory/` (half a day)

One new Brain tool, `recall`, and one mounted path. Nothing is written.

- Mount the `_memory/` directory into the backend container read-only, as
  `/memory`, via a `docker-compose.yml` volume line. Read-only is deliberate:
  stage 1 cannot corrupt the store even if it has a bug.
- Add a `recall(query, kind=None, limit=10)` Brain tool that greps/reads the
  registry, areas, topics and log and returns matching entries with their file and
  line, so every answer can cite where it came from.
- Add one line to the Brain's system prompt: *before answering a question about
  Aman's decisions, preferences, people or history, call `recall` first.*

**What you get for half a day's work:** the Brain stops contradicting decisions you
already made and recorded. This alone closes most of the "it does not know me" gap.

**The one open question I need answered:** where does `_memory/` physically live on
the VPS, and is it inside `/docker/sharecfo/` (soon `/docker/life-llm/`) or in a
different tree? I have never seen it — it does not exist in this repo. Its path is
the only thing blocking stage 1.

---

## Stage 2 — MDO writes memory (half a day)

Only after stage 1 proves the read path.

### The table

```sql
CREATE TABLE IF NOT EXISTS memory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,      -- decision | preference | constraint | fact | person
    subject      TEXT NOT NULL,      -- the thing this is ABOUT, e.g. "morning report"
    body         TEXT NOT NULL,      -- the statement itself, one idea per row
    domain       TEXT DEFAULT '',    -- capital | vwlr | hotel | compliance | personal | meta
    -- provenance: "Aman said, in chat, 17 Aug" carries different weight from
    -- "parsed from a WhatsApp group" or "read off a policy PDF"
    source       TEXT NOT NULL,      -- chat | whatsapp | document | agent | inferred
    source_ref   TEXT DEFAULT '',
    stated_by    TEXT DEFAULT 'Aman',
    stated_at    TEXT DEFAULT (datetime('now')),
    -- supersession, not accumulation
    supersedes   INTEGER,            -- memory.id this replaces
    superseded_by INTEGER,           -- set when something later replaces THIS
    confidence   TEXT DEFAULT 'stated',  -- stated | inferred | assumed
    FOREIGN KEY (supersedes) REFERENCES memory(id)
);
CREATE INDEX IF NOT EXISTS idx_mem_subject ON memory(subject);
CREATE INDEX IF NOT EXISTS idx_mem_live    ON memory(superseded_by) WHERE superseded_by IS NULL;
```

### Why supersession is the load-bearing part

A store that only appends becomes a pile of contradictions — the April portfolio
number and the August one both "true", and retrieval picks whichever it happens to
find. Every row therefore carries `supersedes`, retrieval defaults to
`superseded_by IS NULL`, and **nothing is ever deleted** so the history of a
changed mind stays readable.

This session produced four textbook cases, which is how I know the field is needed:

| Was | Became | Why supersession, not overwrite |
|---|---|---|
| 4 broker accounts | 6 accounts, 5 holders, +3 platforms | The old figure explains why past totals were wrong |
| morning brief at 06:30 is the surface | 08:30 roundup is the first report | You may want the old one back; the reason is the value |
| VPN sidecars for site access | Tailscale | The sidecar reasoning still applies to Tailscale |
| ITR unfiled, deadline passed | filed for all individuals + Aditi Investments | A stale 🔴 that never clears trains you to ignore 🔴 |

### The one tool that writes

`remember(kind, subject, body, domain, supersedes=None)`, plus one instruction in
the Brain's prompt:

> When Aman states a decision, a preference, a constraint, or a fact about his life
> or business that is not already in memory, call `remember`. Do not ask
> permission. Tell him afterwards, in one line, what you stored. If it contradicts
> something recalled earlier, pass that row's id as `supersedes` — never silently
> overwrite.

**Capture must be a byproduct of work you were doing anyway.** Anything that asks
you to stop and file something will be abandoned in a fortnight — the `[EDIT]`
markers in `MDO_VISION.md` §3, untouched since April, are the proof.

### Write-back to `_memory/`

Stage 2 writes to SQLite for speed and to `_memory/` on a schedule so the two
stay one store rather than two. Direction of truth: `_memory/` is canonical, MDO's
table is the working copy. If they ever disagree, `_memory/` wins.

---

## What I would NOT build

**No vector database over everything you have written.** It is the intuitive answer
and it produces a system that confidently retrieves your April opinions in August.
Structured memory with explicit supersession beats semantic search over an
undifferentiated pile — especially for a life, where almost every fact has a
valid-from date. Embeddings later, over the *distilled* memory, once there is
enough of it to be worth searching.

**No raw chat transcript archive.** Transcripts are mostly throat-clearing and
superseded reasoning; retrieving the discarded half of a conversation is worse than
retrieving nothing. Distil 3–8 durable statements at session end instead.

---

## Review checklist

Mark these up and I will build to your answers:

1. Where is `_memory/` on the VPS? **(blocks stage 1 — the only hard blocker)**
2. Are the five `kind` values right — decision, preference, constraint, fact,
   person? Anything missing?
3. Should `remember` write silently and report after, or ask before writing? I have
   proposed silently-then-report, because a prompt every time will make you stop
   using it. Your *"money / signature / regulator = Aman's click"* rule does not
   apply here: storing a note moves no money.
4. Is `_memory/` canonical with MDO as the working copy, or the reverse?
5. Stage 1 only for now, or both stages together?
