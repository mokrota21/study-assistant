# Learning Harness

A universal harness that takes you from "I want to learn X" to genuine mastery —
understanding the theory *and* being able to apply it. Claude Code is the interface; the
filesystem is the state store; an MCP server owns the parts that need computation.

**Start here: [MANUAL.md](MANUAL.md)** — how to run it, and every setting you can change.

Also: [docs/SETUP.md](docs/SETUP.md) for install details and troubleshooting,
[CLAUDE.md](CLAUDE.md) for the protocol Claude follows, and
[learning-harness-prd.md](learning-harness-prd.md) for the design and its evidence base.

## Run it

```powershell
uv sync
claude
```

Then `/intake <subject> [textbook]`. There is no server to start — the MCP server is a
stdio child process Claude Code spawns with the session.

## Why it is built this way

Explanation alone does not produce skill. Mastery comes from isolated deliberate practice,
retrieval practice, spaced repetition, and mastery gating. Two AI-tutor RCTs differ only in
guardrails: the guardrailed tutor produced **2× learning gain**; unguarded model access
produced **+48% on practice and −17% on the independent exam**. Students used the AI as a
crutch and could not tell their learning was degrading.

So the guardrails are structural, not advisory:

- **Solo mode** is on by default, enforced by a hook that re-injects the rule on every
  message rather than trusting the model to remember it.
- **One hint, never the answer**, logged against the concept; a high hint rate blocks mastery.
- **Rubrics are written when the exercise is created**, never while looking at the answer.
- **The mastery gate is a dual threshold** — time-on-task × *varied* reps × distributed
  across days. Twenty identical reps in one sitting count as one.
- **Mastery is provisional.** A failed re-check weeks later revokes it.
- **Performance and learning are measured separately** — in-session correctness vs. delayed
  re-check pass rate. The gap between them is the system's primary health metric.

## Layout

```
harness/            MCP server: scheduler, FSRS, block clock, mastery, pools
.claude/
  hooks/            block clock injection + block-end enforcement
  skills/           intake, study-block, lesson-prep, exercise-design,
                    grading, assessment, solo-practice
  commands/         /intake /study /review /wrapup /status /schedule
                    /kolokvium /exam /stuck /expand /health /commitments
subjects/<name>/    plan.md, materials/, lessons/, notes/, covered.md,
                    exam-pool/, results/
state/              harness.db, block.json, calendar.json
config.json         everything tunable (PRD §7), with per-domain overrides
tests/              uv run python -m tests.run_all
```

## Status

**M1 complete** (theory loop: intake → curriculum → scheduled blocks → retrieval reviews →
колоквиум → exam) plus most of **M2** (isolated drills, solo mode, stuck hatch, hint
analytics, interleaved practical exams, trickle-down FSRS credit). **M3** (real-life
projects) is not started.
