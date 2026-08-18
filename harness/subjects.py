"""Subject scaffolding and the file layout from PRD §2.

Files own prose; this module just guarantees the skeleton exists and that the
two append-only logs (``covered.md``, ``notes/YYYY-MM-DD.md``) stay in a shape
the triggers can read.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Optional

from .config import get_settings
from .store import init_db, log_event
from .timeutil import now, to_iso

PLAN_TEMPLATE = """# {subject} — study plan

**Mode:** {mode}
**Created:** {created}
**Language:** {language}

## Contract

{contract}

## Concept graph

Status values: `planned` · `frontier` · `learning` · `mastered` · `revoked` · `excluded`.
After editing this table, call `register_concepts` so the harness state matches it.

| Concept | Prerequisites | Provable | Source | Status |
|---|---|---|---|---|
| _(fill at intake)_ | | | | planned |

## Excluded but adjacent

Concepts deliberately left out. Pulling one in is an explicit command
("expand into <concept>"), which triggers incremental research and a plan update.

- _(none yet)_

## Coverage against source

{coverage}

## Open suggestions

Adjacent topics noticed while working. Logged, never pursued without a command.

- _(none yet)_
"""

COVERED_TEMPLATE = """# Covered material — {subject}

Append-only log. Each entry is one study block. This is the trigger source for
the колоквиум (~6-8 weeks of accumulated material).

"""

NOTES_TEMPLATE = """# {date} — {subject}

**Block:** {block}
**Topic:** {topic}

## What was covered

## What went well

## What was shaky

_Concepts to re-drill; these should show up as failed or hinted reviews too._

## Hints used

## Deposited into exam pool

## Next lesson

"""

SUBJECT_README = """# {subject}

Layout (PRD §2):

- `plan.md` — curriculum: concept graph, frontier, status per concept
- `materials/` — collected raw documents
- `lessons/lesson-NNN.md` — prepared lessons: stages, explanations, problems, rubrics
- `notes/YYYY-MM-DD.md` — what happened each study day
- `covered.md` — running log; the колоквиум trigger source
- `exam-pool/` — formulations, proofs, problems (rendered from the harness DB)
- `results/` — graded колоквиум/exam records
- `config.json` — per-subject overrides of any config field
"""


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug or "subject"


def scaffold_subject(
    subject: str,
    mode: str = "exploratory",
    sources: Optional[Iterable[str]] = None,
    domain: Optional[str] = None,
    overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create the subject folder tree and seed plan/covered files. Idempotent."""
    if mode not in ("exploratory", "scoped"):
        raise ValueError("mode must be 'exploratory' (no textbook) or 'scoped' (textbook given)")
    init_db()
    settings = get_settings()
    slug = slugify(subject)
    base = settings.subject_dir(slug)
    created = []
    for sub in ("", "materials", "lessons", "notes", "exam-pool", "results"):
        path = base / sub if sub else base
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path.relative_to(settings.root)).replace("\\", "/"))

    source_list = list(sources or [])
    contract = (
        "**Scoped mode.** The learner does not know this material yet — that is why there is a book. "
        "The source is the authority and the agent teaches it. The contract is that the user understands "
        "the material of "
        + ", ".join(f"*{s}*" for s in source_list)
        + " — **not under, not over**. The frontier is derived mechanically from the table of contents; "
        "coverage is tracked against it. Supplementary material may improve explanations but never widens "
        "scope. Adjacent topics are logged as suggestions and pursued only on command. The book's own "
        "problem sets are the primary exam-pool source — real problems beat generated ones. Scope is not "
        "negotiated with the learner here: constraints adjust the schedule, not the material."
        if mode == "scoped"
        else "**Exploratory mode.** No fixed source. The learner's stated goal is the seed, not the "
        "boundary — a learner cannot audit their own blind spots, so the agent researches what the goal "
        "actually requires and proposes the shape of the subject, including prerequisites the learner "
        "never mentioned. The frontier is then negotiated with the agent leading: it explains what each "
        "branch buys and what cutting it would cost before the learner decides. Expansion is an explicit "
        "command. A research-effort budget caps the research phase, but scope is defined in concepts."
    )
    coverage = (
        "Track every TOC entry of the source(s) here: covered / in progress / not started.\n\n"
        "| TOC entry | Concepts | Status |\n|---|---|---|\n| _(fill from the table of contents)_ | | |"
        if mode == "scoped"
        else "_Exploratory mode: no external TOC. Coverage is the concept graph above._"
    )

    files = {}
    plan = base / "plan.md"
    if not plan.exists():
        plan.write_text(
            PLAN_TEMPLATE.format(
                subject=subject,
                mode=mode,
                created=to_iso(now())[:10],
                language=settings.content_language,
                contract=contract,
                coverage=coverage,
            ),
            encoding="utf-8",
        )
        files["plan"] = str(plan.relative_to(settings.root)).replace("\\", "/")

    covered = base / "covered.md"
    if not covered.exists():
        covered.write_text(COVERED_TEMPLATE.format(subject=subject), encoding="utf-8")
        files["covered"] = str(covered.relative_to(settings.root)).replace("\\", "/")

    readme = base / "README.md"
    if not readme.exists():
        readme.write_text(SUBJECT_README.format(subject=subject), encoding="utf-8")

    config_path = base / "config.json"
    config: dict[str, Any] = {"display_name": subject, "mode": mode, "sources": source_list}
    if domain:
        config["domain"] = domain
    config.update(overrides or {})
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
            existing.update(config)
            config = existing
        except json.JSONDecodeError:
            pass
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    log_event(slug, "subject_created", {"mode": mode, "sources": source_list})
    return {
        "subject": slug,
        "display_name": subject,
        "mode": mode,
        "path": str(base.relative_to(settings.root)).replace("\\", "/"),
        "created_dirs": created,
        "created_files": files,
        "next_steps": [
            "Collect materials into materials/ (scoped mode: the source TOC is the frontier).",
            "Draft the concept graph in plan.md, then call register_concepts to sync it.",
            "Negotiate the frontier with the user — included vs. excluded-but-adjacent.",
            "Call seed_cards, then propose_schedule for the first two weeks.",
        ],
    }


