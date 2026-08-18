"""SessionStart: orient Claude before the first message.

Answers, in one short block: is a block already running (e.g. the session was
restarted mid-block), how many reviews are waiting, and when the next block is.
Everything else Claude can look up on demand — this stays terse on purpose.
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
    next_block,
    parse_iso,
    read_block_state,
)


def main():
    parts = []
    state = read_block_state()
    reference = local_now()

    if state.get("active"):
        parts.append("A study block is ALREADY RUNNING: " + (block_line(state, reference) or ""))
        remaining = float(state.get("duration_minutes") or 0) - elapsed_minutes(state, reference)
        if remaining <= 0:
            parts.append(
                "It has already overrun. Run the wrap-up and call end_block, or clear_block_state "
                "if this is stale state left by a crash."
            )
        if state.get("solo_mode"):
            parts.append(SOLO_RULE)
    else:
        overdue, today = due_counts()
        if overdue or today:
            parts.append(
                "Reviews waiting: %d overdue, %d due today. They are fetched live at block start "
                "with review_queue — never pre-allocated." % (overdue, today)
            )
        upcoming = next_block()
        if upcoming:
            start = parse_iso(upcoming.get("start"))
            when = (
                "in " + humanize((start - reference).total_seconds() / 60.0)
                if start
                else upcoming.get("start")
            )
            parts.append(
                "Next scheduled block: %s%s, %s (%s)."
                % (
                    upcoming.get("kind") or "study",
                    " on " + upcoming["subject"] if upcoming.get("subject") else "",
                    when,
                    upcoming.get("topic") or "topic not set",
                )
            )

    if not parts:
        return 0
    parts.append("Learning Harness is active. See CLAUDE.md for the protocol; /status for the full picture.")
    emit_context("SessionStart", "\n".join(parts))
    return 0


if __name__ == "__main__":
    guard(main)
