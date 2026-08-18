"""Scheduling (PRD §3.2).

Rules encoded here rather than left to the model:

* windows are **re-indexed after every placement** — never computed once and
  filled blindly;
* 50/10 focus rhythm with a long break after ~2 h of study;
* **spacing beats massing**: placement goes round-robin over days, so two
  sessions land on two days before a second session lands on one;
* the horizon is 14 days and the plan it produces is explicitly *vague* — topics
  roughly, because real pace is unpredictable;
* the review segment is reserved as **capacity**, never as pre-allocated items
  (§4) — the queue is fetched live at block start.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Iterable, Optional

from .calendar import Interval, get_calendar, merge_intervals
from .config import get_settings
from .store import connect, init_db
from .timeutil import day_start, humanize_minutes, now, parse, to_iso

BLOCK_KINDS = ("study", "review", "prep", "kolokvium", "exam", "remediation")


def _scheduled_intervals(start: dt.datetime, end: dt.datetime) -> list[Interval]:
    """Already-placed study blocks — they block time exactly like life commitments do."""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, subject, kind, start, end, topic FROM blocks "
            "WHERE status IN ('planned','active') AND end > ? AND start < ?",
            (to_iso(start), to_iso(end)),
        ).fetchall()
    return [
        Interval(
            parse(r["start"]),
            parse(r["end"]),
            f"{r['kind']}: {r['topic'] or r['subject'] or 'study'}",
            "block",
        )
        for r in rows
    ]


def free_windows(
    start: Optional[str] = None,
    end: Optional[str] = None,
    min_minutes: Optional[int] = None,
) -> dict[str, Any]:
    """Available windows inside daily study hours, minus commitments and placed blocks."""
    settings = get_settings()
    begin = parse(start) if start else now()
    finish = parse(end) if end else begin + dt.timedelta(days=settings.scheduling_horizon_days)
    minimum = min_minutes or settings.focus_minutes

    busy = merge_intervals(list(get_calendar().busy(begin, finish)) + _scheduled_intervals(begin, finish))
    windows: list[dict[str, Any]] = []

    cursor = day_start(begin)
    while cursor < finish:
        day_open = max(cursor.replace(hour=settings.day_start_hour, minute=0), begin)
        day_close = min(cursor.replace(hour=settings.day_end_hour, minute=0), finish)
        cursor += dt.timedelta(days=1)
        if day_close <= day_open:
            continue
        pointer = day_open
        for interval in busy:
            if interval.end <= day_open or interval.start >= day_close:
                continue
            if interval.start > pointer:
                _append_window(windows, pointer, min(interval.start, day_close), minimum)
            pointer = max(pointer, interval.end)
            if pointer >= day_close:
                break
        if pointer < day_close:
            _append_window(windows, pointer, day_close, minimum)

    return {
        "from": to_iso(begin),
        "to": to_iso(finish),
        "min_minutes": minimum,
        "windows": windows,
        "total_free_minutes": sum(w["minutes"] for w in windows),
        "busy": [i.to_dict() for i in busy],
    }


def _append_window(acc: list[dict[str, Any]], start: dt.datetime, end: dt.datetime, minimum: int) -> None:
    minutes = int((end - start).total_seconds() // 60)
    if minutes >= minimum:
        acc.append(
            {
                "start": to_iso(start),
                "end": to_iso(end),
                "minutes": minutes,
                "day": start.strftime("%Y-%m-%d"),
                "weekday": start.strftime("%a"),
            }
        )


def _blocks_on_day(conn, day: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) n FROM blocks WHERE status IN ('planned','active') AND substr(start,1,10) = ?",
        (day,),
    ).fetchone()["n"]


def propose_schedule(
    subject: str,
    count: int = 5,
    topics: Optional[Iterable[str]] = None,
    kind: str = "study",
    duration_minutes: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    commit: bool = False,
) -> dict[str, Any]:
    """Propose (or place) ``count`` blocks, re-indexing windows after each placement.

    Returns a proposal by default. Placement is a separate, explicit step so the
    user can trim it first — the plan is meant to be vague and negotiable.
    """
    settings = get_settings().for_subject(subject)
    duration = duration_minutes or settings.focus_minutes
    topic_list = list(topics or [])
    begin = parse(start) if start else now() + dt.timedelta(minutes=30)
    finish = parse(end) if end else begin + dt.timedelta(days=settings.scheduling_horizon_days)

    placed: list[dict[str, Any]] = []
    skipped_reason: Optional[str] = None

    for index in range(count):
        # Re-index every iteration: previous placements are already busy time.
        window_data = free_windows(to_iso(begin), to_iso(finish), duration)
        slot = _pick_slot(window_data["windows"], duration, settings, placed)
        if slot is None:
            skipped_reason = (
                "Ran out of free windows in the horizon. Trim commitments, widen day_start/day_end hours, "
                "or extend the horizon."
            )
            break
        topic = topic_list[index] if index < len(topic_list) else None
        entry = {
            "subject": subject,
            "kind": kind,
            "start": slot["start"],
            "end": slot["end"],
            "topic": topic,
            "day": slot["day"],
            "weekday": slot["weekday"],
            "composition": {
                "review_segment_minutes": settings.review_segment_minutes,
                "new_material_minutes": max(0, duration - settings.review_segment_minutes),
                "note": "Review capacity only — the queue is fetched live at block start (§4).",
            },
        }
        if commit:
            entry["id"] = place_block(
                subject=subject, start=slot["start"], end=slot["end"], kind=kind, topic=topic
            )["id"]
        placed.append(entry)

    days_used = sorted({p["day"] for p in placed})
    return {
        "subject": subject,
        "requested": count,
        "placed": len(placed),
        "committed": commit,
        "blocks": placed,
        "distinct_days": len(days_used),
        "days": days_used,
        "spacing_note": (
            "Blocks were distributed round-robin across days: two sessions on two days beat one "
            "double session (§3.2)."
            if settings.prefer_spacing
            else "prefer_spacing is off — blocks were packed into the earliest windows."
        ),
        "horizon_note": "A 2-week plan is intentionally vague: topics roughly, because pace is unpredictable.",
        "warning": skipped_reason,
    }


def _pick_slot(
    windows: list[dict[str, Any]],
    duration: int,
    settings: Any,
    already: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Choose the next slot, preferring days that carry the fewest blocks so far."""
    if not windows:
        return None
    per_day: dict[str, int] = {}
    with connect() as conn:
        for w in windows:
            per_day.setdefault(w["day"], _blocks_on_day(conn, w["day"]))
    for entry in already:
        per_day[entry["day"]] = per_day.get(entry["day"], 0) + 1

    candidates = [w for w in windows if per_day.get(w["day"], 0) < settings.max_blocks_per_day]
    if not candidates:
        return None
    if settings.prefer_spacing:
        candidates.sort(key=lambda w: (per_day.get(w["day"], 0), w["start"]))
    else:
        candidates.sort(key=lambda w: w["start"])

    window = candidates[0]
    start = parse(window["start"])
    # Honour the long break: if this day already has ~2h of study, push the slot later.
    if per_day.get(window["day"], 0) * settings.focus_minutes >= settings.long_break_after_minutes:
        start = start + dt.timedelta(minutes=settings.long_break_minutes)
        if (parse(window["end"]) - start).total_seconds() / 60 < duration:
            return _pick_slot([w for w in windows if w is not window], duration, settings, already)
    end = start + dt.timedelta(minutes=duration)
    return {
        "start": to_iso(start),
        "end": to_iso(end),
        "day": window["day"],
        "weekday": window["weekday"],
    }


