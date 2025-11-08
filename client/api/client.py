"""API client for LabLink server communication."""

import logging
import asyncio
from typing import Optional, Dict, List, Any, Callable
from datetime import datetime

import requests
import websockets
import json

logger = logging.getLogger(__name__)


class LabLinkClient:
    """Client for communicating with LabLink server."""

    def __init__(self, host: str = "localhost", api_port: int = 8000, ws_port: int = 8001):
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
        self.ws_url = f"ws://{host}:{ws_port}/ws"

        self._session = requests.Session()
        self._ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._message_callbacks: List[Callable] = []

        self.connected = False

    # ==================== Connection Management ====================

    def connect(self) -> bool:
        """Test connection to server.

        Returns:
            True if connection successful
        """
        try:
            response = self._session.get(f"http://{self.host}:{self.api_port}/health", timeout=5)
            if response.status_code == 200:
                self.connected = True
                logger.info(f"Connected to LabLink server at {self.host}:{self.api_port}")
                return True
        except Exception as e:
            logger.error(f"Failed to connect to server: {e}")
            self.connected = False

        return False

    def disconnect(self):
        """Disconnect from server."""
        if self._ws_connection:
            asyncio.create_task(self._ws_connection.close())
        self.connected = False
        logger.info("Disconnected from LabLink server")

    async def connect_websocket(self):
        """Connect to WebSocket for real-time data streaming."""
        try:
            self._ws_connection = await websockets.connect(self.ws_url)
            logger.info(f"WebSocket connected to {self.ws_url}")

            # Start message receiving task
            self._ws_task = asyncio.create_task(self._receive_messages())
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            raise

    async def _receive_messages(self):
        """Receive messages from WebSocket."""
        try:
            async for message in self._ws_connection:
                data = json.loads(message)

                # Call all registered callbacks
                for callback in self._message_callbacks:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.error(f"Error in message callback: {e}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

    def register_message_callback(self, callback: Callable):
        """Register callback for WebSocket messages.

        Args:
            callback: Function to call with received data
        """
        self._message_callbacks.append(callback)

    # ==================== Equipment API ====================

    def list_equipment(self) -> List[Dict[str, Any]]:
        """Get list of all equipment.

        Returns:
            List of equipment dictionaries
        """
        response = self._session.get(f"{self.api_base_url}/equipment")
        response.raise_for_status()
        return response.json()["equipment"]

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
        response = self._session.post(f"{self.api_base_url}/equipment/{equipment_id}/connect")
        response.raise_for_status()
        return response.json()

    def disconnect_equipment(self, equipment_id: str) -> Dict[str, Any]:
        """Disconnect from equipment.

        Args:
            equipment_id: Equipment ID

        Returns:
            Response dictionary
        """
        response = self._session.post(f"{self.api_base_url}/equipment/{equipment_id}/disconnect")
        response.raise_for_status()
        return response.json()

    def send_command(self, equipment_id: str, command: str, parameters: Optional[Dict] = None) -> Dict[str, Any]:
        """Send command to equipment.

        Args:
            equipment_id: Equipment ID
            command: Command name
            parameters: Command parameters

        Returns:
            Command result
        """
        payload = {
            "command": command,
            "parameters": parameters or {}
        }
        response = self._session.post(
            f"{self.api_base_url}/equipment/{equipment_id}/command",
            json=payload
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
        response = self._session.get(f"{self.api_base_url}/equipment/{equipment_id}/readings")
        response.raise_for_status()
        return response.json()

    # ==================== Data Acquisition API ====================

    def create_acquisition(self, equipment_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create data acquisition session.

        Args:
            equipment_id: Equipment ID
            config: Acquisition configuration

        Returns:
            Acquisition session details
        """
        response = self._session.post(
            f"{self.api_base_url}/acquisition/create",
            json={"equipment_id": equipment_id, **config}
        )
        response.raise_for_status()
        return response.json()

    def start_acquisition(self, acquisition_id: str) -> Dict[str, Any]:
        """Start data acquisition.

        Args:
            acquisition_id: Acquisition session ID

        Returns:
            Response dictionary
        """
        response = self._session.post(f"{self.api_base_url}/acquisition/{acquisition_id}/start")
        response.raise_for_status()
        return response.json()

    def stop_acquisition(self, acquisition_id: str) -> Dict[str, Any]:
        """Stop data acquisition.

        Args:
            acquisition_id: Acquisition session ID

        Returns:
            Response dictionary
        """
        response = self._session.post(f"{self.api_base_url}/acquisition/{acquisition_id}/stop")
        response.raise_for_status()
        return response.json()

    def get_acquisition_data(self, acquisition_id: str) -> Dict[str, Any]:
        """Get acquisition data.

        Args:
            acquisition_id: Acquisition session ID

        Returns:
            Acquisition data
        """
        response = self._session.get(f"{self.api_base_url}/acquisition/{acquisition_id}/data")
        response.raise_for_status()
        return response.json()

    def list_acquisitions(self, equipment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List acquisition sessions.

        Args:
            equipment_id: Optional equipment ID to filter

        Returns:
            List of acquisition sessions
        """
        params = {"equipment_id": equipment_id} if equipment_id else {}
        response = self._session.get(f"{self.api_base_url}/acquisition/sessions", params=params)
        response.raise_for_status()
        return response.json()["sessions"]

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
            json={"event_id": event_id}
        )
        response.raise_for_status()
        return response.json()

    # ==================== Scheduler API ====================

    def list_jobs(self, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        """List scheduled jobs.

        Args:
            enabled: Filter by enabled status

        Returns:
            List of jobs
        """
        params = {"enabled": enabled} if enabled is not None else {}
        response = self._session.get(f"{self.api_base_url}/scheduler/jobs", params=params)
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
            f"{self.api_base_url}/scheduler/jobs/create",
            json=job_config
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
        response = self._session.post(f"{self.api_base_url}/scheduler/jobs/{job_id}/run")
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

    # ==================== Diagnostics API ====================

    def get_equipment_health(self, equipment_id: str) -> Dict[str, Any]:
        """Get equipment health.

        Args:
            equipment_id: Equipment ID

        Returns:
            Equipment health details
        """
        response = self._session.get(f"{self.api_base_url}/diagnostics/health/{equipment_id}")
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
        response = self._session.post(f"{self.api_base_url}/diagnostics/benchmark/{equipment_id}")
        response.raise_for_status()
        return response.json()["benchmark"]

    def generate_diagnostic_report(
        self,
        equipment_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None
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
            f"{self.api_base_url}/diagnostics/report",
            json=payload
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

    def capture_state(self, equipment_id: str, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """Capture equipment state.

        Args:
            equipment_id: Equipment ID
            name: State name
            description: Optional description

        Returns:
            Captured state details
        """
        payload = {
            "equipment_id": equipment_id,
            "name": name
        }
        if description:
            payload["description"] = description

        response = self._session.post(f"{self.api_base_url}/state/capture", json=payload)
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
