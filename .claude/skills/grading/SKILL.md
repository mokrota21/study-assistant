---
name: grading
description: Score answers against creation-time rubrics and required-element checklists, with self-consistency on high-stakes items and agreement monitoring. Use whenever grading a review, exercise, proof, or exam answer.
---

# Grading

The failure mode this skill prevents: a model reading an answer, forming an opinion of the
question from the answer, and grading generously against that. Sycophancy dressed as
assessment. Every rule below closes one route to it.

## The criteria exist before the answer

**Never construct grading criteria while looking at the user's answer.** They were written
when the exercise was created and live in the lesson file or the pool item. Load them, then
grade. If you find yourself deciding what "counts" after reading the response, stop — you
have already lost the measurement.

If an exercise somehow has no criteria, write them *before* reading the answer, from the
question alone, and say that you did.

## Theory questions — binary element checklist

Every formulation and proof item carries `required_elements`, written when it entered the
pool:

> full answer contains: definition of uniform continuity; the quantifier order δ before x;
> a counterexample showing pointwise continuity is weaker

Grade element by element: **present / partial / missing.** The score is elements present
over elements required. Never an unanchored "you answered about 70% of that" — that number
means nothing and is exactly where drift enters.

Report which elements were missing. That report is more useful to the user than the score.

## Problems — rubric with a novel-solution clause

Score against the rubric's point allocation. Then:

> **Novel-solution clause.** The rubric predicts the common approach. A different approach
> receives full marks if it is correct. Verify it on its own terms — actually check the
> steps — rather than penalizing it for not matching the reference.

If you cannot verify a novel approach, say so and flag it for the user rather than guessing
in either direction.

## Hints change the score

An answer produced after a hint is not equivalent to an unassisted one. Pass
`hints_used` to `grade_review`; it caps the FSRS rating at Hard. Do not quietly forgive a
hint because the final answer was good — that is the crutch effect, and it is invisible
until the exam.

## Self-consistency on high stakes

Колоквиум and exam answers are graded **twice, independently**. Grade once against the
criteria; then grade again as if you had not, deliberately looking for what the first pass
was generous about. If the two disagree materially, do not average — flag it for the user
to review, and record the outcome with `log_grading_spotcheck`.

Routine reviews are graded once. The cost is not worth it there.

## Agreement monitoring

When the user disagrees with a grade, that is data, not an argument to win. Call
`log_grading_spotcheck(subject, ai_score, user_score, item_ref)`. If agreement falls below
the configured threshold (~82%) over enough checks, open-ended auto-grading is pulled from
the mastery gate and restricted to reference-matchable items. `harness_health` reports the
current agreement rate.

Invite spot-checks periodically — the metric is worthless without samples.

## Delivering a grade

1. The verdict, plainly. Correct, partially correct, or not.
2. Which required elements were missing — specifically.
3. What to do about it. Usually: this concept is now due sooner, or it needs re-drilling.
4. Then `grade_review(...)` with `score`, `variant`, `hints_used`, `kind`.

No praise padding. "That's a solid attempt but…" wastes the one moment the user is
attending to feedback. If it was right, say it was right and move on. If it was wrong, say
what was wrong.

## Recording

- Routine review → `grade_review(kind="in_session")`
- Weeks-later re-check → `grade_review(kind="delayed_recheck")` — **this separation is the
  primary health metric of the system**; never record a re-check as a normal review
- Колоквиум / exam → `grade_review(kind="kolokvium"|"exam")` per item, plus
  `record_assessment_result` for the whole sitting
- Always pass `variant`. Untagged reps do not advance the mastery gate.
