"""Session-local event stream for the Streamlit Community Cloud demo.

This keeps the public dashboard self-contained when no API_URL is configured.
The Docker Compose version continues to use PostgreSQL, FastAPI, and the
separate simulator service.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
from typing import MutableMapping

import pandas as pd

from assembly_line.generate import DEFECTS, SHIFTS, STATIONS

INTERVAL_SECONDS = 15
TAKT_MINUTES = 8


def _vehicle(rng: random.Random, vehicle_id: str, completed_at: datetime):
    shift = SHIFTS[(completed_at.hour // 8) % len(SHIFTS)]
    cycles = [rng.randint(4, 11) for _ in STATIONS]
    gaps = [rng.randint(0, 1) for _ in STATIONS]
    cursor = completed_at - timedelta(minutes=sum(cycles) + sum(gaps))
    events, defects = [], []
    for station_id, cycle, gap in zip(STATIONS, cycles, gaps):
        start_ts = cursor
        end_ts = start_ts + timedelta(minutes=cycle)
        status = "rework" if rng.random() < 0.05 else "complete"
        events.append({
            "vehicle_id": vehicle_id,
            "station_id": station_id,
            "operator_shift": shift,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "cycle_time_minutes": cycle,
            "status": status,
        })
        if status == "rework" or rng.random() < 0.04:
            defects.append({
                "vehicle_id": vehicle_id,
                "station_id": station_id,
                "defect_type": rng.choice(DEFECTS),
                "severity": rng.choices(["low", "medium", "high"], [6, 3, 1])[0],
                "rework_flag": status == "rework",
                "recorded_ts": end_ts,
            })
        cursor = end_ts + timedelta(minutes=gap)
    return events, defects


def _seed(state: MutableMapping) -> None:
    rng = random.Random(9618)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    run_id = now.strftime("%Y%m%d%H%M%S")
    events, defects, downtime = [], [], []
    for number in range(1, 37):
        completed_at = now - timedelta(hours=6) + timedelta(minutes=number * 10)
        batch, batch_defects = _vehicle(rng, f"CLOUD-{run_id}-{number:04d}", completed_at)
        events.extend(batch)
        defects.extend(batch_defects)
        if rng.random() < 0.4:
            end_ts = completed_at - timedelta(minutes=rng.randint(0, 20))
            downtime.append({
                "station_id": rng.choice(STATIONS),
                "start_ts": end_ts - timedelta(minutes=rng.randint(4, 40)),
                "end_ts": end_ts,
                "reason_code": rng.choice(["jam", "maintenance", "material_wait", "changeover"]),
            })
    state["cloud_events"] = events
    state["cloud_defects"] = defects
    state["cloud_downtime"] = downtime
    state["cloud_last_batch"] = now
    state["cloud_vehicle_number"] = 36
    state["cloud_run_id"] = run_id
    state["cloud_rng_state"] = rng.getstate()


def advance(state: MutableMapping, now: datetime | None = None) -> bool:
    """Append one simulated vehicle when the 15-second interval has elapsed."""
    if "cloud_events" not in state:
        _seed(state)
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    last_batch = state["cloud_last_batch"]
    if (now - last_batch).total_seconds() < INTERVAL_SECONDS:
        return False

    rng = random.Random()
    rng.setstate(state["cloud_rng_state"])
    state["cloud_vehicle_number"] += 1
    number = state["cloud_vehicle_number"]
    batch, defects = _vehicle(rng, f"CLOUD-{state['cloud_run_id']}-{number:04d}", now)
    state["cloud_events"].extend(batch)
    state["cloud_defects"].extend(defects)
    if rng.random() < 0.18:
        end_ts = now - timedelta(minutes=rng.randint(0, 10))
        state["cloud_downtime"].append({
            "station_id": rng.choice(STATIONS),
            "start_ts": end_ts - timedelta(minutes=rng.randint(3, 25)),
            "end_ts": end_ts,
            "reason_code": rng.choice(["jam", "maintenance", "material_wait", "changeover"]),
        })
    state["cloud_last_batch"] = now
    state["cloud_rng_state"] = rng.getstate()
    return True


def persist_new_records(state: MutableMapping) -> int:
    """Append simulator records created since this shared state was last saved."""
    from assembly_line.db import connect

    event_offset = int(state.get("cloud_persisted_event_count", 0))
    defect_offset = int(state.get("cloud_persisted_defect_count", 0))
    downtime_offset = int(state.get("cloud_persisted_downtime_count", 0))
    events = state.get("cloud_events", [])[event_offset:]
    defects = state.get("cloud_defects", [])[defect_offset:]
    stops = state.get("cloud_downtime", [])[downtime_offset:]
    if not events and not defects and not stops:
        return 0

    with connect() as conn, conn.cursor() as cur:
        for station_id in STATIONS:
            cur.execute("INSERT INTO dim_station(station_id, station_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (station_id, f"Assembly station {station_id[-2:]}"))
        for row in events:
            shift = row["operator_shift"]
            cur.execute("INSERT INTO dim_shift(shift_name) VALUES (%s) ON CONFLICT DO NOTHING", (shift,))
            cur.execute("""INSERT INTO fact_station_event
                (vehicle_id, station_id, shift_id, start_ts, end_ts, cycle_time_minutes, status)
                SELECT %s, s.station_id, sh.shift_id, %s, %s, %s, %s
                FROM dim_station s CROSS JOIN dim_shift sh
                WHERE s.station_id=%s AND sh.shift_name=%s ON CONFLICT DO NOTHING""",
                (row["vehicle_id"], row["start_ts"], row["end_ts"], row["cycle_time_minutes"],
                 row["status"], row["station_id"], shift))
        for row in defects:
            cur.execute("INSERT INTO dim_defect(defect_type) VALUES (%s) ON CONFLICT DO NOTHING", (row["defect_type"],))
            cur.execute("""INSERT INTO fact_defect(vehicle_id, station_id, defect_id, severity, rework_flag, recorded_ts)
                SELECT %s, s.station_id, d.defect_id, %s, %s, %s FROM dim_station s CROSS JOIN dim_defect d
                WHERE s.station_id=%s AND d.defect_type=%s ON CONFLICT DO NOTHING""",
                (row["vehicle_id"], row["severity"], row["rework_flag"], row["recorded_ts"],
                 row["station_id"], row["defect_type"]))
        for row in stops:
            cur.execute("""INSERT INTO fact_downtime(station_id, start_ts, end_ts, reason_code)
                VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (row["station_id"], row["start_ts"], row["end_ts"], row["reason_code"]))
    state["cloud_persisted_event_count"] = len(state.get("cloud_events", []))
    state["cloud_persisted_defect_count"] = len(state.get("cloud_defects", []))
    state["cloud_persisted_downtime_count"] = len(state.get("cloud_downtime", []))
    return len(events)


