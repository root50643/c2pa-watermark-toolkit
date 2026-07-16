# C2PA Watermark Toolkit

[English](README.en.md) | 繁體中文

這是一個以 FastAPI 包裝 [wiltodelta/remove-ai-watermarks](https://github.com/wiltodelta/remove-ai-watermarks) 0.15.3 的自架 REST API。它提供 Swagger，以及預設啟用且可設定停用的 API Key 驗證。

> 僅能處理您有權處理的內容，並請遵守所在地對 AI 標示、內容憑證及個資的法律。此專案不以移除付費圖庫或他人著作權浮水印為目的。

## 功能

- 可見 AI 浮水印移除、指定區域修補、AI metadata 移除與來源辨識。
- 選用 NVIDIA GPU worker 執行 SynthID 等不可見浮水印重生成流程。
- 預設強制 API Key；每位客戶可有多把可撤銷金鑰，亦可明確切換為無 Key 公開模式。
- Swagger `/docs`、ReDoc `/redoc`、[中文 API 文件](docs/API.zh-TW.md)、[英文 API 文件](docs/API.en.md) 與 Postman collection。
- React 雙語圖片工作台，涵蓋識別、可見移除、畫框修補、metadata 與 GPU 工作追蹤。

## 快速啟動（Linux／CPU）

以下指令以 Linux 的 Bash 為準。主機需先安裝 Git、OpenSSL、Docker Engine 與 Docker Compose v2 plugin，並確認目前使用者可以執行 `docker`。

```bash
install -m 600 .env.example .env
pepper="$(openssl rand -hex 32)"
sed -i "s|^API_KEY_PEPPER=.*|API_KEY_PEPPER=${pepper}|" .env
unset pepper

docker compose up -d --build

# 建立客戶並核發第一把金鑰；明文只會顯示這一次
docker compose exec api raiw-api-admin customer create \
  --name "Local developer" --external-id "local-001" --issue-key
```

開啟 <http://localhost:8080>，輸入產生的 `raiw_...` 金鑰即可使用圖片工作台。前端只把金鑰保存在目前瀏覽器工作階段，且使用同源代理呼叫 API。詳細操作見[前端使用文件](docs/FRONTEND.zh-TW.md)。

Swagger 可由 <http://localhost:8080/docs> 或 <http://localhost:8000/docs> 開啟；健康檢查為 <http://localhost:8080/healthz>。

```bash
export RAIW_API_KEY='raiw_REPLACE_ME'

curl -X POST http://localhost:8000/api/v1/identify \
  -H "X-API-Key: $RAIW_API_KEY" \
  -F "file=@image.png"

curl -X POST http://localhost:8000/api/v1/remove/visible \
  -H "X-API-Key: $RAIW_API_KEY" \
  -F "file=@image.png" -F "backend=cv2" \
  --output processed.png
```

### 不要求 API Key（選用）

若服務已由其他身分驗證、私有網路或閘道保護，可在 `.env` 設定以下值後重建／重啟：

```bash
sed -i 's/^REQUIRE_API_KEY=.*/REQUIRE_API_KEY=false/' .env
docker compose up -d --build
```

此模式下前端會自動開啟工作台，API 呼叫可省略 `X-API-Key`，`GET /api/v1/me` 的 `key_id` 與 `key_prefix` 為 `null`。未帶 Key 的請求會歸入固定匿名客戶；若請求有帶 Key，仍會驗證並歸戶，無效 Key 仍回傳 401。此設定會取消客戶間的 API 授權隔離，不建議直接暴露於公網；至少應搭配防火牆、反向代理驗證與速率限制。改回 `REQUIRE_API_KEY=true` 即恢復預設行為。

### Metadata 的 `keep_standard`

`POST /api/v1/remove/metadata` 的 `keep_standard` 決定清除 AI/C2PA 資訊時，是否保留非 AI 的一般 metadata：

| 值 | 行為 |
|---|---|
| `true`（預設） | 移除可辨識的 AI/C2PA 資訊，並盡量保留 Author、Title、Description、Copyright、Comment、Software、Source、Creation Time 等一般欄位。若欄位值本身可辨識出 AI 產生器，仍會移除。 |
| `false` | 不保留上述白名單文字欄位，採較積極的清理。 |

上游會依圖片格式使用不同的無損處理策略，因此 `false` 不代表保證清空所有 metadata；JPEG 可能保留已清除 AI 標記的正常 EXIF，HEIF／AVIF 也會保留非 AI 的容器資料。完整欄位說明見 [API 文件](docs/API.zh-TW.md)。

## GPU profile

Linux 主機必須先安裝 NVIDIA driver、Docker Engine 與 NVIDIA Container Toolkit。首次執行會下載數 GB 模型。

```bash
docker compose --profile gpu up -d --build
```

不可見浮水印與完整流程使用非同步 job API；依序呼叫 `POST /api/v1/jobs/invisible` 或 `/all`、輪詢 `GET /api/v1/jobs/{id}`，最後下載 `/result`。詳細參數見 [API 文件](docs/API.zh-TW.md)。

## 設定

| 環境變數 | 預設值 | 說明 |
|---|---:|---|
| `API_KEY_PEPPER` | 僅開發用字串 | 正式環境必須改成長隨機秘密；更換後舊 key 全部失效 |
| `REQUIRE_API_KEY` | `true` | 是否強制要求 `X-API-Key`；`false` 時未帶 Key 的請求歸入固定匿名客戶 |
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

以下流程以 Linux Bash、Python 3 與 Node.js 22 為準：

```bash
python3 -m venv .bootstrap-venv
. .bootstrap-venv/bin/activate
python -m pip install uv==0.8.2
uv sync --frozen --extra dev
uv run ruff check .
uv run pyright
uv run pytest --cov=raiw_api
uv run python scripts/export_openapi.py --check
docker build -t remove-ai-watermarks-api:local .

cd frontend
corepack enable
pnpm install --frozen-lockfile
pnpm generate:api
pnpm lint
pnpm test
pnpm build
```

## 上游與授權

本專案是獨立 API 包裝器，不是上游官方服務。API 程式採 Apache-2.0；影像演算法來自固定版本的 `remove-ai-watermarks`，詳細 attribution 見 [NOTICE](NOTICE)。
