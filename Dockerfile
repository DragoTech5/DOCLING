# Multi-stage build for Docling hybrid monorepo (Python backend + React/Node.js frontend)

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
COPY telegram-mini-app/vite.config.ts ./telegram-mini-app/
COPY telegram-mini-app/tailwind.config.js ./telegram-mini-app/
COPY telegram-mini-app/postcss.config.js ./telegram-mini-app/
COPY telegram-mini-app/index.html ./telegram-mini-app/

# Build frontend
RUN cd telegram-mini-app && npm run build

# Stage 2: Python runtime with FastAPI backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Python packages (especially for psycopg2, PIL, etc.)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libpq-dev \
    libssh-dev \
    ssh \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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

# Run FastAPI with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
