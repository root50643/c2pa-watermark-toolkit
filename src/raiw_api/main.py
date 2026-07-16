from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from starlette.concurrency import run_in_threadpool

from raiw_api import __version__
from raiw_api.archive import ArchivedUpload, ArchiveManager
from raiw_api.config import Settings, get_settings
from raiw_api.db import Database, utc_now
from raiw_api.errors import APIError, NoVisibleMarkError
from raiw_api.schemas import (
    CapabilitiesResponse,
    ErrorResponse,
    IdentifyResponse,
    JobAccepted,
    JobStatus,
    MeResponse,
)
from raiw_api.security import Principal, authenticate_api_key, client_ip
from raiw_api.services import (
    erase_image,
    identify_image,
    parse_regions,
    remove_metadata_image,
    remove_visible_image,
)

logger = logging.getLogger(__name__)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _upstream_version() -> str:
    try:
        return version("remove-ai-watermarks")
    except PackageNotFoundError:
        return "unavailable"


def _error_response(request: Request, status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": jsonable_encoder(details),
                "request_id": request_id,
            }
        },
    )


def _forwarded_for(request: Request) -> str | None:
    if value := request.headers.get("x-forwarded-for"):
        return value
    forwarded = request.headers.get("forwarded")
    if not forwarded:
        return None
    values: list[str] = []
    for entry in forwarded.split(","):
        for part in entry.split(";"):
            if part.strip().lower().startswith("for="):
                value = part.split("=", 1)[1].strip().strip('"')
                if value.startswith("[") and "]" in value:
                    value = value[1 : value.index("]")]
                elif value.count(":") == 1:
                    value = value.split(":", 1)[0]
                values.append(value)
    return ",".join(values) or None


def _redis_ready(settings: Settings) -> bool:
    try:
        from redis import Redis

        client = Redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
        return bool(client.ping())
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings.archive_root.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_path)
    db.initialize()
    app.state.settings = settings
    app.state.db = db
    app.state.archive = ArchiveManager(settings, db)
    yield


