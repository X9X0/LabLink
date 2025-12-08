"""mDNS/Zeroconf service discovery for LabLink server."""

import logging
import socket
from typing import Any, Dict, Optional

try:
    from zeroconf import ServiceInfo, Zeroconf

    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False
    # Define dummy types for type hints when zeroconf is not available
    Zeroconf = None  # type: ignore
    ServiceInfo = None  # type: ignore

logger = logging.getLogger(__name__)


class LabLinkMDNSService:
    """mDNS service broadcaster for LabLink server."""

    SERVICE_TYPE = "_lablink._tcp.local."

    def __init__(
        self,
        port: int = 8000,
        ws_port: int = 8001,
        server_name: Optional[str] = None,
        server_version: str = "1.0.0",
    ):
        """
        Initialize mDNS service.

        Args:
            port: HTTP API port
            ws_port: WebSocket port
            server_name: Server name (defaults to hostname)
            server_version: Server version
        """
        if not ZEROCONF_AVAILABLE:
            raise ImportError(
                "zeroconf is required for mDNS support. "
                "Install with: pip install zeroconf"
            )

        self.port = port
        self.ws_port = ws_port
        self.server_version = server_version

        # Get server name
        if server_name:
            self.server_name = server_name
        else:
            # Try to get FQDN first, fallback to hostname
            fqdn = socket.getfqdn()
            # Only use FQDN if it's actually different from the short hostname
            # and doesn't resolve to localhost
            hostname = socket.gethostname()
            if fqdn != hostname and not fqdn.startswith("localhost"):
                self.server_name = fqdn
            else:
                self.server_name = hostname

        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.running = False

        logger.info(f"Initialized mDNS service: {self.server_name}")

    def start(self) -> bool:
        """
        Start broadcasting mDNS service.

        Returns:
            True if started successfully, False otherwise
        """
        if not ZEROCONF_AVAILABLE:
            logger.error("Zeroconf not available")
            return False

        if self.running:
            logger.warning("mDNS service already running")
            return True

        try:
            # Create Zeroconf instance
            self.zeroconf = Zeroconf()

            # Get local IP address
            local_ip = self._get_local_ip()

            # Create service info
            service_name = f"{self.server_name}.{self.SERVICE_TYPE}"

            # Service properties
            properties = {
                "version": self.server_version,
                "api_port": str(self.port),
                "ws_port": str(self.ws_port),
                "hostname": self.server_name,
            }

            # Create service info
            self.service_info = ServiceInfo(
                type_=self.SERVICE_TYPE,
                name=service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties=properties,
                server=f"{self.server_name}.local.",
            )

            # Register service
            self.zeroconf.register_service(self.service_info)

            self.running = True

            logger.info(
                f"mDNS service started: {service_name} on {local_ip}:{self.port}"
            )
            logger.info(f"Service properties: {properties}")

            return True

        except Exception as e:
            logger.error(f"Failed to start mDNS service: {e}")
            self.stop()
            return False

    def stop(self):
        """Stop broadcasting mDNS service."""
        if not self.running:
            return

        try:
            if self.zeroconf and self.service_info:
                self.zeroconf.unregister_service(self.service_info)
                logger.info("mDNS service unregistered")

            if self.zeroconf:
                self.zeroconf.close()
                self.zeroconf = None

            self.service_info = None
            self.running = False

            logger.info("mDNS service stopped")

        except Exception as e:
            logger.error(f"Error stopping mDNS service: {e}")

    def update_properties(self, properties: Dict[str, str]):
        """
        Update service properties.

        Args:
            properties: New properties to set
        """
        if not self.running or not self.service_info:
            logger.warning("Cannot update properties: service not running")
            return

        try:
            # Update properties
            self.service_info.properties.update(properties)

            # Re-announce service
            if self.zeroconf:
                self.zeroconf.update_service(self.service_info)

            logger.info(f"Updated mDNS properties: {properties}")

        except Exception as e:
            logger.error(f"Failed to update mDNS properties: {e}")

    def _get_local_ip(self) -> str:
        """
        Get local IP address.

        Returns:
            Local IP address string
        """
        try:
            # Create a socket to get the local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)

            try:
                # Connect to a remote address (doesn't actually send data)
                s.connect(("10.255.255.255", 1))
                local_ip = s.getsockname()[0]
            except Exception:
                local_ip = "127.0.0.1"
            finally:
                s.close()

            return local_ip

        except Exception as e:
            logger.warning(f"Failed to get local IP: {e}, using 127.0.0.1")
            return "127.0.0.1"

    def get_service_info(self) -> Dict[str, Any]:
        """
        Get current service information.

        Returns:
            Dictionary with service info
        """
        return {
            "running": self.running,
            "server_name": self.server_name,
            "port": self.port,
            "ws_port": self.ws_port,
            "version": self.server_version,
            "service_type": self.SERVICE_TYPE,
        }

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

    def __del__(self):
        """Cleanup on deletion."""
        self.stop()
