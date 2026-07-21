# PairFlow API — Railway / Render / Fly.io
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libolm3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Pre-built python-olm wheels from Matrix.org (PyPI sdist is broken on 3.12)
ENV PIP_EXTRA_INDEX_URL=https://gitlab.matrix.org/api/v4/projects/27/packages/pypi/simple
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --only-binary=python-olm "python-olm==3.2.16" \
    && pip install --no-cache-dir -r requirements.txt

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
  CMD curl -f http://127.0.0.1:${PORT:-8000}/api/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
