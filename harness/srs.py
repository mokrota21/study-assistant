"""Spaced repetition (PRD §4), FSRS via the `fsrs` package.

Two rules from the PRD shape this module:

* **The unit is the sub-skill, not the exercise.** A due card means "generate a
  fresh mini-exercise on this concept", so cards carry no question text.
* **Reviews are never pre-allocated into future blocks.** There is no "assign"
  operation — only :func:`due_queue`, fetched live at block start, and
  :func:`forecast`, which the scheduler uses to reserve *capacity*.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from typing import Any, Optional

from fsrs import Card, Rating, Scheduler, State

from .concepts import list_concepts, prerequisites, require_concept_id
from .config import Settings, get_settings
from .store import connect, init_db
from .timeutil import humanize_delta, now, to_iso, to_local, to_utc, parse

RATING_NAMES = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}


def _scheduler(settings: Settings) -> Scheduler:
    return Scheduler(
        desired_retention=settings.fsrs_desired_retention,
        maximum_interval=settings.fsrs_maximum_interval_days,
        enable_fuzzing=settings.fsrs_enable_fuzzing,
    )


def rating_from_score(score: float, hints_used: int = 0) -> int:
    """Map a rubric score (0..1) to an FSRS rating.

    A hint means the retrieval was assisted, so the ceiling drops to Hard — the
    whole point of §6 is that assisted success must not be scored like unassisted
    success, which is exactly how the unguarded-tutor cohort fooled itself.
    """
    if score < 0.5:
        return 1
    if hints_used > 0:
        return 2
    if score < 0.75:
        return 2
    if score < 0.95:
        return 3
    return 4


def _persist_card(conn: sqlite3.Connection, concept_id: int, card: Card) -> None:
    data = card.to_dict()
    conn.execute(
        """INSERT INTO cards(concept_id, card_json, due, state, stability, difficulty,
                             reps, lapses, suspended, last_review, updated_at)
           VALUES(?,?,?,?,?,?,COALESCE((SELECT reps FROM cards WHERE concept_id=?),0),
                  COALESCE((SELECT lapses FROM cards WHERE concept_id=?),0),
                  COALESCE((SELECT suspended FROM cards WHERE concept_id=?),0),?,?)
           ON CONFLICT(concept_id) DO UPDATE SET
             card_json=excluded.card_json, due=excluded.due, state=excluded.state,
             stability=excluded.stability, difficulty=excluded.difficulty,
             last_review=excluded.last_review, updated_at=excluded.updated_at""",
        (
            concept_id,
            json.dumps(data),
            to_iso(to_local(card.due)),
            card.state.name,
            card.stability,
            card.difficulty,
            concept_id,
            concept_id,
            concept_id,
            to_iso(to_local(card.last_review)) if card.last_review else None,
            to_iso(now()),
        ),
    )


def _load_card(conn: sqlite3.Connection, concept_id: int) -> Optional[Card]:
    row = conn.execute("SELECT card_json FROM cards WHERE concept_id = ?", (concept_id,)).fetchone()
    return Card.from_dict(json.loads(row["card_json"])) if row else None


def ensure_card(subject: str, concept: str) -> dict[str, Any]:
    """Create the FSRS card for a concept if it does not exist yet (called when a concept is introduced)."""
    init_db()
    with connect() as conn:
        cid = require_concept_id(conn, subject, concept)
        card = _load_card(conn, cid)
        created = card is None
        if created:
            card = Card()
            _persist_card(conn, cid, card)
    return {
        "subject": subject,
        "concept": concept,
        "created": created,
        "due": to_iso(to_local(card.due)),
        "state": card.state.name,
    }


def due_queue(
    subject: Optional[str] = None,
    limit: Optional[int] = None,
    at: Optional[str] = None,
    include_ahead: bool = True,
) -> dict[str, Any]:
    """The live review queue for a block (§3.4): overdue → due → ahead-of-schedule.

    ``include_ahead`` fills leftover capacity with not-yet-due cards, ordered by
    proximity, so a short review segment is never wasted.
    """
    init_db()
    settings = get_settings().for_subject(subject)
    cap = limit or settings.review_cap_per_block
    reference = parse(at) if at else now()
    ref_iso = to_iso(reference)

    query = (
        "SELECT c.id AS concept_id, c.subject, c.name, c.status, cards.due, cards.state, "
        "       cards.stability, cards.reps, cards.lapses "
        "FROM cards JOIN concepts c ON c.id = cards.concept_id "
        "WHERE cards.suspended = 0 AND c.status != 'excluded'"
    )
    params: list[Any] = []
    if subject:
        query += " AND c.subject = ?"
        params.append(subject)
    query += " ORDER BY cards.due ASC"

    with connect() as conn:
        rows = [dict(r) for r in conn.execute(query, params)]

    due_items, ahead_items = [], []
    for row in rows:
        overdue = row["due"] <= ref_iso
        item = {
            "concept": row["name"],
            "subject": row["subject"],
            "concept_id": row["concept_id"],
            "due": row["due"],
            "when": humanize_delta(parse(row["due"]), reference),
            "overdue": overdue,
            "state": row["state"],
            "reps": row["reps"],
            "lapses": row["lapses"],
            "instruction": "Generate a FRESH free-recall / short-answer exercise on this concept. Never a flashcard.",
        }
        (due_items if overdue else ahead_items).append(item)

    selected = due_items[:cap]
    overflow = max(0, len(due_items) - cap)
    if include_ahead and len(selected) < cap:
        selected += ahead_items[: cap - len(selected)]

    minutes_estimate = len(selected) * 2
    return {
        "as_of": ref_iso,
        "subject": subject,
        "cap": cap,
        "due_now": len(due_items),
        "overflow": overflow,
        "items": selected,
        "estimated_minutes": minutes_estimate,
        "segment_pressure": (
            "Review load exceeds the segment — it eats into new-material time. "
            "Many failed reviews mean the pace is already too fast (§3.4)."
            if minutes_estimate > settings.review_segment_minutes
            else "Fits the review segment."
        ),
        "mandatory": [i["concept"] for i in selected if i["overdue"]],
    }


def grade(
    subject: str,
    concept: str,
    rating: Optional[int] = None,
    score: Optional[float] = None,
    correct: Optional[bool] = None,
    kind: str = "in_session",
    variant: Optional[str] = None,
    exercise_ref: Optional[str] = None,
    hints_used: int = 0,
    duration_s: Optional[int] = None,
    minutes_on_task: Optional[float] = None,
    block_id: Optional[int] = None,
    note: Optional[str] = None,
    at: Optional[str] = None,
) -> dict[str, Any]:
    """Record a graded retrieval attempt: advances FSRS, logs the rep, re-evaluates mastery.

    Pass ``rating`` (1-4) or ``score`` (0..1); if only ``score`` is given the
    rating is derived, with hints capping it at Hard.
    """
    from .mastery import evaluate_mastery

    init_db()
    settings = get_settings().for_subject(subject)
    if rating is None:
        if score is None:
            raise ValueError("pass either rating (1-4) or score (0..1)")
        rating = rating_from_score(score, hints_used)
    if rating not in RATING_NAMES:
        raise ValueError(f"rating must be 1..4, got {rating}")
    if correct is None:
        correct = rating >= 3 if score is None else score >= 0.75
    reviewed_at = parse(at) if at else now()

    with connect() as conn:
        cid = require_concept_id(conn, subject, concept)
        card = _load_card(conn, cid) or Card()
        scheduler = _scheduler(settings)
        updated, _log = scheduler.review_card(
            card, Rating(rating), review_datetime=to_utc(reviewed_at), review_duration=duration_s
        )
        _persist_card(conn, cid, updated)
        conn.execute(
            "UPDATE cards SET reps = reps + 1, lapses = lapses + ? WHERE concept_id = ?",
            (1 if rating == 1 else 0, cid),
        )
        conn.execute(
            """INSERT INTO reviews(concept_id, subject, at, rating, correct, score, kind, variant,
                                   exercise_ref, hints_used, duration_s, block_id, note)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cid,
                subject,
                to_iso(reviewed_at),
                rating,
                int(bool(correct)),
                score,
                kind,
                variant,
                exercise_ref,
                hints_used,
                duration_s,
                block_id,
                note,
            ),
        )
        if minutes_on_task:
            conn.execute(
                "INSERT INTO practice(concept_id, subject, minutes, at, block_id, note) VALUES(?,?,?,?,?,?)",
                (cid, subject, float(minutes_on_task), to_iso(reviewed_at), block_id, exercise_ref),
            )
        if conn.execute("SELECT status FROM concepts WHERE id=?", (cid,)).fetchone()["status"] == "planned":
            conn.execute("UPDATE concepts SET status='learning', started_at=? WHERE id=?", (to_iso(reviewed_at), cid))

    trickled = _apply_trickle_down(subject, concept, rating, settings, reviewed_at) if settings.trickle_down_enabled else []
    mastery = evaluate_mastery(subject, concept)

    return {
        "subject": subject,
        "concept": concept,
        "rating": rating,
        "rating_name": RATING_NAMES[rating],
        "correct": bool(correct),
        "kind": kind,
        "next_due": to_iso(to_local(updated.due)),
        "interval": humanize_delta(to_local(updated.due), reviewed_at),
        "state": updated.state.name,
        "stability_days": round(updated.stability, 2) if updated.stability else None,
        "trickle_down": trickled,
        "mastery": mastery,
    }


