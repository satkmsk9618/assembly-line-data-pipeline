from assembly_line import auth


def test_pending_oauth_client_is_consumed_once():
    client = object()

    auth.remember_oauth_client("flow-test", client)

    assert auth.take_oauth_client("flow-test") is client
    assert auth.take_oauth_client("flow-test") is None


def test_expired_oauth_client_is_not_returned(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    client = object()

    auth.remember_oauth_client("expired-flow-test", client)
    now[0] += auth._OAUTH_STATE_TTL_SECONDS + 1

    assert auth.take_oauth_client("expired-flow-test") is None
