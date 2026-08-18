"""Mastery gates (PRD §3.5) and the performance-vs-learning instrumentation (§8).

The gate is deliberately awkward to satisfy. Four conditions must hold at once:

1. **time-on-task** ≥ ``mastery_min_minutes``
2. **varied correct reps** ≥ ``mastery_min_reps`` — counted by *distinct variant
   tag*, so twenty repetitions of the same exercise count once
3. **distributed** across ≥ ``mastery_min_distinct_days`` days spanning ≥
   ``mastery_min_span_days`` — massed overlearning decays, spaced reps persist
4. **hint rate** ≤ ``mastery_max_hint_rate`` — leaning on the stuck hatch is
   exactly the crutch effect the whole design exists to prevent

Mastery is provisional: :func:`run_delayed_rechecks` revokes it when a
weeks-later re-check fails.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from .concepts import get_concept, list_concepts, require_concept_id, set_status
from .config import get_settings
from .store import connect, init_db, log_event
from .timeutil import local_date, now, parse, to_iso

# Reps counted toward mastery: assessments count, trickle-down credit never does.
COUNTING_KINDS = ("in_session", "delayed_recheck", "exam", "kolokvium", "remediation")


def _concept_evidence(conn, cid: int) -> dict[str, Any]:
    minutes = conn.execute(
        "SELECT COALESCE(SUM(minutes), 0) AS m FROM practice WHERE concept_id = ?", (cid,)
    ).fetchone()["m"]
    placeholders = ",".join("?" * len(COUNTING_KINDS))
    reviews = [
        dict(r)
        for r in conn.execute(
            f"""SELECT at, correct, rating, variant, hints_used, kind, score
                FROM reviews WHERE concept_id = ? AND kind IN ({placeholders})
                ORDER BY at""",
            (cid, *COUNTING_KINDS),
        )
    ]
    hints = conn.execute(
        "SELECT COUNT(*) AS n FROM hints WHERE concept_id = ?", (cid,)
    ).fetchone()["n"]
    return {"minutes": float(minutes or 0), "reviews": reviews, "hints": int(hints)}


def mastery_status(subject: str, concept: str) -> dict[str, Any]:
    """Evidence and remaining requirements for one concept. Read-only."""
    init_db()
    settings = get_settings().for_subject(subject)
    node = get_concept(subject, concept)
    if node is None:
        raise ValueError(f"concept {concept!r} not registered for {subject!r}")

    with connect() as conn:
        cid = int(node["id"])
        ev = _concept_evidence(conn, cid)

    correct = [r for r in ev["reviews"] if r["correct"]]
    variants = {(r["variant"] or f"untagged-{i}") for i, r in enumerate(correct)}
    days = {local_date(parse(r["at"])) for r in correct}
    span_days = 0.0
    if correct:
        first, last = parse(correct[0]["at"]), parse(correct[-1]["at"])
        span_days = (last - first).total_seconds() / 86400.0
    total_reps = len(ev["reviews"])
    hint_rate = (ev["hints"] / total_reps) if total_reps else 0.0

    checks = {
        "time_on_task": {
            "have": round(ev["minutes"], 1),
            "need": settings.mastery_min_minutes,
            "ok": ev["minutes"] >= settings.mastery_min_minutes,
        },
        "varied_reps": {
            "have": len(variants),
            "need": settings.mastery_min_reps,
            "ok": len(variants) >= settings.mastery_min_reps,
            "note": "counted by distinct variant tag — same exercise repeated counts once",
        },
        "distinct_days": {
            "have": len(days),
            "need": settings.mastery_min_distinct_days,
            "ok": len(days) >= settings.mastery_min_distinct_days,
        },
        "span_days": {
            "have": round(span_days, 1),
            "need": settings.mastery_min_span_days,
            "ok": span_days >= settings.mastery_min_span_days,
        },
        "hint_rate": {
            "have": round(hint_rate, 2),
            "max": settings.mastery_max_hint_rate,
            "ok": hint_rate <= settings.mastery_max_hint_rate,
            "note": "frequent stuck-hatch use blocks mastery and schedules more drilling (§6)",
        },
    }
    remaining = [name for name, c in checks.items() if not c["ok"]]
    return {
        "subject": subject,
        "concept": node["name"],
        "status": node["status"],
        "eligible": not remaining,
        "checks": checks,
        "remaining": remaining,
        "attempts": total_reps,
        "correct": len(correct),
        "accuracy": round(len(correct) / total_reps, 2) if total_reps else None,
        "hints": ev["hints"],
    }


def evaluate_mastery(subject: str, concept: str, promote: bool = True) -> dict[str, Any]:
    """Check the gate and promote to ``mastered`` when every condition holds."""
    status = mastery_status(subject, concept)
    if promote and status["eligible"] and status["status"] not in ("mastered", "excluded"):
        set_status(subject, concept, "mastered")
        status["status"] = "mastered"
        status["promoted"] = True
        log_event(subject, "mastery_granted", {"concept": concept, "checks": status["checks"]})
        status["next"] = (
            "Mastery is provisional. A delayed re-check is due in "
            f"{get_settings().for_subject(subject).mastery_recheck_days} days; failing it revokes mastery."
        )
    else:
        status["promoted"] = False
    return status


def revoke_mastery(subject: str, concept: str, reason: str = "failed delayed re-check") -> dict[str, Any]:
    """Provisional mastery lost (§3.5, §8): status drops and the card returns to drilling."""
    node = set_status(subject, concept, "revoked")
    with connect() as conn:
        cid = require_concept_id(conn, subject, concept)
        conn.execute("UPDATE cards SET due = ? WHERE concept_id = ?", (to_iso(now()), cid))
    log_event(subject, "mastery_revoked", {"concept": concept, "reason": reason})
    return {
        "subject": subject,
        "concept": node["name"],
        "status": "revoked",
        "reason": reason,
        "action": "Concept is due immediately and must be re-drilled before dependent concepts advance.",
    }


def due_rechecks(subject: Optional[str] = None) -> dict[str, Any]:
    """Concepts mastered long enough ago that a delayed re-check is owed (§8).

    A delayed re-check is the *learning* signal. In-session correctness is the
    *performance* signal and is systematically misleading — never let the second
    stand in for the first.
    """
    init_db()
    settings = get_settings().for_subject(subject)
    cutoff = to_iso(now() - dt.timedelta(days=settings.mastery_recheck_days))
    query = (
        "SELECT c.subject, c.name, c.mastered_at, "
        "  (SELECT MAX(at) FROM reviews r WHERE r.concept_id = c.id AND r.kind = 'delayed_recheck') AS last_recheck "
        "FROM concepts c WHERE c.status = 'mastered' AND c.mastered_at IS NOT NULL AND c.mastered_at <= ?"
    )
    params: list[Any] = [cutoff]
    if subject:
        query += " AND c.subject = ?"
        params.append(subject)
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(query, params)]
    owed = [r for r in rows if not r["last_recheck"] or r["last_recheck"] <= cutoff]
    return {
        "as_of": to_iso(now()),
        "recheck_after_days": settings.mastery_recheck_days,
        "items": [
            {
                "subject": r["subject"],
                "concept": r["name"],
                "mastered_at": r["mastered_at"],
                "last_recheck": r["last_recheck"],
                "instruction": "Fresh unassisted exercise. Grade with kind='delayed_recheck'. A failure revokes mastery.",
            }
            for r in owed
        ],
        "count": len(owed),
    }


def record_practice(
    subject: str,
    concept: str,
    minutes: float,
    at: Optional[str] = None,
    block_id: Optional[int] = None,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """Log time-on-task. Self-report is trusted (§7) — verification happens via retrieval, not surveillance."""
    init_db()
    stamp = to_iso(parse(at) if at else now())
    with connect() as conn:
        cid = require_concept_id(conn, subject, concept)
        conn.execute(
            "INSERT INTO practice(concept_id, subject, minutes, at, block_id, note) VALUES(?,?,?,?,?,?)",
            (cid, subject, float(minutes), stamp, block_id, note),
        )
    return mastery_status(subject, concept)


def record_hint(
    subject: str,
    concept: str,
    exercise_ref: Optional[str] = None,
    hint_index: int = 1,
    hint_text: Optional[str] = None,
    block_id: Optional[int] = None,
) -> dict[str, Any]:
    """Log a stuck-hatch invocation and report whether the budget is spent (§6)."""
    init_db()
    settings = get_settings().for_subject(subject)
    with connect() as conn:
        cid = require_concept_id(conn, subject, concept)
        conn.execute(
            "INSERT INTO hints(concept_id, subject, at, exercise_ref, hint_index, hint_text, block_id) "
            "VALUES(?,?,?,?,?,?,?)",
            (cid, subject, to_iso(now()), exercise_ref, hint_index, hint_text, block_id),
        )
        used_here = conn.execute(
            "SELECT COUNT(*) AS n FROM hints WHERE concept_id = ? AND exercise_ref IS ?",
            (cid, exercise_ref),
        ).fetchone()["n"]
    status = mastery_status(subject, concept)
    return {
        "subject": subject,
        "concept": concept,
        "hints_used_on_this_exercise": used_here,
        "budget": settings.hints_per_exercise,
        "budget_exhausted": used_here >= settings.hints_per_exercise,
        "rule": "One hint, never the answer. When the budget is spent, the exercise is scored as-is and re-drilled later.",
        "hint_rate": status["checks"]["hint_rate"],
        "mastery_blocked_by_hints": not status["checks"]["hint_rate"]["ok"],
    }


def record_grading_check(
    subject: str,
    ai_score: float,
    user_score: float,
    item_ref: Optional[str] = None,
    tolerance: float = 0.15,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """User spot-check of an AI grade. Drives the §5.5 auto-grading pull-out threshold."""
    init_db()
    settings = get_settings().for_subject(subject)
    agreed = abs(ai_score - user_score) <= tolerance
    with connect() as conn:
        conn.execute(
            "INSERT INTO grading_checks(subject, at, item_ref, ai_score, user_score, agreed, note) "
            "VALUES(?,?,?,?,?,?,?)",
            (subject, to_iso(now()), item_ref, ai_score, user_score, int(agreed), note),
        )
        row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(agreed),0) AS a FROM grading_checks WHERE subject = ?",
            (subject,),
        ).fetchone()
    rate = row["a"] / row["n"] if row["n"] else None
    pulled = rate is not None and row["n"] >= 10 and rate < settings.grading_agreement_pullout
    if pulled:
        log_event(subject, "autograding_pullout", {"agreement": rate, "checks": row["n"]})
    return {
        "subject": subject,
        "agreed": agreed,
        "checks": row["n"],
        "agreement_rate": round(rate, 3) if rate is not None else None,
        "threshold": settings.grading_agreement_pullout,
        "auto_grading_trusted": not pulled,
        "action": (
            "Agreement is below threshold: pull open-ended auto-grading from the mastery gate and "
            "restrict it to reference-matchable items (§5.5)."
            if pulled
            else "Auto-grading remains inside the mastery gate."
        ),
    }


def health_metrics(subject: Optional[str] = None) -> dict[str, Any]:
    """The harness's primary health metric (§8): performance vs. learning, tracked apart."""
    init_db()
    where, params = "", []
    if subject:
        where, params = " WHERE subject = ?", [subject]

    with connect() as conn:
        by_kind = {
            r["kind"]: {"n": r["n"], "correct": r["c"]}
            for r in conn.execute(
                f"SELECT kind, COUNT(*) n, COALESCE(SUM(correct),0) c FROM reviews{where} GROUP BY kind",
                params,
            )
        }
        grading = conn.execute(
            f"SELECT COUNT(*) n, COALESCE(SUM(agreed),0) a FROM grading_checks{where}", params
        ).fetchone()
        hint_row = conn.execute(
            f"SELECT COUNT(*) n FROM hints{where}", params
        ).fetchone()
        revoked = conn.execute(
            "SELECT COUNT(*) n FROM concepts WHERE status='revoked'"
            + (" AND subject = ?" if subject else ""),
            params,
        ).fetchone()["n"]
        mastered = conn.execute(
            "SELECT COUNT(*) n FROM concepts WHERE status='mastered'"
            + (" AND subject = ?" if subject else ""),
            params,
        ).fetchone()["n"]

    def rate(kind: str) -> Optional[float]:
        d = by_kind.get(kind)
        return round(d["correct"] / d["n"], 3) if d and d["n"] else None

    performance = rate("in_session")
    learning = rate("delayed_recheck")
    gap = round(performance - learning, 3) if performance is not None and learning is not None else None
    settings = get_settings().for_subject(subject)
    agreement = round(grading["a"] / grading["n"], 3) if grading["n"] else None

    verdict = "Not enough delayed re-checks yet — learning signal unavailable."
    if gap is not None:
        if gap > 0.25:
            verdict = (
                "Large performance-learning gap: the gate is passing concepts that do not survive. "
                "Tighten it — more consecutive correct reps, longer initial spacing (§8)."
            )
        elif gap > 0.12:
            verdict = "Moderate gap. Watch it; consider raising mastery_min_span_days."
        else:
            verdict = "Gate looks honest — delayed re-checks track in-session performance."

    return {
        "subject": subject,
        "performance_in_session": performance,
        "learning_delayed_recheck": learning,
        "gap": gap,
        "verdict": verdict,
        "by_kind": by_kind,
        "hints_logged": hint_row["n"],
        "concepts_mastered": mastered,
        "mastery_revoked": revoked,
        "grading_agreement": agreement,
        "grading_agreement_threshold": settings.grading_agreement_pullout,
        "auto_grading_trusted": agreement is None
        or grading["n"] < 10
        or agreement >= settings.grading_agreement_pullout,
    }


