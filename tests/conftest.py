from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from raiw_api.main import app
from raiw_api.security import issue_api_key


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    archive = tmp_path / "archive"
    monkeypatch.setenv("ARCHIVE_ROOT", str(archive))
    monkeypatch.setenv("API_KEY_PEPPER", "test-pepper-not-for-production")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "127.0.0.0/8")
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        customer = app.state.db.create_customer("Test Customer", "customer-001", "test@example.invalid")
        key, record = issue_api_key(app.state.db, app.state.settings.api_key_pepper, customer["id"])
        yield test_client, key, customer, record, archive


@pytest.fixture
def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), (120, 80, 40)).save(output, format="PNG")
    return output.getvalue()
