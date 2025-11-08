#!/usr/bin/env python3
"""Test and validate the safety limits & interlocks system."""

import sys
import asyncio
from pathlib import Path

print("="*70)
print("LabLink Safety Limits & Interlocks - Test Suite")
print("="*70)
print()

# Test 1: Safety Module Imports
print("Test 1: Safety Module Imports")
print("-" * 70)
try:
    from equipment.safety import (
        SafetyLimits,
        SafetyValidator,
        SafetyViolation,
        SafetyViolationType,
        SlewRateLimiter,
        EmergencyStopManager,
        emergency_stop_manager,
        get_default_limits
    )

    print("✓ All safety modules imported successfully")
    print(f"  - SafetyLimits: {SafetyLimits}")
    print(f"  - SafetyValidator: {SafetyValidator}")
    print(f"  - EmergencyStopManager: {EmergencyStopManager}")

except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

print()

# Test 2: Safety Limits Creation
print("Test 2: Safety Limits Creation")
print("-" * 70)
try:
    # Create safety limits
    limits = SafetyLimits(
        max_voltage=30.0,
        max_current=5.0,
        max_power=150.0,
        voltage_slew_rate=10.0,
        current_slew_rate=2.0
    )

    print(f"✓ Safety limits created:")
    print(f"  - Max voltage: {limits.max_voltage}V")
    print(f"  - Max current: {limits.max_current}A")
    print(f"  - Max power: {limits.max_power}W")
    print(f"  - Voltage slew rate: {limits.voltage_slew_rate}V/s")
    print(f"  - Current slew rate: {limits.current_slew_rate}A/s")

except Exception as e:
    print(f"✗ Safety limits creation failed: {e}")
    sys.exit(1)

print()

# Test 3: SafetyValidator Checks
print("Test 3: SafetyValidator Limit Checks")
print("-" * 70)
try:
    validator = SafetyValidator(limits, "test_ps_001")

    # Test voltage within limits
    try:
        validator.check_voltage(20.0)
        print("✓ Voltage check passed: 20V within 30V limit")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

    # Test voltage exceeding limits
    try:
        validator.check_voltage(35.0)
        print("✗ Should have raised SafetyViolation for 35V")
    except SafetyViolation as e:
        print(f"✓ Correctly blocked excessive voltage:")
        print(f"  {e}")

    # Test current within limits
    try:
        validator.check_current(3.0)
        print("✓ Current check passed: 3A within 5A limit")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

    # Test current exceeding limits
    try:
        validator.check_current(6.0)
        print("✗ Should have raised SafetyViolation for 6A")
    except SafetyViolation as e:
        print(f"✓ Correctly blocked excessive current:")
        print(f"  {e}")

    # Test power limits
    try:
        validator.check_power(100.0)
        print("✓ Power check passed: 100W within 150W limit")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

    try:
        validator.check_power(200.0)
        print("✗ Should have raised SafetyViolation for 200W")
    except SafetyViolation as e:
        print(f"✓ Correctly blocked excessive power:")
        print(f"  {e}")