def weak_concepts(subject: str, threshold: Optional[float] = None, min_attempts: int = 2) -> dict[str, Any]:
    """Concepts scoring below the remediation threshold — §5.4 replaces surprise exams with these."""
    init_db()
    settings = get_settings().for_subject(subject)
    limit = threshold if threshold is not None else settings.remediation_threshold
    with connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """SELECT c.name, COUNT(r.id) n, COALESCE(AVG(r.correct),0) acc,
                          COALESCE(AVG(COALESCE(r.score, r.correct)),0) avg_score,
                          (SELECT COUNT(*) FROM hints h WHERE h.concept_id = c.id) hints
                   FROM concepts c JOIN reviews r ON r.concept_id = c.id
                   WHERE c.subject = ? GROUP BY c.id HAVING n >= ? ORDER BY avg_score ASC""",
                (subject, min_attempts),
            )
        ]
    weak = [r for r in rows if r["avg_score"] < limit]
    return {
        "subject": subject,
        "threshold": limit,
        "weak": [
            {
                "concept": r["name"],
                "attempts": r["n"],
                "avg_score": round(r["avg_score"], 2),
                "accuracy": round(r["acc"], 2),
                "hints": r["hints"],
            }
            for r in weak
        ],
        "remediation_needed": bool(weak),
        "action": (
            "Schedule a supervised-practice session on these concepts (kind='remediation'). "
            "No surprise exams — the stakes a self-learner lacks make them pointless (§5.4)."
            if weak
            else "No concept is below the remediation threshold."
        ),
    }


def subject_overview(subject: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for c in list_concepts(subject):
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return {"subject": subject, "concepts_by_status": counts, "health": health_metrics(subject)}
