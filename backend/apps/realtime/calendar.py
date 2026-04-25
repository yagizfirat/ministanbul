"""Calendar / day-type helpers shared across realtime modules.

Phase 2 Step 5i-ii laid the stdlib-only foundation
(``ISTANBUL_TZ`` + ``_naive_day_type`` + ``_next_day_type_of``).
Phase 2 Step 5i-iii adds Turkish-holiday awareness on top:

  - ``TURKEY_HOLIDAYS`` — ``holidays.Turkey()`` dictionary, lazily computed
  - ``get_day_type(d)`` — like ``_naive_day_type`` but maps Turkish public
    holidays to ``"sunday"`` (İBB scheduling convention).
  - ``pick_target_date(today)`` — returns ``(target_date, day_type)`` for
    the daily refresh: prefers ``today - 7 days`` (last same weekday),
    falls back to ``today - 14`` if 7-day-back is a holiday, then to the
    last Sunday if even 14-day-back is a holiday.

The original 5i-ii helpers are retained as-is — admin metric code in
5i-iv will surface the snapshot ↔ today day-type relationship through
them, and ``pick_target_date`` itself relies on ``_naive_day_type`` /
``get_day_type`` rather than re-deriving the weekday math.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import holidays

logger = logging.getLogger(__name__)

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
TURKEY_HOLIDAYS = holidays.Turkey()


def _naive_day_type(d: date) -> str:
    """Stdlib weekday → day_type label, no holiday awareness.

    Mon-Fri → ``"weekday"``, Sat → ``"saturday"``, Sun → ``"sunday"``.
    Public holidays land on whatever weekday they fall on; the
    holidays-aware variant is :func:`get_day_type`.
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


def get_day_type(d: date) -> str:
    """Holidays-aware day_type — Turkish public holidays return ``"sunday"``.

    İBB schedules public-holiday service on the Sunday timetable, so the
    refresh task and any consumer that wants a "scheduling label" should
    use this rather than :func:`_naive_day_type` (which is naive about
    holidays).
    """
    if d in TURKEY_HOLIDAYS:
        return "sunday"
    return _naive_day_type(d)


def _last_sunday_before(d: date) -> date:
    """Most recent Sunday strictly before ``d``. If ``d`` itself is a
    Sunday, returns ``d - 7 days`` (the previous Sunday)."""
    days_back = d.weekday() + 1  # Mon=0 → 1, Sun=6 → 7
    return d - timedelta(days=days_back)


def pick_target_date(today: date) -> tuple[date, str]:
    """Pick which archive date to fetch + the day_type label to embed.

    Strategy:
      1. ``today`` is a Turkish public holiday → use last Sunday's archive
         (holidays run on Sunday timetable).
      2. Else: ``today - 7 days`` (last same weekday).
      3. If the 7-day-back candidate is itself a holiday → fall back to
         ``today - 14 days`` (filo change tolerance ~14 days).
      4. If the 14-day-back candidate is ALSO a holiday → log alarm,
         fall back to last Sunday.

    Returns ``(target_date, day_type)`` where ``day_type`` is always
    ``get_day_type(target_date)`` — i.e. the schedule type of the day the
    archive snapshot represents, not of ``today``. This keeps a single
    invariant: ``snapshot_day_type`` always describes ``snapshot_date``.
    """
    if today in TURKEY_HOLIDAYS:
        target = _last_sunday_before(today)
    else:
        candidate = today - timedelta(days=7)
        if candidate in TURKEY_HOLIDAYS:
            candidate_14 = today - timedelta(days=14)
            if candidate_14 in TURKEY_HOLIDAYS:
                logger.warning(
                    "pick_target_date: both 7-day and 14-day fallback are "
                    "holidays (today=%s, 7d=%s, 14d=%s) — using last Sunday",
                    today, candidate, candidate_14,
                )
                target = _last_sunday_before(today)
            else:
                target = candidate_14
        else:
            target = candidate

    return target, get_day_type(target)
