"""Send opted-in users a PDF report for their last completed local day."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from email.message import EmailMessage
import os
import smtplib
import ssl
from zoneinfo import ZoneInfo

import pandas as pd

from assembly_line.db import connect
from assembly_line.report_pdf import create_daily_pdf
from assembly_line.transform import calculate_metrics


def due_preferences(rows: list[dict], now: datetime) -> list[tuple[dict, date]]:
    """Return opted-in reports whose local send time has passed, once per day."""
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    due = []
    for row in rows:
        local_now = now.astimezone(ZoneInfo(row["timezone"]))
        latest_complete_day = local_now.date() - timedelta(days=1)
        last_sent = row.get("last_sent_local_date")
        report_day = last_sent + timedelta(days=1) if last_sent else latest_complete_day
        if local_now.hour >= int(row["send_hour"]) and report_day <= latest_complete_day:
            due.append((row, report_day))
    return due


def build_database_report(report_day: date, zone: ZoneInfo) -> dict:
    """Read a completed local calendar day from persistent PostgreSQL facts."""
    local_start = datetime.combine(report_day, time.min, tzinfo=zone)
    local_end = datetime.combine(report_day + timedelta(days=1), time.min, tzinfo=zone)
    start, end = local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)
    with connect() as conn:
        events = pd.DataFrame(conn.execute("""WITH completed AS (
                SELECT vehicle_id FROM fact_station_event GROUP BY vehicle_id
                HAVING max(end_ts) >= %s AND max(end_ts) < %s
            ) SELECT f.vehicle_id, f.station_id, f.cycle_time_minutes, f.status
              FROM fact_station_event f JOIN completed c USING(vehicle_id)""", (start, end)).fetchall())
        defects = pd.DataFrame(conn.execute("""WITH completed AS (
                SELECT vehicle_id FROM fact_station_event GROUP BY vehicle_id
                HAVING max(end_ts) >= %s AND max(end_ts) < %s
            ) SELECT d.vehicle_id, d.station_id, t.defect_type, d.severity, d.rework_flag
              FROM fact_defect d JOIN dim_defect t USING(defect_id)
              JOIN completed c USING(vehicle_id)""", (start, end)).fetchall())
        downtime = pd.DataFrame(conn.execute("""SELECT station_id, reason_code, start_ts, end_ts
            FROM fact_downtime WHERE end_ts >= %s AND end_ts < %s""", (start, end)).fetchall())

    if events.empty:
        metrics = {"summary": {}, "stations": []}
        quality, stops = [], []
    else:
        metrics = calculate_metrics(events, defects, downtime)
        station_frame = events.groupby("station_id").agg(
            events=("vehicle_id", "size"), avg_cycle_minutes=("cycle_time_minutes", "mean"),
            p90_cycle_minutes=("cycle_time_minutes", lambda values: values.quantile(.90)),
            over_takt_events=("cycle_time_minutes", lambda values: int((values > 8).sum())),
            rework_events=("status", lambda values: int((values == "rework").sum())),
        ).reset_index()
        station_frame["rework_rate_pct"] = 100 * station_frame["rework_events"] / station_frame["events"]
        metrics["stations"] = station_frame.round(2).sort_values("avg_cycle_minutes", ascending=False).to_dict("records")
        if defects.empty:
            quality = []
        else:
            quality = defects.groupby(["defect_type", "severity"], as_index=False).agg(
                defects=("vehicle_id", "size"), rework_defects=("rework_flag", "sum")).to_dict("records")
        if downtime.empty:
            stops = []
        else:
            downtime["downtime_minutes"] = (pd.to_datetime(downtime["end_ts"], utc=True) -
                pd.to_datetime(downtime["start_ts"], utc=True)).dt.total_seconds() / 60
            stops = downtime.groupby(["station_id", "reason_code"], as_index=False).agg(
                stops=("reason_code", "size"), downtime_minutes=("downtime_minutes", "sum")).round(1).to_dict("records")

    summary = metrics["summary"]
    summary["vehicles"] = summary.get("vehicles_processed", 0)
    total_events = summary.get("station_events", 0)
    rework_events = int((events["status"] == "rework").sum()) if not events.empty else 0
    summary["rework_events"] = rework_events
    summary["rework_rate_pct"] = round(100 * rework_events / total_events, 1) if total_events else 0
    summary["events_over_takt"] = int((events["cycle_time_minutes"] > 8).sum()) if not events.empty else 0
    return {"start": local_start, "end": local_end, "summary": summary,
            "stations": metrics["stations"], "quality": quality, "downtime": stops,
            "source": "Stored simulated production records"}


def _email_config() -> dict[str, str]:
    keys = ["REPORT_EMAIL_FROM", "REPORT_SMTP_HOST", "REPORT_SMTP_USERNAME", "REPORT_SMTP_PASSWORD"]
    missing = [key for key in keys if not os.getenv(key)]
    if missing:
        raise RuntimeError("Missing SMTP settings: " + ", ".join(missing))
    return {key: os.environ[key] for key in keys}


def send_pdf_report(recipient: str, report: dict, config: dict[str, str]) -> None:
    summary = report["summary"]
    pdf = create_daily_pdf(summary=summary, stations=report["stations"], quality=report["quality"],
                           downtime=report["downtime"], start=report["start"], end=report["end"],
                           source=report["source"])
    message = EmailMessage()
    message["Subject"] = f"Assembly line daily report — {report['start']:%Y-%m-%d}"
    message["From"] = config["REPORT_EMAIL_FROM"]
    message["To"] = recipient
    message.set_content(
        f"Your opt-in assembly line report for {report['start']:%Y-%m-%d} is attached.\n\n"
        f"Vehicles: {summary.get('vehicles', 0):,}\n"
        f"First-pass yield: {summary.get('first_pass_yield_pct', 0):.1f}%\n"
        f"Average cycle time: {summary.get('avg_cycle_minutes', 0):.2f} minutes\n"
        f"Bottleneck candidate: {summary.get('bottleneck_station', 'No data')}\n\n"
        "This report summarizes stored simulated data from the dashboard."
    )
    message.add_attachment(pdf, maintype="application", subtype="pdf",
                           filename=f"assembly-line-report-{report['start']:%Y-%m-%d}.pdf")
    port = int(os.getenv("REPORT_SMTP_PORT", "587"))
    security = os.getenv("REPORT_SMTP_SECURITY", "starttls").lower()
    if security == "ssl":
        client_type = smtplib.SMTP_SSL
        extra = {"context": ssl.create_default_context()}
    elif security == "starttls":
        client_type, extra = smtplib.SMTP, {}
    else:
        raise ValueError("REPORT_SMTP_SECURITY must be 'starttls' or 'ssl'")
    with client_type(config["REPORT_SMTP_HOST"], port, timeout=30, **extra) as client:
        if security == "starttls":
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        client.login(config["REPORT_SMTP_USERNAME"], config["REPORT_SMTP_PASSWORD"])
        client.send_message(message)


def send_due_reports(now: datetime | None = None) -> int:
    config = _email_config()
    now = now or datetime.now(timezone.utc)
    with connect() as conn:
        subscriptions = [dict(row) for row in conn.execute(
            "SELECT user_id, report_email, timezone, send_hour, last_sent_local_date FROM report_preference WHERE opted_in=TRUE"
        ).fetchall()]
    sent = 0
    for preference, report_day in due_preferences(subscriptions, now):
        report = build_database_report(report_day, ZoneInfo(preference["timezone"]))
        send_pdf_report(preference["report_email"], report, config)
        with connect() as conn:
            conn.execute("UPDATE report_preference SET last_sent_local_date=%s, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s",
                         (report_day, preference["user_id"]))
        sent += 1
    return sent


if __name__ == "__main__":
    count = send_due_reports()
    print(f"Sent {count} opted-in daily PDF report(s).")
