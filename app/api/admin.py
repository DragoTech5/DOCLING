"""
Admin API Routes for Analytics Dashboard.
All endpoints require enterprise tier access.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.db.analytics_repository import analytics_repo
from app.db import telegram_repository as tg_repo
from app.middleware.telegram_auth import (
    TelegramUser,
    require_telegram_tier,
)
from pydantic import BaseModel

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


# ============================================================================
# Affiliate Program Management Endpoints (Enterprise Only)
# ============================================================================


class AffiliateApprovalRequest(BaseModel):
    """Request model for approving an affiliate"""
    notes: Optional[str] = None


class AffiliateRejectionRequest(BaseModel):
    """Request model for rejecting an affiliate"""
    reason: str


@router.get("/affiliates/pending")
async def get_pending_affiliates(
    _user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Get all pending affiliate applications for admin review.
    Returns: Array of affiliate channels with status='pending_review'.
    """
    try:
        channels = await tg_repo.get_pending_affiliate_channels()
        return {
            "data": channels,
            "count": len(channels),
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


@router.post("/affiliates/{affiliate_channel_id}/approve")
async def approve_affiliate(
    affiliate_channel_id: int,
    request: AffiliateApprovalRequest,
    user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Approve an affiliate channel and generate referral code.
    Returns: Affiliate record and generated referral code.
    """
    try:
        # Generate unique referral code
        referral_code = f"REF{secrets.token_hex(4).upper()}"

        # Approve affiliate
        success = await tg_repo.approve_affiliate_channel(
            affiliate_channel_id=affiliate_channel_id,
            admin_telegram_id=user.telegram_id,
            referral_code=referral_code,
        )

        if success:
            # Get updated affiliate record
            from app.config import get_bot_token, BOT_API
            import httpx

            affiliate = await tg_repo.get_affiliate_channel_by_user(
                (await tg_repo.db.execute(
                    "SELECT telegram_user_id FROM affiliate_channels WHERE id = ?",
                    (affiliate_channel_id,)
                )).fetchone()[0] if False else None
            )

            # Notify affiliate
            try:
                from app.api.telegram import send_bot_message
                channel_record = await tg_repo.db.execute(
                    "SELECT telegram_user_id, channel_title FROM affiliate_channels WHERE id = ?",
                    (affiliate_channel_id,)
                )
                row = await channel_record.fetchone()
                if row:
                    telegram_user_id, channel_title = row
                    referral_url = f"https://t.me/AkashaAIHub_bot?start=ref_{referral_code}"
                    # Can't call send_bot_message here, would need to import properly
                    # For now, just log the approval
            except:
                pass

            return {
                "success": True,
                "referral_code": referral_code,
                "affiliate_id": affiliate_channel_id,
            }
        else:
            return {"success": False, "error": "Failed to approve affiliate"}

    except Exception as e:
        return {"error": str(e), "status": "error"}


@router.post("/affiliates/{affiliate_channel_id}/reject")
async def reject_affiliate(
    affiliate_channel_id: int,
    request: AffiliateRejectionRequest,
    user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Reject an affiliate channel application.
    Returns: Success status.
    """
    try:
        success = await tg_repo.reject_affiliate_channel(
            affiliate_channel_id=affiliate_channel_id,
            admin_telegram_id=user.telegram_id,
            reason=request.reason,
        )

        return {
            "success": success,
            "affiliate_id": affiliate_channel_id,
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


@router.post("/affiliates/create-invite")
async def create_affiliate_invite(
    expires_days: Annotated[int, Query(ge=1, le=365)] = 30,
    _user: Annotated[TelegramUser, Depends(require_telegram_tier("enterprise"))] = None,
):
    """
    Generate a new affiliate invite link.
    Returns: Invite URL and expiration date.
    """
    try:
        from datetime import datetime, timedelta

        token = secrets.token_urlsafe(16)
        expires_at = (datetime.utcnow() + timedelta(days=expires_days)).isoformat()

        await tg_repo.create_affiliate_invite(token, expires_at)

        invite_url = f"https://t.me/AkashaAIHub_bot?start=aff_{token}"
        return {
            "invite_url": invite_url,
            "token": token,
            "expires_at": expires_at,
            "expires_days": expires_days,
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}
