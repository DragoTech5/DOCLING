"""
Job Processor - Core logic for processing transcription jobs

Used by both the background worker and (optionally) BackgroundTasks.
Handles single video and channel transcription with progress tracking.

Features:
- Rate limit detection and auto-recovery
- Automatic cookie refresh on auth errors
- Configurable delays between downloads
- Retry logic with exponential backoff
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass

from app.db import repository
from app.db.vector_store import add_documents, get_collection_name
from app.config import config
from app.core.youtube_processor import (
    get_video_info as get_youtube_video_info,
    list_channel_videos as list_youtube_channel_videos,
    transcribe_video as transcribe_youtube_video,
    get_video_url as get_youtube_video_url,
)
from app.core.rumble_processor import (
    get_video_info as get_rumble_video_info,
    list_channel_videos as list_rumble_channel_videos,
    transcribe_video as transcribe_rumble_video,
    get_video_url as get_rumble_video_url,
)
from app.core.embeddings import chunk_text, generate_embeddings
from app.core.docling_processor import extract_preview
from app.core.cookie_refresher import (
    get_cookie_refresher,
    auto_refresh_cookies_if_needed,
)

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a job."""
    success: bool
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    error_message: str | None = None
    paused: bool = False  # Indicates job was paused mid-processing


async def check_should_pause(job_id: int) -> bool:
    """
    Check if processing should pause.

    Returns True if any of:
    - The worker is globally paused
    - The specific job has been paused
    - A higher priority job is waiting (preemption)
    """
    # Check global worker pause
    if await repository.get_worker_paused():
        return True

    # Check job-specific pause
    job = await repository.get_job(job_id)
    if not job:
        return True  # Job deleted, stop processing

    if job.get("status") == "paused":
        return True

    # Check for higher priority jobs (preemption)
    current_priority = job.get("priority", 50)
    higher_priority_job = await repository.get_higher_priority_pending_job(current_priority)
    if higher_priority_job:
        logger.info(
            f"Preempting job {job_id} (priority={current_priority}) "
            f"for job {higher_priority_job['id']} (priority={higher_priority_job['priority']})"
        )
        # Auto-pause current job to allow higher priority job to run
        await repository.pause_job(job_id)
        return True

    return False


async def add_jitter_delay(base_delay: int) -> None:
    """Add a delay with random jitter to avoid detection patterns."""
    # Add 0-50% random jitter
    jitter = random.uniform(0, base_delay * 0.5)
    total_delay = base_delay + jitter
    logger.debug(f"Waiting {total_delay:.1f}s before next request")
    await asyncio.sleep(total_delay)


async def transcribe_with_retry(
    video_url: str,
    max_retries: int = 3,
    base_backoff: int = 60,
    platform: str = "youtube",
    job_id: int | None = None,
) -> tuple[any, str | None]:
    """
    Transcribe a video with automatic retry and cookie refresh.

    Args:
        video_url: Video URL
        max_retries: Maximum number of retry attempts
        base_backoff: Base backoff time in seconds
        platform: "youtube" or "rumble"
        job_id: Optional job ID for RunPod URL building

    Returns:
        Tuple of (result, error_message). Result is None if failed.
    """
    refresher = get_cookie_refresher()
    youtube_config = config.youtube

    # Select transcribe function based on platform
    if platform == "rumble":
        transcribe_fn = transcribe_rumble_video
    else:
        transcribe_fn = transcribe_youtube_video

    for attempt in range(1, max_retries + 1):
        try:
            result = await transcribe_fn(video_url, job_id=job_id)
            if result:
                return result, None
            else:
                # Transcription returned None - likely download/processing issue
                error_msg = "Transcription returned no result"

                # Check if we should try refreshing cookies (YouTube only)
                if platform == "youtube" and youtube_config.auto_refresh_cookies and attempt < max_retries:
                    logger.warning(f"Attempt {attempt} failed, trying cookie refresh")
                    refreshed = await auto_refresh_cookies_if_needed(error_msg)
                    if refreshed:
                        # Wait a bit after refresh before retry
                        await asyncio.sleep(10)
                        continue

                return None, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Attempt {attempt}/{max_retries} failed: {error_msg}")

            # Check if this is a rate limit or auth error (YouTube only)
            if platform == "youtube" and refresher.needs_refresh(error_msg):
                if youtube_config.auto_refresh_cookies:
                    logger.info("Detected cookie/auth error, attempting refresh")
                    refreshed = await auto_refresh_cookies_if_needed(error_msg)

                    if refreshed:
                        # Wait before retry
                        await asyncio.sleep(10)
                        continue

                # If rate limited, wait longer
                if refresher.is_rate_limited(error_msg):
                    wait_time = refresher.get_wait_time_for_rate_limit(attempt)
                    logger.warning(f"Rate limited - waiting {wait_time}s before retry")
                    await asyncio.sleep(wait_time)
                    continue

            # Regular error - use exponential backoff
            if attempt < max_retries:
                backoff_time = base_backoff * (2 ** (attempt - 1))
                logger.info(f"Retrying in {backoff_time}s...")
                await asyncio.sleep(backoff_time)

    return None, f"Failed after {max_retries} attempts"


