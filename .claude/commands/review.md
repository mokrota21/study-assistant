---
description: Review-only session — work the due queue, no new material
argument-hint: [subject] [minutes]
---

Run a review-only session: **$ARGUMENTS**

1. `start_block(subject, duration_minutes, kind="review")`.
2. `review_queue(subject)` and `delayed_rechecks(subject)` — overdue first.
3. For each item: generate a **fresh** free-recall or short-answer exercise. Never a
   flashcard, never a repeat. Vary the axis each time (`exercise-design` skill).
4. Grade against criteria written before the user answers, then `grade_review` with
   `variant`, `hints_used`, and `kind="in_session"` or `"delayed_recheck"`.
5. A failed delayed re-check calls `revoke_mastery` and reschedules drilling.
6. `end_block` with a short honest summary: what held, what did not.

No new material in this session, even if the queue empties early — offer extra retrieval on
shaky concepts instead.
