---
name: study-block
description: Run a study block end to end — review segment, new material, practice, and the wrap-up that writes notes and triggers the next lesson. Use whenever the user starts studying, says they are ready, asks what to work on now, or a scheduled block is starting.
---

# Study block

Every block is **review segment first, then new material.** No exceptions, including when
the user asks to skip straight to the new topic — overdue retrieval is the part that
actually builds durable knowledge, and it is enforced structurally so it does not depend
on anyone's willpower today.

## Open

1. `start_block(subject, duration_minutes, topic, block_id)`. This arms three things: the
   hook that injects the clock into your context, the OS notification timer that reaches
   the user even when they are working alone, and the Stop hook that will refuse to end
   the turn without a wrap-up.
2. `review_queue(subject)` — live, right now. Never a list assembled earlier.
3. `delayed_rechecks(subject)` — fold any owed re-checks into this segment.
4. Read the `## Homework` section of the previous block's notes. If it lists anything, ask
   for it now, before the review queue — see **Homework** below.
5. Tell the user in one line what the block holds: homework, N reviews, then the new topic.

## Review segment (~15 min of capacity)

For each queue item, in order — **overdue first, they are mandatory**:

1. Generate a **fresh** free-recall or short-answer exercise on that concept. Not a
   flashcard. Not the exercise you used last time. Vary the surface: state it, apply it,
   find the counterexample, spot the error in a wrong argument.
2. Write the grading criteria before you show the exercise (see the `grading` skill).
3. Let the user answer. Grade against the criteria.
4. `grade_review(subject, concept, score=…, variant="<what varied>", kind="in_session"|"delayed_recheck", hints_used=…, minutes_on_task=…)`.

`variant` matters: the mastery gate counts distinct variants, so an untagged or repeated
variant does not advance mastery. Make each rep genuinely different.

If the queue overflows the segment, let it. Say so plainly: "reviews ran long, so new
material is shorter today — that is the system telling us the pace was too fast." Then
`set_segment("new_material")` with whatever time is left.

## Homework

A block that runs out of time does not throw away the problems it did not reach. They were
written with reference solutions and rubrics at creation time — that work is already done,
and the rubric is still valid whether it is graded today or in three days.

**At wrap-up**, list every untouched prepared problem under `## Homework` in the notes:
lesson ref, problem number, variant tag. Tell the user which ones and why they matter.

**At the next block open**, ask for it before the review queue. Then:

- Grade each one against the rubric that already exists in the lesson file. Do not
  regenerate the problem and do not soften the rubric because time has passed.
- `grade_review(..., variant="<the tag from the lesson file>", kind="in_session",
  minutes_on_task=…)`. These are real reps: distinct variant tags on a different calendar
  day are exactly what the mastery gate counts, and homework is the cheapest way to earn
  the `distinct_days` and `span_days` conditions that no single block can satisfy.
- Not done? Record that plainly and move on — no lecture. If homework goes undone twice in
  a row, the load is wrong: say so and cut the assigned set, rather than repeating it.

Homework is solo by construction. The no-solutions rule applies to it in full, including
when the user asks between blocks.

## New material

1. `check_gate(subject, concept)` before introducing anything. Blocked means you drill the
   prerequisite instead. Do not explain the concept "just briefly" anyway.
2. **Explanation-first, one step at a time.** Short. Cognitive load is the constraint —
   a wall of text is not thoroughness, it is a worse lesson.
3. **One or two worked examples**, fully worked, thinking made visible.
4. **Then hand it over**: retrieval exercises on the new concept, solo mode on. Load the
   `solo-practice` and `exercise-design` skills.
5. `record_practice(subject, concept, minutes)` as you go.

## Interruptions

`pause_block` when the user steps away, `resume_block` when they return — paused time
does not count. `extend_block` sparingly; the 50/10 rhythm exists because attention
degrades, and "just 20 more minutes" is how it erodes.

## Wrap-up

Triggered by the Stop hook at block end, or manually with `/wrapup`. Do all of it:

1. **Notes** → `subjects/<subject>/notes/YYYY-MM-DD.md` (`notes_skeleton` gives the path
   and skeleton). What was covered, what went well, what was shaky, hints used, what to
   re-drill. Be specific and honest — this file is read later by you and by the user.
2. **`log_covered(subject, concepts, summary, block_id)`** — appends to `covered.md`, the
   колоквиум trigger source.
3. **Exam-pool deposits** — every concept covered deposits held-back questions into
   `formulations`, `proofs`, `problems` via `deposit_pool_item`, with their required
   elements or rubric written now. In scoped mode, prefer real problems from the book and
   set `source`.
4. **`record_practice`** for any time-on-task not yet logged.
5. **Homework** — every prepared problem the block did not reach, listed under `## Homework`
   in the notes with its variant tag, and named to the user.
6. **Prepare lesson N+1 in full** and extend the outline window (`lesson-prep` skill).
7. **Trigger checks**: `kolokvium_check`, `exam_check`, `remediation_check`. Act on any
   that fire — announce, schedule, or tell the user what is coming.
8. **`end_block(notes_path, summary)`** last.
9. Then three or four lines to the user: what was covered, what is shaky, what is next —
   and the homework, if any was assigned.

## Reading the injected clock

A line like `[Block 42/50min, segment=new_material, subject=matan, SOLO, 8m left]` appears
in your context automatically. Act on it:

- `Nm left` under 5: do not start a new concept or a long problem. Converge.
- `OVER by …`: finish the sentence you are on, then wrap up.
- `SOLO`: the solo-practice rules are in force right now.
