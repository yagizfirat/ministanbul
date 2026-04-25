"""Calendar / day-type helpers shared across realtime modules.

Phase 2 Step 5i-ii: stdlib-only foundation. Mapping (build_mapping)
embeds ``snapshot_day_type`` derived here; enrich uses these helpers
for per-vehicle overnight detection; the refresh task picks the target
date through them.

5i-iii will add ``holidays.Turkey()`` integration plus a holidays-aware
``get_day_type()`` and ``pick_target_date()`` on top of this module —
without touching the public surface defined here (only adding new
functions).
"""
from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")


def _naive_day_type(d: date) -> str:
    """Stdlib weekday → day_type label, no holiday awareness.

    Mon-Fri → ``"weekday"``, Sat → ``"saturday"``, Sun → ``"sunday"``.
    Public holidays land on whatever weekday they fall on; 5i-iii will
    introduce ``get_day_type()`` that maps them to ``"sunday"`` per
    İBB scheduling convention.
    """
    weekday = d.weekday()
    if weekday == 5:
        return "saturday"
    if weekday == 6:
        return "sunday"
    return "weekday"


def _next_day_type_of(snapshot_date_str: str) -> str:
    """Day-type label for the day AFTER ``snapshot_date_str`` (ISO format).

    Currently unused after the 5i-ii overnight check pivoted to date-based
    equality. Retained here for 5i-iv admin metrics, where it will surface
    the mapping ↔ today day-type relationship (e.g. "Mapping snapshot:
    weekday — today is also weekday, alignment ok").
    """
    snap = date.fromisoformat(snapshot_date_str)
    return _naive_day_type(snap + timedelta(days=1))
