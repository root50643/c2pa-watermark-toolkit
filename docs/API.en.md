# API Reference (English)

[繁體中文](API.zh-TW.md)

## Basics

- Base URL: `http://localhost:8000`
- Swagger: `/docs`; ReDoc: `/redoc`; OpenAPI: `/openapi.json`
- Authentication: `X-API-Key: raiw_...` by default; operators can disable enforcement
- Formats: PNG, JPEG, WebP, HEIC, HEIF, AVIF
- Defaults: 25 MB and 50,000,000 decoded pixels

With the default `REQUIRE_API_KEY=true`, authentication is required except for health, readiness, capabilities, and documentation. With `false`, a request without a key runs as a stable anonymous customer. A supplied key must still be valid and is attributed to its customer. Every response contains `X-Request-ID`.

Command-line examples in this document target Bash on Linux. Set these shell variables first:

```bash
export BASE_URL='http://localhost:8000'
export RAIW_API_KEY='raiw_REPLACE_ME'
```

In keyless mode, omit `RAIW_API_KEY` and the `-H "X-API-Key: ..."` arguments. Inspect `api_key_required` from `GET /api/v1/capabilities` to discover the runtime mode. Disabling authentication removes per-customer API authorization boundaries and should not be exposed directly to the public Internet.

## Endpoints

- `GET /healthz`: liveness.
- `GET /readyz`: archive and SQLite write readiness.
- `GET /api/v1/capabilities`: versions, formats, limits, backends, Redis availability, and `api_key_required`.
- `GET /api/v1/me`: current customer and key identity; anonymous mode returns `null` key fields.
- `POST /api/v1/identify`: multipart `file`; returns the provenance report as JSON.
- `POST /api/v1/remove/visible`: multipart `file`, `sensitivity=auto|strict|assume_ai`, `backend=cv2|migan|lama`, and `strip_metadata`.
- `POST /api/v1/remove/erase`: multipart `file`, JSON string `regions`, backend, method, dilation, and metadata option.
- `POST /api/v1/remove/metadata`: multipart `file` and `keep_standard`.
- `POST /api/v1/jobs/invisible`: asynchronous GPU regeneration.
- `POST /api/v1/jobs/all`: visible, invisible, and metadata pipeline.
- `GET /api/v1/jobs/{id}` and `/result`: poll and download; only the owning customer has access.

Image responses include `X-Archive-ID`. Visible removal also returns `X-Removed-Marks`. A no-mark result is `422 no_visible_mark`.

In the default mode, select Swagger's top-right **Authorize** button and enter only the complete `raiw_...` value under `X-API-Key`. Do not add `Bearer` or the `X-API-Key:` header name. In keyless mode, protected operations are marked as optionally authenticated and **Try it out** works without Authorize.

### Shared image upload field

Every image-processing endpoint uses `multipart/form-data`. The required `file` field accepts PNG, JPEG, WebP, HEIC, HEIF, and AVIF. Use `/api/v1/capabilities` for the configured byte and decoded-pixel limits. Validation uses magic bytes and actual decoding rather than trusting the extension.

### Visible removal fields

| Field | Default / values | Meaning |
|---|---|---|
| `file` | required | Shared image upload field. |
| `sensitivity` | `auto`; `auto`, `strict`, `assume_ai` | `auto` relaxes detection only when metadata or a sibling mark corroborates it; `strict` never relaxes and minimizes false positives; `assume_ai` relaxes every known detector for higher recall with more false-positive risk. |
| `backend` | `cv2`; `cv2`, `migan`, `lama` | `cv2` is fast classical OpenCV inpainting. MI-GAN and LaMa are more resource-intensive neural inpainting backends, generally suited to larger or more complex regions. |
| `strip_metadata` | `true`; boolean | Remove recognized AI provenance metadata, including C2PA and AI-related EXIF/XMP/IPTC, after producing the result. It is not a full purge of ordinary metadata. |

### Region syntax

