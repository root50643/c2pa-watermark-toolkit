from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi import Path as PathParameter
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
from raiw_api.security import Principal, anonymous_principal, authenticate_api_key, client_ip
from raiw_api.services import (
    erase_image,
    identify_image,
    parse_regions,
    remove_metadata_image,
    remove_visible_image,
)

logger = logging.getLogger(__name__)

UPLOAD_DESCRIPTION = (
    "要處理的圖片檔。支援 PNG、JPEG、WebP、HEIC、HEIF、AVIF；預設上限為 25 MB 與 50 MP，"
    "實際限制以 /api/v1/capabilities 為準。"
)
SENSITIVITY_DESCRIPTION = (
    "可見標記偵測策略：auto 只在 metadata 或同產品標記提供佐證時放寬門檻；strict 永不放寬，"
    "誤判風險最低；assume_ai 對所有已知標記放寬門檻，適合已知為 AI 圖片但較可能誤判。"
)
BACKEND_DESCRIPTION = (
    "指定修補後端：cv2 是快速的傳統 OpenCV 修補；migan 與 lama 是較耗資源的神經網路修補，"
    "通常適合較大或較複雜區域。"
)
STRIP_METADATA_DESCRIPTION = (
    "是否在產生結果後移除可辨識的 AI provenance metadata（包含 C2PA 與 AI 相關 EXIF/XMP/IPTC）。"
    "這不是保證清空所有一般 metadata。"
)
KEEP_STANDARD_DESCRIPTION = (
    "true（預設）會移除 AI/C2PA 資訊，同時盡量保留非 AI 的一般欄位，例如 Author、Title、"
    "Description、Copyright、Comment、Software、Source 與 Creation Time；false 不保留這些白名單文字欄位，"
    "採較積極的清理。上游會依格式採不同的無損策略，因此 false 不保證清空所有 metadata：JPEG 可能保留"
    "已清除 AI 標記的正常 EXIF，HEIF/AVIF 也會保留非 AI 的容器資料。"
)
REGIONS_DESCRIPTION = (
    "以 JSON 字串提供 1 到 20 個原圖像素座標框。格式可為 [[x,y,width,height]] 或"
    ' [{"x":0,"y":0,"width":10,"height":10}]；x/y 是左上角，寬高必須大於 0，且框不可超出圖片。'
)
METHOD_DESCRIPTION = (
    "OpenCV 修補演算法：telea 通常較快且適合小區域；ns 使用 Navier-Stokes 方法。"
    "只有 backend=cv2 時生效。"
)
DILATE_DESCRIPTION = "修補前將每個遮罩向外擴張的像素數；0 表示不擴張，可用來涵蓋浮水印邊緣。"
PIPELINE_DESCRIPTION = (
    "GPU 重生成 pipeline：controlnet（預設）以邊緣條件保留文字、臉部與結構；sdxl 較輕量但在平面圖像上"
    "可能保留訊號；qwen 最重、需要雲端級 CUDA 資源，但通常最能保留文字與結構。"
)
STRENGTH_DESCRIPTION = (
    "擴散重建強度 0 到 1；值越高通常改動越大。省略時使用偵測到的供應商自適應預設值。"
)
STEPS_DESCRIPTION = "擴散去噪步數；增加步數會增加處理時間，且不保證結果一定更好。"
SEED_DESCRIPTION = "選填的隨機種子；固定模型、參數與執行環境時可協助重現結果，省略則使用隨機結果。"
FORCE_DESCRIPTION = (
    "即使本地未偵測到不可見浮水印訊號仍執行 GPU 重生成。可能改動沒有浮水印的圖片，且不代表保證移除訊號。"
)
MAX_RESOLUTION_DESCRIPTION = (
    "擴散處理前的圖片長邊上限（像素）；0 表示不限制。正值可降低 GPU 記憶體需求，但縮小後再放大可能損失細節。"
)
MIN_RESOLUTION_DESCRIPTION = (
    "擴散處理前的圖片長邊下限（像素）；小圖會先放大、完成後還原原尺寸。0 表示停用；若大於 max_resolution，"
    "且 max_resolution 不為 0，上游會忽略此下限。"
)
TILE_DESCRIPTION = (
    "是否以重疊分塊執行擴散，降低大圖的峰值 GPU 記憶體；只有長邊大於 tile_size 時才啟用。"
    "建議搭配 max_resolution=0 以保留原解析度。"
)
TILE_SIZE_DESCRIPTION = "正方形分塊的邊長（像素）；較小可節省記憶體，但會增加分塊數與處理時間。"
TILE_OVERLAP_DESCRIPTION = "相鄰分塊的重疊寬度（像素），用於羽化接合並降低接縫；較大會增加重複運算。"

