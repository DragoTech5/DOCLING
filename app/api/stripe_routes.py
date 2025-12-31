"""
Stripe Payment API Endpoints

Provides endpoints for subscription management and webhook handling.
"""

from typing import Optional, Literal
from fastapi import APIRouter, Request, HTTPException, status, Depends, Header
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.config import config
from app.lib.stripe_client import (
    create_checkout_session,
    create_customer_portal_session,
    construct_webhook_event,
    get_tier_from_price_id,
    get_customer_by_email,
    PRICING,
    format_price,
)
from app.lib.supabase_client import (
    upsert_subscription,
    update_user_tier,
    get_supabase_admin_client,
)
from app.middleware.auth import get_current_user, User

router = APIRouter(tags=["Payments"])


class CheckoutRequest(BaseModel):
    """Request body for creating checkout session."""
    tier: Literal["pro", "enterprise"]
    period: Literal["monthly", "yearly"]


class CheckoutResponse(BaseModel):
    """Response for checkout session creation."""
    url: str


class PortalResponse(BaseModel):
    """Response for customer portal session."""
    url: str


@router.post("/api/stripe/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: Request,
    data: CheckoutRequest,
    user: User = Depends(get_current_user)
):
    """
    Create a Stripe Checkout session for subscription purchase.

    Requires authentication. Creates a new subscription for the logged-in user.
    """
    if not config.stripe.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment processing is not configured"
        )

    # Check if user already has an active subscription
    existing_customer = await get_customer_by_email(user.email)

    origin = request.headers.get("origin", "http://localhost:8200")
    success_url = f"{origin}/dashboard?checkout=success"
    cancel_url = f"{origin}/pricing?checkout=cancelled"

    session = await create_checkout_session(
        customer_email=user.email,
        tier=data.tier,
        period=data.period,
        success_url=success_url,
        cancel_url=cancel_url,
        customer_id=existing_customer.id if existing_customer else None,
        metadata={
            "user_id": user.id,
            "tier": data.tier,
            "period": data.period,
        }
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )

    return CheckoutResponse(url=session.url)


@router.post("/api/stripe/portal", response_model=PortalResponse)
async def create_portal(
    request: Request,
    user: User = Depends(get_current_user)
):
    """
    Create a Stripe Customer Portal session for subscription management.

    Allows users to manage their subscription, update payment method,
    view invoices, and cancel subscription.
    """
    if not config.stripe.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment processing is not configured"
        )

    # Find customer by email
    customer = await get_customer_by_email(user.email)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this account"
        )

    origin = request.headers.get("origin", "http://localhost:8200")
    return_url = f"{origin}/dashboard"

    session = await create_customer_portal_session(
        customer_id=customer.id,
        return_url=return_url,
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create portal session"
        )

    return PortalResponse(url=session.url)


