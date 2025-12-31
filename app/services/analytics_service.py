"""
Analytics Service for non-blocking event tracking in Docling Knowledge Hub.
Provides fire-and-forget async event logging that never blocks user requests.
"""

import asyncio
import logging
from typing import Optional, Dict, Any

from app.db.analytics_repository import analytics_repo
from app.db.models import TelegramUserRecord

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for non-blocking analytics event tracking."""

    @staticmethod
    def _create_background_task(coro):
        """
        Create a fire-and-forget background task that won't block.
        Errors are logged but don't affect user requests.
        """
        task = asyncio.create_task(coro)

        def done_callback(t):
            try:
                t.result()
            except Exception as e:
                logger.error(f"Background task failed: {e}", exc_info=True)

        task.add_done_callback(done_callback)
        return task

    @classmethod
    async def track_event(
        cls,
        event_type: str,
        user: TelegramUserRecord,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        Track a generic event (fire-and-forget).

        Args:
            event_type: Type of event
            user: Telegram user record
            metadata: Optional metadata
            session_id: Optional session ID

        Returns:
            Event ID (if tracked synchronously)
        """
        try:
            return await analytics_repo.create_event(user, event_type, metadata, session_id)
        except Exception as e:
            logger.error(f"Failed to track event {event_type}: {e}")
            return None

    @classmethod
    async def track_user_signup(cls, user: TelegramUserRecord) -> None:
        """
        Track user signup event and initialize conversion funnel.
        Non-blocking.
        """
        async def _track():
            try:
                # Track signup event
                await analytics_repo.create_event(user, "user_signup")

                # Initialize conversion funnel
                await analytics_repo.initialize_conversion_funnel(user["id"])
            except Exception as e:
                logger.error(f"Failed to track signup for user {user['telegram_id']}: {e}")

        cls._create_background_task(_track())

    @classmethod
    async def track_user_login(cls, user: TelegramUserRecord) -> None:
        """
        Track user login event.
        Non-blocking.
        """
        async def _track():
            try:
                await analytics_repo.create_event(user, "user_login")
            except Exception as e:
                logger.error(f"Failed to track login for user {user['telegram_id']}: {e}")

        cls._create_background_task(_track())

    @classmethod
    async def track_chat_query(
        cls,
        telegram_user: TelegramUserRecord,
        conversation_id: int,
        query_text: str,
        collection: str,
        selected_doc_ids: Optional[list] = None,
        session_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        Track a chat query event with metadata.
        Returns event ID for later updates.

        Args:
            telegram_user: Telegram user record
            conversation_id: Associated conversation ID
            query_text: The user's query
            collection: Collection being queried (maglib, bibliothek, etc.)
            selected_doc_ids: Optional list of selected document IDs
            session_id: Optional session ID

        Returns:
            Event ID (needed for metric updates after response)
        """
        try:
            # Create event first (synchronous, returns event ID)
            event_id = await analytics_repo.create_event(
                telegram_user,
                "chat_query",
                metadata={"collection": collection},
                session_id=session_id,
            )

            # Create query metadata (can be async)
            doc_count = len(selected_doc_ids) if selected_doc_ids else 0

            async def _create_metadata():
                try:
                    await analytics_repo.create_query_metadata(
                        event_id,
                        conversation_id,
                        query_text,
                        collection,
                        selected_doc_count=doc_count,
                    )
                except Exception as e:
                    logger.error(f"Failed to create query metadata for event {event_id}: {e}")

            cls._create_background_task(_create_metadata())

            return event_id

        except Exception as e:
            logger.error(f"Failed to track chat query for user {telegram_user['telegram_id']}: {e}")
            return None

    @classmethod
    async def update_query_metrics(
        cls,
        event_id: Optional[int],
        response_time_ms: Optional[int] = None,
        chunk_count: Optional[int] = None,
        source_count: Optional[int] = None,
    ) -> None:
        """
        Update query metrics after response is generated.
        Non-blocking.

        Args:
            event_id: Event ID from track_chat_query
            response_time_ms: Response time in milliseconds
            chunk_count: Number of chunks retrieved
            source_count: Number of sources in response
        """
        if not event_id:
            return

        async def _update():
            try:
                await analytics_repo.update_query_metadata(
                    event_id,
                    response_time_ms=response_time_ms,
                    chunk_count=chunk_count,
                    source_count=source_count,
                )

                # Update conversion funnel first query if not already marked
                # This would require tracking which user this event belongs to
                # For now, we keep it simple
            except Exception as e:
                logger.error(f"Failed to update query metrics for event {event_id}: {e}")

        cls._create_background_task(_update())

    @classmethod
    async def track_subscription_purchase(
        cls,
        telegram_user: TelegramUserRecord,
        tier: str,
        amount_stars: int,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Track subscription purchase and update conversion funnel.
        Non-blocking.

        Args:
            telegram_user: Telegram user record
            tier: Subscription tier
            amount_stars: Amount paid in Telegram Stars
            session_id: Optional session ID
        """
        async def _track():
            try:
                # Track purchase event
                await analytics_repo.create_event(
                    telegram_user,
                    "subscription_purchase",
                    metadata={
                        "tier": tier,
                        "amount_stars": amount_stars,
                    },
                    session_id=session_id,
                )

                # Update conversion funnel - mark purchase milestone
                from datetime import datetime
                timestamp = datetime.now().isoformat()
                await analytics_repo.update_funnel_purchase(telegram_user["id"], timestamp)

            except Exception as e:
                logger.error(f"Failed to track purchase for user {telegram_user['telegram_id']}: {e}")

        cls._create_background_task(_track())

    @classmethod
    async def track_document_browse(
        cls,
        telegram_user: TelegramUserRecord,
        collection: str,
        page: int = 1,
        result_count: int = 0,
    ) -> None:
        """
        Track document browsing activity.
        Non-blocking.
        """
        async def _track():
            try:
                await analytics_repo.create_event(
                    telegram_user,
                    "document_browse",
                    metadata={
                        "collection": collection,
                        "page": page,
                        "result_count": result_count,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to track document browse for user {telegram_user['telegram_id']}: {e}")

        cls._create_background_task(_track())

    @classmethod
    async def track_conversation_saved(
        cls,
        telegram_user: TelegramUserRecord,
        conversation_id: int,
        doc_count: int,
    ) -> None:
        """
        Track saved conversation event.
        Non-blocking.
        """
        async def _track():
            try:
                await analytics_repo.create_event(
                    telegram_user,
                    "conversation_saved",
                    metadata={
                        "conversation_id": conversation_id,
                        "doc_count": doc_count,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to track conversation save for user {telegram_user['telegram_id']}: {e}")

        cls._create_background_task(_track())


# Global instance
analytics_service = AnalyticsService()
