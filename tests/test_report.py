from datetime import datetime, timedelta, timezone
from pathlib import Path

from assembly_line.generate import generate
from assembly_line import report as daily_report
from assembly_line.report import build_report, create_message, render_html, render_text, send_report
from assembly_line.transform import run_pipeline


def test_report_only_counts_events_inside_trailing_day(tmp_path: Path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    generate(tmp_path / "raw", vehicles=12, seed=11, start_at=now - timedelta(hours=20))
    run_pipeline(tmp_path / "raw", tmp_path / "processed")

    report = build_report(tmp_path / "processed", generated_at=now, window_hours=24)

    assert report["summary"]["vehicles_processed"] > 0
    assert report["summary"]["station_events"] >= report["summary"]["vehicles_processed"]
    assert report["window_start"] == now - timedelta(hours=24)
    assert "synthetic" in render_text(report)
    assert "Station detail" in render_html(report)


def test_report_message_has_html_and_plain_text_parts():
    now = datetime.now(timezone.utc)
    report = {
        "window_start": now - timedelta(hours=24), "window_end": now, "window_hours": 24,
        "summary": {
            "vehicles_processed": 2, "station_events": 10, "avg_cycle_minutes": 7.5,
            "first_pass_yield_pct": 100.0, "defect_records": 0, "downtime_events": 0,
            "bottleneck_station": "ST-01",
        },
        "stations": [{"station_id": "ST-01", "events": 2,
                      "avg_cycle_minutes": 7.5, "takt_deviation_minutes": -0.5,
                      "rework_events": 0}],
        "downtime_minutes": 0.0,
    }
    message = create_message(report, "owner@example.com", "report@example.com")

    assert message["To"] == "owner@example.com"
    assert message.get_content_type() == "multipart/alternative"
    assert "First-pass yield" in message.get_body(preferencelist=("plain",)).get_content()
    assert "Assembly Line Daily Report" in message.get_body(preferencelist=("html",)).get_content()


def test_email_sender_requires_secrets_without_opening_connection():
    try:
        send_report({}, environ={})
    except RuntimeError as exc:
        assert "REPORT_SMTP_PASSWORD" in str(exc)
    else:
        raise AssertionError("missing email settings should fail before sending")


def test_email_sender_uses_starttls_and_delivers_message(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self, context):
            calls.append(("starttls", context is not None))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message["To"], message["Subject"]))

    monkeypatch.setattr(daily_report.smtplib, "SMTP", FakeSMTP)
    now = datetime.now(timezone.utc)
    report = {
        "window_start": now - timedelta(hours=24), "window_end": now, "window_hours": 24,
        "summary": {}, "stations": [], "downtime_minutes": 0.0,
    }

    send_report(report, environ={
        "REPORT_EMAIL_TO": "owner@example.com", "REPORT_EMAIL_FROM": "report@example.com",
        "REPORT_SMTP_HOST": "smtp.example.com", "REPORT_SMTP_PORT": "587",
        "REPORT_SMTP_USERNAME": "report@example.com", "REPORT_SMTP_PASSWORD": "private-secret",
    })

    assert calls[0] == ("connect", "smtp.example.com", 587, 30)
    assert ("starttls", True) in calls
    assert ("send", "owner@example.com", f"Assembly line daily report — {now:%Y-%m-%d}") in calls
