"""Simple test client for LabLink server."""

import requests
import json

SERVER_URL = "http://localhost:8000"


def test_server():
    """Test basic server functionality."""
    print("Testing LabLink Server...\n")

    # Test root endpoint
    print("1. Testing root endpoint...")
    response = requests.get(f"{SERVER_URL}/")
    print(f"   Response: {response.json()}\n")

    # Test health endpoint
    print("2. Testing health endpoint...")
    response = requests.get(f"{SERVER_URL}/health")
    print(f"   Response: {response.json()}\n")

    # Test device discovery
    print("3. Testing device discovery...")
    response = requests.get(f"{SERVER_URL}/api/equipment/discover")
    if response.status_code == 200:
        devices = response.json()
        print(f"   Found {len(devices.get('resources', []))} devices:")
        for device in devices.get('resources', []):
            print(f"     - {device}")
    else:
        print(f"   Error: {response.status_code}")
    print()

    # Test list devices
    print("4. Testing list connected devices...")
    response = requests.get(f"{SERVER_URL}/api/equipment/list")
    if response.status_code == 200:
        devices = response.json()
        print(f"   Connected devices: {len(devices)}")
        for device in devices:
            print(f"     - {device.get('model')} ({device.get('id')})")
    else:
        print(f"   Error: {response.status_code}")
    print()

    print("Basic server tests complete!")


def test_connect_device():
    """Test connecting to a device (requires actual hardware)."""
    print("\nTesting device connection...\n")

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
        json=connect_request
    )

    if response.status_code == 200:
        result = response.json()
        print(f"   Success! Equipment ID: {result.get('equipment_id')}")
        return result.get('equipment_id')
    else:
        print(f"   Failed: {response.text}")
        return None


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
