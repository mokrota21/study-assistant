---
description: Plan or re-plan study blocks over the two-week horizon
argument-hint: [subject] [how many blocks] [notes about availability]
---

Plan study blocks: **$ARGUMENTS**

1. `list_commitments` — if the user mentioned new life commitments above, record them with
   `add_commitment` first (recurring: weekdays + start_time/end_time; one-off: start + end).
2. `available_windows` to show what is genuinely free.
3. `review_forecast` — the schedule reserves review *capacity*, never specific items.
4. `propose_schedule(subject, count, topics, commit=False)`. Show it, let the user trim,
   then re-run with `commit=True`.

Constraints the tools already enforce, worth restating to the user: 50-minute focus blocks
with breaks, at most a couple per day, spread across days rather than stacked — two sessions
on two days beat one double session. The plan past the first few days is deliberately vague
about topics, because pace is unpredictable.

If windows run out, say what is blocking (commitments, day-hour bounds, horizon) rather than
quietly placing fewer blocks.
