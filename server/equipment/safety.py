"""Safety limits and interlocks system for equipment protection."""

import logging
import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel, Field

from server.config.settings import settings

logger = logging.getLogger(__name__)


class SafetyViolationType(Enum):
    """Types of safety violations."""
    VOLTAGE_LIMIT = "voltage_limit"
    CURRENT_LIMIT = "current_limit"
    POWER_LIMIT = "power_limit"
    SLEW_RATE = "slew_rate"
    INTERLOCK = "interlock"
    EMERGENCY_STOP = "emergency_stop"


class SafetyLimits(BaseModel):
    """Safety limits for equipment."""

    # Voltage limits
    max_voltage: Optional[float] = Field(None, description="Maximum voltage (V)")
    min_voltage: Optional[float] = Field(0.0, description="Minimum voltage (V)")

    # Current limits
    max_current: Optional[float] = Field(None, description="Maximum current (A)")
    min_current: Optional[float] = Field(0.0, description="Minimum current (A)")

    # Power limits
    max_power: Optional[float] = Field(None, description="Maximum power (W)")

    # Slew rate limits (for gradual changes)
    voltage_slew_rate: Optional[float] = Field(None, description="Max voltage change rate (V/s)")
    current_slew_rate: Optional[float] = Field(None, description="Max current change rate (A/s)")

    # Additional limits
    temperature_limit: Optional[float] = Field(None, description="Maximum temperature (°C)")

    # Interlock requirements
    require_interlock: bool = Field(False, description="Require interlock before operation")

    class Config:
        json_schema_extra = {
            "example": {
                "max_voltage": 30.0,
                "max_current": 5.0,
                "max_power": 150.0,
                "voltage_slew_rate": 10.0,
                "require_interlock": False
            }
        }


