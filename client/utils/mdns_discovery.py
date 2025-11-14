"""mDNS/Zeroconf service discovery for LabLink client."""

import logging
import socket
import time
from typing import Any, Callable, Dict, List, Optional

try:
    from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

logger = logging.getLogger(__name__)


class LabLinkServer:
    """Represents a discovered LabLink server."""

    def __init__(
        self,
        name: str,
        address: str,
        port: int,
        ws_port: int,
        properties: Dict[str, Any],
    ):
        """
        Initialize server info.

        Args:
            name: Server name
            address: IP address
            port: HTTP API port
            ws_port: WebSocket port
            properties: Additional properties
        """
        self.name = name
        self.address = address
        self.port = port
        self.ws_port = ws_port
        self.properties = properties
        self.discovered_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "address": self.address,
            "port": self.port,
            "ws_port": self.ws_port,
            "url": f"http://{self.address}:{self.port}",
            "ws_url": f"ws://{self.address}:{self.ws_port}/ws",
            "properties": self.properties,
            "discovered_at": self.discovered_at,
        }

    def __repr__(self):
        """String representation."""
        return (
            f"LabLinkServer(name='{self.name}', address='{self.address}:{self.port}')"
        )


class LabLinkDiscovery:
    """mDNS service discovery for LabLink servers."""

    SERVICE_TYPE = "_lablink._tcp.local."

    def __init__(self):
        """Initialize discovery service."""
        if not ZEROCONF_AVAILABLE:
            raise ImportError(
                "zeroconf is required for mDNS support. "
                "Install with: pip install zeroconf"
            )

        self.zeroconf: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None
        self.servers: Dict[str, LabLinkServer] = {}
        self.discovery_callbacks: List[Callable] = []
        self.running = False

        logger.info("Initialized mDNS discovery")

    def start(self, timeout: Optional[float] = None):
        """
        Start discovering LabLink servers.

        Args:
            timeout: Optional timeout for discovery (in seconds)
        """
        if not ZEROCONF_AVAILABLE:
            logger.error("Zeroconf not available")
            return

        if self.running:
            logger.warning("Discovery already running")
            return

        try:
            # Create Zeroconf instance
            self.zeroconf = Zeroconf()

            # Create service browser
            self.browser = ServiceBrowser(
                self.zeroconf,
                self.SERVICE_TYPE,
                handlers=[self._on_service_state_change],
            )

            self.running = True

            logger.info(f"Started discovering {self.SERVICE_TYPE} services")

            # If timeout specified, wait then stop
            if timeout:
                import threading

                def stop_after_timeout():
                    time.sleep(timeout)
                    self.stop()

                threading.Thread(target=stop_after_timeout, daemon=True).start()

        except Exception as e:
            logger.error(f"Failed to start discovery: {e}")
            self.stop()

    def stop(self):
        """Stop discovering services."""
        if not self.running:
            return

        try:
            if self.browser:
                self.browser.cancel()
                self.browser = None

            if self.zeroconf:
                self.zeroconf.close()
                self.zeroconf = None

            self.running = False

            logger.info("Stopped discovery")

        except Exception as e:
            logger.error(f"Error stopping discovery: {e}")

    def _on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ):
        """
        Handle service state change.

        Args:
            zeroconf: Zeroconf instance
            service_type: Service type
            name: Service name
            state_change: State change type
        """
        try:
            if state_change is ServiceStateChange.Added:
                self._on_service_added(zeroconf, service_type, name)
            elif state_change is ServiceStateChange.Removed:
                self._on_service_removed(name)
            elif state_change is ServiceStateChange.Updated:
                self._on_service_updated(zeroconf, service_type, name)

        except Exception as e:
            logger.error(f"Error handling service state change: {e}")

    def _on_service_added(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Handle service added."""
        info = zeroconf.get_service_info(service_type, name)

        if info is None:
            logger.warning(f"Could not get info for service: {name}")
            return

        try:
            # Extract server info
            address = socket.inet_ntoa(info.addresses[0])
            port = info.port

            # Extract properties
            properties = {}
            for key, value in info.properties.items():
                try:
                    properties[key.decode("utf-8")] = value.decode("utf-8")
                except:
                    pass

            # Get WebSocket port from properties
            ws_port = int(properties.get("ws_port", port + 1))

            # Get server name
            server_name = properties.get("hostname", name.split(".")[0])

            # Create server object
            server = LabLinkServer(
                name=server_name,
                address=address,
                port=port,
                ws_port=ws_port,
                properties=properties,
            )

            # Add to discovered servers
            self.servers[name] = server

            logger.info(f"Discovered server: {server}")

            # Notify callbacks
            self._notify_callbacks("added", server)

        except Exception as e:
            logger.error(f"Error processing service info: {e}")

    def _on_service_removed(self, name: str):
        """Handle service removed."""
        if name in self.servers:
            server = self.servers.pop(name)
            logger.info(f"Server removed: {server}")

            # Notify callbacks
            self._notify_callbacks("removed", server)

    def _on_service_updated(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Handle service updated."""
        # Re-add with updated info
        self._on_service_added(zeroconf, service_type, name)

        if name in self.servers:
            server = self.servers[name]
            logger.info(f"Server updated: {server}")

            # Notify callbacks
            self._notify_callbacks("updated", server)

    def _notify_callbacks(self, event_type: str, server: LabLinkServer):
        """
        Notify registered callbacks.

        Args:
            event_type: Type of event ('added', 'removed', 'updated')
            server: Server that changed
        """
        for callback in self.discovery_callbacks:
            try:
                callback(event_type, server)
            except Exception as e:
                logger.error(f"Error in discovery callback: {e}")

    def register_callback(self, callback: Callable):
        """
        Register callback for discovery events.

        Args:
            callback: Callback function(event_type: str, server: LabLinkServer)
        """
        if callback not in self.discovery_callbacks:
            self.discovery_callbacks.append(callback)

    def unregister_callback(self, callback: Callable):
        """
        Unregister callback.

        Args:
            callback: Callback to remove
        """
        if callback in self.discovery_callbacks:
            self.discovery_callbacks.remove(callback)

    def get_servers(self) -> List[LabLinkServer]:
        """
        Get list of discovered servers.

        Returns:
            List of LabLinkServer objects
        """
        return list(self.servers.values())

    def get_servers_dict(self) -> List[Dict[str, Any]]:
        """
        Get list of discovered servers as dictionaries.

        Returns:
            List of server dictionaries
        """
        return [server.to_dict() for server in self.servers.values()]

    def find_server_by_name(self, name: str) -> Optional[LabLinkServer]:
        """
        Find server by name.

        Args:
            name: Server name to find

        Returns:
            LabLinkServer if found, None otherwise
        """
        for server in self.servers.values():
            if server.name == name:
                return server
        return None

    def find_server_by_address(self, address: str) -> Optional[LabLinkServer]:
        """
        Find server by IP address.

        Args:
            address: IP address to find

        Returns:
            LabLinkServer if found, None otherwise
        """
        for server in self.servers.values():
            if server.address == address:
                return server
        return None

    def clear(self):
        """Clear discovered servers list."""
        self.servers.clear()
        logger.info("Cleared discovered servers")

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


def discover_servers(timeout: float = 5.0) -> List[LabLinkServer]:
    """
    Convenience function to discover LabLink servers.

    Args:
        timeout: Discovery timeout in seconds

    Returns:
        List of discovered LabLinkServer objects
    """
    if not ZEROCONF_AVAILABLE:
        logger.error("Zeroconf not available")
        return []

    discovery = LabLinkDiscovery()

    try:
        discovery.start()
        time.sleep(timeout)
        servers = discovery.get_servers()
        return servers

    finally:
        discovery.stop()


def discover_servers_dict(timeout: float = 5.0) -> List[Dict[str, Any]]:
    """
    Convenience function to discover LabLink servers.

    Args:
        timeout: Discovery timeout in seconds

    Returns:
        List of server dictionaries
    """
    servers = discover_servers(timeout)
    return [server.to_dict() for server in servers]
