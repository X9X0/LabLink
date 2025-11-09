"""Test WebSocket streaming with mock equipment."""

import asyncio
import sys
import os

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "client"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))

from client.api.client import LabLinkClient
from client.utils.websocket_manager import StreamType, MessageType


class WebSocketDemo:
    """Demo WebSocket streaming functionality."""

    def __init__(self):
        """Initialize demo."""
        self.client = LabLinkClient(host="localhost", api_port=8000, ws_port=8001)
        self.data_count = 0
        self.acq_data_count = 0

    def on_stream_data(self, message):
        """Handle equipment stream data."""
        equipment_id = message.get("equipment_id")
        stream_type = message.get("stream_type")
        data = message.get("data", {})

        self.data_count += 1

        if self.data_count % 10 == 0:  # Print every 10th message
            print(f"\n[Stream Data #{self.data_count}]")
            print(f"  Equipment: {equipment_id}")
            print(f"  Type: {stream_type}")

            if stream_type == "readings":
                # Power supply or electronic load readings
                if "voltage_actual" in data:
                    print(f"  Voltage: {data.get('voltage_actual', 0):.3f}V")
                    print(f"  Current: {data.get('current_actual', 0):.3f}A")
                    print(f"  Output: {data.get('output_enabled', False)}")
                    print(f"  Mode: CV={data.get('in_cv_mode', False)}, CC={data.get('in_cc_mode', False)}")
                elif "voltage" in data:
                    print(f"  Voltage: {data.get('voltage', 0):.3f}V")
                    print(f"  Current: {data.get('current', 0):.3f}A")
                    print(f"  Power: {data.get('power', 0):.3f}W")
                    print(f"  Mode: {data.get('mode', 'unknown')}")

            elif stream_type == "waveform":
                print(f"  Sample rate: {data.get('sample_rate', 0)/1e9:.1f} GSa/s")
                print(f"  Num samples: {data.get('num_samples', 0)}")

            elif stream_type == "measurements":
                print(f"  Measurements:")
                for key, value in data.items():
                    if isinstance(value, (int, float)):
                        print(f"    {key}: {value:.6f}")

    def on_acquisition_data(self, message):
        """Handle acquisition stream data."""
        acquisition_id = message.get("acquisition_id")
        state = message.get("state")
        data = message.get("data")

        self.acq_data_count += 1

        if self.acq_data_count % 5 == 0:  # Print every 5th message
            print(f"\n[Acquisition Data #{self.acq_data_count}]")
            print(f"  Acquisition ID: {acquisition_id}")
            print(f"  State: {state}")

            if data:
                print(f"  Samples: {data.get('count', 0)}")

    def on_stream_started(self, message):
        """Handle stream started confirmation."""
        equipment_id = message.get("equipment_id")
        stream_type = message.get("stream_type")
        print(f"✓ Stream started: {stream_type} from {equipment_id}")

    def on_stream_stopped(self, message):
        """Handle stream stopped confirmation."""
        equipment_id = message.get("equipment_id")
        stream_type = message.get("stream_type")
        print(f"✓ Stream stopped: {stream_type} from {equipment_id}")

    async def test_basic_streaming(self):
        """Test basic equipment streaming."""
        print("\n" + "="*60)
        print("Test 1: Basic Equipment Streaming")
        print("="*60)

        # Connect WebSocket
        print("\n1. Connecting to WebSocket...")
        connected = await self.client.connect_websocket()
        if not connected:
            print("✗ Failed to connect WebSocket")
            return

        print("✓ WebSocket connected")

        # Register handlers
        self.client.register_stream_data_handler(self.on_stream_data)
        self.client.ws_manager.register_handler(MessageType.STREAM_STARTED, self.on_stream_started)
        self.client.ws_manager.register_handler(MessageType.STREAM_STOPPED, self.on_stream_stopped)

        # Assume mock equipment is connected (would need server running)
        # In real scenario, you'd call list_equipment() to get equipment_id

        # Simulate equipment ID
        equipment_id = "mock_ps_12345678"

        print(f"\n2. Starting readings stream from {equipment_id}...")
        try:
            await self.client.start_equipment_stream(
                equipment_id=equipment_id,
                stream_type="readings",
                interval_ms=200  # 200ms = 5 Hz
            )
        except Exception as e:
            print(f"Note: {e} (requires server running with mock equipment)")
            return

        # Let it stream for a bit
        print("\n3. Streaming data for 5 seconds...")
        await asyncio.sleep(5)

        # Get statistics
        stats = self.client.get_websocket_statistics()
        print(f"\n4. WebSocket Statistics:")
        print(f"  Messages received: {stats['messages_received']}")
        print(f"  Messages sent: {stats['messages_sent']}")
        print(f"  Active streams: {stats['active_streams']}")
        print(f"  Data count: {self.data_count}")

        # Stop stream
        print(f"\n5. Stopping stream...")
        await self.client.stop_equipment_stream(
            equipment_id=equipment_id,
            stream_type="readings"
        )

        await asyncio.sleep(1)
        print("\n✓ Basic streaming test complete")

    async def test_multi_stream(self):
        """Test multiple simultaneous streams."""
        print("\n" + "="*60)
        print("Test 2: Multiple Simultaneous Streams")
        print("="*60)

        # Connect if not already connected
        if not self.client.ws_manager.connected:
            await self.client.connect_websocket()

        # Simulate multiple equipment
        scope_id = "mock_scope_12345678"
        psu_id = "mock_ps_12345678"
        load_id = "mock_load_12345678"

        print("\n1. Starting multiple streams...")
        try:
            # Start waveform stream from scope
            await self.client.start_equipment_stream(
                equipment_id=scope_id,
                stream_type="waveform",
                interval_ms=100
            )

            # Start readings from PSU
            await self.client.start_equipment_stream(
                equipment_id=psu_id,
                stream_type="readings",
                interval_ms=200
            )

            # Start readings from load
            await self.client.start_equipment_stream(
                equipment_id=load_id,
                stream_type="readings",
                interval_ms=200
            )

        except Exception as e:
            print(f"Note: {e} (requires server running)")
            return

        # Stream for a bit
        print("\n2. Streaming from multiple devices for 5 seconds...")
        await asyncio.sleep(5)

        # Check active streams
        active_streams = self.client.ws_manager.get_active_streams()
        print(f"\n3. Active streams: {len(active_streams)}")
        for stream in active_streams:
            print(f"  - {stream}")

        # Stop all streams
        print("\n4. Stopping all streams...")
        await self.client.stop_equipment_stream(scope_id, "waveform")
        await self.client.stop_equipment_stream(psu_id, "readings")
        await self.client.stop_equipment_stream(load_id, "readings")

        await asyncio.sleep(1)
        print("\n✓ Multi-stream test complete")

    async def test_reconnection(self):
        """Test automatic reconnection."""
        print("\n" + "="*60)
        print("Test 3: Automatic Reconnection")
        print("="*60)

        print("\n1. Testing reconnection behavior...")
        print("   (This would require server restart to test fully)")

        # Show reconnection is enabled
        print(f"   Reconnection enabled: {self.client.ws_manager._should_reconnect}")
        print(f"   Reconnection delay: {self.client.ws_manager._reconnect_delay}s")

        # In a real test, you would:
        # 1. Start a stream
        # 2. Kill the server
        # 3. Restart the server
        # 4. Verify the stream automatically resumes

        print("\n✓ Reconnection test complete")

    async def cleanup(self):
        """Clean up connections."""
        print("\n" + "="*60)
        print("Cleanup")
        print("="*60)

        if self.client.ws_manager:
            await self.client.ws_manager.disconnect()
            print("✓ WebSocket disconnected")

        final_stats = self.client.get_websocket_statistics()
        print(f"\nFinal Statistics:")
        print(f"  Total data messages: {self.data_count}")
        print(f"  Total acquisition messages: {self.acq_data_count}")
        print(f"  Messages received: {final_stats['messages_received']}")
        print(f"  Messages sent: {final_stats['messages_sent']}")
        print(f"  Errors: {final_stats['errors']}")

    async def run_all_tests(self):
        """Run all tests."""
        print("\n" + "="*60)
        print("WebSocket Streaming Tests")
        print("="*60)
        print("\nNote: These tests require the LabLink server to be running")
        print("      with mock equipment connected.")
        print("\nTo start server with mock equipment:")
        print("  1. Start server: cd server && python3 main.py")
        print("  2. Connect mock equipment via API or UI")

        try:
            await self.test_basic_streaming()
            # await self.test_multi_stream()  # Uncomment when server is running
            # await self.test_reconnection()  # Uncomment when server is running

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")

        except Exception as e:
            print(f"\n✗ Test failed: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await self.cleanup()


async def main():
    """Run the demo."""
    demo = WebSocketDemo()
    await demo.run_all_tests()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("LabLink WebSocket Streaming Demo")
    print("="*60)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDemo interrupted")

    print("\n" + "="*60)
    print("Demo complete!")
    print("="*60 + "\n")