def _apply_trickle_down(
    subject: str, concept: str, rating: int, settings: Settings, reviewed_at: Any
) -> list[dict[str, Any]]:
    """Simplified FIRe-style credit: success on an advanced skill discounts prerequisite reviews.

    This is the *one-level-discount* variant of PRD open question #3, generalized
    to ``trickle_down_depth`` levels with geometric decay: a prerequisite's due
    date is pushed out by a fraction of its own current interval. It never marks
    the prerequisite reviewed, so it cannot manufacture mastery reps — it only
    prevents review-load explosion.
    """
    if rating < 3:
        return []
    # Resolve the graph before opening a connection: prerequisites() opens its own,
    # and nesting them deadlocks SQLite mid-transaction.
    levels = [
        (depth, settings.trickle_down_credit**depth, prerequisites(subject, concept, depth=depth))
        for depth in range(1, settings.trickle_down_depth + 1)
    ]
    applied: list[dict[str, Any]] = []
    with connect() as conn:
        for depth, factor, prereq_names in levels:
            for prereq in prereq_names:
                if any(a["concept"] == prereq for a in applied):
                    continue
                row = conn.execute(
                    """SELECT cards.concept_id, cards.due, cards.last_review, cards.state
                       FROM cards JOIN concepts c ON c.id = cards.concept_id
                       WHERE c.subject = ? AND c.name = ? AND cards.suspended = 0""",
                    (subject, prereq),
                ).fetchone()
                if row is None or row["state"] != State.Review.name or not row["last_review"]:
                    continue
                due = parse(row["due"])
                interval = (due - parse(row["last_review"])).total_seconds()
                if interval <= 0:
                    continue
                new_due = due + dt.timedelta(seconds=interval * factor)
                conn.execute("UPDATE cards SET due = ? WHERE concept_id = ?", (to_iso(new_due), row["concept_id"]))
                applied.append(
                    {
                        "concept": prereq,
                        "depth": depth,
                        "credit": round(factor, 3),
                        "new_due": to_iso(new_due),
                    }
                )
    return applied


