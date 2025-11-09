"""Test and demo for equipment-specific control panels."""

import sys
import os
import asyncio

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "client"))

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTabWidget, QPushButton, QLabel, QComboBox, QMessageBox
    )
    from PyQt6.QtCore import QTimer
    import pyqtgraph as pg
    import numpy as np
    PYQT_AVAILABLE = True
except ImportError as e:
    print(f"Error: {e}")
    print("\nRequired packages:")
    print("  pip install PyQt6 pyqtgraph numpy")
    PYQT_AVAILABLE = False
    sys.exit(1)

from ui.equipment import OscilloscopePanel, PowerSupplyPanel, ElectronicLoadPanel
from api.client import LabLinkClient
from utils.settings import get_settings


class EquipmentPanelDemo(QMainWindow):
    """Demo window for equipment control panels."""

    def __init__(self):
        """Initialize demo window."""
        super().__init__()

        self.setWindowTitle("LabLink Equipment Control Panels - Demo")
        self.setGeometry(100, 100, 1200, 800)

        # Settings
        self.settings = get_settings()

        # Client (initially None - can be connected later)
        self.client: LabLinkClient = None

        # Setup UI
        self._setup_ui()

        # Demo mode flag
        self.demo_mode = True
        self.demo_timer = None

    def _setup_ui(self):
        """Set up user interface."""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        # Header
        header = QLabel("<h1>Equipment Control Panels Demo</h1>")
        layout.addWidget(header)

        # Connection controls
        conn_layout = QHBoxLayout()

        self.status_label = QLabel("<b>Status:</b> Not connected (Demo Mode)")
        conn_layout.addWidget(self.status_label)

        conn_layout.addStretch()

        self.connect_btn = QPushButton("Connect to Server")
        self.connect_btn.clicked.connect(self._on_connect)
        conn_layout.addWidget(self.connect_btn)

        self.demo_btn = QPushButton("Start Demo Data")
        self.demo_btn.clicked.connect(self._on_toggle_demo)
        conn_layout.addWidget(self.demo_btn)

        layout.addLayout(conn_layout)

        # Equipment selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Select Equipment:"))

        self.equipment_combo = QComboBox()
        self.equipment_combo.addItems([
            "Mock Oscilloscope",
            "Mock Power Supply",
            "Mock Electronic Load"
        ])
        self.equipment_combo.currentIndexChanged.connect(self._on_equipment_changed)
        selector_layout.addWidget(self.equipment_combo)

        selector_layout.addStretch()
        layout.addLayout(selector_layout)

        # Tab widget for equipment panels
        self.tabs = QTabWidget()

        # Oscilloscope panel
        self.scope_panel = OscilloscopePanel()
        self.tabs.addTab(self.scope_panel, "Oscilloscope")

        # Power supply panel
        self.psu_panel = PowerSupplyPanel()
        self.tabs.addTab(self.psu_panel, "Power Supply")

        # Electronic load panel
        self.load_panel = ElectronicLoadPanel()
        self.tabs.addTab(self.load_panel, "Electronic Load")

        layout.addWidget(self.tabs)

        # Info footer
        info_label = QLabel(
            "<i>Demo Mode: Simulated data updates without server connection. "
            "Connect to a real LabLink server for actual equipment control.</i>"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

    def _on_connect(self):
        """Connect to LabLink server."""
        # Get connection settings
        host = self.settings.get_last_host(default="localhost")
        api_port = self.settings.get_last_api_port(default=8000)
        ws_port = self.settings.get_last_ws_port(default=8001)

        try:
            # Create client
            self.client = LabLinkClient(host=host, api_port=api_port, ws_port=ws_port)

            # Set client for all panels
            self.scope_panel.set_client(self.client)
            self.psu_panel.set_client(self.client)
            self.load_panel.set_client(self.client)

            # Update status
            self.status_label.setText(f"<b>Status:</b> Connected to {host}:{api_port}")
            self.connect_btn.setText("Disconnect")
            self.demo_mode = False

            # Stop demo timer
            if self.demo_timer:
                self.demo_timer.stop()
                self.demo_btn.setText("Start Demo Data")

            QMessageBox.information(
                self,
                "Connected",
                f"Successfully connected to LabLink server at {host}:{api_port}\n\n"
                "You can now control real equipment through the panels."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Failed to connect to server:\n{e}\n\n"
                "Make sure the LabLink server is running."
            )

    def _on_equipment_changed(self, index: int):
        """Handle equipment selection change."""
        # Switch to corresponding tab
        self.tabs.setCurrentIndex(index)

        # In demo mode, set up mock equipment info
        if self.demo_mode:
            if index == 0:  # Oscilloscope
                self._setup_mock_scope()
            elif index == 1:  # Power Supply
                self._setup_mock_psu()
            elif index == 2:  # Electronic Load
                self._setup_mock_load()

    def _setup_mock_scope(self):
        """Set up mock oscilloscope."""
        mock_info = {
            'model': 'MOCK::SCOPE::4CH',
            'manufacturer': 'LabLink Simulation',
            'capabilities': {
                'num_channels': 4,
                'max_sample_rate': 1e9,
                'max_bandwidth': 100e6,
                'memory_depth': 1000000
            }
        }
        self.scope_panel.set_equipment('mock_scope_001', mock_info)

    def _setup_mock_psu(self):
        """Set up mock power supply."""
        mock_info = {
            'model': 'MOCK::PSU::3CH',
            'manufacturer': 'LabLink Simulation',
            'capabilities': {
                'num_channels': 3,
                'max_voltage': 30.0,
                'max_current': 5.0,
                'max_power': 150.0
            }
        }
        self.psu_panel.set_equipment('mock_psu_001', mock_info)

    def _setup_mock_load(self):
        """Set up mock electronic load."""
        mock_info = {
            'model': 'MOCK::LOAD::350W',
            'manufacturer': 'LabLink Simulation',
            'capabilities': {
                'max_voltage': 120.0,
                'max_current': 30.0,
                'max_power': 350.0,
                'max_resistance': 10000.0,
                'modes': ['CC', 'CV', 'CR', 'CP']
            }
        }
        self.load_panel.set_equipment('mock_load_001', mock_info)

    def _on_toggle_demo(self):
        """Toggle demo data generation."""
        if not self.demo_timer:
            # Create timer for demo data
            self.demo_timer = QTimer()
            self.demo_timer.timeout.connect(self._update_demo_data)
            self.demo_timer.start(100)  # 100ms updates
            self.demo_btn.setText("Stop Demo Data")

            # Set up mock equipment for current selection
            self._on_equipment_changed(self.equipment_combo.currentIndex())

        else:
            # Stop demo
            self.demo_timer.stop()
            self.demo_timer = None
            self.demo_btn.setText("Start Demo Data")

    def _update_demo_data(self):
        """Update demo data for panels."""
        current_index = self.tabs.currentIndex()

        if current_index == 0:  # Oscilloscope
            self._update_scope_demo()
        elif current_index == 1:  # Power Supply
            self._update_psu_demo()
        elif current_index == 2:  # Electronic Load
            self._update_load_demo()

    def _update_scope_demo(self):
        """Update oscilloscope demo data."""
        # Generate mock waveform data
        num_points = 1000
        t = np.linspace(0, 0.01, num_points)

        # Generate waveforms for 4 channels
        ch1 = np.sin(2 * np.pi * 1000 * t)  # 1 kHz sine
        ch2 = np.sin(2 * np.pi * 2000 * t)  # 2 kHz sine
        ch3 = np.sign(np.sin(2 * np.pi * 500 * t))  # 500 Hz square
        ch4 = 2 * (t % (1/1000)) * 1000 - 1  # 1 kHz triangle

        message = {
            'type': 'stream_data',
            'equipment_id': 'mock_scope_001',
            'stream_type': 'waveform',
            'timestamp': asyncio.get_event_loop().time(),
            'data': {
                'channels': [1, 2, 3, 4],
                'waveforms': [ch1.tolist(), ch2.tolist(), ch3.tolist(), ch4.tolist()],
                'time_scale': 0.001,  # 1 ms/div
                'voltage_scales': [1.0, 1.0, 1.0, 1.0]
            }
        }

        self.scope_panel._on_waveform_data(message)

    def _update_psu_demo(self):
        """Update power supply demo data."""
        import random

        # Simulate voltage and current readings
        voltage_set = self.psu_panel.voltage_spin.value()
        current_set = self.psu_panel.current_spin.value()

        # Add some noise
        voltage_actual = voltage_set + random.gauss(0, 0.001)
        current_actual = min(current_set, voltage_set / 10.0) + random.gauss(0, 0.0001)

        message = {
            'type': 'stream_data',
            'equipment_id': 'mock_psu_001',
            'stream_type': 'readings',
            'timestamp': asyncio.get_event_loop().time(),
            'data': {
                'channel': 1,
                'voltage_actual': voltage_actual,
                'current_actual': current_actual,
                'voltage_set': voltage_set,
                'current_set': current_set,
                'in_cv_mode': current_actual < current_set * 0.95,
                'in_cc_mode': current_actual >= current_set * 0.95,
                'output_enabled': self.psu_panel.output_checkbox.isChecked()
            }
        }

        self.psu_panel._on_readings_data(message)

    def _update_load_demo(self):
        """Update electronic load demo data."""
        import random

        # Get current mode and setpoint
        mode_index = self.load_panel.mode_combo.currentIndex()
        modes = ['CC', 'CV', 'CR', 'CP']
        mode = modes[mode_index]

        # Get setpoint based on mode
        if mode == 'CC':
            setpoint = self.load_panel.current_spin.value()
            current = setpoint + random.gauss(0, 0.001)
            voltage = 12.0 + random.gauss(0, 0.01)  # Simulated source
        elif mode == 'CV':
            setpoint = self.load_panel.voltage_spin.value()
            voltage = setpoint + random.gauss(0, 0.001)
            current = 2.0 + random.gauss(0, 0.01)  # Simulated
        elif mode == 'CR':
            setpoint = self.load_panel.resistance_spin.value()
            voltage = 12.0 + random.gauss(0, 0.01)
            current = voltage / setpoint + random.gauss(0, 0.001)
        else:  # CP
            setpoint = self.load_panel.power_spin.value()
            voltage = 12.0 + random.gauss(0, 0.01)
            current = setpoint / voltage + random.gauss(0, 0.001)

        power = voltage * current

        message = {
            'type': 'stream_data',
            'equipment_id': 'mock_load_001',
            'stream_type': 'readings',
            'timestamp': asyncio.get_event_loop().time(),
            'data': {
                'voltage': voltage,
                'current': current,
                'power': power,
                'mode': mode,
                'setpoint': setpoint,
                'input_enabled': self.load_panel.input_checkbox.isChecked()
            }
        }

        self.load_panel._on_readings_data(message)

    def closeEvent(self, event):
        """Handle window close."""
        # Stop demo timer
        if self.demo_timer:
            self.demo_timer.stop()

        # Disconnect client if connected
        if self.client:
            # Would disconnect here
            pass

        event.accept()


def main():
    """Run demo application."""
    if not PYQT_AVAILABLE:
        return

    print("\n" + "="*60)
    print("LabLink Equipment Control Panels Demo")
    print("="*60)
    print("\nThis demo showcases the equipment-specific control panels:")
    print("  1. Oscilloscope Panel - Waveform display and controls")
    print("  2. Power Supply Panel - Voltage/current control and monitoring")
    print("  3. Electronic Load Panel - Multi-mode operation (CC/CV/CR/CP)")
    print("\nFeatures:")
    print("  - Real-time data visualization")
    print("  - Equipment-specific controls")
    print("  - Demo mode with simulated data")
    print("  - Server connection support")
    print("\nClick 'Start Demo Data' to see simulated data updates")
    print("="*60 + "\n")

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Set dark theme
    app.setStyleSheet("""
        QMainWindow {
            background-color: #2b2b2b;
        }
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QGroupBox {
            border: 2px solid #555555;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
        }
        QPushButton {
            background-color: #404040;
            border: 1px solid #555555;
            padding: 5px 15px;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #505050;
        }
        QPushButton:pressed {
            background-color: #303030;
        }
        QTabWidget::pane {
            border: 1px solid #555555;
        }
        QTabBar::tab {
            background-color: #404040;
            border: 1px solid #555555;
            padding: 5px 10px;
        }
        QTabBar::tab:selected {
            background-color: #2b2b2b;
        }
    """)

    window = EquipmentPanelDemo()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
