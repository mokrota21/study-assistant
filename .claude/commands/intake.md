---
description: Start a new subject — scoping, materials, concept graph, first schedule
argument-hint: <subject name> [textbook or source, optional]
---

Run curriculum intake for: **$ARGUMENTS**

Use the `curriculum-intake` skill. Work through it in order:

1. Establish the mode — **scoped** if a textbook/source was named above, **exploratory** if not.
   If it is ambiguous, ask once, then proceed. Both modes assume the learner cannot yet audit
   their own gaps: in scoped mode the book settles scope, in exploratory mode your research
   proposes it. The learner's self-assessment settles neither.
2. `create_subject` to scaffold the folder tree.
3. Collect materials into `materials/` with provenance.
4. Draft the concept graph in `plan.md` with prerequisite edges, `provable` flags and the
   excluded-but-adjacent list.
5. Present it before registering — **for orientation and pacing in scoped mode** (take their
   constraints, adjust the schedule, not the material), **for guided negotiation in exploratory
   mode** (surface prerequisites they never asked about, say what each cut would cost, then
   rework on their decisions).
6. Once settled: `register_concepts`, then `seed_cards`.
7. Ask for life commitments, record them with `add_commitment`, then `propose_schedule`
   (commit=False first, let the user trim).
8. Prepare lessons 1–2 in full and 3–7 as outlines (`lesson-prep` skill).

End with a short summary: scope, what is excluded, how many blocks over what period, and
when the first block is.
