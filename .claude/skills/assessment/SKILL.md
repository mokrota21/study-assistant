---
name: assessment
description: Run колоквиум (announced oral theory exam with formulation gate and доп вопросы), practical interleaved exams, and remediation sessions. Use when an assessment triggers, is scheduled, or the user asks to be examined.
---

# Assessment

Three instruments, each doing a different job: the **колоквиум** verifies theory orally,
the **exam** verifies applied problem-solving, and **remediation** replaces surprise exams.

## Exam pool accrual (continuous)

Every covered concept deposits held-back questions into three pools at block wrap-up:
`formulations` (definitions, theorem statements), `proofs`, `problems`. Use
`deposit_pool_item` with tags for concept, difficulty and format, and grading criteria
written at creation time.

Run `publish_pools(subject)` regularly. Pools are **visible to the user** — an announced
колоквиум draws from a known list, exactly like the real one. Preparation against a known
pool is not cheating; it is the mechanism.

In scoped mode, prefer the textbook's own problems and set `source`.

## Колоквиум — announced oral theory exam

**Trigger:** `kolokvium_check(subject)`. Roughly six to eight weeks of accumulated material,
enough provable items, and pools deep enough to draw from.

**On trigger:**

1. `draw_ticket(subject)` to draft the ticket set and show the user what a ticket looks like.
2. `announce_assessment(subject, "kolokvium", scheduled_at, ticket)`.
3. `schedule_assessment(...)` — places the колоквиум block plus dedicated preparation
   sessions before it.
4. `publish_pools(subject)` and tell the user where the pools are.

**Ticket:** 3 formulation questions + 1–2 proof questions + optionally 1 problem, drawn
from the published pools. Draw the actual ticket at the start of the session, not before.

**Formulation gate — hard.** After the three formulations, call
`formulation_gate(subject, verdicts)`. More than one failure **stops the колоквиум**: keep
formulation credit only, award no proof credit, and schedule remediation. No proof credit
without fundamentals. Do not soften this because the user is close or was unlucky.

**Format: conversational.** This is the anti-memorization mechanism and the reason an oral
format reveals understanding better than a written one.

- Ask the question. Let them answer fully before responding.
- Then **доп вопросы** on the weak spots: "why is that hypothesis needed?", "what breaks if
  we drop completeness?", "give me an example where this fails", "you said 'clearly' —
  show me."
- Probe *every* answer that sounded recited, including correct ones. Fluent recitation of a
  definition and understanding of it are different things, and only follow-ups separate them.
- Do not teach during the колоквиум. Note the gap and move on.

**After:** grade each item (see `grading` — two independent passes on high stakes), write
the record to `subjects/<subject>/results/`, call `record_assessment_result`, and act on
the remediation report it returns.

## Practical exam

**Trigger:** `exam_check(subject)` — the problem pool crossed its threshold.

Generate an exam covering all or most topics. **Interleaved**: problems unlabeled, mixed
across sub-skills, not grouped by method. That forces method *selection*, which blocked
practice never trains and which is most of what "being able to do it" means.

Solo mode throughout. No hints during an exam — the stuck hatch is a practice instrument,
not an exam one.

## Remediation — instead of surprise exams

There are no surprise exams here. The "continuous preparation" effect they exploit assumes
external stakes a self-learner does not have; all a surprise exam produces is a bad day.

Instead: `remediation_check(subject)` after every assessment and periodically. Any concept
below the threshold gets a **dedicated supervised-practice session**, scheduled like any
other block (`propose_schedule(..., kind="remediation")`). Supervised means you are present:
worked examples, then drills, then unassisted retrieval on the specific weakness.

## Delayed re-checks

`delayed_rechecks(subject)` lists concepts whose provisional mastery is due for a
weeks-later re-check. Fold them into review segments. Grade with `kind="delayed_recheck"`.
A failure calls `revoke_mastery` and reschedules drilling — mastery here is provisional by
design, and the gap between in-session performance and delayed re-check pass rate is the
primary health metric of the whole harness (`harness_health`).