def forecast(subject: Optional[str] = None, days: int = 14) -> dict[str, Any]:
    """Reviews coming due per day — the scheduler reserves capacity from this, never slots."""
    init_db()
    query = (
        "SELECT substr(cards.due, 1, 10) AS day, COUNT(*) AS n "
        "FROM cards JOIN concepts c ON c.id = cards.concept_id WHERE cards.suspended = 0"
    )
    params: list[Any] = []
    if subject:
        query += " AND c.subject = ?"
        params.append(subject)
    query += " GROUP BY day ORDER BY day"
    today = to_iso(now())[:10]
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(query, params)]
    overdue = sum(r["n"] for r in rows if r["day"] < today)
    horizon = [r for r in rows if today <= r["day"]][:days]
    return {
        "subject": subject,
        "overdue": overdue,
        "by_day": horizon,
        "peak_day": max(horizon, key=lambda r: r["n"]) if horizon else None,
        "total_cards": sum(r["n"] for r in rows),
    }


def set_suspended(subject: str, concept: str, suspended: bool) -> dict[str, Any]:
    with connect() as conn:
        cid = require_concept_id(conn, subject, concept)
        conn.execute("UPDATE cards SET suspended = ? WHERE concept_id = ?", (int(suspended), cid))
    return {"subject": subject, "concept": concept, "suspended": suspended}


def card_summary(subject: str) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """SELECT c.name, c.status, cards.due, cards.state, cards.reps, cards.lapses,
                      cards.stability, cards.suspended
               FROM concepts c LEFT JOIN cards ON cards.concept_id = c.id
               WHERE c.subject = ? ORDER BY cards.due IS NULL, cards.due""",
            (subject,),
        )
        return [dict(r) for r in rows]


def seed_missing_cards(subject: str) -> dict[str, Any]:
    """Give every non-excluded concept a card. Safe to call repeatedly."""
    created = []
    for concept in list_concepts(subject):
        if concept["status"] == "excluded":
            continue
        result = ensure_card(subject, concept["name"])
        if result["created"]:
            created.append(concept["name"])
    return {"subject": subject, "created": created}
