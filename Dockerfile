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

# Build frontend and remove node_modules to reduce final image size
RUN cd telegram-mini-app && npm run build && rm -rf node_modules

# Stage 2: Python runtime with FastAPI backend (using Debian slim for wheel compatibility)
FROM python:3.11-slim

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

# Copy backend source
COPY app ./app
COPY .env.railway .env

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/telegram-mini-app/dist ./app/static/twa

# Copy entrypoint script for SMB mount support
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose port
EXPOSE 8200

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8200/health')" || exit 1

# PORT is set by Railway deployment platform
# HOST defaults to 0.0.0.0
# SMB_MOUNT_ENABLED controls whether to mount NAS data via SMB (for persistent storage)
ENTRYPOINT ["/docker-entrypoint.sh"]
