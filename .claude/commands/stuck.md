---
description: Request the one hint allowed on the current exercise
argument-hint: [what you have tried]
---

The user is stuck: **$ARGUMENTS**

Use the `solo-practice` skill. Exactly this:

1. Check they are genuinely stuck rather than uncomfortable. Brief discomfort is the
   mechanism working.
2. `stuck_hatch(subject, concept, exercise_ref, hint_text)` **before** you say anything.
3. Give **one** hint, grounded in the reference solution written when the exercise was
   created. Name the kind of move, not the move: "the hypothesis you haven't used yet is
   doing the work here", not "use completeness".
4. Stop. No second hint on this exercise. If they are still stuck, the exercise is too hard
   or a prerequisite is missing — end it, mark it, and drill the prerequisite instead.

The hint caps the rating at Hard and is logged against the concept. Pass `hints_used` when
you grade. Do not forgive it because the final answer was good.
