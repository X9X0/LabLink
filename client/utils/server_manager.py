"""Multi-server connection management."""

import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ServerConnection:
    """Represents a server connection."""

    name: str
    host: str
    api_port: int
    ws_port: int
    connected: bool = False
    last_connected: Optional[datetime] = None
    client: Optional[object] = None  # LabLinkClient instance
    user: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'host': self.host,
            'api_port': self.api_port,
            'ws_port': self.ws_port,
            'last_connected': self.last_connected.isoformat() if self.last_connected else None,
            'user': self.user,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ServerConnection':
        """Create from dictionary."""
        last_connected = None
        if data.get('last_connected'):
            try:
                last_connected = datetime.fromisoformat(data['last_connected'])
            except:
                pass

        return cls(
            name=data['name'],
            host=data['host'],
            api_port=data['api_port'],
            ws_port=data['ws_port'],
            last_connected=last_connected,
            user=data.get('user'),
            metadata=data.get('metadata', {})
        )


class ServerManager:
    """Manages multiple server connections."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize server manager.

        Args:
            config_path: Path to server configuration file
        """
        if config_path is None:
            config_path = Path.home() / ".lablink" / "servers.json"

        self.config_path = config_path
        self.servers: Dict[str, ServerConnection] = {}
        self.active_server: Optional[str] = None

        self._load_servers()

    def _load_servers(self):
        """Load servers from configuration file."""
        if not self.config_path.exists():
            logger.info("No server configuration found, starting fresh")
            return

        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)

            self.servers = {
                name: ServerConnection.from_dict(server_data)
                for name, server_data in data.get('servers', {}).items()
            }

            self.active_server = data.get('active_server')

            logger.info(f"Loaded {len(self.servers)} server configurations")

        except Exception as e:
            logger.error(f"Failed to load server configuration: {e}")

    def _save_servers(self):
        """Save servers to configuration file."""
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'servers': {
                    name: server.to_dict()
                    for name, server in self.servers.items()
                },
                'active_server': self.active_server
            }

            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug("Server configuration saved")

        except Exception as e:
            logger.error(f"Failed to save server configuration: {e}")

    def add_server(self, name: str, host: str, api_port: int, ws_port: int,
                   metadata: Optional[Dict] = None) -> ServerConnection:
        """Add a new server.

        Args:
            name: Server name
            host: Hostname or IP address
            api_port: API port
            ws_port: WebSocket port
            metadata: Additional metadata

        Returns:
            ServerConnection instance
        """
        if name in self.servers:
            raise ValueError(f"Server '{name}' already exists")

        server = ServerConnection(
            name=name,
            host=host,
            api_port=api_port,
            ws_port=ws_port,
            metadata=metadata or {}
        )

        self.servers[name] = server
        self._save_servers()

        logger.info(f"Added server: {name} ({host}:{api_port})")

        return server

    def remove_server(self, name: str):
        """Remove a server.

        Args:
            name: Server name
        """
        if name not in self.servers:
            raise ValueError(f"Server '{name}' not found")

        server = self.servers[name]

        if server.connected:
            raise ValueError(f"Cannot remove connected server '{name}'")

        del self.servers[name]

        if self.active_server == name:
            self.active_server = None

        self._save_servers()

        logger.info(f"Removed server: {name}")

    def update_server(self, name: str, **kwargs):
        """Update server configuration.

        Args:
            name: Server name
            **kwargs: Fields to update
        """
        if name not in self.servers:
            raise ValueError(f"Server '{name}' not found")

        server = self.servers[name]

        for key, value in kwargs.items():
            if hasattr(server, key):
                setattr(server, key, value)

        self._save_servers()

        logger.info(f"Updated server: {name}")

    def get_server(self, name: str) -> Optional[ServerConnection]:
        """Get server by name.

        Args:
            name: Server name

        Returns:
            ServerConnection or None
        """
        return self.servers.get(name)

    def list_servers(self) -> List[ServerConnection]:
        """List all servers.

        Returns:
            List of ServerConnection instances
        """
        return list(self.servers.values())

    def set_active_server(self, name: Optional[str]):
        """Set the active server.

        Args:
            name: Server name or None
        """
        if name is not None and name not in self.servers:
            raise ValueError(f"Server '{name}' not found")

        self.active_server = name
        self._save_servers()

        logger.info(f"Active server set to: {name}")

    def get_active_server(self) -> Optional[ServerConnection]:
        """Get the active server.

        Returns:
            Active ServerConnection or None
        """
        if self.active_server is None:
            return None

        return self.servers.get(self.active_server)

    def mark_connected(self, name: str, client: object, user: Optional[str] = None):
        """Mark a server as connected.

        Args:
            name: Server name
            client: LabLinkClient instance
            user: Username
        """
        if name not in self.servers:
            raise ValueError(f"Server '{name}' not found")

        server = self.servers[name]
        server.connected = True
        server.last_connected = datetime.now()
        server.client = client
        server.user = user

        self._save_servers()

        logger.info(f"Server '{name}' marked as connected")

    def mark_disconnected(self, name: str):
        """Mark a server as disconnected.

        Args:
            name: Server name
        """
        if name not in self.servers:
            return

        server = self.servers[name]
        server.connected = False
        server.client = None

        logger.info(f"Server '{name}' marked as disconnected")

    def get_connected_servers(self) -> List[ServerConnection]:
        """Get list of connected servers.

        Returns:
            List of connected ServerConnection instances
        """
        return [s for s in self.servers.values() if s.connected]

    def disconnect_all(self):
        """Disconnect from all servers."""
        for server in self.servers.values():
            if server.connected and server.client:
                try:
                    server.client.disconnect()
                except:
                    pass

            server.connected = False
            server.client = None

        logger.info("All servers disconnected")

    def find_server_by_host(self, host: str, api_port: int) -> Optional[ServerConnection]:
        """Find server by host and port.

        Args:
            host: Hostname or IP
            api_port: API port

        Returns:
            ServerConnection or None
        """
        for server in self.servers.values():
            if server.host == host and server.api_port == api_port:
                return server

        return None


# Global server manager instance
_server_manager: Optional[ServerManager] = None


def get_server_manager() -> ServerManager:
    """Get global server manager instance.

    Returns:
        ServerManager instance
    """
    global _server_manager

    if _server_manager is None:
        _server_manager = ServerManager()

    return _server_manager
