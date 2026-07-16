# API 文件（繁體中文）

[English](API.en.md)

## 基本資訊

- Base URL：`http://localhost:8000`
- Swagger：`/docs`
- ReDoc：`/redoc`
- OpenAPI：`/openapi.json`
- 認證：預設為 `X-API-Key: raiw_...`；可由部署者停用
- 支援圖片：PNG、JPEG、WebP、HEIC、HEIF、AVIF
- 預設限制：25 MB、50,000,000 pixels

`REQUIRE_API_KEY=true`（預設）時，除 `/healthz`、`/readyz`、`/api/v1/capabilities` 與文件外皆須認證。設為 `false` 時，未帶 Key 的請求以固定匿名客戶執行；若有帶 Key，仍必須有效並會歸入該客戶。每個回應包含 `X-Request-ID`。

本文件的命令列範例以 Linux Bash 為準。先在 shell 設定以下變數：

```bash
export BASE_URL='http://localhost:8000'
export RAIW_API_KEY='raiw_REPLACE_ME'
```

無 Key 模式可省略 `RAIW_API_KEY` 與範例中的 `-H "X-API-Key: ..."`。可由 `GET /api/v1/capabilities` 的 `api_key_required` 判斷目前模式。停用認證會取消客戶間的 API 授權隔離，不應直接暴露於公網。

## 端點

### `GET /healthz`、`GET /readyz`

分別回報程序存活與 archive/SQLite 可寫狀態。`readyz` 不要求 Redis；GPU queue 狀態由 capabilities 回報。

### `GET /api/v1/capabilities`

回傳 API／上游版本、格式、上限、可見後端與 Redis queue 狀態。`api_key_required` 表示目前部署是否強制要求 `X-API-Key`。

### `GET /api/v1/me`

回傳目前身分的 `customer_id`、名稱、external ID、key ID 與非秘密 prefix，不回傳明文或 HMAC。預設模式在 Swagger 請先按頁面右上角 `Authorize`，於 `X-API-Key` 欄位只輸入完整 `raiw_...` 金鑰，不要加入 `Bearer` 或 `X-API-Key:` 前綴。無 Key 模式可直接 Try it out；匿名回應的 `key_id` 與 `key_prefix` 為 `null`。

### 共通圖片上傳欄位

所有圖片處理端點均使用 `multipart/form-data`。`file` 是必填的圖片檔，支援 PNG、JPEG、WebP、HEIC、HEIF、AVIF；實際檔案與像素上限以 `/api/v1/capabilities` 為準。伺服器會以 magic bytes 與實際解碼結果驗證格式，不只相信副檔名。

### `POST /api/v1/identify`

只接受共通的 `file` 欄位。回傳 `request_id`、`archive_id` 與上游 provenance report；`report` 包含格式、尺寸、AI provenance、可見與不可見訊號。此端點只辨識，不產生處理後圖片。

```bash
curl -X POST "$BASE_URL/api/v1/identify" \
  -H "X-API-Key: $RAIW_API_KEY" -F "file=@image.png"
```

### `POST /api/v1/remove/visible`

| 欄位 | 預設／範圍 | 說明 |
|---|---|---|
| `file` | 必填 | 共通圖片上傳欄位。 |
| `sensitivity` | `auto`；`auto`, `strict`, `assume_ai` | `auto` 只有 metadata 或同產品標記提供佐證時放寬偵測門檻；`strict` 永不放寬、誤判最少；`assume_ai` 對所有已知標記放寬，召回率較高但可能誤判。 |
| `backend` | `cv2`；`cv2`, `migan`, `lama` | `cv2` 是快速的傳統 OpenCV 修補；MI-GAN 與 LaMa 是較耗資源的神經網路修補，通常適合較大或複雜區域。 |
| `strip_metadata` | `true`；boolean | 是否在輸出完成後移除可辨識的 AI provenance metadata，包含 C2PA 與 AI 相關 EXIF/XMP/IPTC。這不是清空所有一般 metadata。 |

成功回傳圖片以及 `X-Archive-ID`、`X-Removed-Marks`。沒有支援的可見標記時回傳 `422 no_visible_mark`。

### `POST /api/v1/remove/erase`

| 欄位 | 預設／範圍 | 說明 |
|---|---|---|
| `file` | 必填 | 共通圖片上傳欄位。 |
| `regions` | 必填；1–20 個框 | JSON 字串，格式為 `[[x,y,width,height]]` 或物件陣列。座標以原圖像素計算，`x/y` 是左上角，寬高必須大於 0，且框不可超出圖片。 |
| `backend` | `cv2`；`cv2`, `migan`, `lama` | 與可見標記移除相同的修補後端。 |
| `method` | `telea`；`telea`, `ns` | OpenCV 修補演算法；`telea` 通常較快且適合小區域，`ns` 為 Navier-Stokes。只有 `backend=cv2` 時生效。 |
| `dilate` | `3`；`0..100` | 修補前將遮罩向外擴張的像素數；`0` 表示不擴張，可用來涵蓋浮水印邊緣。 |
| `strip_metadata` | `true`；boolean | 與可見標記移除相同；只清除可辨識的 AI provenance metadata。 |

