import pandas as pd

from assembly_line.generate import generate
from assembly_line.transform import calculate_metrics, clean_events


def test_clean_events_removes_duplicate_missing_and_negative_rows():
    raw = pd.DataFrame([
        {"vehicle_id": "V1", "station_id": "S1", "start_ts": "2026-01-01T00:00:00Z", "end_ts": "2026-01-01T00:05:00Z", "operator_shift": "day", "status": "complete"},
        {"vehicle_id": "V1", "station_id": "S1", "start_ts": "2026-01-01T00:00:00Z", "end_ts": "2026-01-01T00:05:00Z", "operator_shift": "day", "status": "complete"},
        {"vehicle_id": "V2", "station_id": "S1", "start_ts": "", "end_ts": "2026-01-01T00:05:00Z", "operator_shift": "day", "status": "complete"},
        {"vehicle_id": "V3", "station_id": "S1", "start_ts": "2026-01-01T00:08:00Z", "end_ts": "2026-01-01T00:05:00Z", "operator_shift": "day", "status": "complete"},
    ])
    clean, audit = clean_events(raw)
    assert len(clean) == 1
    assert clean.iloc[0].cycle_time_minutes == 5
    assert audit == {"input_rows": 4, "clean_rows": 1, "rejected_rows": 3, "duplicate_rows_removed": 1}


def test_metrics_identify_station_with_longest_average_cycle():
    events = pd.DataFrame([
        {"vehicle_id": "V1", "station_id": "S1", "cycle_time_minutes": 5.0, "status": "complete"},
        {"vehicle_id": "V1", "station_id": "S2", "cycle_time_minutes": 10.0, "status": "rework"},
    ])
    result = calculate_metrics(events, pd.DataFrame(), pd.DataFrame(), takt_minutes=8)
    assert result["summary"]["bottleneck_station"] == "S2"
    assert result["summary"]["first_pass_yield_pct"] == 0.0


def test_metrics_do_not_count_a_vehicle_with_a_missing_station_as_first_pass():
    events = pd.DataFrame([
        {"vehicle_id": "COMPLETE", "station_id": "S1", "cycle_time_minutes": 5.0, "status": "complete"},
        {"vehicle_id": "COMPLETE", "station_id": "S2", "cycle_time_minutes": 5.0, "status": "complete"},
        {"vehicle_id": "INCOMPLETE", "station_id": "S1", "cycle_time_minutes": 5.0, "status": "complete"},
    ])

    result = calculate_metrics(events, pd.DataFrame(), pd.DataFrame())

    assert result["summary"]["first_pass_yield_pct"] == 50.0


def test_generator_can_create_dirty_data_with_one_vehicle(tmp_path):
    generate(tmp_path, vehicles=1, seed=7)
    raw = pd.read_csv(tmp_path / "station_events.csv")
    assert raw["start_ts"].isna().any()
