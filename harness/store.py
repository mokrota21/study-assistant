"""SQLite state store.

Division of ownership (PRD §2): **files own prose, the database owns state that
needs computation.** ``plan.md`` is canonical for the concept graph as a human
reads it; this database is canonical for anything with arithmetic behind it —
FSRS due dates, rep counts, time-on-task, hint usage, grading agreement.

The agent keeps them in sync by calling ``register_concepts`` after editing
``plan.md``. That call is an idempotent upsert, so re-running it is always safe.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import get_settings

_LOCK = threading.RLock()
_SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per concept / sub-skill in a subject's graph.
CREATE TABLE IF NOT EXISTS concepts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject      TEXT NOT NULL,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'concept',   -- concept | subskill
    status       TEXT NOT NULL DEFAULT 'planned',   -- planned | frontier | learning | mastered | revoked | excluded
    prereqs      TEXT NOT NULL DEFAULT '[]',        -- JSON list of concept names in the same subject
    tags         TEXT NOT NULL DEFAULT '[]',
    provable     INTEGER NOT NULL DEFAULT 0,        -- carries a theorem/proof obligation (колоквиум fodder)
    source_ref   TEXT,                              -- e.g. "Zorich ch.3 §2" — TOC anchor in scoped mode
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    mastered_at  TEXT,
    revoked_at   TEXT,
    UNIQUE (subject, name)
);

-- FSRS card, one per concept (PRD §4: the unit is the sub-skill, not the exercise).
CREATE TABLE IF NOT EXISTS cards (
    concept_id   INTEGER PRIMARY KEY REFERENCES concepts(id) ON DELETE CASCADE,
    card_json    TEXT NOT NULL,      -- fsrs.Card.to_dict()
    due          TEXT NOT NULL,      -- denormalized for cheap queue queries
    state        TEXT NOT NULL,
    stability    REAL,
    difficulty   REAL,
    reps         INTEGER NOT NULL DEFAULT 0,
    lapses       INTEGER NOT NULL DEFAULT 0,
    suspended    INTEGER NOT NULL DEFAULT 0,
    last_review  TEXT,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(due);

-- Every graded retrieval attempt. `kind` is what §8 hangs on.
CREATE TABLE IF NOT EXISTS reviews (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id    INTEGER NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    subject       TEXT NOT NULL,
    at            TEXT NOT NULL,
    rating        INTEGER NOT NULL,          -- FSRS 1..4
    correct       INTEGER NOT NULL,          -- rubric verdict, 0/1
    score         REAL,                      -- 0..1 where the rubric is graded partially
    kind          TEXT NOT NULL DEFAULT 'in_session',  -- in_session | delayed_recheck | exam | kolokvium | remediation
    variant       TEXT,                      -- exercise variant tag: enforces "varied reps"
    exercise_ref  TEXT,                      -- path/anchor of the exercise + rubric that produced this
    hints_used    INTEGER NOT NULL DEFAULT 0,
    duration_s    INTEGER,
    block_id      INTEGER,
    credit_source TEXT,                      -- set when the row is trickle-down credit from a descendant
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviews_concept ON reviews(concept_id, at);
CREATE INDEX IF NOT EXISTS idx_reviews_kind ON reviews(subject, kind, at);

-- Time-on-task, half of the dual mastery threshold (§3.5).
CREATE TABLE IF NOT EXISTS practice (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id  INTEGER NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    minutes     REAL NOT NULL,
    at          TEXT NOT NULL,
    block_id    INTEGER,
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_practice_concept ON practice(concept_id, at);

-- Stuck-hatch invocations (§6). Frequent use blocks mastery.
CREATE TABLE IF NOT EXISTS hints (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id   INTEGER NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    subject      TEXT NOT NULL,
    at           TEXT NOT NULL,
    exercise_ref TEXT,
    hint_index   INTEGER NOT NULL DEFAULT 1,
    hint_text    TEXT,
    block_id     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_hints_concept ON hints(concept_id, at);

-- Scheduled study blocks. Non-study commitments live in state/calendar.json.
CREATE TABLE IF NOT EXISTS blocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT,
    kind        TEXT NOT NULL DEFAULT 'study',   -- study | review | prep | kolokvium | exam | remediation
    start       TEXT NOT NULL,
    end         TEXT NOT NULL,
    topic       TEXT,
    status      TEXT NOT NULL DEFAULT 'planned', -- planned | active | done | skipped | cancelled
    lesson_ref  TEXT,
    notes_path  TEXT,
    created_at  TEXT NOT NULL,
    closed_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_blocks_start ON blocks(start);

-- Exam pool (§5.1). The DB is the countable source of truth; exam-pool/*.md is
-- rendered from it so the pools stay visible to the user for preparation.
CREATE TABLE IF NOT EXISTS pool_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    subject           TEXT NOT NULL,
    pool              TEXT NOT NULL,            -- formulations | proofs | problems
    concept_id        INTEGER REFERENCES concepts(id) ON DELETE SET NULL,
    concept_name      TEXT NOT NULL,
    prompt            TEXT NOT NULL,
    required_elements TEXT NOT NULL DEFAULT '[]',  -- binary checklist, written at creation time (§5.5)
    reference_solution TEXT,
    rubric            TEXT,                     -- olympiad-style, also written at creation time
    difficulty        INTEGER NOT NULL DEFAULT 2,
    format            TEXT,                     -- definition | statement | proof | computation | ...
    source            TEXT,                     -- "Zorich 3.2 ex.14" beats a generated problem
    created_at        TEXT NOT NULL,
    used_count        INTEGER NOT NULL DEFAULT 0,
    last_used_at      TEXT,
    retired           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pool ON pool_items(subject, pool, retired);

-- Announced колоквиум / exam records. Prose lives in results/.
CREATE TABLE IF NOT EXISTS assessments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject      TEXT NOT NULL,
    kind         TEXT NOT NULL,               -- kolokvium | exam | remediation
    status       TEXT NOT NULL DEFAULT 'announced', -- announced | in_progress | passed | failed | stopped
    announced_at TEXT NOT NULL,
    scheduled_at TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    ticket       TEXT NOT NULL DEFAULT '{}',  -- JSON: drawn pool item ids by section
    result       TEXT NOT NULL DEFAULT '{}',  -- JSON: per-item scores, gate outcome
    score        REAL,
    record_path  TEXT
);
CREATE INDEX IF NOT EXISTS idx_assessments ON assessments(subject, kind, announced_at);

-- AI grade vs. user spot-check. Drives the §5.5 pull-out threshold.
CREATE TABLE IF NOT EXISTS grading_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,
    at          TEXT NOT NULL,
    item_ref    TEXT,
    ai_score    REAL NOT NULL,
    user_score  REAL NOT NULL,
    agreed      INTEGER NOT NULL,
    note        TEXT
);

-- Generic audit trail: колоквиум announced, mastery revoked, scope expanded...
CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       TEXT NOT NULL,
    subject  TEXT,
    kind     TEXT NOT NULL,
    payload  TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(subject, kind, at);
"""


def _db_file() -> Path:
    return get_settings().db_path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Serialized connection with foreign keys on and dict-like rows."""
    with _LOCK:
        conn = sqlite3.connect(_db_file(), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(_SCHEMA_VERSION),),
        )


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def log_event(subject: Optional[str], kind: str, payload: Optional[dict[str, Any]] = None) -> None:
    from .timeutil import now, to_iso

    with connect() as conn:
        conn.execute(
            "INSERT INTO events(at, subject, kind, payload) VALUES(?,?,?,?)",
            (to_iso(now()), subject, kind, json.dumps(payload or {}, ensure_ascii=False)),
        )
