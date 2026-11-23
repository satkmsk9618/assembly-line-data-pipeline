"""Small PostgreSQL loader for the teaching-sized dimensional model."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def load_processed(processed_dir: Path) -> int:
    """Replace this demo dataset in one transaction; incremental loads are future work."""
    events = pd.read_csv(processed_dir / "station_events_clean.csv")
    defects_path = processed_dir / "quality_defects.csv"
    defects = pd.read_csv(defects_path) if defects_path.exists() else pd.DataFrame()
    downtime_path = processed_dir / "downtime_events.csv"
    downtime = pd.read_csv(downtime_path) if downtime_path.exists() else pd.DataFrame()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE fact_defect ADD COLUMN IF NOT EXISTS recorded_ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
            cur.execute("TRUNCATE fact_station_event, fact_defect, fact_downtime RESTART IDENTITY")
            for station_id in events["station_id"].dropna().unique():
                cur.execute("INSERT INTO dim_station(station_id) VALUES (%s) ON CONFLICT DO NOTHING", (station_id,))
            for shift in events["operator_shift"].dropna().unique():
                cur.execute("INSERT INTO dim_shift(shift_name) VALUES (%s) ON CONFLICT DO NOTHING", (shift,))
            for row in events.itertuples(index=False):
                cur.execute("""INSERT INTO fact_station_event
                    (vehicle_id, station_id, shift_id, start_ts, end_ts, cycle_time_minutes, status)
                    SELECT %s, s.station_id, sh.shift_id, %s, %s, %s, %s
                    FROM dim_station s CROSS JOIN dim_shift sh
                    WHERE s.station_id=%s AND sh.shift_name=%s""",
                    (row.vehicle_id, row.start_ts, row.end_ts, float(row.cycle_time_minutes),
                     row.status, row.station_id, row.operator_shift))
            if not defects.empty:
                for defect_type in defects["defect_type"].dropna().unique():
                    cur.execute("INSERT INTO dim_defect(defect_type) VALUES (%s) ON CONFLICT DO NOTHING", (defect_type,))
                for row in defects.itertuples(index=False):
                    cur.execute("""INSERT INTO fact_defect(vehicle_id, station_id, defect_id, severity, rework_flag, recorded_ts)
                        SELECT %s, s.station_id, d.defect_id, %s, %s, %s FROM dim_station s CROSS JOIN dim_defect d
                        WHERE s.station_id=%s AND d.defect_type=%s""",
                        (row.vehicle_id, row.severity, bool(row.rework_flag), row.recorded_ts,
                         row.station_id, row.defect_type))
            if not downtime.empty:
                for row in downtime.itertuples(index=False):
                    cur.execute("""INSERT INTO fact_downtime(station_id, start_ts, end_ts, reason_code)
                        SELECT station_id, %s, %s, %s FROM dim_station WHERE station_id=%s""",
                        (row.start_ts, row.end_ts, row.reason_code, row.station_id))
    return len(events)
