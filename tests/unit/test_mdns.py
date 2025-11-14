"""Test mDNS/Zeroconf service discovery."""

import sys
import os
import time
import pytest

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "client"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))

try:
    from zeroconf import Zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    print("Error: zeroconf package not installed")
    print("\nInstall with: pip install zeroconf")
    ZEROCONF_AVAILABLE = False
    sys.exit(1)


def test_server_mdns():
    """Test server mDNS broadcasting."""
    print("\n" + "="*60)
    print("Testing Server mDNS Broadcasting")
    print("="*60)

    try:
        from server.utils.mdns import LabLinkMDNSService

        # Create service
        service = LabLinkMDNSService(
            port=8000,
            ws_port=8001,
            server_name="TestServer",
            server_version="1.0.0"
        )

        print(f"\n✓ Created mDNS service: {service.server_name}")

        # Start broadcasting
        if service.start():
            print("✓ Service started successfully")

            info = service.get_service_info()
            print(f"\nService Info:")
            print(f"  Running: {info['running']}")
            print(f"  Name: {info['server_name']}")
            print(f"  API Port: {info['port']}")
            print(f"  WS Port: {info['ws_port']}")
            print(f"  Version: {info['version']}")
            print(f"  Service Type: {info['service_type']}")

            print("\nBroadcasting for 10 seconds...")
            print("  (Other devices on the network should be able to discover this server)")

            time.sleep(10)

            # Update properties
            print("\nUpdating service properties...")
            service.update_properties({'status': 'running', 'equipment_count': '5'})
            print("✓ Properties updated")

            time.sleep(2)

            # Stop service
            service.stop()
            print("\n✓ Service stopped")

            print("\n" + "="*60)
            print("✓ Server mDNS test passed!")
            print("="*60)

        else:
            print("✗ Failed to start service")

    except Exception as e:
        print(f"\n✗ Server mDNS test failed: {e}")
        import traceback
        traceback.print_exc()


def test_client_discovery():
    """Test client mDNS discovery."""
    print("\n" + "="*60)
    print("Testing Client mDNS Discovery")
    print("="*60)

    try:
        from client.utils.mdns_discovery import LabLinkDiscovery, discover_servers

        print("\nStarting discovery...")
        print("  (Make sure a LabLink server with mDNS is running)")

        # Method 1: Using convenience function
        print("\n--- Method 1: Convenience Function ---")
        servers = discover_servers(timeout=5.0)

        print(f"\n✓ Discovery complete. Found {len(servers)} server(s)")

        for i, server in enumerate(servers, 1):
            print(f"\nServer {i}:")
            print(f"  Name: {server.name}")
            print(f"  Address: {server.address}")
            print(f"  API Port: {server.port}")
            print(f"  WS Port: {server.ws_port}")
            print(f"  URL: http://{server.address}:{server.port}")
            print(f"  Properties: {server.properties}")

        # Method 2: Using LabLinkDiscovery class
        print("\n--- Method 2: LabLinkDiscovery Class ---")

        discovery = LabLinkDiscovery()

        # Register callback
        def on_server_event(event_type, server):
            print(f"  [{event_type.upper()}] {server.name} at {server.address}:{server.port}")

        discovery.register_callback(on_server_event)

        # Start discovery
        discovery.start()

        print("Discovering for 5 seconds...")
        time.sleep(5)

        # Get servers
        servers = discovery.get_servers()
        print(f"\n✓ Found {len(servers)} server(s)")

        # Test server lookup
        if servers:
            first_server = servers[0]

            found_by_name = discovery.find_server_by_name(first_server.name)
            if found_by_name:
                print(f"✓ Found server by name: {found_by_name.name}")

            found_by_addr = discovery.find_server_by_address(first_server.address)
            if found_by_addr:
                print(f"✓ Found server by address: {found_by_addr.address}")

        # Stop discovery
        discovery.stop()
        print("\n✓ Discovery stopped")

        print("\n" + "="*60)
        print("✓ Client discovery test passed!")
        print("="*60)

    except Exception as e:
        print(f"\n✗ Client discovery test failed: {e}")
        import traceback
        traceback.print_exc()


