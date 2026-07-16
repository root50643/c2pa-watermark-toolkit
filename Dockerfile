FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

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
