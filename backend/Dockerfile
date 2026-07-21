# PairFlow API — production container (Render / Railway / Fly.io)
FROM python:3.12-slim-bookworm

WORKDIR /app

# libolm + build deps for matrix-nio E2EE
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libolm-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium for report PNG screenshots
RUN playwright install --with-deps chromium

COPY app ./app

RUN mkdir -p /app/data/matrix_store /app/data/reports

ENV APP_ENV=production \
    APP_PORT=8000 \
    PYTHONUNBUFFERED=1 \
    MATRIX_E2EE_STORE_PATH=/app/data/matrix_store

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
