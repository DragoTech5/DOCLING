"""
Telegram Mini App Repository - CRUD operations for Telegram users, subscriptions, conversations
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

import aiosqlite

logger = logging.getLogger(__name__)

from app.db.models import (
    TelegramUserRecord,
    SubscriptionRecord,
    PaymentHistoryRecord,
    TgConversationRecord,
    TgMessageRecord,
    SubscriptionTier,
    TIER_LIMITS,
    get_db_path,
)


def get_dev_whitelist() -> set[int]:
    """Get set of whitelisted Telegram user IDs for dev/testing."""
    whitelist_str = os.getenv("TELEGRAM_DEV_WHITELIST", "")
    if not whitelist_str.strip():
        return set()
    try:
        return {int(uid.strip()) for uid in whitelist_str.split(",") if uid.strip()}
    except ValueError:
        return set()


def is_dev_whitelisted(telegram_id: int) -> bool:
    """Check if a Telegram user ID is in the dev whitelist."""
    return telegram_id in get_dev_whitelist()


# ============================================================================
# Telegram Users Repository
# ============================================================================


async def get_telegram_user(telegram_id: int) -> TelegramUserRecord | None:
    """Get a Telegram user by their Telegram ID."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM telegram_users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_telegram_user_by_id(user_id: int) -> TelegramUserRecord | None:
    """Get a Telegram user by internal ID."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM telegram_users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_or_update_telegram_user(
    telegram_id: int,
    first_name: str,
    last_name: str | None = None,
    username: str | None = None,
    language_code: str | None = None,
    is_premium: bool = False,
) -> TelegramUserRecord:
    """Create a new Telegram user or update existing one. Returns the user record."""
    # Check if user is in dev whitelist (gets enterprise tier)
    is_whitelisted = is_dev_whitelisted(telegram_id)

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Check if user exists
        cursor = await db.execute(
            "SELECT * FROM telegram_users WHERE telegram_id = ?",
            (telegram_id,),
        )
        existing = await cursor.fetchone()

        if existing:
            # Update existing user
            if is_whitelisted:
                # Whitelisted users always get enterprise tier with unlimited queries
                await db.execute(
                    """UPDATE telegram_users SET
                       first_name = ?, last_name = ?, username = ?,
                       language_code = ?, is_premium = ?,
                       tier = 'enterprise', queries_remaining = 999999
                       WHERE telegram_id = ?""",
                    (first_name, last_name, username, language_code, 1 if is_premium else 0, telegram_id),
                )
            else:
                await db.execute(
                    """UPDATE telegram_users SET
                       first_name = ?, last_name = ?, username = ?,
                       language_code = ?, is_premium = ?
                       WHERE telegram_id = ?""",
                    (first_name, last_name, username, language_code, 1 if is_premium else 0, telegram_id),
                )
            await db.commit()

            # Fetch updated record
            cursor = await db.execute(
                "SELECT * FROM telegram_users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            return dict(row)
        else:
            # Create new user
            if is_whitelisted:
                # Whitelisted users get enterprise tier
                cursor = await db.execute(
                    """INSERT INTO telegram_users
                       (telegram_id, first_name, last_name, username, language_code, is_premium,
                        tier, queries_used, queries_remaining)
                       VALUES (?, ?, ?, ?, ?, ?, 'enterprise', 0, 999999)""",
                    (telegram_id, first_name, last_name, username, language_code,
                     1 if is_premium else 0),
                )
                import logging
                logging.getLogger(__name__).info(f"DEV WHITELIST: Created enterprise user for telegram_id={telegram_id}")
            else:
                # Normal users get free tier
                tier_limits = TIER_LIMITS["free"]
                cursor = await db.execute(
                    """INSERT INTO telegram_users
                       (telegram_id, first_name, last_name, username, language_code, is_premium,
                        tier, queries_used, queries_remaining)
                       VALUES (?, ?, ?, ?, ?, ?, 'free', 0, ?)""",
                    (telegram_id, first_name, last_name, username, language_code,
                     1 if is_premium else 0, tier_limits["monthly_queries"]),
                )
            await db.commit()

            # Fetch created record
            cursor = await db.execute(
                "SELECT * FROM telegram_users WHERE id = ?",
                (cursor.lastrowid,),
            )
            row = await cursor.fetchone()
            return dict(row)


async def update_telegram_user_tier(
    telegram_id: int,
    tier: SubscriptionTier,
    subscription_ends_at: str | None = None,
) -> bool:
    """Update user's subscription tier and reset queries."""
    tier_limits = TIER_LIMITS[tier]
    monthly_queries = tier_limits["monthly_queries"]

    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """UPDATE telegram_users SET
               tier = ?, queries_used = 0, queries_remaining = ?,
               subscription_ends_at = ?
               WHERE telegram_id = ?""",
            (tier, monthly_queries, subscription_ends_at, telegram_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def deduct_query_credit(telegram_id: int) -> bool:
    """Deduct one query credit from user. Returns False if no credits remaining."""
    async with aiosqlite.connect(get_db_path()) as db:
        # Check current credits
        cursor = await db.execute(
            "SELECT queries_remaining, tier FROM telegram_users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return False

        queries_remaining = row[0]
        tier = row[1]

        # Enterprise users have unlimited queries
        tier_limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
        if tier_limits["monthly_queries"] is None:
            # Unlimited - just increment used count
            await db.execute(
                "UPDATE telegram_users SET queries_used = queries_used + 1 WHERE telegram_id = ?",
                (telegram_id,),
            )
            await db.commit()
            return True

        # Check if credits available
        if queries_remaining <= 0:
            return False

        # Deduct credit
        cursor = await db.execute(
            """UPDATE telegram_users SET
               queries_used = queries_used + 1,
               queries_remaining = queries_remaining - 1
               WHERE telegram_id = ? AND queries_remaining > 0""",
            (telegram_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def add_query_credits(telegram_id: int, credits: int) -> bool:
    """Add query credits to user (for token bundle purchases)."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            "UPDATE telegram_users SET queries_remaining = queries_remaining + ? WHERE telegram_id = ?",
            (credits, telegram_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def reset_monthly_queries(telegram_id: int) -> bool:
    """Reset monthly queries for a user (called on subscription renewal)."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            "SELECT tier FROM telegram_users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return False

        tier = row[0]
        tier_limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
        monthly_queries = tier_limits["monthly_queries"]

        if monthly_queries is None:
            return True  # Unlimited, nothing to reset

        cursor = await db.execute(
            "UPDATE telegram_users SET queries_used = 0, queries_remaining = ? WHERE telegram_id = ?",
            (monthly_queries, telegram_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ============================================================================
# Subscriptions Repository
# ============================================================================


async def create_subscription(
    telegram_user_id: int,
    tier: SubscriptionTier,
    telegram_payment_charge_id: str | None = None,
) -> int:
    """Create a new subscription (30 days from now)."""
    ends_at = (datetime.now() + timedelta(days=30)).isoformat()

    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """INSERT INTO subscriptions
               (telegram_user_id, tier, status, ends_at, telegram_payment_charge_id)
               VALUES (?, ?, 'active', ?, ?)""",
            (telegram_user_id, tier, ends_at, telegram_payment_charge_id),
        )
        await db.commit()
        return cursor.lastrowid


async def get_active_subscription(telegram_user_id: int) -> SubscriptionRecord | None:
    """Get the active subscription for a user."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM subscriptions
               WHERE telegram_user_id = ? AND status = 'active'
               ORDER BY ends_at DESC LIMIT 1""",
            (telegram_user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def cancel_subscription(subscription_id: int) -> bool:
    """Cancel a subscription."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            "UPDATE subscriptions SET status = 'cancelled' WHERE id = ?",
            (subscription_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def expire_subscription(subscription_id: int) -> bool:
    """Mark a subscription as expired."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            "UPDATE subscriptions SET status = 'expired' WHERE id = ?",
            (subscription_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


# ============================================================================
# Payment History Repository
# ============================================================================


async def create_payment_record(
    telegram_user_id: int,
    payment_type: str,  # 'subscription' or 'token_bundle'
    amount_stars: int,
    telegram_payment_charge_id: str,
    tier: str | None = None,
    bundle_id: str | None = None,
    tokens_added: int | None = None,
    provider_payment_charge_id: str | None = None,
) -> int:
    """Create a payment history record."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """INSERT INTO payment_history
               (telegram_user_id, payment_type, amount_stars, tier, bundle_id,
                tokens_added, telegram_payment_charge_id, provider_payment_charge_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (telegram_user_id, payment_type, amount_stars, tier, bundle_id,
             tokens_added, telegram_payment_charge_id, provider_payment_charge_id),
        )
        await db.commit()
        return cursor.lastrowid


async def get_payment_history(
    telegram_user_id: int,
    limit: int = 20,
) -> list[PaymentHistoryRecord]:
    """Get payment history for a user."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM payment_history
               WHERE telegram_user_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (telegram_user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def mark_payment_refunded(telegram_payment_charge_id: str) -> bool:
    """Mark a payment as refunded."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            "UPDATE payment_history SET status = 'refunded' WHERE telegram_payment_charge_id = ?",
            (telegram_payment_charge_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


# ============================================================================
# Telegram Conversations Repository
# ============================================================================


async def get_tg_conversations(
    telegram_user_id: int,
    limit: int = 50,
) -> list[TgConversationRecord]:
    """Get conversations for a Telegram user."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM tg_conversations
               WHERE telegram_user_id = ?
               ORDER BY updated_at DESC LIMIT ?""",
            (telegram_user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_tg_conversation(
    conversation_id: int,
    telegram_user_id: int | None = None,
) -> TgConversationRecord | None:
    """Get a single Telegram conversation. Optionally verify ownership."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        if telegram_user_id:
            cursor = await db.execute(
                "SELECT * FROM tg_conversations WHERE id = ? AND telegram_user_id = ?",
                (conversation_id, telegram_user_id),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM tg_conversations WHERE id = ?",
                (conversation_id,),
            )

        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_tg_conversation(
    telegram_user_id: int,
    title: str = "New Chat",
    pdf_ids: list[int] | None = None,
) -> int:
    """Create a new Telegram conversation."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """INSERT INTO tg_conversations (telegram_user_id, title, pdf_ids)
               VALUES (?, ?, ?)""",
            (telegram_user_id, title, json.dumps(pdf_ids) if pdf_ids else None),
        )
        await db.commit()
        return cursor.lastrowid


async def update_tg_conversation(
    conversation_id: int,
    title: str | None = None,
    pdf_ids: list[int] | None = None,
) -> bool:
    """Update a Telegram conversation."""
    updates = []
    values = []

    if title is not None:
        updates.append("title = ?")
        values.append(title)
    if pdf_ids is not None:
        updates.append("pdf_ids = ?")
        values.append(json.dumps(pdf_ids) if pdf_ids else None)

    if not updates:
        return False

    values.append(conversation_id)
    query = f"UPDATE tg_conversations SET {', '.join(updates)} WHERE id = ?"

    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(query, values)
        await db.commit()
        return cursor.rowcount > 0


async def delete_tg_conversation(conversation_id: int, telegram_user_id: int) -> bool:
    """Delete a Telegram conversation (with ownership check)."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            "DELETE FROM tg_conversations WHERE id = ? AND telegram_user_id = ?",
            (conversation_id, telegram_user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ============================================================================
# Telegram Messages Repository
# ============================================================================


async def get_tg_messages(
    conversation_id: int,
    limit: int = 100,
) -> list[TgMessageRecord]:
    """Get messages for a Telegram conversation."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM tg_messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC LIMIT ?""",
            (conversation_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def create_tg_message(
    conversation_id: int,
    role: str,
    content: str,
    sources: list[dict] | None = None,
) -> int:
    """Create a new Telegram message."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """INSERT INTO tg_messages (conversation_id, role, content, sources)
               VALUES (?, ?, ?, ?)""",
            (conversation_id, role, content, json.dumps(sources) if sources else None),
        )
        await db.commit()
        return cursor.lastrowid


async def get_tg_conversation_with_messages(
    conversation_id: int,
    telegram_user_id: int | None = None,
) -> dict | None:
    """Get a Telegram conversation with all its messages."""
    conversation = await get_tg_conversation(conversation_id, telegram_user_id)
    if not conversation:
        return None

    messages = await get_tg_messages(conversation_id)

    return {
        **conversation,
        "messages": messages,
    }


# ============================================================================
# History Cleanup (for tier-based retention)
# ============================================================================


async def cleanup_old_conversations(telegram_user_id: int, days: int) -> int:
    """Delete conversations older than specified days. Returns count deleted."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """DELETE FROM tg_conversations
               WHERE telegram_user_id = ? AND updated_at < ?""",
            (telegram_user_id, cutoff),
        )
        await db.commit()
        return cursor.rowcount


# ============================================================================
# Saved Conversations Repository
# ============================================================================


async def save_conversation(
    telegram_user_id: int,
    conversation_id: int,
    title: str,
    selected_doc_ids: list[str] | None = None,
) -> dict:
    """Save a conversation with title and selected documents."""
    from uuid import uuid4

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Insert saved conversation
        share_token = str(uuid4())
        cursor = await db.execute(
            """INSERT INTO saved_conversations
               (telegram_user_id, conversation_id, title, share_token, is_public)
               VALUES (?, ?, ?, ?, ?)""",
            (telegram_user_id, conversation_id, title, share_token, 0),
        )
        await db.commit()
        saved_conv_id = cursor.lastrowid

        # Insert selected documents
        if selected_doc_ids:
            for doc_id in selected_doc_ids:
                await db.execute(
                    """INSERT INTO saved_conversation_documents
                       (saved_conversation_id, document_id)
                       VALUES (?, ?)""",
                    (saved_conv_id, doc_id),
                )
            await db.commit()

        # Get the created record
        cursor = await db.execute(
            "SELECT * FROM saved_conversations WHERE id = ?",
            (saved_conv_id,),
        )
        return dict(await cursor.fetchone())


async def get_saved_conversations(telegram_user_id: int) -> list[dict]:
    """Get all saved conversations for a user."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT sc.id, sc.title, sc.created_at,
                      COUNT(DISTINCT tm.id) as message_count,
                      COUNT(DISTINCT scd.id) as doc_count
               FROM saved_conversations sc
               LEFT JOIN tg_messages tm ON tm.conversation_id = sc.conversation_id
               LEFT JOIN saved_conversation_documents scd ON scd.saved_conversation_id = sc.id
               WHERE sc.telegram_user_id = ?
               GROUP BY sc.id
               ORDER BY sc.created_at DESC""",
            (telegram_user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_saved_conversation(saved_conversation_id: int, telegram_user_id: int = None) -> dict | None:
    """Get a saved conversation by ID with all messages and documents. Optionally verify ownership."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Get saved conversation
        if telegram_user_id:
            # Check ownership if user ID provided
            cursor = await db.execute(
                "SELECT * FROM saved_conversations WHERE id = ? AND telegram_user_id = ?",
                (saved_conversation_id, telegram_user_id),
            )
        else:
            # Get without ownership check (for public sharing)
            cursor = await db.execute(
                "SELECT * FROM saved_conversations WHERE id = ?",
                (saved_conversation_id,),
            )
        saved_conv = await cursor.fetchone()
        if not saved_conv:
            return None

        saved_conv = dict(saved_conv)

        # Get messages from linked conversation
        cursor = await db.execute(
            """SELECT id, role, content, sources, created_at FROM tg_messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC""",
            (saved_conv["conversation_id"],),
        )
        messages = []
        for row in await cursor.fetchall():
            msg = dict(row)
            msg["sources"] = json.loads(msg.get("sources") or "[]")
            messages.append(msg)

        # Get documents
        cursor = await db.execute(
            """SELECT document_id FROM saved_conversation_documents
               WHERE saved_conversation_id = ?
               ORDER BY added_at ASC""",
            (saved_conversation_id,),
        )
        documents = [dict(row) for row in await cursor.fetchall()]

        return {
            **saved_conv,
            "messages": messages,
            "documents": documents,
        }


async def get_saved_conversation_by_share_token(share_token: str) -> dict | None:
    """Get saved conversation by share token (for public sharing)."""
    return await get_saved_conversation_by_share_token_impl(share_token)


async def get_saved_conversation_by_share_token_impl(share_token: str) -> dict | None:
    """Get saved conversation by share token (public access)."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Get saved conversation
        cursor = await db.execute(
            "SELECT * FROM saved_conversations WHERE share_token = ? AND is_public = 1",
            (share_token,),
        )
        saved_conv = await cursor.fetchone()
        if not saved_conv:
            return None

        saved_conv = dict(saved_conv)

        # Get messages
        cursor = await db.execute(
            """SELECT id, role, content, sources, created_at FROM tg_messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC""",
            (saved_conv["conversation_id"],),
        )
        messages = []
        for row in await cursor.fetchall():
            msg = dict(row)
            msg["sources"] = json.loads(msg.get("sources") or "[]")
            messages.append(msg)

        # Get documents
        cursor = await db.execute(
            """SELECT document_id FROM saved_conversation_documents
               WHERE saved_conversation_id = ?
               ORDER BY added_at ASC""",
            (saved_conv["id"],),
        )
        documents = [dict(row) for row in await cursor.fetchall()]

        return {
            **saved_conv,
            "messages": messages,
            "documents": documents,
        }


async def delete_saved_conversation(saved_conversation_id: int, telegram_user_id: int = None) -> bool:
    """Delete a saved conversation. Optionally verify ownership."""
    async with aiosqlite.connect(get_db_path()) as db:
        if telegram_user_id:
            # Verify ownership before deleting
            cursor = await db.execute(
                "DELETE FROM saved_conversations WHERE id = ? AND telegram_user_id = ?",
                (saved_conversation_id, telegram_user_id),
            )
        else:
            # Delete without ownership check
            cursor = await db.execute(
                "DELETE FROM saved_conversations WHERE id = ?",
                (saved_conversation_id,),
            )
        await db.commit()
        return cursor.rowcount > 0


async def enable_conversation_sharing(saved_conversation_id: int, telegram_user_id: int) -> str | None:
    """Enable sharing for a conversation and return share token. Verifies user ownership."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Get the share token and verify ownership
        cursor = await db.execute(
            "SELECT share_token FROM saved_conversations WHERE id = ? AND telegram_user_id = ?",
            (saved_conversation_id, telegram_user_id),
        )
        result = await cursor.fetchone()
        if not result:
            return None

        share_token = result["share_token"]

        # Enable sharing
        await db.execute(
            "UPDATE saved_conversations SET is_public = 1 WHERE id = ?",
            (saved_conversation_id,),
        )
        await db.commit()

        return share_token


async def count_saved_conversations(telegram_user_id: int) -> int:
    """Count saved conversations for a user."""
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM saved_conversations WHERE telegram_user_id = ?",
            (telegram_user_id,),
        )
        result = await cursor.fetchone()
        return result[0] if result else 0


# ============================================================================
# Dodo Payments Repository
# ============================================================================


async def create_dodo_payment_record(
    telegram_user_id: int,
    checkout_session_id: str,
    tier: str,
    amount_usd: int,
    expires_at: str,
    customer_email: str | None = None,
) -> int:
    """
    Create a pending Dodo payment record.

    Args:
        telegram_user_id: Internal user ID
        checkout_session_id: Dodo checkout session ID
        tier: Subscription tier (researcher, unlimited)
        amount_usd: Amount in cents (1500, 3900, 9900)
        expires_at: ISO-8601 checkout session expiry timestamp
        customer_email: Customer email address

    Returns:
        ID of the created payment record
    """
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """
            INSERT INTO dodo_payments (
                telegram_user_id, checkout_session_id, tier, amount_usd,
                status, expires_at, customer_email
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (telegram_user_id, checkout_session_id, tier, amount_usd, expires_at, customer_email),
        )
        await db.commit()
        return cursor.lastrowid


async def complete_dodo_payment(
    checkout_session_id: str,
    payment_id: str,
    payment_method: str,
    customer_id: str,
) -> dict | None:
    """
    Mark a Dodo payment as completed.

    Args:
        checkout_session_id: Dodo checkout session ID
        payment_id: Dodo payment ID
        payment_method: Payment method (card_visa, card_mastercard, etc.)
        customer_id: Dodo customer ID

    Returns:
        Updated payment record as dict, or None if not found
    """
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Update payment record
        await db.execute(
            """
            UPDATE dodo_payments
            SET status = 'completed',
                payment_id = ?,
                payment_method = ?,
                customer_id = ?,
                completed_at = datetime('now')
            WHERE checkout_session_id = ?
            """,
            (payment_id, payment_method, customer_id, checkout_session_id),
        )
        await db.commit()

        # Fetch and return updated record
        cursor = await db.execute(
            "SELECT * FROM dodo_payments WHERE checkout_session_id = ?",
            (checkout_session_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_dodo_payment_by_session(checkout_session_id: str) -> dict | None:
    """
    Retrieve a Dodo payment record by checkout session ID.

    Args:
        checkout_session_id: Dodo checkout session ID

    Returns:
        Payment record as dict, or None if not found
    """
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM dodo_payments WHERE checkout_session_id = ?",
            (checkout_session_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
