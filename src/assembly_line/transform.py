"""Clean raw events and calculate easy-to-explain line metrics."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

LOGGER = logging.getLogger("assembly_line.etl")


def clean_events(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop duplicate, incomplete, and non-positive-cycle station records."""
    frame = raw.copy()
    input_rows = len(frame)
    before_dedup = len(frame)
    frame = frame.drop_duplicates(subset=["vehicle_id", "station_id", "start_ts", "end_ts"])
    duplicates_removed = before_dedup - len(frame)
    frame["start_ts"] = pd.to_datetime(frame["start_ts"], utc=True, errors="coerce")
    frame["end_ts"] = pd.to_datetime(frame["end_ts"], utc=True, errors="coerce")
    frame["cycle_time_minutes"] = (frame["end_ts"] - frame["start_ts"]).dt.total_seconds() / 60
    frame["status"] = frame["status"].fillna("unknown").str.lower().str.strip()
    frame["operator_shift"] = frame["operator_shift"].fillna("unknown").str.lower().str.strip()
    valid = frame.dropna(subset=["vehicle_id", "station_id", "start_ts", "end_ts"])
    valid = valid[valid["cycle_time_minutes"] > 0].copy()
    audit = {"input_rows": input_rows, "clean_rows": len(valid),
             "rejected_rows": input_rows - len(valid), "duplicate_rows_removed": duplicates_removed}
    valid = valid.sort_values(["start_ts", "station_id", "vehicle_id"]).reset_index(drop=True)
    return valid, audit


def calculate_metrics(events: pd.DataFrame, defects: pd.DataFrame, downtime: pd.DataFrame, takt_minutes: float = 8.0) -> dict:
    """Return a summary and station ranking.

    The quality component is an OEE-style proxy. A full OEE calculation also
    needs scheduled production time and ideal run rates, which this simulation
    does not yet generate.
    """
    if events.empty:
        return {"summary": {}, "stations": []}
    station = events.groupby("station_id").agg(
        events=("vehicle_id", "size"),
        avg_cycle_minutes=("cycle_time_minutes", "mean"),
        median_cycle_minutes=("cycle_time_minutes", "median"),
        rework_events=("status", lambda values: int((values == "rework").sum())),
    ).reset_index()
    station["takt_deviation_minutes"] = station["avg_cycle_minutes"] - takt_minutes
    station["downtime_events"] = station["station_id"].map(downtime.groupby("station_id").size()).fillna(0).astype(int) if not downtime.empty else 0
    station["defect_records"] = station["station_id"].map(defects.groupby("station_id").size()).fillna(0).astype(int) if not defects.empty else 0
    station = station.sort_values("avg_cycle_minutes", ascending=False)
    # Yield is vehicle-level: one rework station means the vehicle did not pass
    # every operation on its first attempt.
    expected_stations = events["station_id"].nunique()
    vehicle_summary = events.groupby("vehicle_id").agg(
        all_complete=("status", lambda values: bool((values == "complete").all())),
        stations_seen=("station_id", "nunique"),
    )
    vehicle_pass = vehicle_summary["all_complete"] & (vehicle_summary["stations_seen"] == expected_stations)
    total_vehicles = len(vehicle_pass)
    first_pass = int(vehicle_pass.sum())
    summary = {
        "vehicles_processed": int(events["vehicle_id"].nunique()),
        "station_events": len(events),
        "avg_cycle_minutes": round(float(events["cycle_time_minutes"].mean()), 2),
        "takt_minutes": takt_minutes,
        "takt_deviation_minutes": round(float(events["cycle_time_minutes"].mean() - takt_minutes), 2),
        "first_pass_yield_pct": round(first_pass / total_vehicles * 100, 2) if total_vehicles else 0.0,
        "oee_style_quality_pct": round(first_pass / total_vehicles * 100, 2) if total_vehicles else 0.0,
        "defect_records": len(defects),
        "downtime_events": len(downtime),
        "bottleneck_station": str(station.iloc[0]["station_id"]),
    }
    return {"summary": summary, "stations": station.round(2).to_dict(orient="records")}


def extract_csv(directory: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read machine exports. Station events are required; other files are optional."""
    event_file = directory / "station_events.csv"
    if not event_file.exists():
        raise FileNotFoundError(f"Expected raw station file: {event_file}")
    events = pd.read_csv(event_file)
    def read_optional(name: str) -> pd.DataFrame:
        path = directory / name
        return pd.read_csv(path) if path.exists() else pd.DataFrame()
    return events, read_optional("quality_defects.csv"), read_optional("downtime_events.csv")


def run_pipeline(raw_dir: Path, processed_dir: Path, takt_minutes: float = 8.0) -> dict:
    """Extract, clean, save tidy files, and write a JSON run report."""
    events_raw, defects, downtime = extract_csv(raw_dir)
    events, audit = clean_events(events_raw)
    processed_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(processed_dir / "station_events_clean.csv", index=False)
    defects.to_csv(processed_dir / "quality_defects.csv", index=False)
    downtime.to_csv(processed_dir / "downtime_events.csv", index=False)
    report = {"audit": audit, **calculate_metrics(events, defects, downtime, takt_minutes)}
    (processed_dir / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOGGER.info(json.dumps({"event": "pipeline_complete", **audit, **report.get("summary", {})}))
    return report
