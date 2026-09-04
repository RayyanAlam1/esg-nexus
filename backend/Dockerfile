FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt
COPY backend /app
COPY frameworks /frameworks
COPY seed /seed
ENV ESG_FRAMEWORKS_DIR=/frameworks ESG_SEED_DIR=/seed/ecorp_2023 ESG_LOCAL_STORAGE_DIR=/data/storage
RUN useradd -m esg && mkdir -p /data/storage && chown -R esg /data /app
USER esg
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD curl -fsS http://localhost:8000/health/ready || exit 1
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2}"]
