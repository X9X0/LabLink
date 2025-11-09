#!/usr/bin/env python3
"""
Comprehensive Data Acquisition Demo for LabLink

This demo showcases the full data acquisition system integration including:
- Acquisition session management
- Real-time statistics
- Multi-instrument synchronization
- Data export

Run with: python3 demo_acquisition_full.py
"""

import sys
import logging
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget,
    QStatusBar, QMessageBox
)
from PyQt6.QtCore import Qt

# Add client directory to path
sys.path.insert(0, 'client')

from api.client import LabLinkClient
from ui.acquisition_panel import AcquisitionPanel
from ui.sync_panel import SyncPanel

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AcquisitionDemoWindow(QMainWindow):
    """Main window for acquisition demo."""

    def __init__(self):
        """Initialize demo window."""
        super().__init__()

        self.client: LabLinkClient = None

        self._setup_ui()
        self._connect_to_server()

    def _setup_ui(self):
        """Setup user interface."""
        self.setWindowTitle("LabLink Data Acquisition Demo")
        self.setGeometry(100, 100, 1400, 900)

        # Create tabs
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Acquisition tab
        self.acquisition_panel = AcquisitionPanel()
        self.acquisition_panel.acquisition_started.connect(self._on_acquisition_started)
        self.acquisition_panel.acquisition_stopped.connect(self._on_acquisition_stopped)
        self.tabs.addTab(self.acquisition_panel, "Data Acquisition")

        # Synchronization tab
        self.sync_panel = SyncPanel()
        self.sync_panel.sync_group_created.connect(self._on_sync_group_created)
        self.sync_panel.sync_group_started.connect(self._on_sync_group_started)
        self.sync_panel.sync_group_stopped.connect(self._on_sync_group_stopped)
        self.tabs.addTab(self.sync_panel, "Multi-Instrument Sync")

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _connect_to_server(self):
        """Connect to LabLink server."""
        try:
            # Create client
            self.client = LabLinkClient(
                host="localhost",
                api_port=8000,
                ws_port=8001
            )

            # Try to connect
            if self.client.connect():
                logger.info("Connected to LabLink server")
                self.status_bar.showMessage("Connected to localhost:8000")

                # Set client for panels
                self.acquisition_panel.set_client(self.client)
                self.sync_panel.set_client(self.client)
            else:
                logger.warning("Could not connect to server")
                self.status_bar.showMessage("Not connected - using offline mode")
                QMessageBox.warning(
                    self,
                    "Connection Failed",
                    "Could not connect to LabLink server at localhost:8000\n\n"
                    "Make sure the server is running:\n"
                    "  cd server && python3 main.py\n\n"
                    "Demo will run in offline mode (limited functionality)"
                )

        except Exception as e:
            logger.error(f"Error connecting to server: {e}")
            self.status_bar.showMessage("Connection error")
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Failed to connect to server:\n{str(e)}"
            )

    def _on_acquisition_started(self, acquisition_id: str):
        """Handle acquisition started."""
        self.status_bar.showMessage(f"Acquisition started: {acquisition_id[:8]}...")
        logger.info(f"Acquisition started: {acquisition_id}")

    def _on_acquisition_stopped(self, acquisition_id: str):
        """Handle acquisition stopped."""
        self.status_bar.showMessage(f"Acquisition stopped: {acquisition_id[:8]}...")
        logger.info(f"Acquisition stopped: {acquisition_id}")

    def _on_sync_group_created(self, group_id: str):
        """Handle sync group created."""
        self.status_bar.showMessage(f"Sync group created: {group_id}")
        logger.info(f"Sync group created: {group_id}")

    def _on_sync_group_started(self, group_id: str):
        """Handle sync group started."""
        self.status_bar.showMessage(f"Synchronized acquisition started: {group_id}")
        logger.info(f"Sync group started: {group_id}")

    def _on_sync_group_stopped(self, group_id: str):
        """Handle sync group stopped."""
        self.status_bar.showMessage(f"Synchronized acquisition stopped: {group_id}")
        logger.info(f"Sync group stopped: {group_id}")

    def closeEvent(self, event):
        """Handle window close."""
        if self.client:
            logger.info("Disconnecting from server")
        event.accept()


def main():
    """Run the demo application."""
    app = QApplication(sys.argv)

    # Create and show main window
    window = AcquisitionDemoWindow()
    window.show()

    # Print usage instructions
    print("""
╔═══════════════════════════════════════════════════════════════╗
║         LabLink Data Acquisition System Demo                  ║
╠═══════════════════════════════════════════════════════════════╣
║                                                                ║
║  FEATURES DEMONSTRATED:                                        ║
║                                                                ║
║  1. Data Acquisition Tab                                       ║
║     • Create acquisition sessions with full configuration     ║
║     • Start/Stop/Pause/Resume acquisitions                    ║
║     • Real-time session monitoring with auto-refresh          ║
║     • View acquisition statistics:                            ║
║       - Rolling stats (mean, std, min, max, RMS, P2P)         ║
║       - FFT analysis (fundamental freq, THD, SNR)             ║
║       - Trend detection (rising, falling, stable, noisy)      ║
║       - Data quality metrics (grade, noise, stability)        ║
║     • Load and visualize acquired data                        ║
║     • Export data (CSV, HDF5, NumPy, JSON)                    ║
║                                                                ║
║  2. Multi-Instrument Sync Tab                                  ║
║     • Create synchronization groups                           ║
║     • Add multiple equipment to group                         ║
║     • Configure sync tolerance and master equipment           ║
║     • Start/stop synchronized acquisitions                    ║
║     • Monitor sync status and ready equipment                 ║
║                                                                ║
║  QUICK START:                                                  ║
║                                                                ║
║  1. Ensure LabLink server is running:                         ║
║       cd server && python3 main.py                            ║
║                                                                ║
║  2. In "Data Acquisition" tab:                                 ║
║     a. Select equipment from dropdown                         ║
║     b. Configure acquisition parameters                        ║
║     c. Click "Create Session"                                  ║
║     d. Click "Start" to begin acquisition                      ║
║     e. Use Statistics tab to view analysis                     ║
║                                                                ║
║  3. In "Multi-Instrument Sync" tab:                            ║
║     a. Select multiple equipment (Ctrl+Click)                  ║
║     b. Enter group ID and click "Create Group"                 ║
║     c. Create acquisitions for each equipment first           ║
║     d. Add acquisitions to the sync group                      ║
║     e. Click "Start Group" for synchronized acquisition       ║
║                                                                ║
║  SUPPORTED ACQUISITION MODES:                                  ║
║     • Continuous - Acquire until stopped                       ║
║     • Single-Shot - Acquire N samples                          ║
║     • Triggered - Wait for trigger condition                   ║
║                                                                ║
║  TRIGGER TYPES:                                                ║
║     • Immediate - Start immediately                            ║
║     • Level - Trigger on threshold crossing                    ║
║     • Edge - Trigger on rising/falling edge                    ║
║     • Time - Trigger at specific time                          ║
║     • External - Wait for external signal                      ║
║                                                                ║
║  EXPORT FORMATS:                                               ║
║     • CSV - Spreadsheet compatible                             ║
║     • HDF5 - Large datasets, scientific                        ║
║     • NumPy - Python array format                              ║
║     • JSON - Web/JavaScript applications                       ║
║                                                                ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
