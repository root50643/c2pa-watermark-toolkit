# C2PA Watermark Toolkit

English | [繁體中文](README.md)

A self-hosted FastAPI wrapper for [wiltodelta/remove-ai-watermarks](https://github.com/wiltodelta/remove-ai-watermarks) 0.15.3. It adds Swagger, customer-specific API keys, permanent retention of every accepted input and result, and access auditing with source IP and timestamps.

> Process only content you are authorized to process. Comply with local laws governing AI labels, content credentials, privacy, and audit data. This project is not intended to remove paid stock-preview or third-party copyright watermarks.

## Features

- Visible AI watermark removal, region erasing, AI metadata stripping, and provenance identification.
- Optional NVIDIA GPU worker for asynchronous invisible-watermark regeneration.
- Multiple revocable keys per customer; plaintext keys are never stored.
- A separate permanent input and output copy, response, manifest, and hashes for every request.
- Permanent customer, key, client/peer IP, UTC timestamp, User-Agent, route, status, and latency audit records.
- Swagger `/docs`, ReDoc `/redoc`, [English API reference](docs/API.en.md), [Chinese reference](docs/API.zh-TW.md), and Postman collection.
- A bilingual React image workbench for identification, visible removal, visual region repair, metadata, and GPU job tracking.

## CPU quick start

```powershell
Copy-Item .env.example .env
# Replace API_KEY_PEPPER in .env with a long random secret.
docker compose up -d --build
docker compose exec api raiw-api-admin customer create `
  --name "Local developer" --external-id "local-001" --issue-key
```

Open <http://localhost:8080> and enter the one-time `raiw_...` key to use the image workbench. The frontend keeps the key only for the current browser session and calls the API through a same-origin proxy. See the [frontend guide](docs/FRONTEND.en.md).

Swagger is available at <http://localhost:8080/docs> and <http://localhost:8000/docs>.

```bash
curl -X POST http://localhost:8000/api/v1/identify \
  -H "X-API-Key: $RAIW_API_KEY" -F "file=@image.png"

curl -X POST http://localhost:8000/api/v1/remove/visible \
  -H "X-API-Key: $RAIW_API_KEY" \
  -F "file=@image.png" -F "backend=cv2" --output processed.png
```

## GPU profile

The host needs an NVIDIA driver, Docker, and NVIDIA Container Toolkit. The first inference downloads several gigabytes of models.

```bash
docker compose --profile gpu up -d --build
```

Submit `/api/v1/jobs/invisible` or `/all`, poll `/api/v1/jobs/{id}`, then download `/result`. See the [API reference](docs/API.en.md).

## Permanent data and audit storage

Compose bind-mounts `./archive-data` to `/data/archive`. Every request gets a separate directory even when bytes are identical. SQLite is stored at `archive-data/raiw-api.sqlite3`. Nothing expires automatically; operators are responsible for capacity, backups, access controls, privacy notices, and deletion requests. The directory is Git-ignored and must never be committed.

```bash
docker compose exec api raiw-api-admin customer list
docker compose exec api raiw-api-admin key revoke KEY_ID
docker compose exec api raiw-api-admin archive export --format csv --output /data/archive/archive.csv
docker compose exec api raiw-api-admin audit export --format json --output /data/archive/audit.json
docker compose exec api raiw-api-admin archive verify
docker compose exec api raiw-api-admin archive delete REQUEST_ID --yes
```

Configuration variables are documented in [.env.example](.env.example) and the [API reference](docs/API.en.md). In production, replace `API_KEY_PEPPER`; changing it invalidates every existing key. Forwarded client IP headers are trusted only from `TRUSTED_PROXY_CIDRS`.

## Development

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

## Upstream and license

This is an independent wrapper, not an official upstream service. The API code is Apache-2.0 licensed; the pinned image-processing dependency and attribution are described in [NOTICE](NOTICE).
