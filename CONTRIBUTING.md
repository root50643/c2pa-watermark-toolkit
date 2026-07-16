# Contributing

Development commands and CI target Bash on Linux. A typical local setup is:

```bash
python3 -m venv .bootstrap-venv
. .bootstrap-venv/bin/activate
python -m pip install uv==0.8.2
uv sync --frozen --extra dev
uv run ruff check .
uv run pyright
uv run pytest

cd frontend
corepack enable
pnpm install --frozen-lockfile
pnpm check:api
pnpm lint
pnpm test
pnpm build
```

1. Do not commit customer images, archive databases, secrets, or model caches.
2. Regenerate `openapi/openapi.json` and frontend API types after changing routes or schemas.
3. Update both Chinese and English documents for public interface changes.
4. Preserve upstream attribution and the lawful-use scope.
