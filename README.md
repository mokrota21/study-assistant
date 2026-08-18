# Learning Harness

A tutor that refuses to help you cheat yourself.

You point it at a subject — a textbook, or just a thing you want to learn. It builds a
curriculum, puts study blocks in your calendar, teaches you one concept at a time, and then
makes you retrieve them from memory on a spaced schedule. It will not give you answers while
you practise, it will not let you move past a prerequisite you have not proven, and it
measures whether you actually still know things weeks later rather than whether you felt
good in the lesson.

It runs inside [Claude Code](https://claude.com/claude-code). Your plans, lessons and notes
are ordinary markdown files in this folder; a small local server owns the scheduling and
spaced-repetition arithmetic. Nothing leaves your machine.

---

## What using it looks like

**Day one.** You name a subject and, optionally, a book:

```
/intake Real Analysis, Zorich vol.1
```

It reads the table of contents, drafts a concept graph with real prerequisite edges (not
chapter order), and shows you what it will cover and roughly how long that takes. Then you
give it your week and let it plan:

```
/commitments lectures Mon Wed 10:00-14:00, gym Tue Thu 19:00-20:30
/schedule
```

You get 50-minute blocks spread across days rather than stacked — two sessions on two days
beat one double session, and that is enforced by the scheduler, not left to intention.

**A study block.** `/study` starts the clock. Reviews always come first:

```
[Block 0/50min, segment=review, SOLO, 50m left]

3 reviews due, then we start on the Cauchy criterion.

Review 1 of 3 — Sequence limits.
State the ε-N definition of lim aₙ = L, and explain why the quantifier order matters.
```

Every review is a **freshly written question**, never a flashcard and never one you have
seen before. You answer; it grades against a checklist written when the question was
created — not one invented while reading your answer — tells you which required element you
missed, and the spaced-repetition algorithm moves the next review date accordingly.

Then new material: a short explanation, one or two worked examples, and it hands over.

```
Your turn. Prove that every convergent sequence is Cauchy.
```

Ask for the answer and it says no. If you are genuinely stuck, `/stuck` buys you **one
hint** — never the solution — and logs it. That hint caps the exercise's score, and if
hints keep clustering on one concept, that concept cannot count as mastered until you have
done it unassisted.

At 50 minutes a desktop notification fires. The session will not end until it has written
your notes, logged what you covered, banked exam questions with their marking criteria, and
prepared the next lesson.

**Over weeks.** Concepts come back at widening intervals. A concept only counts as mastered
after enough *varied* attempts spread over enough separate days — twenty repetitions of the
same exercise in one evening count as one. Weeks later it re-tests things you have already
"mastered"; if you have lost it, mastery is revoked and it goes back into the rotation.
Once enough material has accumulated it announces an oral exam (колоквиум) drawn from a
question pool you can see and prepare from, and schedules revision sessions before it.

---

## Quick start

Needs [Claude Code](https://claude.com/claude-code) and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/mokrota21/study-assistant.git
cd study-assistant
uv sync
uv run python -m tests.doctor    # checks your machine; --fix repairs what it can
claude
```

Then `/intake <subject>`. There is no server to start, no Docker, nothing to autostart —
the local server is a child process that lives and dies with your chat session.

Everyday commands: `/study` · `/review` · `/status` · `/stuck` · `/wrapup` · `/health`

---

## Why it is built this way

Explanation does not produce skill. Practice does — but only certain kinds. This system is
built on isolated deliberate practice, retrieval practice, spaced repetition and mastery
gating, and it is deliberately awkward in the places where being easy would defeat the point.

The reason for that awkwardness is one result. Two AI-tutor trials differ only in guardrails:
the guardrailed tutor produced **2× the learning gain**, while unguarded model access
produced **+48% on practice performance and −17% on the independent exam**. The students with
open access were doing better at the time and worse afterwards — and could not tell.

So the guardrails are structural, not advisory:

| Guardrail | How it is enforced |
|---|---|
| **Solo mode** — no solutions during practice | A hook re-injects the rule on every single message, rather than trusting the model to remember it as the conversation grows |
| **One hint, never the answer** | Logged per concept; caps the score; a high hint rate blocks mastery outright |
| **Marking criteria written before you answer** | An exercise is created together with its reference solution and rubric. Grading against a rubric invented while reading the answer is how a model talks itself into being generous |
| **Mastery needs varied, spaced reps** | Time-on-task × distinct exercise variants × spread across days. Cramming cannot satisfy it |
| **Mastery is provisional** | A failed re-check weeks later revokes it and reschedules drilling |
| **Performance ≠ learning** | In-session correctness and delayed re-check pass rate are tracked separately and never averaged. The gap between them is the system's own health metric — `/health` reports it and tells you when the gate is too loose |

You can change almost anything about the pace, the thresholds and the schedule. You cannot
switch off the guardrails from config; that is the point of them.

---

## What is in here

```
harness/          local MCP server: scheduler, spaced repetition, block clock,
                  mastery gates, exam pools  (54 tools)
.claude/
  hooks/          inject the block clock into context; enforce the block-end wrap-up
  skills/         the pedagogy: intake, study blocks, lesson prep, exercise design,
                  grading, exams, solo practice
  commands/       the slash commands listed above
subjects/<name>/  plan.md, materials/, lessons/, notes/, covered.md, exam-pool/, results/
state/            SQLite + the live block clock + your commitments
config.json       every tunable, with per-domain overrides
tests/            doctor.py (environment check) + 5 suites, 110 checks
```

## Documentation

| | |
|---|---|
| **[MANUAL.md](MANUAL.md)** | How to start, and every setting you can change — start here |
| [docs/SETUP.md](docs/SETUP.md) | Install, resource cost, troubleshooting |
| [CLAUDE.md](CLAUDE.md) | The operating protocol Claude follows in this folder |
| [learning-harness-prd.md](learning-harness-prd.md) | Full design and the evidence behind it |

## Status

Personal project, working and in use. The theory loop is complete — intake, curriculum,
scheduling, spaced reviews, mastery gates, oral and practical exams — along with most of the
practice layer: isolated drills, solo mode, the hint hatch, interleaved exams. Hands-on and
real-world project work is designed but not built.

Built and tested on Windows 11. The macOS and Linux paths exist but are unexercised;
`tests/doctor.py` will tell you what needs adjusting.
