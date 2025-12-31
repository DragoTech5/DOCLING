"""
SSH Tunnel Manager for Remote PostgreSQL Access

Handles SSH tunneling to NAS PostgreSQL databases.
Allows Railway backend to securely access NAS databases.
"""

import logging
from contextlib import contextmanager
from typing import Optional

from sshtunnel import SSHTunnelForwarder

logger = logging.getLogger(__name__)


class SSHTunnelManager:
    """Manages SSH tunnels to remote PostgreSQL databases."""

    def __init__(
        self,
        ssh_host: str,
        ssh_username: str,
        ssh_password: str,
        remote_db_host: str = "127.0.0.1",
        remote_db_port: int = 5432,
        ssh_port: int = 22,
    ):
        """
        Initialize SSH tunnel manager.

        Args:
            ssh_host: SSH server hostname/IP (NAS)
            ssh_username: SSH username
            ssh_password: SSH password
            remote_db_host: Remote PostgreSQL host (localhost on NAS)
            remote_db_port: Remote PostgreSQL port
            ssh_port: SSH server port
        """
        self.ssh_host = ssh_host
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.remote_db_host = remote_db_host
        self.remote_db_port = remote_db_port
        self.ssh_port = ssh_port
        self.tunnel: Optional[SSHTunnelForwarder] = None
        self.local_bind_host = "127.0.0.1"
        self.local_bind_port: Optional[int] = None

    def start(self) -> tuple[str, int]:
        """
        Start the SSH tunnel.

        Returns:
            Tuple of (local_host, local_port) for database connection

        Raises:
            Exception: If tunnel fails to start
        """
        try:
            self.tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(self.ssh_host, self.ssh_port),
                ssh_username=self.ssh_username,
                ssh_password=self.ssh_password,
                remote_bind_address=(self.remote_db_host, self.remote_db_port),
                local_bind_address=(self.local_bind_host, 0),  # 0 = find free port
            )

            self.tunnel.start()
            self.local_bind_port = self.tunnel.local_bind_port

            logger.info(
                f"SSH tunnel established: {self.local_bind_host}:{self.local_bind_port} "
                f"-> {self.ssh_host}:{self.ssh_port} -> {self.remote_db_host}:{self.remote_db_port}"
            )

            return self.local_bind_host, self.local_bind_port
        except Exception as e:
            logger.error(f"Failed to establish SSH tunnel: {e}")
            raise

    def stop(self) -> None:
        """Stop the SSH tunnel."""
        if self.tunnel:
            try:
                self.tunnel.stop()
                logger.info("SSH tunnel closed")
            except Exception as e:
                logger.error(f"Error closing SSH tunnel: {e}")
            finally:
                self.tunnel = None
                self.local_bind_port = None

    def is_active(self) -> bool:
        """Check if tunnel is active."""
        return self.tunnel is not None and self.tunnel.is_active

    @contextmanager
    def tunnel_context(self):
        """Context manager for SSH tunnel."""
        try:
            self.start()
            yield self
        finally:
            self.stop()


# Global tunnel managers for each database
_magick_tunnel: Optional[SSHTunnelManager] = None
_bibliothek_tunnel: Optional[SSHTunnelManager] = None


def init_tunnels(
    nas_host: str,
    nas_username: str,
    nas_password: str,
) -> None:
    """
    Initialize SSH tunnels for both databases.

    Args:
        nas_host: NAS hostname/IP
        nas_username: NAS SSH username
        nas_password: NAS SSH password
    """
    global _magick_tunnel, _bibliothek_tunnel

    _magick_tunnel = SSHTunnelManager(
        ssh_host=nas_host,
        ssh_username=nas_username,
        ssh_password=nas_password,
        remote_db_host="127.0.0.1",
        remote_db_port=5432,
    )

    _bibliothek_tunnel = SSHTunnelManager(
        ssh_host=nas_host,
        ssh_username=nas_username,
        ssh_password=nas_password,
        remote_db_host="127.0.0.1",
        remote_db_port=5432,
    )

    logger.info("SSH tunnel managers initialized")


def get_magick_tunnel() -> SSHTunnelManager:
    """Get or create magick database tunnel."""
    global _magick_tunnel
    if _magick_tunnel is None:
        raise RuntimeError("SSH tunnels not initialized. Call init_tunnels first.")
    return _magick_tunnel


def get_bibliothek_tunnel() -> SSHTunnelManager:
    """Get or create bibliothek database tunnel."""
    global _bibliothek_tunnel
    if _bibliothek_tunnel is None:
        raise RuntimeError("SSH tunnels not initialized. Call init_tunnels first.")
    return _bibliothek_tunnel


def close_all_tunnels() -> None:
    """Close all SSH tunnels."""
    global _magick_tunnel, _bibliothek_tunnel

    if _magick_tunnel:
        _magick_tunnel.stop()
    if _bibliothek_tunnel:
        _bibliothek_tunnel.stop()

    logger.info("All SSH tunnels closed")
