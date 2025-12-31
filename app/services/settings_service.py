"""
Settings Service - Manage application settings with persistence
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, Field

from app.config import (
    config,
    DoclingConfig,
    ChunkingConfig,
    WhisperConfig,
    EmbeddingConfig,
    SchedulerConfig,
)
from app.db.repository import get_settings, get_setting, set_setting


# Pydantic schemas for API validation
class DoclingSettings(BaseModel):
    """Docling processing settings."""
    pdf_pipeline: Literal["standard", "vlm", "layout"] = Field(
        default="standard",
        description="PDF processing pipeline type"
    )
    ocr_enabled: bool = Field(default=True, description="Enable OCR for scanned documents")
    ocr_engine: Literal["easyocr", "tesseract", "tesseract_cli"] = Field(
        default="easyocr",
        description="OCR engine to use"
    )
    ocr_lang: list[str] = Field(default=["en"], description="Languages for OCR")
    accelerator: Literal["cpu", "cuda", "mps", "auto"] = Field(
        default="auto",
        description="Hardware accelerator"
    )
    vlm_enabled: bool = Field(default=False, description="Enable Vision Language Model")
    vlm_model: Literal["granite-docling", "smoldocling"] = Field(
        default="granite-docling",
        description="VLM model to use"
    )
    table_structure_enabled: bool = Field(default=True, description="Detect table structure")
    images_scale: float = Field(default=1.0, ge=0.1, le=4.0, description="Image scale factor")
    generate_page_images: bool = Field(default=False, description="Generate page images")
    generate_picture_images: bool = Field(default=False, description="Generate picture images")


class ChunkingSettings(BaseModel):
    """Text chunking settings."""
    strategy: Literal["fixed", "semantic", "paragraph"] = Field(
        default="paragraph",
        description="Chunking strategy"
    )
    chunk_size: int = Field(default=1000, ge=100, le=10000, description="Target chunk size")
    chunk_overlap: int = Field(default=200, ge=0, le=1000, description="Overlap between chunks")
    min_chunk_size: int = Field(default=100, ge=10, le=500, description="Minimum chunk size")


class WhisperSettings(BaseModel):
    """Whisper transcription settings."""
    model_size: Literal["tiny", "base", "small", "medium", "large", "turbo"] = Field(
        default="base",
        description="Whisper model size"
    )
    language: str | None = Field(default=None, description="Language code or None for auto")
    device: Literal["cpu", "cuda", "auto"] = Field(default="auto", description="Device to use")
    compute_type: Literal["int8", "float16", "float32"] = Field(
        default="float16",
        description="Compute precision"
    )


class EmbeddingSettings(BaseModel):
    """Embedding model settings."""
    model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence transformer model name"
    )
    device: Literal["cpu", "cuda", "auto"] = Field(default="auto", description="Device to use")


class SchedulerSettings(BaseModel):
    """Channel monitoring scheduler settings."""
    check_interval_hours: int = Field(
        default=48,
        ge=1,
        le=168,
        description="Hours between channel checks"
    )
    max_concurrent_jobs: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Maximum concurrent jobs"
    )
    enabled: bool = Field(default=True, description="Enable scheduler")


class AllSettings(BaseModel):
    """All application settings."""
    docling: DoclingSettings = Field(default_factory=DoclingSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    whisper: WhisperSettings = Field(default_factory=WhisperSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)


# Settings categories mapping
SETTINGS_CATEGORIES = {
    "docling": DoclingSettings,
    "chunking": ChunkingSettings,
    "whisper": WhisperSettings,
    "embedding": EmbeddingSettings,
    "scheduler": SchedulerSettings,
}


def _config_to_dict(cfg: Any) -> dict[str, Any]:
    """Convert a dataclass config to dict."""
    result = {}
    for field in fields(cfg):
        value = getattr(cfg, field.name)
        if isinstance(value, list):
            result[field.name] = value
        else:
            result[field.name] = value
    return result


def _apply_settings_to_config(category: str, settings: dict[str, Any]) -> None:
    """Apply settings to the global config object."""
    if category == "docling":
        for key, value in settings.items():
            if hasattr(config.docling, key):
                setattr(config.docling, key, value)
    elif category == "chunking":
        for key, value in settings.items():
            if hasattr(config.chunking, key):
                setattr(config.chunking, key, value)
    elif category == "whisper":
        for key, value in settings.items():
            if hasattr(config.whisper, key):
                setattr(config.whisper, key, value)
    elif category == "embedding":
        for key, value in settings.items():
            if hasattr(config.embedding, key):
                setattr(config.embedding, key, value)
    elif category == "scheduler":
        for key, value in settings.items():
            if hasattr(config.scheduler, key):
                setattr(config.scheduler, key, value)


async def get_all_settings() -> AllSettings:
    """Get all settings, merging database values with defaults."""
    settings = AllSettings()

    # Load from database
    db_settings = await get_settings()

    # Group by category
    by_category: dict[str, dict[str, str]] = {}
    for setting in db_settings:
        cat = setting["category"]
        if cat not in by_category:
            by_category[cat] = {}
        by_category[cat][setting["key"]] = setting["value"]

    # Apply database values
    for category, values in by_category.items():
        if category in SETTINGS_CATEGORIES:
            schema = SETTINGS_CATEGORIES[category]
            current = getattr(settings, category)

            for key, value_str in values.items():
                if hasattr(current, key):
                    # Parse JSON value
                    try:
                        value = json.loads(value_str)
                        setattr(current, key, value)
                    except (json.JSONDecodeError, TypeError):
                        setattr(current, key, value_str)

    return settings


async def get_category_settings(category: str) -> BaseModel | None:
    """Get settings for a specific category."""
    if category not in SETTINGS_CATEGORIES:
        return None

    all_settings = await get_all_settings()
    return getattr(all_settings, category)


async def update_settings(category: str, updates: dict[str, Any]) -> bool:
    """
    Update settings for a category.

    Args:
        category: Settings category (docling, chunking, whisper, embedding, scheduler)
        updates: Dictionary of settings to update

    Returns:
        True if successful
    """
    if category not in SETTINGS_CATEGORIES:
        return False

    schema = SETTINGS_CATEGORIES[category]

    # Validate using Pydantic
    try:
        # Get current settings and merge with updates
        current = await get_category_settings(category)
        current_dict = current.model_dump() if current else {}
        current_dict.update(updates)

        # Validate merged settings
        validated = schema(**current_dict)

        # Save each setting to database
        for key, value in validated.model_dump().items():
            value_str = json.dumps(value)
            await set_setting(f"{category}.{key}", value_str, category)

        # Apply to runtime config
        _apply_settings_to_config(category, validated.model_dump())

        return True

    except Exception:
        return False


async def update_setting(key: str, value: Any) -> bool:
    """
    Update a single setting.

    Args:
        key: Full setting key (e.g., "docling.ocr_enabled")
        value: New value

    Returns:
        True if successful
    """
    parts = key.split(".", 1)
    if len(parts) != 2:
        return False

    category, setting_name = parts
    return await update_settings(category, {setting_name: value})


async def reset_settings(category: str | None = None) -> bool:
    """
    Reset settings to defaults.

    Args:
        category: Category to reset, or None for all

    Returns:
        True if successful
    """
    from app.db.repository import delete_setting

    if category:
        if category not in SETTINGS_CATEGORIES:
            return False

        # Delete all settings in this category
        db_settings = await get_settings(category)
        for setting in db_settings:
            await delete_setting(f"{category}.{setting['key']}")

        # Reset runtime config
        default = SETTINGS_CATEGORIES[category]()
        _apply_settings_to_config(category, default.model_dump())
    else:
        # Reset all categories
        for cat in SETTINGS_CATEGORIES:
            await reset_settings(cat)

    return True


async def initialize_default_settings() -> None:
    """Initialize database with default settings if not present."""
    # Check if any settings exist
    existing = await get_settings()

    if not existing:
        # Save all default settings
        defaults = AllSettings()

        for category in SETTINGS_CATEGORIES:
            settings = getattr(defaults, category)
            for key, value in settings.model_dump().items():
                value_str = json.dumps(value)
                await set_setting(f"{category}.{key}", value_str, category)


async def load_settings_to_config() -> None:
    """Load settings from database into runtime config."""
    all_settings = await get_all_settings()

    for category in SETTINGS_CATEGORIES:
        settings = getattr(all_settings, category)
        _apply_settings_to_config(category, settings.model_dump())
