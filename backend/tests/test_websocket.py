import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import auth_headers
from tests.test_ride_flow import _confirmed_ride


def token_of(headers: dict) -> str:
    return headers["Authorization"].split()[1]


def test_chat_websocket_broadcasts_and_persists(client, db_session, monkeypatch):
    monkeypatch.setattr("app.routers.messages.SessionLocal", lambda: db_session)
    (ha, hb, hc), dh, driver, ride = _confirmed_ride(client, db_session)
    url = f"/ws/rides/{ride['id']}"
    with client.websocket_connect(f"{url}?token={token_of(ha)}") as a, client.websocket_connect(f"{url}?token={token_of(dh)}") as d:
        a.send_json({"body": "Call 604 555 1234", "kind": "text"})
        for sock in (a, d):
            msg = sock.receive_json()
            assert msg["type"] == "message" and "[number hidden]" in msg["body"]
    history = client.get(f"/rides/{ride['id']}/messages", headers=hb).json()
    assert any("[number hidden]" in m["body"] for m in history)


def test_websocket_rejects_bad_token_and_non_participants(client, db_session, monkeypatch):
    monkeypatch.setattr("app.routers.messages.SessionLocal", lambda: db_session)
    (ha, hb, hc), dh, driver, ride = _confirmed_ride(client, db_session)
    url = f"/ws/rides/{ride['id']}"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{url}?token=garbage"):
            pass
    stranger = auth_headers(client, "stranger@t.dev")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{url}?token={token_of(stranger)}"):
            pass
