"""Verify the MCP server exposes every tool and answers over the wire.

Runs the server in-process through the MCP client, so it exercises the real
schema generation Claude Code will see.

Run with:  uv run python -m tests.test_mcp
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="harness-mcp-"))
os.environ["HARNESS_ROOT"] = str(TMP)
os.environ["HARNESS_NOTIFICATIONS_ENABLED"] = "false"
(TMP / "subjects").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import Client  # noqa: E402

from harness.server import mcp  # noqa: E402

EXPECTED = {
    "create_subject", "list_subjects", "subject_layout", "log_covered", "notes_skeleton",
    "register_concepts", "list_concept_graph", "set_concept_status", "check_gate", "learning_frontier",
    "seed_cards", "review_queue", "grade_review", "review_forecast", "card_overview", "suspend_concept",
    "mastery_check", "record_practice", "stuck_hatch", "revoke_mastery", "delayed_rechecks",
    "remediation_check", "harness_health", "log_grading_spotcheck",
    "add_commitment", "list_commitments", "remove_commitment", "available_windows", "propose_schedule",
    "place_block", "list_blocks", "update_block", "agenda",
    "start_block", "block_status", "set_segment", "set_solo_mode", "pause_block", "resume_block",
    "extend_block", "end_block", "clear_block_state",
    "deposit_pool_item", "list_pool_items", "publish_pools", "kolokvium_check", "exam_check",
    "draw_ticket", "formulation_gate", "announce_assessment", "schedule_assessment",
    "record_assessment_result", "harness_config", "dashboard",
}


async def main() -> int:
    failures = 0
    async with Client(mcp, raise_exceptions=True) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        missing = EXPECTED - names
        extra = names - EXPECTED
        print(f"tools exposed: {len(names)}")
        if missing:
            print(f"  FAIL missing tools: {sorted(missing)}")
            failures += 1
        if extra:
            print(f"  note extra tools: {sorted(extra)}")
        if not missing:
            print("  ok   every expected tool is exposed")

        undocumented = [t.name for t in tools.tools if not (t.description or "").strip()]
        if undocumented:
            print(f"  FAIL tools without a description: {undocumented}")
            failures += 1
        else:
            print("  ok   every tool carries a description")

        # A real round trip through the protocol.
        result = await client.call_tool("create_subject", {"subject": "Wire Test", "mode": "exploratory"})
        payload = result.structured_content or {}
        if payload.get("subject") != "wire-test":
            print(f"  FAIL create_subject returned {payload}")
            failures += 1
        else:
            print("  ok   create_subject round trip")

        await client.call_tool(
            "register_concepts",
            {"subject": "wire-test", "items": [{"name": "Alpha"}, {"name": "Beta", "prereqs": ["Alpha"]}]},
        )
        gate = await client.call_tool("check_gate", {"subject": "wire-test", "concept": "Beta"})
        if (gate.structured_content or {}).get("allowed") is not False:
            print(f"  FAIL check_gate returned {gate.structured_content}")
            failures += 1
        else:
            print("  ok   check_gate round trip (nested list/dict args and results)")

        board = await client.call_tool("dashboard", {})
        if "now" not in (board.structured_content or {}):
            print(f"  FAIL dashboard returned {board.structured_content}")
            failures += 1
        else:
            print("  ok   dashboard round trip")

    print("\nMCP wire test:", "FAILED" if failures else "passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

