"""
Jobs API Routes - Job queue management
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import repository

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    """Response for a job."""
    id: int
    job_type: str
    status: str
    source_url: str | None
    source_path: str | None
    category_id: int | None
    progress: int
    total_items: int
    current_item: str | None
    error_message: str | None
    priority: int | None = 50
    started_at: str | None
    completed_at: str | None
    created_at: str


class WorkerStatusResponse(BaseModel):
    """Response for worker status."""
    paused: bool


class PriorityRequest(BaseModel):
    """Request to set job priority."""
    priority: int


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 50,
):
    """List jobs with optional filters."""
    jobs = await repository.get_jobs(
        status=status,
        job_type=job_type,
        limit=limit,
    )
    return jobs


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int):
    """Get a single job."""
    job = await repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: int):
    """Cancel a running job."""
    job = await repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] not in ["pending", "running", "paused"]:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")

    await repository.update_job(job_id, status="cancelled")
    return await repository.get_job(job_id)


@router.post("/{job_id}/pause", response_model=JobResponse)
async def pause_job(job_id: int):
    """Pause a running or pending job."""
    job = await repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail="Job cannot be paused")

    await repository.pause_job(job_id)
    return await repository.get_job(job_id)


@router.post("/{job_id}/resume", response_model=JobResponse)
async def resume_job(job_id: int):
    """Resume a paused job."""
    job = await repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "paused":
        raise HTTPException(status_code=400, detail="Job is not paused")

    await repository.resume_job(job_id)
    return await repository.get_job(job_id)


@router.post("/{job_id}/priority", response_model=JobResponse)
async def set_job_priority(job_id: int, request: PriorityRequest):
    """Set job priority (0-100, higher = more priority)."""
    job = await repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] not in ["pending", "paused"]:
        raise HTTPException(status_code=400, detail="Can only change priority of pending/paused jobs")

    priority = max(0, min(100, request.priority))
    await repository.update_job(job_id, priority=priority)
    return await repository.get_job(job_id)


# Worker control endpoints
worker_router = APIRouter(prefix="/api/worker", tags=["worker"])


@worker_router.get("/status", response_model=WorkerStatusResponse)
async def get_worker_status():
    """Get the current worker status."""
    paused = await repository.get_worker_paused()
    return {"paused": paused}


@worker_router.post("/pause", response_model=WorkerStatusResponse)
async def pause_worker():
    """Pause the worker globally."""
    await repository.set_worker_paused(True)
    return {"paused": True}


@worker_router.post("/resume", response_model=WorkerStatusResponse)
async def resume_worker():
    """Resume the worker globally."""
    await repository.set_worker_paused(False)
    return {"paused": False}
