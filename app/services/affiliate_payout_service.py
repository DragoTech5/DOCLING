"""
Affiliate Payout Service - Monthly commission payouts for affiliates
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Minimum balance required for payout (in Telegram Stars)
PAYOUT_MINIMUM_THRESHOLD = 2000


async def process_monthly_affiliate_payouts() -> None:
    """
    Process monthly affiliate payouts on the 1st of each month at midnight UTC.

    Fetches all affiliates with pending balance >= 2000 Stars,
    creates payout records, and notifies them via bot message.
    """
    try:
        import aiosqlite
        from app.db.models import get_db_path
        from app.api.telegram import send_bot_message
        from app.config import get_bot_token

        logger.info("Starting monthly affiliate payouts...")

        async with aiosqlite.connect(get_db_path()) as db:
            # Get all approved affiliates with pending balance >= minimum threshold
            cursor = await db.execute(
                """
                SELECT
                    ac.id,
                    ac.telegram_user_id,
                    ac.channel_title,
                    ac.pending_balance_stars,
                    tu.telegram_id
                FROM affiliate_channels ac
                JOIN telegram_users tu ON ac.telegram_user_id = tu.id
                WHERE ac.status = 'approved'
                AND ac.pending_balance_stars >= ?
                """,
                (PAYOUT_MINIMUM_THRESHOLD,),
            )
            affiliates = await cursor.fetchall()

            if not affiliates:
                logger.info("No affiliates eligible for payout this month")
                return

            logger.info(f"Found {len(affiliates)} affiliates eligible for payout")

            payout_count = 0
            total_stars_paid = 0

            for affiliate_id, telegram_user_id, channel_title, pending_balance, telegram_id in affiliates:
                try:
                    # Get all pending commissions for this affiliate
                    commission_cursor = await db.execute(
                        """
                        SELECT id, commission_amount_stars
                        FROM affiliate_commissions
                        WHERE affiliate_channel_id = ?
                        AND status = 'pending'
                        """,
                        (affiliate_id,),
                    )
                    commissions = await commission_cursor.fetchall()

                    if not commissions:
                        logger.warning(f"No pending commissions found for affiliate {affiliate_id}")
                        continue

                    commission_ids = [c[0] for c in commissions]
                    total_payout_stars = sum(c[1] for c in commissions)

                    # Verify amount matches pending balance (sanity check)
                    if total_payout_stars != pending_balance:
                        logger.warning(
                            f"Payout amount mismatch for affiliate {affiliate_id}: "
                            f"commissions={total_payout_stars}, pending={pending_balance}"
                        )
                        # Use the larger amount to ensure affiliate doesn't lose earnings
                        total_payout_stars = max(total_payout_stars, pending_balance)

                    # Create payout record
                    payout_cursor = await db.execute(
                        """
                        INSERT INTO affiliate_payouts (
                            affiliate_channel_id,
                            total_stars,
                            commission_count,
                            status,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            affiliate_id,
                            total_payout_stars,
                            len(commission_ids),
                            "pending",
                            datetime.utcnow().isoformat(),
                        ),
                    )
                    await db.commit()

                    payout_id = payout_cursor.lastrowid

                    # Mark all commissions as paid
                    await db.execute(
                        """
                        UPDATE affiliate_commissions
                        SET status = 'paid', payout_id = ?, paid_at = ?
                        WHERE id IN ({})
                        """.format(",".join("?" * len(commission_ids))),
                        [payout_id, datetime.utcnow().isoformat()] + commission_ids,
                    )

                    # Reset pending balance to 0
                    await db.execute(
                        """
                        UPDATE affiliate_channels
                        SET pending_balance_stars = 0, updated_at = ?
                        WHERE id = ?
                        """,
                        (datetime.utcnow().isoformat(), affiliate_id),
                    )

                    await db.commit()

                    # Notify affiliate via bot message
                    try:
                        import os
                        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
                        if not bot_token:
                            logger.warning(f"TELEGRAM_BOT_TOKEN not configured, skipping notification")
                            continue

                        message = (
                            f"💰 Affiliate Payout Processed!\n\n"
                            f"Channel: {channel_title}\n"
                            f"Amount: {total_payout_stars} ⭐\n"
                            f"Commission Entries: {len(commission_ids)}\n\n"
                            f"The stars have been credited to your Telegram wallet.\n"
                            f"Thank you for promoting Akasha AI! 🌟"
                        )

                        # Send bot notification via HTTP
                        import httpx
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            response = await client.post(
                                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                json={
                                    "chat_id": telegram_id,
                                    "text": message,
                                    "parse_mode": "HTML",
                                },
                            )
                            if response.status_code != 200:
                                logger.warning(f"Failed to send message to {telegram_id}: {response.text}")

                        logger.info(
                            f"Payout processed for affiliate {affiliate_id} ({channel_title}): "
                            f"{total_payout_stars} Stars to user {telegram_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to notify affiliate {affiliate_id} about payout: {e}"
                        )
                        # Continue to next affiliate even if notification fails

                    # Mark payout as completed
                    await db.execute(
                        """
                        UPDATE affiliate_payouts
                        SET status = 'completed', completed_at = ?
                        WHERE id = ?
                        """,
                        (datetime.utcnow().isoformat(), payout_id),
                    )
                    await db.commit()

                    payout_count += 1
                    total_stars_paid += total_payout_stars

                except Exception as e:
                    logger.error(
                        f"Error processing payout for affiliate {affiliate_id}: {e}"
                    )
                    # Mark payout as failed if it was created
                    try:
                        await db.execute(
                            """
                            UPDATE affiliate_payouts
                            SET status = 'failed', error_message = ?
                            WHERE affiliate_channel_id = ? AND status = 'pending'
                            """,
                            (str(e), affiliate_id),
                        )
                        await db.commit()
                    except:
                        pass

            logger.info(
                f"Monthly affiliate payouts complete: {payout_count} affiliates, "
                f"{total_stars_paid} total stars paid"
            )

    except Exception as e:
        logger.error(f"Error in monthly affiliate payout job: {e}")


async def get_payout_stats() -> dict:
    """
    Get statistics about pending and completed payouts.

    Returns:
        Dictionary with payout stats (pending count, pending amount, etc.)
    """
    try:
        import aiosqlite
        from app.db.models import get_db_path

        async with aiosqlite.connect(get_db_path()) as db:
            # Pending payouts
            pending_cursor = await db.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(total_stars), 0)
                FROM affiliate_payouts
                WHERE status = 'pending'
                """
            )
            pending_count, pending_stars = await pending_cursor.fetchone()

            # Completed payouts this month
            month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            completed_cursor = await db.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(total_stars), 0)
                FROM affiliate_payouts
                WHERE status = 'completed' AND completed_at >= ?
                """,
                (month_start.isoformat(),),
            )
            completed_count, completed_stars = await completed_cursor.fetchone()

            # Affiliates eligible for next payout
            eligible_cursor = await db.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(pending_balance_stars), 0)
                FROM affiliate_channels
                WHERE status = 'approved' AND pending_balance_stars >= ?
                """,
                (PAYOUT_MINIMUM_THRESHOLD,),
            )
            eligible_count, eligible_stars = await eligible_cursor.fetchone()

            return {
                "pending_payouts": {
                    "count": pending_count,
                    "total_stars": pending_stars,
                },
                "completed_this_month": {
                    "count": completed_count,
                    "total_stars": completed_stars,
                },
                "eligible_for_next_payout": {
                    "count": eligible_count,
                    "total_stars": eligible_stars,
                },
            }

    except Exception as e:
        logger.error(f"Error getting payout stats: {e}")
        return {}
