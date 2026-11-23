from datetime import date

from assembly_line.report_pdf import create_daily_pdf


def test_pdf_contains_valid_pdf_header():
    pdf = create_daily_pdf(
        summary={"vehicles": 10, "station_events": 50, "avg_cycle_minutes": 7.5,
                 "first_pass_yield_pct": 90, "rework_rate_pct": 4, "events_over_takt": 8},
        stations=[{"station_id": "ST-01", "events": 10, "avg_cycle_minutes": 7.5,
                   "p90_cycle_minutes": 9.2, "over_takt_events": 2, "rework_events": 1}],
        quality=[{"defect_type": "paint", "severity": "low", "defects": 2, "rework_defects": 1}],
        downtime=[{"station_id": "ST-01", "reason_code": "jam", "stops": 1, "downtime_minutes": 12}],
        start=date(2026, 11, 22), end=date(2026, 11, 23),
    )
    assert pdf.startswith(b"%PDF-")

