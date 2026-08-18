"""Blocked-time sources behind one interface.

PRD open question #1 is answered for now as: **own store, integration-ready.**
Everything the scheduler needs is expressed as :meth:`CalendarProvider.busy` —
a flat list of concrete busy intervals over a date range. That is deliberately
the exact shape of Google Calendar's ``freebusy.query`` response, so
:class:`GoogleCalendarProvider` becomes a credentials-and-HTTP problem rather
than a redesign.

Local store format (``state/calendar.json``)::

    {"commitments": [
      {"id": "...", "title": "Lectures", "weekdays": ["mon","wed"],
       "start_time": "10:00", "end_time": "13:30",
       "from_date": "2026-09-01", "until_date": null},
      {"id": "...", "title": "Dentist",
       "start": "2026-08-10T15:00:00+03:00", "end": "2026-08-10T16:00:00+03:00"}
    ]}
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from abc import ABC, abstractmethod
from typing import Any, Iterable, Optional

from .config import get_settings
from .timeutil import LOCAL_TZ, day_start, now, parse, to_iso

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
WEEKDAY_NAMES = {v: k for k, v in WEEKDAYS.items()}


class Interval:
    """A half-open busy interval ``[start, end)``."""

    __slots__ = ("start", "end", "title", "source")

    def __init__(self, start: dt.datetime, end: dt.datetime, title: str = "busy", source: str = "calendar"):
        self.start, self.end, self.title, self.source = start, end, title, source

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": to_iso(self.start),
            "end": to_iso(self.end),
            "title": self.title,
            "source": self.source,
            "minutes": int((self.end - self.start).total_seconds() // 60),
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Interval({self.title!r}, {to_iso(self.start)} -> {to_iso(self.end)})"


class CalendarProvider(ABC):
    @abstractmethod
    def busy(self, start: dt.datetime, end: dt.datetime) -> list[Interval]:
        """Concrete busy intervals overlapping ``[start, end)``."""

    @abstractmethod
    def list_commitments(self) -> list[dict[str, Any]]:
        ...

    def add_commitment(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(f"{type(self).__name__} is read-only")

    def remove_commitment(self, commitment_id: str) -> dict[str, Any]:
        raise NotImplementedError(f"{type(self).__name__} is read-only")


class LocalJsonCalendar(CalendarProvider):
    """The default: a small JSON file the user and the agent can both edit."""

    def __init__(self, path: Optional[Any] = None):
        self.path = path or get_settings().calendar_path

    # --- persistence ---------------------------------------------------
    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"commitments": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"commitments": []}
        data.setdefault("commitments", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- API -----------------------------------------------------------
    def list_commitments(self) -> list[dict[str, Any]]:
        return self._load()["commitments"]

    def add_commitment(
        self,
        title: str,
        weekdays: Optional[Iterable[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        from_date: Optional[str] = None,
        until_date: Optional[str] = None,
        **_: Any,
    ) -> dict[str, Any]:
        data = self._load()
        entry: dict[str, Any] = {"id": uuid.uuid4().hex[:8], "title": title}
        if weekdays:
            normalized = [str(d).strip().lower()[:3] for d in weekdays]
            unknown = [d for d in normalized if d not in WEEKDAYS]
            if unknown:
                raise ValueError(f"unknown weekday(s): {unknown}; use mon..sun")
            if not (start_time and end_time):
                raise ValueError("recurring commitments need start_time and end_time (HH:MM)")
            entry.update(
                weekdays=normalized,
                start_time=start_time,
                end_time=end_time,
                from_date=from_date,
                until_date=until_date,
            )
        elif start and end:
            entry.update(start=to_iso(parse(start)), end=to_iso(parse(end)))
        else:
            raise ValueError("give either weekdays+start_time+end_time, or start+end")
        data["commitments"].append(entry)
        self._save(data)
        return entry

    def remove_commitment(self, commitment_id: str) -> dict[str, Any]:
        data = self._load()
        before = len(data["commitments"])
        data["commitments"] = [c for c in data["commitments"] if c["id"] != commitment_id]
        self._save(data)
        return {"removed": before - len(data["commitments"]), "id": commitment_id}

    def busy(self, start: dt.datetime, end: dt.datetime) -> list[Interval]:
        out: list[Interval] = []
        for c in self.list_commitments():
            if "weekdays" in c:
                out.extend(self._expand_recurring(c, start, end))
            else:
                s, e = parse(c["start"]), parse(c["end"])
                if s < end and start < e:
                    out.append(Interval(s, e, c.get("title", "busy"), "commitment"))
        return sorted(out, key=lambda i: i.start)

    @staticmethod
    def _expand_recurring(c: dict[str, Any], start: dt.datetime, end: dt.datetime) -> list[Interval]:
        wanted = {WEEKDAYS[d] for d in c["weekdays"]}
        sh, sm = (int(x) for x in c["start_time"].split(":"))
        eh, em = (int(x) for x in c["end_time"].split(":"))
        from_date = parse(c["from_date"]).date() if c.get("from_date") else None
        until_date = parse(c["until_date"]).date() if c.get("until_date") else None
        out: list[Interval] = []
        cursor = day_start(start)
        while cursor < end:
            date = cursor.date()
            if (
                cursor.weekday() in wanted
                and (from_date is None or date >= from_date)
                and (until_date is None or date <= until_date)
            ):
                s = cursor.replace(hour=sh, minute=sm)
                e = cursor.replace(hour=eh, minute=em)
                if e <= s:  # crosses midnight
                    e += dt.timedelta(days=1)
                if s < end and start < e:
                    out.append(Interval(s, e, c.get("title", "busy"), "commitment"))
            cursor += dt.timedelta(days=1)
        return out


class GoogleCalendarProvider(CalendarProvider):
    """Placeholder for the Google integration (PRD open question #1).

    The seam is already correct: implement ``busy()`` with a ``freebusy.query``
    call and the scheduler needs no changes. Commitment mutation stays local —
    the harness should not write to a user's real calendar without being asked.
    """

    SETUP = (
        "Not implemented yet. To add it: create a Google Cloud project, enable the Calendar API, "
        "download an OAuth client secret, then implement busy() with a freebusy.query over the "
        "chosen calendar IDs and set calendar_provider='google' in config.json."
    )

    def busy(self, start: dt.datetime, end: dt.datetime) -> list[Interval]:
        raise NotImplementedError(self.SETUP)

    def list_commitments(self) -> list[dict[str, Any]]:
        raise NotImplementedError(self.SETUP)


def get_calendar() -> CalendarProvider:
    provider = get_settings().calendar_provider.lower()
    if provider == "google":
        return GoogleCalendarProvider()
    return LocalJsonCalendar()


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """Coalesce overlapping busy intervals so window subtraction stays simple."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda i: i.start)
    merged = [Interval(ordered[0].start, ordered[0].end, ordered[0].title, ordered[0].source)]
    for item in ordered[1:]:
        last = merged[-1]
        if item.start <= last.end:
            if item.end > last.end:
                last.end = item.end
                last.title = f"{last.title} + {item.title}" if item.title not in last.title else last.title
        else:
            merged.append(Interval(item.start, item.end, item.title, item.source))
    return merged


def default_horizon() -> tuple[dt.datetime, dt.datetime]:
    settings = get_settings()
    start = now()
    return start, start + dt.timedelta(days=settings.scheduling_horizon_days)


__all__ = [
    "Interval",
    "CalendarProvider",
    "LocalJsonCalendar",
    "GoogleCalendarProvider",
    "get_calendar",
    "merge_intervals",
    "default_horizon",
    "LOCAL_TZ",
]
