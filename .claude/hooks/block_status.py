"""UserPromptSubmit + PostToolUse: inject the block clock into context (PRD §3.4.1, items 2-3).

Hooks always run. Instructions do not — the model forgets them as context fills,
which is exactly why time awareness is not left to a system prompt line.

On user messages this fires every time (cheap, and the user's turn is the natural
place for a status line). On tool calls it is throttled, so a long agent-driven
stretch stays covered without spamming a line after every file read.
"""

from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (  # noqa: E402
    SOLO_RULE,
    block_line,
    due_counts,
    elapsed_minutes,
    emit_context,
    guard,
    humanize,
    local_now,
    read_block_state,
    read_hook_input,
    throttled,
)

TOOL_THROTTLE_SECONDS = 180
CRITICAL_TAIL_MINUTES = 5


def build_context(state, event):
    reference = local_now()
    line = block_line(state, reference)
    if not line:
        return None

    parts = [line]
    duration = float(state.get("duration_minutes") or 0)
    remaining = duration - elapsed_minutes(state, reference)

    if state.get("solo_mode"):
        parts.append(SOLO_RULE)

    segment = state.get("segment")
    budget = float(state.get("review_segment_minutes") or 0)
    if segment == "review" and budget:
        overdue, _today = due_counts()
        if overdue:
            parts.append(
                "%d overdue review(s) outstanding. Overdue reviews are mandatory before new material - "
                "structurally, not by willpower. If they overflow the segment they eat into new-material "
                "time, and that is the design working: many failed reviews mean the pace is too fast."
                % overdue
            )

    if remaining <= 0:
        parts.append(
            "The block is over. Converge now: finish the current exercise, then run the wrap-up "
            "(notes, covered.md, pool deposits, next-lesson prep) and call end_block."
        )
    elif remaining <= CRITICAL_TAIL_MINUTES:
        parts.append(
            "%s left. Do not start a new concept or a long exercise - begin converging toward wrap-up."
            % humanize(remaining)
        )

    return "\n".join(parts)


def main():
    payload = read_hook_input()
    event = payload.get("hook_event_name") or "UserPromptSubmit"
    state = read_block_state()
    if not state.get("active"):
        return 0

    reference = local_now()
    remaining = float(state.get("duration_minutes") or 0) - elapsed_minutes(state, reference)
    critical = remaining <= CRITICAL_TAIL_MINUTES

    if event == "PostToolUse" and not critical:
        if throttled("post_tool_use", TOOL_THROTTLE_SECONDS, reference):
            return 0

    emit_context(event, build_context(state, event))
    return 0


if __name__ == "__main__":
    guard(main)
