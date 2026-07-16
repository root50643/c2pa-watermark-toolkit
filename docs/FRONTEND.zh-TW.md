# 前端工作台使用文件

[English](FRONTEND.en.md)

## 啟動與連接

本文件的命令列指令以 Linux Bash 為準。請從專案根目錄啟動服務：

```bash
docker compose up -d --build
```

接著開啟 <http://localhost:8080>。使用管理 CLI 核發的客戶 API Key 連接工作台；驗證成功後畫面會顯示客戶名稱與 key prefix。金鑰只放在瀏覽器 `sessionStorage`，按下「中斷連接」或結束工作階段即可清除。

首頁系統狀態會顯示 API、Archive 與 GPU queue 是否可用，以及 API／上游版本、格式與單檔限制。右上角可在繁體中文與英文之間切換。

## 圖片工作流程

1. 選擇圖片識別、可見標記、區域修補、Metadata、不可見浮水印或完整處理。
2. 拖放或選擇 PNG、JPEG、WebP、HEIC、HEIF、AVIF 圖片。
3. 設定該流程的參數並按「開始處理」。
4. 同步流程完成後可比較處理前後圖片並下載，畫面同時顯示 request ID 與 archive ID。

圖片識別以 JSON 報告呈現來源與已知訊號。可見標記可設定敏感度、後端及是否一併清除 Metadata。Metadata 流程可選擇是否保留標準 EXIF 欄位。

## 區域修補

區域修補需要瀏覽器可預覽的圖片。直接在圖片上拖曳即可建立矩形；最多 20 個。選取矩形後可在下方精確修改 X、Y、寬與高，或使用 Delete／Backspace 刪除選取區域。

## GPU 工作

以 `docker compose --profile gpu up -d --build` 啟動 Redis 與 GPU worker 後，首頁 GPU 佇列會顯示可用。提交不可見或完整流程後，工作台自動輪詢 queued、running、succeeded、failed 狀態。工作 ID 保留於目前瀏覽器工作階段，重新整理頁面後可繼續追蹤；完成後按下載按鈕取得結果。

## 開發

前端 API 型別由已提交的 `openapi/openapi.json` 產生：

```bash
cd frontend
corepack enable
pnpm install --frozen-lockfile
pnpm generate:api
pnpm check:api
pnpm lint
pnpm test
pnpm build
```

開發伺服器預設為 <http://localhost:5173>，並將 API 路徑代理至 <http://localhost:8000>。