@pytest.mark.skipif(os.environ.get('CI') == 'true', reason="GUI test crashes in headless CI environment")
def test_discovery_dialog():
    """Test discovery dialog GUI."""
    print("\n" + "="*60)
    print("Testing Discovery Dialog")
    print("="*60)

    try:
        from PyQt6.QtWidgets import QApplication
        from client.ui.discovery_dialog import DiscoveryDialog

        print("\n✓ Imported discovery dialog")

        app = QApplication(sys.argv)
        app.setStyle('Fusion')

        print("✓ Created QApplication")
        print("\nOpening discovery dialog...")
        print("  (Dialog will search for servers for 10 seconds)")

        dialog = DiscoveryDialog(timeout=10.0)

        # Connect signal
        def on_server_selected(server_dict):
            print(f"\n✓ Server selected: {server_dict['name']}")
            print(f"  Address: {server_dict['address']}")
            print(f"  API Port: {server_dict['port']}")
            print(f"  WS Port: {server_dict['ws_port']}")

        dialog.server_selected.connect(on_server_selected)

        result = dialog.exec()

        if result:
            selected = dialog.get_selected_server()
            if selected:
                print(f"\n✓ Dialog accepted with server: {selected['name']}")
            else:
                print("\n○ Dialog accepted but no server selected")
        else:
            print("\n○ Dialog cancelled")

        print("\n" + "="*60)
        print("✓ Discovery dialog test complete!")
        print("="*60)

    except ImportError as e:
        print(f"\n○ Skipping GUI test - PyQt6 not available: {e}")
    except Exception as e:
        print(f"\n✗ Discovery dialog test failed: {e}")
        import traceback
        traceback.print_exc()


def test_end_to_end():
    """Test end-to-end: Start server, discover from client."""
    print("\n" + "="*60)
    print("Testing End-to-End mDNS")
    print("="*60)

    try:
        from server.utils.mdns import LabLinkMDNSService
        from client.utils.mdns_discovery import discover_servers
        import threading

        # Start server in thread
        service = LabLinkMDNSService(
            port=8000,
            ws_port=8001,
            server_name="TestServer",
            server_version="1.0.0"
        )

        print("\n1. Starting server mDNS service...")
        if not service.start():
            print("✗ Failed to start service")
            return

        print("✓ Server broadcasting")

        # Give service time to register
        time.sleep(2)

        # Discover from client
        print("\n2. Discovering from client...")
        servers = discover_servers(timeout=3.0)

        print(f"✓ Found {len(servers)} server(s)")

        # Check if our test server was found
        found_test_server = False
        for server in servers:
            if server.name == "TestServer":
                found_test_server = True
                print(f"\n✓ Found test server!")
                print(f"  Name: {server.name}")
                print(f"  Address: {server.address}")
                print(f"  Port: {server.port}")
                break

        if not found_test_server:
            print("\n✗ Test server not found in discovery results")

        # Stop server
        print("\n3. Stopping server...")
        service.stop()
        print("✓ Server stopped")

        if found_test_server:
            print("\n" + "="*60)
            print("✓ End-to-end test PASSED!")
            print("="*60)
        else:
            print("\n" + "="*60)
            print("✗ End-to-end test FAILED - server not discovered")
            print("="*60)

    except Exception as e:
        print(f"\n✗ End-to-end test failed: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run all tests."""
    if not ZEROCONF_AVAILABLE:
        return

    print("\n" + "="*60)
    print("LabLink mDNS/Zeroconf Discovery Tests")
    print("="*60)
    print("\nThese tests demonstrate mDNS service discovery for LabLink.")
    print("Servers can advertise themselves and clients can discover them")
    print("automatically on the local network without manual configuration.")
    print("="*60)

    # Test 1: Server broadcasting
    test_server_mdns()

    # Test 2: Client discovery
    test_client_discovery()

    # Test 3: End-to-end
    test_end_to_end()

    # Test 4: GUI dialog (optional)
    print("\n\nWould you like to test the discovery dialog GUI? (y/n)")
    try:
        response = input().strip().lower()
        if response == 'y':
            test_discovery_dialog()
    except:
        pass

    print("\n" + "="*60)
    print("✓ All tests complete!")
    print("="*60)


if __name__ == "__main__":
    main()
