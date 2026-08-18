---
description: Start a study block — review segment first, then new material
argument-hint: [subject] [duration in minutes]
---

Start a study block: **$ARGUMENTS** (subject and duration optional — infer from the
schedule and config if not given).

Use the `study-block` skill. Briefly:

1. `dashboard` to see where things stand, and `list_blocks` for a scheduled block to attach to.
2. `start_block(subject, duration_minutes, topic, block_id)`.
3. `review_queue` + `delayed_rechecks` — live, right now. Overdue first and mandatory.
4. Fresh retrieval exercise per due concept → grade → `grade_review` with a `variant` tag.
5. `set_segment("new_material")`, `check_gate` before introducing anything, explanation-first,
   1–2 worked examples, then solo practice.
6. At block end run the full wrap-up and `end_block`.

Tell the user in one line what the block holds before you start the first exercise.
