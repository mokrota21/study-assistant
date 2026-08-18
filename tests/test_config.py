"""Configuration layering (PRD §7).

Precedence, lowest first: defaults -> config.json -> HARNESS_* env -> domain
override -> subject override. The last two only apply through `for_subject`.

Run with:  uv run python -m tests.test_config
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PASS = FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="harness-config-"))
    shutil.copy(REPO / "config.json", root / "config.json")
    (root / "subjects" / "matan").mkdir(parents=True)
    (root / "subjects" / "cooking").mkdir(parents=True)
    (root / "subjects" / "matan" / "config.json").write_text(
        json.dumps({"domain": "math", "mastery_min_span_days": 7}), encoding="utf-8"
    )
    (root / "subjects" / "cooking" / "config.json").write_text(
        json.dumps({"domain": "cooking"}), encoding="utf-8"
    )

    os.environ["HARNESS_ROOT"] = str(root)
    os.environ["HARNESS_REVIEW_CAP_PER_BLOCK"] = "7"
    sys.path.insert(0, str(REPO))
    from harness.config import get_settings  # imported late: reads env at construction

    base = get_settings()
    check("defaults load", base.focus_minutes == 50, str(base.focus_minutes))
    check("config.json is read", base.fsrs_desired_retention == 0.9)
    check("env var beats config.json", base.review_cap_per_block == 7, str(base.review_cap_per_block))
    check("comment keys are ignored, not fatal", base.mastery_min_reps == 6)
    check("root honours HARNESS_ROOT", str(base.root) == str(root), str(base.root))

    math = base.for_subject("matan")
    check("domain override applies (reps)", math.mastery_min_reps == 8, str(math.mastery_min_reps))
    check("domain override applies (minutes)", math.mastery_min_minutes == 60, str(math.mastery_min_minutes))
    check("subject override beats domain", math.mastery_min_span_days == 7, str(math.mastery_min_span_days))
    check("unrelated fields unchanged", math.focus_minutes == 50)

    cooking = base.for_subject("cooking")
    check("a second domain resolves independently", cooking.mastery_min_span_days == 14, str(cooking.mastery_min_span_days))

    check("unknown subject falls back to base", base.for_subject("nope").mastery_min_reps == 6)
    check("no subject falls back to base", base.for_subject(None).mastery_min_reps == 6)
    check("base object was not mutated", base.mastery_min_reps == 6 and base.mastery_min_span_days == 5)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
