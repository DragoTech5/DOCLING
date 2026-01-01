"""
Dodo Payments integration service.
Handles checkout session creation, webhook verification, and payment processing.
"""

import os
import logging
import requests
import hmac
import hashlib
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DodoPaymentsService:
    """Service for interacting with Dodo Payments API."""

    # DODO Product ID mapping for subscription tiers
    PRODUCT_IDS = {
        "starter": "pdt_0NVHJtzTmrsZrJ0yfT38v",
        "pro": "pdt_0NVHPtTYToUhm5ZXE39S1",
        "unlimited": "pdt_0NVHQAS9r1ieO5bltXqQr",
    }

    def __init__(self):
        self.api_key = os.getenv("DODO_API_KEY")
        self.webhook_secret = os.getenv("DODO_WEBHOOK_SECRET")
        self.base_url = os.getenv("DODO_API_URL", "https://live.dodopayments.com")

        if not self.api_key:
            logger.warning("DODO_API_KEY not set in environment")
        if not self.webhook_secret:
            logger.warning("DODO_WEBHOOK_SECRET not set in environment")

    async def create_checkout_session(
        self,
        tier: str,
        amount_usd: int,
        customer_email: str,
        telegram_user_id: int,
        return_url_success: str,
        return_url_failure: str,
    ) -> Dict:
        """
        Create Dodo checkout session for subscription purchase.

        Args:
            tier: Subscription tier (researcher, unlimited)
            amount_usd: Amount in cents (1500, 3900, 9900)
            customer_email: Customer email address
            telegram_user_id: Telegram user ID for tracking
            return_url_success: URL to redirect after successful payment
            return_url_failure: URL to redirect after failed payment

        Returns:
            Dict with checkout_session_id, checkout_url, and expires_at

        Raises:
            Exception: If Dodo API returns an error
        """
        # Get DODO product ID for this tier
        product_id = self.PRODUCT_IDS.get(tier)
        if not product_id:
            raise Exception(f"Invalid tier '{tier}': no DODO product ID configured")

        payload = {
            "product_cart": [
                {
                    "product_id": product_id,
                    "quantity": 1,
                }
            ],
            "customer": {
                "email": customer_email,
            },
            "metadata": {
                "telegram_user_id": str(telegram_user_id),
                "tier": tier,
            },
            "return_urls": {
                "success": return_url_success,
                "failure": return_url_failure,
                "cancel": return_url_failure,
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.base_url}/checkouts",
                json=payload,
                headers=headers,
                timeout=10,
            )

            if not response.ok:
                error_msg = response.text
                logger.error(f"Dodo API error: {response.status_code} - {error_msg}")
                raise Exception(f"Dodo API error: {error_msg}")

            data = response.json()

            logger.info(
                f"✅ Dodo checkout session created: {data.get('session_id')} for user {telegram_user_id}"
            )

            return {
                "checkout_session_id": data["session_id"],
                "checkout_url": data["checkout_url"],
                "expires_at": data.get("expires_at"),
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Dodo API request failed: {str(e)}")
            raise Exception(f"Payment provider connection error: {str(e)}")

    def verify_webhook_signature(
        self,
        webhook_id: str,
        webhook_timestamp: str,
        request_body: str,
        signature: str,
    ) -> bool:
        """
        Verify HMAC SHA256 signature from Dodo webhook.

        Critical for security - prevents webhook spoofing.

        Args:
            webhook_id: Webhook event ID from header
            webhook_timestamp: Webhook timestamp from header
            request_body: Raw request body as string
            signature: Signature from webhook-signature header

        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            logger.error("DODO_WEBHOOK_SECRET not configured")
            return False

        signed_content = f"{webhook_id}.{webhook_timestamp}.{request_body}"
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            signed_content.encode(),
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(expected_signature, signature)

        if not is_valid:
            logger.warning(
                f"Invalid webhook signature for event {webhook_id}. "
                f"Expected: {expected_signature[:16]}..., Got: {signature[:16]}..."
            )

        return is_valid

    async def process_payment_completed(
        self,
        payment_id: str,
        checkout_session_id: str,
        amount: int,
        customer_id: str,
        metadata: Dict,
    ) -> Dict:
        """
        Process successful payment from webhook.

        Extracts tier and telegram_user_id from metadata.

        Args:
            payment_id: Dodo payment ID
            checkout_session_id: Checkout session ID
            amount: Payment amount in cents
            customer_id: Dodo customer ID
            metadata: Payment metadata (contains telegram_user_id and tier)

        Returns:
            Dict with telegram_user_id, tier, amount_usd, and customer_id
        """
        return {
            "telegram_user_id": int(metadata.get("telegram_user_id", 0)),
            "tier": metadata.get("tier"),
            "amount_usd": amount,
            "customer_id": customer_id,
        }


# Global instance
dodo_service = DodoPaymentsService()
