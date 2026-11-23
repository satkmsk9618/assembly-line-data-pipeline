from datetime import datetime, timedelta, timezone

from assembly_line import cloud_simulator


def test_cloud_demo_starts_with_recent_station_and_quality_metrics():
    state = {}

    summary = cloud_simulator.metrics(state, "/metrics/live-summary", hours=8)
    stations = cloud_simulator.metrics(state, "/metrics/station-health", hours=8)
    quality = cloud_simulator.metrics(state, "/metrics/quality", hours=8)
    downtime = cloud_simulator.metrics(state, "/metrics/downtime", hours=8)

    assert summary["vehicles"] > 0
    assert summary["station_events"] == summary["vehicles"] * len(cloud_simulator.STATIONS)
    assert len(stations) == len(cloud_simulator.STATIONS)
    assert quality
    assert downtime


def test_cloud_demo_all_time_includes_complete_generated_history():
    state = {}

    all_time = cloud_simulator.metrics(state, "/metrics/live-summary", hours=1, all_time=True)
    recent = cloud_simulator.metrics(state, "/metrics/live-summary", hours=1)
    all_time_trend = cloud_simulator.metrics(state, "/metrics/trend", hours=1, all_time=True)

    assert all_time["station_events"] == 36 * len(cloud_simulator.STATIONS)
    assert all_time["station_events"] > recent["station_events"]
    assert all_time_trend


def test_cloud_demo_adds_a_vehicle_after_fifteen_seconds():
    state = {}
    cloud_simulator.metrics(state, "/metrics/live-summary")
    previous_vehicles = state["cloud_vehicle_number"]
    now = state["cloud_last_batch"] + timedelta(seconds=15)

    assert cloud_simulator.advance(state, now=now)
    assert state["cloud_vehicle_number"] == previous_vehicles + 1
    assert len(state["cloud_events"]) == state["cloud_vehicle_number"] * len(cloud_simulator.STATIONS)


def test_cloud_demo_all_time_daily_chart_includes_new_vehicle():
    state = {}
    before = cloud_simulator.metrics(state, "/metrics/trend", all_time=True)
    now = state["cloud_last_batch"] + timedelta(seconds=15)

    assert cloud_simulator.advance(state, now=now)
    after = cloud_simulator.metrics(state, "/metrics/trend", all_time=True)

    assert sum(row["station_events"] for row in after) == (
        sum(row["station_events"] for row in before) + len(cloud_simulator.STATIONS)
    )


def test_cloud_demo_does_not_add_a_vehicle_early():
    state = {}
    cloud_simulator.metrics(state, "/metrics/live-summary")
    now = state["cloud_last_batch"] + timedelta(seconds=14)

    assert not cloud_simulator.advance(state, now=now)
