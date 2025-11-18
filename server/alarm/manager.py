"""Alarm monitoring and management."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, TYPE_CHECKING, Any

from .models import (AlarmAcknowledgment, AlarmCondition, AlarmConfig,
                     AlarmEvent, AlarmSeverity, AlarmState, AlarmStatistics)

if TYPE_CHECKING:
    from websocket_server import StreamManager

logger = logging.getLogger(__name__)


class AlarmManager:
    """Manages alarm monitoring, triggering, and lifecycle."""

    def __init__(self):
        """Initialize alarm manager."""
        self._alarms: Dict[str, AlarmConfig] = {}
        self._events: Dict[str, AlarmEvent] = {}
        self._active_events: Dict[str, str] = {}  # alarm_id -> event_id
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._event_history: List[AlarmEvent] = []
        self._max_history_size = 1000
        self._lock = asyncio.Lock()
        self._stream_manager: Optional["StreamManager"] = None

    def set_stream_manager(self, stream_manager: "StreamManager"):
        """Set the WebSocket stream manager for broadcasting alarm events.

        Args:
            stream_manager: WebSocket stream manager instance
        """
        self._stream_manager = stream_manager
        logger.info("WebSocket stream manager set for alarm broadcasting")

    async def create_alarm(self, config: AlarmConfig) -> AlarmConfig:
        """
        Create a new alarm configuration.

        Args:
            config: Alarm configuration

        Returns:
            Created alarm configuration
        """
        async with self._lock:
            if config.alarm_id in self._alarms:
                raise ValueError(f"Alarm {config.alarm_id} already exists")

            self._alarms[config.alarm_id] = config

            # Start monitoring if enabled
            if config.enabled:
                await self._start_monitoring(config.alarm_id)

            logger.info(f"Created alarm: {config.alarm_id} ({config.name})")

            return config

    async def update_alarm(self, alarm_id: str, config: AlarmConfig) -> AlarmConfig:
        """
        Update alarm configuration.

        Args:
            alarm_id: Alarm ID to update
            config: New configuration

        Returns:
            Updated configuration
        """
        async with self._lock:
            if alarm_id not in self._alarms:
                raise ValueError(f"Alarm {alarm_id} not found")

            # Stop monitoring if running
            if alarm_id in self._monitoring_tasks:
                await self._stop_monitoring(alarm_id)

            self._alarms[alarm_id] = config

            # Restart monitoring if enabled
            if config.enabled:
                await self._start_monitoring(alarm_id)

            logger.info(f"Updated alarm: {alarm_id}")

            return config

    async def delete_alarm(self, alarm_id: str) -> bool:
        """
        Delete an alarm configuration.

        Args:
            alarm_id: Alarm ID to delete

        Returns:
            True if deleted successfully
        """
        async with self._lock:
            if alarm_id not in self._alarms:
                return False

            # Stop monitoring
            if alarm_id in self._monitoring_tasks:
                await self._stop_monitoring(alarm_id)

            # Clear any active events
            if alarm_id in self._active_events:
                event_id = self._active_events[alarm_id]
                if event_id in self._events:
                    self._events[event_id].state = AlarmState.CLEARED
                    self._events[event_id].cleared_at = datetime.now()
                del self._active_events[alarm_id]

            del self._alarms[alarm_id]

            logger.info(f"Deleted alarm: {alarm_id}")

            return True

    async def enable_alarm(self, alarm_id: str) -> bool:
        """Enable an alarm."""
        async with self._lock:
            if alarm_id not in self._alarms:
                return False

            self._alarms[alarm_id].enabled = True
            await self._start_monitoring(alarm_id)

            logger.info(f"Enabled alarm: {alarm_id}")

            return True

    async def disable_alarm(self, alarm_id: str) -> bool:
        """Disable an alarm."""
        async with self._lock:
            if alarm_id not in self._alarms:
                return False

            self._alarms[alarm_id].enabled = False
            await self._stop_monitoring(alarm_id)

            logger.info(f"Disabled alarm: {alarm_id}")

            return True

    async def check_alarm(self, alarm_id: str, value: float) -> Optional[AlarmEvent]:
        """
        Manually check an alarm condition.

        Args:
            alarm_id: Alarm ID to check
            value: Current value to check

        Returns:
            AlarmEvent if alarm triggered, None otherwise
        """
        if alarm_id not in self._alarms:
            return None

        config = self._alarms[alarm_id]

        if not config.enabled:
            return None

        # Check if condition is met
        triggered = self._evaluate_condition(config, value)

        if triggered:
            return await self._trigger_alarm(alarm_id, value)
        else:
            # Auto-clear if enabled
            if config.auto_clear and alarm_id in self._active_events:
                return await self._clear_alarm(alarm_id)

        return None

    async def acknowledge_alarm(self, acknowledgment: AlarmAcknowledgment) -> bool:
        """
        Acknowledge an alarm event.

        Args:
            acknowledgment: Acknowledgment data

        Returns:
            True if acknowledged successfully
        """
        async with self._lock:
            if acknowledgment.event_id not in self._events:
                return False

            event = self._events[acknowledgment.event_id]

            if event.state != AlarmState.ACTIVE:
                return False

            event.state = AlarmState.ACKNOWLEDGED
            event.acknowledged_at = acknowledgment.timestamp
            event.acknowledged_by = acknowledgment.acknowledged_by
            event.acknowledgment_note = acknowledgment.note

            logger.info(
                f"Acknowledged alarm event: {acknowledgment.event_id} by {acknowledgment.acknowledged_by}"
            )

            # Broadcast alarm_updated event via WebSocket
            await self._broadcast_alarm_updated(event)

            return True

    async def clear_alarm(self, alarm_id: str) -> bool:
        """
        Manually clear an alarm.

        Args:
            alarm_id: Alarm ID to clear

        Returns:
            True if cleared successfully
        """
        result = await self._clear_alarm(alarm_id)
        return result is not None

    def get_alarm(self, alarm_id: str) -> Optional[AlarmConfig]:
        """Get alarm configuration by ID."""
        return self._alarms.get(alarm_id)

    def list_alarms(self) -> List[AlarmConfig]:
        """List all alarm configurations."""
        return list(self._alarms.values())

    def get_event(self, event_id: str) -> Optional[AlarmEvent]:
        """Get alarm event by ID."""
        return self._events.get(event_id)

    def list_active_events(self) -> List[AlarmEvent]:
        """List all active alarm events."""
        return [
            self._events[event_id]
            for event_id in self._active_events.values()
            if event_id in self._events
        ]

    def list_events(
        self,
        state: Optional[AlarmState] = None,
        severity: Optional[AlarmSeverity] = None,
        equipment_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AlarmEvent]:
        """
        List alarm events with filtering.

        Args:
            state: Filter by state
            severity: Filter by severity
            equipment_id: Filter by equipment
            limit: Maximum number of events to return

        Returns:
            List of matching alarm events
        """
        events = list(self._events.values()) + self._event_history

        # Filter
        if state:
            events = [e for e in events if e.state == state]
        if severity:
            events = [e for e in events if e.severity == severity]
        if equipment_id:
            events = [e for e in events if e.equipment_id == equipment_id]

        # Sort by triggered time (newest first)
        events.sort(key=lambda e: e.triggered_at, reverse=True)

        return events[:limit]

    def get_statistics(self) -> AlarmStatistics:
        """Get alarm system statistics."""
        active_events = self.list_active_events()

        stats = AlarmStatistics(
            total_active=len(
                [e for e in active_events if e.state == AlarmState.ACTIVE]
            ),
            total_acknowledged=len(
                [e for e in active_events if e.state == AlarmState.ACKNOWLEDGED]
            ),
            total_cleared=len(self._event_history),
        )

        # Count by severity
        severity_counts = defaultdict(int)
        for event in active_events:
            severity_counts[event.severity] += 1
        stats.by_severity = dict(severity_counts)

        # Count by equipment
        equipment_counts = defaultdict(int)
        for event in active_events:
            if event.equipment_id:
                equipment_counts[event.equipment_id] += 1
        stats.by_equipment = dict(equipment_counts)

        # Most frequent alarms (from history)
        alarm_counts = defaultdict(int)
        for event in self._event_history:
            alarm_counts[event.alarm_id] += 1

        stats.most_frequent = [
            {"alarm_id": alarm_id, "count": count}
            for alarm_id, count in sorted(
                alarm_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]
        ]

        return stats

    async def _start_monitoring(self, alarm_id: str):
        """Start monitoring an alarm (internal)."""
        if alarm_id in self._monitoring_tasks:
            return

        config = self._alarms[alarm_id]

        # Only monitor threshold-based alarms automatically
        if config.alarm_type in [
            AlarmType.THRESHOLD,
            AlarmType.DEVIATION,
            AlarmType.RATE_OF_CHANGE,
        ]:
            task = asyncio.create_task(self._monitoring_loop(alarm_id))
            self._monitoring_tasks[alarm_id] = task

    async def _stop_monitoring(self, alarm_id: str):
        """Stop monitoring an alarm (internal)."""
        if alarm_id in self._monitoring_tasks:
            self._monitoring_tasks[alarm_id].cancel()
            del self._monitoring_tasks[alarm_id]

    async def _monitoring_loop(self, alarm_id: str):
        """Background monitoring loop for an alarm."""
        try:
            config = self._alarms[alarm_id]

            while True:
                if not config.enabled:
                    break

                # Get current value from equipment
                if config.equipment_id:
                    from equipment.manager import equipment_manager

                    equipment = equipment_manager.get_equipment(config.equipment_id)
                    if equipment:
                        try:
                            # Try to get the parameter value
                            value = await self._get_parameter_value(
                                equipment, config.parameter
                            )

                            if value is not None:
                                await self.check_alarm(alarm_id, value)

                        except Exception as e:
                            logger.error(
                                f"Error reading parameter {config.parameter} from {config.equipment_id}: {e}"
                            )

                # Check every 1 second
                await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            logger.debug(f"Monitoring cancelled for alarm {alarm_id}")
        except Exception as e:
            logger.error(f"Error in monitoring loop for alarm {alarm_id}: {e}")

    async def _get_parameter_value(self, equipment, parameter: str) -> Optional[float]:
        """Get parameter value from equipment."""
        # Try common parameter names
        try:
            if parameter in ["voltage", "v", "volt"]:
                result = await equipment.execute_command("get_voltage", {})
                return float(result.voltage) if hasattr(result, "voltage") else None
            elif parameter in ["current", "i", "amp"]:
                result = await equipment.execute_command("get_current", {})
                return float(result.current) if hasattr(result, "current") else None
            elif parameter in ["power", "p", "watt"]:
                result = await equipment.execute_command("get_power", {})
                return float(result.power) if hasattr(result, "power") else None
            elif parameter in ["temperature", "temp", "t"]:
                result = await equipment.execute_command("get_temperature", {})
                return (
                    float(result.temperature)
                    if hasattr(result, "temperature")
                    else None
                )
            else:
                # Try generic get command
                result = await equipment.execute_command(f"get_{parameter}", {})
                if hasattr(result, parameter):
                    return float(getattr(result, parameter))
        except Exception:
            pass

        return None

    def _evaluate_condition(self, config: AlarmConfig, value: float) -> bool:
        """Evaluate if alarm condition is met."""
        if config.threshold is None and config.condition not in [
            AlarmCondition.IN_RANGE,
            AlarmCondition.OUT_OF_RANGE,
        ]:
            return False

        if config.condition == AlarmCondition.GREATER_THAN:
            return value > config.threshold
        elif config.condition == AlarmCondition.LESS_THAN:
            return value < config.threshold
        elif config.condition == AlarmCondition.EQUAL_TO:
            deadband = config.deadband or 0.0
            return abs(value - config.threshold) <= deadband
        elif config.condition == AlarmCondition.NOT_EQUAL_TO:
            deadband = config.deadband or 0.0
            return abs(value - config.threshold) > deadband
        elif config.condition == AlarmCondition.IN_RANGE:
            if config.threshold_low is None or config.threshold_high is None:
                return False
            return config.threshold_low <= value <= config.threshold_high
        elif config.condition == AlarmCondition.OUT_OF_RANGE:
            if config.threshold_low is None or config.threshold_high is None:
                return False
            return value < config.threshold_low or value > config.threshold_high

        return False

    async def _trigger_alarm(self, alarm_id: str, value: float) -> AlarmEvent:
        """Trigger an alarm (internal)."""
        # Check if already active
        if alarm_id in self._active_events:
            return self._events[self._active_events[alarm_id]]

        config = self._alarms[alarm_id]

        # Create alarm event
        event = AlarmEvent(
            alarm_id=alarm_id,
            severity=config.severity,
            message=f"Alarm: {config.name} - {config.parameter} = {value}",
            equipment_id=config.equipment_id,
            parameter=config.parameter,
            value=value,
            threshold=config.threshold,
        )

        self._events[event.event_id] = event
        self._active_events[alarm_id] = event.event_id

        logger.warning(f"Alarm triggered: {config.name} ({alarm_id}) - {event.message}")

        # Send notifications
        await self._send_notifications(event, config)

        # Broadcast alarm_event via WebSocket
        await self._broadcast_alarm_event(event, config)

        return event

    async def _clear_alarm(self, alarm_id: str) -> Optional[AlarmEvent]:
        """Clear an alarm (internal)."""
        if alarm_id not in self._active_events:
            return None

        event_id = self._active_events[alarm_id]
        event = self._events[event_id]

        event.state = AlarmState.CLEARED
        event.cleared_at = datetime.now()

        # Move to history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history.pop(0)

        del self._active_events[alarm_id]
        del self._events[event_id]

        logger.info(f"Alarm cleared: {alarm_id}")

        # Broadcast alarm_cleared event via WebSocket
        await self._broadcast_alarm_cleared(event)

        return event

    async def _send_notifications(self, event: AlarmEvent, config: AlarmConfig):
        """Send notifications for an alarm event."""
        from .notifications import notification_manager

        for method in config.notifications:
            try:
                await notification_manager.send_notification(method, event, config)
                event.notifications_sent.append(method)
                event.notification_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to send {method} notification for alarm {config.alarm_id}: {e}"
                )

    async def _broadcast_alarm_event(self, event: AlarmEvent, config: AlarmConfig):
        """Broadcast new alarm event via WebSocket.

        Args:
            event: Alarm event that was triggered
            config: Alarm configuration
        """
        if not self._stream_manager:
            return

        try:
            message = {
                "type": "alarm_event",
                "data": {
                    "event_id": event.event_id,
                    "alarm_id": event.alarm_id,
                    "alarm_name": config.name,
                    "severity": event.severity.value,
                    "state": event.state.value,
                    "equipment_id": event.equipment_id,
                    "parameter": event.parameter,
                    "value": event.value,
                    "threshold": event.threshold,
                    "message": event.message,
                    "timestamp": event.triggered_at.isoformat(),
                }
            }
            await self._stream_manager.broadcast(message)
            logger.debug(f"Broadcasted alarm event: {event.event_id}")
        except Exception as e:
            logger.error(f"Failed to broadcast alarm event: {e}")

    async def _broadcast_alarm_updated(self, event: AlarmEvent):
        """Broadcast alarm updated event via WebSocket.

        Args:
            event: Alarm event that was updated
        """
        if not self._stream_manager:
            return

        try:
            message = {
                "type": "alarm_updated",
                "data": {
                    "event_id": event.event_id,
                    "state": event.state.value,
                    "acknowledged_at": event.acknowledged_at.isoformat() if event.acknowledged_at else None,
                    "acknowledged_by": event.acknowledged_by,
                }
            }
            await self._stream_manager.broadcast(message)
            logger.debug(f"Broadcasted alarm updated: {event.event_id}")
        except Exception as e:
            logger.error(f"Failed to broadcast alarm updated: {e}")

    async def _broadcast_alarm_cleared(self, event: AlarmEvent):
        """Broadcast alarm cleared event via WebSocket.

        Args:
            event: Alarm event that was cleared
        """
        if not self._stream_manager:
            return

        try:
            message = {
                "type": "alarm_cleared",
                "data": {
                    "event_id": event.event_id,
                }
            }
            await self._stream_manager.broadcast(message)
            logger.debug(f"Broadcasted alarm cleared: {event.event_id}")
        except Exception as e:
            logger.error(f"Failed to broadcast alarm cleared: {e}")


# Import here to avoid circular dependency
from .models import AlarmType

# Global alarm manager instance
alarm_manager = AlarmManager()
