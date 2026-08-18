---
description: Announce, schedule, or run a колоквиум (oral theory exam)
argument-hint: [subject] [announce | schedule | run]
---

Колоквиум: **$ARGUMENTS**

Use the `assessment` skill.

**Announce / schedule:** `kolokvium_check` → if triggered, `draw_ticket` to draft the ticket
set, `announce_assessment`, `schedule_assessment` (places the exam plus dedicated preparation
sessions), `publish_pools`, and tell the user where the pools are. If it is not triggered,
say what is still missing.

**Run:** `start_block(kind="kolokvium")`, then `draw_ticket` for the real ticket.

1. Three formulation questions, one at a time. Let each answer finish.
2. `formulation_gate(subject, verdicts)` — **more than one failure stops the колоквиум.**
   Keep formulation credit only, no proof credit, schedule remediation. Do not soften it.
3. One or two proof questions if the gate passed.
4. Optionally one problem.
5. Доп вопросы throughout — probe anything that sounded recited, including correct answers.
   Do not teach during the колоквиум; note the gap and move on.
6. Grade twice independently (`grading` skill), write the record to `results/`, then
   `record_assessment_result` and act on the remediation report.
