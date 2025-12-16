"""API client for LabLink server communication."""

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from utils.websocket_manager import (MessageType, StreamType,
                                         WebSocketManager)
except ImportError:
    # Fallback if utils not found
    WebSocketManager = None
    StreamType = None
    MessageType = None

logger = logging.getLogger(__name__)


class LabLinkClient:
    """Client for communicating with LabLink server."""

    def __init__(
        self, host: str = "localhost", api_port: int = 8000, ws_port: int = 8001
    ):
        """Initialize LabLink client.

        Args:
            host: Server hostname or IP address
            api_port: REST API port
            ws_port: WebSocket port
        """
        self.host = host
        self.api_port = api_port
        self.ws_port = ws_port

        self.api_base_url = f"http://{host}:{api_port}/api"

        self._session = requests.Session()

        # Session ID for equipment lock management
        self.session_id = str(uuid.uuid4())
        logger.info(f"Client session ID: {self.session_id}")

        # Authentication state
        self.access_token = None
        self.refresh_token = None
        self.user_data = None
        self.authenticated = False

        # Initialize WebSocket manager if available
        # Note: WebSocket is on the same port as API, not a separate port
        if WebSocketManager:
            self.ws_manager = WebSocketManager(host=host, port=api_port)
        else:
            self.ws_manager = None
            logger.warning("WebSocket manager not available")

        self.connected = False

    # ==================== Connection Management ====================

    def connect(self) -> bool:
        """Test connection to server.

        Returns:
            True if connection successful
        """
        try:
            response = self._session.get(
                f"http://{self.host}:{self.api_port}/health", timeout=5
            )
            if response.status_code == 200:
                self.connected = True
                logger.info(
                    f"Connected to LabLink server at {self.host}:{self.api_port}"
                )
                return True
        except Exception as e:
            logger.error(f"Failed to connect to server: {e}")
            self.connected = False

        return False

    async def disconnect(self):
        """Disconnect from server."""
        self.connected = False

        # Disconnect WebSocket if available
        if self.ws_manager:
            await self.ws_manager.disconnect()

        logger.info("Disconnected from LabLink server")

    # ==================== Authentication Methods ====================

    def login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Login to LabLink server with username and password.

        Args:
            username: Username or email
            password: Password

        Returns:
            Login response with tokens and user data

        Raises:
            Exception: If login fails
        """
        try:
            response = self._session.post(
                f"{self.api_base_url}/security/login",
                json={"username": username, "password": password},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()

                # Store tokens
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                self.user_data = data.get("user", {})
                self.authenticated = True

                # Update session headers with Bearer token
                self._update_auth_header()

                logger.info(f"Logged in as {self.user_data.get('username', 'unknown')}")
                return data
            else:
                error_detail = response.json().get("detail", "Login failed")
                raise Exception(f"Login failed: {error_detail}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Login request failed: {e}")
            raise Exception(f"Login request failed: {e}")

    def logout(self) -> bool:
        """Logout from LabLink server.

        Returns:
            True if logout successful
        """
        try:
            if self.authenticated and self.access_token:
                # Call logout endpoint
                response = self._session.post(
                    f"{self.api_base_url}/security/logout", timeout=5
                )

                if response.status_code == 200:
                    logger.info("Logged out successfully")

            # Clear authentication state
            self._clear_auth()
            return True

        except Exception as e:
            logger.error(f"Logout failed: {e}")
            # Clear auth anyway
            self._clear_auth()
            return False

    def refresh_access_token(self) -> bool:
        """Refresh access token using refresh token.

        Returns:
            True if refresh successful
        """
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False

        try:
            response = self._session.post(
                f"{self.api_base_url}/security/refresh",
                json={"refresh_token": self.refresh_token},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token", self.refresh_token)

                # Update session headers
                self._update_auth_header()

                logger.info("Access token refreshed successfully")
                return True
            else:
                logger.error("Token refresh failed")
                self._clear_auth()
                return False

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            self._clear_auth()
            return False

    def _update_auth_header(self):
        """Update session headers with current access token."""
        if self.access_token:
            self._session.headers.update(
                {"Authorization": f"Bearer {self.access_token}"}
            )

    def _clear_auth(self):
        """Clear authentication state."""
        self.access_token = None
        self.refresh_token = None
        self.user_data = None
        self.authenticated = False

        # Remove Authorization header
        if "Authorization" in self._session.headers:
            del self._session.headers["Authorization"]

    def is_authenticated(self) -> bool:
        """Check if client is authenticated.

        Returns:
            True if authenticated
        """
        return self.authenticated and self.access_token is not None

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get current authenticated user data.

        Returns:
            User data dictionary or None
        """
        return self.user_data

    def has_role(self, role_name: str) -> bool:
        """Check if current user has a specific role.

        Args:
            role_name: Role name to check (admin, operator, viewer)

        Returns:
            True if user has the role
        """
        if not self.user_data:
            return False

        # Check if superuser
        if self.user_data.get("is_superuser"):
            return True

        # Check roles
        user_roles = self.user_data.get("roles", [])
        return any(role.get("name") == role_name for role in user_roles)

    # ==================== WebSocket Methods ====================

    async def connect_websocket(self) -> bool:
        """Connect to WebSocket for real-time data streaming.

        Returns:
            True if connection successful
        """
        if not self.ws_manager:
            logger.error("WebSocket manager not available")
            return False

        return await self.ws_manager.connect()

    async def start_equipment_stream(
        self, equipment_id: str, stream_type: str = "readings", interval_ms: int = 100
    ):
        """Start streaming data from equipment.

        Args:
            equipment_id: Equipment ID
            stream_type: Type of data (readings, waveform, measurements)
            interval_ms: Update interval in milliseconds
        """
        if not self.ws_manager:
            raise RuntimeError("WebSocket manager not available")

        # Convert string to enum if needed
        if isinstance(stream_type, str) and StreamType:
            stream_type = StreamType(stream_type)

        await self.ws_manager.start_equipment_stream(
            equipment_id=equipment_id, stream_type=stream_type, interval_ms=interval_ms
        )

    async def stop_equipment_stream(
        self, equipment_id: str, stream_type: str = "readings"
    ):
        """Stop streaming data from equipment.

        Args:
            equipment_id: Equipment ID
            stream_type: Type of data stream to stop
        """
        if not self.ws_manager:
            raise RuntimeError("WebSocket manager not available")

        # Convert string to enum if needed
        if isinstance(stream_type, str) and StreamType:
            stream_type = StreamType(stream_type)

        await self.ws_manager.stop_equipment_stream(
            equipment_id=equipment_id, stream_type=stream_type
        )

    async def start_acquisition_stream(
        self, acquisition_id: str, interval_ms: int = 100, num_samples: int = 100
    ):
        """Start streaming acquisition data.

        Args:
            acquisition_id: Acquisition session ID
            interval_ms: Update interval in milliseconds
            num_samples: Number of samples per update
        """
        if not self.ws_manager:
            raise RuntimeError("WebSocket manager not available")

        await self.ws_manager.start_acquisition_stream(
            acquisition_id=acquisition_id,
            interval_ms=interval_ms,
            num_samples=num_samples,
        )

    async def stop_acquisition_stream(self, acquisition_id: str):
        """Stop streaming acquisition data.

        Args:
            acquisition_id: Acquisition session ID
        """
        if not self.ws_manager:
            raise RuntimeError("WebSocket manager not available")

        await self.ws_manager.stop_acquisition_stream(acquisition_id)

    def register_stream_data_handler(self, handler: Callable):
        """Register handler for equipment stream data.

        Args:
            handler: Callback function
        """
        if not self.ws_manager:
            raise RuntimeError("WebSocket manager not available")

        self.ws_manager.on_stream_data(handler)

    def register_acquisition_data_handler(self, handler: Callable):
        """Register handler for acquisition stream data.

        Args:
            handler: Callback function
        """
        if not self.ws_manager:
            raise RuntimeError("WebSocket manager not available")

        self.ws_manager.on_acquisition_data(handler)

    def register_message_callback(self, handler: Callable):
        """Register generic callback for all WebSocket messages.

        Args:
            handler: Callback function
        """
        if not self.ws_manager:
            raise RuntimeError("WebSocket manager not available")

        self.ws_manager.register_generic_handler(handler)

    def get_websocket_statistics(self) -> Dict[str, Any]:
        """Get WebSocket statistics.

        Returns:
            Statistics dictionary
        """
        if not self.ws_manager:
            return {"error": "WebSocket manager not available"}

        return self.ws_manager.get_statistics()

    # ==================== Equipment API ====================

    def list_equipment(self) -> List[Dict[str, Any]]:
        """Get list of all equipment.

        Returns:
            List of equipment dictionaries
        """
        response = self._session.get(f"{self.api_base_url}/equipment/list")
        response.raise_for_status()
        return response.json()

    def get_equipment(self, equipment_id: str) -> Dict[str, Any]:
        """Get equipment details.

        Args:
            equipment_id: Equipment ID

        Returns:
            Equipment details dictionary
        """
        response = self._session.get(f"{self.api_base_url}/equipment/{equipment_id}")
        response.raise_for_status()
        return response.json()["equipment"]

    def get_equipment_status(self, equipment_id: str) -> Dict[str, Any]:
        """Get equipment status including capabilities.

        Args:
            equipment_id: Equipment ID

        Returns:
            Equipment status dictionary with capabilities
        """
        response = self._session.get(f"{self.api_base_url}/equipment/{equipment_id}/status")
        response.raise_for_status()
        return response.json()

    def connect_equipment(self, equipment_id: str) -> Dict[str, Any]:
        """Connect to equipment.

        Args:
            equipment_id: Equipment ID

        Returns:
            Response dictionary
        """
        response = self._session.post(
            f"{self.api_base_url}/equipment/{equipment_id}/connect"
        )
        response.raise_for_status()
        return response.json()

    def disconnect_equipment(self, equipment_id: str) -> Dict[str, Any]:
        """Disconnect from equipment.

        Args:
            equipment_id: Equipment ID

        Returns:
            Response dictionary
        """
        response = self._session.post(
            f"{self.api_base_url}/equipment/disconnect/{equipment_id}"
        )
        response.raise_for_status()
        return response.json()

    def send_command(
        self, equipment_id: str, command: str, parameters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send command to equipment.

        Args:
            equipment_id: Equipment ID
            command: Command name (action to perform)
            parameters: Command parameters

        Returns:
            Command result
        """
        payload = {
            "command_id": str(uuid.uuid4()),
            "equipment_id": equipment_id,
            "action": command,
            "parameters": parameters or {},
            "session_id": self.session_id,
        }
        response = self._session.post(
            f"{self.api_base_url}/equipment/{equipment_id}/command", json=payload
        )
        response.raise_for_status()
        return response.json()

    def get_readings(self, equipment_id: str) -> Dict[str, Any]:
        """Get current readings from equipment.

        Args:
            equipment_id: Equipment ID

        Returns:
            Readings dictionary
        """
        response = self._session.get(
            f"{self.api_base_url}/equipment/{equipment_id}/readings"
        )
        response.raise_for_status()
        return response.json()

    # ==================== Data Acquisition API ====================

    # Session Management

    def create_acquisition_session(
        self, equipment_id: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create data acquisition session.

        Args:
            equipment_id: Equipment ID
            config: Acquisition configuration (mode, sample_rate, channels, etc.)

        Returns:
            Acquisition session details with acquisition_id
        """
        payload = {"equipment_id": equipment_id, **config}
        response = self._session.post(
            f"{self.api_base_url}/acquisition/session/create", json=payload
        )
        response.raise_for_status()
        return response.json()

    def start_acquisition(self, acquisition_id: str) -> Dict[str, Any]:
        """Start data acquisition.

        Args:
            acquisition_id: Acquisition session ID

        Returns:
            Response with state
        """
        response = self._session.post(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/start"
        )
        response.raise_for_status()
        return response.json()

    def stop_acquisition(self, acquisition_id: str) -> Dict[str, Any]:
        """Stop data acquisition.

        Args:
            acquisition_id: Acquisition session ID

        Returns:
            Response with state
        """
        response = self._session.post(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/stop"
        )
        response.raise_for_status()
        return response.json()

    def pause_acquisition(self, acquisition_id: str) -> Dict[str, Any]:
        """Pause data acquisition.

        Args:
            acquisition_id: Acquisition session ID

        Returns:
            Response with state
        """
        response = self._session.post(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/pause"
        )
        response.raise_for_status()
        return response.json()

    def resume_acquisition(self, acquisition_id: str) -> Dict[str, Any]:
        """Resume paused data acquisition.

        Args:
            acquisition_id: Acquisition session ID

        Returns:
            Response with state
        """
        response = self._session.post(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/resume"
        )
        response.raise_for_status()
        return response.json()

    # ==================== Equipment Lock Methods ====================

    def acquire_lock(
        self, equipment_id: str, lock_mode: str = "exclusive", timeout_seconds: int = 300
    ) -> Dict[str, Any]:
        """Acquire a lock on equipment.

        Args:
            equipment_id: Equipment ID to lock
            lock_mode: Lock mode ("exclusive" or "observer")
            timeout_seconds: Lock timeout in seconds (0 = no timeout)

        Returns:
            Lock acquisition result
        """
        payload = {
            "equipment_id": equipment_id,
            "session_id": self.session_id,
            "lock_mode": lock_mode,
            "timeout_seconds": timeout_seconds,
            "queue_if_busy": False,
        }
        response = self._session.post(
            f"{self.api_base_url}/locks/acquire", json=payload
        )
        response.raise_for_status()
        return response.json()

    def release_lock(self, equipment_id: str, force: bool = False) -> Dict[str, Any]:
        """Release a lock on equipment.

        Args:
            equipment_id: Equipment ID to unlock
            force: Force release even if not owner (for clearing stale locks)

        Returns:
            Lock release result
        """
        payload = {
            "equipment_id": equipment_id,
            "session_id": self.session_id,
            "force": force,
        }
        response = self._session.post(
            f"{self.api_base_url}/locks/release", json=payload
        )
        response.raise_for_status()
        return response.json()

    # ==================== Acquisition Methods ====================

    def get_acquisition_status(self, acquisition_id: str) -> Dict[str, Any]:
        """Get acquisition session status.

        Args:
            acquisition_id: Acquisition session ID

        Returns:
            Session status details
        """
        response = self._session.get(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/status"
        )
        response.raise_for_status()
        return response.json()

    def get_acquisition_data(
        self,
        acquisition_id: str,
        channel: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_points: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get acquired data.

        Args:
            acquisition_id: Acquisition session ID
            channel: Optional channel filter
            start_time: Optional start time (ISO format)
            end_time: Optional end time (ISO format)
            max_points: Optional maximum number of points to return

        Returns:
            Acquisition data
        """
        params = {}
        if channel:
            params["channel"] = channel
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if max_points:
            params["max_points"] = max_points

        response = self._session.get(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/data",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def list_acquisition_sessions(
        self, equipment_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all acquisition sessions.

        Args:
            equipment_id: Optional equipment ID to filter

        Returns:
            List of acquisition sessions
        """
        params = {"equipment_id": equipment_id} if equipment_id else {}
        response = self._session.get(
            f"{self.api_base_url}/acquisition/sessions", params=params
        )
        response.raise_for_status()
        return response.json().get("sessions", [])

    def export_acquisition_data(
        self, acquisition_id: str, format: str = "csv", filepath: Optional[str] = None
    ) -> Dict[str, Any]:
        """Export acquisition data to file.

        Args:
            acquisition_id: Acquisition session ID
            format: Export format (csv, hdf5, npy, json)
            filepath: Optional file path for export

        Returns:
            Export result with filepath
        """
        payload = {"acquisition_id": acquisition_id, "format": format}
        if filepath:
            payload["filepath"] = filepath

        response = self._session.post(
            f"{self.api_base_url}/acquisition/export", json=payload
        )
        response.raise_for_status()
        return response.json()

    def delete_acquisition_session(self, acquisition_id: str) -> Dict[str, Any]:
        """Delete acquisition session.

        Args:
            acquisition_id: Acquisition session ID

        Returns:
            Success response
        """
        response = self._session.delete(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}"
        )
        response.raise_for_status()
        return response.json()

    # Statistics

    def get_acquisition_rolling_stats(
        self, acquisition_id: str, channel: Optional[str] = None, window_size: int = 100
    ) -> Dict[str, Any]:
        """Get rolling statistics for acquisition data.

        Args:
            acquisition_id: Acquisition session ID
            channel: Optional channel filter
            window_size: Window size for rolling statistics

        Returns:
            Rolling statistics (mean, std, min, max, rms, p2p)
        """
        params = {"window_size": window_size}
        if channel:
            params["channel"] = channel

        response = self._session.get(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/stats/rolling",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def get_acquisition_fft(
        self,
        acquisition_id: str,
        channel: Optional[str] = None,
        window: str = "hann",
        detrend: bool = True,
    ) -> Dict[str, Any]:
        """Get FFT analysis of acquisition data.

        Args:
            acquisition_id: Acquisition session ID
            channel: Optional channel filter
            window: Window function (hann, hamming, blackman, etc.)
            detrend: Whether to detrend data before FFT

        Returns:
            FFT results with frequencies, magnitudes, THD, SNR
        """
        params = {"window": window, "detrend": str(detrend).lower()}
        if channel:
            params["channel"] = channel

        response = self._session.get(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/stats/fft",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def get_acquisition_trend(
        self,
        acquisition_id: str,
        channel: Optional[str] = None,
        sensitivity: float = 0.1,
    ) -> Dict[str, Any]:
        """Detect trend in acquisition data.

        Args:
            acquisition_id: Acquisition session ID
            channel: Optional channel filter
            sensitivity: Trend detection sensitivity (0-1)

        Returns:
            Trend analysis (rising, falling, stable, noisy)
        """
        params = {"sensitivity": sensitivity}
        if channel:
            params["channel"] = channel

        response = self._session.get(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/stats/trend",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def get_acquisition_quality(
        self, acquisition_id: str, channel: Optional[str] = None
    ) -> Dict[str, Any]:
        """Assess data quality of acquisition.

        Args:
            acquisition_id: Acquisition session ID
            channel: Optional channel filter

        Returns:
            Quality metrics (noise_level, stability_score, outlier_ratio, quality_grade)
        """
        params = {}
        if channel:
            params["channel"] = channel

        response = self._session.get(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/stats/quality",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def get_acquisition_peaks(
        self,
        acquisition_id: str,
        channel: Optional[str] = None,
        min_height: Optional[float] = None,
        min_distance: int = 1,
    ) -> Dict[str, Any]:
        """Detect peaks in acquisition data.

        Args:
            acquisition_id: Acquisition session ID
            channel: Optional channel filter
            min_height: Minimum peak height
            min_distance: Minimum distance between peaks

        Returns:
            Peak information (indices, values, count)
        """
        params = {"min_distance": min_distance}
        if channel:
            params["channel"] = channel
        if min_height is not None:
            params["min_height"] = min_height

        response = self._session.get(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/stats/peaks",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def get_acquisition_crossings(
        self,
        acquisition_id: str,
        threshold: float,
        channel: Optional[str] = None,
        direction: str = "both",
    ) -> Dict[str, Any]:
        """Detect threshold crossings in acquisition data.

        Args:
            acquisition_id: Acquisition session ID
            threshold: Threshold value
            channel: Optional channel filter
            direction: Crossing direction (rising, falling, both)

        Returns:
            Crossing information (indices, values, count)
        """
        params = {"threshold": threshold, "direction": direction}
        if channel:
            params["channel"] = channel

        response = self._session.get(
            f"{self.api_base_url}/acquisition/session/{acquisition_id}/stats/crossings",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    # Multi-Instrument Synchronization

    def create_sync_group(
        self,
        group_id: str,
        equipment_ids: List[str],
        master_equipment_id: Optional[str] = None,
        sync_tolerance_ms: float = 10.0,
        wait_for_all: bool = True,
        auto_align_timestamps: bool = True,
    ) -> Dict[str, Any]:
        """Create a multi-instrument synchronization group.

        Args:
            group_id: Sync group ID
            equipment_ids: List of equipment IDs to synchronize
            master_equipment_id: Optional master equipment ID
            sync_tolerance_ms: Synchronization tolerance in milliseconds
            wait_for_all: Wait for all equipment before starting
            auto_align_timestamps: Auto-align timestamps

        Returns:
            Sync group status
        """
        payload = {
            "group_id": group_id,
            "equipment_ids": equipment_ids,
            "master_equipment_id": master_equipment_id,
            "sync_tolerance_ms": sync_tolerance_ms,
            "wait_for_all": wait_for_all,
            "auto_align_timestamps": auto_align_timestamps,
        }
        response = self._session.post(
            f"{self.api_base_url}/acquisition/sync/group/create", json=payload
        )
        response.raise_for_status()
        return response.json()

    def add_to_sync_group(
        self, group_id: str, equipment_id: str, acquisition_id: str
    ) -> Dict[str, Any]:
        """Add acquisition session to sync group.

        Args:
            group_id: Sync group ID
            equipment_id: Equipment ID
            acquisition_id: Acquisition session ID

        Returns:
            Sync group status
        """
        payload = {"equipment_id": equipment_id, "acquisition_id": acquisition_id}
        response = self._session.post(
            f"{self.api_base_url}/acquisition/sync/group/{group_id}/add", json=payload
        )
        response.raise_for_status()
        return response.json()

    def start_sync_group(self, group_id: str) -> Dict[str, Any]:
        """Start synchronized acquisition for all equipment in group.

        Args:
            group_id: Sync group ID

        Returns:
            Start result with sync status
        """
        response = self._session.post(
            f"{self.api_base_url}/acquisition/sync/group/{group_id}/start"
        )
        response.raise_for_status()
        return response.json()

    def stop_sync_group(self, group_id: str) -> Dict[str, Any]:
        """Stop synchronized acquisition for all equipment in group.

        Args:
            group_id: Sync group ID

        Returns:
            Stop result
        """
        response = self._session.post(
            f"{self.api_base_url}/acquisition/sync/group/{group_id}/stop"
        )
        response.raise_for_status()
        return response.json()

    def pause_sync_group(self, group_id: str) -> Dict[str, Any]:
        """Pause synchronized acquisition for all equipment in group.

        Args:
            group_id: Sync group ID

        Returns:
            Pause result
        """
        response = self._session.post(
            f"{self.api_base_url}/acquisition/sync/group/{group_id}/pause"
        )
        response.raise_for_status()
        return response.json()

    def resume_sync_group(self, group_id: str) -> Dict[str, Any]:
        """Resume synchronized acquisition for all equipment in group.

        Args:
            group_id: Sync group ID

        Returns:
            Resume result
        """
        response = self._session.post(
            f"{self.api_base_url}/acquisition/sync/group/{group_id}/resume"
        )
        response.raise_for_status()
        return response.json()

    def get_sync_group_status(self, group_id: str) -> Dict[str, Any]:
        """Get status of sync group.

        Args:
            group_id: Sync group ID

        Returns:
            Sync group status
        """
        response = self._session.get(
            f"{self.api_base_url}/acquisition/sync/group/{group_id}/status"
        )
        response.raise_for_status()
        return response.json()

    def get_sync_group_data(
        self,
        group_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get synchronized data from all equipment in group.

        Args:
            group_id: Sync group ID
            start_time: Optional start time (ISO format)
            end_time: Optional end time (ISO format)

        Returns:
            Synchronized data from all equipment
        """
        params = {}
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        response = self._session.get(
            f"{self.api_base_url}/acquisition/sync/group/{group_id}/data", params=params
        )
        response.raise_for_status()
        return response.json()

    def list_sync_groups(self) -> List[Dict[str, Any]]:
        """List all sync groups.

        Returns:
            List of sync groups
        """
        response = self._session.get(f"{self.api_base_url}/acquisition/sync/groups")
        response.raise_for_status()
        return response.json().get("groups", [])

    def delete_sync_group(self, group_id: str) -> Dict[str, Any]:
        """Delete sync group.

        Args:
            group_id: Sync group ID

        Returns:
            Success response
        """
        response = self._session.delete(
            f"{self.api_base_url}/acquisition/sync/group/{group_id}"
        )
        response.raise_for_status()
        return response.json()

    # Legacy compatibility methods (deprecated, use new methods above)
    def create_acquisition(
        self, equipment_id: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Legacy method - use create_acquisition_session instead."""
        return self.create_acquisition_session(equipment_id, config)

    def list_acquisitions(
        self, equipment_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Legacy method - use list_acquisition_sessions instead."""
        return self.list_acquisition_sessions(equipment_id)

    # ==================== Alarm API ====================

    def list_alarms(self, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        """List alarms.

        Args:
            enabled: Filter by enabled status

        Returns:
            List of alarms
        """
        params = {"enabled": enabled} if enabled is not None else {}
        response = self._session.get(f"{self.api_base_url}/alarms", params=params)
        response.raise_for_status()
        return response.json()["alarms"]

    def get_active_alarm_events(self) -> List[Dict[str, Any]]:
        """Get active alarm events.

        Returns:
            List of active alarm events
        """
        response = self._session.get(f"{self.api_base_url}/alarms/events/active")
        response.raise_for_status()
        return response.json()["events"]

    def acknowledge_alarm(self, event_id: str) -> Dict[str, Any]:
        """Acknowledge alarm event.

        Args:
            event_id: Alarm event ID

        Returns:
            Response dictionary
        """
        response = self._session.post(
            f"{self.api_base_url}/alarms/events/acknowledge",
            json={"event_id": event_id},
        )
        response.raise_for_status()
        return response.json()

    def get_alarm_history(
        self,
        limit: Optional[int] = None,
        severity: Optional[str] = None,
        equipment_id: Optional[str] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Get alarm event history.

        Args:
            limit: Maximum number of events to return
            severity: Filter by severity (critical, error, warning, info)
            equipment_id: Filter by equipment ID
            acknowledged: Filter by acknowledged status

        Returns:
            List of alarm events
        """
        params = {}
        if limit is not None:
            params["limit"] = limit
        if severity:
            params["severity"] = severity
        if equipment_id:
            params["equipment_id"] = equipment_id
        if acknowledged is not None:
            params["acknowledged"] = acknowledged

        response = self._session.get(
            f"{self.api_base_url}/alarms/events", params=params
        )
        response.raise_for_status()
        return response.json()["events"]

    def get_alarm_statistics(self) -> Dict[str, Any]:
        """Get alarm statistics.

        Returns:
            Alarm statistics
        """
        response = self._session.get(f"{self.api_base_url}/alarms/statistics")
        response.raise_for_status()
        return response.json()["statistics"]

    # ==================== Scheduler API ====================

    def list_jobs(self, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        """List scheduled jobs.

        Args:
            enabled: Filter by enabled status

        Returns:
            List of jobs
        """
        params = {"enabled": enabled} if enabled is not None else {}
        response = self._session.get(
            f"{self.api_base_url}/scheduler/jobs", params=params
        )
        response.raise_for_status()
        return response.json()["jobs"]

    def create_job(self, job_config: Dict[str, Any]) -> Dict[str, Any]:
        """Create scheduled job.

        Args:
            job_config: Job configuration

        Returns:
            Created job details
        """
        response = self._session.post(
            f"{self.api_base_url}/scheduler/jobs/create", json=job_config
        )
        response.raise_for_status()
        return response.json()

    def run_job_now(self, job_id: str) -> Dict[str, Any]:
        """Trigger job to run immediately.

        Args:
            job_id: Job ID

        Returns:
            Execution details
        """
        response = self._session.post(
            f"{self.api_base_url}/scheduler/jobs/{job_id}/run"
        )
        response.raise_for_status()
        return response.json()

    def get_scheduler_statistics(self) -> Dict[str, Any]:
        """Get scheduler statistics.

        Returns:
            Scheduler statistics
        """
        response = self._session.get(f"{self.api_base_url}/scheduler/statistics")
        response.raise_for_status()
        return response.json()["statistics"]

    def delete_job(self, job_id: str) -> Dict[str, Any]:
        """Delete scheduled job.

        Args:
            job_id: Job ID

        Returns:
            Response dictionary
        """
        response = self._session.delete(f"{self.api_base_url}/scheduler/jobs/{job_id}")
        response.raise_for_status()
        return response.json()

    def pause_job(self, job_id: str) -> Dict[str, Any]:
        """Pause scheduled job.

        Args:
            job_id: Job ID

        Returns:
            Response dictionary
        """
        response = self._session.post(
            f"{self.api_base_url}/scheduler/jobs/{job_id}/pause"
        )
        response.raise_for_status()
        return response.json()

    def resume_job(self, job_id: str) -> Dict[str, Any]:
        """Resume paused job.

        Args:
            job_id: Job ID

        Returns:
            Response dictionary
        """
        response = self._session.post(
            f"{self.api_base_url}/scheduler/jobs/{job_id}/resume"
        )
        response.raise_for_status()
        return response.json()

    # ==================== Diagnostics API ====================

    def get_equipment_health(self, equipment_id: str) -> Dict[str, Any]:
        """Get equipment health.

        Args:
            equipment_id: Equipment ID

        Returns:
            Equipment health details
        """
        response = self._session.get(
            f"{self.api_base_url}/diagnostics/health/{equipment_id}"
        )
        response.raise_for_status()
        return response.json()["health"]

    def get_all_equipment_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health for all equipment.

        Returns:
            Dictionary of equipment health keyed by equipment ID
        """
        response = self._session.get(f"{self.api_base_url}/diagnostics/health")
        response.raise_for_status()
        return response.json()["equipment_health"]

    def run_benchmark(self, equipment_id: str) -> Dict[str, Any]:
        """Run performance benchmark.

        Args:
            equipment_id: Equipment ID

        Returns:
            Benchmark results
        """
        response = self._session.post(
            f"{self.api_base_url}/diagnostics/benchmark/{equipment_id}"
        )
        response.raise_for_status()
        return response.json()["benchmark"]

    def generate_diagnostic_report(
        self,
        equipment_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate diagnostic report.

        Args:
            equipment_ids: Equipment IDs to include
            categories: Diagnostic categories to include

        Returns:
            Diagnostic report
        """
        payload = {}
        if equipment_ids:
            payload["equipment_ids"] = equipment_ids
        if categories:
            payload["categories"] = categories

        response = self._session.post(
            f"{self.api_base_url}/diagnostics/report", json=payload
        )
        response.raise_for_status()
        return response.json()["report"]

    def get_system_diagnostics(self) -> Dict[str, Any]:
        """Get system diagnostics.

        Returns:
            System diagnostics
        """
        response = self._session.get(f"{self.api_base_url}/diagnostics/system")
        response.raise_for_status()
        return response.json()["system"]

    def run_pi_diagnostics(self) -> Dict[str, Any]:
        """Run comprehensive Raspberry Pi diagnostic script.

        This runs the diagnose-pi.sh script on the server to check:
        - System information
        - Network status
        - Docker status
        - LabLink installation and service status
        - Container status
        - Port listeners
        - Recent logs and recommendations

        Returns:
            Dictionary containing:
            - success: Whether the script ran successfully
            - output: Full diagnostic output
            - return_code: Script exit code
            - script_path: Path to the diagnostic script
        """
        response = self._session.post(
            f"{self.api_base_url}/diagnostics/pi-diagnostics",
            timeout=90  # Allow up to 90 seconds for diagnostics to complete
        )
        response.raise_for_status()
        return response.json()

    def run_usb_diagnostics(self, resource_string: str) -> Dict[str, Any]:
        """Run USB device diagnostics to troubleshoot connection issues.

        Analyzes why a USB device's serial number may not be readable and
        provides recommendations for resolving the issue.

        Args:
            resource_string: VISA resource string of the device to diagnose

        Returns:
            Dictionary containing:
            - resource_string: The analyzed resource string
            - has_serial: Whether a serial number is present
            - serial_readable: Whether the serial number can be read
            - usb_info: USB vendor/product/serial information
            - issues: List of detected issues
            - recommendations: List of recommended fixes
        """
        response = self._session.post(
            f"{self.base_url}/equipment/diagnostics/usb",
            json={"resource_string": resource_string},
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    # ==================== State Management API ====================

    def capture_state(
        self, equipment_id: str, name: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Capture equipment state.

        Args:
            equipment_id: Equipment ID
            name: State name
            description: Optional description

        Returns:
            Captured state details
        """
        payload = {"equipment_id": equipment_id, "name": name}
        if description:
            payload["description"] = description

        response = self._session.post(
            f"{self.api_base_url}/state/capture", json=payload
        )
        response.raise_for_status()
        return response.json()

    def restore_state(self, state_id: str) -> Dict[str, Any]:
        """Restore equipment state.

        Args:
            state_id: State ID

        Returns:
            Response dictionary
        """
        response = self._session.post(f"{self.api_base_url}/state/{state_id}/restore")
        response.raise_for_status()
        return response.json()

    def list_states(self, equipment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List saved states.

        Args:
            equipment_id: Optional equipment ID to filter

        Returns:
            List of states
        """
        params = {"equipment_id": equipment_id} if equipment_id else {}
        response = self._session.get(f"{self.api_base_url}/state/list", params=params)
        response.raise_for_status()
        return response.json()["states"]

    # ==================== Test Sequence Methods ====================

    def create_test_sequence(self, sequence_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new test sequence.

        Args:
            sequence_data: Test sequence configuration

        Returns:
            Created sequence details
        """
        response = self._session.post(
            f"{self.api_base_url}/testing/sequences", json=sequence_data
        )
        response.raise_for_status()
        return response.json()

    def get_test_sequence(self, sequence_id: str) -> Dict[str, Any]:
        """Get a test sequence by ID.

        Args:
            sequence_id: Sequence ID

        Returns:
            Test sequence details
        """
        response = self._session.get(
            f"{self.api_base_url}/testing/sequences/{sequence_id}"
        )
        response.raise_for_status()
        return response.json()

    def list_test_templates(self) -> Dict[str, Any]:
        """List available test templates.

        Returns:
            List of templates
        """
        response = self._session.get(f"{self.api_base_url}/testing/templates")
        response.raise_for_status()
        return response.json()

    def create_from_template(
        self,
        template_name: str,
        equipment_id: str,
        test_points: Optional[List[float]] = None,
        start_freq: Optional[float] = None,
        stop_freq: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create test sequence from template.

        Args:
            template_name: Template name
            equipment_id: Equipment ID
            test_points: Test points for voltage accuracy template
            start_freq: Start frequency for frequency response
            stop_freq: Stop frequency for frequency response

        Returns:
            Created test sequence
        """
        params = {"equipment_id": equipment_id}
        if test_points:
            params["test_points"] = test_points
        if start_freq:
            params["start_freq"] = start_freq
        if stop_freq:
            params["stop_freq"] = stop_freq

        response = self._session.post(
            f"{self.api_base_url}/testing/templates/{template_name}", params=params
        )
        response.raise_for_status()
        return response.json()

    def execute_test_sequence(
        self,
        sequence_data: Dict[str, Any],
        executed_by: str,
        environment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a test sequence.

        Args:
            sequence_data: Test sequence configuration
            executed_by: User executing the test
            environment: Optional environment data (temperature, humidity, etc.)

        Returns:
            Execution details
        """
        payload = {
            "sequence": sequence_data,
            "executed_by": executed_by,
            "environment": environment or {},
        }
        response = self._session.post(
            f"{self.api_base_url}/testing/execute", json=payload
        )
        response.raise_for_status()
        return response.json()

    def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """Get status of a test execution.

        Args:
            execution_id: Execution ID

        Returns:
            Execution status and results
        """
        response = self._session.get(
            f"{self.api_base_url}/testing/executions/{execution_id}"
        )
        response.raise_for_status()
        return response.json()

    def abort_test_execution(self, execution_id: str) -> Dict[str, Any]:
        """Abort a running test execution.

        Args:
            execution_id: Execution ID

        Returns:
            Abort confirmation
        """
        response = self._session.post(
            f"{self.api_base_url}/testing/executions/{execution_id}/abort"
        )
        response.raise_for_status()
        return response.json()

    def get_active_test_executions(self) -> Dict[str, Any]:
        """Get all active test executions.

        Returns:
            List of active executions
        """
        response = self._session.get(f"{self.api_base_url}/testing/executions/active")
        response.raise_for_status()
        return response.json()

    def get_testing_info(self) -> Dict[str, Any]:
        """Get information about the test automation system.

        Returns:
            System information and capabilities
        """
        response = self._session.get(f"{self.api_base_url}/testing/info")
        response.raise_for_status()
        return response.json()

    # ==================== Utility Methods ====================

    def get_server_info(self) -> Dict[str, Any]:
        """Get server information.

        Returns:
            Server information
        """
        response = self._session.get(f"http://{self.host}:{self.api_port}/api")
        response.raise_for_status()
        return response.json()

    def health_check(self) -> Dict[str, Any]:
        """Check server health.

        Returns:
            Health status
        """
        response = self._session.get(f"http://{self.host}:{self.api_port}/health")
        response.raise_for_status()
        return response.json()

    # ==================== System Management Methods ====================

    def get_server_version(self) -> Dict[str, Any]:
        """Get server version information.

        Returns:
            Version information including version string and parsed components
        """
        response = self._session.get(f"{self.api_base_url}/system/version")
        response.raise_for_status()
        return response.json()

    def get_update_status(self) -> Dict[str, Any]:
        """Get current update status and progress.

        Returns:
            Update status information including progress, logs, and errors
        """
        response = self._session.get(f"{self.api_base_url}/system/update/status")
        response.raise_for_status()
        return response.json()

    def check_for_updates(
        self, git_remote: str = "origin", git_branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """Check if server updates are available.

        Args:
            git_remote: Git remote name (default: origin)
            git_branch: Git branch to check (default: current branch)

        Returns:
            Update availability information
        """
        payload = {"git_remote": git_remote}
        if git_branch:
            payload["git_branch"] = git_branch

        response = self._session.post(
            f"{self.api_base_url}/system/update/check", json=payload
        )
        response.raise_for_status()
        return response.json()

    def start_server_update(
        self, git_remote: str = "origin", git_branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """Start server update process.

        WARNING: This will pull latest code from git and may require a
        Docker rebuild and service restart.

        Args:
            git_remote: Git remote name (default: origin)
            git_branch: Git branch to pull from (default: current branch)

        Returns:
            Update result with instructions for rebuild if needed
        """
        payload = {"git_remote": git_remote}
        if git_branch:
            payload["git_branch"] = git_branch

        response = self._session.post(
            f"{self.api_base_url}/system/update/start", json=payload
        )
        response.raise_for_status()
        return response.json()

    def rollback_server(self) -> Dict[str, Any]:
        """Rollback server to previous version.

        Returns:
            Rollback result
        """
        response = self._session.post(f"{self.api_base_url}/system/update/rollback")
        response.raise_for_status()
        return response.json()

    def configure_auto_rebuild(
        self, enabled: bool, rebuild_command: Optional[str] = None
    ) -> Dict[str, Any]:
        """Configure automatic Docker rebuild after updates.

        Args:
            enabled: Enable/disable auto-rebuild
            rebuild_command: Optional custom rebuild command

        Returns:
            Configuration result
        """
        payload = {"enabled": enabled}
        if rebuild_command:
            payload["rebuild_command"] = rebuild_command

        response = self._session.post(
            f"{self.api_base_url}/system/update/configure-rebuild", json=payload
        )
        response.raise_for_status()
        return response.json()

    def execute_rebuild(self) -> Dict[str, Any]:
        """Execute Docker rebuild and restart.

        WARNING: This will rebuild Docker containers and restart the server.

        Returns:
            Rebuild result
        """
        response = self._session.post(f"{self.api_base_url}/system/update/rebuild")
        response.raise_for_status()
        return response.json()

    def configure_update_mode(self, mode: str) -> Dict[str, Any]:
        """Configure update detection mode (stable vs development).

        Args:
            mode: Update mode - "stable" for VERSION tracking, "development" for commit tracking

        Returns:
            Configuration result
        """
        payload = {"mode": mode}

        response = self._session.post(
            f"{self.api_base_url}/system/update/configure-mode", json=payload
        )
        response.raise_for_status()
        return response.json()

    def get_available_branches(self, git_remote: str = "origin") -> Dict[str, Any]:
        """Get list of available branches from remote repository.

        Args:
            git_remote: Git remote name (default: origin)

        Returns:
            Dictionary with list of available branches
        """
        payload = {"git_remote": git_remote}

        response = self._session.post(
            f"{self.api_base_url}/system/update/branches", json=payload
        )
        response.raise_for_status()
        return response.json()

    def set_tracked_branch(self, branch_name: str) -> Dict[str, Any]:
        """Set the branch to track for updates in development mode.

        Args:
            branch_name: Name of branch to track

        Returns:
            Configuration result
        """
        payload = {"branch_name": branch_name}

        response = self._session.post(
            f"{self.api_base_url}/system/update/set-tracked-branch", json=payload
        )
        response.raise_for_status()
        return response.json()

    def configure_scheduled_checks(
        self,
        enabled: bool,
        interval_hours: int = 24,
        git_remote: str = "origin",
        git_branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Configure automatic scheduled update checking.

        Args:
            enabled: Enable/disable scheduled checks
            interval_hours: Hours between checks (default: 24)
            git_remote: Git remote to check (default: origin)
            git_branch: Git branch to check (default: current branch)

        Returns:
            Configuration result
        """
        payload = {
            "enabled": enabled,
            "interval_hours": interval_hours,
            "git_remote": git_remote,
        }
        if git_branch:
            payload["git_branch"] = git_branch

        response = self._session.post(
            f"{self.api_base_url}/system/update/configure-scheduled", json=payload
        )
        response.raise_for_status()
        return response.json()

    def start_scheduled_checks(self) -> Dict[str, Any]:
        """Start scheduled update checking.

        Returns:
            Start result
        """
        response = self._session.post(
            f"{self.api_base_url}/system/update/scheduled/start"
        )
        response.raise_for_status()
        return response.json()

    def stop_scheduled_checks(self) -> Dict[str, Any]:
        """Stop scheduled update checking.

        Returns:
            Stop result
        """
        response = self._session.post(
            f"{self.api_base_url}/system/update/scheduled/stop"
        )
        response.raise_for_status()
        return response.json()

    # ==================== Raspberry Pi Discovery Methods ====================

    def scan_raspberry_pis(
        self, network: Optional[str] = None, timeout: float = 2.0
    ) -> Dict[str, Any]:
        """Scan network for Raspberry Pi devices.

        Args:
            network: Network to scan in CIDR notation (e.g., "192.168.1.0/24")
                    If None, auto-detects local network
            timeout: Timeout for each host check in seconds

        Returns:
            Scan results with discovered Raspberry Pis
        """
        params = {"timeout": timeout}
        if network:
            params["network"] = network

        response = self._session.post(
            f"{self.api_base_url}/discovery/pi/scan", params=params
        )
        response.raise_for_status()
        return response.json()

    def get_pi_discovery_status(self) -> Dict[str, Any]:
        """Get Raspberry Pi discovery status.

        Returns:
            Discovery status including scan progress and cached results
        """
        response = self._session.get(f"{self.api_base_url}/discovery/pi/status")
        response.raise_for_status()
        return response.json()

    def get_discovery_settings(self) -> Dict[str, Any]:
        """Get discovery system settings.

        Returns:
            Discovery scanning configuration including serial, GPIB, USB, TCPIP settings
        """
        response = self._session.get(f"{self.api_base_url}/discovery/settings")
        response.raise_for_status()
        return response.json()

    def update_discovery_settings(self, **settings) -> Dict[str, Any]:
        """Update discovery system settings.

        Args:
            **settings: Discovery settings to update (scan_serial, scan_gpib, scan_usb, scan_tcpip, etc.)

        Returns:
            Result with updated settings

        Example:
            client.update_discovery_settings(scan_serial=True, scan_gpib=True)
        """
        response = self._session.post(
            f"{self.api_base_url}/discovery/settings",
            params=settings
        )
        response.raise_for_status()
        return response.json()

    # ==================== Async Equipment Discovery Methods ====================

    async def discover_equipment_async(self) -> Dict[str, Any]:
        """Discover available VISA equipment asynchronously (non-blocking).

        This method uses async HTTP to avoid blocking the UI thread during
        equipment discovery, which can take 5-30+ seconds.

        Returns:
            Discovery response with list of discovered resources

        Example:
            resources = await client.discover_equipment_async()

        Raises:
            ImportError: If aiohttp is not installed
        """
        if aiohttp is None:
            raise ImportError(
                "aiohttp is required for async discovery. "
                "Install with: pip install aiohttp"
            )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_base_url}/equipment/discover",
                headers=self._session.headers  # Include auth headers if present
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def connect_device_async(
        self, resource_string: str, equipment_type: str, model: str
    ) -> Dict[str, Any]:
        """Connect to a discovered device asynchronously (non-blocking).

        Args:
            resource_string: VISA resource string (e.g., "ASRL/dev/ttyUSB0::INSTR")
            equipment_type: Equipment type (e.g., "power_supply")
            model: Equipment model (e.g., "BK1902B")

        Returns:
            Connection response with equipment ID

        Example:
            result = await client.connect_device_async(
                "ASRL/dev/ttyUSB0::INSTR", "power_supply", "BK1902B"
            )

        Raises:
            ImportError: If aiohttp is not installed
        """
        if aiohttp is None:
            raise ImportError(
                "aiohttp is required for async connection. "
                "Install with: pip install aiohttp"
            )

        payload = {
            "resource_string": resource_string,
            "equipment_type": equipment_type,
            "model": model,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_base_url}/equipment/connect",
                json=payload,
                headers=self._session.headers  # Include auth headers if present
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def update_discovery_settings_async(self, **settings) -> Dict[str, Any]:
        """Update discovery system settings asynchronously (non-blocking).

        Args:
            **settings: Discovery settings to update

        Returns:
            Result with updated settings

        Example:
            await client.update_discovery_settings_async(scan_serial=True)

        Raises:
            ImportError: If aiohttp is not installed
        """
        if aiohttp is None:
            raise ImportError(
                "aiohttp is required for async settings update. "
                "Install with: pip install aiohttp"
            )

        # Convert boolean values to strings for aiohttp query parameters
        str_settings = {}
        for key, value in settings.items():
            if isinstance(value, bool):
                str_settings[key] = "true" if value else "false"
            else:
                str_settings[key] = value

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_base_url}/discovery/settings",
                params=str_settings,
                headers=self._session.headers  # Include auth headers if present
            ) as response:
                response.raise_for_status()
                return await response.json()