async def process_single_video(
    job_id: int,
    video_url: str,
    category_id: int | None,
    platform: str = "youtube",
) -> ProcessingResult:
    """
    Process a single video transcription.

    Args:
        job_id: The job ID for tracking
        video_url: Video URL
        category_id: Category to store in
        platform: "youtube" or "rumble"

    Returns:
        ProcessingResult with success/failure info
    """
    # Select platform-specific functions
    if platform == "rumble":
        get_video_info = get_rumble_video_info
        get_video_url = get_rumble_video_url
        source_type = "rumble_transcript"
        id_prefix = "rb"
    else:
        get_video_info = get_youtube_video_info
        get_video_url = get_youtube_video_url
        source_type = "youtube_transcript"
        id_prefix = "yt"

    try:
        # Get video info
        video_info = await get_video_info(video_url)
        if not video_info:
            return ProcessingResult(
                success=False,
                error_message="Could not get video info",
            )

        # Skip if already transcribed
        if await repository.video_exists(video_info.video_id, source_type):
            return ProcessingResult(
                success=True,
                skipped=1,
                error_message="Video already transcribed",
            )

        await repository.update_job(job_id, total_items=1, current_item=video_info.title)

        # Transcribe with retry
        youtube_config = config.youtube
        result, error_msg = await transcribe_with_retry(
            video_url,
            max_retries=youtube_config.max_retries,
            platform=platform,
            job_id=job_id,
        )

        if not result:
            return ProcessingResult(
                success=False,
                error_message=error_msg or "Transcription failed",
            )

        # Chunk the transcript
        chunks = chunk_text(result.text)

        if chunks:
            # Generate embeddings
            chunk_texts = [c.text for c in chunks]
            embeddings = await generate_embeddings(chunk_texts)

            # Store in vector database
            chunk_ids = [f"{id_prefix}_{result.video_id}_chunk_{i}" for i in range(len(chunks))]
            video_url_full = get_video_url(result.video_id)
            metadatas = [
                {
                    "job_id": job_id,
                    "video_id": result.video_id,
                    "chunk_index": c.index,
                    "title": video_info.title,
                    "channel_name": video_info.channel_name,
                    "published_date": video_info.upload_date,
                    "source_url": video_url_full,
                    "source_type": source_type,
                }
                for c in chunks
            ]

            add_documents(
                documents=chunk_texts,
                metadatas=metadatas,
                ids=chunk_ids,
                category_id=category_id,
                embeddings=embeddings,
            )

        # Create content item
        await repository.create_content_item(
            title=result.title,
            source_type=source_type,
            source_url=video_url,
            category_id=category_id,
            content_preview=extract_preview(result.text),
            word_count=result.word_count,
            chunk_count=len(chunks),
            chromadb_collection=get_collection_name(category_id),
            metadata={
                "video_id": result.video_id,
                "duration": result.duration,
                "language": result.language,
            },
        )

        # Update progress to show completion
        await repository.update_job(job_id, progress=1)

        return ProcessingResult(success=True, processed=1)

    except Exception as e:
        logger.error(f"Error processing video {video_url}: {e}")
        return ProcessingResult(success=False, error_message=str(e))