def metrics(state: MutableMapping, path: str, hours: int = 1, all_time: bool = False):
    """Return cloud-demo metrics using the same shapes as the FastAPI routes."""
    if "cloud_events" not in state:
        _seed(state)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    events = pd.DataFrame(state["cloud_events"])
    defects = pd.DataFrame(state["cloud_defects"])
    downtime = pd.DataFrame(state["cloud_downtime"])
    recent = events.copy() if all_time else events[events["end_ts"] >= cutoff].copy()

    if path == "/metrics/live-summary":
        n = len(recent)
        rework = int((recent["status"] == "rework").sum())
        return {
            "station_events": n,
            "vehicles": int(recent["vehicle_id"].nunique()),
            "avg_cycle_minutes": round(float(recent["cycle_time_minutes"].mean()), 2) if n else None,
            "events_over_takt": int((recent["cycle_time_minutes"] > TAKT_MINUTES).sum()),
            "rework_events": rework,
            "rework_rate_pct": round(100 * rework / n, 2) if n else None,
            "latest_event_ts": recent["end_ts"].max().isoformat() if n else None,
        }

    if path == "/metrics/trend":
        if recent.empty:
            return []
        bucket_size = "D" if all_time else "5min"
        recent["time_bucket"] = pd.to_datetime(recent["end_ts"], utc=True).dt.floor(bucket_size)
        result = recent.groupby("time_bucket").agg(
            station_events=("vehicle_id", "size"), vehicles=("vehicle_id", "nunique"),
            avg_cycle_minutes=("cycle_time_minutes", "mean"),
            rework_events=("status", lambda values: int((values == "rework").sum())),
        ).reset_index()
        result["avg_cycle_minutes"] = result["avg_cycle_minutes"].round(2)
        result["time_bucket"] = result["time_bucket"].map(lambda value: value.isoformat())
        return result.to_dict(orient="records")

    if path == "/metrics/station-health":
        if recent.empty:
            return []
        result = recent.groupby("station_id").agg(
            events=("vehicle_id", "size"), avg_cycle_minutes=("cycle_time_minutes", "mean"),
            p90_cycle_minutes=("cycle_time_minutes", lambda values: values.quantile(0.9)),
            over_takt_events=("cycle_time_minutes", lambda values: int((values > TAKT_MINUTES).sum())),
            rework_events=("status", lambda values: int((values == "rework").sum())),
        ).reset_index()
        result["avg_cycle_minutes"] = result["avg_cycle_minutes"].round(2)
        result["p90_cycle_minutes"] = result["p90_cycle_minutes"].round(2)
        result["rework_rate_pct"] = (100 * result["rework_events"] / result["events"]).round(2)
        return result.sort_values("avg_cycle_minutes", ascending=False).to_dict(orient="records")

    if path == "/metrics/quality":
        if defects.empty:
            return []
        recent_defects = defects.copy() if all_time else defects[defects["recorded_ts"] >= cutoff]
        if recent_defects.empty:
            return []
        result = recent_defects.groupby(["defect_type", "severity"]).agg(
            defects=("vehicle_id", "size"),
            rework_defects=("rework_flag", "sum"),
        ).reset_index()
        result["rework_defects"] = result["rework_defects"].astype(int)
        return result.sort_values("defects", ascending=False).to_dict(orient="records")

    if path == "/metrics/downtime":
        if downtime.empty:
            return []
        recent_downtime = downtime.copy() if all_time else downtime[downtime["end_ts"] >= cutoff].copy()
        if recent_downtime.empty:
            return []
        recent_downtime["downtime_minutes"] = (
            (recent_downtime["end_ts"] - recent_downtime["start_ts"]).dt.total_seconds() / 60
        ).round(1)
        return recent_downtime.groupby(["station_id", "reason_code"], as_index=False).agg(
            stops=("reason_code", "size"), downtime_minutes=("downtime_minutes", "sum")
        ).sort_values("downtime_minutes", ascending=False).to_dict(orient="records")

    raise KeyError(f"Unsupported local demo endpoint: {path}")
