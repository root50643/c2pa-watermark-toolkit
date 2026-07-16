# API Reference (English)

[繁體中文](API.zh-TW.md)

## Basics

- Base URL: `http://localhost:8000`
- Swagger: `/docs`; ReDoc: `/redoc`; OpenAPI: `/openapi.json`
- Authentication: `X-API-Key: raiw_...`
- Formats: PNG, JPEG, WebP, HEIC, HEIF, AVIF
- Defaults: 25 MB and 50,000,000 decoded pixels

Authentication is required except for health, readiness, capabilities, and documentation. Every response contains `X-Request-ID`. Once an image passes basic validation, its original bytes and associated audit metadata are retained permanently.

## Endpoints

- `GET /healthz`: liveness.
- `GET /readyz`: archive and SQLite write readiness.
- `GET /api/v1/capabilities`: versions, formats, limits, backends, and Redis availability.
- `GET /api/v1/me`: authenticated customer and key identity.
- `POST /api/v1/identify`: multipart `file`; returns the provenance report as JSON.
- `POST /api/v1/remove/visible`: multipart `file`, `sensitivity=auto|strict|assume_ai`, `backend=cv2|migan|lama`, and `strip_metadata`.
- `POST /api/v1/remove/erase`: multipart `file`, JSON string `regions`, backend, method, dilation, and metadata option.
- `POST /api/v1/remove/metadata`: multipart `file` and `keep_standard`.
- `POST /api/v1/jobs/invisible`: asynchronous GPU regeneration.
- `POST /api/v1/jobs/all`: visible, invisible, and metadata pipeline.
- `GET /api/v1/jobs/{id}` and `/result`: poll and download; only the owning customer has access.

Image responses include `X-Archive-ID`. Visible removal also returns `X-Removed-Marks`. A no-mark result is `422 no_visible_mark`, while the original remains archived.

### Region syntax

`regions` accepts up to 20 boxes as `[[x,y,width,height]]` or objects containing `x`, `y`, `width`, and `height`. Coordinates must remain inside the image.

### GPU fields

`pipeline` defaults to `controlnet` and accepts `sdxl` or `qwen`; `strength` is 0..1 or vendor-adaptive; `steps` is 1..200; `force` overrides the no-signal guard; tiling includes `tile`, `tile_size`, and `tile_overlap`. The server alone controls device, HF token, and model ID.

```bash
curl -X POST "$BASE_URL/api/v1/identify" \
  -H "X-API-Key: $RAIW_API_KEY" -F "file=@image.png"

curl -X POST "$BASE_URL/api/v1/remove/erase" \
  -H "X-API-Key: $RAIW_API_KEY" -F "file=@image.png" \
  -F 'regions=[[10,20,100,50]]' --output erased.png
```

```python
import requests

with open("image.png", "rb") as image:
    response = requests.post(
        "http://localhost:8000/api/v1/remove/metadata",
        headers={"X-API-Key": "raiw_REPLACE_ME"},
        files={"file": ("image.png", image, "image/png")},
        data={"keep_standard": "true"},
        timeout=120,
    )
response.raise_for_status()
open("processed.png", "wb").write(response.content)
```

## Errors

Errors use `{"error":{"code":"...","message":"...","details":null,"request_id":"..."}}`.

- `401`: `missing_api_key`, `invalid_api_key`
- `413`: `upload_too_large`, `image_too_large`
- `415`: `unsupported_media_type`
- `422`: `validation_error`, `invalid_regions`, `no_visible_mark`
- `409`: `job_not_complete`; `410`: `result_missing`
- `503`: `gpu_worker_unavailable`, `queue_failed`
- `507`: `archive_unavailable`; processing does not run when persistence fails

## Retention and audit notice

Every accepted request stores a separate original and, on success, a processed image. Data does not expire or deduplicate. Every `/api/v1/*` access, including authentication and validation failures, permanently records customer/key IDs, raw client and peer IP, UTC timestamps, User-Agent, route, status, and latency. Operators must provide appropriate privacy notice, access control, backups, capacity monitoring, and deletion procedures.