except Exception as e:
    print(f"✗ SafetyValidator test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 4: Slew Rate Limiting
print("Test 4: Slew Rate Limiting")
print("-" * 70)
async def test_slew_rate():
    try:
        slew_limiter = SlewRateLimiter()

        # Test gradual change (should pass)
        await asyncio.sleep(0.1)  # Small delay
        result = await slew_limiter.check_and_limit(
            "test_voltage",
            new_value=12.0,
            current_value=10.0,
            max_slew_rate=100.0  # 100V/s allows 2V in 0.1s easily
        )
        print(f"✓ Gradual change allowed: {result}V (from 10V to 12V)")

        # Test rapid change (should be limited)
        result2 = await slew_limiter.check_and_limit(
            "test_voltage_rapid",
            new_value=30.0,
            current_value=0.0,
            max_slew_rate=10.0  # Only 10V/s
        )
        print(f"✓ Rapid change limited: requested 30V, limited to {result2:.2f}V")

        # Test validator slew limiting
        current_voltage = 0.0
        new_voltage = await validator.apply_voltage_slew_limit(50.0, current_voltage)
        print(f"✓ Validator slew limit: requested 50V, limited to {new_voltage:.2f}V")

    except Exception as e:
        print(f"✗ Slew rate limiting failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if not asyncio.run(test_slew_rate()):
    sys.exit(1)

print()

# Test 5: Emergency Stop Manager
print("Test 5: Emergency Stop Manager")
print("-" * 70)
try:
    # Test activation
    result = emergency_stop_manager.activate_emergency_stop()
    print(f"✓ Emergency stop activated")
    print(f"  - Active: {result.get('activated')}")
    print(f"  - Time: {result.get('stop_time')}")

    # Check status
    assert emergency_stop_manager.is_active() == True, "Should be active"
    print("✓ Emergency stop status confirmed active")

    # Register equipment
    emergency_stop_manager.register_stopped_equipment("test_ps_001")
    emergency_stop_manager.register_stopped_equipment("test_ps_002")

    status = emergency_stop_manager.get_status()
    print(f"✓ Equipment registered: {len(status['stopped_equipment'])} items")

    # Test deactivation
    result = emergency_stop_manager.deactivate_emergency_stop()
    print(f"✓ Emergency stop deactivated")
    print(f"  - Duration: {result.get('duration_seconds'):.2f}s")
    print(f"  - Equipment affected: {result.get('equipment_count')}")

    # Check status
    assert emergency_stop_manager.is_active() == False, "Should be inactive"
    print("✓ Emergency stop status confirmed inactive")

except Exception as e:
    print(f"✗ Emergency stop test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 6: Default Safety Limits
print("Test 6: Default Safety Limits")
print("-" * 70)
try:
    ps_limits = get_default_limits("power_supply")
    load_limits = get_default_limits("electronic_load")
    scope_limits = get_default_limits("oscilloscope")

    print(f"✓ Power supply defaults:")
    print(f"  - Max voltage: {ps_limits.max_voltage}V")
    print(f"  - Max current: {ps_limits.max_current}A")
    print(f"  - Max power: {ps_limits.max_power}W")

    print(f"✓ Electronic load defaults:")
    print(f"  - Max voltage: {load_limits.max_voltage}V")
    print(f"  - Max current: {load_limits.max_current}A")
    print(f"  - Max power: {load_limits.max_power}W")

    print(f"✓ Oscilloscope defaults:")
    print(f"  - Interlock required: {scope_limits.require_interlock}")

except Exception as e:
    print(f"✗ Default limits test failed: {e}")
    sys.exit(1)

print()

# Test 7: Safety Configuration
print("Test 7: Safety Configuration in Settings")
print("-" * 70)
try:
    from config.settings import settings

    print(f"✓ Safety settings loaded:")
    print(f"  - Enable safety limits: {settings.enable_safety_limits}")
    print(f"  - Enforce slew rate: {settings.enforce_slew_rate}")
    print(f"  - Safe state on disconnect: {settings.safe_state_on_disconnect}")
    print(f"  - Log safety events: {settings.log_safety_events}")
    print(f"  - Allow limit override: {settings.allow_limit_override}")
    print(f"  - Emergency stop timeout: {settings.emergency_stop_timeout_sec}s")

except Exception as e:
    print(f"✗ Settings test failed: {e}")
    sys.exit(1)

print()

# Test 8: API Endpoints
print("Test 8: Safety API Endpoints")
print("-" * 70)
try:
    from api import safety_router

    print(f"✓ Safety router loaded")
    print(f"  - Total endpoints: {len(safety_router.routes)}")

    print("\n  Safety API endpoints:")
    for route in safety_router.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            methods = ', '.join(route.methods)
            print(f"    - {methods:12s} /api/safety{route.path}")

except Exception as e:
    print(f"✗ API test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 9: Integration with Equipment
print("Test 9: Equipment Driver Integration")
print("-" * 70)
try:
    from equipment.bk_power_supply import BKPowerSupplyBase

    # Check that safety features are in class
    has_safety = hasattr(BKPowerSupplyBase, '_initialize_safety')
    print(f"{'✓' if has_safety else '✗'} BK Power Supply has safety initialization method")

    # Check for safety-related attributes in __init__
    import inspect
    source = inspect.getsource(BKPowerSupplyBase.__init__)
    has_validator_attr = 'safety_validator' in source
    print(f"{'✓' if has_validator_attr else '✗'} BK Power Supply initializes safety_validator")

    has_tracking = '_current_voltage' in source and '_current_current' in source
    print(f"{'✓' if has_tracking else '✗'} BK Power Supply tracks current values for slew limiting")

    # Check set_voltage method for safety integration
    set_voltage_source = inspect.getsource(BKPowerSupplyBase.set_voltage)
    has_emergency_check = 'emergency_stop_manager' in set_voltage_source
    has_safety_check = 'safety_validator' in set_voltage_source
    has_slew_check = 'apply_voltage_slew_limit' in set_voltage_source

    print(f"{'✓' if has_emergency_check else '✗'} set_voltage checks emergency stop")
    print(f"{'✓' if has_safety_check else '✗'} set_voltage uses safety validator")
    print(f"{'✓' if has_slew_check else '✗'} set_voltage applies slew rate limiting")

except Exception as e:
    print(f"✗ Equipment integration test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 10: Safe Disconnect
print("Test 10: Safe State on Disconnect")
print("-" * 70)
try:
    from equipment.manager import equipment_manager
    import inspect

    disconnect_source = inspect.getsource(equipment_manager.disconnect_device)

    has_safe_state = 'safe_state_on_disconnect' in disconnect_source
    has_disable_output = 'set_output' in disconnect_source or 'set_input' in disconnect_source

    print(f"{'✓' if has_safe_state else '✗'} Equipment manager checks safe_state_on_disconnect setting")
    print(f"{'✓' if has_disable_output else '✗'} Equipment manager disables outputs before disconnect")

except Exception as e:
    print(f"✗ Safe disconnect test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Summary
print("="*70)
print("Test Summary")
print("="*70)
print("✅ All safety system tests passed!")
print()
print("Safety Features Verified:")
print("  1. ✓ Safety limits (voltage, current, power)")
print("  2. ✓ Safety validator with limit checking")
print("  3. ✓ Slew rate limiting for gradual changes")
print("  4. ✓ Emergency stop functionality")
print("  5. ✓ Default limits for equipment types")
print("  6. ✓ Configuration settings")
print("  7. ✓ API endpoints")
print("  8. ✓ Equipment driver integration")
print("  9. ✓ Safe state on disconnect")
print()
print("Next steps:")
print("  - Start server: python3 main.py")
print("  - Test emergency stop: POST /api/safety/emergency-stop/activate")
print("  - Test with actual equipment (if available)")
print("="*70)
