"""
Comprehensive tests for the equipment safety module.

Tests cover:
- SafetyLimits model
- SafetyViolation exceptions
- SlewRateLimiter functionality
- SafetyValidator checks
- EmergencyStopManager
- Default safety limits
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from server.equipment.safety import (
    SafetyLimits,
    SafetyViolation,
    SafetyViolationType,
    SafetyEvent,
    SlewRateLimiter,
    SafetyValidator,
    EmergencyStopManager,
    get_default_limits,
    DEFAULT_SAFETY_LIMITS,
)


class TestSafetyLimits:
    """Test SafetyLimits Pydantic model."""

    def test_default_limits(self):
        """Test creating SafetyLimits with defaults."""
        limits = SafetyLimits()

        assert limits.max_voltage is None
        assert limits.min_voltage == 0.0
        assert limits.max_current is None
        assert limits.min_current == 0.0
        assert limits.max_power is None
        assert limits.voltage_slew_rate is None
        assert limits.current_slew_rate is None
        assert limits.temperature_limit is None
        assert limits.require_interlock is False

    def test_custom_limits(self):
        """Test creating SafetyLimits with custom values."""
        limits = SafetyLimits(
            max_voltage=30.0,
            min_voltage=0.0,
            max_current=5.0,
            max_power=150.0,
            voltage_slew_rate=10.0,
            current_slew_rate=2.0,
            temperature_limit=85.0,
            require_interlock=True,
        )

        assert limits.max_voltage == 30.0
        assert limits.min_voltage == 0.0
        assert limits.max_current == 5.0
        assert limits.max_power == 150.0
        assert limits.voltage_slew_rate == 10.0
        assert limits.current_slew_rate == 2.0
        assert limits.temperature_limit == 85.0
        assert limits.require_interlock is True

    def test_limits_json_serialization(self):
        """Test SafetyLimits can be serialized to JSON."""
        limits = SafetyLimits(max_voltage=30.0, max_current=5.0)
        json_data = limits.model_dump()

        assert json_data["max_voltage"] == 30.0
        assert json_data["max_current"] == 5.0


class TestSafetyViolation:
    """Test SafetyViolation exception."""

    def test_basic_violation(self):
        """Test creating basic safety violation."""
        violation = SafetyViolation(
            SafetyViolationType.VOLTAGE_LIMIT,
            "Voltage too high"
        )

        assert violation.violation_type == SafetyViolationType.VOLTAGE_LIMIT
        assert violation.message == "Voltage too high"
        assert violation.attempted_value is None
        assert violation.limit_value is None
        assert violation.equipment_id is None
        assert isinstance(violation.timestamp, datetime)

    def test_detailed_violation(self):
        """Test creating detailed safety violation."""
        violation = SafetyViolation(
            SafetyViolationType.CURRENT_LIMIT,
            "Current exceeded",
            attempted_value=6.0,
            limit_value=5.0,
            equipment_id="PSU_001"
        )

        assert violation.violation_type == SafetyViolationType.CURRENT_LIMIT
        assert violation.attempted_value == 6.0
        assert violation.limit_value == 5.0
        assert violation.equipment_id == "PSU_001"

    def test_violation_message_formatting(self):
        """Test violation message is properly formatted."""
        violation = SafetyViolation(
            SafetyViolationType.POWER_LIMIT,
            "Power limit exceeded",
            attempted_value=200.0,
            limit_value=150.0,
            equipment_id="LOAD_001"
        )

        message = str(violation)
        assert "SAFETY VIOLATION" in message
        assert "POWER_LIMIT" in message.upper()
        assert "Power limit exceeded" in message
        assert "Attempted: 200.0" in message
        assert "Limit: 150.0" in message
        assert "Equipment: LOAD_001" in message
        assert "Action blocked for safety" in message

    def test_all_violation_types(self):
        """Test all violation type enums exist."""
        assert SafetyViolationType.VOLTAGE_LIMIT
        assert SafetyViolationType.CURRENT_LIMIT
        assert SafetyViolationType.POWER_LIMIT
        assert SafetyViolationType.SLEW_RATE
        assert SafetyViolationType.INTERLOCK
        assert SafetyViolationType.EMERGENCY_STOP


class TestSafetyEvent:
    """Test SafetyEvent model."""

    def test_safety_event_creation(self):
        """Test creating a safety event."""
        event = SafetyEvent(
            equipment_id="PSU_001",
            violation_type=SafetyViolationType.VOLTAGE_LIMIT,
            message="Voltage exceeded limit",
            attempted_value=35.0,
            limit_value=30.0,
            action_taken="blocked"
        )

        assert event.equipment_id == "PSU_001"
        assert event.violation_type == SafetyViolationType.VOLTAGE_LIMIT
        assert event.message == "Voltage exceeded limit"
        assert event.attempted_value == 35.0
        assert event.limit_value == 30.0
        assert event.action_taken == "blocked"
        assert isinstance(event.timestamp, datetime)


class TestSlewRateLimiter:
    """Test SlewRateLimiter class."""

    @pytest.mark.asyncio
    async def test_first_change_allowed(self):
        """Test first change is always allowed."""
        limiter = SlewRateLimiter()

        result = await limiter.check_and_limit(
            key="test_voltage",
            new_value=10.0,
            current_value=0.0,
            max_slew_rate=5.0
        )

        assert result == 10.0

    @pytest.mark.asyncio
    async def test_change_within_slew_rate(self):
        """Test change within slew rate is allowed."""
        limiter = SlewRateLimiter()

        # First change
        await limiter.check_and_limit("test_v", 5.0, 0.0, 10.0)

        # Wait a bit
        await asyncio.sleep(0.1)

        # Small change (within limits for 0.1s at 10V/s = 1V max change)
        result = await limiter.check_and_limit("test_v", 5.5, 5.0, 10.0)

        # Should allow the change since 0.5V over 0.1s = 5V/s which is < 10V/s
        assert result == 5.5

    @pytest.mark.asyncio
    async def test_change_exceeds_slew_rate(self):
        """Test change exceeding slew rate is limited."""
        limiter = SlewRateLimiter()

        # First change
        await limiter.check_and_limit("test_voltage", 0.0, 0.0, 5.0)

        # Wait 0.1s
        await asyncio.sleep(0.1)

        # Try to change by 10V (exceeds 5V/s * 0.1s = 0.5V max)
        result = await limiter.check_and_limit("test_voltage", 10.0, 0.0, 5.0)

        # Should be limited to approximately current + (max_slew_rate * time_delta)
        # With 0.1s and 5V/s, max change is 0.5V, so result should be ~0.5V
        assert result < 10.0  # Definitely limited
        assert result <= 1.0  # Should be around 0.5V with some tolerance

    @pytest.mark.asyncio
    async def test_negative_slew_rate(self):
        """Test slew rate limiting works for decreasing values."""
        limiter = SlewRateLimiter()

        # Set initial high value
        await limiter.check_and_limit("test_v", 10.0, 10.0, 5.0)

        # Wait
        await asyncio.sleep(0.1)

        # Try to drop to 0 (should be limited)
        result = await limiter.check_and_limit("test_v", 0.0, 10.0, 5.0)

        # Should be limited (can't drop by 10V in 0.1s at 5V/s)
        assert result > 0.0
        assert result < 10.0

    @pytest.mark.asyncio
    async def test_multiple_parameters(self):
        """Test limiter can track multiple parameters independently."""
        limiter = SlewRateLimiter()

        # Set two different parameters
        result1 = await limiter.check_and_limit("voltage", 5.0, 0.0, 10.0)
        result2 = await limiter.check_and_limit("current", 2.0, 0.0, 5.0)

        assert result1 == 5.0
        assert result2 == 2.0


class TestSafetyValidator:
    """Test SafetyValidator class."""

    def test_validator_creation(self):
        """Test creating SafetyValidator."""
        limits = SafetyLimits(max_voltage=30.0, max_current=5.0)
        validator = SafetyValidator(limits, "PSU_001")

        assert validator.limits == limits
        assert validator.equipment_id == "PSU_001"
        assert isinstance(validator.slew_limiter, SlewRateLimiter)

    def test_voltage_within_limits(self):
        """Test voltage check passes when within limits."""
        limits = SafetyLimits(max_voltage=30.0, min_voltage=0.0)
        validator = SafetyValidator(limits, "PSU_001")

        # Should not raise
        validator.check_voltage(15.0)
        validator.check_voltage(0.0)
        validator.check_voltage(30.0)

    def test_voltage_exceeds_max_limit(self):
        """Test voltage check raises when exceeding max."""
        limits = SafetyLimits(max_voltage=30.0)
        validator = SafetyValidator(limits, "PSU_001")

        with pytest.raises(SafetyViolation) as exc_info:
            validator.check_voltage(35.0)

        assert exc_info.value.violation_type == SafetyViolationType.VOLTAGE_LIMIT
        assert exc_info.value.attempted_value == 35.0
        assert exc_info.value.limit_value == 30.0
        assert exc_info.value.equipment_id == "PSU_001"

    def test_voltage_below_min_limit(self):
        """Test voltage check raises when below min."""
        limits = SafetyLimits(min_voltage=5.0)
        validator = SafetyValidator(limits, "PSU_001")

        with pytest.raises(SafetyViolation) as exc_info:
            validator.check_voltage(2.0)

        assert exc_info.value.violation_type == SafetyViolationType.VOLTAGE_LIMIT
        assert exc_info.value.attempted_value == 2.0
        assert exc_info.value.limit_value == 5.0

    def test_current_within_limits(self):
        """Test current check passes when within limits."""
        limits = SafetyLimits(max_current=5.0, min_current=0.0)
        validator = SafetyValidator(limits, "PSU_001")

        # Should not raise
        validator.check_current(2.5)
        validator.check_current(0.0)
        validator.check_current(5.0)

    def test_current_exceeds_max_limit(self):
        """Test current check raises when exceeding max."""
        limits = SafetyLimits(max_current=5.0)
        validator = SafetyValidator(limits, "PSU_001")

        with pytest.raises(SafetyViolation) as exc_info:
            validator.check_current(6.0)

        assert exc_info.value.violation_type == SafetyViolationType.CURRENT_LIMIT
        assert exc_info.value.attempted_value == 6.0
        assert exc_info.value.limit_value == 5.0

    def test_current_below_min_limit(self):
        """Test current check raises when below min."""
        limits = SafetyLimits(min_current=1.0)
        validator = SafetyValidator(limits, "PSU_001")

        with pytest.raises(SafetyViolation) as exc_info:
            validator.check_current(0.5)

        assert exc_info.value.violation_type == SafetyViolationType.CURRENT_LIMIT

    def test_power_within_limits(self):
        """Test power check passes when within limits."""
        limits = SafetyLimits(max_power=150.0)
        validator = SafetyValidator(limits, "PSU_001")

        # Should not raise
        validator.check_power(100.0)
        validator.check_power(150.0)

    def test_power_exceeds_limit(self):
        """Test power check raises when exceeding limit."""
        limits = SafetyLimits(max_power=150.0)
        validator = SafetyValidator(limits, "PSU_001")

        with pytest.raises(SafetyViolation) as exc_info:
            validator.check_power(200.0)

        assert exc_info.value.violation_type == SafetyViolationType.POWER_LIMIT
        assert exc_info.value.attempted_value == 200.0
        assert exc_info.value.limit_value == 150.0

    def test_interlock_not_required(self):
        """Test interlock check passes when not required."""
        limits = SafetyLimits(require_interlock=False)
        validator = SafetyValidator(limits, "PSU_001")

        # Should not raise
        validator.check_interlock()

    def test_interlock_required_but_not_set(self):
        """Test interlock check raises when required but not set."""
        limits = SafetyLimits(require_interlock=True)
        validator = SafetyValidator(limits, "PSU_001")

        with pytest.raises(SafetyViolation) as exc_info:
            validator.check_interlock()

        assert exc_info.value.violation_type == SafetyViolationType.INTERLOCK

    def test_interlock_set_and_required(self):
        """Test interlock check passes when set and required."""
        limits = SafetyLimits(require_interlock=True)
        validator = SafetyValidator(limits, "PSU_001")

        validator.set_interlock(True)

        # Should not raise
        validator.check_interlock()

    def test_interlock_state_changes(self):
        """Test interlock state can be changed."""
        limits = SafetyLimits(require_interlock=True)
        validator = SafetyValidator(limits, "PSU_001")

        # Initially should fail
        with pytest.raises(SafetyViolation):
            validator.check_interlock()

        # Set interlock
        validator.set_interlock(True)
        validator.check_interlock()  # Should pass

        # Release interlock
        validator.set_interlock(False)
        with pytest.raises(SafetyViolation):
            validator.check_interlock()

    @pytest.mark.asyncio
    async def test_voltage_slew_limit_applied(self):
        """Test voltage slew rate limiting is applied."""
        limits = SafetyLimits(voltage_slew_rate=5.0)
        validator = SafetyValidator(limits, "PSU_001")

        # First change
        result = await validator.apply_voltage_slew_limit(10.0, 0.0)
        assert result == 10.0

        # Wait a bit
        await asyncio.sleep(0.1)

        # Large change should be limited
        result = await validator.apply_voltage_slew_limit(20.0, 10.0)
        # Result should be limited (can't change by 10V at 5V/s in 0.1s)
        assert result < 20.0

    @pytest.mark.asyncio
    async def test_voltage_slew_limit_none(self):
        """Test voltage change when no slew limit is set."""
        limits = SafetyLimits()  # No slew rate
        validator = SafetyValidator(limits, "PSU_001")

        result = await validator.apply_voltage_slew_limit(100.0, 0.0)
        assert result == 100.0  # No limiting

    @pytest.mark.asyncio
    async def test_current_slew_limit_applied(self):
        """Test current slew rate limiting is applied."""
        limits = SafetyLimits(current_slew_rate=2.0)
        validator = SafetyValidator(limits, "PSU_001")

        # First change
        result = await validator.apply_current_slew_limit(5.0, 0.0)
        assert result == 5.0

        # Wait
        await asyncio.sleep(0.1)

        # Large change should be limited
        result = await validator.apply_current_slew_limit(10.0, 5.0)
        assert result < 10.0

    @pytest.mark.asyncio
    async def test_current_slew_limit_none(self):
        """Test current change when no slew limit is set."""
        limits = SafetyLimits()  # No slew rate
        validator = SafetyValidator(limits, "PSU_001")

        result = await validator.apply_current_slew_limit(50.0, 0.0)
        assert result == 50.0  # No limiting

    def test_log_safety_event(self):
        """Test logging safety events."""
        limits = SafetyLimits()
        validator = SafetyValidator(limits, "PSU_001")

        validator.log_safety_event(
            SafetyViolationType.VOLTAGE_LIMIT,
            "Test violation",
            attempted_value=35.0,
            limit_value=30.0,
            action_taken="blocked"
        )

        events = validator.get_safety_events()
        assert len(events) == 1
        assert events[0].equipment_id == "PSU_001"
        assert events[0].violation_type == SafetyViolationType.VOLTAGE_LIMIT
        assert events[0].message == "Test violation"

    def test_safety_events_limit(self):
        """Test safety events are limited to 100."""
        limits = SafetyLimits()
        validator = SafetyValidator(limits, "PSU_001")

        # Log 150 events
        for i in range(150):
            validator.log_safety_event(
                SafetyViolationType.VOLTAGE_LIMIT,
                f"Event {i}",
                action_taken="blocked"
            )

        events = validator.get_safety_events(limit=200)
        assert len(events) == 100  # Should only keep last 100

    def test_get_safety_events_with_limit(self):
        """Test getting safety events with custom limit."""
        limits = SafetyLimits()
        validator = SafetyValidator(limits, "PSU_001")

        # Log 20 events
        for i in range(20):
            validator.log_safety_event(
                SafetyViolationType.VOLTAGE_LIMIT,
                f"Event {i}",
                action_taken="blocked"
            )

        events = validator.get_safety_events(limit=5)
        assert len(events) == 5
        # Should get the last 5 events
        assert events[0].message == "Event 15"
        assert events[4].message == "Event 19"


class TestEmergencyStopManager:
    """Test EmergencyStopManager class."""

    def test_initial_state(self):
        """Test emergency stop manager initial state."""
        manager = EmergencyStopManager()

        assert manager.is_active() is False
        status = manager.get_status()
        assert status["active"] is False
        assert status["stop_time"] is None
        assert status["stopped_equipment"] == []

    def test_activate_emergency_stop(self):
        """Test activating emergency stop."""
        manager = EmergencyStopManager()

        result = manager.activate_emergency_stop()

        assert result["activated"] is True
        assert "stop_time" in result
        assert manager.is_active() is True

    def test_activate_already_active(self):
        """Test activating emergency stop when already active."""
        manager = EmergencyStopManager()

        # First activation
        result1 = manager.activate_emergency_stop()
        assert result1["activated"] is True

        # Second activation
        result2 = manager.activate_emergency_stop()
        assert result2.get("already_active") is True

    def test_deactivate_emergency_stop(self):
        """Test deactivating emergency stop."""
        manager = EmergencyStopManager()

        # Activate first
        manager.activate_emergency_stop()
        assert manager.is_active() is True

        # Deactivate
        result = manager.deactivate_emergency_stop()

        assert result["deactivated"] is True
        assert "duration_seconds" in result
        assert manager.is_active() is False

    def test_deactivate_already_inactive(self):
        """Test deactivating when already inactive."""
        manager = EmergencyStopManager()

        result = manager.deactivate_emergency_stop()

        assert result.get("already_inactive") is True

    def test_register_stopped_equipment(self):
        """Test registering stopped equipment."""
        manager = EmergencyStopManager()

        manager.activate_emergency_stop()
        manager.register_stopped_equipment("PSU_001")
        manager.register_stopped_equipment("SCOPE_001")

        status = manager.get_status()
        assert len(status["stopped_equipment"]) == 2
        assert "PSU_001" in status["stopped_equipment"]
        assert "SCOPE_001" in status["stopped_equipment"]

    def test_register_equipment_no_duplicates(self):
        """Test equipment is not registered twice."""
        manager = EmergencyStopManager()

        manager.activate_emergency_stop()
        manager.register_stopped_equipment("PSU_001")
        manager.register_stopped_equipment("PSU_001")  # Duplicate

        status = manager.get_status()
        assert len(status["stopped_equipment"]) == 1

    def test_equipment_cleared_on_deactivate(self):
        """Test stopped equipment list is cleared on deactivate."""
        manager = EmergencyStopManager()

        manager.activate_emergency_stop()
        manager.register_stopped_equipment("PSU_001")
        manager.register_stopped_equipment("SCOPE_001")

        result = manager.deactivate_emergency_stop()
        assert result["equipment_count"] == 2

        status = manager.get_status()
        assert len(status["stopped_equipment"]) == 0

    def test_full_emergency_stop_cycle(self):
        """Test complete emergency stop activation/deactivation cycle."""
        manager = EmergencyStopManager()

        # Initially inactive
        assert manager.is_active() is False

        # Activate
        activate_result = manager.activate_emergency_stop()
        assert activate_result["activated"] is True
        assert manager.is_active() is True

        # Register equipment
        manager.register_stopped_equipment("PSU_001")
        manager.register_stopped_equipment("LOAD_001")

        # Deactivate
        deactivate_result = manager.deactivate_emergency_stop()
        assert deactivate_result["deactivated"] is True
        assert deactivate_result["equipment_count"] == 2
        assert manager.is_active() is False

        # Status should be clear
        status = manager.get_status()
        assert status["active"] is False
        assert len(status["stopped_equipment"]) == 0


class TestDefaultSafetyLimits:
    """Test default safety limits."""

    def test_default_limits_exist(self):
        """Test default limits are defined for equipment types."""
        assert "oscilloscope" in DEFAULT_SAFETY_LIMITS
        assert "power_supply" in DEFAULT_SAFETY_LIMITS
        assert "electronic_load" in DEFAULT_SAFETY_LIMITS

    def test_get_default_oscilloscope_limits(self):
        """Test getting default oscilloscope limits."""
        limits = get_default_limits("oscilloscope")

        assert isinstance(limits, SafetyLimits)
        assert limits.require_interlock is False
        # Oscilloscopes don't have output limits
        assert limits.max_voltage is None

    def test_get_default_power_supply_limits(self):
        """Test getting default power supply limits."""
        limits = get_default_limits("power_supply")

        assert isinstance(limits, SafetyLimits)
        assert limits.max_voltage == 120.0
        assert limits.max_current == 10.0
        assert limits.max_power == 300.0
        assert limits.voltage_slew_rate == 20.0
        assert limits.current_slew_rate == 5.0

    def test_get_default_electronic_load_limits(self):
        """Test getting default electronic load limits."""
        limits = get_default_limits("electronic_load")

        assert isinstance(limits, SafetyLimits)
        assert limits.max_voltage == 150.0
        assert limits.max_current == 40.0
        assert limits.max_power == 200.0
        assert limits.voltage_slew_rate == 50.0
        assert limits.current_slew_rate == 10.0

    def test_get_default_unknown_type(self):
        """Test getting default limits for unknown equipment type."""
        limits = get_default_limits("unknown_equipment")

        assert isinstance(limits, SafetyLimits)
        # Should return empty limits
        assert limits.max_voltage is None
        assert limits.max_current is None

    def test_case_insensitive_equipment_type(self):
        """Test equipment type lookup is case insensitive."""
        limits1 = get_default_limits("POWER_SUPPLY")
        limits2 = get_default_limits("power_supply")
        limits3 = get_default_limits("Power_Supply")

        assert limits1.max_voltage == limits2.max_voltage == limits3.max_voltage
        assert limits1.max_current == limits2.max_current == limits3.max_current


# Mark all tests as unit tests
pytestmark = pytest.mark.unit
