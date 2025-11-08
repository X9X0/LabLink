"""Logging middleware for FastAPI."""

import time
import logging
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable

# Create loggers
access_logger = logging.getLogger("lablink.access")
audit_logger = logging.getLogger("lablink.audit")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details."""
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Extract request information
        client_host = request.client.host if request.client else "unknown"
        method = request.method
        url = str(request.url)
        path = request.url.path

        # Start timer
        start_time = time.time()

        # Process request
        try:
            response = await call_next(request)
            error = None
        except Exception as e:
            error = str(e)
            # Re-raise to let error handlers deal with it
            raise
        finally:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log access
            status_code = response.status_code if 'response' in locals() else 500

            access_logger.info(
                f"{method} {path}",
                extra={
                    "request_id": request_id,
                    "client_host": client_host,
                    "method": method,
                    "url": url,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 2),
                    "error": error
                }
            )

            # Log to audit trail for sensitive operations
            if self._is_audit_worthy(method, path):
                audit_logger.info(
                    f"User action: {method} {path}",
                    extra={
                        "request_id": request_id,
                        "client_host": client_host,
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "action": self._extract_action(method, path)
                    }
                )

        return response

    def _is_audit_worthy(self, method: str, path: str) -> bool:
        """Determine if request should be logged to audit trail."""
        # Log all write operations
        if method in ["POST", "PUT", "DELETE", "PATCH"]:
            return True

        # Log sensitive read operations
        sensitive_paths = [
            "/api/equipment/connect",
            "/api/equipment/disconnect",
            "/api/safety/",
            "/api/locks/",
            "/api/state/",
            "/api/acquisition/session"
        ]

        return any(path.startswith(p) for p in sensitive_paths)

    def _extract_action(self, method: str, path: str) -> str:
        """Extract human-readable action from request."""
        # Parse path to determine action
        parts = path.split("/")

        if "equipment" in path:
            if "connect" in path:
                return "connect_equipment"
            elif "disconnect" in path:
                return "disconnect_equipment"
            elif method == "POST":
                return "create_equipment"
            elif method == "DELETE":
                return "delete_equipment"
            elif method == "PUT":
                return "update_equipment"

        if "acquisition" in path:
            if "start" in path:
                return "start_acquisition"
            elif "stop" in path:
                return "stop_acquisition"
            elif "session/create" in path:
                return "create_acquisition_session"

        if "safety" in path:
            if "emergency" in path:
                return "emergency_stop"
            elif "limits" in path:
                return "update_safety_limits"

        if "locks" in path:
            if "acquire" in path:
                return "acquire_lock"
            elif "release" in path:
                return "release_lock"

        if "state" in path:
            if "capture" in path:
                return "capture_state"
            elif "restore" in path:
                return "restore_state"

        # Generic action
        action_map = {
            "POST": "create",
            "GET": "read",
            "PUT": "update",
            "DELETE": "delete",
            "PATCH": "patch"
        }

        return action_map.get(method, "unknown")


class EquipmentEventLogger:
    """Logger for equipment-specific events."""

    def __init__(self):
        """Initialize equipment event logger."""
        self.logger = logging.getLogger("lablink.equipment")

    def log_connection(self, equipment_id: str, address: str, success: bool, error: str = None):
        """Log equipment connection event."""
        self.logger.info(
            f"Equipment connection: {equipment_id}",
            extra={
                "equipment_id": equipment_id,
                "address": address,
                "event": "connection",
                "success": success,
                "error": error
            }
        )

    def log_disconnection(self, equipment_id: str, reason: str = None):
        """Log equipment disconnection event."""
        self.logger.info(
            f"Equipment disconnection: {equipment_id}",
            extra={
                "equipment_id": equipment_id,
                "event": "disconnection",
                "reason": reason
            }
        )

    def log_command(self, equipment_id: str, command: str, success: bool, duration_ms: float, error: str = None):
        """Log equipment command execution."""
        self.logger.info(
            f"Equipment command: {equipment_id} - {command}",
            extra={
                "equipment_id": equipment_id,
                "event": "command",
                "command": command,
                "success": success,
                "duration_ms": round(duration_ms, 2),
                "error": error
            }
        )

    def log_error(self, equipment_id: str, error_type: str, error_message: str):
        """Log equipment error."""
        self.logger.error(
            f"Equipment error: {equipment_id} - {error_type}",
            extra={
                "equipment_id": equipment_id,
                "event": "error",
                "error_type": error_type,
                "error_message": error_message
            }
        )

    def log_state_change(self, equipment_id: str, old_state: str, new_state: str):
        """Log equipment state change."""
        self.logger.info(
            f"Equipment state change: {equipment_id} ({old_state} -> {new_state})",
            extra={
                "equipment_id": equipment_id,
                "event": "state_change",
                "old_state": old_state,
                "new_state": new_state
            }
        )

    def log_health_check(self, equipment_id: str, is_healthy: bool, metrics: dict):
        """Log equipment health check result."""
        self.logger.info(
            f"Equipment health check: {equipment_id}",
            extra={
                "equipment_id": equipment_id,
                "event": "health_check",
                "is_healthy": is_healthy,
                **metrics
            }
        )


# Global equipment event logger instance
equipment_event_logger = EquipmentEventLogger()
