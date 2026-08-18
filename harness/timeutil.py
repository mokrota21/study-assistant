"""Time helpers.

Convention for the whole harness: every timestamp that crosses a process
boundary (SQLite, JSON state files, MCP tool arguments and results) is an
ISO-8601 string *with an explicit UTC offset*, e.g. ``2026-08-06T19:30:00+03:00``.

Two reasons:
  * ``datetime.fromisoformat`` in Python 3.8 (the system interpreter the
    Claude Code hooks run on) parses offsets but not a trailing ``Z``.
  * FSRS works in UTC internally; scheduling is inherently local. Carrying the
    offset lets both sides convert without guessing.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

LOCAL_TZ = dt.datetime.now().astimezone().tzinfo


def now() -> dt.datetime:
    """Timezone-aware 'now' in the machine's local zone."""
    return dt.datetime.now(tz=LOCAL_TZ)


def to_iso(value: dt.datetime) -> str:
    """Serialize an aware datetime to offset-carrying ISO-8601 (second precision)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=LOCAL_TZ)
    return value.isoformat(timespec="seconds")


def parse(value: str | dt.datetime | None, default: Optional[dt.datetime] = None) -> dt.datetime:
    """Parse an ISO-8601 string into an aware datetime.

    Accepts a trailing ``Z``, a bare date (``2026-08-06`` -> midnight local),
    and naive timestamps (assumed local). Never returns a naive datetime.
    """
    if value is None:
        return default if default is not None else now()
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        text = value.strip()
        if not text:
            return default if default is not None else now()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        text = text.replace(" ", "T", 1) if " " in text and "T" not in text else text
        parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed


def to_utc(value: dt.datetime) -> dt.datetime:
    """Convert to an aware UTC datetime (what FSRS expects)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=LOCAL_TZ)
    return value.astimezone(dt.timezone.utc)


def to_local(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(LOCAL_TZ)


def day_start(value: dt.datetime) -> dt.datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def local_date(value: dt.datetime) -> str:
    """``YYYY-MM-DD`` in local time — the key used for 'distinct study days'."""
    return to_local(value).strftime("%Y-%m-%d")


def humanize_minutes(minutes: float) -> str:
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes}m"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h{rest:02d}m" if rest else f"{hours}h"


def humanize_delta(target: dt.datetime, reference: Optional[dt.datetime] = None) -> str:
    """'in 3d', 'overdue 2h' — for review queue readability."""
    reference = reference or now()
    seconds = (target - reference).total_seconds()
    overdue = seconds < 0
    seconds = abs(seconds)
    if seconds < 3600:
        amount = f"{int(seconds // 60)}m"
    elif seconds < 86400:
        amount = f"{seconds / 3600:.1f}h"
    else:
        amount = f"{seconds / 86400:.1f}d"
    return f"overdue {amount}" if overdue else f"in {amount}"
