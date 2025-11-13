"""Error handling and recovery system for equipment connections."""

import logging
import asyncio
from typing import Optional, Callable, Any
from datetime import datetime, timedelta
from enum import Enum

from server.config.settings import settings

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EquipmentError(Exception):
    """Base exception for equipment-related errors."""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recoverable: bool = True,
        troubleshooting_hint: Optional[str] = None
    ):
        self.message = message
        self.severity = severity
        self.recoverable = recoverable
        self.troubleshooting_hint = troubleshooting_hint
        self.timestamp = datetime.now()
        super().__init__(self.message)

    def __str__(self):
        base = f"[{self.severity.value.upper()}] {self.message}"
        if self.troubleshooting_hint:
            base += f"\n  💡 Hint: {self.troubleshooting_hint}"
        return base


class ConnectionError(EquipmentError):
    """Equipment connection error."""

    def __init__(self, resource_string: str, original_error: Exception):
        super().__init__(
            message=f"Failed to connect to {resource_string}: {str(original_error)}",
            severity=ErrorSeverity.HIGH,
            recoverable=True,
            troubleshooting_hint=(
                "Check: 1) Equipment is powered on, "
                "2) USB/Network cable is connected, "
                "3) Equipment is not in use by another application, "
                "4) VISA drivers are installed correctly"
            )
        )
        self.resource_string = resource_string
        self.original_error = original_error


class CommandError(EquipmentError):
    """Equipment command execution error."""

    def __init__(self, command: str, equipment_id: str, original_error: Exception):
        super().__init__(
            message=f"Command '{command}' failed on equipment {equipment_id}: {str(original_error)}",
            severity=ErrorSeverity.MEDIUM,
            recoverable=True,
            troubleshooting_hint=(
                "Check: 1) Equipment is still connected, "
                "2) Command parameters are valid, "
                "3) Equipment is not in an error state"
            )
        )
        self.command = command
        self.equipment_id = equipment_id
        self.original_error = original_error


class TimeoutError(EquipmentError):
    """Equipment operation timeout error."""

    def __init__(self, operation: str, timeout_ms: int):
        super().__init__(
            message=f"Operation '{operation}' timed out after {timeout_ms}ms",
            severity=ErrorSeverity.HIGH,
            recoverable=True,
            troubleshooting_hint=(
                "Try: 1) Increasing the timeout value, "
                "2) Checking equipment responsiveness, "
                "3) Reducing command complexity"
            )
        )
        self.operation = operation
        self.timeout_ms = timeout_ms


class RetryHandler:
    """Handles command retry logic with exponential backoff."""

    def __init__(self):
        self.max_retries = settings.max_command_retries
        self.retry_delay_ms = settings.retry_delay_ms
        self.enabled = settings.enable_command_retry

    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        operation_name: str = "operation",
        **kwargs
    ) -> Any:
        """
        Execute a function with retry logic.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            operation_name: Name of operation for logging
            **kwargs: Keyword arguments for func

        Returns:
            Result of successful function execution

        Raises:
            Exception: If all retries are exhausted
        """
        if not self.enabled:
            return await func(*args, **kwargs)

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                if attempt > 0:
                    logger.info(f"{operation_name} succeeded on retry {attempt}")
                return result

            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay_ms = self.retry_delay_ms * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{self.max_retries + 1}). "
                        f"Retrying in {delay_ms}ms... Error: {str(e)}"
                    )
                    await asyncio.sleep(delay_ms / 1000.0)
                else:
                    logger.error(
                        f"{operation_name} failed after {self.max_retries + 1} attempts"
                    )

        raise last_error


class ReconnectionHandler:
    """Handles automatic reconnection with exponential backoff."""

    def __init__(self):
        self.max_attempts = settings.reconnect_attempts
        self.base_delay_ms = settings.reconnect_delay_ms
        self.backoff_multiplier = settings.reconnect_backoff_multiplier
        self.enabled = settings.enable_auto_reconnect

    async def attempt_reconnect(
        self,
        connect_func: Callable,
        equipment_id: str,
        *args,
        **kwargs
    ) -> bool:
        """
        Attempt to reconnect to equipment.

        Args:
            connect_func: Async function that performs connection
            equipment_id: Equipment identifier
            *args: Arguments for connect_func
            **kwargs: Keyword arguments for connect_func

        Returns:
            bool: True if reconnection successful, False otherwise
        """
        if not self.enabled:
            logger.info(f"Auto-reconnect disabled for {equipment_id}")
            return False

        logger.info(f"Attempting to reconnect to {equipment_id}...")

        for attempt in range(self.max_attempts):
            try:
                delay_ms = self.base_delay_ms * (self.backoff_multiplier ** attempt)

                if attempt > 0:
                    logger.info(
                        f"Reconnection attempt {attempt + 1}/{self.max_attempts} "
                        f"for {equipment_id} in {delay_ms:.0f}ms..."
                    )
                    await asyncio.sleep(delay_ms / 1000.0)

                await connect_func(*args, **kwargs)
                logger.info(f"✅ Successfully reconnected to {equipment_id}")
                return True

            except Exception as e:
                logger.warning(
                    f"Reconnection attempt {attempt + 1}/{self.max_attempts} failed for {equipment_id}: {e}"
                )

        logger.error(f"❌ Failed to reconnect to {equipment_id} after {self.max_attempts} attempts")
        return False


class HealthMonitor:
    """Monitors equipment health and triggers recovery actions."""

    def __init__(self):
        self.enabled = settings.enable_health_monitoring
        self.check_interval_sec = settings.health_check_interval_sec
        self.equipment_health = {}  # equipment_id -> last_check_time
        self._monitor_task: Optional[asyncio.Task] = None

    async def start(self, equipment_manager):
        """Start health monitoring."""
        if not self.enabled:
            logger.info("Health monitoring disabled")
            return

        logger.info(f"Starting health monitoring (interval: {self.check_interval_sec}s)")
        self._monitor_task = asyncio.create_task(self._monitor_loop(equipment_manager))

    async def stop(self):
        """Stop health monitoring."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("Health monitoring stopped")

    async def _monitor_loop(self, equipment_manager):
        """Main monitoring loop."""
        while True:
            try:
                await asyncio.sleep(self.check_interval_sec)
                await self._check_all_equipment(equipment_manager)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")

    async def _check_all_equipment(self, equipment_manager):
        """Check health of all connected equipment."""
        for equipment_id, equipment in equipment_manager.equipment.items():
            try:
                # Perform health check (get status)
                status = await equipment.get_status()

                if not status.connected:
                    logger.warning(f"Health check failed for {equipment_id} - disconnected")
                    # Trigger reconnection
                    reconnect_handler = ReconnectionHandler()
                    await reconnect_handler.attempt_reconnect(
                        equipment.connect,
                        equipment_id
                    )
                else:
                    self.equipment_health[equipment_id] = datetime.now()

            except Exception as e:
                logger.error(f"Health check error for {equipment_id}: {e}")


# Global instances
retry_handler = RetryHandler()
reconnection_handler = ReconnectionHandler()
health_monitor = HealthMonitor()
