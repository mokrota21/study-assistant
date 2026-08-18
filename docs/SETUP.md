# Setup and operations

## TL;DR

```
cd c:\Users\mokrota\Documents\GitHub\study-assistant
uv sync
claude
```

Then `/intake <subject> [textbook]`.

**There is no server to start.** No Docker, no daemon, no autostart to configure — see
[Do I need to run a server?](#do-i-need-to-run-a-server) below.

---

## What is installed

| Piece | Where | What it does |
|---|---|---|
| MCP server | `harness/`, launched via `.mcp.json` | Scheduler, FSRS queue, block clock, mastery gates, exam pools — 54 tools |
| Hooks | `.claude/hooks/` | Inject the block clock into context; refuse to stop at block end |
| Operating manual | `CLAUDE.md` | The protocol Claude follows in this folder |
| Skills | `.claude/skills/` | Deep pedagogy: intake, blocks, lessons, exercises, grading, assessment, solo mode |
| Commands | `.claude/commands/` | `/intake` `/study` `/review` `/wrapup` `/status` `/schedule` `/kolokvium` `/exam` `/stuck` `/expand` `/health` `/commitments` |
| Config | `config.json` | Every tunable from PRD §7, plus per-domain overrides |
| State | `state/` | `harness.db` (SQLite), `block.json` (live clock), `calendar.json` (commitments) |

---

## Do I need to run a server?

**No.** The MCP server uses **stdio** transport, which means Claude Code spawns it as a
child process when the session starts and kills it when the session ends. `.mcp.json`
already declares it:

```json
{ "mcpServers": { "learning-harness": {
    "type": "stdio", "command": "uv", "args": ["run", "--quiet", "learning-harness"] } } }
```

So:

- **Starting it:** automatic, on `claude` in this folder. Nothing to type.
- **Autostart:** already the case. There is nothing to add to Task Scheduler or systemd.
- **Docker:** not wanted here, and it would actively break two features. The server writes
  to your real filesystem (`state/`, `subjects/`) and fires **OS desktop notifications**
  during solo practice; both need host access, and containerizing them would mean bind
  mounts plus a notification bridge to buy nothing. Docker earns its place for
  long-running network services. This is a child process that lives and dies with your
  chat session.

### Measured cost on this machine

| | |
|---|---|
| Server memory (resident) | **~80 MB** while a session is open, plus a ~12 MB `uv` shim |
| Startup to first tool call | **0.87 s**, once per Claude Code session |
| Per tool call | **~4 ms** |
| Hook latency | **~75 ms** per user message (system Python 3.8, stdlib only, no venv) |
| Idle CPU | ~0. The background block timer wakes every 5 s to compare two timestamps |
| Disk | SQLite grows by kilobytes per study block |

Nothing runs when Claude Code is closed. If you want the block-end desktop notification
to reach you while you practise offline, leave the Claude Code session open — that is what
keeps the timer thread alive.

---

## First run

```powershell
cd c:\Users\mokrota\Documents\GitHub\study-assistant
uv sync            # creates .venv with Python 3.12, installs mcp + fsrs + pydantic
claude
```

Inside Claude Code:

```
/intake Матан I, Zorich vol.1        # scoped mode — the book is the contract
/intake cooking                       # exploratory mode — agent researches the scope
```

Then, once a plan exists:

```
/commitments lectures Mon and Wed 10:00-14:00, gym Tue Thu 19:00-20:30
/schedule                             # propose blocks over the 2-week horizon
/study                                # run one
```

Everyday commands: `/status`, `/study`, `/review`, `/wrapup`, `/stuck`, `/health`.

---

## Verifying the install

```powershell
uv run python -m tests.run_all
```

Four suites: the core loop and its guardrails (63 checks), the MCP tool surface (54 tools),
the hooks against the *system* interpreter (27 checks), and a real stdio launch of the
server exactly as Claude Code starts it. All run against throwaway directories and never
touch `state/` or `subjects/`.

Inside Claude Code, `/mcp` should list `learning-harness` as connected.

---

## Configuration

Precedence, lowest first: defaults in `harness/config.py` → `config.json` → `HARNESS_*`
env vars → `config.json`'s `domains.<domain>` → `subjects/<subject>/config.json`.

```jsonc
// config.json
{ "focus_minutes": 50, "mastery_min_reps": 6, "fsrs_desired_retention": 0.9,
  "domains": { "math": { "mastery_min_minutes": 60, "mastery_min_reps": 8 } } }
```

```jsonc
// subjects/matan-i/config.json — wins over everything for this subject
{ "domain": "math", "mastery_min_span_days": 7 }
```

Ask Claude for the effective values with the `harness_config` tool, or just `/status`.

### Worth tuning early

| Field | Why |
|---|---|
| `day_start_hour` / `day_end_hour` | Defaults are 9–22. The scheduler will not place a block outside these. |
| `review_cap_per_block` | 12 is a guess. Raise it if reviews finish too fast, lower it if they eat every block. |
| `mastery_min_*` | The gate. `/health` tells you when it is too loose — see below. |
| `notification_sound` | Set `false` if the block-end chime is annoying. |

---

## The one number that matters

`/health` reports the gap between **in-session correctness** and **delayed re-check pass
rate**. In-session correctness is cheap and systematically misleading; the delayed re-check
is the real signal. A large gap (>0.25) means the mastery gate is letting through concepts
that do not survive three weeks, and the fix is to tighten `mastery_min_reps`,
`mastery_min_span_days`, or `fsrs_desired_retention`.

Check it every few weeks. It is the primary health metric of the whole harness, and it only
becomes meaningful after enough delayed re-checks have accumulated.

---

## Troubleshooting

**`/mcp` shows the server as failed.** Run `uv run learning-harness` in a terminal — it
should sit there silently waiting for stdio input (Ctrl+C to quit). If it errors, `uv sync`
again. If `uv` is not on PATH for the Claude Code process, put its absolute path in
`.mcp.json` (`C:\Users\mokrota\.local\bin\uv.exe`).

**No block-clock line appears in Claude's context.** The hooks call `python`. Check
`python --version` resolves (3.8+ is fine — the hooks are stdlib-only by design). If your
`python` is not on PATH, edit the four commands in `.claude/settings.json` to an absolute
interpreter path. Verify with `uv run python -m tests.test_hooks`.

**No desktop notification at block end.** Test the backend directly:
```powershell
uv run python -c "from harness.notify import notify; print(notify('test','hello'))"
```
It should print `{'sent': True, ...}` and show a toast. Windows Focus Assist / Do Not
Disturb suppresses these silently; check Settings → System → Notifications.

**A block is stuck active after a crash.** `clear_block_state` (ask Claude, or delete
`state/block.json`).

**Wrong timezone in schedules.** Everything uses the machine's local zone with explicit
offsets. Change the OS timezone and restart the Claude Code session.

**Reset everything.** Delete `state/harness.db` — the concept graph can be re-registered
from `plan.md`, but FSRS history, mastery evidence and exam pools are lost. Back it up
first; it is a single SQLite file.

---

## Adding Google Calendar later

The seam already exists. `harness/calendar.py` defines `CalendarProvider` with one method
that matters, `busy(start, end) -> list[Interval]`, which is deliberately the shape of
Google's `freebusy.query` response. Implement `GoogleCalendarProvider.busy`, set
`"calendar_provider": "google"` in `config.json`, and the scheduler needs no changes.

Commitment *writing* stays local on purpose — the harness should not create events in your
real calendar without being asked.

---

## What is not built yet

M3 (real-life / hands-on projects) is untouched: no project decomposer, no physical-skill
verification. The PRD's open question #4 needs its own design round.

Also deferred, and noted in the PRD as accepted: Claude only becomes time-aware when a hook
fires. During a long idle stretch the OS notification reaches you, but not the model. This
has not caused a problem in testing; revisit if the agent starts overrunning blocks
mid-generation.
