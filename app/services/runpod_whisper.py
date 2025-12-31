"""
RunPod Whisper Service - Serverless GPU transcription via RunPod

Handles transcription jobs using RunPod's faster-whisper serverless endpoint.
Audio files are served via Docling's public URL for RunPod to fetch.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import config

logger = logging.getLogger(__name__)

# RunPod API base URL
RUNPOD_API_BASE = "https://api.runpod.ai/v2"


@dataclass
class TranscriptionResult:
    """Result from RunPod transcription."""
    text: str
    language: str | None
    duration: float
    word_count: int
    segments: list[dict] | None = None


class RunPodWhisperError(Exception):
    """Base exception for RunPod Whisper errors."""
    pass


class RunPodJobTimeoutError(RunPodWhisperError):
    """Job timed out waiting for completion."""
    pass


class RunPodJobFailedError(RunPodWhisperError):
    """Job failed with an error."""
    pass


async def submit_transcription_job(
    audio_url: str,
    model: str | None = None,
    language: str | None = None,
) -> str:
    """
    Submit a transcription job to RunPod.

    Args:
        audio_url: Public URL where RunPod can fetch the audio file
        model: Whisper model to use (default from config)
        language: Language code or None for auto-detect

    Returns:
        Job ID for polling status

    Raises:
        RunPodWhisperError: If submission fails
    """
    runpod_config = config.runpod

    if not runpod_config.is_configured:
        raise RunPodWhisperError("RunPod is not configured")

    endpoint_url = f"{RUNPOD_API_BASE}/{runpod_config.endpoint_id}/run"

    # Build request payload
    payload = {
        "input": {
            "audio": audio_url,
            "model": model or runpod_config.model,
            "transcription": "plain_text",
            "enable_vad": True,  # Voice activity detection for better results
        }
    }

    # Add language if specified (otherwise auto-detect)
    if language:
        payload["input"]["language"] = language

    headers = {
        "Authorization": f"Bearer {runpod_config.api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(endpoint_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            job_id = data.get("id")
            if not job_id:
                raise RunPodWhisperError(f"No job ID in response: {data}")

            logger.info(f"Submitted RunPod transcription job: {job_id}")
            return job_id

        except httpx.HTTPStatusError as e:
            error_text = e.response.text if e.response else str(e)
            raise RunPodWhisperError(f"Failed to submit job: {e.response.status_code} - {error_text}")
        except Exception as e:
            raise RunPodWhisperError(f"Failed to submit job: {e}")


async def get_job_status(job_id: str) -> dict[str, Any]:
    """
    Get the status of a RunPod job.

    Args:
        job_id: The job ID to check

    Returns:
        Job status dict with 'status' and optionally 'output' or 'error'
    """
    runpod_config = config.runpod
    status_url = f"{RUNPOD_API_BASE}/{runpod_config.endpoint_id}/status/{job_id}"

    headers = {
        "Authorization": f"Bearer {runpod_config.api_key}",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(status_url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise RunPodWhisperError(f"Failed to get job status: {e}")


async def wait_for_job_completion(
    job_id: str,
    timeout: float | None = None,
    poll_interval: float | None = None,
) -> dict[str, Any]:
    """
    Wait for a RunPod job to complete.

    Args:
        job_id: The job ID to wait for
        timeout: Maximum time to wait (default from config)
        poll_interval: Time between status checks (default from config)

    Returns:
        Completed job data with output

    Raises:
        RunPodJobTimeoutError: If job doesn't complete in time
        RunPodJobFailedError: If job fails
    """
    runpod_config = config.runpod
    timeout = timeout or runpod_config.job_timeout
    poll_interval = poll_interval or runpod_config.poll_interval

    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise RunPodJobTimeoutError(f"Job {job_id} timed out after {timeout}s")

        status_data = await get_job_status(job_id)
        status = status_data.get("status")

        if status == "COMPLETED":
            logger.info(f"Job {job_id} completed in {elapsed:.1f}s")
            return status_data

        elif status == "FAILED":
            error = status_data.get("error", "Unknown error")
            raise RunPodJobFailedError(f"Job {job_id} failed: {error}")

        elif status in ("IN_QUEUE", "IN_PROGRESS"):
            logger.debug(f"Job {job_id} status: {status} (elapsed: {elapsed:.1f}s)")
            await asyncio.sleep(poll_interval)

        else:
            # Unknown status - wait and retry
            logger.warning(f"Unknown job status: {status}")
            await asyncio.sleep(poll_interval)


def parse_transcription_output(output: dict) -> TranscriptionResult:
    """
    Parse the output from a completed RunPod transcription job.

    Args:
        output: The 'output' dict from job status

    Returns:
        TranscriptionResult with parsed data
    """
    # Handle different output formats
    if isinstance(output, dict):
        # Standard format from faster-whisper worker
        text = output.get("transcription") or output.get("text", "")
        language = output.get("detected_language") or output.get("language")
        segments = output.get("segments")

        # Calculate duration from segments if available
        duration = 0.0
        if segments and len(segments) > 0:
            last_segment = segments[-1]
            duration = last_segment.get("end", 0.0)

        # Calculate word count
        word_count = len(text.split()) if text else 0

        return TranscriptionResult(
            text=text.strip(),
            language=language,
            duration=duration,
            word_count=word_count,
            segments=segments,
        )
    else:
        # Plain text output
        text = str(output).strip()
        return TranscriptionResult(
            text=text,
            language=None,
            duration=0.0,
            word_count=len(text.split()),
            segments=None,
        )


async def transcribe_audio_runpod(
    audio_url: str,
    language: str | None = None,
) -> TranscriptionResult:
    """
    Transcribe audio using RunPod serverless endpoint.

    This is the main entry point for RunPod transcription.

    Args:
        audio_url: Public URL where RunPod can fetch the audio file
        language: Language code or None for auto-detect

    Returns:
        TranscriptionResult with transcription data

    Raises:
        RunPodWhisperError: If transcription fails
    """
    # Submit job
    job_id = await submit_transcription_job(audio_url, language=language)

    # Wait for completion
    result = await wait_for_job_completion(job_id)

    # Parse output
    output = result.get("output", {})
    return parse_transcription_output(output)


def build_audio_url(job_id: int, filename: str, token: str | None = None) -> str:
    """
    Build the public URL for RunPod to fetch an audio file.

    Args:
        job_id: The Docling job ID
        filename: The audio filename
        token: Auth token (default from config)

    Returns:
        Full public URL for the audio file
    """
    runpod_config = config.runpod
    token = token or runpod_config.audio_token

    base_url = runpod_config.public_url.rstrip("/")
    url = f"{base_url}/api/audio-files/{job_id}/{filename}"

    if token:
        url = f"{url}?token={token}"

    return url


async def is_runpod_available() -> bool:
    """
    Check if RunPod service is available and configured.

    Returns:
        True if RunPod can be used for transcription
    """
    runpod_config = config.runpod

    if not runpod_config.is_configured:
        return False

    # Optionally ping the endpoint to check availability
    try:
        health_url = f"{RUNPOD_API_BASE}/{runpod_config.endpoint_id}/health"
        headers = {"Authorization": f"Bearer {runpod_config.api_key}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(health_url, headers=headers)
            return response.status_code == 200
    except Exception as e:
        logger.warning(f"RunPod health check failed: {e}")
        return False
