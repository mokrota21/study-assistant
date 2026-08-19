---
description: Close the current block — notes, covered.md, pool deposits, next-lesson prep
---

Run the block wrap-up now, in full:

1. Write `subjects/<subject>/notes/YYYY-MM-DD.md` — covered, went well, shaky, hints used,
   what to re-drill. Use `notes_skeleton` for the path and skeleton.
2. `log_covered(subject, concepts, summary, block_id)`.
3. Deposit held-back questions into all three pools with `deposit_pool_item` — required
   elements for theory, rubric plus reference solution for problems, `source` when they
   come from the textbook. Then `publish_pools`.
4. `record_practice` for any unlogged time-on-task; grade any ungraded exercises.
5. **Homework**: every prepared problem the block did not reach is assigned, not discarded.
   List them under `## Homework` in the notes — lesson ref, problem number, variant tag —
   and tell the user which ones. Do not rewrite them; they already have rubrics.
6. Prepare lesson N+1 in full and extend the outline window (`lesson-prep` skill).
7. `kolokvium_check`, `exam_check`, `remediation_check` — act on whatever fires.
8. `end_block(notes_path, summary)`.

Then three or four lines to the user: covered, shaky, next.
