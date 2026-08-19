"""Block clock and background timer (PRD §3.4.1).

The constraint this module works around: an MCP server cannot push a message
into an idle Claude Code conversation. So time awareness is split in two.

* **For the model** — ``state/block.json``, which the Claude Code hooks read on
  every user message and tool call. Hooks always run; instructions get forgotten
  as context fills, which is precisely why this is not left to the model.
* **For the human** — a background thread in this process fires OS notifications
  at the end-warning and at block end, covering the solo-mode gap where nothing
  the user does triggers a hook.

Everything the hooks need is in one small JSON file, parseable with the standard
library on an old interpreter. Keep it that way.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from typing import Any, Optional

from .config import get_settings
from .notify import notify
from .store import log_event
from .timeutil import humanize_minutes, now, parse, to_iso

_TIMER_LOCK = threading.Lock()
_TIMER: Optional[threading.Thread] = None
_TIMER_GENERATION = 0

SEGMENTS = ("review", "new_material", "practice", "assessment", "wrapup", "break")

EMPTY_STATE: dict[str, Any] = {"active": False}


def _path():
    return get_settings().block_state_path


def read_state() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return dict(EMPTY_STATE)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(EMPTY_STATE)


def write_state(state: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _elapsed_minutes(state: dict[str, Any], reference: Optional[dt.datetime] = None) -> float:
    reference = reference or now()
    start = parse(state["start"])
    paused = float(state.get("paused_total_s", 0))
    if state.get("paused") and state.get("paused_at"):
        paused += (reference - parse(state["paused_at"])).total_seconds()
    return max(0.0, ((reference - start).total_seconds() - paused) / 60.0)


def status(reference: Optional[dt.datetime] = None) -> dict[str, Any]:
    """Full block status. Safe to call when no block is running."""
    state = read_state()
    if not state.get("active"):
        return {
            "active": False,
            "summary": "No block running.",
            "hint": "Call start_block to begin a study block.",
        }
    reference = reference or now()
    duration = float(state["duration_minutes"])
    elapsed = _elapsed_minutes(state, reference)
    remaining = duration - elapsed
    settings = get_settings().for_subject(state.get("subject"))

    segment = state.get("segment", "review")
    segment_elapsed = (
        (reference - parse(state["segment_started"])).total_seconds() / 60.0
        if state.get("segment_started")
        else elapsed
    )
    review_budget = float(state.get("review_segment_minutes", settings.review_segment_minutes))

    flags = []
    if state.get("paused"):
        flags.append("PAUSED")
    if state.get("solo_mode"):
        flags.append("SOLO MODE — no solutions, one hint max via stuck_hatch")
    if segment == "review" and segment_elapsed > review_budget:
        flags.append(
            f"Review segment over budget by {humanize_minutes(segment_elapsed - review_budget)} — "
            "it eats into new material, which is the intended behaviour (§3.4)"
        )
    if remaining <= 0:
        flags.append("BLOCK OVER — wrap up now: write notes, update covered.md, prep next lesson")
    elif remaining <= settings.notify_before_end_minutes:
        flags.append(f"{humanize_minutes(remaining)} left — start converging")

    return {
        "active": True,
        "block_id": state.get("block_id"),
        "subject": state.get("subject"),
        "kind": state.get("kind", "study"),
        "topic": state.get("topic"),
        "start": state["start"],
        "end": state["end"],
        "duration_minutes": duration,
        "elapsed_minutes": round(elapsed, 1),
        "remaining_minutes": round(remaining, 1),
        "overrun": remaining < 0,
        "segment": segment,
        "segment_elapsed_minutes": round(segment_elapsed, 1),
        "review_segment_minutes": review_budget,
        "solo_mode": bool(state.get("solo_mode")),
        "paused": bool(state.get("paused")),
        "wrapup_requested": bool(state.get("wrapup_requested")),
        "wrapup_done": bool(state.get("wrapup_done")),
        "notes_path": state.get("notes_path"),
        "lesson_ref": state.get("lesson_ref"),
        "flags": flags,
        "summary": compact_line(state, reference),
    }


def compact_line(state: Optional[dict[str, Any]] = None, reference: Optional[dt.datetime] = None) -> str:
    """The one-liner the hooks inject. Kept short — it appears on every turn."""
    state = state if state is not None else read_state()
    if not state.get("active"):
        return "[No study block running]"
    reference = reference or now()
    duration = float(state["duration_minutes"])
    elapsed = _elapsed_minutes(state, reference)
    remaining = duration - elapsed
    bits = [
        f"Block {int(elapsed)}/{int(duration)}min",
        f"segment={state.get('segment', 'review')}",
    ]
    if state.get("subject"):
        bits.append(f"subject={state['subject']}")
    if state.get("paused"):
        bits.append("PAUSED")
    if state.get("solo_mode"):
        bits.append("SOLO")
    if remaining <= 0:
        bits.append(f"OVER by {humanize_minutes(-remaining)} — WRAP UP")
    else:
        bits.append(f"{humanize_minutes(remaining)} left")
    return "[" + ", ".join(bits) + "]"


# --- background timer ----------------------------------------------------


def _timer_loop(generation: int) -> None:
    """Fires the human-facing notifications. One thread per block; supersedes on restart."""
    warned = False
    while True:
        with _TIMER_LOCK:
            if generation != _TIMER_GENERATION:
                return
        state = read_state()
        if not state.get("active"):
            return
        settings = get_settings().for_subject(state.get("subject"))
        elapsed = _elapsed_minutes(state)
        remaining = float(state["duration_minutes"]) - elapsed

        if not state.get("paused"):
            if not warned and 0 < remaining <= settings.notify_before_end_minutes:
                warned = True
                notify(
                    "Study block ending soon",
                    f"{humanize_minutes(remaining)} left"
                    + (f" — {state.get('topic')}" if state.get("topic") else ""),
                )
            if remaining <= 0:
                notify(
                    "Block over — take a break",
                    f"{int(state['duration_minutes'])} min done. "
                    f"Break for {settings.break_minutes} min, then wrap-up.",
                )
                log_event(state.get("subject"), "block_timer_fired", {"block_id": state.get("block_id")})
                state["timer_fired"] = True
                write_state(state)
                _break_timer(settings.break_minutes, generation)
                return
        threading.Event().wait(5.0)


def _break_timer(minutes: int, generation: int) -> None:
    def fire() -> None:
        threading.Event().wait(minutes * 60)
        with _TIMER_LOCK:
            if generation != _TIMER_GENERATION:
                return
        notify("Break over", "Ready for the next block?")

    thread = threading.Thread(target=fire, daemon=True, name="harness-break-timer")
    thread.start()


def _start_timer() -> None:
    global _TIMER, _TIMER_GENERATION
    with _TIMER_LOCK:
        _TIMER_GENERATION += 1
        generation = _TIMER_GENERATION
    thread = threading.Thread(target=_timer_loop, args=(generation,), daemon=True, name="harness-block-timer")
    thread.start()
    globals()["_TIMER"] = thread


def _stop_timer() -> None:
    global _TIMER_GENERATION
    with _TIMER_LOCK:
        _TIMER_GENERATION += 1


# --- lifecycle -----------------------------------------------------------


def start_block(
    subject: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    kind: str = "study",
    topic: Optional[str] = None,
    block_id: Optional[int] = None,
    lesson_ref: Optional[str] = None,
    solo_mode: Optional[bool] = None,
    review_segment_minutes: Optional[int] = None,
) -> dict[str, Any]:
    """Begin a block: write the state hooks read, arm the notification timer."""
    settings = get_settings().for_subject(subject)
    existing = read_state()
    if existing.get("active"):
        return {
            "error": "a block is already running",
            "current": status(),
            "hint": "call end_block first, or extend_block if you just need more time",
        }
    duration = duration_minutes or settings.focus_minutes
    started = now()
    state = {
        "active": True,
        "block_id": block_id,
        "subject": subject,
        "kind": kind,
        "topic": topic,
        "lesson_ref": lesson_ref,
        "start": to_iso(started),
        "end": to_iso(started + dt.timedelta(minutes=duration)),
        "duration_minutes": duration,
        "segment": "review" if kind in ("study", "review") else "assessment",
        "segment_started": to_iso(started),
        "review_segment_minutes": review_segment_minutes or settings.review_segment_minutes,
        "solo_mode": settings.solo_mode_default if solo_mode is None else bool(solo_mode),
        "paused": False,
        "paused_total_s": 0,
        "wrapup_requested": False,
        "wrapup_done": False,
        "notes_path": _notes_path(subject, started),
    }
    write_state(state)
    _start_timer()
    if block_id:
        from .scheduler import update_block

        update_block(block_id, status="active")
    log_event(subject, "block_started", {"kind": kind, "topic": topic, "duration": duration})
    return {
        "started": True,
        "state": status(),
        "protocol": (
            "Review segment first, then new material (§3.4). Fetch the live queue now with review_queue — "
            "never a pre-allocated list. Overdue items are mandatory before new material."
        ),
    }


def _notes_path(subject: Optional[str], when: dt.datetime) -> Optional[str]:
    if not subject:
        return None
    return f"subjects/{subject}/notes/{when.strftime('%Y-%m-%d')}.md"


def set_segment(segment: str) -> dict[str, Any]:
    if segment not in SEGMENTS:
        raise ValueError(f"segment must be one of {SEGMENTS}")
    state = read_state()
    if not state.get("active"):
        return {"error": "no block running"}
    state["segment"] = segment
    state["segment_started"] = to_iso(now())
    write_state(state)
    return status()


def set_solo_mode(enabled: bool) -> dict[str, Any]:
    state = read_state()
    if not state.get("active"):
        return {"error": "no block running"}
    state["solo_mode"] = bool(enabled)
    write_state(state)
    return {
        "solo_mode": bool(enabled),
        "rule": (
            "Solo mode ON: the user works without AI help. Do not give solutions, corrections, or "
            "leading questions. One hint per exercise via stuck_hatch, grounded in the reference solution."
            if enabled
            else "Solo mode OFF: normal explanation allowed."
        ),
        "state": status(),
    }


def pause_block(reason: Optional[str] = None) -> dict[str, Any]:
    state = read_state()
    if not state.get("active"):
        return {"error": "no block running"}
    if state.get("paused"):
        return status()
    state["paused"] = True
    state["paused_at"] = to_iso(now())
    state["pause_reason"] = reason
    write_state(state)
    return status()


def resume_block() -> dict[str, Any]:
    state = read_state()
    if not state.get("active") or not state.get("paused"):
        return status()
    paused_at = parse(state["paused_at"])
    state["paused_total_s"] = float(state.get("paused_total_s", 0)) + (now() - paused_at).total_seconds()
    state["paused"] = False
    state.pop("paused_at", None)
    state["end"] = to_iso(
        parse(state["start"])
        + dt.timedelta(minutes=float(state["duration_minutes"]), seconds=state["paused_total_s"])
    )
    write_state(state)
    return status()


def extend_block(minutes: int) -> dict[str, Any]:
    state = read_state()
    if not state.get("active"):
        return {"error": "no block running"}
    state["duration_minutes"] = float(state["duration_minutes"]) + minutes
    state["end"] = to_iso(parse(state["end"]) + dt.timedelta(minutes=minutes))
    state["wrapup_requested"] = False
    state["timer_fired"] = False
    write_state(state)
    _start_timer()
    return status()


def mark_wrapup_requested() -> dict[str, Any]:
    """Called by the Stop hook so the wrap-up directive is injected exactly once."""
    state = read_state()
    if not state.get("active"):
        return {"active": False}
    state["wrapup_requested"] = True
    write_state(state)
    return state


def end_block(
    notes_path: Optional[str] = None,
    summary: Optional[str] = None,
    mark_done: bool = True,
) -> dict[str, Any]:
    """Close the block: stop the timer, clear state, return the wrap-up checklist."""
    state = read_state()
    if not state.get("active"):
        return {"error": "no block running"}
    _stop_timer()
    elapsed = _elapsed_minutes(state)
    subject = state.get("subject")
    block_id = state.get("block_id")
    if block_id and mark_done:
        from .scheduler import update_block

        update_block(block_id, status="done", notes_path=notes_path or state.get("notes_path"))
    log_event(
        subject,
        "block_ended",
        {"block_id": block_id, "minutes": round(elapsed, 1), "summary": summary},
    )
    write_state({"active": False, "last_block": {**state, "ended_at": to_iso(now())}})
    return {
        "ended": True,
        "subject": subject,
        "minutes": round(elapsed, 1),
        "notes_path": notes_path or state.get("notes_path"),
        "checklist": [
            f"Write notes to {notes_path or state.get('notes_path')} — what was covered, what was shaky",
            "Append covered concepts to subjects/<subject>/covered.md",
            "Deposit held-back questions into exam-pool/ (formulations, proofs, problems) with rubrics",
            "Record time-on-task per concept (record_practice) and grade any pending exercises",
            "Assign every prepared-but-untouched problem as homework — list it in the notes "
            "under ## Homework with lesson ref, problem number and variant tag",
            "Trigger full preparation of lesson N+1 and extend the outline window (§3.3)",
            "Check kolokvium_check and remediation_check before ending the turn",
        ],
    }


def clear_state() -> dict[str, Any]:
    """Escape hatch for a stale state file (crash, forced restart)."""
    _stop_timer()
    write_state(dict(EMPTY_STATE))
    return {"cleared": True}