| Field | Default / values | Meaning |
|---|---|---|
| `file` | required | Shared image upload field. |
| `regions` | required; 1–20 boxes | A JSON string containing `[[x,y,width,height]]` or objects with `x`, `y`, `width`, and `height`. Coordinates use original-image pixels; x/y is the top-left corner, dimensions must be positive, and every box must remain inside the image. |
| `backend` | `cv2`; `cv2`, `migan`, `lama` | Same inpainting backend as visible removal. |
| `method` | `telea`; `telea`, `ns` | OpenCV inpainting algorithm. Telea is usually faster for small regions; `ns` is Navier–Stokes. Used only when `backend=cv2`. |
| `dilate` | `3`; `0..100` | Pixels by which each mask expands before inpainting; 0 disables expansion. Use it to cover watermark edges. |
| `strip_metadata` | `true`; boolean | Same AI-provenance cleanup as visible removal. |

### Metadata removal fields

| Field | Default / values | Meaning |
|---|---|---|
| `file` | required | Shared image upload field. |
| `keep_standard` | `true`; boolean | `true` removes AI/C2PA information while retaining ordinary non-AI fields such as Author, Title, Description, Copyright, Comment, Software, Source, and Creation Time where possible. A value that identifies an AI generator is still removed. `false` does not retain those allowlisted text fields and selects the more aggressive cleanup path. |

`keep_standard=false` is not a guarantee that every metadata item is blank. The upstream uses format-specific lossless strategies: JPEG may retain scrubbed non-AI EXIF, while HEIF/AVIF retains non-AI container data.

### GPU fields

| Field | Default / values | Meaning |
|---|---|---|
| `file` | required | Shared image upload field. |
| `pipeline` | `controlnet`; `controlnet`, `sdxl`, `qwen` | ControlNet uses edge conditioning to preserve text, faces, and structure. SDXL is lighter but can leave signals in flat graphics. Qwen is the most resource-intensive and generally needs cloud-class CUDA, but prioritizes text and structure preservation. |
| `strength` | omitted; `0..1` | Diffusion reconstruction strength; larger values generally alter more pixels. Omit it to use the detected vendor-adaptive default. |
| `steps` | `50`; `1..200` | Denoising steps. More steps take longer and do not guarantee a better result. |
| `seed` | omitted; integer | Helps reproduce a result when the model, parameters, and environment remain fixed. Omit it for a random result. |
| `force` | `false`; boolean | Run regeneration even when no local invisible signal is detected. It can alter a clean image and does not guarantee signal removal. |
| `strip_metadata` | `true`; boolean; `invisible` only | Remove recognized AI provenance metadata after generation; it is not a full purge of ordinary metadata. |
| `max_resolution` | `0`; `0..8192` | Long-side cap in pixels before diffusion. 0 disables the cap. A positive cap saves GPU memory but the downscale/upscale round-trip can lose detail. |
| `min_resolution` | `1024`; `0..4096` | Long-side floor before diffusion; small inputs are enlarged and the output is restored to the original size. 0 disables it. When `max_resolution` is nonzero and the floor exceeds that cap, the upstream ignores the floor. |
| `tile` | `false`; boolean | Use overlapping tiles only when the long side exceeds `tile_size`, reducing peak GPU memory on large images. Pair with `max_resolution=0` to retain native resolution. |
| `tile_size` | `1024`; `512..2048` | Square tile edge in pixels. Smaller values save memory but increase tile count and processing time. |
| `tile_overlap` | `128`; `0..512` | Overlap in pixels for feather blending and seam reduction. Larger values repeat more work. |

`jobs/all` additionally accepts the visible-removal `sensitivity` and `backend` fields. It always removes AI metadata at the end with `keep_standard=true`, so it exposes neither `strip_metadata` nor `keep_standard`. The server alone controls device, HF token, and model ID.

Job status is `queued`, `running`, `succeeded`, or `failed`. `progress` is a 0–100 stage estimate, not an exact time remaining. Use the returned `job_id` to poll. The result is downloadable only after `succeeded`; otherwise `/result` returns `409 job_not_complete`.

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

- `401`: `missing_api_key` in the default mode, or `invalid_api_key` when an invalid/revoked key is supplied in either mode
- `413`: `upload_too_large`, `image_too_large`
- `415`: `unsupported_media_type`
- `422`: `validation_error`, `invalid_regions`, `no_visible_mark`
- `409`: `job_not_complete`; `410`: `result_missing`
- `503`: `gpu_worker_unavailable`, `queue_failed`
- `507`: `archive_unavailable`; processing does not run when archive storage is unavailable
