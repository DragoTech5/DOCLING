"""
Telegram Mini App Authentication

Validates initData from Telegram WebApp using HMAC-SHA-256.
See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, unquote

from fastapi import Request, HTTPException, status, Depends

from app.config import config
from app.db.telegram_repository import (
    get_telegram_user,
    create_or_update_telegram_user,
    TelegramUserRecord,
)


# Maximum age of auth_date in seconds (5 minutes)
MAX_AUTH_AGE_SECONDS = 300


@dataclass
class TelegramUser:
    """Authenticated Telegram user from initData."""
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    is_premium: bool = False
    # Database record (populated after DB lookup)
    db_record: Optional[TelegramUserRecord] = None


def get_bot_token() -> str:
    """Get the Telegram bot token from config or environment."""
    import os
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def validate_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """
    Validate Telegram WebApp initData using HMAC-SHA-256.

    The validation process:
    1. Parse the URL-encoded initData string
    2. Extract and remove the 'hash' field
    3. Sort remaining fields alphabetically by key
    4. Create data_check_string by joining key=value pairs with newline
    5. Create secret_key = HMAC-SHA256("WebAppData", bot_token)
    6. Calculate hash = HMAC-SHA256(secret_key, data_check_string)
    7. Compare calculated hash with provided hash

    Args:
        init_data: The URL-encoded initData string from Telegram.WebApp.initData
        bot_token: The bot token from BotFather

    Returns:
        Parsed data dict if valid, None if invalid
    """
    if not init_data or not bot_token:
        return None

    try:
        # Parse URL-encoded data
        parsed = parse_qs(init_data, keep_blank_values=True)

        # Convert to dict (parse_qs returns lists)
        data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

        # Extract hash
        received_hash = data.pop("hash", None)
        if not received_hash:
            return None

        # Sort keys and create data_check_string
        sorted_keys = sorted(data.keys())
        data_check_string = "\n".join(f"{key}={data[key]}" for key in sorted_keys)

        # Create secret key: HMAC-SHA256("WebAppData", bot_token)
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        # Calculate hash: HMAC-SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        # Compare hashes (constant-time comparison)
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        return data

    except Exception as e:
        print(f"initData validation error: {e}")
        return None


def parse_telegram_user(data: dict) -> Optional[TelegramUser]:
    """
    Parse Telegram user from validated initData.

    Args:
        data: Validated initData dict

    Returns:
        TelegramUser object or None if user data missing
    """
    user_str = data.get("user")
    if not user_str:
        return None

    try:
        # User is JSON-encoded within the initData
        user_data = json.loads(unquote(user_str))

        return TelegramUser(
            id=user_data.get("id"),
            first_name=user_data.get("first_name", ""),
            last_name=user_data.get("last_name"),
            username=user_data.get("username"),
            language_code=user_data.get("language_code"),
            is_premium=user_data.get("is_premium", False),
        )
    except (json.JSONDecodeError, KeyError) as e:
        print(f"User parsing error: {e}")
        return None


def check_auth_date(data: dict, max_age_seconds: int = MAX_AUTH_AGE_SECONDS) -> bool:
    """
    Check if auth_date is recent enough (replay protection).

    Args:
        data: Validated initData dict
        max_age_seconds: Maximum age in seconds

    Returns:
        True if auth_date is recent, False otherwise
    """
    auth_date_str = data.get("auth_date")
    if not auth_date_str:
        return False

    try:
        auth_date = int(auth_date_str)
        current_time = int(time.time())

        # Check if auth_date is not in the future and not too old
        if auth_date > current_time + 60:  # Allow 1 minute clock skew
            return False

        if current_time - auth_date > max_age_seconds:
            return False

        return True
    except ValueError:
        return False


async def authenticate_telegram_request(
    init_data: str,
    check_age: bool = True,
) -> Optional[TelegramUser]:
    """
    Authenticate a Telegram Mini App request.

    Validates initData, checks auth_date, and returns the user.

    Args:
        init_data: The initData string from X-Telegram-Init-Data header
        check_age: Whether to enforce auth_date freshness

    Returns:
        TelegramUser with database record, or None if invalid
    """
    import logging
    logger = logging.getLogger(__name__)

    bot_token = get_bot_token()
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set")
        return None

    # Validate initData signature
    data = validate_init_data(init_data, bot_token)
    if not data:
        return None

    # Check auth_date for replay protection
    if check_age and not check_auth_date(data):
        return None

    # Parse user data
    user = parse_telegram_user(data)
    if not user:
        return None

    # Log user info (helpful for getting telegram_id for whitelist)
    logger.info(f"Telegram auth: id={user.id}, username={user.username}, name={user.first_name}")

    # Create or update user in database
    db_user = await create_or_update_telegram_user(
        telegram_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        language_code=user.language_code,
        is_premium=user.is_premium,
    )

    # Log tier info
    tier = db_user.get("tier", "free") if db_user else "unknown"
    logger.info(f"Telegram user {user.id} authenticated with tier={tier}")

    user.db_record = db_user
    return user


def extract_init_data(request: Request) -> Optional[str]:
    """
    Extract initData from request header.

    Args:
        request: FastAPI request object

    Returns:
        initData string or None
    """
    return request.headers.get("X-Telegram-Init-Data")


async def get_telegram_user_from_request(request: Request) -> Optional[TelegramUser]:
    """
    Get authenticated Telegram user from request.

    Extracts initData from header and validates it.

    Args:
        request: FastAPI request object

    Returns:
        TelegramUser or None if not authenticated
    """
    init_data = extract_init_data(request)
    if not init_data:
        return None

    return await authenticate_telegram_request(init_data)


async def get_current_telegram_user(request: Request) -> TelegramUser:
    """
    FastAPI dependency to require Telegram authentication.

    Raises HTTPException if not authenticated.
    In TWA_DEV_MODE, bypasses auth and uses a test user.

    Usage:
        @router.get("/protected")
        async def protected(user: TelegramUser = Depends(get_current_telegram_user)):
            return {"user_id": user.id}
    """
    user = await get_telegram_user_from_request(request)

    if user is None:
        # Check for dev mode bypass
        from app.config import config
        if config.mode.twa_dev_mode:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"TWA_DEV_MODE: Using test user {config.mode.twa_dev_telegram_id}")

            # Get or create the dev user from database
            db_user = await get_telegram_user(config.mode.twa_dev_telegram_id)
            if not db_user:
                # Create dev user if not exists
                db_user = await create_or_update_telegram_user(
                    telegram_id=config.mode.twa_dev_telegram_id,
                    first_name="Dev",
                    last_name="User",
                    username="dev_user",
                    language_code="en",
                    is_premium=False,
                )

            return TelegramUser(
                id=config.mode.twa_dev_telegram_id,
                first_name=db_user.get("first_name", "Dev") if db_user else "Dev",
                last_name=db_user.get("last_name") if db_user else None,
                username=db_user.get("username") if db_user else "dev_user",
                db_record=db_user,
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Telegram authentication",
        )

    return user


async def get_optional_telegram_user(request: Request) -> Optional[TelegramUser]:
    """
    FastAPI dependency to optionally get Telegram user.

    Returns None if not authenticated (doesn't raise exception).

    Usage:
        @router.get("/optional")
        async def optional(user: Optional[TelegramUser] = Depends(get_optional_telegram_user)):
            if user:
                return {"user_id": user.id}
            return {"message": "Guest"}
    """
    return await get_telegram_user_from_request(request)


def require_telegram_tier(min_tier: str):
    """
    FastAPI dependency factory to require minimum subscription tier.

    Args:
        min_tier: Minimum tier required

    Usage:
        @router.get("/pro-feature")
        async def pro(user: TelegramUser = Depends(require_telegram_tier("pro"))):
            return {"feature": "unlocked"}
    """
    tier_levels = {
        "free": 0,
        "starter": 1,
        "pro": 2,
        "business": 3,
        "enterprise": 4,
    }
    required_level = tier_levels.get(min_tier, 0)

    async def dependency(request: Request) -> TelegramUser:
        user = await get_current_telegram_user(request)

        if not user.db_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found in database",
            )

        user_tier = user.db_record.get("tier", "free")
        user_level = tier_levels.get(user_tier, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires {min_tier} tier or higher",
            )

        return user

    return dependency


def require_query_credits():
    """
    FastAPI dependency to require available query credits.

    Usage:
        @router.post("/chat")
        async def chat(user: TelegramUser = Depends(require_query_credits())):
            # User has credits available
            ...
    """
    async def dependency(request: Request) -> TelegramUser:
        user = await get_current_telegram_user(request)

        if not user.db_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found in database",
            )

        # Check if user has unlimited queries (enterprise or unlimited tier)
        tier = user.db_record.get("tier", "free")
        if tier in ("enterprise", "unlimited"):
            return user

        # Check remaining credits
        remaining = user.db_record.get("queries_remaining", 0)
        if remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="No query credits remaining. Please upgrade or purchase more.",
            )

        return user

    return dependency
