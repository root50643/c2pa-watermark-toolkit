from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from celery import Celery

from raiw_api.archive import ArchivedUpload, ArchiveManager
from raiw_api.config import get_settings
from raiw_api.db import Database
from raiw_api.errors import NoInvisibleSignalError
from raiw_api.services import remove_all_image, remove_invisible_image

settings = get_settings()
celery_app = Celery("raiw_api", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    result_expires=None,
)
logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="raiw_api.process_job")
def process_job(task: Any, job_id: str) -> dict[str, Any]:
    db = Database(settings.database_path)
    db.initialize()
    archive = ArchiveManager(settings, db)
    job = db.get_job(job_id)
    if not job:
        raise RuntimeError(f"Unknown job: {job_id}")
    row = db.get_archive(job["archive_id"])
    if not row:
        raise RuntimeError(f"Unknown archive: {job['archive_id']}")
    archived = ArchivedUpload(
        request_id=row["request_id"],
        directory=archive.absolute_path(row["input_path"]).parent,
        input_path=archive.absolute_path(row["input_path"]),
        extension=Path(row["input_path"]).suffix,
        mime=row["mime"],
        width=row["width"],
        height=row["height"],
    )
    output_work = archive.work_path(archived, "gpu-result")
    params = db.decode_params(row)
    started = time.perf_counter()
    progress_value = 10

    def progress(message: str) -> None:
        nonlocal progress_value
        progress_value = min(90, progress_value + 10)
        db.update_job(job_id, status="running", progress=progress_value, message=message)
        task.update_state(state="PROGRESS", meta={"progress": progress_value, "message": message})

    db.update_job(job_id, status="running", progress=5, message="Starting GPU worker")
    db.update_archive(row["request_id"], status="running")
    try:
        if job["task_name"] == "invisible":
            result = remove_invisible_image(
                archived.input_path,
                output_work,
                params=params,
                progress=progress,
            )
        elif job["task_name"] == "all":
            result = remove_all_image(
                archived.input_path,
                output_work,
                params=params,
                progress=progress,
            )
        else:
            raise RuntimeError(f"Unsupported task: {job['task_name']}")
        duration = (time.perf_counter() - started) * 1000
        payload = {"request_id": row["request_id"], "archive_id": row["request_id"], "result": result}
        result_path = archive.mark_success(
            row["request_id"], response=payload, output_source=output_work, duration_ms=duration
        )
        relative_result = result_path.relative_to(settings.archive_root).as_posix() if result_path else None
        db.update_job(
            job_id,
            status="succeeded",
            progress=100,
            message="Completed",
            result_path=relative_result,
            error_code=None,
            error_message=None,
        )
        return payload
    except NoInvisibleSignalError as exc:
        code = "no_invisible_signal"
        duration = (time.perf_counter() - started) * 1000
        archive.mark_failure(row["request_id"], code=code, message=str(exc), duration_ms=duration)
        db.update_job(job_id, status="failed", progress=100, message=str(exc), error_code=code, error_message=str(exc))
        raise
    except Exception as exc:
        code = "processing_failed"
        duration = (time.perf_counter() - started) * 1000
        logger.exception("GPU job %s failed", job_id)
        archive.mark_failure(
            row["request_id"],
            code=code,
            message="GPU processing failed",
            details=str(exc),
            duration_ms=duration,
        )
        db.update_job(
            job_id,
            status="failed",
            progress=100,
            message="GPU processing failed",
            error_code=code,
            error_message=str(exc)[:1000],
        )
        raise
    finally:
        output_work.unlink(missing_ok=True)
