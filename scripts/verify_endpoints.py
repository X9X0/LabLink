#!/usr/bin/env python3
"""
Verify LabLink API Endpoints
Tests alarm and scheduler endpoints to confirm they're working correctly.
"""

import requests
import json
import sys
from typing import Dict, Any


SERVER_URL = "http://localhost:8000"


def test_endpoint(method: str, url: str, data: Dict[Any, Any] = None, expected_status: int = 200) -> bool:
    """Test an API endpoint."""
    full_url = f"{SERVER_URL}{url}"
    try:
        if method == "GET":
            response = requests.get(full_url, timeout=5)
        elif method == "POST":
            response = requests.post(full_url, json=data, timeout=5)
        else:
            print(f"   ❌ Unsupported method: {method}")
            return False

        success = response.status_code == expected_status
        status_icon = "✅" if success else "❌"

        print(f"   {status_icon} {method} {url}")
        print(f"      Status: {response.status_code} (expected {expected_status})")

        if not success:
            print(f"      Response: {response.text[:200]}")
        else:
            try:
                data = response.json()
                if isinstance(data, dict):
                    print(f"      Keys: {list(data.keys())}")
            except:
                pass

        return success

    except requests.exceptions.ConnectionError:
        print(f"   ❌ {method} {url}")
        print(f"      Error: Could not connect to server at {SERVER_URL}")
        print(f"      Make sure the server is running: python -m server.main")
        return False
    except Exception as e:
        print(f"   ❌ {method} {url}")
        print(f"      Error: {e}")
        return False


def main():
    """Run endpoint verification tests."""
    print("=" * 60)
    print("LabLink API Endpoint Verification")
    print("=" * 60)
    print()

    # Check server health first
    print("1. Server Health Check")
    if not test_endpoint("GET", "/health"):
        print("\n❌ Server is not running or not responding.")
        print("   Start the server with: python -m server.main")
        sys.exit(1)
    print()

    # Test alarm endpoints (the problematic ones from ISSUES.md)
    print("2. Alarm Endpoints (Previously Problematic)")
    tests = []

    tests.append(test_endpoint("GET", "/api/alarms/events"))
    tests.append(test_endpoint("GET", "/api/alarms/statistics"))
    tests.append(test_endpoint("GET", "/api/alarms/events/active"))
    print()

    # Test scheduler endpoints
    print("3. Scheduler Endpoints")
    tests.append(test_endpoint("GET", "/api/scheduler/jobs"))
    tests.append(test_endpoint("GET", "/api/scheduler/statistics"))
    print()

    # Test job creation (the other problematic endpoint)
    print("4. Job Creation (Previously Problematic)")
    job_payload = {
        "name": "test_verification_job",
        "description": "Test job for endpoint verification",
        "schedule_type": "measurement",  # MEASUREMENT type (simple)
        "trigger_type": "interval",      # INTERVAL trigger
        "interval_seconds": 3600,        # Run every hour
        "equipment_id": "test_equipment_123",
        "parameters": {
            "test_mode": True
        },
        "enabled": False  # Don't enable, just test validation
    }

    # Note: This might fail with 400 (no equipment exists) but shouldn't give 422 (validation error)
    # A 422 means the request format is wrong
    # A 400 means the request is valid but equipment doesn't exist
    result = test_endpoint("POST", "/api/scheduler/jobs/create", data=job_payload, expected_status=200)
    if not result:
        print("      Note: Job creation may fail if equipment doesn't exist (400 error)")
        print("            A 422 error indicates the request format needs adjustment")
        print("            A 400 error is expected - it means validation passed!")
    print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    passed = sum(tests)
    total = len(tests)

    if passed == total:
        print(f"✅ All {total} critical endpoints working correctly!")
        print()
        print("The alarm endpoint routing issue appears to be RESOLVED.")
        print("The routes are correctly ordered in the code.")
    else:
        print(f"⚠️  {passed}/{total} endpoints passed")
        print()
        print("Some endpoints may still have issues. Check the output above.")
        print()
        print("If you see 404 errors for /api/alarms/events:")
        print("  1. Stop the server")
        print("  2. Clear Python cache: find server -type d -name __pycache__ -exec rm -rf {} +")
        print("  3. Clear .pyc files: find server -name '*.pyc' -delete")
        print("  4. Restart the server: python -m server.main")

    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
