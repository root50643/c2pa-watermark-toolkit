# Frontend workbench guide

[繁體中文](FRONTEND.zh-TW.md)

## Start and connect

Command-line instructions in this guide target Bash on Linux. Start the services from the repository root:

```bash
docker compose up -d --build
```

Then open <http://localhost:8080>. By default, connect with a customer API key issued by the administration CLI. After validation, the workbench displays the customer name and key prefix. The key is kept in browser `sessionStorage` only and can be removed with Disconnect or by ending the session. When the operator sets `REQUIRE_API_KEY=false`, the frontend discovers that mode through capabilities, opens as the anonymous identity automatically, and does not display the API-key input.

The status panel reports API, Archive, and GPU queue availability together with versions, supported formats, and file limits. Use the top-right control to switch between Traditional Chinese and English.

## Image workflows

1. Select identification, visible removal, region repair, metadata, invisible watermark, or complete processing.
2. Drop or choose a PNG, JPEG, WebP, HEIC, HEIF, or AVIF image.
3. Configure the workflow and select Start processing.
4. Synchronous workflows show a before/after comparison, download action, request ID, and archive ID.

Identification presents a JSON provenance report. Visible removal exposes sensitivity, backend, and metadata options. The metadata workflow keeps ordinary non-AI metadata by default, including fields such as Author, Title, and Copyright. Turning it off selects a more aggressive cleanup path, but format-specific lossless processing means it is not a guarantee that every metadata item is blank.

## Region repair

Region repair requires a browser-previewable image. Drag directly on the image to add up to 20 rectangles. Select a rectangle to edit its X, Y, width, and height values, or remove it with Delete or Backspace.

## GPU jobs

Start Redis and the GPU worker with `docker compose --profile gpu up -d --build`. The workbench polls queued, running, succeeded, and failed states automatically. Job IDs remain available for the current browser session and polling resumes after a refresh. Completed results can be downloaded from the job list.

## Development

Frontend API types are generated from the committed `openapi/openapi.json`:

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

The development server uses <http://localhost:5173> and proxies API routes to <http://localhost:8000>.
