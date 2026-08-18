"""End-to-end smoke test over a throwaway harness root.

Runs the full M1 loop the PRD describes: intake -> concept graph -> gating ->
scheduling -> block -> reviews -> mastery -> pools -> колоквиум trigger, and
asserts the guardrails that are the point of the system (prereq gating, hint
penalties, spacing requirements, formulation gate).

Run with:  uv run python -m tests.test_smoke
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="harness-smoke-"))
os.environ["HARNESS_ROOT"] = str(TMP)
os.environ["HARNESS_NOTIFICATIONS_ENABLED"] = "false"
(TMP / "subjects").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import assessment, blockclock, concepts, mastery, scheduler, srs, subjects  # noqa: E402
from harness.calendar import get_calendar  # noqa: E402
from harness.config import get_settings  # noqa: E402
from harness.store import init_db  # noqa: E402
from harness.timeutil import now, to_iso  # noqa: E402

PASS, FAIL = 0, 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def main() -> int:
    init_db()
    print(f"harness root: {TMP}\n")

    # --- intake ---------------------------------------------------------
    print("intake")
    created = subjects.scaffold_subject("Матан I", mode="scoped", sources=["Zorich vol.1"], domain="math")
    subject = created["subject"]
    check("subject scaffolded", (get_settings().subject_dir(subject) / "plan.md").exists())
    check("scoped mode recorded", created["mode"] == "scoped")
    check("exam-pool dir exists", (get_settings().subject_dir(subject) / "exam-pool").is_dir())

    # --- concept graph --------------------------------------------------
    print("\nconcept graph")
    graph = [
        {"name": "Sequence limit", "prereqs": [], "provable": True, "source_ref": "Zorich 3.1"},
        {"name": "Cauchy criterion", "prereqs": ["Sequence limit"], "provable": True, "source_ref": "Zorich 3.2"},
        {"name": "Function limit", "prereqs": ["Sequence limit"], "provable": True},
        {"name": "Continuity", "prereqs": ["Function limit"], "provable": True},
        {"name": "Measure theory", "prereqs": [], "status": "excluded"},
    ]
    result = concepts.register_concepts(subject, graph)
    check("5 concepts registered", len(result["created"]) == 5, str(result))
    check("re-register is idempotent", len(concepts.register_concepts(subject, graph)["created"]) == 0)

    gate = concepts.gate_check(subject, "Continuity")
    check("prereq gate blocks unmastered chain", not gate["allowed"], str(gate["blocking"]))
    front = concepts.frontier(subject)
    check("frontier = root concept only", [f["concept"] for f in front["ready"]] == ["Sequence limit"], str(front["ready"]))
    check("excluded concept stays out of frontier", "Measure theory" in front["excluded"])

    # --- calendar and scheduling ----------------------------------------
    print("\nscheduling")
    cal = get_calendar()
    cal.add_commitment("Lectures", weekdays=["mon", "wed"], start_time="10:00", end_time="14:00")
    cal.add_commitment("Gym", weekdays=["tue", "thu"], start_time="19:00", end_time="20:30")
    check("2 commitments stored", len(cal.list_commitments()) == 2)

    windows = scheduler.free_windows()
    check("free windows found", len(windows["windows"]) > 0)
    check("busy time expanded from recurrence", len(windows["busy"]) > 0)

    proposal = scheduler.propose_schedule(subject, count=4, topics=["Sequence limit"] * 4, commit=True)
    check("4 blocks placed", proposal["placed"] == 4, str(proposal.get("warning")))
    check("spacing: blocks spread over >= 3 days", proposal["distinct_days"] >= 3, str(proposal["days"]))

    overlapping = None
    try:
        scheduler.place_block(subject, proposal["blocks"][0]["start"], duration_minutes=50)
    except ValueError as exc:
        overlapping = str(exc)
    check("double-booking refused", overlapping is not None and "overlaps" in overlapping)

    # a placed block must not appear as free time any more
    after = scheduler.free_windows()
    first = proposal["blocks"][0]
    clash = [w for w in after["windows"] if w["start"] <= first["start"] < w["end"]]
    check("placed block removed from free windows", not clash)

    # --- block clock ----------------------------------------------------
    print("\nblock clock")
    block_id = proposal["blocks"][0].get("id")
    started = blockclock.start_block(subject, duration_minutes=50, topic="Sequence limit", block_id=block_id)
    check("block started", started.get("started") is True, str(started))
    check("solo mode on by default", blockclock.status()["solo_mode"])
    check("starts in review segment", blockclock.status()["segment"] == "review")
    check("second start refused", "error" in blockclock.start_block(subject))
    line = blockclock.compact_line()
    check("hook line renders", line.startswith("[Block 0/50min"), line)

    blockclock.pause_block("phone call")
    check("pause registers", blockclock.status()["paused"])
    blockclock.resume_block()
    check("resume registers", not blockclock.status()["paused"])
    blockclock.set_segment("new_material")
    check("segment switch", blockclock.status()["segment"] == "new_material")

    # --- reviews and FSRS ------------------------------------------------
    print("\nspaced repetition")
    srs.seed_missing_cards(subject)
    queue = srs.due_queue(subject)
    check("all non-excluded concepts have cards", queue["due_now"] == 4, str(queue["due_now"]))
    check("excluded concept has no card", all(i["concept"] != "Measure theory" for i in queue["items"]))

    graded = srs.grade(subject, "Sequence limit", score=1.0, variant="epsilon-N from definition", minutes_on_task=12)
    check("good grade schedules forward", graded["next_due"] > to_iso(now()), graded["next_due"])
    check("rating derived as Easy", graded["rating_name"] == "Easy", graded["rating_name"])

    hinted = srs.grade(subject, "Cauchy criterion", score=1.0, hints_used=1, variant="v1")
    check("hint caps rating at Hard", hinted["rating_name"] == "Hard", hinted["rating_name"])

    failed = srs.grade(subject, "Function limit", score=0.2, variant="v1")
    check("failure rated Again", failed["rating_name"] == "Again")

    # --- mastery gate ----------------------------------------------------
    print("\nmastery gate")
    status = mastery.mastery_status(subject, "Sequence limit")
    check("not mastered on one rep", not status["eligible"], str(status["remaining"]))
    check("time-on-task tracked", status["checks"]["time_on_task"]["have"] == 12.0)

    # Six varied reps, all today: reps satisfied, spacing not.
    base = now()
    for i in range(6):
        srs.grade(
            subject,
            "Sequence limit",
            score=1.0,
            variant=f"variant-{i}",
            minutes_on_task=10,
            at=to_iso(base),
        )
    massed = mastery.mastery_status(subject, "Sequence limit")
    check("massed reps do NOT confer mastery", not massed["eligible"], str(massed["remaining"]))
    check("blocked specifically on spacing", set(massed["remaining"]) <= {"distinct_days", "span_days"}, str(massed["remaining"]))

    # Same reps spread over a week: gate opens.
    for i in range(6):
        srs.grade(
            subject,
            "Sequence limit",
            score=1.0,
            variant=f"spaced-{i}",
            minutes_on_task=10,
            at=to_iso(base + dt.timedelta(days=i + 1)),
        )
    spaced = mastery.evaluate_mastery(subject, "Sequence limit")
    check("spaced reps confer mastery", spaced["eligible"] and spaced["status"] == "mastered", str(spaced["remaining"]))

    gate_now = concepts.gate_check(subject, "Function limit")
    check("gate opens once prereq is mastered", gate_now["allowed"], str(gate_now["blocking"]))

    # Repeating one variant many times must not count as varied reps.
    for _ in range(8):
        srs.grade(subject, "Continuity", score=1.0, variant="same-exercise", minutes_on_task=10)
    same = mastery.mastery_status(subject, "Continuity")
    check("repeated identical variant counts once", same["checks"]["varied_reps"]["have"] == 1, str(same["checks"]["varied_reps"]))

    # --- hint analytics ---------------------------------------------------
    print("\nhint analytics")
    for _ in range(4):
        mastery.record_hint(subject, "Cauchy criterion", exercise_ref="ex-1")
    hint_status = mastery.mastery_status(subject, "Cauchy criterion")
    check("high hint rate blocks mastery", "hint_rate" in hint_status["remaining"], str(hint_status["checks"]["hint_rate"]))
    budget = mastery.record_hint(subject, "Cauchy criterion", exercise_ref="ex-2")
    check("hint budget reported", budget["budget_exhausted"] is True, str(budget))

    # --- trickle-down ------------------------------------------------------
    print("\ntrickle-down credit")
    before = srs.card_summary(subject)
    due_before = {c["name"]: c["due"] for c in before}
    srs.grade(subject, "Function limit", score=1.0, variant="td-1")
    after_cards = {c["name"]: c["due"] for c in srs.card_summary(subject)}
    check(
        "success on advanced skill pushes prerequisite due date out",
        after_cards["Sequence limit"] >= due_before["Sequence limit"],
        f"{due_before['Sequence limit']} -> {after_cards['Sequence limit']}",
    )

    # --- exam pools --------------------------------------------------------
    print("\nexam pools")
    rejected = None
    try:
        assessment.add_pool_item(subject, "formulations", "Sequence limit", "State the definition.")
    except ValueError as exc:
        rejected = str(exc)
    check("theory item without checklist refused", rejected is not None and "required_elements" in rejected)

    rejected_problem = None
    try:
        assessment.add_pool_item(subject, "problems", "Sequence limit", "Compute the limit.", rubric="x")
    except ValueError as exc:
        rejected_problem = str(exc)
    check("problem without reference solution refused", rejected_problem is not None)

    for i in range(10):
        assessment.add_pool_item(
            subject,
            "formulations",
            "Sequence limit",
            f"State definition #{i}.",
            required_elements=["epsilon-N form", "quantifier order"],
            format="definition",
        )
    for i in range(8):
        assessment.add_pool_item(
            subject,
            "proofs",
            "Cauchy criterion",
            f"Prove statement #{i}.",
            required_elements=["completeness used", "both directions"],
            format="proof",
        )
    for i in range(22):
        assessment.add_pool_item(
            subject,
            "problems",
            "Function limit",
            f"Problem #{i}",
            rubric="2 pts setup, 2 pts estimate, 1 pt conclusion",
            reference_solution="…",
            source="Zorich 3.2 ex.14",
        )
    pools = assessment.list_pool(subject)
    check("pool counts", pools["counts"] == {"formulations": 10, "proofs": 8, "problems": 22}, str(pools["counts"]))

    published = assessment.render_pools(subject)
    check("pools rendered to files", len(published["written"]) == 3)
    check("pool file readable", (TMP / "subjects" / subject / "exam-pool" / "formulations.md").exists())

    ticket = assessment.draw_ticket(subject)
    check("ticket has 3 formulations", len(ticket["ticket"]["formulations"]) == 3)
    check("ticket has 1-2 proofs", 1 <= len(ticket["ticket"]["proofs"]) <= 2)
    check("ticket carries required elements", bool(ticket["ticket"]["formulations"][0]["required_elements"]))

    gate_stop = assessment.grade_formulation_gate(subject, [True, False, False])
    check("formulation gate stops on 2 failures", not gate_stop["gate_passed"])
    gate_ok = assessment.grade_formulation_gate(subject, [True, True, False])
    check("formulation gate passes on 1 failure", gate_ok["gate_passed"])

    check("exam trigger fires on problem pool", assessment.exam_check(subject)["triggered"])
    kolok = assessment.kolokvium_check(subject)
    check("kolokvium check returns conditions", "weeks_of_material" in kolok["conditions"])

    announced = assessment.announce_assessment(subject, "kolokvium", to_iso(now() + dt.timedelta(days=7)), ticket)
    check("assessment announced", announced["id"] > 0)
    recorded = assessment.record_assessment_result(announced["id"], {"formulations": [1, 1, 0]}, score=0.7)
    check("assessment result recorded", recorded["status"] == "passed")

    # --- instrumentation ---------------------------------------------------
    print("\ninstrumentation (§8)")
    srs.grade(subject, "Sequence limit", score=0.2, kind="delayed_recheck", variant="recheck-1")
    health = mastery.health_metrics(subject)
    check("performance and learning tracked apart", health["performance_in_session"] is not None and health["learning_delayed_recheck"] is not None, str(health))
    check("gap computed", health["gap"] is not None)

    mastery.revoke_mastery(subject, "Sequence limit")
    revoked_gate = concepts.gate_check(subject, "Function limit")
    check("revoking mastery re-closes the downstream gate", not revoked_gate["allowed"])

    weak = mastery.weak_concepts(subject)
    check("weak concepts surfaced for remediation", isinstance(weak["weak"], list))

    mastery.record_grading_check(subject, 0.9, 0.5)
    agreement = mastery.health_metrics(subject)["grading_agreement"]
    check("grading agreement tracked", agreement == 0.0, str(agreement))

    # --- wrap-up ------------------------------------------------------------
    print("\nblock wrap-up")
    subjects.append_covered(subject, ["Sequence limit"], "Covered the epsilon-N definition.", block_id)
    covered_text = (TMP / "subjects" / subject / "covered.md").read_text(encoding="utf-8")
    check("covered.md appended", "epsilon-N" in covered_text)

    ended = blockclock.end_block(summary="smoke test")
    check("block ended", ended.get("ended") is True)
    check("wrap-up checklist returned", len(ended["checklist"]) >= 5)
    check("block marked done", scheduler.list_blocks(subject, status="done")["count"] == 1)
    check("state cleared", not blockclock.status()["active"])

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