def place_block(
    subject: Optional[str],
    start: str,
    end: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    kind: str = "study",
    topic: Optional[str] = None,
    lesson_ref: Optional[str] = None,
) -> dict[str, Any]:
    """Commit one block to the schedule. Refuses to double-book."""
    if kind not in BLOCK_KINDS:
        raise ValueError(f"kind must be one of {BLOCK_KINDS}")
    settings = get_settings().for_subject(subject)
    begin = parse(start)
    finish = (
        parse(end)
        if end
        else begin + dt.timedelta(minutes=duration_minutes or settings.focus_minutes)
    )
    if finish <= begin:
        raise ValueError("block end must be after start")

    init_db()
    with connect() as conn:
        clash = conn.execute(
            "SELECT id, kind, topic, start, end FROM blocks "
            "WHERE status IN ('planned','active') AND start < ? AND end > ?",
            (to_iso(finish), to_iso(begin)),
        ).fetchone()
        if clash:
            raise ValueError(
                f"overlaps block #{clash['id']} ({clash['kind']} {clash['start']} → {clash['end']}); "
                "cancel or reschedule it first"
            )
        cursor = conn.execute(
            """INSERT INTO blocks(subject, kind, start, end, topic, status, lesson_ref, created_at)
               VALUES(?,?,?,?,?,'planned',?,?)""",
            (subject, kind, to_iso(begin), to_iso(finish), topic, lesson_ref, to_iso(now())),
        )
        block_id = int(cursor.lastrowid)
    return {
        "id": block_id,
        "subject": subject,
        "kind": kind,
        "start": to_iso(begin),
        "end": to_iso(finish),
        "duration": humanize_minutes((finish - begin).total_seconds() / 60),
        "topic": topic,
    }


