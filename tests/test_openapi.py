from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from raiw_api.main import app

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _resolve(schema: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if not reference:
        return schema
    name = reference.rsplit("/", 1)[-1]
    return document["components"]["schemas"][name]


def test_every_request_field_has_a_swagger_description() -> None:
    document = app.openapi()
    missing: list[str] = []
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            for parameter in operation.get("parameters", []):
                if not parameter.get("description"):
                    missing.append(f"{method.upper()} {path} parameter:{parameter['name']}")
            for media_type, media in operation.get("requestBody", {}).get("content", {}).items():
                body_schema = _resolve(media["schema"], document)
                for name, field_schema in body_schema.get("properties", {}).items():
                    if not field_schema.get("description"):
                        missing.append(f"{method.upper()} {path} {media_type}:{name}")
    assert missing == []


def test_api_key_and_keep_standard_are_explicitly_documented() -> None:
    document = app.openapi()
    api_key = document["components"]["securitySchemes"]["X-API-Key"]
    assert api_key["type"] == "apiKey"
    assert api_key["in"] == "header"
    assert api_key["name"] == "X-API-Key"
    assert "Bearer" in api_key["description"]

    operation = document["paths"]["/api/v1/remove/metadata"]["post"]
    body_reference = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    body_schema = _resolve(body_reference, document)
    description = body_schema["properties"]["keep_standard"]["description"]
    assert "true" in description
    assert "false" in description
    assert "C2PA" in description
    assert "不保證清空所有 metadata" in description


def test_protected_operations_reference_the_api_key_scheme() -> None:
    document = app.openapi()
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            if path.startswith("/api/v1/") and path != "/api/v1/capabilities":
                assert operation["security"] == [{"X-API-Key": []}], f"{method.upper()} {path}"


def test_openapi_marks_key_as_optional_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_API_KEY", "false")
    document = app.openapi()
    operation = document["paths"]["/api/v1/me"]["get"]
    assert operation["security"] == [{}, {"X-API-Key": []}]
    assert "未強制" in document["components"]["securitySchemes"]["X-API-Key"]["description"]

    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    assert app.openapi()["paths"]["/api/v1/me"]["get"]["security"] == [{"X-API-Key": []}]


def test_openapi_does_not_publish_image_retention_notice() -> None:
    published = json.dumps(app.openapi(), ensure_ascii=False).lower()
    for phrase in ("永久", "retained permanently", "permanently archived", "retention and audit"):
        assert phrase not in published


def test_response_model_fields_have_descriptions() -> None:
    document = app.openapi()
    names = {
        "CapabilitiesResponse",
        "ErrorBody",
        "ErrorResponse",
        "IdentifyResponse",
        "JobAccepted",
        "JobStatus",
        "MeResponse",
    }
    missing: list[str] = []
    for name in names:
        model = document["components"]["schemas"][name]
        for field_name, field_schema in model["properties"].items():
            if not field_schema.get("description"):
                missing.append(f"{name}.{field_name}")
    assert missing == []


def test_postman_multipart_fields_match_openapi_and_have_descriptions() -> None:
    document = app.openapi()
    collection_path = Path("postman/remove-ai-watermarks-api.postman_collection.json")
    collection = json.loads(collection_path.read_text(encoding="utf-8"))

    requests: dict[str, dict[str, Any]] = {}

    def collect(items: list[dict[str, Any]]) -> None:
        for item in items:
            if "item" in item:
                collect(item["item"])
                continue
            request = item["request"]
            url = request["url"].removeprefix("{{base_url}}")
            requests[url] = request

    collect(collection["item"])
    for path, path_item in document["paths"].items():
        operation = path_item.get("post")
        if not operation or "requestBody" not in operation:
            continue
        body_reference = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
        body_schema = _resolve(body_reference, document)
        postman_fields = requests[path]["body"]["formdata"]
        assert {field["key"] for field in postman_fields} == set(body_schema["properties"]), path
        assert all(field.get("description") for field in postman_fields), path
