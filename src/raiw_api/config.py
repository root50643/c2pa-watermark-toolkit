from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    archive_root: Path
    api_key_pepper: str
    max_upload_bytes: int
    max_image_pixels: int
    trusted_proxy_cidrs: tuple[str, ...]
    redis_url: str
    gpu_device: str
    gpu_model_id: str | None
    hf_token: str | None
    git_commit: str
    log_level: str

    @property
    def database_path(self) -> Path:
        return self.archive_root / "raiw-api.sqlite3"


def get_settings() -> Settings:
    root = Path(os.getenv("ARCHIVE_ROOT", "./archive-data")).expanduser().resolve()
    return Settings(
        archive_root=root,
        api_key_pepper=os.getenv("API_KEY_PEPPER", "development-only-change-me"),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024,
        max_image_pixels=int(os.getenv("MAX_IMAGE_PIXELS", "50000000")),
        trusted_proxy_cidrs=_csv(os.getenv("TRUSTED_PROXY_CIDRS", "")),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        gpu_device=os.getenv("GPU_DEVICE", "cuda"),
        gpu_model_id=os.getenv("GPU_MODEL_ID") or None,
        hf_token=os.getenv("HF_TOKEN") or None,
        git_commit=os.getenv("GIT_COMMIT", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
