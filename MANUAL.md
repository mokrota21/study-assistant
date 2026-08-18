# Manual

Two parts: **[how to start](#how-to-start)** (read once) and **[what you can change](#what-you-can-change)**
(come back whenever something annoys you).

---

## How to start

### The one-time bit

You need [Claude Code](https://claude.com/claude-code) and
[uv](https://docs.astral.sh/uv/getting-started/installation/) installed. Then:

```powershell
cd study-assistant
uv sync                              # installs everything into a local .venv
uv run python -m tests.doctor        # checks this machine is set up right
```

That's it. There's no server to start, nothing to leave running, nothing in Task Scheduler.
Claude Code launches the harness itself and shuts it down when you close the chat.

If `doctor` reports a problem, it tells you the fix; `--fix` repairs the safe ones itself.

### Every time

```powershell
claude
```

Then talk to it. Slash commands are shortcuts, not requirements — plain English works too
("let's study", "quiz me on last week").

### Your first subject

```
/intake Матан I, Zorich vol.1
```

**Naming a book → scoped mode.** You're here because you *don't* know this material yet;
the book is the authority and the assistant's job is to teach you what's in it — not less,
not more. It won't ask you to trim chapters you haven't seen. Tell it your deadline and how
many hours a week you have, and it adjusts the *schedule* instead.

**No book → exploratory mode.** You say what you want; it researches what that actually
requires and proposes the shape — including prerequisites you didn't ask about, since you
can't be expected to know what you're missing. It walks you through the plan and tells you
what each cut would cost before you decide. Push back there; that's the moment scope is
cheapest to control.

Then tell it when you're busy and let it plan:

```
/commitments lectures Mon and Wed 10:00-14:00, gym Tue Thu 19:00-20:30
/schedule
```

### Then, day to day

| You want to | Type |
|---|---|
| Study now | `/study` |
| Just do reviews, no new material | `/review` |
| See where everything stands | `/status` |
| Get a hint (one per problem) | `/stuck` |
| Close the session properly | `/wrapup` |
| Add a topic you'd cut earlier | `/expand <topic>` |
| Be examined | `/kolokvium` or `/exam` |
| Check the system isn't fooling you | `/health` |

A study block always runs **reviews first, then new material.** That's deliberate and it
won't skip them for you.

### Two things that will happen and are not bugs

- **Reviews eat into new material sometimes.** That means you're moving too fast. It's the
  design working.
- **It won't give you answers during practice.** One hint, and it's logged. Ask enough
  times on one topic and it will refuse to mark that topic mastered.

### If something breaks

`/status` first. Then [docs/SETUP.md](docs/SETUP.md#troubleshooting) has the fix-it list
(server won't connect, no clock line, no notifications, stuck block).

---

## What you can change

### "I don't like X" → change this

| What's bugging you | Set this | To |
|---|---|---|
| 50-minute blocks are too long / short | `focus_minutes` | e.g. `35` or `60` |
| It schedules blocks too early or too late | `day_start_hour`, `day_end_hour` | e.g. `11` and `20` |
| Too many study blocks in one day | `max_blocks_per_day` | e.g. `2` |
| I'd rather do one long session than two short ones | `prefer_spacing` | `false` (evidence says don't) |
| Review segment drags on forever | `review_cap_per_block` | e.g. `8` |
| Reviews finish in two minutes, feels pointless | `review_cap_per_block` | e.g. `20` |
| Things come back for review too often | `fsrs_desired_retention` | `0.85` (fewer reviews, more forgetting) |
| I forget things between reviews | `fsrs_desired_retention` | `0.93` (more reviews) |
| It marks things "mastered" too easily | `mastery_min_reps`, `mastery_min_span_days` | raise both |
| It never marks anything mastered | same two | lower both |
| Mastery keeps getting revoked weeks later | `mastery_min_span_days` | raise it — the gate is too loose |
| The block-end sound startles me | `notification_sound` | `false` |
| No desktop popups at all, please | `notifications_enabled` | `false` |
| I want more warning before a block ends | `notify_before_end_minutes` | e.g. `10` |
| Exams show up too rarely / often | `exam_problem_pool_threshold` | lower / raise |
| Колоквиум is coming too soon | `kolokvium_trigger_weeks` | e.g. `9` |
| Solo mode is too strict for me right now | `solo_mode_default` | `false` (read §6 of the PRD first) |
| I want lessons in Russian | `content_language` | `"ru"` |
| Planning two weeks ahead is useless to me | `scheduling_horizon_days` | e.g. `7` |

### Where to put the change

Three places, each overriding the one above it:

**1. `config.json`** — the normal place. Applies to everything.

```jsonc
{ "focus_minutes": 40, "review_cap_per_block": 8 }
```

**2. `config.json` → `domains`** — applies to every subject tagged with that domain.

```jsonc
{ "domains": { "math": { "mastery_min_minutes": 60, "mastery_min_reps": 8 } } }
```

**3. `subjects/<subject>/config.json`** — wins over both, for that subject only.

```jsonc
{ "domain": "math", "mastery_min_span_days": 7 }
```

There's also `HARNESS_*` environment variables (e.g. `HARNESS_FOCUS_MINUTES=40`), which beat
`config.json` — useful for a one-off experiment without editing files.

Easiest route of all: **just ask Claude.** "Make blocks 40 minutes" — it knows where the
settings live and will edit the right file.

To see what's actually in effect: `/status`, or ask for the `harness_config` tool.

---

## Every parameter

Defaults are what ships in `config.json`. Anything you don't set falls back to these.

### Focus rhythm — when and how long you study

| Parameter | Default | What it does |
|---|---|---|
| `focus_minutes` | `50` | Length of one focused block |
| `break_minutes` | `10` | Break after a block; also how long until the "break over" notification |
| `long_break_after_minutes` | `120` | Study time in a day before a longer break is forced |
| `long_break_minutes` | `30` | Length of that longer break |
| `max_blocks_per_day` | `4` | Hard cap on blocks placed in one day |
| `prefer_spacing` | `true` | Spread blocks across days before stacking two on one day |
| `day_start_hour` | `9` | No block starts before this hour |
| `day_end_hour` | `22` | No block ends after this hour |

### Block composition — what happens inside a session

| Parameter | Default | What it does |
|---|---|---|
| `review_segment_minutes` | `15` | Nominal time reserved for reviews at the start |
| `review_cap_per_block` | `12` | Most review items fetched in one block |
| `review_overflow_eats_new_material` | `true` | Overdue reviews come before new material. *Advisory — read by Claude, not enforced by code* |

### Spaced repetition — when things come back

| Parameter | Default | What it does |
|---|---|---|
| `fsrs_desired_retention` | `0.90` | Target recall probability. Higher = more reviews, less forgetting. Range 0.70–0.99 |
| `fsrs_maximum_interval_days` | `1095` | Longest a concept can go without a review (3 years) |
| `fsrs_enable_fuzzing` | `true` | Jitters due dates so reviews don't clump on one day |
| `trickle_down_enabled` | `true` | Succeeding at an advanced skill pushes its prerequisites' reviews further out |
| `trickle_down_credit` | `0.5` | How much credit flows down, as a fraction of the prerequisite's current interval |
| `trickle_down_depth` | `2` | How many prerequisite levels get credit |

### Mastery gate — what counts as "learned"

All four must hold at once before a concept is marked mastered.

| Parameter | Default | What it does |
|---|---|---|
| `mastery_min_minutes` | `45` | Minimum time spent on the concept |
| `mastery_min_reps` | `6` | Minimum *distinct* correct exercises. Same exercise repeated counts once |
| `mastery_min_distinct_days` | `3` | Those reps must land on this many separate days |
| `mastery_min_span_days` | `5` | Calendar days from first rep to the qualifying one |
| `mastery_max_hint_rate` | `0.34` | Hints per rep above which mastery is blocked |
| `mastery_recheck_days` | `21` | How long after mastery a delayed re-check is owed |

### Assessment — колоквиум and exams

| Parameter | Default | What it does |
|---|---|---|
| `kolokvium_trigger_weeks` | `7.0` | Weeks of material before a колоквиум triggers |
| `kolokvium_trigger_concepts` | `12` | Alternative trigger: this many concepts covered |
| `kolokvium_min_provable` | `4` | Provable items required — a hard requirement, not an alternative |
| `kolokvium_prep_sessions` | `2` | Preparation blocks scheduled before it |
| `ticket_formulations` | `3` | Formulation questions per ticket |
| `ticket_proofs_min` / `_max` | `1` / `2` | Proof questions per ticket (random in range) |
| `ticket_problems` | `1` | Problems per ticket |
| `formulation_gate_max_failures` | `1` | Fail more than this many formulations → колоквиум stops, no proof credit |
| `exam_problem_pool_threshold` | `20` | Problems in the pool before a practical exam triggers |
| `remediation_threshold` | `0.6` | Average score below this schedules a supervised-practice session |
| `grading_self_consistency_passes` | `2` | Independent gradings on high-stakes answers. *Advisory* |
| `grading_agreement_pullout` | `0.82` | If your spot-checks agree with AI grades less often than this, auto-grading is pulled from the mastery gate |

### Practice

| Parameter | Default | What it does |
|---|---|---|
| `solo_mode_default` | `true` | New blocks start in solo mode — no solutions, no corrections |
| `hints_per_exercise` | `1` | Hints the stuck hatch will give per exercise |

### Curriculum and planning

| Parameter | Default | What it does |
|---|---|---|
| `scheduling_horizon_days` | `14` | How far ahead blocks are planned |
| `prep_full_lessons` | `2` | Lessons prepared in full detail. *Advisory* |
| `prep_outline_lessons` | `7` | Lessons kept as rough outlines. *Advisory* |
| `content_language` | `"en"` | Language for lessons, notes, exams. Russian terms (колоквиум, доп вопросы) stay as-is regardless |

### Notifications

| Parameter | Default | What it does |
|---|---|---|
| `notifications_enabled` | `true` | Desktop popups at all |
| `notification_sound` | `true` | Sound with the popup |
| `notify_before_end_minutes` | `5` | Heads-up before a block ends |

### Calendar

| Parameter | Default | What it does |
|---|---|---|
| `calendar_provider` | `"local"` | `"local"` = the JSON store in `state/calendar.json`. `"google"` is stubbed, not implemented |

---

## Not configurable (on purpose)

These are the guardrails. They're the reason the system works at all, and there's no
setting for them — if you want them gone, you'd edit the code and you'd know you did it.

- **Reviews are always fetched live**, at block start. They're never assigned in advance.
- **Grading criteria are written before you answer**, never after.
- **Prerequisites gate strictly.** No advancing past an unmastered prerequisite.
- **The stuck hatch gives a hint, never the answer** — and every use is logged.
- **A hint caps that exercise's rating** at "Hard", no matter how good the final answer.
- **In-session correctness and delayed re-check results are never mixed** into one number.
  That separation is the whole point of `/health`.
- **The formulation gate stops a колоквиум.** You can raise
  `formulation_gate_max_failures`, but the gate itself doesn't turn off.

---

## Where your stuff lives

| Path | What | Safe to edit by hand? |
|---|---|---|
| `subjects/<name>/plan.md` | Concept graph, scope, coverage | Yes — tell Claude after, so it re-syncs |
| `subjects/<name>/notes/` | Daily session notes | Yes |
| `subjects/<name>/covered.md` | Running log; triggers the колоквиум | Append only |
| `subjects/<name>/exam-pool/` | The question pools you prepare from | No — regenerated from the database |
| `subjects/<name>/results/` | Graded exam records | Yes |
| `state/calendar.json` | Your commitments | Yes |
| `state/harness.db` | Reviews, mastery, pools, schedule | No — ask Claude instead |
| `state/block.json` | The live block clock | Delete it if a block is stuck |
| `config.json` | Everything on this page | Yes |

Deleting `state/harness.db` resets all progress: FSRS history, mastery evidence, exam pools.
The concept graph survives in `plan.md`. Back it up first — it's one file.

---

Deeper reading: [docs/SETUP.md](docs/SETUP.md) for install and troubleshooting,
[CLAUDE.md](CLAUDE.md) for the protocol Claude follows,
[learning-harness-prd.md](learning-harness-prd.md) for why any of it is designed this way.
