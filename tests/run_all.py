"""Run the whole test suite.

    uv run python -m tests.run_all

Each suite runs in its own process against a throwaway harness root, so nothing
here touches your real study data.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SUITES = [
    ("configuration layering", "tests.test_config"),
    ("core loop (M1 + M2 guardrails)", "tests.test_smoke"),
    ("MCP tool surface", "tests.test_mcp"),
    ("Claude Code hooks", "tests.test_hooks"),
    ("stdio launch (as Claude Code starts it)", "tests.test_launch"),
]


def main() -> int:
    failed = []
    for label, module in SUITES:
        print(f"\n{'=' * 72}\n{label}  ({module})\n{'=' * 72}")
        proc = subprocess.run([sys.executable, "-m", module], cwd=REPO)
        if proc.returncode != 0:
            failed.append(label)
    print(f"\n{'=' * 72}")
    if failed:
        print("FAILED suites: " + ", ".join(failed))
        return 1
    print(f"All {len(SUITES)} suites passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
