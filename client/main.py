#!/usr/bin/env python3
"""LabLink GUI Client - Main entry point."""

import asyncio
import logging
import sys
from pathlib import Path

# Add client directory to path
client_dir = Path(__file__).parent
sys.path.insert(0, str(client_dir))

import qasync
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from client.ui.main_window import MainWindow


def setup_logging():
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("lablink_client.log")],
    )


def main():
    """Main application entry point."""
    # Set up logging
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting LabLink GUI Client v0.10.0 with async WebSocket support")

    # Enable high DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("LabLink")
    app.setApplicationVersion("0.10.0")
    app.setOrganizationName("LabLink Project")

    # Set application style (optional)
    app.setStyle("Fusion")

    # Create qasync event loop for asyncio integration
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Show connection dialog on startup
    window.show_connection_dialog()

    # Run application with qasync event loop
    with loop:
        sys.exit(loop.run_forever())


if __name__ == "__main__":
    main()
