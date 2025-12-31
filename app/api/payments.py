"""
Dodo Payments API endpoints.
Handles checkout session creation and webhook processing for credit card payments.
"""

import os
import json
import logging
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, Request, HTTPException, Header

from app.services.dodo_service import dodo_service
from app.db.telegram_repository import (
    create_dodo_payment_record,
    complete_dodo_payment,
    get_dodo_payment_by_session,
    get_telegram_user_by_id,
    update_telegram_user_tier,
    create_subscription,
)
from app.middleware.telegram_auth import TelegramUser, get_current_telegram_user
from app.db.models import TIER_LIMITS, get_db_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments/dodo", tags=["payments"])


@router.post("/create-checkout")
async def create_dodo_checkout(
    tier: str,
    user: Annotated[TelegramUser, Depends(get_current_telegram_user)],
):
    """
    Create Dodo checkout session for Researcher or Unlimited tier.

    Returns checkout URL for user to complete payment.
    Scholar tier should use Telegram Stars instead.

    Query Parameters:
        tier: Subscription tier (researcher or unlimited)

    Returns:
        {
            "checkout_url": "https://checkout.dodopayments.com/...",
            "expires_at": "ISO-8601 timestamp",
            "tier": "researcher",
            "amount_usd": 39.00
        }
    """
    # Validate tier
    if tier not in ["researcher", "unlimited"]:
        raise HTTPException(
            status_code=400, detail="Dodo payments only for Researcher/Unlimited tiers"
        )

    tier_config = TIER_LIMITS.get(tier)
    if not tier_config:
        raise HTTPException(status_code=400, detail="Invalid tier")

    if tier_config.get("payment_method") != "dodo":
        raise HTTPException(
            status_code=400,
            detail=f"Tier {tier} should use {tier_config['payment_method']} payment",
        )

    amount_usd = tier_config["price_usd"]  # In cents

    # Create checkout session via Dodo API
    try:
        app_url = os.getenv("APP_URL", "http://localhost:8200")

        session = await dodo_service.create_checkout_session(
            tier=tier,
            amount_usd=amount_usd,
            customer_email=user.email or f"{user.telegram_id}@telegram.user",
            telegram_user_id=user.db_record["id"],
            return_url_success=f"{app_url}/twa/payment-success?tier={tier}",
            return_url_failure=f"{app_url}/twa/payment-failure",
        )
    except Exception as e:
        logger.error(f"Dodo checkout creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Payment provider error: {str(e)}")

    # Store pending payment record
    await create_dodo_payment_record(
        telegram_user_id=user.db_record["id"],
        checkout_session_id=session["checkout_session_id"],
        tier=tier,
        amount_usd=amount_usd,
        expires_at=session["expires_at"],
        customer_email=user.email,
    )

    return {
        "checkout_url": session["checkout_url"],
        "expires_at": session["expires_at"],
        "tier": tier,
        "amount_usd": amount_usd / 100,  # Convert to dollars for display
    }


@router.post("/webhook")
async def handle_dodo_webhook(
    request: Request,
    webhook_id: Annotated[str, Header(alias="webhook-id")],
    webhook_signature: Annotated[str, Header(alias="webhook-signature")],
    webhook_timestamp: Annotated[str, Header(alias="webhook-timestamp")],
):
    """
    Dodo webhook handler for payment events.

    Critical: Must verify HMAC signature for security.
    Events: payment.completed, payment.failed, payment.refunded

    Headers:
        webhook-id: Unique event identifier
        webhook-signature: HMAC SHA256 signature
        webhook-timestamp: Unix timestamp

    Returns:
        {"status": "received"}
    """
    # Read raw body for signature verification
    body = await request.body()
    body_str = body.decode()

    # Verify webhook signature (critical security check)
    if not dodo_service.verify_webhook_signature(
        webhook_id, webhook_timestamp, body_str, webhook_signature
    ):
        logger.warning(f"Invalid Dodo webhook signature: {webhook_id}")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse event data
    try:
        event = json.loads(body_str)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in webhook: {webhook_id}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type")
    logger.info(f"Dodo webhook received: {event_type} (ID: {webhook_id})")

    # Handle payment success events (DODO sends "payment.succeeded")
    if event_type in ["payment.completed", "payment.succeeded"]:
        await _handle_payment_completed(event)

    # Handle payment.failed event
    elif event_type == "payment.failed":
        await _handle_payment_failed(event)

    # Handle payment.cancelled event (optional - for tracking)
    elif event_type == "payment.cancelled":
        logger.info(f"Payment cancelled: {event.get('data', {}).get('checkoutSessionId')}")

    # Acknowledge receipt
    return {"status": "received"}


