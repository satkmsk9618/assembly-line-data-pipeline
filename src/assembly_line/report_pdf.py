"""Create a compact, readable PDF snapshot from dashboard metrics."""
from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INK = colors.HexColor("#18333B")
TEAL = colors.HexColor("#146C63")
PALE = colors.HexColor("#EAF3F2")
MUTED = colors.HexColor("#61757B")


def _table(rows: list[list[Any]], widths=None) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("LEADING", (0, 0), (-1, -1), 12),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D4E0E2")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def create_daily_pdf(*, summary: dict, stations: list[dict], quality: list[dict],
                     downtime: list[dict], start: date | datetime, end: date | datetime,
                     source: str = "Simulated production data") -> bytes:
    """Render the key daily KPIs, station performance, quality, and downtime."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title="Assembly Line Daily Report", author="Assembly Line Dashboard")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], textColor=TEAL,
                              alignment=TA_LEFT, fontSize=21, leading=26, spaceAfter=3))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], textColor=INK,
                              fontSize=12, leading=15, spaceBefore=13, spaceAfter=6))
    styles.add(ParagraphStyle(name="SmallNote", parent=styles["BodyText"], textColor=MUTED,
                              fontSize=8.5, leading=12))
    story = [Paragraph("Assembly Line Daily Report", styles["ReportTitle"]),
             Paragraph(f"Reporting window: {start} through {end} &nbsp; · &nbsp; Source: {source}", styles["SmallNote"]),
             Paragraph(f"Generated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", styles["SmallNote"]),
             Spacer(1, 9)]

    defect_count = sum(int(row.get("defects", 0) or 0) for row in quality)
    downtime_stops = sum(int(row.get("stops", 0) or 0) for row in downtime)
    downtime_minutes = sum(float(row.get("downtime_minutes", 0) or 0) for row in downtime)

    items = [
        ("Vehicles", summary.get("vehicles") or summary.get("vehicles_processed") or 0),
        ("Station events", summary.get("station_events") or 0),
        ("Average cycle", f"{summary.get('avg_cycle_minutes') or 0:.2f} min"),
        ("First-pass yield", f"{summary.get('first_pass_yield_pct') or 0:.1f}%"),
        ("Rework", f"{summary.get('rework_rate_pct') or 0:.1f}%"),
        ("Over takt", summary.get("events_over_takt") or 0),
        ("Defect records", defect_count),
        ("Downtime", f"{downtime_minutes:.1f} min / {downtime_stops} stops"),
    ]
    kpi_rows = [[Paragraph(f"<b>{label}</b>", styles["BodyText"]), str(value)] for label, value in items]
    story.extend([Paragraph("Daily summary", styles["Section"]),
                  _table([["Measure", "Result"], *kpi_rows], [70 * mm, 90 * mm])])

    station_rows = [["Station", "Events", "Avg cycle", "P90 cycle", "Over takt", "Rework"]]
    for row in stations:
        station_rows.append([str(row.get("station_id", "")), str(row.get("events", 0)),
                             f"{float(row.get('avg_cycle_minutes') or 0):.2f} min",
                             f"{float(row.get('p90_cycle_minutes') or 0):.2f} min",
                             str(row.get("over_takt_events", 0)), str(row.get("rework_events", 0))])
    story.append(Paragraph("Station performance", styles["Section"]))
    story.append(_table(station_rows, [31 * mm, 20 * mm, 27 * mm, 27 * mm, 23 * mm, 21 * mm])
                 if stations else Paragraph("No station records were stored for this reporting window.", styles["BodyText"]))

    q_rows = [["Defect type", "Severity", "Records", "Rework records"]]
    q_rows.extend([[str(row.get("defect_type", "")), str(row.get("severity", "")),
                    str(row.get("defects", 0)), str(row.get("rework_defects", 0))] for row in quality])
    story.append(Paragraph("Quality and defects", styles["Section"]))
    story.append(_table(q_rows, [58 * mm, 35 * mm, 30 * mm, 38 * mm])
                 if quality else Paragraph("No defect records were stored for this reporting window.", styles["BodyText"]))
    if quality:
        top_defect = max(quality, key=lambda row: int(row.get("defects", 0) or 0))
        story.append(Paragraph(f"Most frequent defect category: {top_defect.get('defect_type')} ({top_defect.get('severity')}, {int(top_defect.get('defects', 0))} records).", styles["SmallNote"]))

    d_rows = [["Station", "Stop reason", "Stops", "Downtime minutes"]]
    d_rows.extend([[str(row.get("station_id", "")), str(row.get("reason_code", "")),
                    str(row.get("stops", 0)), f"{float(row.get('downtime_minutes') or 0):.1f}"] for row in downtime])
    story.append(Paragraph("Downtime", styles["Section"]))
    story.append(_table(d_rows, [42 * mm, 51 * mm, 27 * mm, 42 * mm])
                 if downtime else Paragraph("No downtime records were stored for this reporting window.", styles["BodyText"]))
    if downtime:
        top_stop = max(downtime, key=lambda row: float(row.get("downtime_minutes", 0) or 0))
        story.append(Paragraph(f"Largest recorded loss: {top_stop.get('reason_code')} at {top_stop.get('station_id')} ({float(top_stop.get('downtime_minutes', 0)):.1f} minutes).", styles["SmallNote"]))
    if not summary:
        story.append(Paragraph("No station events were available for this reporting window.", styles["Section"]))
    story.extend([Spacer(1, 10),
                  Paragraph("Interpretation: longer cycle times and takt misses are investigation candidates, not proof of a bottleneck. Review shift mix, event completeness, and downtime context before taking action.", styles["SmallNote"]),
                  Paragraph("This report reflects the selected reporting window. Synthetic data is for demonstration and is not a live factory record.", styles["SmallNote"])])
    doc.build(story)
    return buffer.getvalue()