def list_subjects() -> dict[str, Any]:
    settings = get_settings()
    if not settings.subjects_dir.exists():
        return {"subjects": [], "note": "No subjects yet. Run intake to create one."}
    out = []
    for path in sorted(p for p in settings.subjects_dir.iterdir() if p.is_dir()):
        config = {}
        config_path = path / "config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                config = {}
        out.append(
            {
                "subject": path.name,
                "display_name": config.get("display_name", path.name),
                "mode": config.get("mode"),
                "sources": config.get("sources", []),
                "has_plan": (path / "plan.md").exists(),
            }
        )
    return {"subjects": out, "count": len(out)}


def append_covered(
    subject: str,
    concepts: Iterable[str],
    summary: str,
    block_id: Optional[int] = None,
    date: Optional[str] = None,
) -> dict[str, Any]:
    """Append one block's coverage to ``covered.md`` — the колоквиум trigger source (§5.2)."""
    settings = get_settings()
    path = settings.subject_dir(subject) / "covered.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(COVERED_TEMPLATE.format(subject=subject), encoding="utf-8")
    stamp = (date or to_iso(now()))[:10]
    concept_list = list(concepts)
    entry = [
        f"## {stamp}" + (f" — block #{block_id}" if block_id else ""),
        "",
        f"**Concepts:** {', '.join(concept_list) if concept_list else '—'}",
        "",
        summary.strip(),
        "",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(entry) + "\n")
    return {
        "subject": subject,
        "path": str(path.relative_to(settings.root)).replace("\\", "/"),
        "concepts": concept_list,
        "date": stamp,
    }


def notes_template(subject: str, topic: str = "", block: str = "") -> dict[str, Any]:
    """Path and skeleton for today's notes file. The agent writes the content itself."""
    settings = get_settings()
    stamp = to_iso(now())[:10]
    path = settings.subject_dir(subject) / "notes" / f"{stamp}.md"
    return {
        "path": str(path.relative_to(settings.root)).replace("\\", "/"),
        "exists": path.exists(),
        "template": NOTES_TEMPLATE.format(date=stamp, subject=subject, topic=topic or "—", block=block or "—"),
    }
