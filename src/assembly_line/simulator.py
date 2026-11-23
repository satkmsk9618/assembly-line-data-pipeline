"""Append a small, clearly simulated stream of new production events."""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone

from assembly_line.db import connect
from assembly_line.generate import DEFECTS, SHIFTS, STATIONS

LOGGER = logging.getLogger("assembly_line.simulator")
REASONS = ["jam", "maintenance", "material_wait", "changeover"]
STREAM_INTERVAL_SECONDS = 15


def produce_batch(rng: random.Random) -> dict[str, int | str]:
    """Write one simulated vehicle across all stations and return a small log."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    vehicle_id = f"LIVE-{now:%Y%m%d%H%M%S}-{rng.randrange(1_000_000):06d}"
    shift = SHIFTS[(now.hour // 8) % len(SHIFTS)]
    events_written = 0
    defects_written = 0
    downtime_written = 0

    with connect() as conn, conn.cursor() as cur:
        for station_id in STATIONS:
            cur.execute(
                "INSERT INTO dim_station (station_id, station_name) VALUES (%s, %s) "
                "ON CONFLICT (station_id) DO NOTHING",
                (station_id, f"Assembly station {station_id[-2:]}")
            )
        cur.execute("INSERT INTO dim_shift (shift_name) VALUES (%s) ON CONFLICT DO NOTHING", (shift,))

        cycles = [rng.randint(4, 11) for _ in STATIONS]
        gaps = [rng.randint(0, 1) for _ in STATIONS]
        cursor = now - timedelta(minutes=sum(cycles) + sum(gaps))
        for station_id, cycle, gap in zip(STATIONS, cycles, gaps):
            # Keep this vehicle's station timestamps in line order while
            # spreading its events over a recent, believable production cycle.
            start_ts = cursor
            end_ts = start_ts + timedelta(minutes=cycle)
            status = "rework" if rng.random() < 0.04 else "complete"
            cur.execute(
                """INSERT INTO fact_station_event
                   (vehicle_id, station_id, shift_id, start_ts, end_ts,
                    cycle_time_minutes, status)
                   SELECT %s, s.station_id, sh.shift_id, %s, %s, %s, %s
                   FROM dim_station s CROSS JOIN dim_shift sh
                   WHERE s.station_id = %s AND sh.shift_name = %s""",
                (vehicle_id, start_ts, end_ts, cycle, status, station_id, shift)
            )
            events_written += 1
            cursor = end_ts + timedelta(minutes=gap)

            if status == "rework" or rng.random() < 0.035:
                defect_type = rng.choice(DEFECTS)
                severity = rng.choices(["low", "medium", "high"], weights=[6, 3, 1])[0]
                cur.execute("INSERT INTO dim_defect (defect_type) VALUES (%s) ON CONFLICT DO NOTHING", (defect_type,))
                cur.execute(
                    """INSERT INTO fact_defect
                       (vehicle_id, station_id, defect_id, severity, rework_flag, recorded_ts)
                       SELECT %s, s.station_id, d.defect_id, %s, %s, %s
                       FROM dim_station s CROSS JOIN dim_defect d
                       WHERE s.station_id = %s AND d.defect_type = %s""",
                    (vehicle_id, severity, status == "rework", end_ts, station_id, defect_type)
                )
                defects_written += 1

        if rng.random() < 0.18:
            station_id = rng.choice(STATIONS)
            duration = rng.randint(3, 25)
            end_ts = now - timedelta(minutes=rng.randint(0, 10))
            cur.execute(
                """INSERT INTO fact_downtime (station_id, start_ts, end_ts, reason_code)
                   VALUES (%s, %s, %s, %s)""",
                (station_id, end_ts - timedelta(minutes=duration), end_ts, rng.choice(REASONS))
            )
            downtime_written += 1

    return {"event": "live_batch_written", "vehicle_id": vehicle_id,
            "station_events": events_written, "defects": defects_written,
            "downtime_events": downtime_written}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rng = random.Random()
    LOGGER.info(json.dumps({"event": "simulator_started", "interval_seconds": STREAM_INTERVAL_SECONDS,
                            "source": "simulated"}))
    schema_ready = False
    while True:
        try:
            if not schema_ready:
                with connect() as conn:
                    conn.execute(
                        "ALTER TABLE fact_defect ADD COLUMN IF NOT EXISTS recorded_ts "
                        "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    )
                    # Older demo databases did not store defect timestamps.
                    # Recover them from the matching station event instead of
                    # making historical defects look like fresh live records.
                    conn.execute("""UPDATE fact_defect AS d SET recorded_ts = e.last_event_ts
                        FROM (SELECT vehicle_id, station_id, max(end_ts) AS last_event_ts
                              FROM fact_station_event GROUP BY vehicle_id, station_id) AS e
                        WHERE d.vehicle_id = e.vehicle_id AND d.station_id = e.station_id""")
                    conn.execute("CREATE INDEX IF NOT EXISTS ix_event_end_ts ON fact_station_event (end_ts)")
                    conn.execute("CREATE INDEX IF NOT EXISTS ix_defect_recorded_ts ON fact_defect (recorded_ts)")
                    conn.execute("CREATE INDEX IF NOT EXISTS ix_downtime_end_ts ON fact_downtime (end_ts)")
                    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_event_vehicle_station_time ON fact_station_event (vehicle_id, station_id, start_ts)")
                    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_defect_natural_key ON fact_defect (vehicle_id, station_id, defect_id, recorded_ts)")
                    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_downtime_natural_key ON fact_downtime (station_id, start_ts, end_ts, reason_code)")
                    conn.execute("""CREATE TABLE IF NOT EXISTS report_preference (
                        user_id TEXT PRIMARY KEY, report_email TEXT NOT NULL,
                        timezone TEXT NOT NULL DEFAULT 'UTC',
                        send_hour SMALLINT NOT NULL DEFAULT 9 CHECK(send_hour BETWEEN 0 AND 23),
                        opted_in BOOLEAN NOT NULL DEFAULT FALSE, last_sent_local_date DATE,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
                schema_ready = True
            LOGGER.info(json.dumps(produce_batch(rng)))
        except Exception as exc:  # Keep the demo stream alive if the DB restarts.
            schema_ready = False
            LOGGER.error(json.dumps({"event": "simulator_error", "message": str(exc)}))
        time.sleep(STREAM_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
