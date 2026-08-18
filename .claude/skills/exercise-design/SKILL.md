---
name: exercise-design
description: Design isolated sub-skill drills and varied exercise sets where the target concept is the bottleneck, each with a reference solution and creation-time rubric. Use when generating any practice problem, review exercise, or drill set.
---

# Exercise design

The single design criterion: **the target concept must be the bottleneck.** If the user
can fail your exercise for a reason unrelated to the concept — arithmetic, unfamiliar
notation, an unstated prerequisite, ambiguous wording — the exercise is broken, and worse,
it teaches the wrong lesson about where they are weak.

## Isolation

Before writing anything, name the sub-skill in one sentence: "recognize when the Cauchy
criterion applies and apply it", not "understand sequences". Then strip everything else
out. Give away the parts that are not being tested.

## Variation

Mastery counts **distinct variants**, so twenty copies of one exercise count as one rep.
"Twenty differently pre-salted broths": same sub-skill, different surface every time.
Rotate the axes:

- **Direction** — apply it forward / recognize where it applies / find the counterexample /
  reconstruct the statement from a use of it.
- **Representation** — symbolic, verbal, graphical, numeric, code.
- **Failure mode** — here is a wrong argument, find the flaw.
- **Boundary** — the edge case, the degenerate case, the hypothesis that cannot be dropped.
- **Selection** — mixed with other concepts, unlabeled, so the method must be chosen.

Pass the axis you varied as `variant` to `grade_review`. An untagged rep does not count.

## Difficulty honesty

Generated problems cluster easy-to-medium, and pretending otherwise is how a system
produces confident learners who cannot do hard problems. For genuinely hard material:

1. **Search curated sources** — the textbook's own problem sets first (in scoped mode
   these are the primary source and beat anything you write), then Math StackExchange,
   competition archives, published problem books.
2. **Parameterize a known-hard problem** — change the constants, the space, the hypothesis.
   Much safer than inventing: the difficulty structure is already validated.
3. **If neither works, say so** and recommend a book or reading list for independent work.
   That is an honest answer. A weak invented "hard problem" is not.

Label the difficulty you actually achieved (1 easy … 5 hard) and mean it.

## Every exercise is born with

- **A reference solution** — complete, not a sketch. You need it to give hints without
  leaking answers, and to grade consistently.
- **A rubric** — see the `grading` skill. Written now, before the user answers.
- **The expected wrong turn** and the one hint that unsticks it *without solving it*. This
  is what `stuck_hatch` will hand out, so write it in advance rather than improvising when
  the user is frustrated.

## Sets

For a drill set on one sub-skill: 5–8 items, ordered easy → hard, each varying a different
axis, spread across sessions rather than done in one sitting. Massed practice produces
fluency that decays; spaced practice produces knowledge that lasts, and the mastery gate
enforces the difference.

For an interleaved set (review, or a practical exam): mix sub-skills, leave the problems
unlabeled, and do not group them by method. Selection is the skill being trained.

## Anti-patterns

- Multiple choice, or anything the user can recognize rather than produce.
- "Explain X to me" as a review — too vague to grade against a checklist.
- Problems whose difficulty comes from tedium rather than insight.
- Exercises whose answer is visible in the explanation you just gave.
- A hard problem you cannot fully solve yourself. Do not deploy it.
