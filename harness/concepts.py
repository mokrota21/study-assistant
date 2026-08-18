"""Concept graph: registration, prerequisite edges, frontier, gating."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Optional

from .store import connect, init_db
from .timeutil import now, to_iso

VALID_STATUS = {"planned", "frontier", "learning", "mastered", "revoked", "excluded"}


def _norm(name: str) -> str:
    return " ".join(name.strip().split())


def register_concepts(subject: str, items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Idempotent upsert of concept nodes. Called after the agent edits ``plan.md``.

    Each item: ``{name, prereqs?, status?, kind?, provable?, tags?, source_ref?}``.
    Unknown prerequisite names are accepted and reported back — a graph is often
    written top-down, and refusing forward references would make intake painful.
    """
    init_db()
    created, updated = [], []
    stamp = to_iso(now())
    with connect() as conn:
        for raw in items:
            name = _norm(str(raw["name"]))
            status = raw.get("status", "planned")
            if status not in VALID_STATUS:
                raise ValueError(f"invalid status {status!r} for concept {name!r}")
            prereqs = json.dumps([_norm(str(p)) for p in raw.get("prereqs", [])], ensure_ascii=False)
            tags = json.dumps(list(raw.get("tags", [])), ensure_ascii=False)
            existing = conn.execute(
                "SELECT id FROM concepts WHERE subject = ? AND name = ?", (subject, name)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE concepts SET kind=?, status=?, prereqs=?, tags=?, provable=?, source_ref=?
                       WHERE id=?""",
                    (
                        raw.get("kind", "concept"),
                        status,
                        prereqs,
                        tags,
                        int(bool(raw.get("provable", False))),
                        raw.get("source_ref"),
                        existing["id"],
                    ),
                )
                updated.append(name)
            else:
                conn.execute(
                    """INSERT INTO concepts(subject, name, kind, status, prereqs, tags, provable,
                                            source_ref, created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        subject,
                        name,
                        raw.get("kind", "concept"),
                        status,
                        prereqs,
                        tags,
                        int(bool(raw.get("provable", False))),
                        raw.get("source_ref"),
                        stamp,
                    ),
                )
                created.append(name)
        known = {r["name"] for r in conn.execute("SELECT name FROM concepts WHERE subject = ?", (subject,))}
    dangling = sorted(
        {p for raw in items for p in (_norm(str(x)) for x in raw.get("prereqs", []))} - known
    )
    return {
        "subject": subject,
        "created": created,
        "updated": updated,
        "unknown_prereqs": dangling,
        "note": "unknown_prereqs are accepted; register them to complete the graph" if dangling else None,
    }


def get_concept(subject: str, name: str, conn: Optional[sqlite3.Connection] = None) -> Optional[dict[str, Any]]:
    def _run(c: sqlite3.Connection) -> Optional[dict[str, Any]]:
        row = c.execute(
            "SELECT * FROM concepts WHERE subject = ? AND name = ?", (subject, _norm(name))
        ).fetchone()
        return _hydrate(row)

    if conn is not None:
        return _run(conn)
    with connect() as c:
        return _run(c)


def require_concept_id(conn: sqlite3.Connection, subject: str, name: str) -> int:
    row = conn.execute(
        "SELECT id FROM concepts WHERE subject = ? AND name = ?", (subject, _norm(name))
    ).fetchone()
    if row is None:
        raise ValueError(
            f"concept {name!r} is not registered for subject {subject!r} — call register_concepts first"
        )
    return int(row["id"])


