from __future__ import annotations

from raiw_api.security import authenticate_api_key, client_ip, issue_api_key


def test_key_is_hashed_and_can_be_revoked(client):
    _, _, customer, _, _ = client
    from raiw_api.main import app

    plain, record = issue_api_key(app.state.db, app.state.settings.api_key_pepper, customer["id"])
    stored = app.state.db.get_api_key(record["id"])
    assert stored is not None
    assert plain not in stored["key_hmac"]
    assert authenticate_api_key(app.state.db, app.state.settings.api_key_pepper, plain) is not None
    assert app.state.db.revoke_api_key(record["id"])
    assert authenticate_api_key(app.state.db, app.state.settings.api_key_pepper, plain) is None


def test_forwarded_ip_only_from_trusted_peer():
    trusted = ("10.0.0.0/8",)
    assert client_ip("10.0.0.2", "198.51.100.10, 10.0.0.3", trusted) == "198.51.100.10"
    assert client_ip("203.0.113.8", "198.51.100.10", trusted) == "203.0.113.8"
