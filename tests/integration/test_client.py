"""Simple test client for LabLink server."""

import pytest
import requests
import json

SERVER_URL = "http://localhost:8000"


def _require_lablink_server():
    """Skip unless a real LabLink server answers on SERVER_URL.

    A bare ConnectionError check is not enough: an unrelated service may hold
    the port and return HTML, which then fails as a JSON decode error rather
    than skipping.
    """
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=5)
        payload = response.json()
    except (requests.exceptions.RequestException, ValueError):
        pytest.skip("LabLink server not running on localhost:8000")

    if response.status_code != 200 or "status" not in payload:
        pytest.skip("localhost:8000 is not a LabLink server")


@pytest.mark.integration
def test_server():
    """Test basic server functionality."""
    _require_lablink_server()
    print("Testing LabLink Server...\n")

    try:
        # Test root endpoint. `/` serves the dashboard HTML; the JSON
        # description of the server is at `/api`.
        print("1. Testing root endpoint...")
        response = requests.get(f"{SERVER_URL}/api", timeout=5)
        print(f"   Response: {response.json()}\n")

        # Test health endpoint
        print("2. Testing health endpoint...")
        response = requests.get(f"{SERVER_URL}/health", timeout=5)
        print(f"   Response: {response.json()}\n")

        # Test device discovery
        print("3. Testing device discovery...")
        # Discovery scans VISA/serial and is slow -- 25s against a bench with
        # real ports attached. Five seconds was never going to be enough.
        response = requests.post(f"{SERVER_URL}/api/equipment/discover", timeout=45)
        if response.status_code == 200:
            devices = response.json()
            print(f"   Found {len(devices.get('devices', []))} devices:")
            for device in devices.get('devices', []):
                print(f"     - {device.get('resource_name')}")
        else:
            print(f"   Error: {response.status_code}")
        print()

        # Test list devices
        print("4. Testing list connected devices...")
        response = requests.get(f"{SERVER_URL}/api/equipment/list", timeout=5)
        if response.status_code == 200:
            devices = response.json()
            print(f"   Connected devices: {len(devices)}")
            for device in devices:
                print(f"     - {device.get('model')} ({device.get('id')})")
        else:
            print(f"   Error: {response.status_code}")
        print()

        print("Basic server tests complete!")

    except requests.exceptions.ConnectionError:
        pytest.skip("Server not running")


@pytest.mark.integration
def test_connect_device():
    """Test connecting to a device (requires actual hardware)."""
    _require_lablink_server()
    print("\nTesting device connection...\n")

    try:
        # This is just an example - you'll need to replace with actual device info
        connect_request = {
            "resource_string": "USB0::0x1AB1::0x04CE::DS2A123456789::INSTR",  # Example
            "equipment_type": "oscilloscope",
            "model": "MSO2072A"
        }

        print(f"Attempting to connect to: {connect_request['model']}")
        print("(This will fail without actual hardware connected)")

        response = requests.post(
            f"{SERVER_URL}/api/equipment/connect",
            json=connect_request,
            timeout=5
        )

        if response.status_code == 200:
            result = response.json()
            print(f"   Success! Equipment ID: {result.get('equipment_id')}")
            return result.get('equipment_id')
        else:
            print(f"   Failed: {response.text}")
            return None

    except requests.exceptions.ConnectionError:
        pytest.skip("Server not running")


if __name__ == "__main__":
    try:
        test_server()

        # Uncomment to test device connection (requires hardware)
        # test_connect_device()

    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to server.")
        print("Make sure the server is running with: python server/main.py")
    except Exception as e:
        print(f"Error: {e}")