api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="X-API-Key",
    description="輸入 raiw_ 開頭的完整客戶 API Key；不要加上 X-API-Key: 或 Bearer 前綴。",
    auto_error=False,
)


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
    if not settings.require_api_key:
        anonymous_principal(db)
    app.state.settings = settings
    app.state.db = db
    app.state.archive = ArchiveManager(settings, db)
    app.openapi_schema = None
    yield


app = FastAPI(
    title="C2PA Watermark Toolkit API",
    summary="AI 浮水印識別、Metadata 清理與影像修補 API",
    description=(
        "除健康檢查、capabilities 與文件外，預設請先在 Swagger 的 Authorize 輸入客戶專屬 "
        "X-API-Key；部署者可用 "
        "REQUIRE_API_KEY=false 關閉強制驗證，實際狀態以 capabilities 為準。"
    ),
    version=__version__,
    license_info={"name": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"},
    responses={
        422: {"model": ErrorResponse, "description": "Validation or image-processing error"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
    lifespan=lifespan,
)

_default_openapi = app.openapi
_openapi_mode: bool | None = None


def custom_openapi() -> dict[str, Any]:
    """Describe authentication according to this deployment's runtime setting."""
    global _openapi_mode
    require_api_key = get_settings().require_api_key
    if _openapi_mode != require_api_key:
        app.openapi_schema = None
    schema = _default_openapi()
    if not require_api_key:
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if isinstance(operation, dict) and operation.get("security") == [{"X-API-Key": []}]:
                    operation["security"] = [{}, {"X-API-Key": []}]
        scheme = schema.get("components", {}).get("securitySchemes", {}).get("X-API-Key")
        if isinstance(scheme, dict):
            scheme["description"] = (
                "此部署未強制要求 API Key。留空會使用匿名身分；若提供金鑰，仍會驗證並歸戶。"
            )
    _openapi_mode = require_api_key
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]


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
        if request.app.state.settings.require_api_key:
            raise APIError(401, "missing_api_key", "X-API-Key is required")
        principal = await run_in_threadpool(anonymous_principal, request.app.state.db)
    else:
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
        api_key_required=settings.require_api_key,
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
    file: Annotated[UploadFile, File(description=UPLOAD_DESCRIPTION)],
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
    file: Annotated[UploadFile, File(description=UPLOAD_DESCRIPTION)],
    sensitivity: Annotated[
        Literal["auto", "strict", "assume_ai"], Form(description=SENSITIVITY_DESCRIPTION)
    ] = "auto",
    backend: Annotated[Literal["cv2", "migan", "lama"], Form(description=BACKEND_DESCRIPTION)] = "cv2",
    strip_metadata: Annotated[bool, Form(description=STRIP_METADATA_DESCRIPTION)] = True,
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
    file: Annotated[UploadFile, File(description=UPLOAD_DESCRIPTION)],
    regions: Annotated[str, Form(description=REGIONS_DESCRIPTION)],
    backend: Annotated[Literal["cv2", "migan", "lama"], Form(description=BACKEND_DESCRIPTION)] = "cv2",
    method: Annotated[Literal["telea", "ns"], Form(description=METHOD_DESCRIPTION)] = "telea",
    dilate: Annotated[int, Form(ge=0, le=100, description=DILATE_DESCRIPTION)] = 3,
    strip_metadata: Annotated[bool, Form(description=STRIP_METADATA_DESCRIPTION)] = True,
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
    file: Annotated[UploadFile, File(description=UPLOAD_DESCRIPTION)],
    keep_standard: Annotated[bool, Form(description=KEEP_STANDARD_DESCRIPTION)] = True,
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
    file: Annotated[UploadFile, File(description=UPLOAD_DESCRIPTION)],
    pipeline: Annotated[
        Literal["controlnet", "sdxl", "qwen"], Form(description=PIPELINE_DESCRIPTION)
    ] = "controlnet",
    strength: Annotated[float | None, Form(ge=0, le=1, description=STRENGTH_DESCRIPTION)] = None,
    steps: Annotated[int, Form(ge=1, le=200, description=STEPS_DESCRIPTION)] = 50,
    seed: Annotated[int | None, Form(description=SEED_DESCRIPTION)] = None,
    force: Annotated[bool, Form(description=FORCE_DESCRIPTION)] = False,
    strip_metadata: Annotated[bool, Form(description=STRIP_METADATA_DESCRIPTION)] = True,
    max_resolution: Annotated[int, Form(ge=0, le=8192, description=MAX_RESOLUTION_DESCRIPTION)] = 0,
    min_resolution: Annotated[int, Form(ge=0, le=4096, description=MIN_RESOLUTION_DESCRIPTION)] = 1024,
    tile: Annotated[bool, Form(description=TILE_DESCRIPTION)] = False,
    tile_size: Annotated[int, Form(ge=512, le=2048, description=TILE_SIZE_DESCRIPTION)] = 1024,
    tile_overlap: Annotated[int, Form(ge=0, le=512, description=TILE_OVERLAP_DESCRIPTION)] = 128,
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
    file: Annotated[UploadFile, File(description=UPLOAD_DESCRIPTION)],
    pipeline: Annotated[
        Literal["controlnet", "sdxl", "qwen"], Form(description=PIPELINE_DESCRIPTION)
    ] = "controlnet",
    strength: Annotated[float | None, Form(ge=0, le=1, description=STRENGTH_DESCRIPTION)] = None,
    steps: Annotated[int, Form(ge=1, le=200, description=STEPS_DESCRIPTION)] = 50,
    seed: Annotated[int | None, Form(description=SEED_DESCRIPTION)] = None,
    force: Annotated[bool, Form(description=FORCE_DESCRIPTION)] = False,
    sensitivity: Annotated[
        Literal["auto", "strict", "assume_ai"], Form(description=SENSITIVITY_DESCRIPTION)
    ] = "auto",
    backend: Annotated[Literal["cv2", "migan", "lama"], Form(description=BACKEND_DESCRIPTION)] = "cv2",
    max_resolution: Annotated[int, Form(ge=0, le=8192, description=MAX_RESOLUTION_DESCRIPTION)] = 0,
    min_resolution: Annotated[int, Form(ge=0, le=4096, description=MIN_RESOLUTION_DESCRIPTION)] = 1024,
    tile: Annotated[bool, Form(description=TILE_DESCRIPTION)] = False,
    tile_size: Annotated[int, Form(ge=512, le=2048, description=TILE_SIZE_DESCRIPTION)] = 1024,
    tile_overlap: Annotated[int, Form(ge=0, le=512, description=TILE_OVERLAP_DESCRIPTION)] = 128,
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
    job_id: Annotated[str, PathParameter(description="提交 GPU 工作時取得的 job_id；只能查詢同一客戶的工作。")],
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
    job_id: Annotated[
        str, PathParameter(description="已成功完成的 GPU job_id；工作未完成時回傳 409，結果遺失時回傳 410。")
    ],
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
