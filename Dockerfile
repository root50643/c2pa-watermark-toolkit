FROM python:3.14-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md requirements.cpu.lock ./
COPY src ./src
RUN pip install --upgrade pip \
    && pip install -r requirements.cpu.lock \
    && pip install . --no-deps

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/archive \
    && chown -R appuser:appuser /data /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "raiw_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
