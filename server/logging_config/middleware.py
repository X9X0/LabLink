"""Logging middleware for FastAPI."""

import time
import logging
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable, Optional, Dict, Any

# Create loggers
access_logger = logging.getLogger("lablink.access")
audit_logger = logging.getLogger("lablink.audit")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses."""

    def _extract_user_info(self, request: Request) -> Dict[str, Any]:
        """
        Extract user identification from request.

        Supports multiple authentication schemes:
        - JWT tokens (Authorization header)
        - API keys (X-API-Key header)
        - Session-based auth (request.user)
        - Custom headers (X-User-ID, X-User-Name)
        """
        user_info = {
            "user_id": None,
            "user_name": None,
            "user_email": None,
            "user_role": None,
            "auth_method": None
        }

        # 1. Check for user in request state (set by auth middleware)
        if hasattr(request.state, "user"):
            user = request.state.user
            if user:
                user_info["user_id"] = getattr(user, "id", None) or getattr(user, "user_id", None)
                user_info["user_name"] = getattr(user, "name", None) or getattr(user, "username", None)
                user_info["user_email"] = getattr(user, "email", None)
                user_info["user_role"] = getattr(user, "role", None)
                user_info["auth_method"] = "session"
                return user_info

        # 2. Check for custom user headers
        if request.headers.get("X-User-ID"):
            user_info["user_id"] = request.headers.get("X-User-ID")
            user_info["user_name"] = request.headers.get("X-User-Name")
            user_info["user_email"] = request.headers.get("X-User-Email")
            user_info["user_role"] = request.headers.get("X-User-Role")
            user_info["auth_method"] = "custom_header"
            return user_info

        # 3. Check for API key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # In production, look up user by API key
            user_info["user_id"] = f"api_key_{api_key[:8]}"
            user_info["auth_method"] = "api_key"
            return user_info

        # 4. Check for JWT token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # In production, decode and validate JWT
            # For now, just indicate JWT was used
            user_info["auth_method"] = "jwt"
            # You would decode the JWT here and extract user info
            # token = auth_header.split(" ")[1]
            # decoded = jwt.decode(token, ...)
            # user_info["user_id"] = decoded.get("sub")
            # user_info["user_name"] = decoded.get("name")
            return user_info

        # 5. Anonymous user
        user_info["user_id"] = "anonymous"
        user_info["auth_method"] = "none"
        return user_info

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

        # Extract user information
        user_info = self._extract_user_info(request)

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
                    "error": error,
                    # User identification
                    "user_id": user_info["user_id"],
                    "user_name": user_info["user_name"],
                    "user_role": user_info["user_role"],
                    "auth_method": user_info["auth_method"]
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
                        "action": self._extract_action(method, path),
                        # User identification
                        "user_id": user_info["user_id"],
                        "user_name": user_info["user_name"],
                        "user_email": user_info["user_email"],
                        "user_role": user_info["user_role"],
                        "auth_method": user_info["auth_method"]
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

    def log_connection(self, equipment_id: str, address: str, success: bool, error: str = None,
                      user_id: Optional[str] = None, user_name: Optional[str] = None):
        """Log equipment connection event."""
        extra = {
            "equipment_id": equipment_id,
            "address": address,
            "event": "connection",
            "success": success,
            "error": error
        }
        if user_id:
            extra["user_id"] = user_id
        if user_name:
            extra["user_name"] = user_name

        self.logger.info(
            f"Equipment connection: {equipment_id}",
            extra=extra
        )

    def log_disconnection(self, equipment_id: str, reason: str = None,
                         user_id: Optional[str] = None, user_name: Optional[str] = None):
        """Log equipment disconnection event."""
        extra = {
            "equipment_id": equipment_id,
            "event": "disconnection",
            "reason": reason
        }
        if user_id:
            extra["user_id"] = user_id
        if user_name:
            extra["user_name"] = user_name

        self.logger.info(
            f"Equipment disconnection: {equipment_id}",
            extra=extra
        )

    def log_command(self, equipment_id: str, command: str, success: bool, duration_ms: float,
                   error: str = None, user_id: Optional[str] = None, user_name: Optional[str] = None):
        """Log equipment command execution."""
        extra = {
            "equipment_id": equipment_id,
            "event": "command",
            "command": command,
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "error": error
        }
        if user_id:
            extra["user_id"] = user_id
        if user_name:
            extra["user_name"] = user_name

        self.logger.info(
            f"Equipment command: {equipment_id} - {command}",
            extra=extra
        )

    def log_error(self, equipment_id: str, error_type: str, error_message: str,
                 user_id: Optional[str] = None, user_name: Optional[str] = None):
        """Log equipment error."""
        extra = {
            "equipment_id": equipment_id,
            "event": "error",
            "error_type": error_type,
            "error_message": error_message
        }
        if user_id:
            extra["user_id"] = user_id
        if user_name:
            extra["user_name"] = user_name

        self.logger.error(
            f"Equipment error: {equipment_id} - {error_type}",
            extra=extra
        )

    def log_state_change(self, equipment_id: str, old_state: str, new_state: str,
                        user_id: Optional[str] = None, user_name: Optional[str] = None):
        """Log equipment state change."""
        extra = {
            "equipment_id": equipment_id,
            "event": "state_change",
            "old_state": old_state,
            "new_state": new_state
        }
        if user_id:
            extra["user_id"] = user_id
        if user_name:
            extra["user_name"] = user_name

        self.logger.info(
            f"Equipment state change: {equipment_id} ({old_state} -> {new_state})",
            extra=extra
        )

    def log_health_check(self, equipment_id: str, is_healthy: bool, metrics: dict,
                        user_id: Optional[str] = None, user_name: Optional[str] = None):
        """Log equipment health check result."""
        extra = {
            "equipment_id": equipment_id,
            "event": "health_check",
            "is_healthy": is_healthy,
            **metrics
        }
        if user_id:
            extra["user_id"] = user_id
        if user_name:
            extra["user_name"] = user_name

        self.logger.info(
            f"Equipment health check: {equipment_id}",
            extra=extra
        )


# Global equipment event logger instance
equipment_event_logger = EquipmentEventLogger()