```bash
curl -X POST "$BASE_URL/api/v1/remove/erase" \
  -H "X-API-Key: $RAIW_API_KEY" -F "file=@image.png" \
  -F 'regions=[[10,20,100,50]]' --output erased.png
```

### `POST /api/v1/remove/metadata`

| 欄位 | 預設／範圍 | 說明 |
|---|---|---|
| `file` | 必填 | 共通圖片上傳欄位。 |
| `keep_standard` | `true`；boolean | `true` 會移除 AI/C2PA 資訊並盡量保留非 AI 的 Author、Title、Description、Copyright、Comment、Software、Source、Creation Time 等一般欄位；欄位值若可辨識出 AI 產生器仍會移除。`false` 不保留這些白名單文字欄位，採較積極清理。 |

`keep_standard=false` 不等於保證清空所有 metadata。上游依格式採用不同的無損策略：JPEG 可能保留已清除 AI 標記的正常 EXIF，HEIF／AVIF 會保留非 AI 的容器資料。

### `POST /api/v1/jobs/invisible`、`POST /api/v1/jobs/all`

GPU profile 未啟動時回傳 `503 gpu_worker_unavailable`。

| 欄位 | 預設／範圍 | 說明 |
|---|---|---|
| `file` | 必填 | 共通圖片上傳欄位。 |
| `pipeline` | `controlnet`；`controlnet`, `sdxl`, `qwen` | `controlnet` 以邊緣條件保留文字、臉部與結構；`sdxl` 較輕量但在平面圖像上可能保留訊號；`qwen` 最耗資源、通常需要雲端級 CUDA，但最重視文字與結構。 |
| `strength` | 省略；`0..1` | 擴散重建強度，越高通常改動越大；省略時使用偵測到的供應商自適應值。 |
| `steps` | `50`；`1..200` | 擴散去噪步數；增加會延長處理時間，不保證一定改善結果。 |
| `seed` | 省略；integer | 固定模型、參數及執行環境時可協助重現結果；省略則使用隨機結果。 |
| `force` | `false`；boolean | 未偵測到本地不可見訊號時仍強制重生成；可能改動乾淨圖片，也不代表保證移除訊號。 |
| `strip_metadata` | `true`；boolean；僅 `invisible` | 結果完成後移除可辨識的 AI provenance metadata，不是清除所有一般 metadata。 |
| `max_resolution` | `0`；`0..8192` | 擴散前的圖片長邊上限，單位像素；`0` 不限制。正值可省 GPU 記憶體，但縮小再放大可能損失細節。 |
| `min_resolution` | `1024`；`0..4096` | 擴散前的圖片長邊下限；小圖先放大，完成後還原原尺寸。`0` 停用；若 `max_resolution` 不為 0 且下限大於上限，則由上游忽略下限。 |
| `tile` | `false`；boolean | 長邊大於 `tile_size` 時才以重疊分塊處理，降低大圖峰值 GPU 記憶體。建議搭配 `max_resolution=0`。 |
| `tile_size` | `1024`；`512..2048` | 正方形分塊邊長，單位像素；較小可節省記憶體，但增加分塊數與時間。 |
| `tile_overlap` | `128`；`0..512` | 相鄰分塊的重疊像素，用於羽化接合、降低接縫；較大會增加重複運算。 |

`all` 另接受與可見移除相同的 `sensitivity` 與 `backend`，並固定在流程末端以 `keep_standard=true` 移除 AI metadata；因此沒有 `strip_metadata` 或 `keep_standard` 欄位。伺服器不接受客戶端提供 HF token、device 或任意 model ID。

```bash
JOB_ID="$(
  curl -fsS -X POST "$BASE_URL/api/v1/jobs/invisible" \
    -H "X-API-Key: $RAIW_API_KEY" \
    -F "file=@image.png" -F "force=true" \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["job_id"])'
)"
curl -H "X-API-Key: $RAIW_API_KEY" "$BASE_URL/api/v1/jobs/$JOB_ID"
curl -H "X-API-Key: $RAIW_API_KEY" \
  "$BASE_URL/api/v1/jobs/$JOB_ID/result" --output processed.png
```

Job 狀態為 `queued`、`running`、`succeeded` 或 `failed`。`progress` 是 0–100 的階段估算值，不是精確剩餘時間。`job_id` 由提交回應取得；只有建立工作的同一客戶能查詢與下載。結果只有在 `succeeded` 後可下載，否則 `/result` 回傳 `409 job_not_complete`。

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
| 401 | `missing_api_key`, `invalid_api_key` | 預設模式缺少金鑰，或任何模式提供了撤銷／無效金鑰 |
| 413 | `upload_too_large`, `image_too_large` | 檔案或像素超限 |
| 415 | `unsupported_media_type` | magic bytes／解碼格式不支援 |
| 422 | `validation_error`, `invalid_regions`, `no_visible_mark` | 參數或處理條件不成立 |
| 409 | `job_not_complete` | 結果尚未完成 |
| 410 | `result_missing` | DB 有紀錄但 archive 檔案遺失 |
| 503 | `gpu_worker_unavailable`, `queue_failed` | GPU queue 不可用 |
| 507 | `archive_unavailable` | Archive 無法寫入，演算法不會執行 |
