"""Small PostgreSQL loader for the teaching-sized dimensional model."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()


def database_url() -> str:
    """Read the private connection string from env or Streamlit server secrets."""
    value = os.getenv("DATABASE_URL")
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL", "")
    except Exception:
        return ""


def connect():
    url = database_url()
    if not url:
        raise RuntimeError("Set DATABASE_URL in the environment or Streamlit secrets to connect PostgreSQL")
    return psycopg.connect(url, row_factory=dict_row)


def load_processed(processed_dir: Path) -> int:
    """Append cleaned records and skip records already loaded in a prior run."""
    events = pd.read_csv(processed_dir / "station_events_clean.csv")
    defects_path = processed_dir / "quality_defects.csv"
    defects = pd.read_csv(defects_path) if defects_path.exists() else pd.DataFrame()
    downtime_path = processed_dir / "downtime_events.csv"
    downtime = pd.read_csv(downtime_path) if downtime_path.exists() else pd.DataFrame()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE fact_defect ADD COLUMN IF NOT EXISTS recorded_ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_event_vehicle_station_time ON fact_station_event (vehicle_id, station_id, start_ts)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_defect_natural_key ON fact_defect (vehicle_id, station_id, defect_id, recorded_ts)")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_downtime_natural_key ON fact_downtime (station_id, start_ts, end_ts, reason_code)")
            inserted = 0
            for station_id in events["station_id"].dropna().unique():
                cur.execute("INSERT INTO dim_station(station_id) VALUES (%s) ON CONFLICT DO NOTHING", (station_id,))
            for shift in events["operator_shift"].dropna().unique():
                cur.execute("INSERT INTO dim_shift(shift_name) VALUES (%s) ON CONFLICT DO NOTHING", (shift,))
            for row in events.itertuples(index=False):
                cur.execute("""INSERT INTO fact_station_event
                    (vehicle_id, station_id, shift_id, start_ts, end_ts, cycle_time_minutes, status)
                    SELECT %s, s.station_id, sh.shift_id, %s, %s, %s, %s
                    FROM dim_station s CROSS JOIN dim_shift sh
                    WHERE s.station_id=%s AND sh.shift_name=%s
                    ON CONFLICT (vehicle_id, station_id, start_ts) DO NOTHING""",
                    (row.vehicle_id, row.start_ts, row.end_ts, float(row.cycle_time_minutes),
                     row.status, row.station_id, row.operator_shift))
                inserted += cur.rowcount
            if not defects.empty:
                for defect_type in defects["defect_type"].dropna().unique():
                    cur.execute("INSERT INTO dim_defect(defect_type) VALUES (%s) ON CONFLICT DO NOTHING", (defect_type,))
                for row in defects.itertuples(index=False):
                    cur.execute("""INSERT INTO fact_defect(vehicle_id, station_id, defect_id, severity, rework_flag, recorded_ts)
                        SELECT %s, s.station_id, d.defect_id, %s, %s, %s FROM dim_station s CROSS JOIN dim_defect d
                        WHERE s.station_id=%s AND d.defect_type=%s ON CONFLICT DO NOTHING""",
                        (row.vehicle_id, row.severity, bool(row.rework_flag), row.recorded_ts,
                         row.station_id, row.defect_type))
            if not downtime.empty:
                for row in downtime.itertuples(index=False):
                    cur.execute("""INSERT INTO fact_downtime(station_id, start_ts, end_ts, reason_code)
                        SELECT station_id, %s, %s, %s FROM dim_station WHERE station_id=%s
                        ON CONFLICT DO NOTHING""",
                        (row.start_ts, row.end_ts, row.reason_code, row.station_id))
    return inserted
