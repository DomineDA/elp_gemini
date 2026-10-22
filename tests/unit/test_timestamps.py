from datetime import datetime, timedelta, timezone

from app.utils.timestamps import utc_iso


def test_naive_is_treated_as_utc():
    value = datetime(2026, 10, 21, 10, 36, 54)
    assert utc_iso(value) == "2026-10-21T10:36:54+00:00"


def test_none_passes_through():
    assert utc_iso(None) is None


def test_aware_is_converted_to_utc():
    kst = timezone(timedelta(hours=9))
    value = datetime(2026, 10, 21, 19, 36, 54, tzinfo=kst)
    assert utc_iso(value) == "2026-10-21T10:36:54+00:00"
