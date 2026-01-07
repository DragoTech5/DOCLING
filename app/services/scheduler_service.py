"""
Scheduler Service - Channel monitoring with APScheduler
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.config import config
from app.db import repository
from app.db.vector_store import add_documents, get_collection_name
from app.core.youtube_processor import list_channel_videos, transcribe_video, get_video_url
from app.core.embeddings import chunk_text, generate_embeddings
from app.core.docling_processor import extract_preview

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler instance."""
    global _scheduler

    if _scheduler is None:
        _scheduler = AsyncIOScheduler()

    return _scheduler


async def check_channel_for_new_videos(channel_id: int) -> None:
    """
    Check a monitored channel for new videos and transcribe them.

    Args:
        channel_id: Database ID of the monitored channel
    """
    try:
        # Get channel info
        channel = await repository.get_monitored_channel(channel_id)
        if not channel or not channel["is_active"]:
            return

        logger.info(f"Checking channel: {channel['channel_name']}")

        # Get videos since last check
        videos = await list_channel_videos(
            channel["channel_url"],
            limit=10,  # Check last 10 videos
            after_video_id=channel["last_video_id"],
        )

        if not videos:
            logger.info(f"No new videos for {channel['channel_name']}")
            await repository.update_monitored_channel(
                channel_id,
                last_checked_at=datetime.now().isoformat(),
            )
            return

        # Create job for processing
        job_id = await repository.create_job(
            job_type="youtube_channel_check",
            source_url=channel["channel_url"],
            category_id=channel["category_id"],
            total_items=len(videos),
        )

        await repository.start_job(job_id)

        # Process each new video
        processed = 0
        skipped = 0
        for i, video in enumerate(videos):
            video_url = get_video_url(video.video_id)

            try:
                await repository.update_job(
                    job_id,
                    progress=i,
                    current_item=video.title,
                )

                # Skip if already transcribed (deduplication)
                if await repository.video_exists(video.video_id):
                    logger.info(f"Skipping already transcribed video: {video.title}")
                    skipped += 1
                    continue

                result = await transcribe_video(video_url)

                if result:
                    # Chunk and embed
                    chunks = chunk_text(result.text)

                    if chunks:
                        chunk_texts = [c.text for c in chunks]
                        embeddings = await generate_embeddings(chunk_texts)

                        chunk_ids = [
                            f"yt_{result.video_id}_chunk_{j}"
                            for j in range(len(chunks))
                        ]
                        metadatas = [
                            {
                                "job_id": job_id,
                                "video_id": result.video_id,
                                "chunk_index": c.index,
                                "title": result.title,
                                "channel": channel["channel_name"],
                            }
                            for c in chunks
                        ]

                        add_documents(
                            documents=chunk_texts,
                            metadatas=metadatas,
                            ids=chunk_ids,
                            category_id=channel["category_id"],
                            embeddings=embeddings,
                        )

                    # Create content item
                    await repository.create_content_item(
                        title=result.title,
                        source_type="youtube_transcript",
                        source_url=video_url,
                        category_id=channel["category_id"],
                        content_preview=extract_preview(result.text),
                        word_count=result.word_count,
                        chunk_count=len(chunks),
                        chromadb_collection=get_collection_name(channel["category_id"]),
                        metadata={
                            "video_id": result.video_id,
                            "duration": result.duration,
                            "language": result.language,
                        },
                    )

                    processed += 1

            except Exception as e:
                logger.error(f"Error processing video {video.video_id}: {e}")
                continue

        # Update channel with latest video
        latest_video_id = videos[0].video_id if videos else channel["last_video_id"]
        await repository.update_monitored_channel(
            channel_id,
            last_checked_at=datetime.now().isoformat(),
            last_video_id=latest_video_id,
            video_count=channel["video_count"] + processed,
        )

        await repository.update_job(job_id, progress=len(videos))
        await repository.complete_job(job_id)

        logger.info(
            f"Channel check complete for {channel['channel_name']}: "
            f"processed={processed}, skipped={skipped}, total_checked={len(videos)}"
        )

    except Exception as e:
        logger.error(f"Error checking channel {channel_id}: {e}")


async def reset_daily_queries() -> None:
    """
    Reset daily query quotas for all users at UTC midnight.

    This job runs every day at 00:00 UTC and resets queries_remaining
    to the daily limit for each user's subscription tier.
    """
    try:
        import aiosqlite
        from app.db.models import TIER_LIMITS, get_db_path

        logger.info("Starting daily query quota reset...")

        async with aiosqlite.connect(get_db_path()) as db:
            # Get all active users
            cursor = await db.execute(
                "SELECT id, telegram_id, tier FROM telegram_users WHERE tier != 'enterprise'"
            )
            users = await cursor.fetchall()

            reset_count = 0
            for user_id, telegram_id, tier in users:
                tier_limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
                daily_limit = tier_limits.get("daily_queries")

                # Only reset if tier has defined daily limits (not unlimited)
                if daily_limit is not None:
                    await db.execute(
                        "UPDATE telegram_users SET queries_remaining = ? WHERE id = ?",
                        (daily_limit, user_id)
                    )
                    reset_count += 1

            await db.commit()
            logger.info(f"Daily query reset complete: {reset_count} users updated")

    except Exception as e:
        logger.error(f"Error resetting daily queries: {e}")


async def check_all_channels() -> None:
    """Check all active monitored channels for new videos."""
    if not config.scheduler.enabled:
        return

    logger.info("Running scheduled channel check...")

    try:
        channels = await repository.get_monitored_channels(active_only=True)

        for channel in channels:
            # Run channel checks with some delay between them
            await check_channel_for_new_videos(channel["id"])
            await asyncio.sleep(5)  # 5 second delay between channels

    except Exception as e:
        logger.error(f"Error in scheduled channel check: {e}")


def start_scheduler() -> None:
    """Start the background scheduler."""
    if not config.scheduler.enabled:
        logger.info("Scheduler is disabled")
        return

    scheduler = get_scheduler()

    # Add daily query reset job (runs at 00:00 UTC every day)
    scheduler.add_job(
        reset_daily_queries,
        trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
        id="reset_daily_queries",
        name="Reset daily query quotas",
        replace_existing=True,
    )

    # Add the channel check job
    scheduler.add_job(
        check_all_channels,
        trigger=IntervalTrigger(hours=config.scheduler.check_interval_hours),
        id="check_channels",
        name="Check monitored YouTube channels",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        f"Scheduler started - reset_daily_queries at 00:00 UTC, "
        f"checking channels every {config.scheduler.check_interval_hours} hours"
    )


def stop_scheduler() -> None:
    """Stop the background scheduler."""
    scheduler = get_scheduler()

    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


async def trigger_channel_check(channel_id: int | None = None) -> None:
    """
    Manually trigger a channel check.

    Args:
        channel_id: Specific channel to check, or None for all
    """
    if channel_id:
        await check_channel_for_new_videos(channel_id)
    else:
        await check_all_channels()
