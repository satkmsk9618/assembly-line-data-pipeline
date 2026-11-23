from datetime import date

import pytest
from fastapi import HTTPException

from assembly_line.api import _history_filter


def test_history_filter_is_inclusive_of_both_calendar_dates():
    where, params = _history_filter("f.end_ts", 24, date(2026, 11, 20), date(2026, 11, 22))
    assert where == " WHERE f.end_ts >= %s::date AND f.end_ts < (%s::date + INTERVAL '1 day')"
    assert params == [date(2026, 11, 20), date(2026, 11, 22)]


def test_history_filter_rejects_reversed_date_range():
    with pytest.raises(HTTPException) as error:
        _history_filter("end_ts", 24, date(2026, 11, 23), date(2026, 11, 22))
    assert error.value.status_code == 422


def test_all_time_filter_does_not_add_a_time_limit():
    where, params = _history_filter("f.end_ts", 24, None, None, all_time=True)

    assert where == ""
    assert params == []


def test_date_range_still_applies_when_all_time_flag_is_set():
    where, params = _history_filter("f.end_ts", 24, date(2026, 11, 20), date(2026, 11, 22), all_time=True)

    assert "f.end_ts >= %s::date" in where
    assert params == [date(2026, 11, 20), date(2026, 11, 22)]

