# C2PA Watermark Toolkit

[English](README.en.md) | 繁體中文

這是一個以 FastAPI 包裝 [wiltodelta/remove-ai-watermarks](https://github.com/wiltodelta/remove-ai-watermarks) 0.15.3 的自架 REST API。它提供 Swagger、客戶專屬 API Key、永久保存每次上傳與處理結果，以及包含來源 IP 與時間的存取稽核。

> 僅能處理您有權處理的內容，並請遵守所在地對 AI 標示、內容憑證、個資及稽核資料的法律。此專案不以移除付費圖庫或他人著作權浮水印為目的。

## 功能

- 可見 AI 浮水印移除、指定區域修補、AI metadata 移除與來源辨識。
- 選用 NVIDIA GPU worker 執行 SynthID 等不可見浮水印重生成流程。
- 每位客戶可擁有多把可撤銷 API Key；資料庫不保存明文金鑰。
- 每個請求永久保存獨立原圖、結果、response、manifest 與 SHA-256，不做去重。
- 永久稽核 customer ID、key ID、client/peer IP、UTC 時間、User-Agent、路由、狀態與耗時。
- Swagger `/docs`、ReDoc `/redoc`、[中文 API 文件](docs/API.zh-TW.md)、[英文 API 文件](docs/API.en.md) 與 Postman collection。
- React 雙語圖片工作台，涵蓋識別、可見移除、畫框修補、metadata 與 GPU 工作追蹤。

## 快速啟動（CPU）

```powershell
Copy-Item .env.example .env
# 先把 .env 的 API_KEY_PEPPER 換成足夠長的隨機值
docker compose up -d --build

# 建立客戶並核發第一把金鑰；明文只會顯示這一次
docker compose exec api raiw-api-admin customer create `
  --name "Local developer" --external-id "local-001" --issue-key
```

開啟 <http://localhost:8080>，輸入產生的 `raiw_...` 金鑰即可使用圖片工作台。前端只把金鑰保存在目前瀏覽器工作階段，且使用同源代理呼叫 API。詳細操作見[前端使用文件](docs/FRONTEND.zh-TW.md)。

Swagger 可由 <http://localhost:8080/docs> 或 <http://localhost:8000/docs> 開啟；健康檢查為 <http://localhost:8080/healthz>。

```bash
curl -X POST http://localhost:8000/api/v1/identify \
  -H "X-API-Key: $RAIW_API_KEY" \
  -F "file=@image.png"

curl -X POST http://localhost:8000/api/v1/remove/visible \
  -H "X-API-Key: $RAIW_API_KEY" \
  -F "file=@image.png" -F "backend=cv2" \
  --output processed.png
```

## GPU profile

主機必須先安裝 NVIDIA driver、Docker Desktop／Engine 與 NVIDIA Container Toolkit。首次執行會下載數 GB 模型。

```bash
docker compose --profile gpu up -d --build
```

不可見浮水印與完整流程使用非同步 job API；依序呼叫 `POST /api/v1/jobs/invisible` 或 `/all`、輪詢 `GET /api/v1/jobs/{id}`，最後下載 `/result`。詳細參數見 [API 文件](docs/API.zh-TW.md)。

## 永久保存與稽核

預設將主機 `./archive-data` 掛載為容器 `/data/archive`：

```text
archive-data/YYYY/MM/DD/{request_id}/
  original.{ext}
  processed.{ext}
  response.json
  manifest.json
```

SQLite 位於 `archive-data/raiw-api.sqlite3`。即使圖片相同，每次請求仍各存一份。資料不會自動清除，因此部署者必須負責容量監控、備份、存取權限、隱私告知與刪除請求。`archive-data/` 已被 Git 忽略，請勿把客戶圖片或資料庫提交到 GitHub。

```bash
# 客戶與金鑰
docker compose exec api raiw-api-admin customer list
docker compose exec api raiw-api-admin key list --customer-id CUSTOMER_ID
docker compose exec api raiw-api-admin key revoke KEY_ID

# 匯出與驗證
docker compose exec api raiw-api-admin archive export --format csv --output /data/archive/archive.csv
docker compose exec api raiw-api-admin audit export --format json --output /data/archive/audit.json
docker compose exec api raiw-api-admin archive verify

# 明確永久刪除單筆資料
docker compose exec api raiw-api-admin archive delete REQUEST_ID --yes
```

## 設定

| 環境變數 | 預設值 | 說明 |
|---|---:|---|
| `API_KEY_PEPPER` | 僅開發用字串 | 正式環境必須改成長隨機秘密；更換後舊 key 全部失效 |
| `ARCHIVE_HOST_PATH` | `./archive-data` | Compose 掛載的主機資料夾 |
| `ARCHIVE_ROOT` | `/data/archive` | 容器內 archive 根目錄 |
| `MAX_UPLOAD_MB` | `25` | 單檔上限 |
| `MAX_IMAGE_PIXELS` | `50000000` | 解碼後像素上限 |
| `TRUSTED_PROXY_CIDRS` | `172.30.10.10/32` | 僅信任內建 Nginx proxy；自訂網路時需同步調整 |
| `FRONTEND_PORT` | `8080` | 前端與同源 API proxy 的主機連接埠 |
| `PROXY_SUBNET` | `172.30.10.0/24` | Compose 專用 proxy network；衝突時可調整 |
| `FRONTEND_PROXY_IP` | `172.30.10.10` | Nginx 在 proxy network 的固定位置 |
| `API_PROXY_IP` | `172.30.10.20` | API 在 proxy network 的固定位置 |
| `REDIS_URL` | `redis://redis:6379/0` | GPU queue broker/backend |
| `HF_TOKEN` | 空白 | GPU worker 的 Hugging Face token，不接受客戶端傳入 |
| `GPU_DEVICE` | `cuda` | GPU worker 裝置 |
| `GPU_MODEL_ID` | 上游預設 | 由伺服器控制的模型 ID |

若未明確信任反向代理，API 只記錄 TCP peer IP，避免客戶偽造 `X-Forwarded-For`。

## 開發與測試

```bash
python -m pip install uv==0.8.2
uv sync --frozen --extra dev
uv run ruff check .
uv run pyright
uv run pytest --cov=raiw_api
uv run python scripts/export_openapi.py --check
docker build -t remove-ai-watermarks-api:local .

cd frontend
pnpm install --frozen-lockfile
pnpm generate:api
pnpm lint
pnpm test
pnpm build
```

## 上游與授權

本專案是獨立 API 包裝器，不是上游官方服務。API 程式採 Apache-2.0；影像演算法來自固定版本的 `remove-ai-watermarks`，詳細 attribution 見 [NOTICE](NOTICE)。
