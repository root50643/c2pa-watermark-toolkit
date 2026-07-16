# C2PA Watermark Toolkit

English | [繁體中文](README.md)

A self-hosted FastAPI wrapper for [wiltodelta/remove-ai-watermarks](https://github.com/wiltodelta/remove-ai-watermarks) 0.15.3. It adds Swagger and API-key enforcement that is enabled by default and can be explicitly disabled.

> Process only content you are authorized to process. Comply with local laws governing AI labels, content credentials, and privacy. This project is not intended to remove paid stock-preview or third-party copyright watermarks.

## Features

- Visible AI watermark removal, region erasing, AI metadata stripping, and provenance identification.
- Optional NVIDIA GPU worker for asynchronous invisible-watermark regeneration.
- API keys are required by default, with multiple revocable keys per customer and an explicit keyless mode.
- Swagger `/docs`, ReDoc `/redoc`, [English API reference](docs/API.en.md), [Chinese reference](docs/API.zh-TW.md), and Postman collection.
- A bilingual React image workbench for identification, visible removal, visual region repair, metadata, and GPU job tracking.

## Linux CPU quick start

The commands below target Bash on Linux. Install Git, OpenSSL, Docker Engine, and the Docker Compose v2 plugin first, and ensure the current user can run `docker`.

```bash
install -m 600 .env.example .env
pepper="$(openssl rand -hex 32)"
sed -i "s|^API_KEY_PEPPER=.*|API_KEY_PEPPER=${pepper}|" .env
unset pepper

docker compose up -d --build
docker compose exec api raiw-api-admin customer create \
  --name "Local developer" --external-id "local-001" --issue-key
```

Open <http://localhost:8080> and enter the one-time `raiw_...` key to use the image workbench. The frontend keeps the key only for the current browser session and calls the API through a same-origin proxy. See the [frontend guide](docs/FRONTEND.en.md).

Swagger is available at <http://localhost:8080/docs> and <http://localhost:8000/docs>.

```bash
export RAIW_API_KEY='raiw_REPLACE_ME'

curl -X POST http://localhost:8000/api/v1/identify \
  -H "X-API-Key: $RAIW_API_KEY" -F "file=@image.png"

curl -X POST http://localhost:8000/api/v1/remove/visible \
  -H "X-API-Key: $RAIW_API_KEY" \
  -F "file=@image.png" -F "backend=cv2" --output processed.png
```

### Keyless mode (optional)

If another identity layer, private network, or gateway protects the service, disable API-key enforcement in `.env` and rebuild/restart:

```bash
sed -i 's/^REQUIRE_API_KEY=.*/REQUIRE_API_KEY=false/' .env
docker compose up -d --build
```

The frontend then opens automatically and API calls may omit `X-API-Key`. `/api/v1/me` returns `null` for `key_id` and `key_prefix`; unauthenticated requests are attributed to a stable anonymous customer. A supplied key is still validated and attributed, and an invalid supplied key still returns 401. This removes per-customer API authorization boundaries, so do not expose it directly to the public Internet; use firewalling, gateway authentication, and rate limiting. Set `REQUIRE_API_KEY=true` to restore the secure default.

### Metadata `keep_standard`

The `keep_standard` field on `POST /api/v1/remove/metadata` controls whether non-AI metadata is retained while AI/C2PA information is removed:

| Value | Behavior |
|---|---|
| `true` (default) | Remove recognized AI/C2PA information while preserving ordinary fields such as Author, Title, Description, Copyright, Comment, Software, Source, and Creation Time where possible. A field is still removed when its value identifies an AI generator. |
| `false` | Do not retain the allowlisted text fields above; use the more aggressive cleanup path. |

The pinned upstream applies format-specific lossless strategies, so `false` does not guarantee that every metadata item is blank. JPEG may retain scrubbed non-AI EXIF, while HEIF/AVIF retains non-AI container data. See the [API reference](docs/API.en.md) for every request field.

## GPU profile

The Linux host needs an NVIDIA driver, Docker Engine, and NVIDIA Container Toolkit. The first inference downloads several gigabytes of models.

```bash
docker compose --profile gpu up -d --build
```

Submit `/api/v1/jobs/invisible` or `/all`, poll `/api/v1/jobs/{id}`, then download `/result`. See the [API reference](docs/API.en.md).

Configuration variables are documented in [.env.example](.env.example) and the [API reference](docs/API.en.md). `REQUIRE_API_KEY` defaults to `true`. In production, replace `API_KEY_PEPPER`; changing it invalidates every existing key. Forwarded client IP headers are trusted only from `TRUSTED_PROXY_CIDRS`.

## Development

The following workflow targets Linux Bash with Python 3 and Node.js 22:

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

## Upstream and license

This is an independent wrapper, not an official upstream service. The API code is Apache-2.0 licensed; the pinned image-processing dependency and attribution are described in [NOTICE](NOTICE).
