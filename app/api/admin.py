"""
Admin API Routes for Analytics Dashboard.
All endpoints require enterprise tier access.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.db.analytics_repository import analytics_repo
from app.middleware.telegram_auth import (
    TelegramUser,
    require_telegram_tier,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================================================================
# Admin Dashboard Endpoints (Enterprise Only)
# ============================================================================


@router.get("/overview")
async def get_overview(
    _user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Get overview statistics for the admin dashboard.
    Returns: Total users, MRR, active users, queries today with percentage changes.
    """
    try:
        stats = await analytics_repo.get_overview_stats()
        return stats
    except Exception as e:
        return {"error": str(e), "status": "error"}


@router.get("/revenue")
async def get_revenue(
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    _user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Get daily revenue breakdown for the last N days.
    Returns: Array of daily revenue data with new subscriptions and renewals.
    """
    try:
        timeline = await analytics_repo.get_revenue_timeline(days)
        return {
            "data": timeline,
            "days": days,
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


@router.get("/tier-distribution")
async def get_tier_distribution(
    _user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Get user count breakdown by subscription tier.
    Returns: Array with tier, count, and percentage for each tier.
    """
    try:
        distribution = await analytics_repo.get_tier_distribution()
        return {
            "data": distribution,
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


@router.get("/conversion-funnel")
async def get_conversion_funnel(
    _user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Get conversion funnel stages with counts and conversion rates.
    Returns: Array of funnel stages (Signups, First Query, Paid Users).
    """
    try:
        funnel = await analytics_repo.get_conversion_funnel()
        return {
            "data": funnel,
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


@router.get("/usage-by-tier")
async def get_usage_by_tier(
    _user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Get query volume breakdown by subscription tier.
    Returns: Array with tier and query count for each tier.
    """
    try:
        usage = await analytics_repo.get_usage_by_tier()
        return {
            "data": usage,
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


@router.get("/users")
async def get_users(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str, Query()] = "",
    tier: Annotated[str, Query()] = "",
    sort: Annotated[str, Query()] = "created",
    _user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Get paginated list of users with optional filtering and sorting.

    Query Parameters:
    - page: Page number (default 1)
    - per_page: Items per page (default 20, max 100)
    - search: Search by name, username, or telegram_id
    - tier: Filter by tier (free, starter, pro, unlimited, enterprise)
    - sort: Sort column (created, tier, queries_used, etc.)

    Returns: Array of users with pagination metadata.
    """
    try:
        result = await analytics_repo.get_users_paginated(page, per_page, search, tier, sort)
        return result
    except Exception as e:
        return {"error": str(e), "status": "error"}


@router.get("/users/{telegram_id}/history")
async def get_user_history(
    telegram_id: int,
    _user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Get detailed history for a specific user.
    Returns: User info and recent events/queries.
    """
    try:
        history = await analytics_repo.get_user_history(telegram_id)
        return history
    except Exception as e:
        return {"error": str(e), "status": "error"}
