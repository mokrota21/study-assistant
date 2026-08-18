"""Stop hook: refuse to stop at block end and inject the wrap-up directive (PRD §3.4.1, item 4).

This is what makes block-end automation deterministic rather than something the
model may or may not remember to do. It fires exactly once per block: the
`wrapup_requested` flag in the state file is set the first time, so a second Stop
is allowed through even if the wrap-up was imperfect. `stop_hook_active` is
honoured too, so there is no way to trap the session in a loop.
"""

from __future__ import print_function

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (  # noqa: E402
    WRAPUP_DIRECTIVE,
    elapsed_minutes,
    guard,
    local_now,
    read_block_state,
    read_hook_input,
    write_block_state,
)


def main():
    payload = read_hook_input()
    if payload.get("stop_hook_active"):
        return 0

    state = read_block_state()
    if not state.get("active"):
        return 0
    if state.get("wrapup_requested") or state.get("wrapup_done"):
        return 0

    duration = float(state.get("duration_minutes") or 0)
    if elapsed_minutes(state, local_now()) < duration:
        return 0

    state["wrapup_requested"] = True
    write_block_state(state)

    sys.stdout.write(
        json.dumps(
            {
                "decision": "block",
                "reason": WRAPUP_DIRECTIVE,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    guard(main)
