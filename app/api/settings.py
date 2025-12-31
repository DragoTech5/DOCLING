"""
Settings API Routes
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.settings_service import (
    get_all_settings,
    get_category_settings,
    update_settings,
    reset_settings,
    AllSettings,
    DoclingSettings,
    ChunkingSettings,
    WhisperSettings,
    EmbeddingSettings,
    SchedulerSettings,
    SETTINGS_CATEGORIES,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdateRequest(BaseModel):
    """Request to update settings."""
    settings: dict[str, Any]


class SettingsResponse(BaseModel):
    """Response with settings."""
    success: bool
    message: str


@router.get("", response_model=AllSettings)
async def get_settings():
    """Get all application settings."""
    return await get_all_settings()


@router.get("/docling", response_model=DoclingSettings)
async def get_docling_settings():
    """Get Docling processing settings."""
    return await get_category_settings("docling")


@router.put("/docling", response_model=SettingsResponse)
async def update_docling_settings(data: DoclingSettings):
    """Update Docling settings."""
    success = await update_settings("docling", data.model_dump(exclude_unset=True))
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update settings")
    return SettingsResponse(success=True, message="Settings updated")


@router.get("/chunking", response_model=ChunkingSettings)
async def get_chunking_settings():
    """Get chunking settings."""
    return await get_category_settings("chunking")


@router.put("/chunking", response_model=SettingsResponse)
async def update_chunking_settings(data: ChunkingSettings):
    """Update chunking settings."""
    success = await update_settings("chunking", data.model_dump(exclude_unset=True))
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update settings")
    return SettingsResponse(success=True, message="Settings updated")


@router.get("/whisper", response_model=WhisperSettings)
async def get_whisper_settings():
    """Get Whisper transcription settings."""
    return await get_category_settings("whisper")


@router.put("/whisper", response_model=SettingsResponse)
async def update_whisper_settings(data: WhisperSettings):
    """Update Whisper settings."""
    success = await update_settings("whisper", data.model_dump(exclude_unset=True))
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update settings")
    return SettingsResponse(success=True, message="Settings updated")


@router.get("/embedding", response_model=EmbeddingSettings)
async def get_embedding_settings():
    """Get embedding settings."""
    return await get_category_settings("embedding")


@router.put("/embedding", response_model=SettingsResponse)
async def update_embedding_settings(data: EmbeddingSettings):
    """Update embedding settings."""
    success = await update_settings("embedding", data.model_dump(exclude_unset=True))
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update settings")
    return SettingsResponse(success=True, message="Settings updated")


@router.get("/scheduler", response_model=SchedulerSettings)
async def get_scheduler_settings():
    """Get scheduler settings."""
    return await get_category_settings("scheduler")


@router.put("/scheduler", response_model=SettingsResponse)
async def update_scheduler_settings(data: SchedulerSettings):
    """Update scheduler settings."""
    success = await update_settings("scheduler", data.model_dump(exclude_unset=True))
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update settings")
    return SettingsResponse(success=True, message="Settings updated")


@router.post("/reset", response_model=SettingsResponse)
async def reset_all_settings(category: str | None = None):
    """Reset settings to defaults."""
    if category and category not in SETTINGS_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")

    success = await reset_settings(category)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to reset settings")

    return SettingsResponse(
        success=True,
        message=f"Settings reset for {category or 'all categories'}",
    )
