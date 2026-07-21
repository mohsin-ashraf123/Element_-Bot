# PairFlow API — production container (Railway / Render / Fly.io)
FROM python:3.12-slim-bookworm

WORKDIR /app

# System libolm — python3-olm binds to these headers/libs (do not build bundled olm from sdist)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libolm-dev \
    libolm3 \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Olm Python bindings: PEP517 isolated builds miss interface-include/ — use system libolm
RUN pip install --no-cache-dir --upgrade pip setuptools wheel cffi \
    && pip install --no-cache-dir --no-build-isolation "python3-olm>=3.2.20" \
    && pip install --no-cache-dir -r requirements.txt

# Playwright is heavy — skip on small Railway/Fly VMs: docker build --build-arg SKIP_PLAYWRIGHT=1
ARG SKIP_PLAYWRIGHT=1
RUN if [ "$SKIP_PLAYWRIGHT" = "0" ]; then playwright install --with-deps chromium; fi

COPY app ./app

RUN mkdir -p /app/data/matrix_store /app/data/reports

ENV APP_ENV=production \
    APP_PORT=8000 \
    PYTHONUNBUFFERED=1 \
    MATRIX_E2EE_STORE_PATH=/app/data/matrix_store

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -f http://127.0.0.1:8000/api/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