async def _handle_payment_completed(event: dict) -> None:
    """Handle payment.completed webhook event."""
    try:
        payment_data = event.get("data", {})
        checkout_session_id = payment_data.get("checkoutSessionId")
        payment_id = payment_data.get("id")
        amount = payment_data.get("amount")
        customer_id = payment_data.get("customerId")
        payment_method = payment_data.get("paymentMethod")
        metadata = payment_data.get("metadata", {})

        if not checkout_session_id or not payment_id:
            logger.error("Missing required fields in payment.completed event")
            return

        # Update Dodo payment record
        payment_record = await complete_dodo_payment(
            checkout_session_id=checkout_session_id,
            payment_id=payment_id,
            payment_method=payment_method or "unknown",
            customer_id=customer_id or "",
        )

        if not payment_record:
            logger.error(f"Payment record not found for session: {checkout_session_id}")
            return

        # Activate subscription
        telegram_user_id = payment_record.get("telegram_user_id")
        tier = payment_record.get("tier")

        if not telegram_user_id or not tier:
            logger.error(f"Missing user or tier in payment record: {payment_record}")
            return

        # Update user tier
        await update_telegram_user_tier(telegram_user_id=telegram_user_id, tier=tier)

        # Create subscription
        from datetime import datetime, timedelta
        ends_at = (datetime.now() + timedelta(days=30)).isoformat()  # 30-day subscription
        await create_subscription(
            telegram_user_id=telegram_user_id,
            tier=tier,
            telegram_payment_charge_id=payment_id,
            ends_at=ends_at,
        )

        # Track analytics (fire-and-forget)
        try:
            from app.services.analytics_service import analytics_service

            user = await get_telegram_user_by_id(telegram_user_id)
            if user:
                await analytics_service.track_subscription_purchase(
                    telegram_user=user,
                    tier=tier,
                    amount_stars=0,  # Dodo payment, not Stars
                    session_id=None,
                )
        except Exception as e:
            logger.error(f"Analytics tracking failed (non-critical): {e}")

        logger.info(f"✅ Dodo payment completed: User {telegram_user_id} → {tier}")

    except Exception as e:
        logger.error(f"Error handling payment.completed: {e}", exc_info=True)


async def _handle_payment_failed(event: dict) -> None:
    """Handle payment.failed webhook event."""
    try:
        payment_data = event.get("data", {})
        checkout_session_id = payment_data.get("checkoutSessionId")
        error_code = payment_data.get("errorCode")
        error_message = payment_data.get("errorMessage")

        if not checkout_session_id:
            logger.error("Missing checkoutSessionId in payment.failed event")
            return

        # Mark payment as failed in database
        async with aiosqlite.connect(get_db_path()) as db:
            await db.execute(
                """
                UPDATE dodo_payments
                SET status = 'failed', error_code = ?, error_message = ?
                WHERE checkout_session_id = ?
                """,
                (error_code, error_message, checkout_session_id),
            )
            await db.commit()

        logger.warning(
            f"❌ Dodo payment failed: {checkout_session_id} - {error_code}: {error_message}"
        )

    except Exception as e:
        logger.error(f"Error handling payment.failed: {e}", exc_info=True)
