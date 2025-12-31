"""
Audio Files API - Serves audio files for RunPod transcription

This endpoint allows RunPod serverless workers to fetch audio files
from Docling for transcription. Protected by a token to prevent
unauthorized access.
"""

from pathlib import Path
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import config, TRANSCRIPTS_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audio-files", tags=["audio-files"])


@router.get("/{job_id}/{filename}")
async def get_audio_file(
    job_id: int,
    filename: str,
    token: str = Query(None, description="Auth token for access"),
):
    """
    Serve an audio file for RunPod to fetch.

    This endpoint is called by RunPod serverless workers to download
    audio files for transcription. Access is protected by a token.

    Args:
        job_id: The Docling job ID (used for logging/tracking)
        filename: The audio filename to serve
        token: Auth token (must match RUNPOD_AUDIO_TOKEN)

    Returns:
        The audio file as a streaming response
    """
    runpod_config = config.runpod

    # Validate token if configured
    if runpod_config.audio_token:
        if token != runpod_config.audio_token:
            logger.warning(f"Invalid audio token for job {job_id}, file {filename}")
            raise HTTPException(status_code=403, detail="Invalid token")

    # Sanitize filename to prevent path traversal
    safe_filename = Path(filename).name
    if safe_filename != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Look for the file in transcripts directory
    file_path = TRANSCRIPTS_DIR / safe_filename

    if not file_path.exists():
        logger.warning(f"Audio file not found: {file_path}")
        raise HTTPException(status_code=404, detail="File not found")

    # Verify the file is within the allowed directory
    try:
        file_path.resolve().relative_to(TRANSCRIPTS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    logger.info(f"Serving audio file for job {job_id}: {safe_filename}")

    # Determine media type based on extension
    extension = file_path.suffix.lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
        ".opus": "audio/opus",
    }
    media_type = media_types.get(extension, "application/octet-stream")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=safe_filename,
    )


@router.head("/{job_id}/{filename}")
async def check_audio_file(
    job_id: int,
    filename: str,
    token: str = Query(None, description="Auth token for access"),
):
    """
    Check if an audio file exists (HEAD request).

    RunPod may use HEAD requests to check file availability before downloading.
    """
    runpod_config = config.runpod

    # Validate token if configured
    if runpod_config.audio_token:
        if token != runpod_config.audio_token:
            raise HTTPException(status_code=403, detail="Invalid token")

    # Sanitize filename
    safe_filename = Path(filename).name
    if safe_filename != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = TRANSCRIPTS_DIR / safe_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return {"exists": True, "size": file_path.stat().st_size}
