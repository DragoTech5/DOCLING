"""
Rumble API Routes - Video and channel processing

Jobs are created with status='pending' and processed by the background worker.
Run the worker separately: ENV_FILE=.env.local python -m app.worker
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import repository
from app.core.rumble_processor import (
    get_video_info,
    get_channel_info,
    get_video_url,
    is_rumble_url,
)

router = APIRouter(prefix="/api/rumble", tags=["rumble"])


class VideoRequest(BaseModel):
    """Request to process a Rumble video."""
    url: str = Field(description="Rumble video URL")
    category_id: int | None = None


class ChannelRequest(BaseModel):
    """Request to process a Rumble channel."""
    url: str = Field(description="Rumble channel URL")
    category_id: int | None = None
    limit: int | None = Field(default=None, description="Max videos to process")


class VideoInfoResponse(BaseModel):
    """Response with video information."""
    video_id: str
    title: str
    channel_name: str
    duration: int
    view_count: int
    thumbnail_url: str | None


class ChannelInfoResponse(BaseModel):
    """Response with channel information."""
    channel_id: str
    channel_name: str
    channel_url: str
    description: str
    subscriber_count: int | None = None


class JobResponse(BaseModel):
    """Response with job information."""
    job_id: int
    status: str
    duplicate: bool = False
    message: str | None = None


@router.post("/video/info", response_model=VideoInfoResponse)
async def get_video_information(data: VideoRequest):
    """Get information about a Rumble video."""
    if not is_rumble_url(data.url):
        raise HTTPException(status_code=400, detail="Not a valid Rumble URL")

    info = await get_video_info(data.url)
    if not info:
        raise HTTPException(status_code=400, detail="Could not get video information")

    return VideoInfoResponse(
        video_id=info.video_id,
        title=info.title,
        channel_name=info.channel_name,
        duration=info.duration,
        view_count=info.view_count,
        thumbnail_url=info.thumbnail_url,
    )


@router.post("/video/transcribe", response_model=JobResponse)
async def transcribe_rumble_video(data: VideoRequest):
    """Transcribe a Rumble video.

    Creates a job with status='pending'. Run the worker to process:
    ENV_FILE=.env.local python -m app.worker

    Deduplication: Returns existing job if URL is already queued or processed.
    """
    if not is_rumble_url(data.url):
        raise HTTPException(status_code=400, detail="Not a valid Rumble URL")

    # Check for existing active job (deduplication)
    existing_job = await repository.get_active_job_by_url(data.url)
    if existing_job:
        return JobResponse(
            job_id=existing_job["id"],
            status=existing_job["status"],
            duplicate=True,
            message=f"Job already exists with status '{existing_job['status']}'"
        )

    # Check if content already processed
    existing_content = await repository.get_content_by_url(data.url)
    if existing_content:
        raise HTTPException(
            status_code=409,
            detail=f"Content already exists: '{existing_content['title']}'"
        )

    # Validate category
    if data.category_id:
        category = await repository.get_category(data.category_id)
        if not category:
            raise HTTPException(status_code=400, detail="Invalid category")

    # Create job (worker will pick it up)
    job_id = await repository.create_job(
        job_type="rumble_video",
        source_url=data.url,
        category_id=data.category_id,
    )

    return JobResponse(job_id=job_id, status="pending")


@router.post("/channel/info", response_model=ChannelInfoResponse)
async def get_channel_information(data: ChannelRequest):
    """Get information about a Rumble channel."""
    if not is_rumble_url(data.url):
        raise HTTPException(status_code=400, detail="Not a valid Rumble URL")

    info = await get_channel_info(data.url)
    if not info:
        raise HTTPException(status_code=400, detail="Could not get channel information")

    return ChannelInfoResponse(
        channel_id=info["channel_id"],
        channel_name=info["channel_name"],
        channel_url=info["channel_url"],
        description=info["description"],
        subscriber_count=info.get("subscriber_count"),
    )


@router.post("/channel/transcribe", response_model=JobResponse)
async def transcribe_channel_videos(data: ChannelRequest):
    """Transcribe all videos from a Rumble channel.

    Creates a job with status='pending'. Run the worker to process:
    ENV_FILE=.env.local python -m app.worker

    Deduplication: Returns existing job if channel URL is already queued.
    """
    if not is_rumble_url(data.url):
        raise HTTPException(status_code=400, detail="Not a valid Rumble URL")

    # Check for existing active job (deduplication)
    existing_job = await repository.get_active_job_by_url(data.url)
    if existing_job:
        return JobResponse(
            job_id=existing_job["id"],
            status=existing_job["status"],
            duplicate=True,
            message=f"Job already exists with status '{existing_job['status']}'"
        )

    # Validate category
    if data.category_id:
        category = await repository.get_category(data.category_id)
        if not category:
            raise HTTPException(status_code=400, detail="Invalid category")

    # Create job (worker will pick it up)
    job_id = await repository.create_job(
        job_type="rumble_channel",
        source_url=data.url,
        category_id=data.category_id,
    )

    return JobResponse(job_id=job_id, status="pending")
