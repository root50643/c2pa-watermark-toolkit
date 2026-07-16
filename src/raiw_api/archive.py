from __future__ import annotations

import hashlib
import json
import os
import shutil
import warnings
from contextlib import suppress
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from PIL import Image

from raiw_api import __version__
from raiw_api.config import Settings
from raiw_api.db import Database, utc_now
from raiw_api.errors import APIError
from raiw_api.security import Principal

FORMAT_MAP = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "WEBP": (".webp", "image/webp"),
    "HEIF": (".heif", "image/heif"),
    "HEIC": (".heic", "image/heic"),
    "AVIF": (".avif", "image/avif"),
}


@dataclass(frozen=True, slots=True)
class ArchivedUpload:
    request_id: str
    directory: Path
    input_path: Path
    extension: str
    mime: str
    width: int
    height: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _upstream_version() -> str:
    try:
        return version("remove-ai-watermarks")
    except PackageNotFoundError:
        return "unavailable"


def _register_heif() -> None:
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except ImportError:
        pass


def _sniff_magic(head: bytes) -> bool:
    if head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff"):
        return True
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return True
    return len(head) >= 12 and head[4:8] == b"ftyp"


class ArchiveManager:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db

    async def archive_upload(
        self,
        upload: UploadFile,
        *,
        request_id: str,
        endpoint: str,
        params: dict[str, Any],
        principal: Principal,
    ) -> ArchivedUpload:
        now = utc_now()
        day = now[:10].replace("-", os.sep)
        directory = self.settings.archive_root / day / request_id
        directory.mkdir(parents=True, exist_ok=False)
        temp_path = directory / ".original.uploading"
        size = 0
        digest = hashlib.sha256()
        head = b""
        try:
            with temp_path.open("xb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise APIError(413, "upload_too_large", "Uploaded image exceeds the configured size limit")
                    if len(head) < 64:
                        head += chunk[: 64 - len(head)]
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if size == 0:
                raise APIError(422, "empty_upload", "Uploaded file is empty")
            if not _sniff_magic(head):
                raise APIError(415, "unsupported_media_type", "File signature is not a supported image format")

            _register_heif()
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(temp_path) as image:
                    image_format = (image.format or "").upper()
                    width, height = image.size
                    if width <= 0 or height <= 0 or width * height > self.settings.max_image_pixels:
                        raise APIError(413, "image_too_large", "Decoded image exceeds the configured pixel limit")
                    image.verify()
            if image_format not in FORMAT_MAP:
                raise APIError(415, "unsupported_media_type", f"Unsupported decoded image format: {image_format}")
            extension, mime = FORMAT_MAP[image_format]
            input_path = directory / f"original{extension}"
            temp_path.replace(input_path)
            relative_input = input_path.relative_to(self.settings.archive_root).as_posix()
            relative_manifest = (directory / "manifest.json").relative_to(self.settings.archive_root).as_posix()
            row = {
                "request_id": request_id,
                "customer_id": principal.customer_id,
                "key_id": principal.key_id,
                "received_at": now,
                "endpoint": endpoint,
                "params_json": json.dumps(params, ensure_ascii=False, sort_keys=True),
                "status": "accepted",
                "input_path": relative_input,
                "input_sha256": digest.hexdigest(),
                "input_size": size,
                "width": width,
                "height": height,
                "mime": mime,
                "manifest_path": relative_manifest,
                "app_version": __version__,
                "upstream_version": _upstream_version(),
                "git_commit": self.settings.git_commit,
            }
            self.db.insert_archive(row)
            self.write_manifest(request_id)
            return ArchivedUpload(request_id, directory, input_path, extension, mime, width, height)
        except APIError:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        except Exception as exc:
            with suppress(Exception):
                self.db.delete_archive_record(request_id)
            shutil.rmtree(directory, ignore_errors=True)
            raise APIError(507, "archive_unavailable", "Could not persist the uploaded image", str(exc)) from exc
        finally:
            await upload.close()

    def work_path(self, archived: ArchivedUpload, label: str = "working") -> Path:
        return archived.directory / f".{label}{archived.extension}"

    def mark_success(
        self,
        request_id: str,
        *,
        response: dict[str, Any],
        output_source: Path | None = None,
        duration_ms: float | None = None,
    ) -> Path | None:
        row = self.db.get_archive(request_id)
        if not row:
            raise RuntimeError(f"Archive record not found: {request_id}")
        directory = self.settings.archive_root / Path(row["input_path"]).parent
        response_path = directory / "response.json"
        self._atomic_json(response_path, response)
        changes: dict[str, Any] = {
            "status": "succeeded",
            "response_path": response_path.relative_to(self.settings.archive_root).as_posix(),
            "duration_ms": duration_ms,
            "error_code": None,
            "error_message": None,
        }
        output_path: Path | None = None
        if output_source is not None:
            extension = Path(row["input_path"]).suffix
            output_path = directory / f"processed{extension}"
            temp_output = directory / f".processed{extension}.tmp"
            shutil.copyfile(output_source, temp_output)
            with temp_output.open("rb") as handle:
                os.fsync(handle.fileno())
            temp_output.replace(output_path)
            changes.update(
                output_path=output_path.relative_to(self.settings.archive_root).as_posix(),
                output_sha256=_sha256(output_path),
                output_size=output_path.stat().st_size,
            )
        self.db.update_archive(request_id, **changes)
        self.write_manifest(request_id)
        return output_path

    def mark_failure(
        self,
        request_id: str,
        *,
        code: str,
        message: str,
        details: Any = None,
        duration_ms: float | None = None,
    ) -> None:
        row = self.db.get_archive(request_id)
        if not row:
            return
        directory = self.settings.archive_root / Path(row["input_path"]).parent
        response_path = directory / "response.json"
        payload = {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}
        self._atomic_json(response_path, payload)
        self.db.update_archive(
            request_id,
            status="failed",
            error_code=code,
            error_message=message,
            response_path=response_path.relative_to(self.settings.archive_root).as_posix(),
            duration_ms=duration_ms,
        )
        self.write_manifest(request_id)

    def write_manifest(self, request_id: str) -> None:
        row = self.db.get_archive(request_id)
        if not row:
            return
        manifest = dict(row)
        manifest["parameters"] = json.loads(manifest.pop("params_json"))
        path = self.settings.archive_root / row["manifest_path"]
        self._atomic_json(path, manifest)

    def absolute_path(self, relative_path: str) -> Path:
        resolved = (self.settings.archive_root / relative_path).resolve()
        if self.settings.archive_root not in resolved.parents and resolved != self.settings.archive_root:
            raise ValueError("Archive path escaped the configured root")
        return resolved

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        temp = path.with_name(f".{path.name}.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        temp.replace(path)
