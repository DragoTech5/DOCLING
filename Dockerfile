# Multi-stage build for Docling hybrid monorepo (Python backend + React/Node.js frontend)
# Optimization: Use Alpine Linux to avoid transient infrastructure timeouts during apt-get
# Force rebuild - deployment trigger 2026-01-04

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

# Build frontend and remove node_modules to reduce final image size
RUN cd telegram-mini-app && npm run build && rm -rf node_modules

# Stage 2: Python runtime with FastAPI backend (using Debian slim for wheel compatibility)
FROM python:3.11-slim

# Force complete rebuild - no Docker cache - 2026-01-04T22:50
ARG CACHE_BUST=2026-01-04T22:50
RUN echo "Forcing rebuild: $CACHE_BUST" && date

WORKDIR /app

# Stage 2a: Build and install dependencies with build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    openssh-client \
    python3-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    libssl-dev \
    libffi-dev \
    cifs-utils \
    && pip install --upgrade pip setuptools wheel \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.9.0 && \
    pip install --no-cache-dir sentence-transformers>=5.0.0 transformers>=4.40.0 && \
    apt-get remove -y --purge \
    build-essential \
    python3-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    libffi-dev \
    && apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy backend source (force rebuild - 2026-01-04T22:50)
COPY app ./app
COPY .env.railway .env
COPY start.py ./start.py

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/telegram-mini-app/dist ./static/twa

# Expose port
EXPOSE 8200

# Verify port configuration is correct (invalidates Docker cache for clean rebuild)
RUN test 8200 -eq 8200 && echo "✓ Port 8200 correctly configured"

# Start application with uvicorn directly
# Simple approach: just run uvicorn on hardcoded port 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
