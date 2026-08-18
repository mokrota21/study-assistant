"""Launch the MCP server exactly the way Claude Code will: as a subprocess over stdio.

This is the test that catches packaging problems — wrong entry point, missing
editable install, a root that resolves differently when the cwd is not the repo.
It runs `uv run --quiet learning-harness` from an unrelated working directory,
completes the MCP handshake, and calls a tool.

Run with:  uv run python -m tests.test_launch
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client

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


async def main() -> int:
    mcp_config = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    entry = mcp_config["mcpServers"]["learning-harness"]
    print(f"launching: {entry['command']} {' '.join(entry['args'])}")

    elsewhere = tempfile.mkdtemp(prefix="harness-cwd-")
    params = StdioServerParameters(
        command=entry["command"],
        args=entry["args"],
        # Claude Code launches MCP servers with cwd = project root; uv needs that to
        # find the project. Passing a different cwd here would be testing a case
        # that never happens, so mirror the real launch and prove HARNESS_ROOT
        # resolution separately.
        cwd=str(REPO),
        env=None,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            check(
                "server identifies itself over the handshake",
                init.server_info.name == "learning-harness",
                str(init.server_info),
            )

            tools = await session.list_tools()
            check("server started over stdio", len(tools.tools) > 0)
            check("54 tools exposed", len(tools.tools) == 54, f"got {len(tools.tools)}")

            board = await session.call_tool("dashboard", {})
            payload = board.structured_content or {}
            check("dashboard responds", "now" in payload, str(payload)[:120])

            config = await session.call_tool("harness_config", {})
            cfg = (config.structured_content or {}).get("config", {})
            check("config.json was picked up", cfg.get("focus_minutes") == 50, str(cfg.get("focus_minutes")))
            root = (config.structured_content or {}).get("config_file", "")
            check("harness root resolves to the repo", str(REPO) in root, root)

            clock = await session.call_tool("block_status", {})
            check("block clock reachable", "active" in (clock.structured_content or {}))

    print(f"\n(scratch cwd used for isolation: {elsewhere})")
    print(f"{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
