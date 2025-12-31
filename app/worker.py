#!/usr/bin/env python3
"""
Background Worker - Processes YouTube transcription jobs

This worker runs as a separate process from the FastAPI web server,
allowing the web server to remain responsive while Whisper
transcription runs in the background.

Usage:
    # In development (with .env.local)
    ENV_FILE=.env.local python -m app.worker

    # In production
    python -m app.worker

The worker:
1. Polls the database for pending or interrupted jobs
2. Claims and processes jobs one at a time
3. Handles graceful shutdown on SIGTERM/SIGINT
4. Automatically resumes interrupted jobs from their last progress
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime

# Add the project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv

env_file = os.environ.get("ENV_FILE", ".env")
load_dotenv(env_file)

from app.db import repository
from app.core.job_processor import process_job, ProcessingResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("worker")

# Worker state
_shutdown_requested = False
_current_job_id: int | None = None


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, requesting graceful shutdown...")
    _shutdown_requested = True

    if _current_job_id:
        logger.info(f"Current job {_current_job_id} will complete current video before stopping")


async def process_pending_job(job: dict) -> bool:
    """
    Process a single pending or interrupted job.

    Returns True if job was processed successfully.
    """
    global _current_job_id

    job_id = job["id"]
    job_type = job["job_type"]
    status = job["status"]
    progress = job.get("progress", 0) or 0

    logger.info(
        f"Processing job {job_id} (type={job_type}, status={status}, progress={progress})"
    )

    # Claim the job
    if not await repository.claim_job(job_id):
        logger.warning(f"Failed to claim job {job_id}, skipping")
        return False

    _current_job_id = job_id

    try:
        # Process the job
        result: ProcessingResult = await process_job(job_id)

        # Handle paused jobs - don't mark as completed
        if result.paused:
            logger.info(
                f"Job {job_id} paused: "
                f"processed={result.processed}, skipped={result.skipped}, failed={result.failed}"
            )
            return True  # Considered successful, just paused

        if result.success:
            await repository.complete_job(job_id)
            logger.info(
                f"Job {job_id} completed: "
                f"processed={result.processed}, skipped={result.skipped}, failed={result.failed}"
            )
        else:
            await repository.complete_job(job_id, error_message=result.error_message)
            logger.error(f"Job {job_id} failed: {result.error_message}")

        return result.success

    except Exception as e:
        logger.exception(f"Error processing job {job_id}: {e}")
        await repository.complete_job(job_id, error_message=str(e))
        return False

    finally:
        _current_job_id = None


async def check_job_paused(job_id: int) -> bool:
    """Check if a specific job has been paused."""
    job = await repository.get_job(job_id)
    return job and job.get("status") == "paused"


async def worker_loop(poll_interval: int = 5):
    """
    Main worker loop.

    Continuously polls for pending jobs and processes them.
    Respects global worker pause and individual job pause signals.

    Args:
        poll_interval: Seconds to wait between polls when no jobs found
    """
    logger.info("Worker started, polling for jobs...")

    while not _shutdown_requested:
        try:
            # Check if worker is globally paused
            if await repository.get_worker_paused():
                logger.debug("Worker is paused, waiting...")
                await asyncio.sleep(poll_interval)
                continue

            # Get pending or interrupted jobs (ordered by priority)
            jobs = await repository.get_pending_jobs()

            if jobs:
                job = jobs[0]  # Process one job at a time
                await process_pending_job(job)

                # Small delay between jobs to allow other operations
                await asyncio.sleep(0.5)
            else:
                # No jobs, wait before polling again
                logger.debug(f"No pending jobs, waiting {poll_interval}s...")
                await asyncio.sleep(poll_interval)

        except Exception as e:
            logger.exception(f"Error in worker loop: {e}")
            await asyncio.sleep(poll_interval)

    logger.info("Worker shutting down...")


def main():
    """Main entry point for the worker."""
    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("=" * 60)
    logger.info("Docling Knowledge Hub - Background Worker")
    logger.info("=" * 60)
    logger.info(f"Environment file: {env_file}")
    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    # Run the worker loop
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("Worker stopped by keyboard interrupt")
    except Exception as e:
        logger.exception(f"Worker crashed: {e}")
        sys.exit(1)

    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
