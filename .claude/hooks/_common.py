"""Shared helpers for the Learning Harness hooks.

Hard constraints, and the reasons for them:

* **Standard library only, Python 3.8 compatible.** These run on the system
  interpreter on every user message. Importing the harness package (or paying
  for `uv run`) would add hundreds of milliseconds to every turn.
* **Never raise.** A hook that crashes degrades the session for a study aid.
  Every entry point wraps itself and exits 0 on any error.
* **Read-only on state**, apart from two tiny bookkeeping flags.
"""

from __future__ import print_function

import json
import os
import sys
from datetime import datetime, timedelta

STATE_REL = os.path.join("state", "block.json")
CACHE_REL = os.path.join("state", "hook-cache.json")
DB_REL = os.path.join("state", "harness.db")


def project_dir():
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return env
    # .claude/hooks/_common.py -> project root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_json(path, default=None):
    try:
        # utf-8-sig: a BOM (anything hand-edited on Windows) must not silently
        # look like "no block running".
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except Exception:
        return default if default is not None else {}


def write_json(path, data):
    try:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


def read_block_state():
    return read_json(os.path.join(project_dir(), STATE_REL), {"active": False})


def write_block_state(state):
    write_json(os.path.join(project_dir(), STATE_REL), state)


def read_hook_input():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def parse_iso(text):
    """ISO-8601 with offset. The harness never writes 'Z', but tolerate it anyway."""
    if not text:
        return None
    try:
        if text.endswith("Z") or text.endswith("z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None


def local_now():
    return datetime.now().astimezone()


def humanize(minutes):
    minutes = int(round(minutes))
    if minutes < 60:
        return "%dm" % minutes
    hours, rest = divmod(minutes, 60)
    return "%dh%02dm" % (hours, rest) if rest else "%dh" % hours


def elapsed_minutes(state, reference=None):
    reference = reference or local_now()
    start = parse_iso(state.get("start"))
    if start is None:
        return 0.0
    paused = float(state.get("paused_total_s", 0) or 0)
    if state.get("paused") and state.get("paused_at"):
        paused_at = parse_iso(state.get("paused_at"))
        if paused_at:
            paused += (reference - paused_at).total_seconds()
    return max(0.0, ((reference - start).total_seconds() - paused) / 60.0)


def block_line(state, reference=None):
    """The one-liner injected into context. Mirrors harness.blockclock.compact_line."""
    if not state.get("active"):
        return None
    reference = reference or local_now()
    duration = float(state.get("duration_minutes") or 0)
    elapsed = elapsed_minutes(state, reference)
    remaining = duration - elapsed
    bits = ["Block %d/%dmin" % (int(elapsed), int(duration))]
    bits.append("segment=%s" % state.get("segment", "review"))
    if state.get("subject"):
        bits.append("subject=%s" % state["subject"])
    if state.get("paused"):
        bits.append("PAUSED")
    if state.get("solo_mode"):
        bits.append("SOLO")
    if remaining <= 0:
        bits.append("OVER by %s - WRAP UP NOW" % humanize(-remaining))
    else:
        bits.append("%s left" % humanize(remaining))
    return "[" + ", ".join(bits) + "]"


SOLO_RULE = (
    "SOLO MODE IS ACTIVE. The user is practising without AI help - this is the point of the "
    "system, and the evidence is unambiguous that unguarded help inflates practice scores while "
    "lowering independent exam results. Do not give solutions, partial solutions, corrections, "
    "confirmations, or leading questions. If the user is genuinely stuck, call the stuck_hatch "
    "tool first, then give exactly ONE hint grounded in the reference solution - never the answer."
)

WRAPUP_DIRECTIVE = (
    "The study block is over. Before you finish this turn, run the wrap-up (§3.4):\n"
    "1. Write today's notes to subjects/<subject>/notes/YYYY-MM-DD.md - what was covered, what was "
    "shaky, hints used.\n"
    "2. Call log_covered to append the covered concepts to covered.md.\n"
    "3. Deposit held-back questions into the exam pools with deposit_pool_item - required elements "
    "for theory, rubric plus reference solution for problems. Written now, not at grading time.\n"
    "4. Call record_practice for time-on-task per concept, and grade any ungraded exercises.\n"
    "5. Assign the problems the block did not reach as homework - list them in the notes under "
    "## Homework with lesson ref, problem number and variant tag, and tell the user. They are "
    "already written and already have rubrics; solo work between blocks is what earns the "
    "distinct days and varied reps the mastery gate counts.\n"
    "6. Prepare lesson N+1 in full and extend the outline window (§3.3).\n"
    "7. Check kolokvium_check, exam_check and remediation_check.\n"
    "8. Call end_block last. Then summarise the session for the user in a few lines."
)


def guard(main):
    """Run a hook entry point, swallowing every error. A broken hook must not break the session."""
    try:
        code = main()
        sys.exit(code if isinstance(code, int) else 0)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)


def emit_context(event_name, text):
    """Feed text back into Claude's context in the shape the harness expects."""
    if not text:
        return
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


def throttled(key, min_seconds, reference=None):
    """True when `key` last fired less than `min_seconds` ago. Records the firing otherwise."""
    reference = reference or local_now()
    path = os.path.join(project_dir(), CACHE_REL)
    cache = read_json(path, {})
    last = parse_iso(cache.get(key))
    if last is not None and (reference - last).total_seconds() < min_seconds:
        return True
    cache[key] = reference.isoformat(timespec="seconds")
    write_json(path, cache)
    return False


def query_db(sql, params=()):
    """Small read-only query. Returns [] if the database is absent or busy."""
    import sqlite3

    path = os.path.join(project_dir(), DB_REL)
    if not os.path.exists(path):
        return []
    try:
        conn = sqlite3.connect(path, timeout=1.0)
        try:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, params)]
        finally:
            conn.close()
    except Exception:
        return []


def due_counts():
    """(overdue, due_today) review counts, straight from the FSRS card table."""
    now_iso = local_now().isoformat(timespec="seconds")
    end_of_day = (local_now().replace(hour=23, minute=59, second=59)).isoformat(timespec="seconds")
    rows = query_db(
        "SELECT SUM(CASE WHEN due <= ? THEN 1 ELSE 0 END) AS overdue, "
        "       SUM(CASE WHEN due > ? AND due <= ? THEN 1 ELSE 0 END) AS today "
        "FROM cards JOIN concepts c ON c.id = cards.concept_id "
        "WHERE cards.suspended = 0 AND c.status != 'excluded'",
        (now_iso, now_iso, end_of_day),
    )
    if not rows:
        return 0, 0
    return int(rows[0].get("overdue") or 0), int(rows[0].get("today") or 0)


def next_block():
    now_iso = local_now().isoformat(timespec="seconds")
    rows = query_db(
        "SELECT subject, kind, start, topic FROM blocks WHERE status = 'planned' AND start >= ? "
        "ORDER BY start LIMIT 1",
        (now_iso,),
    )
    return rows[0] if rows else None


__all__ = [
    "block_line",
    "due_counts",
    "elapsed_minutes",
    "emit_context",
    "guard",
    "humanize",
    "local_now",
    "next_block",
    "parse_iso",
    "project_dir",
    "read_block_state",
    "read_hook_input",
    "SOLO_RULE",
    "throttled",
    "timedelta",
    "write_block_state",
    "WRAPUP_DIRECTIVE",
]
