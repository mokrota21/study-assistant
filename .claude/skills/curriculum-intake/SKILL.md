---
name: curriculum-intake
description: Take a new subject from "I want to learn X" to an approved concept graph, collected materials, and a first two-week schedule. Use when the user names a new subject, provides a textbook, asks to start studying something, or wants to expand an existing subject's scope.
---

# Curriculum intake

Produces four things: a scoped concept graph, materials in `materials/`, a `plan.md` the
user has approved, and a schedule. Nothing is drilled before the user approves the scope.

## 1. Establish the mode

Ask for the subject name (required) and any textbook / document with problem sets
(optional). Then pick the mode explicitly and record it — the two differ in **where scope
comes from**, and both rest on the same assumption about the learner: **they cannot yet
audit their own gaps.** In scoped mode the book settles scope; in exploratory mode your
research proposes it. In neither does the learner's self-assessment settle it — not knowing
that a prerequisite exists is indistinguishable, from the inside, from not needing it.

**Scoped mode** — textbook(s) given.

*Learner stance: they do not know this material yet.* That is why there is a book. They
picked it, or it was assigned, precisely because they cannot yet judge what matters in this
subject. **The book is the authority and you are teaching it to them.**

- Your contract: the user understands the material of this book — **not under, not over.**
- The frontier is derived *mechanically* from the table of contents. Read the TOC, do not
  invent structure, and do not quietly drop sections that look inessential to you.
- Track coverage against the TOC in `plan.md` ("not under").
- Supplementary material may improve explanation quality but never widens scope. Adjacent
  topics get logged under "Open suggestions" and are pursued only on explicit command
  ("not over").
- **The book's own problem sets are the primary exam-pool source.** Real problems beat
  generated ones; deposit them with `source` set to the book reference.
- Multiple textbooks: union of TOCs, with your proposed deduplication for the user to approve.
- **Do not ask them to trim the scope.** They have no basis for it — "is Chapter 7 worth
  doing?" is a question about material they have not seen. Show the graph for orientation
  and pace, take their constraints (deadline, hours per week), and adjust the *schedule*
  rather than the *scope*. If the book genuinely must be cut, propose the cut yourself with
  reasoning, and say what they lose.

**Exploratory mode** — no textbook.

*Learner stance: treat their self-assessment as unreliable.* They may tell you how far they
want to go, and they may even be right — but they cannot see what they have never met.
**Their stated goal is the seed, not the boundary. You propose the shape of the subject.**

- Take their goal as the starting point, then **research what actually surrounds it**
  (WebSearch/WebFetch): what it rests on, what it is normally taught alongside, where people
  who skip parts of it get stuck later.
- **Surface what they did not ask for.** If their target needs three prerequisites they never
  mentioned, saying so is the most valuable thing you produce at intake. Name them explicitly
  rather than quietly folding them into the graph.
- The frontier is *proposed* by you and then negotiated, with **you leading the negotiation**:
  explain what each branch buys and what cutting it would cost, then let them decide. "Do you
  want measure theory?" is a bad question — they cannot answer it. "Without measure theory
  you cannot do X, which you said you wanted — keep it?" is a good one.
- Do not treat "I don't need that" as final until you have said what it forecloses. Once you
  have, it is their call.
- Fill the excluded-but-adjacent list carefully. It is how unknown unknowns become visible.
- Ask where they want to end up in practice ("able to read papers", "able to cook this without
  a recipe"). A concrete endpoint sets the depth far more reliably than a self-rating does.
- Cap the research phase by effort, but define scope in concepts, never in tokens.

## 2. Scaffold

Call `create_subject(subject, mode, sources, domain)`. It creates the folder tree and
seeds `plan.md` and `covered.md`. Set `domain` (e.g. `math`, `cooking`, `hardware`) so
per-domain config overrides apply.

## 3. Collect materials

Save what you gather into `materials/` as readable files, with provenance at the top of
each (where it came from, when, why it is in scope). For a physical textbook the user
owns, record the TOC and the problem-set structure — that is what the harness needs.

## 4. Build the concept graph

The scope control is the **graph boundary**, not a token budget. Write the concept table
in `plan.md`:

| Concept | Prerequisites | Provable | Source | Status |
|---|---|---|---|---|
| Sequence limit | — | yes | Zorich 3.1 | planned |
| Cauchy criterion | Sequence limit | yes | Zorich 3.2 | planned |

Rules:

- Prerequisite edges are real dependencies, not chapter order. "Ch. 4 follows Ch. 3" is
  not an edge; "you cannot state the Cauchy criterion without the limit definition" is.
- Mark `provable: yes` for anything carrying a theorem or proof obligation — those items
  feed the колоквиум trigger and the proofs pool.
- Keep concepts drillable. "Real analysis" is not a concept; "prove a sequence converges
  from the ε-N definition" is. If you cannot imagine a five-minute exercise isolating it,
  split it.
- Fill the **Excluded but adjacent** section with named concepts you deliberately left
  out. This is what makes scope creep visible.

Then present the graph — but what you are asking for depends on the mode:

- **Scoped:** present it for *orientation*, not for scope approval. "Here is what the book
  covers, here is the order, here is roughly how long." Ask about constraints — deadline,
  hours per week — and adjust the schedule to fit. They cannot sensibly trim material they
  have not met.
- **Exploratory:** present it for *guided negotiation*. Walk them through it — what each
  branch is for, what it depends on, what dropping it would cost them later. They can and
  should push back, and the final call is theirs; your job is to make sure the call is
  informed. Rework the graph on their decisions and record what was cut in the excluded list.

Either way, say plainly how long you expect it to take. When it is settled, call
`register_concepts`, then `seed_cards`.

## 5. Schedule

1. Ask for life commitments and record them with `add_commitment` (recurring:
   weekdays + start/end times; one-off: explicit start/end).
2. `available_windows` to show what is actually free.
3. `propose_schedule(subject, count, topics, commit=False)` — show the proposal, let the
   user trim, then re-run with `commit=True`.

Horizon is two weeks and the plan past the first few days is **intentionally vague**:
which topics roughly, because real pace is unpredictable. Do not write a detailed
day-by-day curriculum for two weeks; it will be wrong by Wednesday.

## 6. Prepare the first lessons

Load the `lesson-prep` skill: lessons 1–2 in full, 3–7 as shaped outlines.

## Expanding scope later

"Expand into <concept>" is the only way scope grows. On that command: pull the node from
excluded into included, run incremental research, update `plan.md` and the excluded list,
call `register_concepts` and `seed_cards`, and tell the user what it costs in time. Never
widen scope because a topic came up naturally — log it under Open suggestions instead.