class SafetyViolation(Exception):
    """Exception raised when safety limit is violated."""

    def __init__(
        self,
        violation_type: SafetyViolationType,
        message: str,
        attempted_value: Optional[float] = None,
        limit_value: Optional[float] = None,
        equipment_id: Optional[str] = None
    ):
        self.violation_type = violation_type
        self.message = message
        self.attempted_value = attempted_value
        self.limit_value = limit_value
        self.equipment_id = equipment_id
        self.timestamp = datetime.now()

        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format violation message."""
        msg = f"[SAFETY VIOLATION - {self.violation_type.value.upper()}] {self.message}"

        if self.attempted_value is not None and self.limit_value is not None:
            msg += f"\n  Attempted: {self.attempted_value}, Limit: {self.limit_value}"

        if self.equipment_id:
            msg += f"\n  Equipment: {self.equipment_id}"

        msg += "\n  🛑 Action blocked for safety"

        return msg


class SafetyEvent(BaseModel):
    """Record of a safety event."""
    timestamp: datetime = Field(default_factory=datetime.now)
    equipment_id: str
    violation_type: SafetyViolationType
    message: str
    attempted_value: Optional[float] = None
    limit_value: Optional[float] = None
    action_taken: str


class SlewRateLimiter:
    """Limits the rate of change for parameters."""

    def __init__(self):
        self._last_values: Dict[str, float] = {}
        self._last_times: Dict[str, datetime] = {}

    async def check_and_limit(
        self,
        key: str,
        new_value: float,
        current_value: float,
        max_slew_rate: float
    ) -> float:
        """
        Check slew rate and return safe value.

        Args:
            key: Unique identifier for the parameter
            new_value: Desired new value
            current_value: Current value
            max_slew_rate: Maximum rate of change per second

        Returns:
            Safe value that doesn't exceed slew rate
        """
        now = datetime.now()

        # First time or after long delay - allow full change
        if key not in self._last_times:
            self._last_values[key] = new_value
            self._last_times[key] = now
            return new_value

        # Calculate time since last change
        time_delta = (now - self._last_times[key]).total_seconds()

        if time_delta <= 0:
            time_delta = 0.001  # Minimum 1ms

        # Calculate maximum allowed change
        max_change = max_slew_rate * time_delta

        # Calculate actual change
        change = new_value - current_value

        # Limit the change
        if abs(change) > max_change:
            # Limit exceeded, calculate safe value
            safe_value = current_value + (max_change if change > 0 else -max_change)

            logger.warning(
                f"Slew rate limit applied for {key}: "
                f"requested {new_value}, limited to {safe_value} "
                f"(max change: {max_change} over {time_delta:.3f}s)"
            )

            self._last_values[key] = safe_value
            self._last_times[key] = now
            return safe_value
        else:
            # Within limits
            self._last_values[key] = new_value
            self._last_times[key] = now
            return new_value


class SafetyValidator:
    """Validates operations against safety limits."""

    def __init__(self, limits: SafetyLimits, equipment_id: str):
        self.limits = limits
        self.equipment_id = equipment_id
        self.slew_limiter = SlewRateLimiter()
        self._interlock_state = False
        self._safety_events: List[SafetyEvent] = []

    def check_voltage(self, voltage: float) -> None:
        """
        Check if voltage is within limits.

        Raises:
            SafetyViolation: If voltage exceeds limits
        """
        if self.limits.max_voltage is not None and voltage > self.limits.max_voltage:
            raise SafetyViolation(
                SafetyViolationType.VOLTAGE_LIMIT,
                f"Voltage {voltage}V exceeds maximum limit",
                attempted_value=voltage,
                limit_value=self.limits.max_voltage,
                equipment_id=self.equipment_id
            )

        if self.limits.min_voltage is not None and voltage < self.limits.min_voltage:
            raise SafetyViolation(
                SafetyViolationType.VOLTAGE_LIMIT,
                f"Voltage {voltage}V below minimum limit",
                attempted_value=voltage,
                limit_value=self.limits.min_voltage,
                equipment_id=self.equipment_id
            )

    def check_current(self, current: float) -> None:
        """
        Check if current is within limits.

        Raises:
            SafetyViolation: If current exceeds limits
        """
        if self.limits.max_current is not None and current > self.limits.max_current:
            raise SafetyViolation(
                SafetyViolationType.CURRENT_LIMIT,
                f"Current {current}A exceeds maximum limit",
                attempted_value=current,
                limit_value=self.limits.max_current,
                equipment_id=self.equipment_id
            )

        if self.limits.min_current is not None and current < self.limits.min_current:
            raise SafetyViolation(
                SafetyViolationType.CURRENT_LIMIT,
                f"Current {current}A below minimum limit",
                attempted_value=current,
                limit_value=self.limits.min_current,
                equipment_id=self.equipment_id
            )

    def check_power(self, power: float) -> None:
        """
        Check if power is within limits.

        Raises:
            SafetyViolation: If power exceeds limits
        """
        if self.limits.max_power is not None and power > self.limits.max_power:
            raise SafetyViolation(
                SafetyViolationType.POWER_LIMIT,
                f"Power {power}W exceeds maximum limit",
                attempted_value=power,
                limit_value=self.limits.max_power,
                equipment_id=self.equipment_id
            )

    def check_interlock(self) -> None:
        """
        Check if interlock is satisfied.

        Raises:
            SafetyViolation: If interlock is required but not engaged
        """
        if self.limits.require_interlock and not self._interlock_state:
            raise SafetyViolation(
                SafetyViolationType.INTERLOCK,
                "Interlock required but not engaged",
                equipment_id=self.equipment_id
            )

    def set_interlock(self, state: bool) -> None:
        """Set interlock state."""
        self._interlock_state = state
        logger.info(f"Interlock {'engaged' if state else 'released'} for {self.equipment_id}")

    async def apply_voltage_slew_limit(
        self,
        new_voltage: float,
        current_voltage: float
    ) -> float:
        """
        Apply slew rate limiting to voltage change.

        Returns:
            Safe voltage value
        """
        if self.limits.voltage_slew_rate is None:
            return new_voltage

        return await self.slew_limiter.check_and_limit(
            f"{self.equipment_id}_voltage",
            new_voltage,
            current_voltage,
            self.limits.voltage_slew_rate
        )

    async def apply_current_slew_limit(
        self,
        new_current: float,
        current_current: float
    ) -> float:
        """
        Apply slew rate limiting to current change.

        Returns:
            Safe current value
        """
        if self.limits.current_slew_rate is None:
            return new_current

        return await self.slew_limiter.check_and_limit(
            f"{self.equipment_id}_current",
            new_current,
            current_current,
            self.limits.current_slew_rate
        )

    def log_safety_event(
        self,
        violation_type: SafetyViolationType,
        message: str,
        attempted_value: Optional[float] = None,
        limit_value: Optional[float] = None,
        action_taken: str = "blocked"
    ):
        """Log a safety event."""
        event = SafetyEvent(
            equipment_id=self.equipment_id,
            violation_type=violation_type,
            message=message,
            attempted_value=attempted_value,
            limit_value=limit_value,
            action_taken=action_taken
        )

        self._safety_events.append(event)
        logger.warning(f"Safety event: {message} - {action_taken}")

        # Keep only last 100 events
        if len(self._safety_events) > 100:
            self._safety_events = self._safety_events[-100:]

    def get_safety_events(self, limit: int = 50) -> List[SafetyEvent]:
        """Get recent safety events."""
        return self._safety_events[-limit:]


class EmergencyStopManager:
    """Manages emergency stop state across all equipment."""

    def __init__(self):
        self._emergency_stop_active = False
        self._stop_time: Optional[datetime] = None
        self._stopped_equipment: List[str] = []

    def activate_emergency_stop(self) -> Dict[str, any]:
        """
        Activate emergency stop.

        Returns:
            Status information
        """
        if self._emergency_stop_active:
            return {
                "already_active": True,
                "stop_time": self._stop_time,
                "equipment_count": len(self._stopped_equipment)
            }

        self._emergency_stop_active = True
        self._stop_time = datetime.now()

        logger.critical("🛑 EMERGENCY STOP ACTIVATED 🛑")

        return {
            "activated": True,
            "stop_time": self._stop_time,
            "message": "Emergency stop activated - all outputs will be disabled"
        }

    def deactivate_emergency_stop(self) -> Dict[str, any]:
        """
        Deactivate emergency stop.

        Returns:
            Status information
        """
        if not self._emergency_stop_active:
            return {"already_inactive": True}

        duration = (datetime.now() - self._stop_time).total_seconds() if self._stop_time else 0

        self._emergency_stop_active = False
        stopped_count = len(self._stopped_equipment)
        self._stopped_equipment.clear()

        logger.info(f"Emergency stop deactivated after {duration:.1f}s - {stopped_count} equipment affected")

        return {
            "deactivated": True,
            "duration_seconds": duration,
            "equipment_count": stopped_count
        }

    def is_active(self) -> bool:
        """Check if emergency stop is active."""
        return self._emergency_stop_active

    def register_stopped_equipment(self, equipment_id: str):
        """Register equipment that was stopped."""
        if equipment_id not in self._stopped_equipment:
            self._stopped_equipment.append(equipment_id)

    def get_status(self) -> Dict[str, any]:
        """Get emergency stop status."""
        return {
            "active": self._emergency_stop_active,
            "stop_time": self._stop_time,
            "stopped_equipment": self._stopped_equipment.copy()
        }


# Global emergency stop manager
emergency_stop_manager = EmergencyStopManager()


# Default safety limits for different equipment types
DEFAULT_SAFETY_LIMITS = {
    "oscilloscope": SafetyLimits(
        # Oscilloscopes typically don't have output limits
        require_interlock=False
    ),
    "power_supply": SafetyLimits(
        max_voltage=120.0,  # Conservative default
        max_current=10.0,
        max_power=300.0,
        voltage_slew_rate=20.0,  # 20V/s
        current_slew_rate=5.0,   # 5A/s
        require_interlock=False
    ),
    "electronic_load": SafetyLimits(
        max_voltage=150.0,
        max_current=40.0,
        max_power=200.0,
        voltage_slew_rate=50.0,
        current_slew_rate=10.0,
        require_interlock=False
    ),
}


def get_default_limits(equipment_type: str) -> SafetyLimits:
    """Get default safety limits for equipment type."""
    return DEFAULT_SAFETY_LIMITS.get(
        equipment_type.lower(),
        SafetyLimits()  # Empty limits if unknown type
    )
