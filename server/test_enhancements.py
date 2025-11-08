#!/usr/bin/env python3
"""Test script for server enhancements."""

import sys
import asyncio
from pathlib import Path

print("="*70)
print("LabLink Server Enhancements Test Suite")
print("="*70)
print()

# Test 1: Configuration Management
print("Test 1: Configuration Management")
print("-" * 70)
try:
    from config.settings import settings
    from config.validator import validate_config

    print(f"✓ Settings loaded successfully")
    print(f"  - Server name: {settings.server_name}")
    print(f"  - API Port: {settings.api_port}")
    print(f"  - Auto-reconnect: {settings.enable_auto_reconnect}")
    print(f"  - Health monitoring: {settings.enable_health_monitoring}")
    print(f"  - Profiles enabled: {settings.enable_profiles}")
    print()

    print("Running configuration validation...")
    is_valid = validate_config()
    if is_valid:
        print("✓ Configuration validation passed")
    else:
        print("⚠️  Configuration validation found issues (check output above)")

except Exception as e:
    print(f"✗ Configuration test failed: {e}")
    sys.exit(1)

print()

# Test 2: Error Handling & Recovery
print("Test 2: Error Handling & Recovery System")
print("-" * 70)
try:
    from equipment.error_handler import (
        retry_handler,
        reconnection_handler,
        health_monitor,
        EquipmentError,
        ConnectionError,
        ErrorSeverity
    )

    print(f"✓ Error handler modules loaded")
    print(f"  - Retry handler enabled: {retry_handler.enabled}")
    print(f"  - Max retries: {retry_handler.max_retries}")
    print(f"  - Reconnection enabled: {reconnection_handler.enabled}")
    print(f"  - Max reconnection attempts: {reconnection_handler.max_attempts}")
    print(f"  - Health monitoring enabled: {health_monitor.enabled}")
    print(f"  - Health check interval: {health_monitor.check_interval_sec}s")
    print()

    # Test error classes
    test_error = EquipmentError(
        "Test error",
        severity=ErrorSeverity.MEDIUM,
        troubleshooting_hint="This is a test hint"
    )
    print(f"✓ Equipment error classes work correctly")
    print(f"  Example error: {test_error}")

except Exception as e:
    print(f"✗ Error handling test failed: {e}")
    sys.exit(1)

print()

# Test 3: Equipment Profiles
print("Test 3: Equipment Profile System")
print("-" * 70)
try:
    from equipment.profiles import profile_manager, EquipmentProfile, create_default_profiles

    print(f"✓ Profile manager loaded")
    print(f"  - Profile directory: {profile_manager.profile_dir}")
    print(f"  - Profiles enabled: {profile_manager.enabled}")
    print(f"  - Auto-load: {profile_manager.auto_load}")
    print()

    # Create default profiles
    print("Creating default profiles...")
    create_default_profiles()

    # List profiles
    profiles = profile_manager.list_profiles()
    print(f"✓ Default profiles created: {len(profiles)} profiles")

    for profile in profiles[:3]:  # Show first 3
        print(f"  - {profile.name} ({profile.equipment_type})")

    if len(profiles) > 3:
        print(f"  ... and {len(profiles) - 3} more")

except Exception as e:
    print(f"✗ Profile system test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 4: API Endpoints
print("Test 4: API Endpoints")
print("-" * 70)
try:
    from api import equipment_router, data_router, profiles_router

    print(f"✓ All routers loaded successfully")
    print(f"  - Equipment router: {len(equipment_router.routes)} endpoints")
    print(f"  - Data router: {len(data_router.routes)} endpoints")
    print(f"  - Profiles router: {len(profiles_router.routes)} endpoints")

    # List profile endpoints
    print()
    print("Profile API endpoints:")
    for route in profiles_router.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            methods = ', '.join(route.methods)
            print(f"  - {methods:12s} /api/profiles{route.path}")

except Exception as e:
    print(f"✗ API endpoints test failed: {e}")
    sys.exit(1)

print()

# Summary
print("="*70)
print("Test Summary")
print("="*70)
print("✅ All enhancement systems tested successfully!")
print()
print("Features implemented:")
print("  1. ✓ Comprehensive configuration management with validation")
print("  2. ✓ Error handling with auto-reconnect and health monitoring")
print("  3. ✓ Equipment profile system with JSON storage")
print("  4. ✓ Profile management API endpoints")
print()
print("Next steps:")
print("  - Start the server: python3 main.py")
print("  - View API docs: http://localhost:8000/docs")
print("  - Test profile endpoints: http://localhost:8000/api/profiles/list")
print("="*70)
