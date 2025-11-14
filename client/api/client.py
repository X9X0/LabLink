"""API client for LabLink server communication."""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

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

        # Authentication state
        self.access_token = None
        self.refresh_token = None
        self.user_data = None
        self.authenticated = False

        # Initialize WebSocket manager if available
        if WebSocketManager:
            self.ws_manager = WebSocketManager(host=host, port=ws_port)
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
            f"{self.api_base_url}/equipment/{equipment_id}/disconnect"
        )
        response.raise_for_status()
        return response.json()

    def send_command(
        self, equipment_id: str, command: str, parameters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send command to equipment.

        Args:
            equipment_id: Equipment ID
            command: Command name
            parameters: Command parameters

        Returns:
            Command result
        """
        payload = {"command": command, "parameters": parameters or {}}
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

    # ==================== Utility Methods ====================

    def get_server_info(self) -> Dict[str, Any]:
        """Get server information.

        Returns:
            Server information
        """
        response = self._session.get(f"http://{self.host}:{self.api_port}/")
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
