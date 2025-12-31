"""
YouTube API Routes - Video and channel processing

Jobs are created with status='pending' and processed by the background worker.
Run the worker separately: ENV_FILE=.env.local python -m app.worker
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import repository
from app.core.youtube_processor import (
    get_video_info,
    get_channel_info,
    get_video_url,
)

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


class VideoRequest(BaseModel):
    """Request to process a YouTube video."""
    url: str = Field(description="YouTube video URL")
    category_id: int | None = None


class ChannelRequest(BaseModel):
    """Request to process a YouTube channel."""
    url: str = Field(description="YouTube channel URL")
    category_id: int | None = None
    limit: int | None = Field(default=None, description="Max videos to process")


class MonitorRequest(BaseModel):
    """Request to start monitoring a YouTube channel."""
    url: str = Field(description="YouTube channel URL")
    category_id: int | None = None
    check_interval_hours: int = Field(default=48, ge=1, le=168)
    initial_video_limit: int | None = Field(
        default=None,
        description="Max videos to process immediately (None for all videos, 0 to skip)",
    )


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


class MonitoredChannelResponse(BaseModel):
    """Response for monitored channel."""
    id: int
    channel_id: str
    channel_name: str
    channel_url: str
    category_id: int | None
    last_checked_at: str | None
    video_count: int
    is_active: bool
    check_interval_hours: int


class MonitorWithJobResponse(BaseModel):
    """Response for monitored channel with initial processing job."""
    channel: MonitoredChannelResponse
    job: JobResponse | None = None


@router.post("/video/info", response_model=VideoInfoResponse)
async def get_video_information(data: VideoRequest):
    """Get information about a YouTube video."""
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
async def transcribe_youtube_video(data: VideoRequest):
    """Transcribe a YouTube video.

    Creates a job with status='pending'. Run the worker to process:
    ENV_FILE=.env.local python -m app.worker

    Deduplication: Returns existing job if URL is already queued or processed.
    """
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
        job_type="youtube_video",
        source_url=data.url,
        category_id=data.category_id,
    )

    return JobResponse(job_id=job_id, status="pending")


@router.post("/channel/info", response_model=ChannelInfoResponse)
async def get_channel_information(data: ChannelRequest):
    """Get information about a YouTube channel."""
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
    """Transcribe all videos from a YouTube channel.

    Creates a job with status='pending'. Run the worker to process:
    ENV_FILE=.env.local python -m app.worker

    Deduplication: Returns existing job if channel URL is already queued.
    """
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
        job_type="youtube_channel",
        source_url=data.url,
        category_id=data.category_id,
    )

    return JobResponse(job_id=job_id, status="pending")


@router.post("/channel/monitor", response_model=MonitorWithJobResponse)
async def start_monitoring_channel(data: MonitorRequest):
    """Start monitoring a YouTube channel for new videos.

    Creates a job with status='pending' for initial processing.
    Run the worker to process: ENV_FILE=.env.local python -m app.worker
    """
    # Get channel info
    info = await get_channel_info(data.url)
    if not info:
        raise HTTPException(status_code=400, detail="Could not get channel information")

    # Check if already monitoring
    existing = await repository.get_channel_by_youtube_id(info["channel_id"])
    if existing:
        raise HTTPException(status_code=400, detail="Channel is already being monitored")

    # Validate category
    if data.category_id:
        category = await repository.get_category(data.category_id)
        if not category:
            raise HTTPException(status_code=400, detail="Invalid category")

    # Create monitored channel
    channel_id = await repository.create_monitored_channel(
        channel_id=info["channel_id"],
        channel_name=info["channel_name"],
        channel_url=info["channel_url"],
        category_id=data.category_id,
        check_interval_hours=data.check_interval_hours,
    )

    channel = await repository.get_monitored_channel(channel_id)

    # Create job for initial processing (worker will pick it up)
    job_response = None
    if data.initial_video_limit != 0:  # 0 means skip initial processing
        # Check for existing active job (deduplication)
        existing_job = await repository.get_active_job_by_url(info["channel_url"])
        if existing_job:
            job_response = JobResponse(
                job_id=existing_job["id"],
                status=existing_job["status"],
                duplicate=True,
                message=f"Job already exists with status '{existing_job['status']}'"
            )
        else:
            job_id = await repository.create_job(
                job_type="youtube_channel",
                source_url=info["channel_url"],
                category_id=data.category_id,
            )
            job_response = JobResponse(job_id=job_id, status="pending")

    return MonitorWithJobResponse(channel=channel, job=job_response)


@router.get("/channels", response_model=list[MonitoredChannelResponse])
async def list_monitored_channels(active_only: bool = False):
    """List monitored YouTube channels."""
    channels = await repository.get_monitored_channels(active_only)
    return channels


@router.delete("/channels/{channel_id}", status_code=204)
async def stop_monitoring_channel(channel_id: int):
    """Stop monitoring a YouTube channel."""
    channel = await repository.get_monitored_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    await repository.delete_monitored_channel(channel_id)
