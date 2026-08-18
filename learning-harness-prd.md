# PRD: Learning Harness

**Status:** Draft v1
**Date:** 2026-08-06
**Owner:** [you]

---

## 1. Vision

A universal harness that takes a person from "I want to learn X" to genuine mastery — understanding the theory *and* being able to apply it in practice. Universal means the same system eventually serves theoretical math, hardware understanding, cooking, or any other domain.

The core bet, validated by learning science: explanation alone doesn't produce skill. Mastery comes from **isolated deliberate practice** (drilling one sub-skill at a time, varied exercises, at the edge of ability), **retrieval practice** (fresh generated questions, not rereading or flashcards), **spaced repetition** (distributed over time, not massed grinding), and **mastery gating** (no advancement past unproven prerequisites). The harness's job is to construct exercises where the target concept is the bottleneck, enforce the schedule, and honestly verify understanding.

### Milestones

| # | Scope | Definition of done |
|---|-------|-------------------|
| M1 | Theoretical knowledge | Full loop works for a theory-heavy subject (e.g., a math course): intake → curriculum → scheduled study blocks → retrieval reviews → колоквиум → exam |
| M2 | + Tailored practice exercises | Isolated sub-skill drills with solo mode, hard-problem outsourcing, practical exams |
| M3 | + Real-life / hands-on projects | Physical-world skills decomposed and drilled; project milestones count as exams |

### Guiding principle from research (non-negotiable)

The two flagship AI-tutor RCTs differ only in guardrails: guardrailed tutor → 2× learning gain (Harvard PS2); unguarded GPT access → +48% practice performance but **−17% on the independent exam** (Bastani, Turkish schools). Students used AI as a crutch and didn't notice their learning degrade. Every design decision below that restricts AI help during practice exists because of this result.

---

## 2. Form factor

**Claude Code chat** as the top-level interface. Rationale: the filesystem is the state store for free (plans, notes, materials, exam pools as files — inspectable, diffable, portable), the agent loop handles orchestration, and iteration on pedagogy is prompt-editing, not software releases.

**MCP server** owns only what needs computation and dynamic state:
- Scheduler (availability windows, block placement)
- Spaced-repetition queue (FSRS)
- Block clock + background timer (OS notifications for the human; see §3.4.1)

**Claude Code hooks** (UserPromptSubmit, PostToolUse, Stop) make time-awareness and block-end automation deterministic rather than model-dependent (§3.4.1).

**Files** own everything else. Per-subject folder layout:

```
subjects/<subject-name>/
  plan.md                  # curriculum: concept graph, frontier, status per concept
  materials/               # collected raw documents (textbook excerpts, articles)
  lessons/
    lesson-NNN.md          # prepared lesson: stages, explanations, problems, rubrics
  notes/
    YYYY-MM-DD.md          # what happened each study day (auto-written at block end)
  covered.md               # running log of covered material (колоквиум/exam trigger source)
  exam-pool/
    formulations.md        # definitions & theorem statements pool
    proofs.md              # proof questions pool
    problems.md            # problem ideas pool
  results/                 # graded колоквиум/exam records
```

---

## 3. Subject lifecycle

### 3.1 Intake

**Input:** (a) subject name — required; (b) textbook(s) / documents with problem sets — optional.

**Two explicit curriculum modes**, chosen at intake:

- **Exploratory mode** (no textbook, or user doesn't know how far to go): agent runs deep research to build a study plan and collect materials. The concept frontier is *proposed* by the agent and negotiated with the user; expansion via explicit command.
- **Scoped mode** (textbook(s) given): the agent's contract is to ensure the user understands the material of this book — **not under, not over**. The frontier is *derived* mechanically from the book's table of contents. Coverage is tracked against the TOC ("not under"). Supplementary material may be collected to improve explanation quality but never widens scope; adjacent topics are logged as suggestions and pursued only on user command ("not over"). The book's own problem sets become the primary exam-pool source (real problems beat generated ones). Multiple textbooks = union of TOCs with agent-proposed deduplication.

All collected materials land in `materials/`; the plan in `plan.md`.

**Scope control — concept graph boundary (not token limits).** In both modes the curriculum is an explicit concept list with a marked frontier:

- **Included:** concepts in scope, with prerequisite edges
- **Excluded but adjacent:** named concepts deliberately left out

The user approves or trims. Expansion is an explicit command ("expand into <concept>") that pulls an excluded node in and triggers incremental research + plan update. A token/effort budget may cap the *research phase* as a secondary control, but scope itself is always defined in concepts.

### 3.2 Scheduling

MCP scheduler tool exposes availability windows based on already-blocked time.

- Supports non-study blocks (user's life commitments).
- Fills windows one by one; **re-indexes available windows after each placement**.
- **Focus rhythm:** 50 minutes focused study, then ≥10 minutes break. Longer break after ~2 hours. Prefer 2 sessions on 2 days over one double session (spacing beats massing — strongly evidenced).
- **Horizon: max 2 weeks ahead**, and only as a *vague* plan (which topics, roughly), because actual pace is unpredictable.
- All rhythm parameters live in config (see §7).

### 3.3 Lesson preparation — rolling window with detail gradient

A rolling ~1-week preparation window, maintained continuously:

- **Next 1–2 lessons: fully prepared** — lesson stages, explanations, worked examples, practice problems *with grading rubrics generated at creation time*.
- **Lessons 3–7: shaped outlines** — topics, lesson stages, which concepts compound into which. Cheap to reshuffle when pace shifts.

Trigger: writing lesson N's notes (block end) automatically kicks off full preparation of lesson N+1 and outline extension of the window.

### 3.4 Study block structure

Every block = **review segment first, then new material**:

1. **Review segment (~15 min placeholder in plan; actual content fetched live).** At block start, agent calls MCP: "everything due now, capped at M items, overdue first." Order: overdue → due → ahead-of-schedule if time remains. Each review = a **freshly generated free-recall / short-answer mini-exercise** on the due sub-skill — never a flashcard. Graded result feeds back to FSRS as the rating.
2. **New material.** Explanation-first (concise, one step at a time — CLT/Direct Instruction style), 1–2 worked examples, then retrieval exercises on the new concept.

**Enforcement mechanic:** if the review queue overflows the segment, it eats into new-material time. Self-balancing: many failed reviews = moving too fast anyway. Overdue reviews are mandatory before new material — structurally, not by willpower.

**Block end:** notes auto-written to `notes/YYYY-MM-DD.md` (or manually triggered); `covered.md` updated; exam-pool deposits made (§5.1); lesson N+1 prep triggered.

### 3.4.1 Time awareness during blocks

Constraint: MCP servers cannot push messages into an idle Claude Code conversation (turn-based loop). Time awareness is therefore built from **Claude Code hooks + MCP-owned clock**, requiring zero user vigilance:

1. **`start_block(duration, type)`** (MCP) writes block state — start time, duration, segment — to a state file.
2. **UserPromptSubmit hook** reads the state file and injects `[Block: elapsed/total, segment status]` into context on *every* user message. Hooks always run — unlike instructions, the model cannot forget them as context fills.
3. **PostToolUse hook** injects the same via `additionalContext` on tool calls, covering long agent-driven stretches.
4. **Stop hook** at block end: refuses Claude's stop and injects the wrap-up directive — write notes, update `covered.md`, trigger next-lesson prep. Makes block-end automation deterministic.
5. **Solo-mode gap** (user working alone, no messages, no tool calls → no hooks fire): the human is the one who needs the signal. The MCP server runs a background timer and fires an **OS desktop notification** ("time's up / break"). On the user's next message, the hook brings Claude current instantly.

### 3.5 Mastery

A concept counts as mastered only after meeting a **dual threshold: time-on-task × repetitions** (both configurable minimums), where reps are *varied* exercises isolating the same sub-skill ("20 differently pre-salted broths"), **distributed across spaced sessions** — not massed in one sitting (overlearning research: massed extra reps decay; spaced reps persist). Prerequisites are strictly gated: no advancement until the prerequisite passes its gate.

Mastery is provisional: failing spaced re-checks weeks later revokes it and reschedules drilling (see §8, performance-vs-learning).

---

## 4. Spaced repetition

- **Algorithm:** FSRS via open-source library (py-fsrs / ts-fsrs / fsrs-rs), wrapped in the MCP server.
- **Unit:** the sub-skill/concept, *not* the individual exercise. A due "card" means "generate a fresh mini-exercise on this sub-skill."
- **Never pre-allocate reviews into future blocks.** The schedule reserves review *capacity*; the queue stays live and is fetched at block start. (FSRS due-dates shift with every graded review — freezing a two-week allocation defeats the algorithm.)
- Desired retention default 0.90 (configurable).
- **Later (M2+):** hierarchical trickle-down credit (Math Academy FIRe-style) — success on an advanced skill discounts prerequisite reviews. Simplified version acceptable; prevents review-load explosion and "sea of isolated facts."

---

## 5. Assessment

### 5.1 Exam pool accrual

Every covered concept deposits held-back questions into three pools (mirroring HSE ПМИ колоквиум structure): **formulations** (definitions, theorem statements), **proofs**, **problems**. Items tagged by concept, difficulty, format. Pools are **visible to the user** for preparation — announced exams draw from a known list, exactly like the real коллоквиум.

### 5.2 Колоквиум (announced theoretical exam)

Calibrated against real HSE ПМИ практика (матан, multiple years):

- **Trigger:** ~6–8 weeks of covered material accumulated in `covered.md` (or configurable concept count including several "provable" items). Agent drafts the ticket set and announces the колоквиум; scheduler places it plus **dedicated preparation sessions** before it.
- **Ticket:** 3 formulation questions + 1–2 proof questions + optionally 1 problem, drawn from the published pools.
- **Formulation gate:** fail more than 1 formulation → колоквиум stops, only formulation credit is kept. No proof credit without fundamentals.
- **Format:** conversational — agent asks follow-up / probing questions (доп вопросы) on weak spots. Anti-memorization by design; also where an oral format demonstrably reveals understanding better than written.

### 5.3 Exam (practical)

- **Trigger:** problem-idea pool exceeds threshold → agent generates an exam covering all or most topics.
- Interleaved: problems unlabeled, mixed across sub-skills — forces method *selection*, which blocked practice never trains.

### 5.4 Remediation sessions (replaces surprise exams)

No surprise exams: the "continuous preparation" effect they exploit assumes external stakes a self-learner doesn't have. Instead: **performance below a configurable threshold triggers a dedicated supervised-practice session** on the weak concepts, scheduled like any block.

### 5.5 Grading

- **Rubric at creation time, never at grading time.** Every exercise/problem is born with a math-olympiad-style rubric and reference solution. (A model grading its own fresh interpretation of a question is the sycophancy trap.)
- **Novel-solution clause:** the rubric predicts the common approach; a novel approach receives full score if verified correct.
- **Theory questions:** binary **required-elements checklist** created when the question enters the pool ("full answer contains: definition of X, statement of Y, counterexample for Z"). Grade = elements present / partial / missing. No unanchored "percentage answered."
- **Search-assisted grading (M2):** for open problems, agent searches for worked examples of similar problems to cover alternative solution angles before judging.
- **Self-consistency on high stakes:** колоквиум/exam answers graded twice; disagreement → flagged for user review. Routine reviews graded once.
- If AI-grading agreement with user spot-checks falls below ~80–85%, open-ended auto-grading is pulled from the mastery gate and restricted to reference-matchable items.

---

## 6. Practice protocol (M2 core, partially in M1)

- **Solo mode:** exercises completed without AI help. This is the point of the whole system.
- **Stuck hatch:** when genuinely stuck, one invocation yields **one hint — never the answer** — grounded in the reference solution, and is logged against the concept.
- **Hint analytics:** frequent hatch use on a concept blocks mastery and schedules more drilling.
- **Difficulty honesty:** AI-generated problems cluster easy-medium. Acceptable for drilling; for hard problems the agent (a) searches curated sources / Math StackExchange, (b) parameterizes known-hard problems (safer than inventing), (c) failing both, recommends books / reading lists for independent work.

---

## 7. Configuration

Central `config.py` — pydantic Settings object reading env vars. Everything tunable, per-domain overrides supported:

| Parameter | Default |
|---|---|
| Focus block / break | 50 min / ≥10 min |
| Long break | after ~2 h |
| Mastery: min time-on-task × min varied reps | per-domain |
| FSRS desired retention | 0.90 |
| Review cap per block (M items) | TBD |
| Scheduling horizon | 14 days |
| Prep window (full / outline) | 2 lessons / 7 lessons |
| Колоквиум trigger | ~6–8 weeks of material |
| Exam trigger | problem-pool threshold |
| Remediation threshold | TBD |
| Grading self-consistency | 2× on exams |

Self-report is trusted (RLHF-flavored honesty) — the system verifies understanding via retrieval and exams, not surveillance.

---

## 8. Instrumentation: performance vs. learning

The system must never optimize the fluency illusion. Track separately:

- **In-session correctness** (performance) — cheap signal, systematically misleading.
- **Delayed re-check pass rate** (learning) — did the concept survive weeks later?

If learners pass mastery gates but fail delayed re-checks at high rates → tighten the gate (more consecutive correct, longer initial spacing). This is the primary health metric of the harness.

---

## 9. Milestone breakdown

**M1 — Theoretical knowledge**
- Subject intake + concept-graph scoping + material collection
- Subject folder structure, plan.md, notes automation
- MCP: scheduler + FSRS queue
- Study blocks: review-first structure, live review fetch, explanation engine
- Mastery gates on concepts
- Exam pool accrual (3 pools), колоквиум (full spec §5.2), remediation triggers
- Grading v1: creation-time rubrics, element checklists, self-consistency on exams

**M2 — Tailored practice**
- Exercise generator: isolated sub-skill drills, varied, with reference solutions
- Solo mode + stuck hatch + hint analytics
- Hard-problem outsourcing pipeline
- Search-assisted grading
- Interleaved review sets + practical exams
- Hierarchical trickle-down credit in FSRS

**M3 — Real-life projects**
- Project decomposer → sub-skills mapped to concept graph
- Physical exercise design; evidence-based check-ins (user reports, agent probes)
- Project-as-exam; cross-domain transfer tracking

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| AI-as-crutch degrades learning while inflating perceived progress | Solo mode, one-hint hatch, hint logging, delayed re-checks (§8) |
| LLM grading unreliability / sycophancy | Creation-time rubrics, element checklists, self-consistency, agreement monitoring with pull-out threshold |
| Generated problems too easy for true mastery | Outsourcing pipeline; honest labeling of difficulty ceiling |
| Self-paced mastery → abandonment (documented mastery-learning cost) | Overdue-reviews-first enforcement; unfinished subjects before new ones |
| Stale prepared lessons when pace shifts | Rolling window + detail gradient (only 1–2 lessons are expensive) |
| Frozen review plans fight the SR algorithm | Live queue fetch; schedule reserves capacity only |
| Curriculum scope creep ("multiplication → all of math") | Concept-graph frontier + explicit expand command |

## 11. Open questions

1. Scheduler's calendar source — integrate an external calendar or maintain its own blocked-time store?
2. Exact review cap M per block and remediation threshold — set after first weeks of real usage data.
3. Trickle-down credit model — full FIRe-style graph propagation vs. simplified one-level discount.
4. M3 evaluation of physical skills — photo/description-based verification protocol needs its own design round.
5. **Known gap (accepted for now):** Claude only becomes time-aware when a hook fires — i.e., on a user message or tool call. During idle stretches the agent has no clock; the OS notification covers the human but not the model. Revisit if this causes real problems in practice (e.g., agent overrunning a block mid-generation).
