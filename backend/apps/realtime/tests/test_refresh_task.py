"""Tests for ``apps.realtime.tasks.refresh_iett_mapping``.

Celery is not started — the task is called as a plain function (the
``@shared_task`` decorator still lets it be invoked directly). Redis
is faked via ``fakeredis``; the İETT SOAP endpoint is stubbed with
``requests_mock``. No network, no broker.
"""
from __future__ import annotations

import json
from pathlib import Path

import fakeredis
import pytest
from freezegun import freeze_time

from apps.realtime.adapters.iett_soap import ARSIV_URL
from apps.realtime import tasks as tasks_module
from apps.realtime.tasks import (
    DAY_TYPE_MISMATCH_COUNT_KEY,
    MAPPING_CACHE_KEY,
    refresh_iett_mapping,
)

CASSETTES = Path(__file__).parent / "cassettes"


@pytest.fixture
def fake_redis(monkeypatch):
    """Share one FakeStrictRedis across every ``redis.from_url`` call
    made inside the task (client, limiters, lock)."""
    client = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(
        tasks_module.redis, "from_url",
        lambda *a, **kw: client,
    )
    return client


@pytest.fixture
def arsiv_ok_body() -> str:
    return (CASSETTES / "arsiv_gorev_20260422_ok.xml").read_text(encoding="utf-8")


@pytest.fixture
def arsiv_empty_body() -> str:
    return (CASSETTES / "arsiv_gorev_empty_today.xml").read_text(encoding="utf-8")


@pytest.fixture
def policy_falsified_body() -> str:
    return (CASSETTES / "policy_falsified_fault.xml").read_text(encoding="utf-8")


def _wrap_arsiv(body_json: str) -> str:
    """Inline helper for synthetic cassette bodies (metrobus-only test)."""
    entity = (
        body_json.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n'
        "  <soap:Body>\n"
        '    <GetIettArsivGorev_jsonResponse xmlns="http://tempuri.org/">\n'
        f"      <GetIettArsivGorev_jsonResult>{entity}</GetIettArsivGorev_jsonResult>\n"
        "    </GetIettArsivGorev_jsonResponse>\n"
        "  </soap:Body>\n"
        "</soap:Envelope>\n"
    )


# 2026-04-29 09:00 UTC = 2026-04-29 12:00 Europe/Istanbul → today=2026-04-29
# (Wednesday, normal weekday — no holiday). pick_target_date returns
# 2026-04-22 (last Wednesday) which matches the cassette/synthetic record
# DTBASLAMAZAMANI dates, so build_mapping's outside_snapshot skip rule
# does not throw the records away.
#
# The holiday-fallback branch (today=holiday → last Sunday) is covered
# by sentinel unit tests in test_calendar.py
# (test_pick_target_date_today_is_holiday_uses_last_sunday and
# test_pick_target_date_day_type_describes_target_not_today). The
# refresh-task end-to-end test stays on a normal weekday so that the
# fixed cassette dates remain semantically aligned.
FROZEN_NOW_UTC = "2026-04-29 09:00:00"
EXPECTED_TODAY = "2026-04-29"
EXPECTED_TARGET_DATE = "2026-04-22"
EXPECTED_DAY_TYPE = "weekday"


def test_refresh_success_end_to_end(fake_redis, arsiv_ok_body, requests_mock):
    """End-to-end refresh test on a normal weekday (FROZEN=2026-04-29 Wed).
    pick_target_date returns 2026-04-22 (last Wed) which matches the cassette
    timestamps. Holiday-fallback branch coverage lives in test_calendar.py
    (test_pick_target_date_today_is_holiday_uses_last_sunday)."""
    # freeze_time freezes time.monotonic too, so elapsed_seconds will be
    # exactly 0.0. All assertions that depend on TTL / Redis presence have
    # to stay inside the with-block: outside it, real wall clock is past
    # the frozen expiry and fakeredis returns None.
    requests_mock.post(ARSIV_URL, text=arsiv_ok_body, status_code=200)

    with freeze_time(FROZEN_NOW_UTC):
        result = refresh_iett_mapping()

        assert result["status"] == "ok"
        assert result["today"] == EXPECTED_TODAY
        assert result["target_date"] == EXPECTED_TARGET_DATE
        assert result["day_type"] == EXPECTED_DAY_TYPE
        # Cassette carries 502 parser-passed records (T + non-null start/end).
        assert result["records_received"] == 502
        assert result["active_routes_count"] > 0
        assert result["payload_bytes"] > 0
        assert result["elapsed_seconds"] >= 0  # frozen clock → 0.0

        # Redis side: key exists, JSON parses, structure matches build_mapping().
        raw = fake_redis.get(MAPPING_CACHE_KEY)
        assert raw is not None
        payload = json.loads(raw)
        assert payload["snapshot_date"] == EXPECTED_TARGET_DATE
        assert payload["snapshot_day_type"] == EXPECTED_DAY_TYPE
        assert set(payload) == {
            "snapshot_date", "snapshot_day_type",
            "by_kapi", "active_routes", "routes_by_mode",
        }
        assert set(payload["routes_by_mode"]) == {"metrobus", "bus"}
        assert len(payload["active_routes"]) == result["active_routes_count"]

        # TTL is ~28 h; accept ±120 s for test timing drift.
        ttl = fake_redis.ttl(MAPPING_CACHE_KEY)
        assert 28 * 3600 - 120 <= ttl <= 28 * 3600

    # The <Tarih> element in the posted envelope reflects target_date.
    assert "<Tarih>20260422</Tarih>" in requests_mock.last_request.text


