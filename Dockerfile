FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY backend/main.py ./main.py
# scripts/ + data/ để chạy ingest Neo4j và index Qdrant NGAY BÊN TRONG container
# (docker compose exec app python scripts/...). .dockerignore đã loại bỏ file nặng không cần.
COPY scripts ./scripts
COPY data ./data

RUN chmod +x /app/scripts/docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f "http://127.0.0.1:${PORT}/api/health" || exit 1

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
