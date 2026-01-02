#!/bin/bash
# Docker entrypoint script that mounts NAS SMB share before starting app

set -e

echo "=== Docling Entrypoint ==="

# Check if SMB mount is needed
if [ "$SMB_MOUNT_ENABLED" = "true" ]; then
    echo "SMB mount enabled - mounting NAS data directory..."

    SMB_HOST="${SMB_HOST:-192.168.1.117}"
    SMB_SHARE="${SMB_SHARE:-data}"
    SMB_USERNAME="${SMB_USERNAME:-kanat}"
    SMB_PASSWORD="${SMB_PASSWORD:-Drakuul55+}"
    MOUNT_POINT="${MOUNT_POINT:-/app/data}"

    # Create mount point
    mkdir -p "$MOUNT_POINT"

    # Mount SMB share using credentials from environment
    echo "Mounting //$SMB_HOST/$SMB_SHARE to $MOUNT_POINT..."
    mount -t cifs "//$SMB_HOST/$SMB_SHARE" "$MOUNT_POINT" \
        -o "username=$SMB_USERNAME,password=$SMB_PASSWORD,uid=0,gid=0,dir_mode=0777,file_mode=0777" 2>&1 || {
        echo "Failed to mount SMB share, retrying in 2 seconds..."
        sleep 2
        mount -t cifs "//$SMB_HOST/$SMB_SHARE" "$MOUNT_POINT" \
            -o "username=$SMB_USERNAME,password=$SMB_PASSWORD,uid=0,gid=0,dir_mode=0777,file_mode=0777"
    }

    echo "✓ SMB share mounted to $MOUNT_POINT"
    echo "  Share: $SMB_SHARE on $SMB_HOST"
    echo "  Checking mount contents..."
    ls -la "$MOUNT_POINT" | head -5
else
    echo "SMB mount disabled - using local data directory"
fi

# Verify data directory exists
if [ ! -d "/app/data" ]; then
    echo "Creating /app/data directory..."
    mkdir -p /app/data
fi

echo "Starting Docling application..."
echo "HOST: ${HOST:-0.0.0.0}"
echo "PORT: ${PORT:-8200}"

# Start the FastAPI application
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8200}"
