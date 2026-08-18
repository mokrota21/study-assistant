"""Exam pools, колоквиум, and practical exams (PRD §5).

Design commitments worth restating because they are easy to erode:

* **Rubrics are written at creation time, never at grading time.** An item may
  not enter a pool without either a required-elements checklist (theory) or a
  rubric plus reference solution (problems). A model grading its own fresh
  interpretation of a question is the sycophancy trap.
* **Pools are visible to the user.** ``render_pools`` writes them to
  ``exam-pool/*.md`` so an announced колоквиум draws from a known list, exactly
  like the real one.
* **The formulation gate is hard.** More than ``formulation_gate_max_failures``
  failed formulations stops the колоквиум; only formulation credit is kept.
  No proof credit without fundamentals.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path
from typing import Any, Iterable, Optional

from .concepts import get_concept, list_concepts
from .config import get_settings
from .store import connect, init_db, log_event
from .timeutil import now, parse, to_iso

POOLS = ("formulations", "proofs", "problems")


# --- pool accrual --------------------------------------------------------


def add_pool_item(
    subject: str,
    pool: str,
    concept: str,
    prompt: str,
    required_elements: Optional[Iterable[str]] = None,
    reference_solution: Optional[str] = None,
    rubric: Optional[str] = None,
    difficulty: int = 2,
    format: Optional[str] = None,
    source: Optional[str] = None,
) -> dict[str, Any]:
    """Deposit one held-back question. Refuses items without creation-time grading criteria."""
    if pool not in POOLS:
        raise ValueError(f"pool must be one of {POOLS}")
    elements = [str(e) for e in (required_elements or [])]
    if pool in ("formulations", "proofs") and not elements:
        raise ValueError(
            "theory items need required_elements: the binary checklist is written when the question "
            "enters the pool, not when it is graded (§5.5)"
        )
    if pool == "problems" and not (rubric and reference_solution):
        raise ValueError(
            "problem items need both a rubric and a reference_solution, generated now (§5.5). "
            "The rubric predicts the common approach; a verified novel approach still scores full marks."
        )

    init_db()
    node = get_concept(subject, concept)
    with connect() as conn:
        cursor = conn.execute(
            """INSERT INTO pool_items(subject, pool, concept_id, concept_name, prompt, required_elements,
                                      reference_solution, rubric, difficulty, format, source, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                subject,
                pool,
                node["id"] if node else None,
                node["name"] if node else concept,
                prompt,
                json.dumps(elements, ensure_ascii=False),
                reference_solution,
                rubric,
                int(difficulty),
                format,
                source,
                to_iso(now()),
            ),
        )
        item_id = int(cursor.lastrowid)
    return {"id": item_id, "subject": subject, "pool": pool, "concept": concept, "difficulty": difficulty}


def list_pool(
    subject: str, pool: Optional[str] = None, concept: Optional[str] = None, include_retired: bool = False
) -> dict[str, Any]:
    init_db()
    query = "SELECT * FROM pool_items WHERE subject = ?"
    params: list[Any] = [subject]
    if pool:
        query += " AND pool = ?"
        params.append(pool)
    if concept:
        query += " AND concept_name = ?"
        params.append(concept)
    if not include_retired:
        query += " AND retired = 0"
    query += " ORDER BY pool, concept_name, id"
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(query, params)]
    for row in rows:
        row["required_elements"] = json.loads(row["required_elements"])
    counts = {p: sum(1 for r in rows if r["pool"] == p) for p in POOLS}
    return {"subject": subject, "counts": counts, "items": rows, "total": len(rows)}


