# ---------- Backend image: FastAPI + PyTorch (CPU) ----------
FROM python:3.10-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production

WORKDIR /app

# System libraries needed by Pillow / PyTorch CPU wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo-dev zlib1g-dev libwebp-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
# CPU-only torch keeps the image ~2 GB smaller than the CUDA build
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 \
       --index-url https://download.pytorch.org/whl/cpu

COPY ml /app/ml
COPY backend /app/backend
COPY models /app/models

WORKDIR /app/backend

# Data (SQLite + encrypted uploads) lives on a volume
RUN mkdir -p /app/backend/data/encrypted_uploads /app/backend/data/tmp

# Run as a non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
