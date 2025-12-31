"""
Supabase Client Utilities

Provides Supabase client initialization for authentication and database operations.
"""

from typing import Optional
from supabase import create_client, Client
from jose import jwt, JWTError
from datetime import datetime

from app.config import config


# Module-level clients (initialized lazily)
_supabase_client: Optional[Client] = None
_supabase_admin_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Get the Supabase client using anon key.
    Use this for client-side operations that respect RLS.
    """
    global _supabase_client

    if not config.supabase.is_configured:
        raise ValueError("Supabase is not configured. Please set SUPABASE_URL and SUPABASE_ANON_KEY.")

    if _supabase_client is None:
        _supabase_client = create_client(
            config.supabase.url,
            config.supabase.anon_key
        )

    return _supabase_client


def get_supabase_admin_client() -> Client:
    """
    Get the Supabase admin client using service role key.
    Use this for server-side operations that bypass RLS (e.g., webhooks).
    """
    global _supabase_admin_client

    if not config.supabase.service_role_key:
        raise ValueError("Supabase service role key is not configured.")

    if _supabase_admin_client is None:
        _supabase_admin_client = create_client(
            config.supabase.url,
            config.supabase.service_role_key
        )

    return _supabase_admin_client


def verify_jwt_token(token: str) -> Optional[dict]:
    """
    Verify a Supabase JWT token and return the payload.

    Args:
        token: The JWT token to verify

    Returns:
        The decoded token payload if valid, None otherwise
    """
    if not config.supabase.jwt_secret:
        # If JWT secret not configured, use Supabase to verify
        return verify_token_with_supabase(token)

    try:
        payload = jwt.decode(
            token,
            config.supabase.jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )

        # Check expiration
        exp = payload.get("exp")
        if exp and datetime.utcnow().timestamp() > exp:
            return None

        return payload
    except JWTError:
        return None


def verify_token_with_supabase(token: str) -> Optional[dict]:
    """
    Verify a token by calling Supabase auth.getUser().

    Args:
        token: The access token to verify

    Returns:
        User data if valid, None otherwise
    """
    try:
        client = get_supabase_client()
        response = client.auth.get_user(token)
        if response and response.user:
            return {
                "sub": response.user.id,
                "email": response.user.email,
                "user_metadata": response.user.user_metadata,
                "app_metadata": response.user.app_metadata,
            }
        return None
    except Exception:
        return None


async def get_user_profile(user_id: str) -> Optional[dict]:
    """
    Get a user's profile from the profiles table.

    Args:
        user_id: The user's UUID

    Returns:
        Profile data if found, None otherwise
    """
    try:
        client = get_supabase_admin_client()
        response = client.table("profiles").select("*").eq("id", user_id).single().execute()
        return response.data if response.data else None
    except Exception:
        return None


async def get_user_subscription(user_id: str) -> Optional[dict]:
    """
    Get a user's active subscription.

    Args:
        user_id: The user's UUID

    Returns:
        Subscription data if found, None otherwise
    """
    try:
        client = get_supabase_admin_client()
        response = (
            client.table("subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .in_("status", ["active", "trialing"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception:
        return None


async def upsert_subscription(subscription_data: dict) -> Optional[dict]:
    """
    Create or update a subscription record.

    Args:
        subscription_data: The subscription data to upsert

    Returns:
        The upserted subscription data
    """
    try:
        client = get_supabase_admin_client()
        response = (
            client.table("subscriptions")
            .upsert(subscription_data, on_conflict="stripe_subscription_id")
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error upserting subscription: {e}")
        return None


async def update_user_tier(user_id: str, tier: str) -> bool:
    """
    Update a user's membership tier in their profile.

    Args:
        user_id: The user's UUID
        tier: The membership tier (free, pro, enterprise)

    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_supabase_admin_client()
        response = (
            client.table("profiles")
            .update({"membership_tier": tier})
            .eq("id", user_id)
            .execute()
        )
        return bool(response.data)
    except Exception as e:
        print(f"Error updating user tier: {e}")
        return False
