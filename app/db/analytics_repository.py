"""
Analytics Repository for tracking user events and metrics in Docling Knowledge Hub.
Provides database operations for event logging, query metrics, and conversion funnel tracking.
"""

import json
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from app.db.models import (
    AnalyticsEventRecord,
    AnalyticsQueryMetadataRecord,
    AnalyticsConversionFunnelRecord,
    TelegramUserRecord,
)
from app.config import config


class AnalyticsRepository:
    """Repository for analytics database operations."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.database.sqlite_path

    # ========== Core Event Tracking ==========

    async def create_event(
        self,
        telegram_user: TelegramUserRecord,
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> int:
        """
        Log an analytics event.

        Args:
            telegram_user: Telegram user record
            event_type: Type of event (user_signup, user_login, document_browse, etc.)
            metadata: Optional JSON metadata
            session_id: Optional session ID

        Returns:
            Event ID
        """
        metadata_json = json.dumps(metadata) if metadata else None

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO analytics_events
                (telegram_user_id, telegram_id, user_tier, event_type, metadata, session_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_user["id"],
                    telegram_user["telegram_id"],
                    telegram_user["tier"],
                    event_type,
                    metadata_json,
                    session_id,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def create_query_metadata(
        self,
        event_id: int,
        conversation_id: int,
        query_text: str,
        collection: str,
        selected_doc_count: int = 0,
    ) -> int:
        """
        Log detailed query metadata.

        Args:
            event_id: Associated event ID
            conversation_id: Associated conversation ID
            query_text: The query text
            collection: Collection name (maglib, bibliothek, etc.)
            selected_doc_count: Number of selected documents

        Returns:
            Metadata record ID
        """
        query_length = len(query_text)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO analytics_query_metadata
                (event_id, conversation_id, query_text, query_length, collection, selected_doc_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, conversation_id, query_text, query_length, collection, selected_doc_count),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_query_metadata(
        self,
        event_id: int,
        response_time_ms: Optional[int] = None,
        chunk_count: Optional[int] = None,
        source_count: Optional[int] = None,
    ) -> None:
        """Update query metadata with response metrics."""
        has_sources = 1 if source_count and source_count > 0 else 0

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE analytics_query_metadata
                SET response_time_ms = ?, source_count = ?, has_sources = ?
                WHERE event_id = ?
                """,
                (response_time_ms, source_count, has_sources, event_id),
            )
            await db.commit()

    # ========== Conversion Funnel Tracking ==========

    async def initialize_conversion_funnel(self, telegram_user_id: int) -> int:
        """Initialize conversion funnel record for a new user."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if already exists
            cursor = await db.execute(
                "SELECT id FROM analytics_conversion_funnel WHERE telegram_user_id = ?",
                (telegram_user_id,),
            )
            existing = await cursor.fetchone()
            if existing:
                return existing[0]

            # Create new funnel record
            cursor = await db.execute(
                """
                INSERT INTO analytics_conversion_funnel (telegram_user_id, reached_signup, signup_at)
                VALUES (?, 1, datetime('now'))
                """,
                (telegram_user_id,),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_funnel_first_query(self, telegram_user_id: int, timestamp: str) -> None:
        """Mark first query milestone in conversion funnel."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE analytics_conversion_funnel
                SET reached_first_query = 1, first_query_at = ?
                WHERE telegram_user_id = ? AND reached_first_query = 0
                """,
                (timestamp, telegram_user_id),
            )
            await db.commit()

    async def update_funnel_purchase(
        self,
        telegram_user_id: int,
        timestamp: str,
    ) -> None:
        """Mark purchase milestone in conversion funnel and calculate queries_before_upgrade."""
        async with aiosqlite.connect(self.db_path) as db:
            # Get current event count before this purchase
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM analytics_events
                WHERE telegram_user_id = ? AND event_type = 'chat_query'
                AND created_at < ?
                """,
                (telegram_user_id, timestamp),
            )
            queries_before = (await cursor.fetchone())[0] or 0

            # Update funnel record
            await db.execute(
                """
                UPDATE analytics_conversion_funnel
                SET reached_purchase = 1, purchase_at = ?, queries_before_upgrade = ?
                WHERE telegram_user_id = ? AND reached_purchase = 0
                """,
                (timestamp, queries_before, telegram_user_id),
            )
            await db.commit()

    # ========== Dashboard Aggregations ==========

    async def get_overview_stats(self) -> Dict[str, Any]:
        """Get overview statistics for dashboard."""
        async with aiosqlite.connect(self.db_path) as db:
            # Total users
            cursor = await db.execute("SELECT COUNT(*) FROM telegram_users")
            total_users = (await cursor.fetchone())[0] or 0

            # MRR calculation (sum of active subscriptions)
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(CASE
                    WHEN tier = 'starter' THEN 12
                    WHEN tier = 'pro' THEN 24
                    WHEN tier = 'unlimited' THEN 39
                    WHEN tier = 'enterprise' THEN 39
                    ELSE 0
                END), 0)
                FROM telegram_users
                WHERE tier IN ('starter', 'pro', 'unlimited', 'enterprise')
                AND subscription_ends_at > datetime('now')
                """
            )
            mrr = (await cursor.fetchone())[0] or 0

            # Active users (logged in past 7 days)
            cursor = await db.execute(
                """
                SELECT COUNT(DISTINCT telegram_user_id)
                FROM analytics_events
                WHERE event_type IN ('user_login', 'chat_query')
                AND created_at > datetime('now', '-7 days')
                """
            )
            active_users = (await cursor.fetchone())[0] or 0

            # Queries today
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM analytics_events
                WHERE event_type = 'chat_query'
                AND created_at > datetime('now', 'start of day')
                """
            )
            queries_today = (await cursor.fetchone())[0] or 0

            # Calculate percentage changes (last 7 days vs previous 7 days)
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM telegram_users
                WHERE created_at > datetime('now', '-14 days', 'start of day')
                AND created_at < datetime('now', '-7 days', 'start of day')
                """
            )
            prev_new_users = (await cursor.fetchone())[0] or 1
            users_change = ((total_users - prev_new_users) / prev_new_users * 100) if prev_new_users > 0 else 0

            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM analytics_events
                WHERE event_type = 'chat_query'
                AND created_at > datetime('now', '-14 days', 'start of day')
                AND created_at < datetime('now', '-7 days', 'start of day')
                """
            )
            prev_queries = (await cursor.fetchone())[0] or 1
            queries_change = ((queries_today - prev_queries) / prev_queries * 100) if prev_queries > 0 else 0

            return {
                "totalUsers": total_users,
                "totalUsersChange": round(users_change, 1),
                "mrr": round(mrr, 2),
                "mrrChange": 0,  # Would need historical data
                "activeUsers": active_users,
                "activeUsersChange": 0,  # Would need historical data
                "queriesToday": queries_today,
                "queriesTodayChange": round(queries_change, 1),
            }

    async def get_revenue_timeline(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily revenue breakdown for the last N days."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT
                    DATE(ph.created_at) as date,
                    COUNT(CASE WHEN ph.payment_type = 'subscription' THEN 1 END) as newSubscriptions,
                    COUNT(CASE WHEN ph.status = 'refunded' THEN 1 END) as refunds,
                    COALESCE(SUM(CASE
                        WHEN ph.tier = 'starter' THEN 12
                        WHEN ph.tier = 'pro' THEN 24
                        WHEN ph.tier = 'unlimited' THEN 39
                        ELSE 0
                    END), 0) as revenue
                FROM payment_history ph
                WHERE ph.created_at > datetime('now', '-' || ? || ' days')
                GROUP BY DATE(ph.created_at)
                ORDER BY date DESC
                """,
                (days,),
            )
            rows = await cursor.fetchall()

            # Fill in missing dates with zeros
            result = []
            for date_str, new_subs, refunds, revenue in (rows or []):
                result.append({
                    "date": date_str,
                    "revenue": float(revenue),
                    "newSubscriptions": new_subs,
                    "renewals": 0,  # Would need historical subscription data
                })

            return result[::-1]  # Reverse to chronological order

    async def get_tier_distribution(self) -> List[Dict[str, Any]]:
        """Get user count breakdown by subscription tier."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT tier, COUNT(*) as count
                FROM telegram_users
                GROUP BY tier
                ORDER BY count DESC
                """
            )
            rows = await cursor.fetchall()

            total = sum(count for _, count in rows)
            result = []
            for tier, count in rows:
                result.append({
                    "tier": tier,
                    "count": count,
                    "percentage": round((count / total * 100), 1) if total > 0 else 0,
                })

            return result

    async def get_conversion_funnel(self) -> List[Dict[str, Any]]:
        """Get conversion funnel stages with counts and conversion rates."""
        async with aiosqlite.connect(self.db_path) as db:
            # Get signup count
            cursor = await db.execute(
                "SELECT COUNT(*) FROM telegram_users WHERE created_at > datetime('now', '-30 days')"
            )
            signups = (await cursor.fetchone())[0] or 1

            # Get first query count
            cursor = await db.execute(
                """
                SELECT COUNT(DISTINCT telegram_user_id) FROM analytics_events
                WHERE event_type = 'chat_query'
                AND created_at > datetime('now', '-30 days')
                """
            )
            first_query = (await cursor.fetchone())[0] or 0

            # Get paid users count
            cursor = await db.execute(
                """
                SELECT COUNT(DISTINCT telegram_user_id) FROM telegram_users
                WHERE tier IN ('starter', 'pro', 'unlimited', 'enterprise')
                AND created_at > datetime('now', '-30 days')
                """
            )
            paid = (await cursor.fetchone())[0] or 0

            return [
                {
                    "name": "Signups",
                    "count": signups,
                    "percentage": 100.0,
                },
                {
                    "name": "First Query",
                    "count": first_query,
                    "percentage": round((first_query / signups * 100), 1) if signups > 0 else 0,
                },
                {
                    "name": "Paid Users",
                    "count": paid,
                    "percentage": round((paid / signups * 100), 1) if signups > 0 else 0,
                },
            ]

    async def get_usage_by_tier(self) -> List[Dict[str, Any]]:
        """Get query volume by subscription tier."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT ae.user_tier, COUNT(*) as queries
                FROM analytics_events ae
                WHERE ae.event_type = 'chat_query'
                GROUP BY ae.user_tier
                ORDER BY queries DESC
                """
            )
            rows = await cursor.fetchall()

            return [
                {
                    "tier": tier,
                    "queries": count,
                }
                for tier, count in (rows or [])
            ]

    async def get_users_paginated(
        self,
        page: int = 1,
        per_page: int = 20,
        search: str = "",
        tier: str = "",
        sort: str = "created",
    ) -> Dict[str, Any]:
        """Get paginated list of users with optional filtering and sorting."""
        per_page = min(per_page, 100)  # Cap at 100
        offset = (page - 1) * per_page

        # Build query
        where_clauses = []
        params: List[Any] = []

        if search:
            where_clauses.append(
                "(first_name LIKE ? OR last_name LIKE ? OR username LIKE ? OR telegram_id = ?)"
            )
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param, search if search.isdigit() else -1])

        if tier and tier != "all":
            where_clauses.append("tier = ?")
            params.append(tier)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Determine sort column
        sort_col = "created_at" if sort == "created" else sort
        sort_sql = f"ORDER BY {sort_col} DESC"

        # Get total count
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"SELECT COUNT(*) FROM telegram_users WHERE {where_sql}",
                params,
            )
            total = (await cursor.fetchone())[0] or 0

            # Get paginated results
            cursor = await db.execute(
                f"""
                SELECT id, telegram_id, first_name, last_name, username, tier,
                       queries_used, queries_remaining, subscription_ends_at, created_at
                FROM telegram_users
                WHERE {where_sql}
                {sort_sql}
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset],
            )
            rows = await cursor.fetchall()

            users = [
                {
                    "telegramId": row[1],
                    "firstName": row[2],
                    "lastName": row[3],
                    "username": row[4],
                    "tier": row[5],
                    "queriesUsed": row[6],
                    "queriesRemaining": row[7],
                    "subscriptionEndsAt": row[8],
                    "createdAt": row[9],
                    "lastActive": None,  # Would need to fetch from events
                }
                for row in rows
            ]

            pages = (total + per_page - 1) // per_page

            return {
                "users": users,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "pages": pages,
                },
            }

    async def get_user_history(self, telegram_id: int) -> Dict[str, Any]:
        """Get detailed history for a specific user."""
        async with aiosqlite.connect(self.db_path) as db:
            # Get user info
            cursor = await db.execute(
                """
                SELECT id, telegram_id, first_name, last_name, username, tier,
                       queries_used, queries_remaining, subscription_ends_at, created_at
                FROM telegram_users
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
            user_row = await cursor.fetchone()
            if not user_row:
                return {"error": "User not found"}

            user_id = user_row[0]

            # Get user's events
            cursor = await db.execute(
                """
                SELECT ae.id, ae.event_type, ae.created_at, ae.metadata,
                       aqm.query_text, aqm.response_time_ms, aqm.source_count
                FROM analytics_events ae
                LEFT JOIN analytics_query_metadata aqm ON ae.id = aqm.event_id
                WHERE ae.telegram_user_id = ?
                ORDER BY ae.created_at DESC
                LIMIT 100
                """,
                (user_id,),
            )
            events = []
            for row in await cursor.fetchall():
                events.append({
                    "id": row[0],
                    "type": row[1],
                    "timestamp": row[2],
                    "metadata": json.loads(row[3]) if row[3] else None,
                    "queryText": row[4],
                    "responseTime": row[5],
                    "sourceCount": row[6],
                })

            return {
                "user": {
                    "telegramId": user_row[1],
                    "firstName": user_row[2],
                    "lastName": user_row[3],
                    "username": user_row[4],
                    "tier": user_row[5],
                    "queriesUsed": user_row[6],
                    "queriesRemaining": user_row[7],
                    "subscriptionEndsAt": user_row[8],
                    "createdAt": user_row[9],
                },
                "events": events,
            }


# Global instance
analytics_repo = AnalyticsRepository()
