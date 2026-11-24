from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

DAY = 86400
SEASONAL_TYPES = ("spring", "summer", "autumn", "black_friday", "winter")
# Sales open 10am Pacific (~18:00 UTC); we use that as the boundary time.
_OPEN_HOUR_UTC = 18

# Which historical "slot" an upcoming event type is judged against.
TYPE_TO_SLOT = {"spring": "spring", "summer": "summer", "autumn": "autumn",
                "black_friday": "autumn", "winter": "winter"}

# Deliberately wide windows so date drift between years (Autumn Sale moved from late Nov to Oct) is
# still captured. Each slot is a list of (start_month, start_day, end_month, end_day[, year_offset]).
SEASON_WINDOWS = {
    "spring": [((3, 8), (3, 31))],
    "summer": [((6, 15), (7, 14))],
    "autumn": [((9, 28), (12, 6))],  # one window: the sale moved between early Oct and late Nov
    "winter": [((12, 10), (1, 8))],  # crosses new year
}

# Typical depth multiplier vs. a game's overall seasonal depth (Summer/Winter are the deepest).
DEPTH_MULT = {"summer": 1.0, "winter": 1.0, "autumn": 0.95, "spring": 0.9, "black_friday": 0.95}


@dataclass(frozen=True)
class Event:
    name: str
    type: str
    start_ts: int
    end_ts: int
    confirmed: bool

    def as_dict(self) -> dict:
        return {
            "name": self.name, "type": self.type, "confirmed": self.confirmed,
            "start": datetime.fromtimestamp(self.start_ts, timezone.utc).date().isoformat(),
            "end": datetime.fromtimestamp(self.end_ts, timezone.utc).date().isoformat(),
        }


def _ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, _OPEN_HOUR_UTC, tzinfo=timezone.utc).timestamp())


def _parse(d: str) -> date:
    return date.fromisoformat(d)


def _black_friday(year: int) -> date:
    # Friday after the 4th Thursday of November
    d = date(year, 11, 1)
    first_thu = d + timedelta(days=(3 - d.weekday()) % 7)
    return first_thu + timedelta(days=7 * 3 + 1)


def _estimated_for_year(year: int) -> list[Event]:
    bf = _black_friday(year)
    return [
        Event(f"Steam Spring Sale {year} (est.)", "spring", _ts(date(year, 3, 18)), _ts(date(year, 3, 25)), False),
        Event(f"Steam Summer Sale {year} (est.)", "summer", _ts(date(year, 6, 24)), _ts(date(year, 7, 8)), False),
        Event(f"Steam Autumn Sale {year} (est.)", "autumn", _ts(date(year, 10, 1)), _ts(date(year, 10, 8)), False),
        Event(f"Black Friday deals {year} (est.)", "black_friday", _ts(bf - timedelta(days=3)),
              _ts(bf + timedelta(days=4)), False),
        Event(f"Steam Winter Sale {year} (est.)", "winter", _ts(date(year, 12, 17)), _ts(date(year + 1, 1, 4)), False),
    ]


def load_events(path: str) -> list[Event]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        raw = {"events": []}
    return [
        Event(e["name"], e["type"], _ts(_parse(e["start"])), _ts(_parse(e["end"])), bool(e.get("confirmed")))
        for e in raw.get("events", [])
    ]


def upcoming(events: list[Event], now: int, horizon_days: int = 400) -> list[Event]:
    """Published events still to come (or in progress) plus estimates filling any seasonal slot that
    Valve has not published yet. Sorted by start."""
    end = now + horizon_days * DAY
    out = [e for e in events if e.end_ts >= now and e.start_ts <= end]
    covered = {(e.type, datetime.fromtimestamp(e.start_ts, timezone.utc).year) for e in events}
    y0 = datetime.fromtimestamp(now, timezone.utc).year
    for year in range(y0, y0 + 3):
        for est in _estimated_for_year(year):
            est_year = datetime.fromtimestamp(est.start_ts, timezone.utc).year
            if (est.type, est_year) in covered:
                continue
            if est.end_ts >= now and est.start_ts <= end:
                out.append(est)
    return sorted(out, key=lambda e: e.start_ts)


def season_slots(first_ts: int, now: int, only_complete: bool = True) -> list[tuple[str, int, int]]:
    """Season windows (slot, start_ts, end_ts) overlapping the period we have watched.

    With only_complete=True only fully-elapsed windows that began after we started watching are returned
    (used to measure participation fairly)."""
    y0 = datetime.fromtimestamp(first_ts, timezone.utc).year - 1
    y1 = datetime.fromtimestamp(now, timezone.utc).year
    slots = []
    for year in range(y0, y1 + 1):
        for slot, windows in SEASON_WINDOWS.items():
            for (m1, d1), (m2, d2) in windows:
                start = date(year, m1, d1)
                end = date(year + (1 if (m2, d2) < (m1, d1) else 0), m2, d2)
                s, e = _ts(start), _ts(end)
                if only_complete:
                    if s >= first_ts - 7 * DAY and e <= now:
                        slots.append((slot, s, e))
                elif e >= first_ts - 30 * DAY and s <= now + 30 * DAY:
                    slots.append((slot, s, e))
    return slots
