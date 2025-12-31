"""
Cookie Refresher - Automatically refresh YouTube cookies from Chrome browser.

This module handles:
- Extracting cookies from Chrome browser using yt-dlp
- Detecting rate-limit and auth errors
- Auto-refreshing cookies when needed
- Automatically unlocking GNOME keyring when locked
"""

import asyncio
import subprocess
import logging
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.config import config, DATA_DIR

logger = logging.getLogger(__name__)


def unlock_gnome_keyring() -> bool:
    """
    Unlock the GNOME keyring collection if it's locked.

    The keyring can get locked due to system idle, session restart, or reboot.
    This function ensures cookies can be decrypted by yt-dlp.

    Returns:
        True if keyring is unlocked (or was already unlocked), False on error
    """
    try:
        import secretstorage

        # Get D-Bus address from environment or use default
        dbus_addr = os.environ.get('DBUS_SESSION_BUS_ADDRESS')
        if not dbus_addr:
            # Try common D-Bus socket locations
            uid = os.getuid()
            possible_paths = [
                f"/run/user/{uid}/bus",
                "/tmp/dbus-*",  # Will need glob
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    dbus_addr = f"unix:path={path}"
                    os.environ['DBUS_SESSION_BUS_ADDRESS'] = dbus_addr
                    break

        bus = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(bus)

        if collection.is_locked():
            logger.info("GNOME keyring is locked, attempting to unlock...")
            collection.unlock()

            if collection.is_locked():
                logger.error("Failed to unlock GNOME keyring")
                return False

            logger.info("GNOME keyring unlocked successfully")

        return True

    except ImportError:
        logger.warning("secretstorage not available - keyring unlock skipped")
        return True  # Continue anyway, yt-dlp might work without it
    except Exception as e:
        logger.error(f"Error unlocking keyring: {e}")
        return False

# Error patterns that indicate cookie/auth issues
RATE_LIMIT_PATTERNS = [
    r"rate.?limit",
    r"try again later",
    r"too many requests",
    r"429",
]

AUTH_ERROR_PATTERNS = [
    r"sign in to confirm",
    r"not a bot",
    r"cookies.*authentication",
    r"login required",
    r"private video",
    r"item does not exist",  # GNOME keyring locked/corrupted
    r"could not decrypt",  # Cookie decryption failed
]

# Combined patterns for errors that can be fixed by cookie refresh
COOKIE_REFRESH_PATTERNS = RATE_LIMIT_PATTERNS + AUTH_ERROR_PATTERNS


@dataclass
class CookieRefreshResult:
    """Result of cookie refresh attempt."""
    success: bool
    cookies_path: str | None = None
    cookies_count: int = 0
    error: str | None = None


class CookieRefresher:
    """Manages YouTube cookie refresh from Chrome browser."""

    def __init__(
        self,
        chrome_profile: str = "Profile 12",
        cookies_output_path: Path | None = None,
        min_refresh_interval: int = 300,  # 5 minutes minimum between refreshes
    ):
        self.chrome_profile = chrome_profile
        self.cookies_path = cookies_output_path or (DATA_DIR / "cookies" / "youtube.txt")
        self.min_refresh_interval = min_refresh_interval
        self._last_refresh: datetime | None = None
        self._refresh_lock = asyncio.Lock()

    def needs_refresh(self, error_message: str) -> bool:
        """Check if an error message indicates cookies need refreshing."""
        error_lower = error_message.lower()
        for pattern in COOKIE_REFRESH_PATTERNS:
            if re.search(pattern, error_lower):
                return True
        return False

    def is_rate_limited(self, error_message: str) -> bool:
        """Check if error indicates rate limiting."""
        error_lower = error_message.lower()
        for pattern in RATE_LIMIT_PATTERNS:
            if re.search(pattern, error_lower):
                return True
        return False

    def can_refresh(self) -> bool:
        """Check if enough time has passed since last refresh."""
        if self._last_refresh is None:
            return True
        elapsed = (datetime.now() - self._last_refresh).total_seconds()
        return elapsed >= self.min_refresh_interval

    async def refresh_cookies(self, force: bool = False) -> CookieRefreshResult:
        """
        Refresh cookies from Chrome browser.

        Args:
            force: If True, ignore minimum refresh interval

        Returns:
            CookieRefreshResult with success status
        """
        async with self._refresh_lock:
            # Check if we can refresh
            if not force and not self.can_refresh():
                wait_time = self.min_refresh_interval - (
                    datetime.now() - self._last_refresh
                ).total_seconds()
                return CookieRefreshResult(
                    success=False,
                    error=f"Rate limited - wait {int(wait_time)}s before next refresh"
                )

            logger.info(f"Refreshing cookies from Chrome profile: {self.chrome_profile}")

            # Ensure output directory exists
            self.cookies_path.parent.mkdir(parents=True, exist_ok=True)

            # Unlock GNOME keyring if locked (required for cookie decryption)
            if not unlock_gnome_keyring():
                logger.warning("Could not unlock keyring, cookie extraction may fail")

            # Use yt-dlp to extract cookies
            cmd = [
                "yt-dlp",
                f"--cookies-from-browser", f"chrome:{self.chrome_profile}",
                "--cookies", str(self.cookies_path),
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Test video
                "--skip-download",
                "--quiet",
            ]

            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                # Check if cookies file was created/updated
                if self.cookies_path.exists():
                    with open(self.cookies_path) as f:
                        lines = f.readlines()
                    cookies_count = sum(1 for line in lines if not line.startswith('#') and line.strip())

                    self._last_refresh = datetime.now()
                    logger.info(f"Cookies refreshed successfully: {cookies_count} cookies")

                    return CookieRefreshResult(
                        success=True,
                        cookies_path=str(self.cookies_path),
                        cookies_count=cookies_count,
                    )
                else:
                    return CookieRefreshResult(
                        success=False,
                        error="Cookies file not created"
                    )

            except subprocess.TimeoutExpired:
                return CookieRefreshResult(
                    success=False,
                    error="Cookie extraction timed out"
                )
            except Exception as e:
                return CookieRefreshResult(
                    success=False,
                    error=str(e)
                )

    def get_wait_time_for_rate_limit(self, attempt: int = 1) -> int:
        """
        Calculate wait time for rate limit with exponential backoff.

        Args:
            attempt: Current retry attempt number (1-based)

        Returns:
            Wait time in seconds
        """
        # Base wait time: 60 seconds, doubles each attempt, max 30 minutes
        base_wait = 60
        max_wait = 1800  # 30 minutes
        wait_time = min(base_wait * (2 ** (attempt - 1)), max_wait)
        return wait_time


# Global instance
_cookie_refresher: CookieRefresher | None = None


def get_cookie_refresher() -> CookieRefresher:
    """Get or create the global cookie refresher instance."""
    global _cookie_refresher
    if _cookie_refresher is None:
        # Get Chrome profile from config or use default
        chrome_profile = config.youtube.chrome_profile or "Profile 12"
        cookies_path = Path(config.youtube.cookies_file) if config.youtube.cookies_file else None
        _cookie_refresher = CookieRefresher(
            chrome_profile=chrome_profile,
            cookies_output_path=cookies_path,
        )
    return _cookie_refresher


async def auto_refresh_cookies_if_needed(error_message: str) -> bool:
    """
    Automatically refresh cookies if the error indicates it's needed.

    Args:
        error_message: The error message from yt-dlp

    Returns:
        True if cookies were refreshed successfully, False otherwise
    """
    refresher = get_cookie_refresher()

    if not refresher.needs_refresh(error_message):
        return False

    if not refresher.can_refresh():
        logger.warning("Cookie refresh needed but rate limited - waiting")
        return False

    result = await refresher.refresh_cookies()

    if result.success:
        logger.info(f"Auto-refreshed {result.cookies_count} cookies")
        return True
    else:
        logger.error(f"Cookie refresh failed: {result.error}")
        return False
