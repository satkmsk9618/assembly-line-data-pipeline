from datetime import date, datetime, timezone

from assembly_line.scheduled_reports import due_preferences


def test_due_report_uses_user_timezone_and_only_once_for_local_day():
    rows = [
        {"timezone": "Asia/Kolkata", "send_hour": 9, "last_sent_local_date": None},
        {"timezone": "UTC", "send_hour": 20, "last_sent_local_date": None},
    ]
    due = due_preferences(rows, datetime(2026, 11, 23, 4, 0, tzinfo=timezone.utc))
    assert due == [(rows[0], date(2026, 11, 22))]


def test_due_report_skips_when_local_day_already_sent():
    row = {"timezone": "UTC", "send_hour": 9, "last_sent_local_date": date(2026, 11, 22)}
    assert due_preferences([row], datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)) == []

