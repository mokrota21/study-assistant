"""MCP server for the Learning Harness.

Scope discipline (PRD §2): this server owns **only what needs computation or
dynamic state** — the scheduler, the FSRS queue, the block clock, mastery
arithmetic, and the countable half of the exam pools. Lessons, explanations,
notes and plans are files the agent writes directly; none of that belongs here.

Transport is stdio, so Claude Code starts and stops the process with the
session. There is no daemon to run and nothing to keep alive between sessions.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp.server import MCPServer

from . import assessment, blockclock, concepts, mastery, scheduler, srs, subjects
from .calendar import get_calendar
from .config import get_settings, reload_settings
from .store import init_db
from .timeutil import now, to_iso

mcp = MCPServer(
    name="learning-harness",
    version="0.1.0",
    instructions=(
        "Scheduler, spaced-repetition queue, block clock and mastery gates for the Learning Harness. "
        "Files own prose (plans, lessons, notes, materials); these tools own computed state. "
        "Never pre-allocate reviews into future blocks — fetch review_queue live at block start."
    ),
)


# --- subjects ------------------------------------------------------------


@mcp.tool()
def create_subject(
    subject: str,
    mode: str = "exploratory",
    sources: Optional[list[str]] = None,
    domain: Optional[str] = None,
) -> dict[str, Any]:
    """Scaffold a subject folder (plan, materials, lessons, notes, exam-pool, results).

    mode='scoped' — textbook(s) given. The learner does not know this material yet; the
    book is the authority and the contract is "understands this book, not under, not over".
    Scope is not negotiated with them.

    mode='exploratory' — no fixed source. The learner's goal is the seed, not the boundary;
    a learner cannot audit their own gaps, so the agent researches what the goal requires,
    proposes the frontier including unmentioned prerequisites, and leads the negotiation.
    """
    return subjects.scaffold_subject(subject, mode=mode, sources=sources, domain=domain)


@mcp.tool()
def list_subjects() -> dict[str, Any]:
    """All subjects known to the harness, with their curriculum mode and sources."""
    return subjects.list_subjects()


@mcp.tool()
def subject_layout(subject: str) -> dict[str, Any]:
    """Canonical file paths for a subject, relative to the harness root."""
    return assessment.subject_paths(subject)


@mcp.tool()
def log_covered(
    subject: str, concepts: list[str], summary: str, block_id: Optional[int] = None
) -> dict[str, Any]:
    """Append a block's coverage to covered.md — the колоквиум trigger source."""
    return subjects.append_covered(subject, concepts, summary, block_id)


@mcp.tool()
def notes_skeleton(subject: str, topic: str = "", block: str = "") -> dict[str, Any]:
    """Path and skeleton for today's notes file. Write the content yourself with the file tools."""
    return subjects.notes_template(subject, topic, block)


# --- concept graph -------------------------------------------------------


