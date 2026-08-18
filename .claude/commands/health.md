---
description: Is the harness actually working? Performance vs. learning, grading agreement
argument-hint: [subject]
---

Report harness health: **$ARGUMENTS**

1. `harness_health(subject)` — the primary metric is the **gap between in-session
   correctness (performance) and delayed re-check pass rate (learning)**. In-session
   correctness is cheap and systematically misleading on its own.
   - Gap > 0.25: the gate is passing concepts that do not survive. Propose concrete
     tightening — more varied reps, longer `mastery_min_span_days`, higher
     `fsrs_desired_retention` — and offer to apply it to `config.json`.
   - Not enough delayed re-checks yet: say so rather than reporting a number that means
     nothing, and schedule some (`delayed_rechecks`).
2. **Grading agreement** — if below threshold, open-ended auto-grading comes out of the
   mastery gate and is restricted to reference-matchable items. If there are too few
   spot-checks to judge, ask the user to check a few grades against your scores and record
   them with `log_grading_spotcheck`.
3. **Hint load** — which concepts the stuck-hatch uses cluster on. That clustering is
   usually the real finding.
4. `remediation_check` — anything below threshold, and whether sessions are scheduled.

Be blunt. This command exists to catch the system fooling itself, and a reassuring report
that hides a bad gap is the failure mode it is meant to prevent.
