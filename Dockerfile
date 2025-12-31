# Multi-stage build for Docling hybrid monorepo (Python backend + React/Node.js frontend)
# Optimization: Use Alpine Linux to avoid transient infrastructure timeouts during apt-get

# Stage 1: Build frontend (Node.js/Vite)
FROM node:22-alpine AS frontend-builder

WORKDIR /app

# Copy only package files first (for better cache)
COPY telegram-mini-app/package.json telegram-mini-app/package-lock.json ./telegram-mini-app/

# Install frontend dependencies
RUN cd telegram-mini-app && npm ci --frozen-lockfile

# Copy frontend source
COPY telegram-mini-app/src ./telegram-mini-app/src
COPY telegram-mini-app/public ./telegram-mini-app/public
COPY telegram-mini-app/tsconfig.json ./telegram-mini-app/
COPY telegram-mini-app/tsconfig.node.json ./telegram-mini-app/
COPY telegram-mini-app/vite.config.ts ./telegram-mini-app/
COPY telegram-mini-app/tailwind.config.js ./telegram-mini-app/
COPY telegram-mini-app/postcss.config.js ./telegram-mini-app/
COPY telegram-mini-app/index.html ./telegram-mini-app/

# Build frontend
RUN cd telegram-mini-app && npm run build

# Stage 2: Python runtime with FastAPI backend (using Debian slim for wheel compatibility)
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Python packages (PostgreSQL client libs, SSH, build tools, ML libraries)
# Use single RUN command with proper apt caching to avoid timeouts
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    openssh-client \
    git \
    python3-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY app ./app
COPY .env.railway .env

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/telegram-mini-app/dist ./app/static/twa

# Expose port
EXPOSE 8200

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8200/health')" || exit 1

# Use shell form to support environment variable expansion
# PORT defaults to 8200, HOST defaults to 0.0.0.0
ENTRYPOINT sh -c 'uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8200}'
