"""Create reproducible, intentionally imperfect machine-export files."""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

STATIONS = ["ST-01", "ST-02", "ST-03", "ST-04", "ST-05"]
SHIFTS = ["day", "swing", "night"]
DEFECTS = ["paint_scratch", "loose_fastener", "sensor_fault", "misalignment"]


def generate(output_dir: Path, vehicles: int = 1000, seed: int = 7) -> None:
    """Write three raw CSV exports; a fixed seed makes reruns comparable."""
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 1, 5, 6, tzinfo=timezone.utc)
    events, defects, downtime = [], [], []
    for number in range(1, vehicles + 1):
        vehicle_id = f"V-{number:06d}"
        cursor = base + timedelta(minutes=number * 4)
        shift = SHIFTS[(number // 250) % len(SHIFTS)]
        for station_id in STATIONS:
            start = cursor + timedelta(minutes=rng.randint(0, 2))
            duration = rng.randint(3, 11)
            end = start + timedelta(minutes=duration)
            status = "complete" if rng.random() > 0.025 else "rework"
            row = {"vehicle_id": vehicle_id, "station_id": station_id,
                   "start_ts": start.isoformat(), "end_ts": end.isoformat(),
                   "operator_shift": shift, "status": status}
            events.append(row)
            if rng.random() < 0.045:
                defects.append({"vehicle_id": vehicle_id, "station_id": station_id,
                    "defect_type": rng.choice(DEFECTS), "severity": rng.choice(["low", "medium", "high"]),
                    "rework_flag": status == "rework", "recorded_ts": end.isoformat()})
            cursor = end
            if rng.random() < 0.012:
                stop_start = start + timedelta(minutes=duration // 2)
                downtime.append({"station_id": station_id, "start_ts": stop_start.isoformat(),
                    "end_ts": (stop_start + timedelta(minutes=rng.randint(5, 45))).isoformat(),
                    "reason_code": rng.choice(["jam", "maintenance", "material_wait", "changeover"])})
    # Deliberately dirty exports give the cleaning step meaningful work.
    for index, row in enumerate(events):
        if index % 211 == 0:
            events.append(row.copy())
        if index % 307 == 0:
            row["start_ts"] = ""
        # Index 0 is also a missing-timestamp row, so don't parse its blank
        # start time while injecting the separate negative-cycle fault.
        if index % 401 == 0 and row["start_ts"]:
            start = datetime.fromisoformat(row["start_ts"])
            row["end_ts"] = (start - timedelta(minutes=5)).isoformat()
    rng.shuffle(events)
    pd.DataFrame(events).to_csv(output_dir / "station_events.csv", index=False)
    pd.DataFrame(defects, columns=["vehicle_id", "station_id", "defect_type", "severity", "rework_flag", "recorded_ts"]).to_csv(output_dir / "quality_defects.csv", index=False)
    pd.DataFrame(downtime, columns=["station_id", "start_ts", "end_ts", "reason_code"]).to_csv(output_dir / "downtime_events.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicles", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    generate(args.output, args.vehicles, args.seed)
    print(f"Generated exports for {args.vehicles} vehicles in {args.output}")


if __name__ == "__main__":
    main()
