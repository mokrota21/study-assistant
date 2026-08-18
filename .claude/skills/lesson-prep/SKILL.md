---
name: lesson-prep
description: Prepare lessons in the rolling one-week window — the next 1-2 in full detail with rubrics, the following 3-7 as cheap reshuffleable outlines. Use at block wrap-up, when the pace shifts, or when the user asks what is coming next.
---

# Lesson preparation — rolling window with detail gradient

Full preparation is expensive and goes stale the moment the pace changes. So only the
next one or two lessons are expensive; the rest are cheap enough to throw away.

## The gradient

**Lessons N+1 and N+2 — fully prepared.** `subjects/<subject>/lessons/lesson-NNN.md`:

```markdown
# Lesson NNN — <topic>

**Concepts:** <names exactly as registered in plan.md>
**Prerequisites checked:** <check_gate result>
**Estimated:** <minutes>

## Stages
1. Review segment (live queue — not listed here)
2. <stage>: <what happens, how long>

## Explanation
<concise, one step at a time; the minimum that makes the worked example legible>

## Worked examples
### Example 1
<full solution, reasoning visible, including why this approach and not another>

## Practice
### P1 — <sub-skill isolated> — variant tag: <tag>
<problem>
**Reference solution:** <full>
**Rubric:** <points and what earns them>
**Common wrong turn:** <the one you expect, and the hint that unsticks it without solving>

## Held back for the exam pool
<items to deposit at wrap-up, with their required elements / rubrics>
```

Rubrics and reference solutions are written **now**, at creation time. That is the whole
point — see the `grading` skill.

**Lessons N+3 to N+7 — shaped outlines.** Topic, stages, which concepts compound into
which, roughly how long. Two or three lines each, kept at the bottom of the newest lesson
file or in `plan.md`. Cheap to reshuffle when the pace shifts, and it will.

## Trigger

Writing lesson N's notes at block end automatically kicks off:

1. Full preparation of lesson N+1.
2. Extension of the outline window so it still reaches seven lessons out.

Do not batch-prepare a fortnight of lessons. If the user asks for it, explain that
prepared lessons go stale within days and offer the outline instead.

## When the pace shifts

The common case: the user needed two blocks for what you outlined as one.

1. Do not compress. Re-outline from where they actually are.
2. Check whether the sticking point is a missing prerequisite — `mastery_check` on the
   concepts involved and `check_gate` on what came next. Often the outline was wrong, not
   the learner.
3. Rewrite the outline window; leave the prepared lesson N+1 alone if it is still next.
4. If the schedule now looks unrealistic, say so and re-run `propose_schedule`.

## Sequencing rules

- One new concept at a time as the bottleneck. If an exercise needs two new things, split
  it.
- Interleave *old* concepts into practice as soon as there are two of them — method
  selection is a skill of its own, and blocked practice never trains it.
- Compound deliberately: a lesson that uses last week's concept as a tool is better than
  one that re-teaches it.
- Never plan a lesson whose prerequisites are not yet mastered. `check_gate` decides that,
  not the chapter order.