def _hydrate(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    data = dict(row)
    data["prereqs"] = json.loads(data.get("prereqs") or "[]")
    data["tags"] = json.loads(data.get("tags") or "[]")
    data["provable"] = bool(data.get("provable"))
    return data


def list_concepts(subject: str, status: Optional[str] = None) -> list[dict[str, Any]]:
    init_db()
    query = "SELECT * FROM concepts WHERE subject = ?"
    params: list[Any] = [subject]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY id"
    with connect() as conn:
        return [_hydrate(r) for r in conn.execute(query, params)]  # type: ignore[misc]


def set_status(subject: str, name: str, status: str) -> dict[str, Any]:
    if status not in VALID_STATUS:
        raise ValueError(f"invalid status {status!r}")
    stamp = to_iso(now())
    with connect() as conn:
        cid = require_concept_id(conn, subject, name)
        fields = {"status": status}
        if status == "learning":
            fields["started_at"] = stamp
        elif status == "mastered":
            fields["mastered_at"] = stamp
            fields["revoked_at"] = None  # type: ignore[assignment]
        elif status == "revoked":
            fields["revoked_at"] = stamp
            fields["mastered_at"] = None  # type: ignore[assignment]
        assignments = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE concepts SET {assignments} WHERE id = ?", (*fields.values(), cid))
        row = conn.execute("SELECT * FROM concepts WHERE id = ?", (cid,)).fetchone()
    return _hydrate(row)  # type: ignore[return-value]


def prerequisites(subject: str, name: str, depth: int = 1) -> list[str]:
    """Prerequisite names up to ``depth`` levels back (breadth-first, cycle-safe)."""
    by_name = {c["name"]: c for c in list_concepts(subject)}
    seen: set[str] = set()
    frontier = [_norm(name)]
    out: list[str] = []
    for _ in range(max(depth, 0)):
        nxt: list[str] = []
        for item in frontier:
            for prereq in (by_name.get(item, {}) or {}).get("prereqs", []):
                if prereq in seen or prereq == _norm(name):
                    continue
                seen.add(prereq)
                if prereq in by_name:
                    out.append(prereq)
                    nxt.append(prereq)
        frontier = nxt
        if not frontier:
            break
    return out


def dependents(subject: str, name: str) -> list[str]:
    target = _norm(name)
    return [c["name"] for c in list_concepts(subject) if target in c["prereqs"]]


def gate_check(subject: str, name: str) -> dict[str, Any]:
    """Strict prerequisite gate (§3.5): may the user start this concept?

    Blocking = a direct prerequisite that is not mastered. Anything not yet
    registered is reported separately rather than silently passing.
    """
    from .mastery import mastery_status

    concept = get_concept(subject, name)
    if concept is None:
        raise ValueError(f"concept {name!r} not registered for {subject!r}")
    blocking, missing, ok = [], [], []
    for prereq in concept["prereqs"]:
        node = get_concept(subject, prereq)
        if node is None:
            missing.append(prereq)
            continue
        if node["status"] == "mastered":
            ok.append(prereq)
        else:
            status = mastery_status(subject, prereq)
            blocking.append(
                {
                    "concept": prereq,
                    "status": node["status"],
                    "remaining": status["remaining"],
                }
            )
    allowed = not blocking and not missing
    return {
        "concept": concept["name"],
        "allowed": allowed,
        "satisfied": ok,
        "blocking": blocking,
        "unregistered_prereqs": missing,
        "verdict": (
            "clear to advance"
            if allowed
            else "blocked — drill the prerequisites below before introducing this concept"
        ),
    }


def frontier(subject: str) -> dict[str, Any]:
    """What is learnable right now: every non-mastered concept whose prereqs are all mastered."""
    concepts = list_concepts(subject)
    mastered = {c["name"] for c in concepts if c["status"] == "mastered"}
    ready, blocked = [], []
    for c in concepts:
        if c["status"] in ("mastered", "excluded"):
            continue
        unmet = [p for p in c["prereqs"] if p not in mastered]
        (blocked if unmet else ready).append(
            {"concept": c["name"], "status": c["status"], "unmet_prereqs": unmet}
        )
    return {
        "subject": subject,
        "mastered": sorted(mastered),
        "ready": ready,
        "blocked": blocked,
        "excluded": [c["name"] for c in concepts if c["status"] == "excluded"],
    }