def render_pools(subject: str) -> dict[str, Any]:
    """Write ``exam-pool/*.md`` from the database so the user can prepare from them (§5.1)."""
    settings = get_settings()
    directory = settings.subject_dir(subject) / "exam-pool"
    directory.mkdir(parents=True, exist_ok=True)
    data = list_pool(subject)
    written = []
    for pool in POOLS:
        items = [i for i in data["items"] if i["pool"] == pool]
        lines = [
            f"# {pool.capitalize()} pool — {subject}",
            "",
            f"_{len(items)} items. Rendered from the harness database on {to_iso(now())[:16]}._",
            "_These are the questions an announced колоквиум/exam can draw from. Prepare against this list._",
            "",
        ]
        by_concept: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            by_concept.setdefault(item["concept_name"], []).append(item)
        for concept in sorted(by_concept):
            lines.append(f"## {concept}")
            lines.append("")
            for item in by_concept[concept]:
                tags = [f"#{item['id']}", f"difficulty {item['difficulty']}"]
                if item["format"]:
                    tags.append(item["format"])
                if item["source"]:
                    tags.append(f"source: {item['source']}")
                if item["used_count"]:
                    tags.append(f"used {item['used_count']}×")
                lines.append(f"- **[{' · '.join(tags)}]** {item['prompt']}")
                if item["required_elements"]:
                    lines.append(
                        "  - required elements: " + "; ".join(item["required_elements"])
                    )
            lines.append("")
        path = directory / f"{pool}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(str(path.relative_to(settings.root)))
    return {"subject": subject, "written": written, "counts": data["counts"]}


# --- triggers ------------------------------------------------------------


def _covered_weeks(subject: str) -> float:
    """Weeks of material accumulated, measured from the first study event on record."""
    with connect() as conn:
        row = conn.execute(
            """SELECT MIN(at) first, MAX(at) last FROM (
                   SELECT at FROM reviews WHERE subject = ?
                   UNION ALL SELECT at FROM practice WHERE subject = ?
               )""",
            (subject, subject),
        ).fetchone()
        last_kolok = conn.execute(
            "SELECT MAX(finished_at) f FROM assessments WHERE subject = ? AND kind = 'kolokvium' "
            "AND status IN ('passed','failed','stopped')",
            (subject,),
        ).fetchone()["f"]
    if not row or not row["first"]:
        return 0.0
    start = parse(last_kolok) if last_kolok else parse(row["first"])
    return max(0.0, (parse(row["last"]) - start).total_seconds() / (7 * 86400))


def kolokvium_check(subject: str) -> dict[str, Any]:
    """Has enough material accumulated to announce a колоквиум? (§5.2)"""
    init_db()
    settings = get_settings().for_subject(subject)
    weeks = _covered_weeks(subject)
    concepts = [c for c in list_concepts(subject) if c["status"] in ("learning", "mastered")]
    provable = [c for c in concepts if c["provable"]]
    pool = list_pool(subject)

    conditions = {
        "weeks_of_material": {
            "have": round(weeks, 1),
            "need": settings.kolokvium_trigger_weeks,
            "ok": weeks >= settings.kolokvium_trigger_weeks,
        },
        "covered_concepts": {
            "have": len(concepts),
            "need": settings.kolokvium_trigger_concepts,
            "ok": len(concepts) >= settings.kolokvium_trigger_concepts,
        },
        "provable_items": {
            "have": len(provable),
            "need": settings.kolokvium_min_provable,
            "ok": len(provable) >= settings.kolokvium_min_provable,
        },
        "pool_ready": {
            "have": pool["counts"],
            "need": {
                "formulations": settings.ticket_formulations * 3,
                "proofs": settings.ticket_proofs_max * 3,
            },
            "ok": pool["counts"]["formulations"] >= settings.ticket_formulations * 3
            and pool["counts"]["proofs"] >= settings.ticket_proofs_max * 3,
        },
    }
    # Either time or concept count may trigger; provable items and pool depth are hard requirements.
    triggered = (
        (conditions["weeks_of_material"]["ok"] or conditions["covered_concepts"]["ok"])
        and conditions["provable_items"]["ok"]
        and conditions["pool_ready"]["ok"]
    )
    return {
        "subject": subject,
        "triggered": triggered,
        "conditions": conditions,
        "action": (
            "Announce the колоквиум: draft the ticket set with draw_ticket, publish the pools with "
            f"render_pools, then schedule it plus {settings.kolokvium_prep_sessions} dedicated "
            "preparation sessions before it (§5.2)."
            if triggered
            else "Not yet. Keep depositing pool items as concepts are covered."
        ),
    }