def list_blocks(
    subject: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    init_db()
    query = "SELECT * FROM blocks WHERE 1=1"
    params: list[Any] = []
    if subject:
        query += " AND subject = ?"
        params.append(subject)
    if start:
        query += " AND end >= ?"
        params.append(to_iso(parse(start)))
    if end:
        query += " AND start <= ?"
        params.append(to_iso(parse(end)))
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY start"
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(query, params)]
    reference = now()
    for row in rows:
        row["is_next"] = False
    upcoming = [r for r in rows if parse(r["start"]) >= reference and r["status"] == "planned"]
    if upcoming:
        upcoming[0]["is_next"] = True
    return {"blocks": rows, "count": len(rows), "next": upcoming[0] if upcoming else None}


def update_block(
    block_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
    topic: Optional[str] = None,
    lesson_ref: Optional[str] = None,
    notes_path: Optional[str] = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if start:
        fields["start"] = to_iso(parse(start))
    if end:
        fields["end"] = to_iso(parse(end))
    if status:
        fields["status"] = status
        if status in ("done", "skipped", "cancelled"):
            fields["closed_at"] = to_iso(now())
    if topic is not None:
        fields["topic"] = topic
    if lesson_ref is not None:
        fields["lesson_ref"] = lesson_ref
    if notes_path is not None:
        fields["notes_path"] = notes_path
    if not fields:
        raise ValueError("nothing to update")
    assignments = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE blocks SET {assignments} WHERE id = ?", (*fields.values(), block_id))
        row = conn.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
    if row is None:
        raise ValueError(f"no block #{block_id}")
    return dict(row)


def agenda(subject: Optional[str] = None, days: int = 7) -> dict[str, Any]:
    """Compact upcoming view: blocks plus the review load they will have to absorb."""
    from .srs import forecast

    reference = now()
    blocks = list_blocks(subject, to_iso(reference), to_iso(reference + dt.timedelta(days=days)), "planned")
    load = forecast(subject, days)
    by_day: dict[str, dict[str, Any]] = {}
    for block in blocks["blocks"]:
        day = block["start"][:10]
        by_day.setdefault(day, {"blocks": [], "reviews_due": 0})
        by_day[day]["blocks"].append(
            {"id": block["id"], "kind": block["kind"], "start": block["start"][11:16], "topic": block["topic"]}
        )
    for entry in load["by_day"]:
        by_day.setdefault(entry["day"], {"blocks": [], "reviews_due": 0})["reviews_due"] = entry["n"]
    return {
        "subject": subject,
        "days": days,
        "agenda": dict(sorted(by_day.items())),
        "overdue_reviews": load["overdue"],
        "next_block": blocks["next"],
    }
