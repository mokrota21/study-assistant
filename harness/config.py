"""Central configuration (PRD §7).

Resolution order, lowest priority first:

1. Defaults below.
2. ``config.json`` in the harness root (agent- and human-editable).
3. Environment variables prefixed ``HARNESS_`` (e.g. ``HARNESS_FOCUS_MINUTES=45``).
4. Per-domain overrides: ``config.json -> domains.<domain>.<field>``.
5. Per-subject overrides: ``subjects/<subject>/config.json`` (flat field map).

Levels 4 and 5 are applied by :meth:`Settings.for_subject`, so the base object
stays a plain validated Settings and every consumer gets an effective view.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def harness_root() -> Path:
    """Project root — the folder holding ``subjects/`` and ``config.json``.

    ``HARNESS_ROOT`` wins so the MCP server can be launched from anywhere;
    otherwise we walk up from this file (harness/config.py -> repo root).
    """
    for var in ("HARNESS_ROOT", "CLAUDE_PROJECT_DIR"):
        value = os.environ.get(var)
        if value and Path(value).expanduser().is_dir():
            return Path(value).expanduser().resolve()
    # Walk up to the directory holding pyproject.toml (correct for an editable
    # install, which is how uv sets this project up).
    here = Path(__file__).resolve().parent
    for candidate in (here.parent, *here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return here.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HARNESS_",
        extra="ignore",
        json_file=str(harness_root() / "config.json"),
        json_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority is first to last: explicit args > env vars > config.json > defaults.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    # --- Focus rhythm (§3.2) -------------------------------------------------
    focus_minutes: int = Field(50, description="Length of one focused study block")
    break_minutes: int = Field(10, description="Minimum break after a focus block")
    long_break_after_minutes: int = Field(120, description="Study time before a long break is required")
    long_break_minutes: int = Field(30, description="Length of the long break")
    max_blocks_per_day: int = Field(4, description="Cap on focus blocks placed in one day")
    prefer_spacing: bool = Field(
        True,
        description="Prefer 2 sessions on 2 days over one double session (spacing beats massing)",
    )
    day_start_hour: int = Field(9, description="Earliest hour a block may be placed")
    day_end_hour: int = Field(22, description="Latest hour a block may end")

    # --- Study block composition (§3.4) --------------------------------------
    review_segment_minutes: int = Field(15, description="Nominal review segment at block start")
    review_cap_per_block: int = Field(12, description="Max review items fetched per block (M)")
    review_overflow_eats_new_material: bool = Field(
        True, description="Overdue reviews are mandatory before new material"
    )

    # --- Spaced repetition (§4) ----------------------------------------------
    fsrs_desired_retention: float = Field(0.90, ge=0.70, le=0.99)
    fsrs_maximum_interval_days: int = Field(365 * 3)
    fsrs_enable_fuzzing: bool = Field(True)
    trickle_down_enabled: bool = Field(
        True, description="Success on an advanced skill discounts prerequisite reviews (FIRe-style)"
    )
    trickle_down_credit: float = Field(
        0.5, ge=0.0, le=1.0, description="Fraction of the elapsed-interval credit passed to prerequisites"
    )
    trickle_down_depth: int = Field(2, ge=0, description="How many prerequisite levels receive credit")

    # --- Mastery gate (§3.5) -------------------------------------------------
    mastery_min_minutes: int = Field(45, description="Minimum time-on-task per concept")
    mastery_min_reps: int = Field(6, description="Minimum varied, correct reps per concept")
    mastery_min_distinct_days: int = Field(3, description="Reps must be distributed across this many days")
    mastery_min_span_days: int = Field(5, description="Calendar span from first to qualifying rep")
    mastery_max_hint_rate: float = Field(
        0.34, ge=0.0, le=1.0, description="Hint-hatch uses per rep above which mastery is blocked (§6)"
    )
    mastery_recheck_days: int = Field(21, description="Delayed re-check offset used for learning (not performance)")

    # --- Assessment (§5) -----------------------------------------------------
    kolokvium_trigger_weeks: float = Field(7.0, description="~6-8 weeks of covered material")
    kolokvium_trigger_concepts: int = Field(12, description="Alternative trigger: covered concept count")
    kolokvium_min_provable: int = Field(4, description="Provable items required before a колоквиум")
    kolokvium_prep_sessions: int = Field(2, description="Dedicated preparation blocks placed before it")
    ticket_formulations: int = Field(3)
    ticket_proofs_min: int = Field(1)
    ticket_proofs_max: int = Field(2)
    ticket_problems: int = Field(1)
    formulation_gate_max_failures: int = Field(
        1, description="Fail more than this many formulations -> колоквиум stops"
    )
    exam_problem_pool_threshold: int = Field(20, description="Problem-idea pool size that triggers an exam")
    remediation_threshold: float = Field(
        0.6, ge=0.0, le=1.0, description="Score below this triggers a supervised-practice session (§5.4)"
    )
    grading_self_consistency_passes: int = Field(2, description="Independent gradings on колоквиум/exam")
    grading_agreement_pullout: float = Field(
        0.82, description="AI/user agreement below this pulls open-ended auto-grading from the mastery gate (§5.5)"
    )

    # --- Practice protocol (§6) ----------------------------------------------
    solo_mode_default: bool = Field(True, description="New practice segments start in solo mode")
    hints_per_exercise: int = Field(1, description="Stuck hatch yields one hint, never the answer")

    # --- Curriculum (§3.1, §3.3) ---------------------------------------------
    scheduling_horizon_days: int = Field(14)
    prep_full_lessons: int = Field(2, description="Lessons prepared in full detail")
    prep_outline_lessons: int = Field(7, description="Lessons kept as shaped outlines")

    # --- Content ------------------------------------------------------------
    content_language: str = Field(
        "en",
        description="Language for lessons/notes/exams. Russian domain terms (колоквиум, доп вопросы) are kept as-is.",
    )

    # --- Notifications (§3.4.1) ---------------------------------------------
    notifications_enabled: bool = Field(True)
    notification_sound: bool = Field(True)
    notify_before_end_minutes: int = Field(5, description="Heads-up notification before a block ends")

    # --- Calendar -----------------------------------------------------------
    calendar_provider: str = Field("local", description="'local' (JSON store) or 'google' (not yet implemented)")

    # --- Paths --------------------------------------------------------------
    @property
    def root(self) -> Path:
        return harness_root()

    @property
    def subjects_dir(self) -> Path:
        return self.root / "subjects"

    @property
    def state_dir(self) -> Path:
        path = self.root / "state"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def db_path(self) -> Path:
        return self.state_dir / "harness.db"

    @property
    def block_state_path(self) -> Path:
        """Read by the Claude Code hooks on every prompt — keep it small and stdlib-parseable."""
        return self.state_dir / "block.json"

    @property
    def calendar_path(self) -> Path:
        return self.state_dir / "calendar.json"

    def subject_dir(self, subject: str) -> Path:
        return self.subjects_dir / subject

    # --- Overrides ----------------------------------------------------------
    def for_subject(self, subject: str | None) -> "Settings":
        """Effective settings for one subject: base < domain override < subject override."""
        if not subject:
            return self
        overrides: Dict[str, Any] = {}
        file_cfg = _load_config_file(self.root)
        subject_path = self.subject_dir(subject) / "config.json"
        subject_cfg: Dict[str, Any] = {}
        if subject_path.exists():
            try:
                subject_cfg = json.loads(subject_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                subject_cfg = {}
        domain = subject_cfg.get("domain")
        if domain:
            overrides.update((file_cfg.get("domains") or {}).get(domain, {}))
        overrides.update({k: v for k, v in subject_cfg.items() if k not in ("domain", "domains")})
        if not overrides:
            return self
        merged = self.model_dump()
        merged.update({k: v for k, v in overrides.items() if k in merged})
        return Settings(**merged)


def _load_config_file(root: Path) -> Dict[str, Any]:
    path = root / "config.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