def exam_check(subject: str) -> dict[str, Any]:
    """Has the problem-idea pool exceeded the exam threshold? (§5.3)"""
    settings = get_settings().for_subject(subject)
    counts = list_pool(subject)["counts"]
    triggered = counts["problems"] >= settings.exam_problem_pool_threshold
    return {
        "subject": subject,
        "triggered": triggered,
        "problems_in_pool": counts["problems"],
        "threshold": settings.exam_problem_pool_threshold,
        "action": (
            "Generate a practical exam covering all or most topics. Interleave it: problems unlabeled and "
            "mixed across sub-skills, so the user must select the method — blocked practice never trains that (§5.3)."
            if triggered
            else "Keep depositing problem ideas."
        ),
    }


# --- tickets -------------------------------------------------------------


def draw_ticket(
    subject: str,
    concepts: Optional[Iterable[str]] = None,
    seed: Optional[int] = None,
    include_problem: bool = True,
) -> dict[str, Any]:
    """Draw one колоквиум ticket: 3 formulations + 1-2 proofs + optionally 1 problem (§5.2)."""
    settings = get_settings().for_subject(subject)
    rng = random.Random(seed)
    data = list_pool(subject)
    scope = set(concepts or [])

    def pick(pool: str, count: int) -> list[dict[str, Any]]:
        candidates = [i for i in data["items"] if i["pool"] == pool and (not scope or i["concept_name"] in scope)]
        if not candidates:
            return []
        # Prefer unused items, then least-recently used; spreads the pool over successive tickets.
        candidates.sort(key=lambda i: (i["used_count"], i["last_used_at"] or ""))
        head = candidates[: max(count * 3, count)]
        rng.shuffle(head)
        return head[:count]

    proofs_n = rng.randint(settings.ticket_proofs_min, settings.ticket_proofs_max)
    ticket = {
        "formulations": pick("formulations", settings.ticket_formulations),
        "proofs": pick("proofs", proofs_n),
        "problems": pick("problems", settings.ticket_problems) if include_problem else [],
    }
    shortfall = {
        section: needed - len(items)
        for section, needed, items in (
            ("formulations", settings.ticket_formulations, ticket["formulations"]),
            ("proofs", proofs_n, ticket["proofs"]),
        )
        if needed - len(items) > 0
    }
    return {
        "subject": subject,
        "ticket": {
            section: [
                {
                    "id": i["id"],
                    "concept": i["concept_name"],
                    "prompt": i["prompt"],
                    "required_elements": i["required_elements"],
                    "difficulty": i["difficulty"],
                    "source": i["source"],
                }
                for i in items
            ]
            for section, items in ticket.items()
        },
        "shortfall": shortfall or None,
        "gate": (
            f"Formulation gate: more than {settings.formulation_gate_max_failures} failed formulation(s) "
            "stops the колоквиум. Only formulation credit is kept — no proof credit without fundamentals."
        ),
        "format": (
            "Conversational. Ask доп вопросы on weak spots — probing follow-ups are the anti-memorization "
            "mechanism and reveal understanding better than a written answer."
        ),
    }