app = FastAPI(
    title="C2PA Watermark Toolkit API",
    summary="具有永久圖片留存與客戶稽核的 AI 浮水印處理 API",
    description=(
        "所有通過基本驗證的上傳圖片都會永久保存。除健康檢查、capabilities 與文件外，"
        "請先在 Swagger 的 Authorize 輸入客戶專屬 X-API-Key。"
    ),
    version=__version__,
    license_info={"name": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"},
    responses={
        422: {"model": ErrorResponse, "description": "Validation or image-processing error"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
    lifespan=lifespan,
)


@app.middleware("http")
async def request_audit_middleware(request: Request, call_next: Any) -> JSONResponse:
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    request.state.customer_id = None
    request.state.key_id = None
    request.state.archive_id = None
    started_at = utc_now()
    started = time.perf_counter()
    peer_ip = request.client.host if request.client else "unknown"
    settings: Settings = getattr(request.app.state, "settings", get_settings())
    source_ip = client_ip(peer_ip, _forwarded_for(request), settings.trusted_proxy_cidrs)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error (%s)", request_id)
        response = _error_response(request, 500, "internal_error", "Unexpected server error")
    response.headers["X-Request-ID"] = request_id
    if request.url.path.startswith("/api/v1/"):
        duration = (time.perf_counter() - started) * 1000
        route = getattr(request.scope.get("route"), "path", request.url.path)
        row = {
            "request_id": request_id,
            "customer_id": request.state.customer_id,
            "key_id": request.state.key_id,
            "started_at": started_at,
            "finished_at": utc_now(),
            "client_ip": source_ip,
            "peer_ip": peer_ip,
            "user_agent": request.headers.get("user-agent", "")[:512],
            "method": request.method,
            "route": route,
            "status_code": response.status_code,
            "duration_ms": duration,
            "request_bytes": (
                int(request.headers["content-length"])
                if request.headers.get("content-length", "").isdigit()
                else None
            ),
            "response_bytes": (
                int(response.headers["content-length"])
                if response.headers.get("content-length", "").isdigit()
                else None
            ),
            "archive_id": request.state.archive_id,
        }
        try:
            request.app.state.db.insert_access_log(row)
        except Exception:
            logger.exception("Could not persist access log for %s", request_id)
    return response


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return _error_response(request, exc.status_code, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(request, 422, "validation_error", "Request validation failed", exc.errors())


async def require_principal(
    request: Request,
    api_key: Annotated[str | None, Depends(api_key_header)],
) -> Principal:
    if not api_key:
        raise APIError(401, "missing_api_key", "X-API-Key is required")
    principal = await run_in_threadpool(
        authenticate_api_key,
        request.app.state.db,
        request.app.state.settings.api_key_pepper,
        api_key,
    )
    if not principal:
        raise APIError(401, "invalid_api_key", "API key is invalid, revoked, or belongs to a disabled customer")
    request.state.customer_id = principal.customer_id
    request.state.key_id = principal.key_id
    return principal


def _archive(request: Request) -> ArchiveManager:
    return request.app.state.archive


async def _save_upload(
    request: Request,
    upload: UploadFile,
    principal: Principal,
    params: dict[str, Any],
) -> ArchivedUpload:
    archived = await _archive(request).archive_upload(
        upload,
        request_id=request.state.request_id,
        endpoint=request.url.path,
        params=params,
        principal=principal,
    )
    request.state.archive_id = archived.request_id
    return archived


def _fail_archived(request: Request, code: str, message: str, details: Any, started: float) -> None:
    _archive(request).mark_failure(
        request.state.request_id,
        code=code,
        message=message,
        details=details,
        duration_ms=(time.perf_counter() - started) * 1000,
    )


@app.get("/healthz", tags=["System"])
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz", tags=["System"])
async def readyz(request: Request) -> JSONResponse:
    try:
        test_file = request.app.state.settings.archive_root / ".ready"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        request.app.state.db._one("SELECT 1 AS ok")
        return JSONResponse({"status": "ready", "archive": True, "database": True})
    except Exception as exc:
        return _error_response(request, 503, "not_ready", "Archive or database is unavailable", str(exc))


@app.get("/api/v1/capabilities", response_model=CapabilitiesResponse, tags=["System"])
async def capabilities(request: Request) -> CapabilitiesResponse:
    settings: Settings = request.app.state.settings
    return CapabilitiesResponse(
        app_version=__version__,
        upstream_version=_upstream_version(),
        supported_formats=["avif", "heic", "heif", "jpeg", "png", "webp"],
        max_upload_mb=settings.max_upload_bytes // 1024 // 1024,
        max_image_pixels=settings.max_image_pixels,
        archive_ready=settings.archive_root.is_dir(),
        redis_ready=await run_in_threadpool(_redis_ready, settings),
        visible_backends=["cv2", "migan", "lama"],
        gpu_pipelines=["controlnet", "sdxl", "qwen"],
    )


@app.get("/api/v1/me", response_model=MeResponse, tags=["Customer"])
async def me(principal: Annotated[Principal, Depends(require_principal)]) -> MeResponse:
    return MeResponse(
        customer_id=principal.customer_id,
        customer_name=principal.customer_name,
        external_id=principal.external_id,
        key_id=principal.key_id,
        key_prefix=principal.key_prefix,
    )


@app.post(
    "/api/v1/identify",
    response_model=IdentifyResponse,
    responses={401: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}},
    tags=["Analysis"],
)
async def identify_endpoint(
    request: Request,
    principal: Annotated[Principal, Depends(require_principal)],
    file: Annotated[UploadFile, File(description="PNG, JPEG, WebP, HEIC, HEIF, or AVIF image")],
) -> IdentifyResponse:
    started = time.perf_counter()
    archived = await _save_upload(request, file, principal, {})
    try:
        report = jsonable_encoder(await run_in_threadpool(identify_image, archived.input_path))
        payload = {"request_id": archived.request_id, "archive_id": archived.request_id, "report": report}
        _archive(request).mark_success(
            archived.request_id,
            response=payload,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        return IdentifyResponse(**payload)
    except Exception as exc:
        _fail_archived(request, "processing_failed", "Image identification failed", str(exc), started)
        raise APIError(500, "processing_failed", "Image identification failed") from exc


@app.post("/api/v1/remove/visible", responses={200: {"content": {"image/*": {}}}}, tags=["Removal"])
async def visible_endpoint(
    request: Request,
    principal: Annotated[Principal, Depends(require_principal)],
    file: Annotated[UploadFile, File()],
    sensitivity: Annotated[Literal["auto", "strict", "assume_ai"], Form()] = "auto",
    backend: Annotated[Literal["cv2", "migan", "lama"], Form()] = "cv2",
    strip_metadata: Annotated[bool, Form()] = True,
) -> FileResponse:
    params = {"sensitivity": sensitivity, "backend": backend, "strip_metadata": strip_metadata}
    started = time.perf_counter()
    archived = await _save_upload(request, file, principal, params)
    work = _archive(request).work_path(archived, "visible")
    try:
        removed = await run_in_threadpool(
            remove_visible_image,
            archived.input_path,
            work,
            sensitivity=sensitivity,
            backend=backend,
            strip_metadata=strip_metadata,
        )
        payload = {"request_id": archived.request_id, "archive_id": archived.request_id, "removed_marks": removed}
        output = _archive(request).mark_success(
            archived.request_id,
            response=payload,
            output_source=work,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        if output is None:
            raise RuntimeError("Archive did not produce a visible-removal result")
        return FileResponse(
            output,
            media_type=archived.mime,
            filename=f"processed{archived.extension}",
            headers={"X-Archive-ID": archived.request_id, "X-Removed-Marks": ", ".join(removed)},
        )
    except NoVisibleMarkError as exc:
        _fail_archived(request, "no_visible_mark", str(exc), None, started)
        raise APIError(422, "no_visible_mark", str(exc)) from exc
    except APIError:
        raise
    except Exception as exc:
        _fail_archived(request, "processing_failed", "Visible watermark removal failed", str(exc), started)
        raise APIError(500, "processing_failed", "Visible watermark removal failed") from exc
    finally:
        work.unlink(missing_ok=True)


@app.post("/api/v1/remove/erase", responses={200: {"content": {"image/*": {}}}}, tags=["Removal"])
async def erase_endpoint(
    request: Request,
    principal: Annotated[Principal, Depends(require_principal)],
    file: Annotated[UploadFile, File()],
    regions: Annotated[str, Form(description='JSON: [[x,y,width,height]] or [{"x":0,"y":0,"width":10,"height":10}]')],
    backend: Annotated[Literal["cv2", "migan", "lama"], Form()] = "cv2",
    method: Annotated[Literal["telea", "ns"], Form()] = "telea",
    dilate: Annotated[int, Form(ge=0, le=100)] = 3,
    strip_metadata: Annotated[bool, Form()] = True,
) -> FileResponse:
    params = {
        "regions": regions,
        "backend": backend,
        "method": method,
        "dilate": dilate,
        "strip_metadata": strip_metadata,
    }
    started = time.perf_counter()
    archived = await _save_upload(request, file, principal, params)
    work = _archive(request).work_path(archived, "erase")
    try:
        boxes = parse_regions(regions, width=archived.width, height=archived.height)
        await run_in_threadpool(
            erase_image,
            archived.input_path,
            work,
            boxes=boxes,
            backend=backend,
            method=method,
            dilate=dilate,
            strip_metadata=strip_metadata,
        )
        payload = {"request_id": archived.request_id, "archive_id": archived.request_id, "regions": len(boxes)}
        output = _archive(request).mark_success(
            archived.request_id,
            response=payload,
            output_source=work,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        if output is None:
            raise RuntimeError("Archive did not produce an erase result")
        return FileResponse(
            output,
            media_type=archived.mime,
            filename=f"processed{archived.extension}",
            headers={"X-Archive-ID": archived.request_id},
        )
    except APIError as exc:
        _fail_archived(request, exc.code, exc.message, exc.details, started)
        raise
    except Exception as exc:
        _fail_archived(request, "processing_failed", "Region erase failed", str(exc), started)
        raise APIError(500, "processing_failed", "Region erase failed") from exc
    finally:
        work.unlink(missing_ok=True)


@app.post("/api/v1/remove/metadata", responses={200: {"content": {"image/*": {}}}}, tags=["Removal"])
async def metadata_endpoint(
    request: Request,
    principal: Annotated[Principal, Depends(require_principal)],
    file: Annotated[UploadFile, File()],
    keep_standard: Annotated[bool, Form()] = True,
) -> FileResponse:
    params = {"keep_standard": keep_standard}
    started = time.perf_counter()
    archived = await _save_upload(request, file, principal, params)
    work = _archive(request).work_path(archived, "metadata")
    try:
        await run_in_threadpool(remove_metadata_image, archived.input_path, work, keep_standard=keep_standard)
        payload = {"request_id": archived.request_id, "archive_id": archived.request_id, "metadata_removed": True}
        output = _archive(request).mark_success(
            archived.request_id,
            response=payload,
            output_source=work,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        if output is None:
            raise RuntimeError("Archive did not produce a metadata result")
        return FileResponse(
            output,
            media_type=archived.mime,
            filename=f"processed{archived.extension}",
            headers={"X-Archive-ID": archived.request_id},
        )
    except Exception as exc:
        _fail_archived(request, "processing_failed", "Metadata removal failed", str(exc), started)
        raise APIError(500, "processing_failed", "Metadata removal failed") from exc
    finally:
        work.unlink(missing_ok=True)


def _gpu_params(
    *,
    pipeline: str,
    strength: float | None,
    steps: int,
    seed: int | None,
    force: bool,
    strip_metadata: bool,
    max_resolution: int,
    min_resolution: int,
    tile: bool,
    tile_size: int,
    tile_overlap: int,
    sensitivity: str,
    backend: str,
) -> dict[str, Any]:
    return {
        "pipeline": pipeline,
        "strength": strength,
        "steps": steps,
        "seed": seed,
        "force": force,
        "strip_metadata": strip_metadata,
        "max_resolution": max_resolution,
        "min_resolution": min_resolution,
        "tile": tile,
        "tile_size": tile_size,
        "tile_overlap": tile_overlap,
        "sensitivity": sensitivity,
        "backend": backend,
        "adaptive_polish": True,
        "upscaler": "lanczos",
    }


async def _submit_job(
    request: Request,
    principal: Principal,
    file: UploadFile,
    task_name: Literal["invisible", "all"],
    params: dict[str, Any],
) -> JobAccepted:
    archived = await _save_upload(request, file, principal, params)
    if not await run_in_threadpool(_redis_ready, request.app.state.settings):
        _archive(request).mark_failure(
            archived.request_id,
            code="gpu_worker_unavailable",
            message="Redis/GPU queue is unavailable",
        )
        raise APIError(503, "gpu_worker_unavailable", "Start Docker Compose with the gpu profile")
    job = request.app.state.db.create_job(archived.request_id, task_name)
    _archive(request).write_manifest(archived.request_id)
    try:
        from raiw_api.tasks import celery_app

        celery_app.send_task("raiw_api.process_job", args=[job["id"]], task_id=job["id"])
    except Exception as exc:
        request.app.state.db.update_job(job["id"], status="failed", error_code="queue_failed", error_message=str(exc))
        _archive(request).mark_failure(
            archived.request_id,
            code="queue_failed",
            message="Could not enqueue GPU job",
            details=str(exc),
        )
        raise APIError(503, "queue_failed", "Could not enqueue GPU job") from exc
    base = str(request.base_url).rstrip("/")
    return JobAccepted(
        job_id=job["id"],
        archive_id=archived.request_id,
        status_url=f"{base}/api/v1/jobs/{job['id']}",
        result_url=f"{base}/api/v1/jobs/{job['id']}/result",
    )


@app.post("/api/v1/jobs/invisible", response_model=JobAccepted, status_code=202, tags=["GPU Jobs"])
async def invisible_job(
    request: Request,
    principal: Annotated[Principal, Depends(require_principal)],
    file: Annotated[UploadFile, File()],
    pipeline: Annotated[Literal["controlnet", "sdxl", "qwen"], Form()] = "controlnet",
    strength: Annotated[float | None, Form(ge=0, le=1)] = None,
    steps: Annotated[int, Form(ge=1, le=200)] = 50,
    seed: Annotated[int | None, Form()] = None,
    force: Annotated[bool, Form()] = False,
    strip_metadata: Annotated[bool, Form()] = True,
    max_resolution: Annotated[int, Form(ge=0, le=8192)] = 0,
    min_resolution: Annotated[int, Form(ge=0, le=4096)] = 1024,
    tile: Annotated[bool, Form()] = False,
    tile_size: Annotated[int, Form(ge=512, le=2048)] = 1024,
    tile_overlap: Annotated[int, Form(ge=0, le=512)] = 128,
) -> JobAccepted:
    params = _gpu_params(
        pipeline=pipeline,
        strength=strength,
        steps=steps,
        seed=seed,
        force=force,
        strip_metadata=strip_metadata,
        max_resolution=max_resolution,
        min_resolution=min_resolution,
        tile=tile,
        tile_size=tile_size,
        tile_overlap=tile_overlap,
        sensitivity="auto",
        backend="cv2",
    )
    return await _submit_job(request, principal, file, "invisible", params)


@app.post("/api/v1/jobs/all", response_model=JobAccepted, status_code=202, tags=["GPU Jobs"])
async def all_job(
    request: Request,
    principal: Annotated[Principal, Depends(require_principal)],
    file: Annotated[UploadFile, File()],
    pipeline: Annotated[Literal["controlnet", "sdxl", "qwen"], Form()] = "controlnet",
    strength: Annotated[float | None, Form(ge=0, le=1)] = None,
    steps: Annotated[int, Form(ge=1, le=200)] = 50,
    seed: Annotated[int | None, Form()] = None,
    force: Annotated[bool, Form()] = False,
    sensitivity: Annotated[Literal["auto", "strict", "assume_ai"], Form()] = "auto",
    backend: Annotated[Literal["cv2", "migan", "lama"], Form()] = "cv2",
    max_resolution: Annotated[int, Form(ge=0, le=8192)] = 0,
    min_resolution: Annotated[int, Form(ge=0, le=4096)] = 1024,
    tile: Annotated[bool, Form()] = False,
    tile_size: Annotated[int, Form(ge=512, le=2048)] = 1024,
    tile_overlap: Annotated[int, Form(ge=0, le=512)] = 128,
) -> JobAccepted:
    params = _gpu_params(
        pipeline=pipeline,
        strength=strength,
        steps=steps,
        seed=seed,
        force=force,
        strip_metadata=True,
        max_resolution=max_resolution,
        min_resolution=min_resolution,
        tile=tile,
        tile_size=tile_size,
        tile_overlap=tile_overlap,
        sensitivity=sensitivity,
        backend=backend,
    )
    return await _submit_job(request, principal, file, "all", params)


def _authorized_job(request: Request, principal: Principal, job_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    job = request.app.state.db.get_job(job_id)
    if not job:
        raise APIError(404, "job_not_found", "Job was not found")
    archive = request.app.state.db.get_archive(job["archive_id"])
    if not archive or archive["customer_id"] != principal.customer_id:
        raise APIError(404, "job_not_found", "Job was not found")
    return job, archive


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatus, tags=["GPU Jobs"])
async def get_job(
    request: Request,
    job_id: str,
    principal: Annotated[Principal, Depends(require_principal)],
) -> JobStatus:
    job, _ = _authorized_job(request, principal, job_id)
    base = str(request.base_url).rstrip("/")
    error = None
    if job["error_code"]:
        error = {"code": job["error_code"], "message": job["error_message"]}
    return JobStatus(
        job_id=job["id"],
        archive_id=job["archive_id"],
        task_name=job["task_name"],
        status=job["status"],
        progress=job["progress"],
        message=job["message"],
        error=error,
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        result_url=f"{base}/api/v1/jobs/{job_id}/result" if job["status"] == "succeeded" else None,
    )


@app.get("/api/v1/jobs/{job_id}/result", tags=["GPU Jobs"])
async def get_job_result(
    request: Request,
    job_id: str,
    principal: Annotated[Principal, Depends(require_principal)],
) -> FileResponse:
    job, archive = _authorized_job(request, principal, job_id)
    if job["status"] != "succeeded" or not job["result_path"]:
        raise APIError(409, "job_not_complete", "Job result is not available")
    result = _archive(request).absolute_path(job["result_path"])
    if not result.exists():
        raise APIError(410, "result_missing", "Archived result file is missing")
    return FileResponse(result, media_type=archive["mime"], filename=f"processed{result.suffix}")


def run() -> None:
    import uvicorn

    uvicorn.run("raiw_api.main:app", host="0.0.0.0", port=8000)