async def process_channel_videos(
    job_id: int,
    channel_url: str,
    category_id: int | None,
    limit: int | None = None,
    start_from: int = 0,
    platform: str = "youtube",
) -> ProcessingResult:
    """
    Process all videos from a channel.

    Args:
        job_id: The job ID for tracking
        channel_url: Channel URL
        category_id: Category to store in
        limit: Maximum number of videos to process (None = all)
        start_from: Index to start processing from (for resume)
        platform: "youtube" or "rumble"

    Returns:
        ProcessingResult with counts
    """
    # Select platform-specific functions
    if platform == "rumble":
        list_channel_videos = list_rumble_channel_videos
        get_video_url = get_rumble_video_url
        source_type = "rumble_transcript"
        id_prefix = "rb"
    else:
        list_channel_videos = list_youtube_channel_videos
        get_video_url = get_youtube_video_url
        source_type = "youtube_transcript"
        id_prefix = "yt"

    processed = 0
    skipped = 0
    failed = 0

    try:
        # Get videos
        videos = await list_channel_videos(channel_url, limit)

        if not videos:
            return ProcessingResult(
                success=False,
                error_message="No videos found",
            )

        await repository.update_job(job_id, total_items=len(videos))

        for i, video in enumerate(videos):
            # Skip videos before start_from (already processed in previous run)
            if i < start_from:
                continue

            # Check for pause signal before processing each video
            if await check_should_pause(job_id):
                logger.info(f"Job {job_id} paused at video {i}/{len(videos)}")
                return ProcessingResult(
                    success=True,
                    processed=processed,
                    skipped=skipped,
                    failed=failed,
                    paused=True,
                )

            video_url = get_video_url(video.video_id)
            await repository.update_job(
                job_id,
                progress=i,
                current_item=video.title,
            )

            # Skip if already transcribed (deduplication)
            if await repository.video_exists(video.video_id, source_type):
                skipped += 1
                logger.info(f"Skipping already transcribed video: {video.title}")
                continue

            # Add delay between downloads to avoid rate limiting
            youtube_config = config.youtube
            if i > start_from:  # Don't delay on first video
                await add_jitter_delay(youtube_config.download_delay)

            try:
                # Use retry-enabled transcription
                result, error_msg = await transcribe_with_retry(
                    video_url,
                    max_retries=youtube_config.max_retries,
                    platform=platform,
                    job_id=job_id,
                )

                if result:
                    chunks = chunk_text(result.text)

                    if chunks:
                        chunk_texts = [c.text for c in chunks]
                        embeddings = await generate_embeddings(chunk_texts)

                        chunk_ids = [f"{id_prefix}_{result.video_id}_chunk_{j}" for j in range(len(chunks))]
                        metadatas = [
                            {
                                "job_id": job_id,
                                "video_id": result.video_id,
                                "chunk_index": c.index,
                                "title": video.title,
                                "channel_name": video.channel_name,
                                "published_date": video.upload_date,
                                "source_url": video_url,
                                "source_type": source_type,
                            }
                            for c in chunks
                        ]

                        add_documents(
                            documents=chunk_texts,
                            metadatas=metadatas,
                            ids=chunk_ids,
                            category_id=category_id,
                            embeddings=embeddings,
                        )

                    await repository.create_content_item(
                        title=result.title,
                        source_type=source_type,
                        source_url=video_url,
                        category_id=category_id,
                        content_preview=extract_preview(result.text),
                        word_count=result.word_count,
                        chunk_count=len(chunks),
                        chromadb_collection=get_collection_name(category_id),
                        metadata={
                            "video_id": result.video_id,
                            "duration": result.duration,
                            "language": result.language,
                        },
                    )

                    processed += 1
                    logger.info(f"Processed video {i+1}/{len(videos)}: {video.title}")
                else:
                    failed += 1
                    logger.warning(f"Failed to transcribe video: {video.title} - {error_msg}")

            except Exception as e:
                failed += 1
                logger.error(f"Error processing video {video.title}: {e}")
                # Continue to next video after unexpected errors

        # Final progress update
        await repository.update_job(job_id, progress=len(videos))

        return ProcessingResult(
            success=True,
            processed=processed,
            skipped=skipped,
            failed=failed,
        )

    except Exception as e:
        logger.error(f"Error processing channel {channel_url}: {e}")
        return ProcessingResult(
            success=False,
            processed=processed,
            skipped=skipped,
            failed=failed,
            error_message=str(e),
        )


async def process_job(job_id: int) -> ProcessingResult:
    """
    Process a job based on its type.

    Called by the worker to process pending/running jobs.
    Handles single video and channel jobs for YouTube and Rumble.

    Args:
        job_id: The job ID to process

    Returns:
        ProcessingResult with success/failure info
    """
    job = await repository.get_job(job_id)
    if not job:
        return ProcessingResult(success=False, error_message="Job not found")

    job_type = job["job_type"]
    source_url = job["source_url"]
    category_id = job["category_id"]

    # For interrupted jobs, get the progress to resume from
    start_from = job.get("progress", 0) or 0

    logger.info(f"Processing job {job_id} (type={job_type}, start_from={start_from})")

    if job_type == "youtube_video":
        return await process_single_video(job_id, source_url, category_id, platform="youtube")

    elif job_type == "youtube_channel":
        return await process_channel_videos(
            job_id=job_id,
            channel_url=source_url,
            category_id=category_id,
            limit=None,
            start_from=start_from,
            platform="youtube",
        )

    elif job_type == "rumble_video":
        return await process_single_video(job_id, source_url, category_id, platform="rumble")

    elif job_type == "rumble_channel":
        return await process_channel_videos(
            job_id=job_id,
            channel_url=source_url,
            category_id=category_id,
            limit=None,
            start_from=start_from,
            platform="rumble",
        )

    else:
        return ProcessingResult(
            success=False,
            error_message=f"Unknown job type: {job_type}",
        )
