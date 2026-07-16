# Contributing

1. Do not commit customer images, archive databases, secrets, or model caches.
2. Install `.[dev]` and run `ruff check .`, `pyright`, and `pytest`.
3. In `frontend/`, run `pnpm check:api`, `pnpm lint`, `pnpm test`, and `pnpm build`.
4. Regenerate `openapi/openapi.json` and frontend API types after changing routes or schemas.
5. Update both Chinese and English documents for public interface changes.
6. Preserve upstream attribution and the lawful-use scope.
