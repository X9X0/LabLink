#!/usr/bin/env python3
"""
GUI Integration Test with Mock Equipment

This script tests the GUI client with mock equipment to verify end-to-end functionality.

Prerequisites:
1. Start server with mock equipment:
   export LABLINK_ENABLE_MOCK_EQUIPMENT=true
   python -m server.main

2. Run this test:
   python test_gui_with_mock.py

The script will:
- Start the GUI client
- Connect to the server
- Verify mock equipment is available
- Test basic operations
"""

import sys
import logging
from pathlib import Path

# Add client path
sys.path.insert(0, str(Path(__file__).parent / "client"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt, QTimer
import qasync
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GUIMockEquipmentTest:
    """Test GUI client with mock equipment."""

    def __init__(self, app, loop):
        """Initialize test."""
        self.app = app
        self.loop = loop
        self.test_results = []

    async def run_tests(self):
        """Run all GUI tests."""
        logger.info("="*60)
        logger.info("GUI Client Mock Equipment Integration Test")
        logger.info("="*60)

        try:
            # Import after Qt app is created
            from ui.main_window import MainWindow
            from api.client import LabLinkClient

            # Test 1: Create main window
            logger.info("\nTest 1: Creating main window...")
            self.main_window = MainWindow()
            self.main_window.show()
            await asyncio.sleep(0.5)
            self.test_results.append(("Create main window", True, None))
            logger.info("✅ Main window created")

            # Test 2: Connect to server
            logger.info("\nTest 2: Connecting to server...")
            try:
                success = await self._connect_to_server()
                if success:
                    self.test_results.append(("Connect to server", True, None))
                    logger.info("✅ Connected to server")
                else:
                    self.test_results.append(("Connect to server", False, "Connection failed"))
                    logger.error("❌ Failed to connect to server")
                    return
            except Exception as e:
                self.test_results.append(("Connect to server", False, str(e)))
                logger.error(f"❌ Connection error: {e}")
                return

            # Test 3: Check for mock equipment
            logger.info("\nTest 3: Checking for mock equipment...")
            await asyncio.sleep(1)  # Wait for equipment list to populate
            try:
                equipment_count = await self._check_mock_equipment()
                if equipment_count > 0:
                    self.test_results.append(("Check mock equipment", True, None))
                    logger.info(f"✅ Found {equipment_count} mock equipment devices")
                else:
                    self.test_results.append(("Check mock equipment", False, "No equipment found"))
                    logger.warning("⚠️  No mock equipment found - did you start server with ENABLE_MOCK_EQUIPMENT=true?")
            except Exception as e:
                self.test_results.append(("Check mock equipment", False, str(e)))
                logger.error(f"❌ Error checking equipment: {e}")

            # Test 4: Test equipment panel
            logger.info("\nTest 4: Testing equipment panel...")
            try:
                panel_works = await self._test_equipment_panel()
                if panel_works:
                    self.test_results.append(("Test equipment panel", True, None))
                    logger.info("✅ Equipment panel functional")
                else:
                    self.test_results.append(("Test equipment panel", False, "Panel test failed"))
                    logger.error("❌ Equipment panel test failed")
            except Exception as e:
                self.test_results.append(("Test equipment panel", False, str(e)))
                logger.error(f"❌ Equipment panel error: {e}")

            # Test 5: Test WebSocket connection
            logger.info("\nTest 5: Testing WebSocket connection...")
            try:
                ws_connected = await self._test_websocket()
                if ws_connected:
                    self.test_results.append(("Test WebSocket", True, None))
                    logger.info("✅ WebSocket connected")
                else:
                    self.test_results.append(("Test WebSocket", False, "WebSocket not connected"))
                    logger.warning("⚠️  WebSocket not connected (optional)")
            except Exception as e:
                self.test_results.append(("Test WebSocket", False, str(e)))
                logger.error(f"❌ WebSocket error: {e}")

            # Print summary
            await self._print_summary()

        except Exception as e:
            logger.error(f"Test error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Close window after tests
            QTimer.singleShot(2000, self.main_window.close)

    async def _connect_to_server(self):
        """Connect to local server."""
        try:
            # Use quick connect to localhost
            if hasattr(self.main_window, 'quick_connect_localhost'):
                await self.main_window.quick_connect_localhost()
            else:
                # Manual connection
                await self.main_window.connect_to_server("localhost", 8000, 8001)

            # Wait for connection
            await asyncio.sleep(1)

            # Check if connected
            if self.main_window.client and self.main_window.client.connected:
                return True

            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def _check_mock_equipment(self):
        """Check if mock equipment is available."""
        try:
            if not self.main_window.client:
                return 0

            # Get equipment list
            equipment_list = self.main_window.client.list_equipment()
            logger.info(f"Found {len(equipment_list)} equipment devices")

            # Count mock equipment
            mock_count = 0
            for equipment in equipment_list:
                if "Mock" in equipment.get("model", "") or "MOCK" in equipment.get("resource_string", ""):
                    mock_count += 1
                    logger.info(f"  - {equipment.get('model', 'Unknown')}: {equipment.get('id', 'Unknown')}")

            return mock_count
        except Exception as e:
            logger.error(f"Error checking equipment: {e}")
            return 0

    async def _test_equipment_panel(self):
        """Test equipment panel functionality."""
        try:
            # Switch to equipment tab
            if hasattr(self.main_window, 'tabs'):
                self.main_window.tabs.setCurrentIndex(0)  # Equipment panel
                await asyncio.sleep(0.5)

            # Check if equipment panel exists
            if hasattr(self.main_window, 'equipment_panel'):
                panel = self.main_window.equipment_panel

                # Check if client is set
                if hasattr(panel, 'client') and panel.client:
                    logger.info("  Equipment panel has client")
                    return True

            return False
        except Exception as e:
            logger.error(f"Equipment panel test error: {e}")
            return False

    async def _test_websocket(self):
        """Test WebSocket connection."""
        try:
            if not self.main_window.client:
                return False

            if hasattr(self.main_window.client, 'ws_manager'):
                ws_manager = self.main_window.client.ws_manager
                if ws_manager and hasattr(ws_manager, 'connected'):
                    return ws_manager.connected

            return False
        except Exception as e:
            logger.error(f"WebSocket test error: {e}")
            return False

    async def _print_summary(self):
        """Print test summary."""
        logger.info("\n" + "="*60)
        logger.info("Test Summary")
        logger.info("="*60)

        passed = 0
        failed = 0

        for test_name, success, error in self.test_results:
            if success:
                logger.info(f"✅ {test_name}")
                passed += 1
            else:
                logger.error(f"❌ {test_name}: {error}")
                failed += 1

        logger.info("\n" + "="*60)
        logger.info(f"Results: {passed} passed, {failed} failed")
        logger.info("="*60 + "\n")

        if failed == 0:
            logger.info("🎉 All tests passed!")
        else:
            logger.warning(f"⚠️  {failed} test(s) failed")


async def main():
    """Main test function."""
    # Create Qt application
    app = QApplication(sys.argv)

    # Create event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create and run tests
    tester = GUIMockEquipmentTest(app, loop)

    # Schedule tests to run after app starts
    loop.create_task(tester.run_tests())

    # Run app
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    logger.info("Starting GUI Mock Equipment Integration Test")
    logger.info("Make sure server is running with LABLINK_ENABLE_MOCK_EQUIPMENT=true")
    logger.info("")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
    except Exception as e:
        logger.error(f"Test error: {e}")
        import traceback
        traceback.print_exc()
