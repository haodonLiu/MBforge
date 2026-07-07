# syntax=docker/dockerfile:1.7
# MBForge — multi-stage CUDA Docker image
# Build: docker build -t mbforge:dev .
# Run:   docker run --rm --gpus all -p 18792:18792 mbforge:dev

ARG PYTHON_VERSION=3.12
ARG CUDA_VERSION=12.8.0

# ============================================================================
# Stage 1: Frontend build (discarded)
# ============================================================================
FROM node:22-alpine AS frontend-builder
WORKDIR /build

# Install deps first for layer caching
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Build
COPY frontend/ ./
RUN npm run build
# → /build/frontend/dist (Vite default)


# ============================================================================
# Stage 2: Python dependencies via uv (discarded)
# ============================================================================
FROM python:${PYTHON_VERSION}-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./

# Use a separate cache mount for uv to keep builds fast
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev


# ============================================================================
# Stage 3: Runtime (FINAL image)
# ============================================================================
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu22.04 AS runtime

# Python 3.12 + minimal system libs (PyTorch/Ultralytics need libgl/libglib)
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3-pip ca-certificates \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3

WORKDIR /app

# Python environment
COPY --from=deps /app/.venv .venv
COPY pyproject.toml uv.lock ./
COPY src ./src

# Frontend build output (served as static by FastAPI)
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    MBFORGE_HOST=0.0.0.0 \
    MBFORGE_PORT=18792 \
    MBFORGE_IN_DOCKER=1 \
    FRONTEND_DIST=/app/frontend/dist \
    NVIDIA_VISIBLE_DEVICES=all

EXPOSE 18792

# Healthcheck (after backend has time to load ML models)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://127.0.0.1:18792/api/v1/health', timeout=5).raise_for_status()" || exit 1

CMD ["python", "-m", "mbforge"]