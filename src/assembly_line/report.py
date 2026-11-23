"""Build and email a report from a fresh, simulated 24-hour production window."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import os
from pathlib import Path
import smtplib
import ssl

import pandas as pd

from assembly_line.transform import calculate_metrics


def build_report(processed_dir: Path, generated_at: datetime | None = None,
                 window_hours: int = 24) -> dict:
    """Summarize processed CSVs over the requested trailing time window."""
    if window_hours <= 0:
        raise ValueError("window_hours must be greater than zero")
    end = generated_at or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    end = end.astimezone(timezone.utc)
    start = end - timedelta(hours=window_hours)

    events = pd.read_csv(processed_dir / "station_events_clean.csv")
    defects = pd.read_csv(processed_dir / "quality_defects.csv")
    downtime = pd.read_csv(processed_dir / "downtime_events.csv")

    events["end_ts"] = pd.to_datetime(events["end_ts"], utc=True, errors="coerce")
    # Select vehicle cohorts by line completion, then keep all of their station
    # rows so first-pass yield is not biased by vehicles straddling the cutoff.
    vehicle_completion = events.groupby("vehicle_id")["end_ts"].max()
    selected_vehicles = vehicle_completion.index[
        (vehicle_completion >= start) & (vehicle_completion <= end)
    ]
    events = events[events["vehicle_id"].isin(selected_vehicles)].copy()
    defects["recorded_ts"] = pd.to_datetime(defects["recorded_ts"], utc=True, errors="coerce")
    defects = defects[defects["vehicle_id"].isin(selected_vehicles)].copy()
    downtime["end_ts"] = pd.to_datetime(downtime["end_ts"], utc=True, errors="coerce")
    downtime = downtime[(downtime["end_ts"] >= start) & (downtime["end_ts"] <= end)].copy()
    if not downtime.empty:
        downtime["start_ts"] = pd.to_datetime(downtime["start_ts"], utc=True, errors="coerce")

    metrics = calculate_metrics(events, defects, downtime)
    downtime_minutes = 0.0
    if not downtime.empty:
        downtime_minutes = round(float(
            (downtime["end_ts"] - downtime["start_ts"]).dt.total_seconds().sum() / 60
        ), 1)
    return {
        "window_start": start,
        "window_end": end,
        "window_hours": window_hours,
        "summary": metrics["summary"],
        "stations": metrics["stations"],
        "downtime_minutes": downtime_minutes,
    }


def render_text(report: dict) -> str:
    summary = report["summary"]
    if not summary:
        return "No station events were available in the reporting window."
    lines = [
        f"Assembly line daily report ({report['window_hours']}h synthetic sample)",
        f"Window: {report['window_start'].isoformat()} to {report['window_end'].isoformat()}",
        "",
        f"Vehicles: {summary['vehicles_processed']:,}",
        f"Station events: {summary['station_events']:,}",
        f"Average cycle: {summary['avg_cycle_minutes']:.2f} minutes",
        f"First-pass yield: {summary['first_pass_yield_pct']:.1f}%",
        f"Defect records: {summary['defect_records']:,}",
        f"Downtime events: {summary['downtime_events']:,} ({report['downtime_minutes']:.1f} minutes)",
        f"Bottleneck candidate: {summary['bottleneck_station']}",
        "",
        "All production records in this report are generated synthetic data.",
    ]
    return "\n".join(lines)


def render_html(report: dict) -> str:
    summary = report["summary"]
    start = report["window_start"].strftime("%Y-%m-%d %H:%M UTC")
    end = report["window_end"].strftime("%Y-%m-%d %H:%M UTC")
    if not summary:
        return f"<h2>Assembly line daily report</h2><p>No station events were available from {start} to {end}.</p>"

    station_rows = "".join(
        "<tr><td>{station}</td><td>{events}</td><td>{cycle:.2f} min</td><td>{takt}</td><td>{rework}</td></tr>".format(
            station=row["station_id"], events=row["events"], cycle=row["avg_cycle_minutes"],
            takt=row["takt_deviation_minutes"], rework=row["rework_events"])
        for row in report["stations"]
    )
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#152b35;max-width:760px;margin:auto">
<h1 style="color:#146c63">Assembly Line Daily Report</h1>
<p><strong>Reporting window:</strong> {start} – {end}<br><strong>Source:</strong> generated synthetic production sample</p>
<table style="border-collapse:collapse;width:100%;margin:20px 0"><tbody>
<tr><td>Vehicles</td><td><strong>{summary['vehicles_processed']:,}</strong></td><td>Station events</td><td><strong>{summary['station_events']:,}</strong></td></tr>
<tr><td>Average cycle</td><td><strong>{summary['avg_cycle_minutes']:.2f} min</strong></td><td>First-pass yield</td><td><strong>{summary['first_pass_yield_pct']:.1f}%</strong></td></tr>
<tr><td>Defects</td><td><strong>{summary['defect_records']:,}</strong></td><td>Downtime</td><td><strong>{report['downtime_minutes']:.1f} min</strong></td></tr>
<tr><td>Downtime events</td><td><strong>{summary['downtime_events']:,}</strong></td><td>Bottleneck candidate</td><td><strong>{summary['bottleneck_station']}</strong></td></tr>
</tbody></table>
<h2>Station detail</h2><table style="border-collapse:collapse;width:100%"><thead><tr><th>Station</th><th>Events</th><th>Avg cycle</th><th>Takt deviation</th><th>Rework</th></tr></thead><tbody>{station_rows}</tbody></table>
<p style="color:#587079;font-size:13px;margin-top:24px">All production records are synthetic; no factory equipment is connected. The dashboard and this email are separate runs of the same project metrics.</p>
</body></html>"""


def create_message(report: dict, recipient: str, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"Assembly line daily report — {report['window_end']:%Y-%m-%d}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(render_text(report))
    message.add_alternative(render_html(report), subtype="html")
    return message


def send_report(report: dict, environ: dict[str, str] | None = None) -> None:
    config = os.environ if environ is None else environ
    required = ["REPORT_EMAIL_TO", "REPORT_EMAIL_FROM", "REPORT_SMTP_HOST",
                "REPORT_SMTP_USERNAME", "REPORT_SMTP_PASSWORD"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"Missing report email configuration: {', '.join(missing)}")
    port = int(config.get("REPORT_SMTP_PORT", "587"))
    message = create_message(report, config["REPORT_EMAIL_TO"], config["REPORT_EMAIL_FROM"])
    security = config.get("REPORT_SMTP_SECURITY", "starttls").lower()
    if security not in {"starttls", "ssl"}:
        raise ValueError("REPORT_SMTP_SECURITY must be 'starttls' or 'ssl'")
    connection_type = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    with connection_type(config["REPORT_SMTP_HOST"], port, timeout=30,
                         **({"context": ssl.create_default_context()} if security == "ssl" else {})) as client:
        if security == "starttls":
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        client.login(config["REPORT_SMTP_USERNAME"], config["REPORT_SMTP_PASSWORD"])
        client.send_message(message)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--output", type=Path, help="write report JSON instead of sending email")
    args = parser.parse_args()
    report = build_report(args.processed, window_hours=args.window_hours)
    if args.output:
        import json
        serializable = {
            **report,
            "window_start": report["window_start"].isoformat(),
            "window_end": report["window_end"].isoformat(),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        return
    send_report(report)


if __name__ == "__main__":
    main()