@mcp.tool()
def register_concepts(subject: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Sync the concept graph from plan.md into harness state. Idempotent upsert.

    Each item: {name, prereqs?, status?, kind?, provable?, tags?, source_ref?}.
    Call this after every edit to plan.md's concept table.
    """
    return concepts.register_concepts(subject, items)


@mcp.tool()
def list_concept_graph(subject: str, status: Optional[str] = None) -> dict[str, Any]:
    """The registered concept graph, optionally filtered by status."""
    return {"subject": subject, "concepts": concepts.list_concepts(subject, status)}


@mcp.tool()
def set_concept_status(subject: str, concept: str, status: str) -> dict[str, Any]:
    """Set a concept's status: planned | frontier | learning | mastered | revoked | excluded."""
    return concepts.set_status(subject, concept, status)


@mcp.tool()
def check_gate(subject: str, concept: str) -> dict[str, Any]:
    """May the user start this concept? Prerequisites are strictly gated (§3.5).

    Call this before introducing any new concept. A blocked verdict means drilling
    the prerequisite first — not explaining the new concept anyway.
    """
    return concepts.gate_check(subject, concept)


@mcp.tool()
def learning_frontier(subject: str) -> dict[str, Any]:
    """What is learnable right now: unmastered concepts whose prerequisites are all mastered."""
    return concepts.frontier(subject)


# --- spaced repetition ---------------------------------------------------


@mcp.tool()
def seed_cards(subject: str) -> dict[str, Any]:
    """Give every registered concept an FSRS card. Safe to call repeatedly."""
    return srs.seed_missing_cards(subject)


@mcp.tool()
def review_queue(
    subject: Optional[str] = None, limit: Optional[int] = None, include_ahead: bool = True
) -> dict[str, Any]:
    """The live review queue for right now: overdue first, then due, then ahead-of-schedule.

    Call this at the START of every block. Each item means "generate a fresh
    free-recall exercise on this concept" — never a flashcard, never a repeat of a
    previous exercise. Overdue items are mandatory before new material.
    """
    return srs.due_queue(subject, limit, include_ahead=include_ahead)


@mcp.tool()
def grade_review(
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
) -> dict[str, Any]:
    """Record a graded retrieval attempt: advances FSRS, logs the rep, re-checks the mastery gate.

    Pass rating (1=Again 2=Hard 3=Good 4=Easy) or score (0..1). Hints cap the rating at Hard.
    `variant` is the exercise-variation tag — mastery counts distinct variants, so
    always pass one. `kind='delayed_recheck'` marks a weeks-later re-check, which is
    the learning signal in §8; leave it 'in_session' for normal reviews.
    """
    return srs.grade(
        subject=subject,
        concept=concept,
        rating=rating,
        score=score,
        correct=correct,
        kind=kind,
        variant=variant,
        exercise_ref=exercise_ref,
        hints_used=hints_used,
        duration_s=duration_s,
        minutes_on_task=minutes_on_task,
        block_id=block_id,
        note=note,
    )


@mcp.tool()
def review_forecast(subject: Optional[str] = None, days: int = 14) -> dict[str, Any]:
    """Reviews coming due per day. The schedule reserves capacity from this — never slots."""
    return srs.forecast(subject, days)


@mcp.tool()
def card_overview(subject: str) -> dict[str, Any]:
    """Per-concept card state: due date, stability, reps, lapses."""
    return {"subject": subject, "cards": srs.card_summary(subject)}


@mcp.tool()
def suspend_concept(subject: str, concept: str, suspended: bool = True) -> dict[str, Any]:
    """Take a concept out of (or back into) the review rotation."""
    return srs.set_suspended(subject, concept, suspended)


# --- mastery and instrumentation ----------------------------------------


@mcp.tool()
def mastery_check(subject: str, concept: str) -> dict[str, Any]:
    """Evidence and remaining requirements for one concept's mastery gate. Read-only."""
    return mastery.mastery_status(subject, concept)


@mcp.tool()
def record_practice(
    subject: str,
    concept: str,
    minutes: float,
    block_id: Optional[int] = None,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """Log time-on-task for a concept — half of the dual mastery threshold.

    Self-report is trusted; verification happens through retrieval and exams, not surveillance.
    """
    return mastery.record_practice(subject, concept, minutes, block_id=block_id, note=note)


@mcp.tool()
def stuck_hatch(
    subject: str,
    concept: str,
    exercise_ref: Optional[str] = None,
    hint_text: Optional[str] = None,
    block_id: Optional[int] = None,
) -> dict[str, Any]:
    """Log a stuck-hatch invocation before giving the ONE hint.

    Rules: one hint per exercise, never the answer, grounded in the reference
    solution. Hint use is logged against the concept, caps the FSRS rating at Hard,
    and blocks mastery when it gets frequent. Call this BEFORE you say the hint.
    """
    return mastery.record_hint(subject, concept, exercise_ref=exercise_ref, hint_text=hint_text, block_id=block_id)


@mcp.tool()
def revoke_mastery(subject: str, concept: str, reason: str = "failed delayed re-check") -> dict[str, Any]:
    """Revoke provisional mastery and make the concept due immediately."""
    return mastery.revoke_mastery(subject, concept, reason)


@mcp.tool()
def delayed_rechecks(subject: Optional[str] = None) -> dict[str, Any]:
    """Mastered concepts owed a weeks-later re-check — the learning signal of §8.

    Fold these into review segments. Grade them with kind='delayed_recheck'; a
    failure revokes mastery and reschedules drilling.
    """
    return mastery.due_rechecks(subject)


@mcp.tool()
def remediation_check(subject: str, threshold: Optional[float] = None) -> dict[str, Any]:
    """Concepts below the remediation threshold. §5.4 replaces surprise exams with these sessions."""
    return mastery.weak_concepts(subject, threshold)


@mcp.tool()
def harness_health(subject: Optional[str] = None) -> dict[str, Any]:
    """Performance vs. learning (§8), grading agreement, hint load, revocations.

    The gap between in-session correctness and delayed re-check pass rate is the
    primary health metric. A large gap means the mastery gate is too loose.
    """
    return mastery.health_metrics(subject)


@mcp.tool()
def log_grading_spotcheck(
    subject: str,
    ai_score: float,
    user_score: float,
    item_ref: Optional[str] = None,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """Record a user spot-check of an AI grade. Drives the auto-grading pull-out threshold (§5.5)."""
    return mastery.record_grading_check(subject, ai_score, user_score, item_ref=item_ref, note=note)


# --- calendar and scheduling --------------------------------------------


@mcp.tool()
def add_commitment(
    title: str,
    weekdays: Optional[list[str]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    from_date: Optional[str] = None,
    until_date: Optional[str] = None,
) -> dict[str, Any]:
    """Block out non-study time. Recurring: weekdays + start_time/end_time (HH:MM).
    One-off: start + end as ISO timestamps."""
    return get_calendar().add_commitment(
        title=title,
        weekdays=weekdays,
        start_time=start_time,
        end_time=end_time,
        start=start,
        end=end,
        from_date=from_date,
        until_date=until_date,
    )


@mcp.tool()
def list_commitments() -> dict[str, Any]:
    """All non-study commitments in the calendar store."""
    return {"commitments": get_calendar().list_commitments()}


@mcp.tool()
def remove_commitment(commitment_id: str) -> dict[str, Any]:
    """Delete a commitment by id."""
    return get_calendar().remove_commitment(commitment_id)


@mcp.tool()
def available_windows(
    start: Optional[str] = None, end: Optional[str] = None, min_minutes: Optional[int] = None
) -> dict[str, Any]:
    """Free windows inside study hours, minus commitments and already-placed blocks."""
    return scheduler.free_windows(start, end, min_minutes)


@mcp.tool()
def propose_schedule(
    subject: str,
    count: int = 5,
    topics: Optional[list[str]] = None,
    kind: str = "study",
    duration_minutes: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    commit: bool = False,
) -> dict[str, Any]:
    """Propose (commit=False) or place (commit=True) study blocks over the horizon.

    Windows are re-indexed after every placement, and placement is spread across
    days first: two sessions on two days beat one double session. Keep the plan
    vague past a few days — real pace is unpredictable.
    """
    return scheduler.propose_schedule(
        subject, count, topics, kind, duration_minutes, start, end, commit
    )


@mcp.tool()
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
    return scheduler.place_block(subject, start, end, duration_minutes, kind, topic, lesson_ref)


@mcp.tool()
def list_blocks(
    subject: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    """Scheduled blocks in a range, with the next upcoming one flagged."""
    return scheduler.list_blocks(subject, start, end, status)


@mcp.tool()
def update_block(
    block_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
    topic: Optional[str] = None,
    lesson_ref: Optional[str] = None,
    notes_path: Optional[str] = None,
) -> dict[str, Any]:
    """Reschedule, retopic, or close a block (status: planned|active|done|skipped|cancelled)."""
    return scheduler.update_block(block_id, start, end, status, topic, lesson_ref, notes_path)


@mcp.tool()
def agenda(subject: Optional[str] = None, days: int = 7) -> dict[str, Any]:
    """Upcoming blocks plus the review load each day will have to absorb."""
    return scheduler.agenda(subject, days)


# --- block clock ---------------------------------------------------------


@mcp.tool()
def start_block(
    subject: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    kind: str = "study",
    topic: Optional[str] = None,
    block_id: Optional[int] = None,
    lesson_ref: Optional[str] = None,
    solo_mode: Optional[bool] = None,
) -> dict[str, Any]:
    """Start the block clock: arms the hooks' time injection and the OS notification timer.

    Call this at the beginning of every study session. Then fetch review_queue —
    review segment first, new material second.
    """
    return blockclock.start_block(
        subject=subject,
        duration_minutes=duration_minutes,
        kind=kind,
        topic=topic,
        block_id=block_id,
        lesson_ref=lesson_ref,
        solo_mode=solo_mode,
    )


@mcp.tool()
def block_status() -> dict[str, Any]:
    """Elapsed/remaining time, current segment, solo-mode flag, and any active warnings."""
    return blockclock.status()


@mcp.tool()
def set_segment(segment: str) -> dict[str, Any]:
    """Switch segment: review | new_material | practice | assessment | wrapup | break."""
    return blockclock.set_segment(segment)


@mcp.tool()
def set_solo_mode(enabled: bool) -> dict[str, Any]:
    """Turn solo mode on/off. On: no solutions, no corrections, one hint per exercise via stuck_hatch."""
    return blockclock.set_solo_mode(enabled)


@mcp.tool()
def pause_block(reason: Optional[str] = None) -> dict[str, Any]:
    """Pause the block clock (interruption). Paused time does not count toward the block."""
    return blockclock.pause_block(reason)


@mcp.tool()
def resume_block() -> dict[str, Any]:
    """Resume after a pause."""
    return blockclock.resume_block()


@mcp.tool()
def extend_block(minutes: int) -> dict[str, Any]:
    """Extend the running block. Use sparingly — the rhythm exists for a reason."""
    return blockclock.extend_block(minutes)


@mcp.tool()
def end_block(
    notes_path: Optional[str] = None, summary: Optional[str] = None
) -> dict[str, Any]:
    """Close the block and return the wrap-up checklist (notes, covered.md, pool deposits, next-lesson prep)."""
    return blockclock.end_block(notes_path, summary)


@mcp.tool()
def clear_block_state() -> dict[str, Any]:
    """Escape hatch for a stale block state after a crash or forced restart."""
    return blockclock.clear_state()


# --- exam pools and assessment ------------------------------------------


@mcp.tool()
def deposit_pool_item(
    subject: str,
    pool: str,
    concept: str,
    prompt: str,
    required_elements: Optional[list[str]] = None,
    reference_solution: Optional[str] = None,
    rubric: Optional[str] = None,
    difficulty: int = 2,
    format: Optional[str] = None,
    source: Optional[str] = None,
) -> dict[str, Any]:
    """Deposit a held-back question into a pool: formulations | proofs | problems.

    Grading criteria are written NOW, not at grading time. Theory items require
    required_elements (a binary checklist); problems require both a rubric and a
    reference_solution. Prefer real problems from the source book over generated ones —
    pass `source` when they come from one.
    """
    return assessment.add_pool_item(
        subject=subject,
        pool=pool,
        concept=concept,
        prompt=prompt,
        required_elements=required_elements,
        reference_solution=reference_solution,
        rubric=rubric,
        difficulty=difficulty,
        format=format,
        source=source,
    )


@mcp.tool()
def list_pool_items(
    subject: str, pool: Optional[str] = None, concept: Optional[str] = None
) -> dict[str, Any]:
    """Pool contents with counts per pool."""
    return assessment.list_pool(subject, pool, concept)


@mcp.tool()
def publish_pools(subject: str) -> dict[str, Any]:
    """Render exam-pool/*.md from the database so the user can prepare from a known list."""
    return assessment.render_pools(subject)


@mcp.tool()
def kolokvium_check(subject: str) -> dict[str, Any]:
    """Has enough material accumulated to announce a колоквиум? (~6-8 weeks, §5.2)"""
    return assessment.kolokvium_check(subject)


@mcp.tool()
def exam_check(subject: str) -> dict[str, Any]:
    """Has the problem pool crossed the practical-exam threshold? (§5.3)"""
    return assessment.exam_check(subject)


@mcp.tool()
def draw_ticket(
    subject: str,
    concepts: Optional[list[str]] = None,
    seed: Optional[int] = None,
    include_problem: bool = True,
) -> dict[str, Any]:
    """Draw a колоквиум ticket: 3 formulations + 1-2 proofs + optionally 1 problem, from the published pools."""
    return assessment.draw_ticket(subject, concepts, seed, include_problem)


@mcp.tool()
def formulation_gate(subject: str, verdicts: list[bool]) -> dict[str, Any]:
    """Apply the hard formulation gate to per-formulation pass/fail verdicts.

    More than one failure stops the колоквиум: only formulation credit is kept,
    no proof credit without fundamentals.
    """
    return assessment.grade_formulation_gate(subject, verdicts)


@mcp.tool()
def announce_assessment(
    subject: str,
    kind: str = "kolokvium",
    scheduled_at: Optional[str] = None,
    ticket: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Record an announced колоквиум/exam. Announce first, schedule prep sessions, draw the ticket at the session."""
    return assessment.announce_assessment(subject, kind, scheduled_at, ticket)


@mcp.tool()
def schedule_assessment(
    subject: str, kind: str = "kolokvium", days_ahead: int = 7, duration_minutes: int = 90
) -> dict[str, Any]:
    """Place the assessment block plus its dedicated preparation sessions."""
    return assessment.schedule_assessment(subject, kind, days_ahead, duration_minutes)


@mcp.tool()
def record_assessment_result(
    assessment_id: int,
    result: dict[str, Any],
    score: Optional[float] = None,
    status: str = "passed",
    record_path: Optional[str] = None,
) -> dict[str, Any]:
    """Persist a graded assessment and return the remediation consequences."""
    return assessment.record_assessment_result(assessment_id, result, score, status, record_path)


# --- config and overview -------------------------------------------------


@mcp.tool()
def harness_config(subject: Optional[str] = None, reload: bool = False) -> dict[str, Any]:
    """Effective configuration, optionally with a subject's domain/subject overrides applied."""
    settings = reload_settings() if reload else get_settings()
    effective = settings.for_subject(subject)
    return {
        "subject": subject,
        "config": effective.model_dump(),
        "config_file": str(settings.root / "config.json"),
        "note": "Edit config.json or set HARNESS_* env vars; per-subject overrides go in subjects/<s>/config.json.",
    }


@mcp.tool()
def dashboard(subject: Optional[str] = None) -> dict[str, Any]:
    """One-call situational awareness: block, agenda, review load, health, pending triggers."""
    init_db()
    known = subjects.list_subjects()
    target = subject or (known["subjects"][0]["subject"] if known["subjects"] else None)
    view: dict[str, Any] = {
        "now": to_iso(now()),
        "block": blockclock.status(),
        "subjects": known["subjects"],
        "agenda": scheduler.agenda(target, 7),
    }
    if target:
        view["subject"] = target
        view["reviews_due"] = srs.due_queue(target)["due_now"]
        view["frontier"] = concepts.frontier(target)
        view["health"] = mastery.health_metrics(target)
        view["delayed_rechecks"] = mastery.due_rechecks(target)["count"]
        view["kolokvium"] = assessment.kolokvium_check(target)["triggered"]
        view["exam"] = assessment.exam_check(target)["triggered"]
        view["remediation"] = mastery.weak_concepts(target)["remediation_needed"]
    return view


def main() -> None:
    init_db()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
