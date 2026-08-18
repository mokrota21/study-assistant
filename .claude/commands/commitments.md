---
description: View or record blocked (non-study) time
argument-hint: [e.g. "lectures Mon and Wed 10:00-14:00", "gym Tue Thu 19:00-20:30"]
---

Manage blocked time: **$ARGUMENTS**

- With no arguments: `list_commitments` and show them grouped by weekday, plus
  `available_windows` for the next week so the user sees what is actually free.
- With a description: parse it into `add_commitment` calls.
  - Recurring → `weekdays` (mon..sun) + `start_time` + `end_time` as `HH:MM`, optionally
    `from_date` / `until_date` for a term.
  - One-off → `start` + `end` as ISO timestamps.
  - Confirm what you understood before adding anything ambiguous.
- To remove: `remove_commitment(id)`.

Commitments are stored in `state/calendar.json` — plain JSON, editable by hand. The
scheduler treats them and already-placed study blocks identically as busy time, and
re-indexes free windows after every placement.