def test_refresh_rate_limit_blocked(
    fake_redis, policy_falsified_body, requests_mock
):
    requests_mock.post(ARSIV_URL, text=policy_falsified_body, status_code=500)

    with freeze_time(FROZEN_NOW_UTC):
        # Seed stale cache INSIDE freeze_time so its TTL is relative to
        # the frozen clock too — otherwise real wall clock expires it.
        stale = (
            b'{"date":"2026-04-21","by_kapi":{},"active_routes":[],'
            b'"routes_by_mode":{"metrobus":[],"bus":[]}}'
        )
        fake_redis.set(MAPPING_CACHE_KEY, stale, ex=3600)

        result = refresh_iett_mapping()

        assert result["status"] == "error"
        assert result["error_type"] == "rate_limit_violation"
        assert result["target_date"] == EXPECTED_TARGET_DATE
        assert result["day_type"] == EXPECTED_DAY_TYPE

        # Stale cache must survive: task aborted before any write.
        assert fake_redis.get(MAPPING_CACHE_KEY) == stale

        # Adapter armed the cooldown on the archive limiter.
        assert fake_redis.exists("iett:ratelimit:arsiv:cooldown") == 1


def test_refresh_empty_response(fake_redis, arsiv_empty_body, requests_mock):
    requests_mock.post(ARSIV_URL, text=arsiv_empty_body, status_code=200)

    with freeze_time(FROZEN_NOW_UTC):
        result = refresh_iett_mapping()

        assert result["status"] == "ok"
        assert result["records_received"] == 0
        assert result["active_routes_count"] == 0
        assert result["metrobus_coverage"] == "0/10"
        assert len(result["metrobus_missing"]) == 10

        # Empty mapping is still a legitimate snapshot; Redis is written.
        raw = fake_redis.get(MAPPING_CACHE_KEY)
        assert raw is not None
        payload = json.loads(raw)
        assert payload["by_kapi"] == {}
        assert payload["active_routes"] == []


def test_refresh_metrobus_coverage_missing(fake_redis, requests_mock):
    # Synthetic: three metrobus routes active, seven missing.
    records = [
        {
            "SHATKODU": hat, "SGUZERGAHKODU": f"{hat}_G_D0",
            "SKAPINUMARA": f"M{i:04d}",
            "DTBASLAMAZAMANI": "/Date(1776863726000)/",
            "DTBITISZAMANI": "/Date(1776868886000)/",
            "SGOREVDURUM": "T",
        }
        for i, hat in enumerate(["34", "34A", "34B"])
    ]
    body = _wrap_arsiv(json.dumps(records, ensure_ascii=False))
    requests_mock.post(ARSIV_URL, text=body, status_code=200)

    with freeze_time(FROZEN_NOW_UTC):
        result = refresh_iett_mapping()

        assert result["status"] == "ok"
        assert result["records_received"] == 3
        assert result["active_routes_count"] == 3
        assert result["metrobus_coverage"] == "3/10"
        assert result["metrobus_missing"] == [
            "34AS", "34BZ", "34C", "34G", "34T", "34U", "34Z",
        ]


def test_refresh_timing_included(fake_redis, arsiv_empty_body, requests_mock):
    # freeze_time pins time.monotonic too, so elapsed_seconds == 0.0 here.
    # Under real wall clock (production) it's meaningful; the contract
    # we care about in tests is "the key is present in the result dict
    # and non-negative".
    requests_mock.post(ARSIV_URL, text=arsiv_empty_body, status_code=200)

    with freeze_time(FROZEN_NOW_UTC):
        result = refresh_iett_mapping()

    assert "elapsed_seconds" in result
    assert result["elapsed_seconds"] >= 0
    assert result["elapsed_seconds"] < 5.0


def test_refresh_resets_mismatch_counter(
    fake_redis, arsiv_ok_body, requests_mock,
):
    """5i-iv: success path overwrites stats:day_type_mismatch_count to 0,
    so a fresh day starts with zero recorded mismatches."""
    requests_mock.post(ARSIV_URL, text=arsiv_ok_body, status_code=200)
    fake_redis.set(DAY_TYPE_MISMATCH_COUNT_KEY, 42)  # leftover from prior day

    with freeze_time(FROZEN_NOW_UTC):
        result = refresh_iett_mapping()

        assert result["status"] == "ok"
        assert int(fake_redis.get(DAY_TYPE_MISMATCH_COUNT_KEY)) == 0
