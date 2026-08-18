---
description: Generate or run an interleaved practical exam
argument-hint: [subject] [generate | run]
---

Practical exam: **$ARGUMENTS**

Use the `assessment` skill.

**Generate:** `exam_check(subject)`; if triggered, build an exam from the problems pool
covering all or most topics. **Interleaved** — problems unlabeled, mixed across sub-skills,
not grouped by method, because method selection is the skill being tested. Write it to
`subjects/<subject>/results/exam-YYYY-MM-DD.md` with the rubrics kept separate from the
questions the user sees.

**Run:** `start_block(kind="exam")`, solo mode on, **no hints** — the stuck hatch is a
practice instrument, not an exam one. Grade twice independently afterwards, record with
`record_assessment_result`, then `remediation_check` and schedule what it returns.
