"""Hook tests, run against the *system* interpreter the hooks will actually use.

Deliberately not run through uv: the point is to prove the hooks work on a bare
Python with no dependencies and no virtualenv, because that is how Claude Code
will invoke them on every message.

Run with:  uv run python -m tests.test_hooks   (or:  python tests/test_hooks.py)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / ".claude" / "hooks"
PASS = FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def iso(offset_minutes: float) -> str:
    return (datetime.now().astimezone() + timedelta(minutes=offset_minutes)).isoformat(timespec="seconds")


def run_hook(script: str, payload: dict, project: Path, interpreter: str = sys.executable) -> dict | None:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    proc = subprocess.run(
        [interpreter, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise AssertionError(f"{script} exited {proc.returncode}: {proc.stderr}")
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def write_state(project: Path, **overrides) -> dict:
    state = {
        "active": True,
        "block_id": 1,
        "subject": "matan",
        "kind": "study",
        "topic": "Sequence limits",
        "start": iso(-40),
        "end": iso(10),
        "duration_minutes": 50,
        "segment": "review",
        "segment_started": iso(-40),
        "review_segment_minutes": 15,
        "solo_mode": True,
        "paused": False,
        "paused_total_s": 0,
        "wrapup_requested": False,
        "wrapup_done": False,
    }
    state.update(overrides)
    (project / "state").mkdir(parents=True, exist_ok=True)
    (project / "state" / "block.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def read_state(project: Path) -> dict:
    return json.loads((project / "state" / "block.json").read_text(encoding="utf-8"))


def context_of(result: dict | None) -> str:
    if not result:
        return ""
    return (result.get("hookSpecificOutput") or {}).get("additionalContext") or ""


def main() -> int:
    interpreter = shutil.which("python") or sys.executable
    version = subprocess.run(
        [interpreter, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(f"hook interpreter: {interpreter} (Python {version})\n")

    project = Path(tempfile.mkdtemp(prefix="harness-hooks-"))

    print("no block running")
    (project / "state").mkdir(parents=True, exist_ok=True)
    (project / "state" / "block.json").write_text('{"active": false}', encoding="utf-8")
    check("UserPromptSubmit stays silent", run_hook("block_status.py", {"hook_event_name": "UserPromptSubmit"}, project) is None)
    check("Stop stays silent", run_hook("block_end.py", {"hook_event_name": "Stop"}, project) is None)

    print("\nmissing / corrupt state file")
    broken = Path(tempfile.mkdtemp(prefix="harness-hooks-broken-"))
    check("missing state file is survivable", run_hook("block_status.py", {"hook_event_name": "UserPromptSubmit"}, broken) is None)
    (broken / "state").mkdir(parents=True, exist_ok=True)
    (broken / "state" / "block.json").write_text("{not json at all", encoding="utf-8")
    check("corrupt state file is survivable", run_hook("block_status.py", {"hook_event_name": "UserPromptSubmit"}, broken) is None)
    (broken / "state" / "block.json").write_text('﻿{"active": true, "start": "' + iso(-5) + '", "duration_minutes": 50, "segment": "review"}', encoding="utf-8")
    check("BOM-prefixed state still parses", "Block" in context_of(run_hook("block_status.py", {"hook_event_name": "UserPromptSubmit"}, broken)))

    print("\nmid-block")
    write_state(project)
    context = context_of(run_hook("block_status.py", {"hook_event_name": "UserPromptSubmit"}, project))
    check("elapsed/total injected", "Block 40/50min" in context, context[:80])
    check("remaining time injected", "9m left" in context or "10m left" in context, context[:80])
    check("subject injected", "subject=matan" in context)
    check("solo rule injected", "SOLO MODE IS ACTIVE" in context)

    print("\nsolo mode off")
    write_state(project, solo_mode=False)
    context = context_of(run_hook("block_status.py", {"hook_event_name": "UserPromptSubmit"}, project))
    check("no solo rule when disabled", "SOLO MODE IS ACTIVE" not in context)

    print("\nPostToolUse throttling")
    write_state(project, start=iso(-20), duration_minutes=50)
    (project / "state" / "hook-cache.json").unlink(missing_ok=True)
    first = run_hook("block_status.py", {"hook_event_name": "PostToolUse"}, project)
    second = run_hook("block_status.py", {"hook_event_name": "PostToolUse"}, project)
    check("first tool call injects", first is not None)
    check("immediate second tool call is throttled", second is None)
    check("user messages are never throttled", run_hook("block_status.py", {"hook_event_name": "UserPromptSubmit"}, project) is not None)

    print("\nfinal minutes override the throttle")
    write_state(project, start=iso(-47), duration_minutes=50)
    run_hook("block_status.py", {"hook_event_name": "PostToolUse"}, project)
    tail = context_of(run_hook("block_status.py", {"hook_event_name": "PostToolUse"}, project))
    check("tail-of-block tool call still injects", "left" in tail, tail[:80])
    check("convergence warning present", "converging" in tail, tail[:120])

    print("\npaused block")
    write_state(project, start=iso(-60), paused=True, paused_at=iso(-20), duration_minutes=50)
    context = context_of(run_hook("block_status.py", {"hook_event_name": "UserPromptSubmit"}, project))
    check("paused flag shown", "PAUSED" in context, context[:80])
    check("paused time excluded from elapsed", "Block 40/50min" in context, context[:80])

    print("\nStop hook at block end")
    write_state(project, start=iso(-55), duration_minutes=50)
    result = run_hook("block_end.py", {"hook_event_name": "Stop", "stop_hook_active": False}, project)
    check("stop is refused at block end", (result or {}).get("decision") == "block", str(result))
    check("wrap-up directive injected", "wrap-up" in (result or {}).get("reason", "").lower())
    check("directive names end_block last", "end_block" in (result or {}).get("reason", ""))
    check("state flags wrapup_requested", read_state(project).get("wrapup_requested") is True)

    second_stop = run_hook("block_end.py", {"hook_event_name": "Stop", "stop_hook_active": False}, project)
    check("second stop is allowed through (no loop)", second_stop is None)

    write_state(project, start=iso(-55), duration_minutes=50)
    check(
        "stop_hook_active short-circuits",
        run_hook("block_end.py", {"hook_event_name": "Stop", "stop_hook_active": True}, project) is None,
    )

    print("\noverrun")
    write_state(project, start=iso(-70), duration_minutes=50, wrapup_requested=True)
    context = context_of(run_hook("block_status.py", {"hook_event_name": "UserPromptSubmit"}, project))
    check("overrun reported", "OVER by" in context, context[:80])
    check("wrap-up nudge present", "wrap-up" in context.lower())

    print("\nSessionStart")
    write_state(project, start=iso(-10), duration_minutes=50)
    context = context_of(run_hook("session_start.py", {"hook_event_name": "SessionStart"}, project))
    check("running block surfaced at session start", "ALREADY RUNNING" in context, context[:80])
    (project / "state" / "block.json").write_text('{"active": false}', encoding="utf-8")
    check("silent with nothing to report", run_hook("session_start.py", {"hook_event_name": "SessionStart"}, project) is None)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
