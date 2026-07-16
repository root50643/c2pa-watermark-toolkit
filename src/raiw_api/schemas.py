from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class MeResponse(BaseModel):
    customer_id: str
    customer_name: str
    external_id: str | None
    key_id: str
    key_prefix: str


class IdentifyResponse(BaseModel):
    request_id: str
    archive_id: str
    report: dict[str, Any]


class JobAccepted(BaseModel):
    job_id: str
    archive_id: str
    status: Literal["queued"] = "queued"
    status_url: str
    result_url: str


class JobStatus(BaseModel):
    job_id: str
    archive_id: str
    task_name: str
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: int = Field(ge=0, le=100)
    message: str | None = None
    error: dict[str, Any] | None = None
    created_at: str
    updated_at: str
    result_url: str | None = None


class CapabilitiesResponse(BaseModel):
    app_version: str
    upstream_version: str
    supported_formats: list[str]
    max_upload_mb: int
    max_image_pixels: int
    archive_ready: bool
    redis_ready: bool
    visible_backends: list[str]
    gpu_pipelines: list[str]
