# Multi-stage build for Docling Knowledge Hub + Telegram Mini App
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Install Node dependencies and build frontend
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && cd telegram-mini-app \
    && npm ci --production=false \
    && npm run build \
    && cd .. \
    && rm -rf telegram-mini-app/node_modules \
    && apt-get remove -y nodejs npm \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8200/health || exit 1

# Expose port
EXPOSE 8200

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
