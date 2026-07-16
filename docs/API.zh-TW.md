# API 文件（繁體中文）

[English](API.en.md)

## 基本資訊

- Base URL：`http://localhost:8000`
- Swagger：`/docs`
- ReDoc：`/redoc`
- OpenAPI：`/openapi.json`
- 認證：`X-API-Key: raiw_...`
- 支援圖片：PNG、JPEG、WebP、HEIC、HEIF、AVIF
- 預設限制：25 MB、50,000,000 pixels

除 `/healthz`、`/readyz`、`/api/v1/capabilities` 與文件外皆須認證。每個回應包含 `X-Request-ID`。通過基本圖片驗證後，原圖與客戶稽核會永久保存。

## 端點

### `GET /healthz`、`GET /readyz`

分別回報程序存活與 archive/SQLite 可寫狀態。`readyz` 不要求 Redis；GPU queue 狀態由 capabilities 回報。

### `GET /api/v1/capabilities`

回傳 API／上游版本、格式、上限、可見後端與 Redis queue 狀態。

### `GET /api/v1/me`

回傳目前 key 的 `customer_id`、名稱、external ID、key ID 與 prefix，不回傳明文或 HMAC。

### `POST /api/v1/identify`

Multipart 欄位：`file`。回傳 `request_id`、`archive_id` 與上游 provenance report。

```bash
curl -X POST "$BASE_URL/api/v1/identify" \
  -H "X-API-Key: $RAIW_API_KEY" -F "file=@image.png"
```

### `POST /api/v1/remove/visible`

| 欄位 | 預設 | 值 |
|---|---|---|
| `file` | 必填 | 圖片 |
| `sensitivity` | `auto` | `auto`, `strict`, `assume_ai` |
| `backend` | `cv2` | `cv2`, `migan`, `lama` |
| `strip_metadata` | `true` | boolean |

成功回傳圖片以及 `X-Archive-ID`、`X-Removed-Marks`。沒有支援的可見標記時回傳 `422 no_visible_mark`，原圖仍會保存。

### `POST /api/v1/remove/erase`

`regions` 是 JSON 字串，最多 20 個框；可使用 `[[x,y,width,height]]` 或物件陣列。其他欄位：`backend=cv2|migan|lama`、`method=telea|ns`、`dilate=0..100`、`strip_metadata=true|false`。

```bash
curl -X POST "$BASE_URL/api/v1/remove/erase" \
  -H "X-API-Key: $RAIW_API_KEY" -F "file=@image.png" \
  -F 'regions=[[10,20,100,50]]' --output erased.png
```

### `POST /api/v1/remove/metadata`

Multipart 欄位：`file`、`keep_standard`（預設 true）。成功時回傳處理後圖片。

### `POST /api/v1/jobs/invisible`、`POST /api/v1/jobs/all`

GPU profile 未啟動時回傳 `503 gpu_worker_unavailable`，但已驗證的上傳仍會留存。

| 欄位 | 預設 | 限制 |
|---|---:|---|
| `pipeline` | `controlnet` | `controlnet`, `sdxl`, `qwen` |
| `strength` | vendor adaptive | `0..1` |
| `steps` | `50` | `1..200` |
| `seed` | null | integer |
| `force` | false | 無本地 signal 時是否強制重生成 |
| `max_resolution` | `0` | `0..8192` |
| `min_resolution` | `1024` | `0..4096` |
| `tile` | false | boolean |
| `tile_size` | `1024` | `512..2048` |
| `tile_overlap` | `128` | `0..512` |

`all` 另接受 `sensitivity` 與 `backend`。伺服器不接受客戶端提供 HF token、device 或任意 model ID。

```bash
JOB=$(curl -s -X POST "$BASE_URL/api/v1/jobs/invisible" \
  -H "X-API-Key: $RAIW_API_KEY" -F "file=@image.png" -F "force=true")
curl -H "X-API-Key: $RAIW_API_KEY" "$BASE_URL/api/v1/jobs/JOB_ID"
curl -H "X-API-Key: $RAIW_API_KEY" \
  "$BASE_URL/api/v1/jobs/JOB_ID/result" --output processed.png
```

Job 狀態為 `queued`、`running`、`succeeded` 或 `failed`。只有建立工作的同一客戶能查詢與下載。

## Python 範例

```python
import requests

base = "http://localhost:8000"
headers = {"X-API-Key": "raiw_REPLACE_ME"}
with open("image.png", "rb") as image:
    response = requests.post(
        f"{base}/api/v1/remove/metadata",
        headers=headers,
        files={"file": ("image.png", image, "image/png")},
        data={"keep_standard": "true"},
        timeout=120,
    )
response.raise_for_status()
open("processed.png", "wb").write(response.content)
print(response.headers["X-Request-ID"], response.headers["X-Archive-ID"])
```

## 錯誤碼

錯誤格式：`{"error":{"code":"...","message":"...","details":null,"request_id":"..."}}`。

| HTTP | code | 說明 |
|---:|---|---|
| 401 | `missing_api_key`, `invalid_api_key` | 缺少、撤銷或無效金鑰 |
| 413 | `upload_too_large`, `image_too_large` | 檔案或像素超限 |
| 415 | `unsupported_media_type` | magic bytes／解碼格式不支援 |
| 422 | `validation_error`, `invalid_regions`, `no_visible_mark` | 參數或處理條件不成立 |
| 409 | `job_not_complete` | 結果尚未完成 |
| 410 | `result_missing` | DB 有紀錄但 archive 檔案遺失 |
| 503 | `gpu_worker_unavailable`, `queue_failed` | GPU queue 不可用 |
| 507 | `archive_unavailable` | 永久保存失敗，演算法不會執行 |

## 留存與稽核告知

通過基本圖片驗證後，系統永久保存原圖；成功時另保存處理後檔案。每次請求各存一份，不去重。所有 `/api/v1/*` 存取（包含認證與驗證失敗）永久記錄客戶 ID、key ID、原始 client/peer IP、UTC 時間、User-Agent、route、狀態與耗時。部署者必須在客戶使用前完成隱私告知並建立適當的存取、備份與刪除程序。
