from __future__ import annotations

import shutil
from pathlib import Path

from raiw_api.errors import NoVisibleMarkError


def auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def upload(data: bytes, name: str = "image.png") -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, data, "image/png")}


def test_health_and_authentication(client):
    http, key, customer, record, _ = client
    assert http.get("/healthz").status_code == 200
    denied = http.get("/api/v1/me")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "missing_api_key"
    allowed = http.get("/api/v1/me", headers=auth(key))
    assert allowed.status_code == 200
    assert allowed.json()["customer_id"] == customer["id"]
    assert allowed.json()["key_id"] == record["id"]
    assert allowed.headers["X-Request-ID"]


def test_identify_archives_original_and_response(client, png_bytes, monkeypatch):
    http, key, _, _, archive_root = client
    monkeypatch.setattr("raiw_api.main.identify_image", lambda path: {"path": str(path), "platform": "test"})
    response = http.post("/api/v1/identify", headers=auth(key), files=upload(png_bytes))
    assert response.status_code == 200
    archive_id = response.json()["archive_id"]
    from raiw_api.main import app

    row = app.state.db.get_archive(archive_id)
    assert row is not None and row["status"] == "succeeded"
    assert (archive_root / row["input_path"]).read_bytes() == png_bytes
    assert (archive_root / row["response_path"]).exists()
    assert (archive_root / row["manifest_path"]).exists()


def test_every_request_gets_a_separate_copy(client, png_bytes, monkeypatch):
    http, key, _, _, archive_root = client

    def copy_metadata(source: Path, output: Path, *, keep_standard: bool) -> None:
        shutil.copyfile(source, output)

    monkeypatch.setattr("raiw_api.main.remove_metadata_image", copy_metadata)
    first = http.post("/api/v1/remove/metadata", headers=auth(key), files=upload(png_bytes))
    second = http.post("/api/v1/remove/metadata", headers=auth(key), files=upload(png_bytes))
    assert first.status_code == second.status_code == 200
    assert first.headers["X-Archive-ID"] != second.headers["X-Archive-ID"]
    from raiw_api.main import app

    rows = app.state.db.list_archives()
    assert len(rows) == 2
    assert rows[0]["input_sha256"] == rows[1]["input_sha256"]
    assert rows[0]["input_path"] != rows[1]["input_path"]
    assert all((archive_root / row["output_path"]).exists() for row in rows)


def test_no_visible_mark_returns_422_and_keeps_input(client, png_bytes, monkeypatch):
    http, key, _, _, archive_root = client

    def no_mark(*args, **kwargs):
        raise NoVisibleMarkError("none")

    monkeypatch.setattr("raiw_api.main.remove_visible_image", no_mark)
    response = http.post("/api/v1/remove/visible", headers=auth(key), files=upload(png_bytes))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_visible_mark"
    from raiw_api.main import app

    row = app.state.db.list_archives()[0]
    assert row["status"] == "failed"
    assert (archive_root / row["input_path"]).exists()


def test_invalid_magic_is_not_archived_but_is_audited(client):
    http, key, _, _, _ = client
    response = http.post("/api/v1/identify", headers=auth(key), files=upload(b"not an image"))
    assert response.status_code == 415
    from raiw_api.main import app

    assert app.state.db.list_archives() == []
    logs = app.state.db.list_access_logs()
    assert logs[-1]["status_code"] == 415


def test_access_log_records_customer_ip_and_route(client):
    http, key, customer, record, _ = client
    response = http.get(
        "/api/v1/me",
        headers={**auth(key), "X-Forwarded-For": "198.51.100.44", "User-Agent": "audit-test"},
    )
    assert response.status_code == 200
    from raiw_api.main import app

    row = app.state.db.list_access_logs()[-1]
    assert row["customer_id"] == customer["id"]
    assert row["key_id"] == record["id"]
    assert row["client_ip"] == "198.51.100.44"
    assert row["peer_ip"] == "127.0.0.1"
    assert row["route"] == "/api/v1/me"
    assert row["user_agent"] == "audit-test"
