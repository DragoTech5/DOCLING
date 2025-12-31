"""
Stripe Client Utilities

Provides Stripe client initialization and helper functions for payment operations.
"""

from typing import Optional, Literal
import stripe

from app.config import config


# Type aliases
MembershipTier = Literal["free", "pro", "enterprise"]
BillingPeriod = Literal["monthly", "yearly"]


def initialize_stripe():
    """Initialize the Stripe client with the secret key."""
    if config.stripe.secret_key:
        stripe.api_key = config.stripe.secret_key


def get_price_id(tier: MembershipTier, period: BillingPeriod) -> Optional[str]:
    """
    Get the Stripe price ID for a given tier and billing period.

    Args:
        tier: The membership tier (pro or enterprise)
        period: The billing period (monthly or yearly)

    Returns:
        The Stripe price ID or None if not configured
    """
    price_map = {
        ("pro", "monthly"): config.stripe.pro_monthly_price_id,
        ("pro", "yearly"): config.stripe.pro_yearly_price_id,
        ("enterprise", "monthly"): config.stripe.enterprise_monthly_price_id,
        ("enterprise", "yearly"): config.stripe.enterprise_yearly_price_id,
    }
    return price_map.get((tier, period))


def get_tier_from_price_id(price_id: str) -> MembershipTier:
    """
    Get the membership tier from a Stripe price ID.

    Args:
        price_id: The Stripe price ID

    Returns:
        The membership tier (defaults to 'free' if not found)
    """
    if price_id in [config.stripe.pro_monthly_price_id, config.stripe.pro_yearly_price_id]:
        return "pro"
    if price_id in [config.stripe.enterprise_monthly_price_id, config.stripe.enterprise_yearly_price_id]:
        return "enterprise"
    return "free"


async def create_checkout_session(
    customer_email: str,
    tier: MembershipTier,
    period: BillingPeriod,
    success_url: str,
    cancel_url: str,
    customer_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[stripe.checkout.Session]:
    """
    Create a Stripe Checkout session for subscription purchase.

    Args:
        customer_email: The customer's email address
        tier: The membership tier to subscribe to
        period: The billing period (monthly or yearly)
        success_url: URL to redirect to on successful payment
        cancel_url: URL to redirect to on cancelled payment
        customer_id: Optional existing Stripe customer ID
        metadata: Optional metadata to attach to the session

    Returns:
        The Stripe Checkout Session object or None on error
    """
    initialize_stripe()

    price_id = get_price_id(tier, period)
    if not price_id:
        raise ValueError(f"No price ID configured for {tier} {period}")

    try:
        session_params = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata or {},
        }

        if customer_id:
            session_params["customer"] = customer_id
        else:
            session_params["customer_email"] = customer_email

        session = stripe.checkout.Session.create(**session_params)
        return session
    except stripe.error.StripeError as e:
        print(f"Stripe error creating checkout session: {e}")
        return None


async def create_customer_portal_session(
    customer_id: str,
    return_url: str,
) -> Optional[stripe.billing_portal.Session]:
    """
    Create a Stripe Customer Portal session for subscription management.

    Args:
        customer_id: The Stripe customer ID
        return_url: URL to redirect to when the customer is done

    Returns:
        The Stripe Portal Session object or None on error
    """
    initialize_stripe()

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session
    except stripe.error.StripeError as e:
        print(f"Stripe error creating portal session: {e}")
        return None


def construct_webhook_event(payload: bytes, sig_header: str) -> Optional[stripe.Event]:
    """
    Construct and verify a Stripe webhook event.

    Args:
        payload: The raw request body
        sig_header: The Stripe-Signature header value

    Returns:
        The verified Stripe Event object or None on error
    """
    initialize_stripe()

    if not config.stripe.webhook_secret:
        raise ValueError("Stripe webhook secret is not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.stripe.webhook_secret
        )
        return event
    except ValueError:
        # Invalid payload
        return None
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return None


async def get_customer_by_email(email: str) -> Optional[stripe.Customer]:
    """
    Find a Stripe customer by email.

    Args:
        email: The customer's email address

    Returns:
        The Stripe Customer object or None if not found
    """
    initialize_stripe()

    try:
        customers = stripe.Customer.list(email=email, limit=1)
        return customers.data[0] if customers.data else None
    except stripe.error.StripeError:
        return None


async def get_subscription(subscription_id: str) -> Optional[stripe.Subscription]:
    """
    Get a Stripe subscription by ID.

    Args:
        subscription_id: The Stripe subscription ID

    Returns:
        The Stripe Subscription object or None if not found
    """
    initialize_stripe()

    try:
        return stripe.Subscription.retrieve(subscription_id)
    except stripe.error.StripeError:
        return None


# Pricing configuration for display
PRICING = {
    "pro": {
        "name": "Pro",
        "description": "For power users",
        "features": [
            "Unlimited document uploads",
            "Unlimited YouTube transcriptions",
            "Priority processing",
            "Advanced RAG queries",
            "API access",
        ],
        "monthly_price": 9.99,
        "yearly_price": 99.99,
    },
    "enterprise": {
        "name": "Enterprise",
        "description": "For teams and businesses",
        "features": [
            "Everything in Pro",
            "Unlimited team members",
            "Custom integrations",
            "Dedicated support",
            "SLA guarantee",
            "On-premise deployment",
        ],
        "monthly_price": 29.99,
        "yearly_price": 299.99,
    },
}


def format_price(amount: float, currency: str = "USD") -> str:
    """Format a price for display."""
    if currency == "USD":
        return f"${amount:.2f}"
    return f"{amount:.2f} {currency}"