def announce_assessment(
    subject: str,
    kind: str = "kolokvium",
    scheduled_at: Optional[str] = None,
    ticket: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Record an announced колоквиум/exam and mark its pool items as drawn."""
    init_db()
    settings = get_settings().for_subject(subject)
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO assessments(subject, kind, status, announced_at, scheduled_at, ticket) "
            "VALUES(?,?,'announced',?,?,?)",
            (
                subject,
                kind,
                to_iso(now()),
                to_iso(parse(scheduled_at)) if scheduled_at else None,
                json.dumps(ticket or {}, ensure_ascii=False),
            ),
        )
        assessment_id = int(cursor.lastrowid)
    log_event(subject, f"{kind}_announced", {"id": assessment_id, "scheduled_at": scheduled_at})
    return {
        "id": assessment_id,
        "subject": subject,
        "kind": kind,
        "scheduled_at": scheduled_at,
        "next_steps": [
            "Publish the pools (render_pools) so the user prepares against a known list.",
            f"Schedule {settings.kolokvium_prep_sessions} dedicated preparation blocks before the date.",
            "Do not draw the final ticket until the session starts.",
        ],
    }


def record_assessment_result(
    assessment_id: int,
    result: dict[str, Any],
    score: Optional[float] = None,
    status: str = "passed",
    record_path: Optional[str] = None,
) -> dict[str, Any]:
    """Persist a graded assessment and fan out its consequences (remediation, mastery)."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
        if row is None:
            raise ValueError(f"no assessment #{assessment_id}")
        conn.execute(
            "UPDATE assessments SET status=?, finished_at=?, result=?, score=?, record_path=? WHERE id=?",
            (status, to_iso(now()), json.dumps(result, ensure_ascii=False), score, record_path, assessment_id),
        )
        used_ids = [
            item["id"]
            for section in json.loads(row["ticket"] or "{}").get("ticket", {}).values()
            if isinstance(section, list)
            for item in section
            if isinstance(item, dict) and "id" in item
        ]
        for item_id in used_ids:
            conn.execute(
                "UPDATE pool_items SET used_count = used_count + 1, last_used_at = ? WHERE id = ?",
                (to_iso(now()), item_id),
            )
    log_event(row["subject"], f"{row['kind']}_graded", {"id": assessment_id, "score": score, "status": status})

    from .mastery import weak_concepts

    return {
        "id": assessment_id,
        "subject": row["subject"],
        "kind": row["kind"],
        "status": status,
        "score": score,
        "record_path": record_path,
        "remediation": weak_concepts(row["subject"]),
    }


def grade_formulation_gate(subject: str, verdicts: list[bool]) -> dict[str, Any]:
    """Apply the hard formulation gate to a list of per-formulation pass/fail verdicts (§5.2)."""
    settings = get_settings().for_subject(subject)
    failures = sum(1 for v in verdicts if not v)
    stopped = failures > settings.formulation_gate_max_failures
    return {
        "failures": failures,
        "allowed_failures": settings.formulation_gate_max_failures,
        "gate_passed": not stopped,
        "action": (
            "STOP the колоквиум now. Keep only formulation credit; award no proof credit. "
            "Schedule remediation on the failed formulations."
            if stopped
            else "Gate passed — continue to the proof questions."
        ),
    }


def schedule_assessment(
    subject: str, kind: str = "kolokvium", days_ahead: int = 7, duration_minutes: int = 90
) -> dict[str, Any]:
    """Place the assessment block plus its dedicated preparation sessions (§5.2)."""
    from .scheduler import place_block, propose_schedule

    settings = get_settings().for_subject(subject)
    target = now() + dt.timedelta(days=days_ahead)
    prep = propose_schedule(
        subject,
        count=settings.kolokvium_prep_sessions,
        kind="prep",
        topics=[f"{kind} preparation"] * settings.kolokvium_prep_sessions,
        start=to_iso(now() + dt.timedelta(hours=12)),
        end=to_iso(target),
        commit=True,
    )
    exam_block = place_block(
        subject=subject,
        start=to_iso(target.replace(minute=0, second=0, microsecond=0)),
        duration_minutes=duration_minutes,
        kind=kind if kind in ("kolokvium", "exam") else "exam",
        topic=f"{kind}",
    )
    return {"assessment_block": exam_block, "preparation_blocks": prep["blocks"], "warning": prep.get("warning")}


def subject_paths(subject: str) -> dict[str, str]:
    """Canonical file layout for a subject (§2). Returns paths relative to the harness root."""
    settings = get_settings()
    base = settings.subject_dir(subject)
    layout = {
        "root": base,
        "plan": base / "plan.md",
        "materials": base / "materials",
        "lessons": base / "lessons",
        "notes": base / "notes",
        "covered": base / "covered.md",
        "exam_pool": base / "exam-pool",
        "results": base / "results",
        "config": base / "config.json",
    }
    return {k: str(Path(v).relative_to(settings.root)).replace("\\", "/") for k, v in layout.items()}