@router.post("/api/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """
    Handle Stripe webhook events.

    This endpoint receives and processes webhook events from Stripe,
    including subscription creation, updates, and cancellations.
    """
    if not config.stripe.webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret not configured"
        )

    # Get raw body
    payload = await request.body()

    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header"
        )

    # Verify and construct event
    event = construct_webhook_event(payload, stripe_signature)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature or payload"
        )

    # Handle different event types
    event_type = event.type
    data = event.data.object

    print(f"Received Stripe webhook: {event_type}")

    try:
        if event_type == "customer.created":
            # Log customer creation
            print(f"Customer created: {data.get('id')} - {data.get('email')}")

        elif event_type == "customer.subscription.created":
            await handle_subscription_created(data)

        elif event_type == "customer.subscription.updated":
            await handle_subscription_updated(data)

        elif event_type == "customer.subscription.deleted":
            await handle_subscription_deleted(data)

        elif event_type == "invoice.payment_succeeded":
            print(f"Payment succeeded for invoice: {data.get('id')}")

        elif event_type == "invoice.payment_failed":
            await handle_payment_failed(data)

        else:
            print(f"Unhandled event type: {event_type}")

    except Exception as e:
        print(f"Error handling webhook: {e}")
        # Return 200 to prevent Stripe from retrying
        return JSONResponse(
            content={"received": True, "error": str(e)},
            status_code=status.HTTP_200_OK
        )

    return JSONResponse(content={"received": True})


async def handle_subscription_created(subscription):
    """Handle new subscription creation."""
    customer_id = subscription.get("customer")
    subscription_id = subscription.get("id")
    status_value = subscription.get("status")

    # Get price ID and determine tier
    items = subscription.get("items", {}).get("data", [])
    price_id = items[0].get("price", {}).get("id") if items else None
    tier = get_tier_from_price_id(price_id) if price_id else "free"

    # Get user_id from metadata
    metadata = subscription.get("metadata", {})
    user_id = metadata.get("user_id")

    if not user_id:
        # Try to find user by customer email
        print(f"No user_id in metadata for subscription {subscription_id}")
        return

    # Create subscription record
    subscription_data = {
        "user_id": user_id,
        "stripe_customer_id": customer_id,
        "stripe_subscription_id": subscription_id,
        "stripe_price_id": price_id,
        "membership_tier": tier,
        "status": status_value,
        "current_period_start": subscription.get("current_period_start"),
        "current_period_end": subscription.get("current_period_end"),
        "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
    }

    await upsert_subscription(subscription_data)

    # Update user's membership tier
    if status_value in ["active", "trialing"]:
        await update_user_tier(user_id, tier)

    print(f"Subscription created: {subscription_id} - {tier} for user {user_id}")


async def handle_subscription_updated(subscription):
    """Handle subscription updates (upgrades, downgrades, status changes)."""
    subscription_id = subscription.get("id")
    status_value = subscription.get("status")

    # Get price ID and determine tier
    items = subscription.get("items", {}).get("data", [])
    price_id = items[0].get("price", {}).get("id") if items else None
    tier = get_tier_from_price_id(price_id) if price_id else "free"

    # Get user_id from metadata
    metadata = subscription.get("metadata", {})
    user_id = metadata.get("user_id")

    if user_id:
        # Update subscription record
        subscription_data = {
            "stripe_subscription_id": subscription_id,
            "stripe_price_id": price_id,
            "membership_tier": tier,
            "status": status_value,
            "current_period_start": subscription.get("current_period_start"),
            "current_period_end": subscription.get("current_period_end"),
            "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
        }

        await upsert_subscription(subscription_data)

        # Update user's membership tier based on status
        if status_value in ["active", "trialing"]:
            await update_user_tier(user_id, tier)
        elif status_value in ["canceled", "past_due", "unpaid"]:
            await update_user_tier(user_id, "free")

    print(f"Subscription updated: {subscription_id} - {status_value} - {tier}")


async def handle_subscription_deleted(subscription):
    """Handle subscription cancellation/deletion."""
    subscription_id = subscription.get("id")

    # Get user_id from metadata
    metadata = subscription.get("metadata", {})
    user_id = metadata.get("user_id")

    if user_id:
        # Update subscription status
        subscription_data = {
            "stripe_subscription_id": subscription_id,
            "status": "canceled",
        }
        await upsert_subscription(subscription_data)

        # Downgrade user to free tier
        await update_user_tier(user_id, "free")

    print(f"Subscription deleted: {subscription_id}")


async def handle_payment_failed(invoice):
    """Handle failed payment."""
    customer_id = invoice.get("customer")
    subscription_id = invoice.get("subscription")

    print(f"Payment failed for subscription {subscription_id}, customer {customer_id}")

    # Could send notification email to user here


@router.get("/api/stripe/pricing")
async def get_pricing():
    """
    Get the pricing information for display.
    """
    return {
        "configured": config.stripe.is_configured,
        "tiers": PRICING,
    }
