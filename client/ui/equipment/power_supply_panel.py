"""Power supply-specific control panel."""

import asyncio
import logging
from typing import Optional

try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFormLayout,
                                 QGroupBox, QHBoxLayout, QLabel, QPushButton,
                                 QSlider, QSpinBox, QTabWidget, QVBoxLayout,
                                 QWidget)

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from client.api.client import LabLinkClient, call_blocking
from client.ui.widgets.power_chart_widget import PowerChartWidget

logger = logging.getLogger(__name__)


class PowerSupplyPanel(QWidget):
    """Control panel for power supply equipment."""

    def __init__(self, parent=None):
        """Initialize power supply panel."""
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 is required")

        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.equipment_id: Optional[str] = None
        self.streaming = False
        self.num_channels = 1

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Power Supply Control</h2>")
        layout.addWidget(header)

        # Equipment info
        self.info_label = QLabel("<i>No equipment connected</i>")
        layout.addWidget(self.info_label)

        # Tabs
        tabs = QTabWidget()

        # Control tab
        control_tab = self._create_control_tab()
        tabs.addTab(control_tab, "Control")

        # Monitor tab
        monitor_tab = self._create_monitor_tab()
        tabs.addTab(monitor_tab, "Monitor")

        layout.addWidget(tabs)

        # Status bar
        status_layout = QHBoxLayout()

        self.status_label = QLabel("Status: Not connected")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.mode_label = QLabel("Mode: ---")
        self.mode_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        status_layout.addWidget(self.mode_label)

        layout.addLayout(status_layout)

    def _create_control_tab(self) -> QWidget:
        """Create control tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Channel selection (for multi-channel PSU)
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Channel:"))

        self.channel_selector = QSpinBox()
        self.channel_selector.setRange(1, 3)
        self.channel_selector.setValue(1)
        self.channel_selector.valueChanged.connect(self._on_channel_changed)
        channel_layout.addWidget(self.channel_selector)

        channel_layout.addStretch()
        layout.addLayout(channel_layout)

        # Voltage control
        voltage_group = QGroupBox("Voltage Control")
        voltage_layout = QVBoxLayout()

        # Voltage setpoint
        v_setpoint_layout = QHBoxLayout()

        v_setpoint_layout.addWidget(QLabel("Setpoint:"))

        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setRange(0, 60)
        self.voltage_spin.setDecimals(3)
        self.voltage_spin.setSuffix(" V")
        self.voltage_spin.setSingleStep(0.1)
        self.voltage_spin.valueChanged.connect(self._on_voltage_changed)
        v_setpoint_layout.addWidget(self.voltage_spin)

        v_setpoint_layout.addStretch()
        voltage_layout.addLayout(v_setpoint_layout)

        # Voltage slider
        self.voltage_slider = QSlider(Qt.Orientation.Horizontal)
        self.voltage_slider.setRange(0, 60000)  # mV
        self.voltage_slider.valueChanged.connect(self._on_voltage_slider_changed)
        voltage_layout.addWidget(self.voltage_slider)

        # Voltage readback
        v_readback_layout = QHBoxLayout()
        v_readback_layout.addWidget(QLabel("Actual:"))

        self.voltage_actual_label = QLabel("0.000 V")
        self.voltage_actual_label.setStyleSheet(
            "font-size: 16pt; font-weight: bold; color: #FF0000;"
        )
        v_readback_layout.addWidget(self.voltage_actual_label)

        v_readback_layout.addStretch()
        voltage_layout.addLayout(v_readback_layout)

        voltage_group.setLayout(voltage_layout)
        layout.addWidget(voltage_group)

        # Current control
        current_group = QGroupBox("Current Control")
        current_layout = QVBoxLayout()

        # Current limit
        i_setpoint_layout = QHBoxLayout()

        i_setpoint_layout.addWidget(QLabel("Limit:"))

        self.current_spin = QDoubleSpinBox()
        self.current_spin.setRange(0, 10)
        self.current_spin.setDecimals(3)
        self.current_spin.setSuffix(" A")
        self.current_spin.setSingleStep(0.01)
        self.current_spin.valueChanged.connect(self._on_current_changed)
        i_setpoint_layout.addWidget(self.current_spin)

        i_setpoint_layout.addStretch()
        current_layout.addLayout(i_setpoint_layout)

        # Current slider
        self.current_slider = QSlider(Qt.Orientation.Horizontal)
        self.current_slider.setRange(0, 10000)  # mA
        self.current_slider.valueChanged.connect(self._on_current_slider_changed)
        current_layout.addWidget(self.current_slider)

        # Current readback
        i_readback_layout = QHBoxLayout()
        i_readback_layout.addWidget(QLabel("Actual:"))

        self.current_actual_label = QLabel("0.000 A")
        self.current_actual_label.setStyleSheet(
            "font-size: 16pt; font-weight: bold; color: #00FF00;"
        )
        i_readback_layout.addWidget(self.current_actual_label)

        i_readback_layout.addStretch()
        current_layout.addLayout(i_readback_layout)

        current_group.setLayout(current_layout)
        layout.addWidget(current_group)

        # Power display
        power_layout = QHBoxLayout()
        power_layout.addWidget(QLabel("<b>Power:</b>"))

        self.power_label = QLabel("0.000 W")
        self.power_label.setStyleSheet(
            "font-size: 16pt; font-weight: bold; color: #0000FF;"
        )
        power_layout.addWidget(self.power_label)

        power_layout.addStretch()
        layout.addLayout(power_layout)

        # Protection (OVP / OCP)
        layout.addWidget(self._create_protection_group())

        # Output control
        output_layout = QHBoxLayout()

        self.output_checkbox = QCheckBox("Output Enabled")
        self.output_checkbox.setStyleSheet("font-size: 14pt;")
        self.output_checkbox.stateChanged.connect(self._on_output_changed)
        output_layout.addWidget(self.output_checkbox)

        output_layout.addStretch()
        layout.addLayout(output_layout)

        # Quick actions
        actions_layout = QHBoxLayout()

        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;"
        )
        self.apply_btn.clicked.connect(self._on_apply_settings)
        self.apply_btn.setEnabled(False)
        actions_layout.addWidget(self.apply_btn)

        zero_btn = QPushButton("Set to Zero")
        zero_btn.clicked.connect(self._on_set_zero)
        actions_layout.addWidget(zero_btn)

        layout.addLayout(actions_layout)

        layout.addStretch()

        return widget

    def _create_protection_group(self) -> QGroupBox:
        """Build the OVP/OCP controls.

        These are trip *ceilings*, not setpoints, so they are deliberately kept
        out of "Apply Settings": an operator arming a guard at 12.5 V should
        not also push the output to whatever the voltage roller happens to be
        showing. Each has its own Arm button and takes effect on its own.
        """
        group = QGroupBox("Protection")
        layout = QVBoxLayout()

        self.protection_note = QLabel()
        self.protection_note.setWordWrap(True)
        self.protection_note.setVisible(False)
        layout.addWidget(self.protection_note)

        form = QFormLayout()

        # --- Over-voltage ------------------------------------------------
        ovp_row = QHBoxLayout()
        self.ovp_spin = QDoubleSpinBox()
        self.ovp_spin.setRange(0, 60)
        self.ovp_spin.setDecimals(3)
        self.ovp_spin.setSuffix(" V")
        self.ovp_spin.setSingleStep(0.1)
        ovp_row.addWidget(self.ovp_spin)

        self.ovp_enable = QCheckBox("Arm")
        ovp_row.addWidget(self.ovp_enable)

        self.ovp_apply_btn = QPushButton("Set OVP")
        self.ovp_apply_btn.clicked.connect(self._on_apply_ovp)
        ovp_row.addWidget(self.ovp_apply_btn)

        self.ovp_indicator = QLabel("—")
        self.ovp_indicator.setToolTip("Over-voltage protection status")
        ovp_row.addWidget(self.ovp_indicator)

        ovp_row.addStretch()
        form.addRow("Over-voltage:", self._wrap(ovp_row))

        # OVP slider, in millivolts like the voltage roller above it.
        self.ovp_slider = QSlider(Qt.Orientation.Horizontal)
        self.ovp_slider.setRange(0, 60000)
        self.ovp_slider.valueChanged.connect(self._on_ovp_slider_changed)
        self.ovp_spin.valueChanged.connect(self._on_ovp_spin_changed)
        form.addRow("", self.ovp_slider)

        # --- Over-current ------------------------------------------------
        ocp_row = QHBoxLayout()
        self.ocp_spin = QDoubleSpinBox()
        self.ocp_spin.setRange(0, 10)
        self.ocp_spin.setDecimals(3)
        self.ocp_spin.setSuffix(" A")
        self.ocp_spin.setSingleStep(0.01)
        ocp_row.addWidget(self.ocp_spin)

        self.ocp_enable = QCheckBox("Arm")
        ocp_row.addWidget(self.ocp_enable)

        self.ocp_apply_btn = QPushButton("Set OCP")
        self.ocp_apply_btn.clicked.connect(self._on_apply_ocp)
        ocp_row.addWidget(self.ocp_apply_btn)

        self.ocp_indicator = QLabel("—")
        self.ocp_indicator.setToolTip("Over-current protection status")
        ocp_row.addWidget(self.ocp_indicator)

        ocp_row.addStretch()
        form.addRow("Over-current:", self._wrap(ocp_row))

        self.ocp_slider = QSlider(Qt.Orientation.Horizontal)
        self.ocp_slider.setRange(0, 10000)  # mA
        self.ocp_slider.valueChanged.connect(self._on_ocp_slider_changed)
        self.ocp_spin.valueChanged.connect(self._on_ocp_spin_changed)
        form.addRow("", self.ocp_slider)

        # A delay is what stops OCP firing on the inrush of a healthy
        # capacitive load every time the output is enabled.
        self.ocp_delay_spin = QDoubleSpinBox()
        self.ocp_delay_spin.setRange(0, 10)
        self.ocp_delay_spin.setDecimals(2)
        self.ocp_delay_spin.setSuffix(" s")
        self.ocp_delay_spin.setSingleStep(0.05)
        self.ocp_delay_spin.setToolTip(
            "Blanks the OCP trip for this long after the output is enabled, "
            "so inrush into a capacitive load does not trip it"
        )
        form.addRow("OCP delay:", self.ocp_delay_spin)

        layout.addLayout(form)

        # --- Trip state --------------------------------------------------
        trip_row = QHBoxLayout()

        self.protection_status_label = QLabel("Protection: not read")
        trip_row.addWidget(self.protection_status_label)

        trip_row.addStretch()

        self.refresh_protection_btn = QPushButton("Refresh")
        self.refresh_protection_btn.clicked.connect(self._on_refresh_protection)
        trip_row.addWidget(self.refresh_protection_btn)

        self.clear_protection_btn = QPushButton("Clear Trip")
        self.clear_protection_btn.setToolTip(
            "A tripped supply stays latched off until the trip is cleared"
        )
        self.clear_protection_btn.clicked.connect(self._on_clear_protection)
        trip_row.addWidget(self.clear_protection_btn)

        layout.addLayout(trip_row)

        group.setLayout(layout)
        self.protection_group = group

        # Nothing is connected yet, so nothing here can be driven.
        self._set_protection_enabled(False)
        return group

    @staticmethod
    def _spawn(coro) -> bool:
        """Schedule a coroutine, tolerating there being no loop yet.

        Button handlers always run under qasync, but `set_equipment` is called
        from ordinary synchronous code that may not. Raising there would take
        out the connection itself over a background refresh, so a missing loop
        just means the read does not happen and the Refresh button is left to
        do it.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            logger.debug("No running event loop; skipping background refresh")
            return False
        asyncio.create_task(coro)
        return True

    @staticmethod
    def _wrap(inner_layout) -> QWidget:
        """Put a layout in a widget so QFormLayout can take it as a field."""
        holder = QWidget()
        holder.setLayout(inner_layout)
        return holder

    def _set_protection_enabled(self, enabled: bool):
        """Enable or disable every protection control as a unit."""
        for control in (
            self.ovp_spin, self.ovp_slider, self.ovp_enable, self.ovp_apply_btn,
            self.ocp_spin, self.ocp_slider, self.ocp_enable, self.ocp_apply_btn,
            self.ocp_delay_spin, self.refresh_protection_btn,
            self.clear_protection_btn,
        ):
            control.setEnabled(enabled)

    def _create_monitor_tab(self) -> QWidget:
        """Create monitoring tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Chart
        self.chart = PowerChartWidget(equipment_type="power_supply", buffer_size=500)
        layout.addWidget(self.chart)

        # Stream control
        stream_layout = QHBoxLayout()

        self.start_monitor_btn = QPushButton("Start Monitoring")
        self.start_monitor_btn.clicked.connect(self._on_start_monitoring)
        self.start_monitor_btn.setEnabled(False)
        stream_layout.addWidget(self.start_monitor_btn)

        self.stop_monitor_btn = QPushButton("Stop Monitoring")
        self.stop_monitor_btn.clicked.connect(self._on_stop_monitoring)
        self.stop_monitor_btn.setEnabled(False)
        stream_layout.addWidget(self.stop_monitor_btn)

        stream_layout.addStretch()

        layout.addLayout(stream_layout)

        return widget

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client

    def set_equipment(self, equipment_id: str, info: dict):
        """Set connected equipment."""
        self.equipment_id = equipment_id

        # Update info
        model = info.get("model", "Unknown")
        manufacturer = info.get("manufacturer", "Unknown")
        self.info_label.setText(
            f"<b>Connected:</b> {manufacturer} {model} ({equipment_id})"
        )

        # Get capabilities
        capabilities = info.get("capabilities", {})
        num_channels = capabilities.get("num_channels", 1)
        max_voltage = capabilities.get("max_voltage", 60)
        max_current = capabilities.get("max_current", 10)

        self.num_channels = num_channels
        self.channel_selector.setMaximum(num_channels)

        # Update ranges
        self.voltage_spin.setMaximum(max_voltage)
        self.voltage_slider.setMaximum(int(max_voltage * 1000))

        self.current_spin.setMaximum(max_current)
        self.current_slider.setMaximum(int(max_current * 1000))

        # A trip ceiling is set above the working point, so the protection
        # rollers share the supply's full range rather than the setpoint's.
        self.ovp_spin.setMaximum(max_voltage)
        self.ovp_slider.setMaximum(int(max_voltage * 1000))
        self.ocp_spin.setMaximum(max_current)
        self.ocp_slider.setMaximum(int(max_current * 1000))

        # Enable controls
        self.apply_btn.setEnabled(True)
        self.start_monitor_btn.setEnabled(True)

        # Only offer protection where the driver implements it. Controls that
        # silently do nothing are worse than controls that are visibly absent,
        # and on a supply this one could be read as a guard that is armed.
        supports_protection = capabilities.get("supports_protection", False)
        self._set_protection_enabled(supports_protection)
        self.protection_note.setVisible(not supports_protection)
        if supports_protection:
            self.protection_status_label.setText("Protection: not read")
            self._spawn(self._refresh_protection_async())
        else:
            self.protection_note.setText(
                f"<i>{manufacturer} {model} does not support remote OVP/OCP "
                f"through LabLink. Set protection from the front panel.</i>"
            )
            self.protection_status_label.setText("Protection: not available")

        self.status_label.setText("Status: Connected")

        logger.info(
            f"Equipment set: {equipment_id}, channels={num_channels}, "
            f"protection={supports_protection}"
        )

    def _on_channel_changed(self, channel: int):
        """Handle channel selection change."""
        logger.info(f"Channel changed: {channel}")
        # Protection is per-channel on a multi-output supply, so what is on
        # screen belongs to the channel that was selected a moment ago.
        if self.client and self.equipment_id and self.ovp_spin.isEnabled():
            self._spawn(self._refresh_protection_async())

    def _on_voltage_changed(self, value: float):
        """Handle voltage spinbox change."""
        self.voltage_slider.blockSignals(True)
        self.voltage_slider.setValue(int(value * 1000))
        self.voltage_slider.blockSignals(False)

    def _on_voltage_slider_changed(self, value: int):
        """Handle voltage slider change."""
        voltage = value / 1000.0
        self.voltage_spin.blockSignals(True)
        self.voltage_spin.setValue(voltage)
        self.voltage_spin.blockSignals(False)

    def _on_current_changed(self, value: float):
        """Handle current spinbox change."""
        self.current_slider.blockSignals(True)
        self.current_slider.setValue(int(value * 1000))
        self.current_slider.blockSignals(False)

    def _on_current_slider_changed(self, value: int):
        """Handle current slider change."""
        current = value / 1000.0
        self.current_spin.blockSignals(True)
        self.current_spin.setValue(current)
        self.current_spin.blockSignals(False)

    # ---- protection ------------------------------------------------------

    def _on_ovp_spin_changed(self, value: float):
        self.ovp_slider.blockSignals(True)
        self.ovp_slider.setValue(int(value * 1000))
        self.ovp_slider.blockSignals(False)

    def _on_ovp_slider_changed(self, value: int):
        self.ovp_spin.blockSignals(True)
        self.ovp_spin.setValue(value / 1000.0)
        self.ovp_spin.blockSignals(False)

    def _on_ocp_spin_changed(self, value: float):
        self.ocp_slider.blockSignals(True)
        self.ocp_slider.setValue(int(value * 1000))
        self.ocp_slider.blockSignals(False)

    def _on_ocp_slider_changed(self, value: int):
        self.ocp_spin.blockSignals(True)
        self.ocp_spin.setValue(value / 1000.0)
        self.ocp_spin.blockSignals(False)

    def _on_apply_ovp(self):
        if not self.client or not self.equipment_id:
            return
        self._spawn(
            self._apply_ovp_async(
                self.ovp_spin.value(),
                self.ovp_enable.isChecked(),
                self.channel_selector.value(),
            )
        )

    async def _apply_ovp_async(self, voltage: float, enabled: bool, channel: int):
        try:
            await call_blocking(
                self.client.send_command,
                self.equipment_id,
                "set_ovp",
                {"voltage": voltage, "enabled": enabled, "channel": channel},
            )
            state = "armed" if enabled else "disarmed"
            self.status_label.setText(f"Status: OVP {state} at {voltage:.3f} V")
            await self._refresh_protection_async()
        except Exception as e:
            self.status_label.setText(f"Status: OVP failed - {e}")
            logger.error(f"Failed to set OVP: {e}")

    def _on_apply_ocp(self):
        if not self.client or not self.equipment_id:
            return
        self._spawn(
            self._apply_ocp_async(
                self.ocp_spin.value(),
                self.ocp_enable.isChecked(),
                self.ocp_delay_spin.value(),
                self.channel_selector.value(),
            )
        )

    async def _apply_ocp_async(
        self, current: float, enabled: bool, delay: float, channel: int
    ):
        try:
            parameters = {
                "current": current, "enabled": enabled, "channel": channel,
            }
            # Zero means "no blanking"; send nothing rather than a 0 s delay,
            # so a model without the delay command is not handed one.
            if delay > 0:
                parameters["delay"] = delay

            await call_blocking(
                self.client.send_command,
                self.equipment_id,
                "set_ocp",
                parameters,
            )
            state = "armed" if enabled else "disarmed"
            self.status_label.setText(f"Status: OCP {state} at {current:.3f} A")
            await self._refresh_protection_async()
        except Exception as e:
            self.status_label.setText(f"Status: OCP failed - {e}")
            logger.error(f"Failed to set OCP: {e}")

    def _on_refresh_protection(self):
        if not self.client or not self.equipment_id:
            return
        self._spawn(self._refresh_protection_async())

    async def _refresh_protection_async(self):
        """Read protection state back and show it."""
        try:
            response = await call_blocking(
                self.client.send_command,
                self.equipment_id,
                "get_protection",
                {"channel": self.channel_selector.value()},
            )
        except Exception as e:
            self.protection_status_label.setText(f"Protection: read failed - {e}")
            logger.error(f"Failed to read protection state: {e}")
            return

        data = (response or {}).get("data") or {}
        self._show_protection(data)

    def _show_protection(self, data: dict):
        """Reflect a protection readback into the controls and indicators.

        Each field is optional: models differ in which protection queries they
        answer. A value that came back as None is left showing "—" rather than
        being rendered as a zero, which would read as a real, armed limit of
        0 V — the most misleading thing this panel could display.
        """
        for level_key, spin, slider, scale in (
            ("ovp_level", self.ovp_spin, self.ovp_slider, 1000),
            ("ocp_level", self.ocp_spin, self.ocp_slider, 1000),
        ):
            level = data.get(level_key)
            if level is None:
                continue
            spin.blockSignals(True)
            slider.blockSignals(True)
            spin.setValue(level)
            slider.setValue(int(level * scale))
            spin.blockSignals(False)
            slider.blockSignals(False)

        for enabled_key, checkbox in (
            ("ovp_enabled", self.ovp_enable),
            ("ocp_enabled", self.ocp_enable),
        ):
            enabled = data.get(enabled_key)
            if enabled is None:
                continue
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(enabled))
            checkbox.blockSignals(False)

        delay = data.get("ocp_delay")
        if delay is not None:
            self.ocp_delay_spin.blockSignals(True)
            self.ocp_delay_spin.setValue(delay)
            self.ocp_delay_spin.blockSignals(False)

        tripped = []
        for trip_key, enabled_key, indicator, name in (
            ("ovp_tripped", "ovp_enabled", self.ovp_indicator, "OVP"),
            ("ocp_tripped", "ocp_enabled", self.ocp_indicator, "OCP"),
        ):
            self._set_indicator(
                indicator, data.get(trip_key), data.get(enabled_key)
            )
            if data.get(trip_key):
                tripped.append(name)

        if tripped:
            self.protection_status_label.setText(
                f"<b>Protection: {' and '.join(tripped)} TRIPPED — "
                f"output is latched off</b>"
            )
            self.protection_status_label.setStyleSheet("color: #C62828;")
        else:
            self.protection_status_label.setText("Protection: no trip")
            self.protection_status_label.setStyleSheet("")

    @staticmethod
    def _set_indicator(label, tripped, enabled):
        """Three states, not two: tripped, armed, and not-known."""
        if tripped:
            label.setText("TRIPPED")
            label.setStyleSheet("color: #C62828; font-weight: bold;")
        elif tripped is None:
            # The model does not answer the trip query. Saying "OK" here would
            # be an assertion nobody checked.
            label.setText("—")
            label.setStyleSheet("color: palette(mid);")
        elif enabled:
            label.setText("armed")
            label.setStyleSheet("color: #2E7D32;")
        else:
            label.setText("off")
            label.setStyleSheet("color: palette(mid);")

    def _on_clear_protection(self):
        if not self.client or not self.equipment_id:
            return
        self._spawn(self._clear_protection_async())

    async def _clear_protection_async(self):
        try:
            await call_blocking(
                self.client.send_command,
                self.equipment_id,
                "clear_protection",
                {"channel": self.channel_selector.value()},
            )
            self.status_label.setText("Status: protection trip cleared")
            await self._refresh_protection_async()
        except Exception as e:
            self.status_label.setText(f"Status: clear failed - {e}")
            logger.error(f"Failed to clear protection: {e}")

    def _on_output_changed(self, state: int):
        """Handle output checkbox change."""
        enabled = state == Qt.CheckState.Checked.value
        logger.info(f"Output changed: {enabled}")

    def _on_apply_settings(self):
        """Apply voltage/current settings."""
        if not self.client or not self.equipment_id:
            return

        voltage = self.voltage_spin.value()
        current = self.current_spin.value()
        channel = self.channel_selector.value()
        output_enabled = self.output_checkbox.isChecked()

        logger.info(
            f"Applying: V={voltage}V, I={current}A, CH={channel}, OUT={output_enabled}"
        )

        self._spawn(
            self._apply_settings_async(voltage, current, channel, output_enabled)
        )

    async def _apply_settings_async(
        self, voltage: float, current: float, channel: int, output_enabled: bool
    ):
        """Apply settings asynchronously."""
        try:
            # LabLinkClient is synchronous, so each call goes through
            # call_blocking: awaiting it directly raises TypeError on the dict
            # it returns, and would freeze the GUI for the round trip if it
            # did not.
            await call_blocking(
                self.client.send_command,
                self.equipment_id,
                "set_voltage",
                {"voltage": voltage, "channel": channel},
            )

            await call_blocking(
                self.client.send_command,
                self.equipment_id,
                "set_current",
                {"current": current, "channel": channel},
            )

            await call_blocking(
                self.client.send_command,
                self.equipment_id,
                "set_output",
                {"enabled": output_enabled, "channel": channel},
            )

            self.status_label.setText("Status: Settings applied")
            logger.info("Settings applied successfully")

        except Exception as e:
            self.status_label.setText(f"Status: Error - {e}")
            logger.error(f"Failed to apply settings: {e}")

    def _on_set_zero(self):
        """Set voltage and current to zero."""
        self.voltage_spin.setValue(0.0)
        self.current_spin.setValue(0.0)
        self.output_checkbox.setChecked(False)

    def _on_start_monitoring(self):
        """Start real-time monitoring."""
        if not self.client or not self.equipment_id:
            return

        # Register handler
        self.client.register_stream_data_handler(self._on_readings_data)

        # Start streaming
        asyncio.create_task(self._start_streaming())

    async def _start_streaming(self):
        """Start streaming (async)."""
        try:
            await self.client.start_equipment_stream(
                equipment_id=self.equipment_id, stream_type="readings", interval_ms=200
            )

            self.streaming = True
            self.start_monitor_btn.setEnabled(False)
            self.stop_monitor_btn.setEnabled(True)

            logger.info("Started monitoring")

        except Exception as e:
            logger.error(f"Failed to start monitoring: {e}")

    def _on_stop_monitoring(self):
        """Stop real-time monitoring."""
        asyncio.create_task(self._stop_streaming())

    async def _stop_streaming(self):
        """Stop streaming (async)."""
        try:
            await self.client.stop_equipment_stream(
                equipment_id=self.equipment_id, stream_type="readings"
            )

            self.streaming = False
            self.start_monitor_btn.setEnabled(True)
            self.stop_monitor_btn.setEnabled(False)

            logger.info("Stopped monitoring")

        except Exception as e:
            logger.error(f"Failed to stop monitoring: {e}")

    def _on_readings_data(self, message: dict):
        """Handle incoming readings data."""
        if message.get("equipment_id") != self.equipment_id:
            return

        if message.get("stream_type") != "readings":
            return

        data = message.get("data", {})

        # Update displays
        voltage = data.get("voltage_actual", 0.0)
        current = data.get("current_actual", 0.0)
        power = voltage * current

        self.voltage_actual_label.setText(f"{voltage:.3f} V")
        self.current_actual_label.setText(f"{current:.3f} A")
        self.power_label.setText(f"{power:.3f} W")

        # Update mode
        in_cv = data.get("in_cv_mode", False)
        in_cc = data.get("in_cc_mode", False)

        if in_cv:
            self.mode_label.setText("Mode: CV (Constant Voltage)")
            self.mode_label.setStyleSheet(
                "font-weight: bold; font-size: 12pt; color: #FF0000;"
            )
        elif in_cc:
            self.mode_label.setText("Mode: CC (Constant Current)")
            self.mode_label.setStyleSheet(
                "font-weight: bold; font-size: 12pt; color: #00FF00;"
            )
        else:
            self.mode_label.setText("Mode: ---")

        # Update chart
        self.chart.update_from_message(message)
