from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from raiw_api.errors import APIError, NoInvisibleSignalError, NoVisibleMarkError


def identify_image(path: Path) -> dict[str, Any]:
    from remove_ai_watermarks.identify import identify

    return asdict(identify(path, check_visible=True, check_invisible=True))


def remove_visible_image(
    source: Path,
    output: Path,
    *,
    sensitivity: str,
    backend: str,
    strip_metadata: bool,
) -> list[str]:
    from remove_ai_watermarks.api import remove_visible

    _, removed = remove_visible(
        source,
        output,
        sensitivity=sensitivity,  # type: ignore[arg-type]
        backend=backend,  # type: ignore[arg-type]
        strip_metadata=strip_metadata,
        write_noop=False,
    )
    if not removed:
        output.unlink(missing_ok=True)
        raise NoVisibleMarkError("No supported visible AI watermark was detected")
    return removed


def parse_regions(value: str, *, width: int, height: int) -> list[tuple[int, int, int, int]]:
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise APIError(422, "invalid_regions", "regions must be a JSON array", str(exc)) from exc
    if not isinstance(raw, list) or not raw or len(raw) > 20:
        raise APIError(422, "invalid_regions", "regions must contain between 1 and 20 boxes")
    boxes: list[tuple[int, int, int, int]] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            values = [item.get(key) for key in ("x", "y", "width", "height")]
        elif isinstance(item, list) and len(item) == 4:
            values = item
        else:
            raise APIError(422, "invalid_regions", f"Region {index} must be [x,y,width,height] or an object")
        validated: list[int] = []
        for coordinate in values:
            if isinstance(coordinate, bool) or not isinstance(coordinate, int):
                raise APIError(422, "invalid_regions", f"Region {index} coordinates must be integers")
            validated.append(coordinate)
        x, y, w, h = validated
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise APIError(422, "invalid_regions", f"Region {index} is outside the image bounds")
        boxes.append((x, y, w, h))
    return boxes


def erase_image(
    source: Path,
    output: Path,
    *,
    boxes: list[tuple[int, int, int, int]],
    backend: str,
    method: str,
    dilate: int,
    strip_metadata: bool,
) -> None:
    from remove_ai_watermarks import image_io, metadata, region_eraser

    image, alpha = image_io.read_bgr_and_alpha(source)
    if image is None:
        raise ValueError("Could not decode archived input")
    result = region_eraser.erase(
        image,
        boxes=boxes,
        backend=backend,  # type: ignore[arg-type]
        dilate=dilate,
        cv2_method=method,  # type: ignore[arg-type]
    )
    image_io.write_bgr_with_alpha(output, result, alpha)
    if strip_metadata:
        metadata.remove_ai_metadata(output, output)


def remove_metadata_image(source: Path, output: Path, *, keep_standard: bool) -> None:
    from remove_ai_watermarks.metadata import remove_ai_metadata

    remove_ai_metadata(source, output, keep_standard=keep_standard)


_ENGINE_CACHE: dict[tuple[str | None, str, str, float], Any] = {}


def _engine(params: dict[str, Any], progress: Callable[[str], None]) -> Any:
    from remove_ai_watermarks.invisible_engine import InvisibleEngine

    from raiw_api.config import get_settings

    settings = get_settings()
    pipeline = str(params.get("pipeline", "controlnet"))
    controlnet_scale = float(params.get("controlnet_scale", 1.0))
    cache_key = (settings.gpu_model_id, settings.gpu_device, pipeline, controlnet_scale)
    if cache_key not in _ENGINE_CACHE:
        _ENGINE_CACHE[cache_key] = InvisibleEngine(
            model_id=settings.gpu_model_id,
            device=settings.gpu_device,
            pipeline=pipeline,
            hf_token=settings.hf_token,
            progress_callback=progress,
            controlnet_conditioning_scale=controlnet_scale,
        )
    else:
        _ENGINE_CACHE[cache_key]._progress_callback = progress
        _ENGINE_CACHE[cache_key]._remover._progress_callback = progress
    return _ENGINE_CACHE[cache_key]


def remove_invisible_image(
    source: Path,
    output: Path,
    *,
    params: dict[str, Any],
    progress: Callable[[str], None],
    check_signal: bool = True,
) -> dict[str, Any]:
    from remove_ai_watermarks import image_io, metadata
    from remove_ai_watermarks.identify import has_invisible_target
    from remove_ai_watermarks.noai.watermark_profiles import vendor_for_strength

    force = bool(params.get("force", False))
    if check_signal and not force and not has_invisible_target(source):
        raise NoInvisibleSignalError("No locally detectable invisible watermark signal; use force=true to override")
    engine = _engine(params, progress)
    engine.remove_watermark(
        image_path=source,
        output_path=output,
        strength=params.get("strength"),
        num_inference_steps=int(params.get("steps", 50)),
        guidance_scale=params.get("guidance_scale"),
        seed=params.get("seed"),
        humanize=float(params.get("humanize", 0.0)),
        max_resolution=int(params.get("max_resolution", 0)),
        min_resolution=int(params.get("min_resolution", 1024)),
        vendor=vendor_for_strength(source),
        unsharp=float(params.get("unsharp", 0.0)),
        adaptive_polish=bool(params.get("adaptive_polish", True)),
        upscaler=str(params.get("upscaler", "lanczos")),
        tile=bool(params.get("tile", False)),
        tile_size=int(params.get("tile_size", 1024)),
        tile_overlap=int(params.get("tile_overlap", 128)),
    )
    _, original_alpha = image_io.read_bgr_and_alpha(source)
    if original_alpha is not None:
        result, _ = image_io.read_bgr_and_alpha(output)
        if result is not None:
            image_io.write_bgr_with_alpha(output, result, original_alpha)
    if bool(params.get("strip_metadata", True)):
        metadata.remove_ai_metadata(output, output)
    return {"invisible_removed": True, "pipeline": params.get("pipeline", "controlnet")}


def remove_all_image(
    source: Path,
    output: Path,
    *,
    params: dict[str, Any],
    progress: Callable[[str], None],
) -> dict[str, Any]:
    from remove_ai_watermarks.api import remove_visible
    from remove_ai_watermarks.identify import has_invisible_target

    visible_path = output.with_name(f".all-visible{output.suffix}")
    invisible_path = output.with_name(f".all-invisible{output.suffix}")
    removed: list[str] = []
    invisible_removed = False
    try:
        progress("Removing visible watermark")
        _, removed = remove_visible(
            source,
            visible_path,
            sensitivity=params.get("sensitivity", "auto"),
            backend=params.get("backend", "cv2"),
            strip_metadata=False,
            write_noop=True,
        )
        should_run = bool(params.get("force", False)) or has_invisible_target(source)
        current = visible_path
        if should_run:
            progress("Removing invisible watermark")
            remove_invisible_image(visible_path, invisible_path, params=params, progress=progress, check_signal=False)
            current = invisible_path
            invisible_removed = True
        progress("Removing AI metadata")
        remove_metadata_image(current, output, keep_standard=True)
        return {
            "visible_removed": removed,
            "invisible_removed": invisible_removed,
            "metadata_removed": True,
        }
    finally:
        visible_path.unlink(missing_ok=True)
        invisible_path.unlink(missing_ok=True)


def copy_image(source: Path, output: Path) -> None:
    shutil.copyfile(source, output)
