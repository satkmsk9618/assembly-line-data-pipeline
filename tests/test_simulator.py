import random

from assembly_line import simulator


class FakeCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor


def test_live_generator_writes_one_vehicle_across_five_stations(monkeypatch):
    cursor = FakeCursor()
    monkeypatch.setattr(simulator, "connect", lambda: FakeConnection(cursor))

    result = simulator.produce_batch(random.Random(7))

    station_calls = [call for call in cursor.calls if "INSERT INTO fact_station_event" in call[0]]
    assert len(station_calls) == 5
    assert len({call[1][0] for call in station_calls}) == 1
    assert all(call[1][3] > 0 for call in station_calls)
    assert result["station_events"] == 5


def test_live_generator_uses_fifteen_second_interval():
    assert simulator.STREAM_INTERVAL_SECONDS == 15
