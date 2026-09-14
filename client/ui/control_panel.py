"""Equipment control panel with advanced controls and visualization."""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from typing import Dict, Optional

import qasync
from client.ui.theme import dialog_palette, get_theme_setting
from client.models.equipment import ConnectionStatus, Equipment
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QDial, QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QRadioButton, QSizePolicy,
    QSplitter, QVBoxLayout, QWidget
)
from PyQt6.QtGui import QFont, QFontMetrics, QPalette, QColor, QPainter
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis

from client.api.client import LabLinkClient, call_blocking

logger = logging.getLogger(__name__)


class FittedReadout(QLabel):
    """A readout whose text is sized to fill the box it is given.

    Two things made the digital display unreadable. The obvious one is that it
    was two short bars while the analog and graph modes filled the panel. The
    other is that ``setFont(QFont("Arial", 48))`` never took effect at all: a
    Qt stylesheet beats setFont, and the application sheet sets
    ``QWidget { font-size: 9pt }``, so the readout rendered at 12px while the
    code said 48pt. Anything that sets a size here has to do it through this
    widget's own stylesheet, which is what ``_apply_font_size`` does.

    Sizing on every resize, rather than at one fixed point size, is what makes
    "fills the box" true at more than one window size.
    """

    #: Fraction of the box height one line of digits should occupy.
    HEIGHT_RATIO = 0.62

    #: Never grow past this, or a maximised window turns the reading into
    #: wallpaper and the decimals stop being scannable at a glance.
    MAX_POINT_SIZE = 200

    MIN_POINT_SIZE = 8

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._point_size = None
        self._apply_font_size(self.MIN_POINT_SIZE)

    def _apply_font_size(self, point_size: int):
        if point_size == self._point_size:
            return
        self._point_size = point_size
        # Colours stay with the panel; only the size is this widget's business.
        self.setStyleSheet(
            f"QLabel {{ background-color: transparent; color: #39FF14; "
            f"font-family: Arial; font-weight: bold; "
            f"font-size: {point_size}pt; }}"
        )

    def _fit(self):
        """Largest point size whose text fits the current box, both ways."""
        text = self.text() or "0"
        available_h = max(self.height() - 8, 1)
        available_w = max(self.width() - 16, 1)

        target = int(available_h * self.HEIGHT_RATIO)
        size = max(self.MIN_POINT_SIZE, min(self.MAX_POINT_SIZE, target))

        # Point size sets the line height; the string still has to fit across.
        # Shrink until it does rather than letting Qt elide or clip it.
        while size > self.MIN_POINT_SIZE:
            font = QFont("Arial", size, QFont.Weight.Bold)
            if QFontMetrics(font).horizontalAdvance(text) <= available_w:
                break
            size -= 1

        self._apply_font_size(size)

    def setText(self, text):
        super().setText(text)
        self._fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class ChartWithReadouts(QChartView):
    """A chart view carrying a live voltage and current reading across its top.

    The numbers are children of the view rather than a row above it, so they
    sit on the chart's own face where the reading belongs -- next to the trace
    it describes, not on the panel behind it. Qt lays out children only when
    something asks it to, so the positions are recomputed on every resize.
    """

    #: Horizontal placement, as a fraction of the view's width. A quarter in
    #: from each edge keeps both clear of the chart title in the middle.
    LEFT_FRACTION = 0.25
    RIGHT_FRACTION = 0.75

    #: Down from the top, as a fraction of height -- level with the title.
    TOP_FRACTION = 0.07

    #: Point size when there is room for it, and the floor when there is not.
    #: A reading is never elided to fit: half a number looks like a whole one
    #: and would be misread, so the text shrinks instead.
    POINT_SIZE = 16
    MIN_POINT_SIZE = 7

    def __init__(self, chart, parent=None):
        super().__init__(chart, parent)

        self.voltage_readout = QLabel("Volts: 0.000", self)
        self.current_readout = QLabel("Amps: 0.000", self)

        _c = dialog_palette()
        for readout, colour in (
            # Close to the series colours, so each number reads as belonging
            # to its trace, but chosen against the card the chart theme paints
            # rather than copied from the line: the series blue sits at 4.3:1
            # on the dark card, which is below what is comfortably readable.
            (self.voltage_readout, _c["chart_voltage"]),
            (self.current_readout, _c["chart_current"]),
        ):
            readout.setProperty("colour", colour)
            self._set_point_size(readout, self.POINT_SIZE)
            readout.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            readout.adjustSize()

    def _set_point_size(self, readout, point_size):
        if readout.property("pointSize") == point_size:
            return
        readout.setProperty("pointSize", point_size)
        colour = readout.property("colour")
        readout.setStyleSheet(
            f"QLabel {{ background-color: transparent; color: {colour}; "
            f"font-family: Arial; font-weight: bold; "
            f"font-size: {point_size}pt; }}"
        )

    def _fit(self, readout):
        """Shrink until the reading fits its half of the view."""
        available = max(self.width() // 2 - 16, 1)
        size = self.POINT_SIZE
        while size > self.MIN_POINT_SIZE:
            self._set_point_size(readout, size)
            readout.adjustSize()
            if readout.width() <= available:
                break
            size -= 1
        else:
            self._set_point_size(readout, self.MIN_POINT_SIZE)
            readout.adjustSize()

    def _place(self):
        top = int(self.height() * self.TOP_FRACTION)

        for readout, fraction in (
            (self.voltage_readout, self.LEFT_FRACTION),
            (self.current_readout, self.RIGHT_FRACTION),
        ):
            self._fit(readout)
            # Centred on the fraction, then clamped so a long reading cannot
            # slide off either edge of the view.
            x = int(self.width() * fraction) - readout.width() // 2
            x = max(4, min(x, self.width() - readout.width() - 4))
            readout.move(x, top)
            readout.raise_()

    def set_readings(self, voltage: float, current: float,
                     voltage_decimals: int = 3, current_decimals: int = 3):
        self.voltage_readout.setText(f"Volts: {voltage:.{voltage_decimals}f}")
        self.current_readout.setText(f"Amps: {current:.{current_decimals}f}")
        self._place()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place()


class AnalogGauge(QWidget):
    """Custom analog gauge widget for voltage/current display."""

    def __init__(self, title="", min_value=0, max_value=100, unit="", parent=None):
        """Initialize analog gauge.

        Args:
            title: Gauge title
            min_value: Minimum value
            max_value: Maximum value
            unit: Unit of measurement
            parent: Parent widget
        """
        super().__init__(parent)
        self.title = title
        self.min_value = min_value
        self.max_value = max_value
        self.unit = unit
        self.current_value = 0.0

        self.setMinimumSize(200, 200)

    def set_value(self, value: float):
        """Set the current value and update display."""
        self.current_value = max(self.min_value, min(self.max_value, value))
        self.update()

    def paintEvent(self, event):
        """Paint the gauge."""
        from PyQt6.QtGui import QPainter, QPen, QBrush, QConicalGradient
        from PyQt6.QtCore import QPointF, QRectF
        import math

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get dimensions
        width = self.width()
        height = self.height()
        size = min(width, height) - 20
        center_x = width / 2
        center_y = height / 2

        # Draw gauge background
        painter.setPen(QPen(Qt.GlobalColor.gray, 2))
        painter.setBrush(QBrush(Qt.GlobalColor.lightGray))
        painter.drawEllipse(QPointF(center_x, center_y), size / 2, size / 2)

        # Draw tick marks (short radial lines at each graduation)
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        tick_inner_radius = size / 2 - 20
        tick_outer_radius = size / 2 - 10
        for i in range(11):
            angle = 225 - (i * 27)  # 270 degrees range
            rad = math.radians(angle)
            x1 = center_x + tick_inner_radius * math.cos(rad)
            y1 = center_y - tick_inner_radius * math.sin(rad)
            x2 = center_x + tick_outer_radius * math.cos(rad)
            y2 = center_y - tick_outer_radius * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Draw value labels (variable radius: outer at top, inner at bottom edges)
        painter.setFont(QFont("Arial", 8))
        base_radius = size / 2 - 8  # Perfect at 12 o'clock
        for i in range(11):
            value = self.min_value + (self.max_value - self.min_value) * i / 10
            angle = 225 - (i * 27)
            rad = math.radians(angle)

            # Vary radius: full at top (90°), reduced at bottom edges (225° and -45°)
            # Distance from top: 0 at 90°, max at 225° and -45°
            angle_from_top = abs(angle - 90)
            radius_reduction = (angle_from_top / 135) * 30  # Reduce up to 30px at extremes
            label_radius = base_radius - radius_reduction

            x = center_x + label_radius * math.cos(rad)
            y = center_y - label_radius * math.sin(rad)
            painter.drawText(int(x - 15), int(y + 5), 30, 20, Qt.AlignmentFlag.AlignCenter, f"{value:.1f}")

        # Draw needle
        value_ratio = (self.current_value - self.min_value) / (self.max_value - self.min_value)
        needle_angle = 225 - (value_ratio * 270)
        rad = math.radians(needle_angle)
        needle_length = size / 2 - 40

        painter.setPen(QPen(Qt.GlobalColor.red, 3))
        x_end = center_x + needle_length * math.cos(rad)
        y_end = center_y - needle_length * math.sin(rad)
        painter.drawLine(int(center_x), int(center_y), int(x_end), int(y_end))

        # Draw center dot
        painter.setBrush(QBrush(Qt.GlobalColor.red))
        painter.drawEllipse(QPointF(center_x, center_y), 5, 5)

        # Draw unit label at top center (like a real power supply meter)
        painter.setPen(QPen(Qt.GlobalColor.black))
        painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        painter.drawText(0, int(center_y - size / 2 + 30), width, 30, Qt.AlignmentFlag.AlignCenter, self.unit)

        # Draw title below the unit
        painter.setFont(QFont("Arial", 10))
        painter.drawText(0, int(center_y - size / 2 + 55), width, 20, Qt.AlignmentFlag.AlignCenter, self.title)

        # Draw current value in the center
        painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        value_text = f"{self.current_value:.2f}"
        painter.drawText(0, int(center_y - 10), width, 30, Qt.AlignmentFlag.AlignCenter, value_text)

        # Draw "LabLink" branding at bottom (subtle)
        painter.setPen(QPen(QColor(100, 100, 100)))  # Gray color for subtlety
        painter.setFont(QFont("Arial", 8, QFont.Weight.Normal))
        painter.drawText(0, int(center_y + size / 2 - 20), width, 20, Qt.AlignmentFlag.AlignCenter, "LabLink")


class ControlPanel(QWidget):
    """Advanced equipment control panel with visualization."""

    equipment_selected = pyqtSignal(str)
    # Something the user needs told about, shown in the main window's status
    # bar. Currently: control of an instrument passing to somebody else.
    status_message = pyqtSignal(str)

    def __init__(self, client: Optional[LabLinkClient] = None, parent=None):
        """Initialize control panel.

        Args:
            client: LabLink API client
            parent: Parent widget
        """
        super().__init__(parent)
        self.client = client
        self.selected_equipment: Optional[Equipment] = None

        # How many places the selected instrument's readings actually resolve
        # to. A supply that sends hundredths printed as 0.300 A claims a digit
        # it never sent. The server reports this per model; these are the
        # fallbacks for one too old to say.
        self.instrument_max_voltage = 60.0
        self.instrument_max_current = 5.0

        # Min/max tracking, reset by the button rather than by a reading.
        self._extremes = {"v_min": None, "v_max": None,
                          "i_min": None, "i_max": None}

        self.voltage_decimals = 2
        self.current_decimals = 3
        self.equipment_list: List[Equipment] = []

        # Data storage for graphs
        self.voltage_data = deque(maxlen=100)
        self.current_data = deque(maxlen=100)
        self.time_data = deque(maxlen=100)

        # Track last command time to prevent reading updates from overwriting user actions
        self._last_output_command_time = 0
        self._readings_in_flight = False

        # Timer for reading updates (single timer to prevent serial port overload)
        self.readings_timer = QTimer()
        self.readings_timer.timeout.connect(self._update_readings)

        # Lock state changes without us doing anything: it counts down, someone
        # else can take or release it, and it can expire. Polled slowly -- this
        # is a server-side query, not a serial one, and the countdown only needs
        # to look alive.
        self.lock_timer = QTimer()
        self.lock_timer.timeout.connect(self._poll_lock_status)
        self._lock_poll_in_flight = False
        self._had_control = False

        self._setup_ui()

    def _setup_ui(self):
        """Set up the user interface."""
        main_layout = QHBoxLayout(self)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - Equipment list
        left_panel = self._create_equipment_list_panel()
        splitter.addWidget(left_panel)

        # Right panel - Controls and displays
        right_panel = self._create_control_panel()
        splitter.addWidget(right_panel)

        # Set initial sizes (20% left, 80% right)
        splitter.setSizes([200, 800])

        main_layout.addWidget(splitter)

    def _create_equipment_list_panel(self) -> QWidget:
        """Create the equipment list panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Title
        title = QLabel("<h3>Connected Equipment</h3>")
        layout.addWidget(title)

        # Equipment list
        self.equipment_list_widget = QListWidget()
        self.equipment_list_widget.itemClicked.connect(self._on_equipment_selected)
        layout.addWidget(self.equipment_list_widget)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_equipment_list)
        layout.addWidget(refresh_btn)

        return panel

    def _create_control_panel(self) -> QWidget:
        """Create the main control panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Equipment info
        self.equipment_info_label = QLabel("No equipment selected")
        self.equipment_info_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.equipment_info_label)

        # Who holds this instrument. Always on screen, because "why will it not
        # let me set anything" is otherwise unanswerable from the interface.
        from client.ui.equipment_lock_dialog import LockStatusWidget

        lock_row = QHBoxLayout()
        self.lock_status_widget = LockStatusWidget()
        lock_row.addWidget(self.lock_status_widget)
        lock_row.addStretch()
        self.manage_lock_button = QPushButton("Manage lock…")
        self.manage_lock_button.clicked.connect(self._show_lock_dialog)
        self.manage_lock_button.setEnabled(False)
        lock_row.addWidget(self.manage_lock_button)
        layout.addLayout(lock_row)

        # Control section
        control_group = self._create_control_section()
        layout.addWidget(control_group)

        # Display mode selection
        display_mode_group = self._create_display_mode_section()
        layout.addWidget(display_mode_group)

        # Display area
        self.display_stack = QWidget()
        self.display_layout = QVBoxLayout(self.display_stack)

        # Create display modes
        self.digital_display = self._create_digital_display()
        self.analog_display = self._create_analog_display()
        self.graph_display = self._create_graph_display()

        # Add to stack (only one visible at a time)
        self.display_layout.addWidget(self.digital_display)
        self.display_layout.addWidget(self.analog_display)
        self.display_layout.addWidget(self.graph_display)

        # Initially show digital
        self.analog_display.hide()
        self.graph_display.hide()

        # One row of tools under the stack: only one display is visible at a
        # time, so these serve digital, analog and graph alike.
        self.display_layout.addWidget(self._create_display_tools())

        layout.addWidget(self.display_stack)

        return panel

    def _create_control_section(self) -> QGroupBox:
        """Create the control section with knobs and inputs."""
        group = QGroupBox("Controls")
        layout = QVBoxLayout(group)

        # Top row: Voltage and Current controls
        controls_layout = QHBoxLayout()

        # Voltage control
        voltage_group = QGroupBox("Voltage Control")
        voltage_layout = QVBoxLayout(voltage_group)

        # Voltage knob
        self.voltage_dial = QDial()
        self.voltage_dial.setMinimum(0)
        self.voltage_dial.setMaximum(600)  # 60.0V * 10
        self.voltage_dial.setValue(0)
        self.voltage_dial.setNotchesVisible(True)
        self.voltage_dial.valueChanged.connect(self._on_voltage_dial_changed)
        self.voltage_dial.setWrapping(False)
        voltage_layout.addWidget(self.voltage_dial)

        # Voltage numeric input
        voltage_input_layout = QHBoxLayout()
        voltage_input_layout.addWidget(QLabel("Voltage (V):"))
        self.voltage_spinbox = QDoubleSpinBox()
        self.voltage_spinbox.setMinimum(0.0)
        self.voltage_spinbox.setMaximum(60.0)
        self.voltage_spinbox.setValue(0.0)
        self.voltage_spinbox.setDecimals(2)
        self.voltage_spinbox.setSingleStep(0.1)
        self.voltage_spinbox.valueChanged.connect(self._on_voltage_spinbox_changed)
        voltage_input_layout.addWidget(self.voltage_spinbox)
        voltage_layout.addLayout(voltage_input_layout)

        controls_layout.addWidget(voltage_group)

        # Current control
        current_group = QGroupBox("Current Control")
        current_layout = QVBoxLayout(current_group)

        # Current knob
        self.current_dial = QDial()
        self.current_dial.setMinimum(0)
        self.current_dial.setMaximum(160)  # 16.0A * 10
        self.current_dial.setValue(0)
        self.current_dial.setNotchesVisible(True)
        self.current_dial.valueChanged.connect(self._on_current_dial_changed)
        self.current_dial.setWrapping(False)
        current_layout.addWidget(self.current_dial)

        # Current numeric input
        current_input_layout = QHBoxLayout()
        current_input_layout.addWidget(QLabel("Current (A):"))
        self.current_spinbox = QDoubleSpinBox()
        self.current_spinbox.setMinimum(0.0)
        self.current_spinbox.setMaximum(16.0)
        self.current_spinbox.setValue(0.0)
        self.current_spinbox.setDecimals(2)
        self.current_spinbox.setSingleStep(0.1)
        self.current_spinbox.valueChanged.connect(self._on_current_spinbox_changed)
        current_input_layout.addWidget(self.current_spinbox)
        current_layout.addLayout(current_input_layout)

        controls_layout.addWidget(current_group)

        layout.addLayout(controls_layout)

        # Bottom row: Output control and mode indicators
        bottom_layout = QHBoxLayout()

        # Output control
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)

        self.output_button = QPushButton("Output: OFF")
        self.output_button.setCheckable(True)
        self.output_button.setStyleSheet("QPushButton:checked { background-color: green; color: white; }")
        self.output_button.clicked.connect(self._on_output_toggled)
        output_layout.addWidget(self.output_button)

        bottom_layout.addWidget(output_group)

        # Mode indicators
        mode_group = QGroupBox("Operating Mode")
        mode_layout = QVBoxLayout(mode_group)

        self.cv_indicator = QLabel("CV: OFF")
        self.cv_indicator.setStyleSheet("QLabel { background-color: gray; color: white; padding: 5px; }")
        mode_layout.addWidget(self.cv_indicator)

        self.cc_indicator = QLabel("CC: OFF")
        self.cc_indicator.setStyleSheet("QLabel { background-color: gray; color: white; padding: 5px; }")
        mode_layout.addWidget(self.cc_indicator)

        bottom_layout.addWidget(mode_group)

        # Refresh rate controls
        refresh_group = QGroupBox("Refresh Rate")
        refresh_layout = QHBoxLayout(refresh_group)

        # Single refresh rate control for all readings
        refresh_layout.addWidget(QLabel("Update Rate (Hz):"))
        self.refresh_spinbox = QDoubleSpinBox()
        self.refresh_spinbox.setMinimum(0.1)
        self.refresh_spinbox.setMaximum(10.0)
        try:
            from client.utils.settings import SettingsManager

            self.refresh_spinbox.setValue(SettingsManager().get_reading_rate(1.0))
        except Exception:
            self.refresh_spinbox.setValue(1.0)
        self.refresh_spinbox.setDecimals(1)
        self.refresh_spinbox.setSingleStep(0.1)
        self.refresh_spinbox.setToolTip("How often to query voltage and current readings from the equipment")
        self.refresh_spinbox.valueChanged.connect(self._on_refresh_changed)
        refresh_layout.addWidget(self.refresh_spinbox)

        bottom_layout.addWidget(refresh_group)

        layout.addLayout(bottom_layout)

        return group

    def _create_display_mode_section(self) -> QGroupBox:
        """Create display mode selection."""
        group = QGroupBox("Display Mode")
        layout = QHBoxLayout(group)

        self.display_mode_group = QButtonGroup()

        self.digital_radio = QRadioButton("Digital")
        self.digital_radio.setChecked(True)
        self.digital_radio.toggled.connect(lambda: self._on_display_mode_changed("digital"))
        self.display_mode_group.addButton(self.digital_radio)
        layout.addWidget(self.digital_radio)

        self.analog_radio = QRadioButton("Analog")
        self.analog_radio.toggled.connect(lambda: self._on_display_mode_changed("analog"))
        self.display_mode_group.addButton(self.analog_radio)
        layout.addWidget(self.analog_radio)

        self.graph_radio = QRadioButton("Graph")
        self.graph_radio.toggled.connect(lambda: self._on_display_mode_changed("graph"))
        self.display_mode_group.addButton(self.graph_radio)
        layout.addWidget(self.graph_radio)

        return group

    def _create_display_tools(self) -> QWidget:
        """Min/max tracking and auto-ranging, shared by all three displays."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 4, 0, 0)

        self.minmax_button = QPushButton("Min/Max")
        self.minmax_button.setCheckable(True)
        self.minmax_button.setToolTip(
            "Track the highest and lowest readings seen.\n"
            "Useful for catching a transient that the live number misses."
        )
        self.minmax_button.toggled.connect(self._on_minmax_toggled)
        row.addWidget(self.minmax_button)

        self.minmax_label = QLabel("")
        self.minmax_label.setToolTip("Lowest and highest reading since tracking began")
        row.addWidget(self.minmax_label, 1)

        self.minmax_reset_button = QPushButton("Reset")
        self.minmax_reset_button.setToolTip("Start tracking again from the next reading")
        self.minmax_reset_button.clicked.connect(self._reset_extremes)
        self.minmax_reset_button.setEnabled(False)
        row.addWidget(self.minmax_reset_button)

        self.autorange_button = QPushButton("Auto Range")
        self.autorange_button.setCheckable(True)
        self.autorange_button.setToolTip(
            "Scale the gauges and the graph to the readings actually seen.\n"
            "A 5 A supply sitting at 0.3 A uses a sixteenth of the dial "
            "otherwise, and small changes are invisible."
        )
        self.autorange_button.toggled.connect(self._on_autorange_toggled)
        row.addWidget(self.autorange_button)

        return widget

    # ==================== Min/max and auto-range ====================

    def _reset_extremes(self):
        """Forget what has been seen and start again."""
        self._extremes = {"v_min": None, "v_max": None,
                          "i_min": None, "i_max": None}
        self._update_minmax_label()

    def _on_minmax_toggled(self, enabled: bool):
        self.minmax_reset_button.setEnabled(enabled)
        if enabled:
            self._reset_extremes()
        else:
            self.minmax_label.setText("")

    def _on_autorange_toggled(self, enabled: bool):
        if not enabled:
            # Back to what the instrument can actually do, so the dial means
            # the same thing again.
            self.voltage_gauge.max_value = self.instrument_max_voltage
            self.current_gauge.max_value = self.instrument_max_current
            self.axis_y_voltage.setRange(0, self.instrument_max_voltage)
            self.axis_y_current.setRange(0, self.instrument_max_current)
            self.voltage_gauge.update()
            self.current_gauge.update()
        else:
            self._apply_auto_range()

    def _track_extremes(self, voltage: float, current: float):
        """Record the highest and lowest readings seen."""
        if not self.minmax_button.isChecked():
            return

        for key, value in (("v", voltage), ("i", current)):
            low, high = self._extremes[f"{key}_min"], self._extremes[f"{key}_max"]
            self._extremes[f"{key}_min"] = value if low is None else min(low, value)
            self._extremes[f"{key}_max"] = value if high is None else max(high, value)

        self._update_minmax_label()

    def _update_minmax_label(self):
        """Show the extremes to the resolution the instrument reports."""
        extremes = self._extremes
        v_min = extremes["v_min"]
        if v_min is None:
            self.minmax_label.setText("waiting for a reading...")
            return

        v_max = extremes["v_max"]
        i_min = extremes["i_min"]
        i_max = extremes["i_max"]
        vd = self.voltage_decimals
        cd = self.current_decimals
        self.minmax_label.setText(
            f"V  {v_min:.{vd}f} / {v_max:.{vd}f}       "
            f"A  {i_min:.{cd}f} / {i_max:.{cd}f}"
        )

    def _apply_auto_range(self):
        """Scale the gauges and graph to the readings actually seen.

        A 5 A supply sitting at 0.3 A uses a sixteenth of the dial, and a
        change of 10 mA moves the needle by a pixel. Ranging to the data is
        what makes the analog and graph modes worth looking at.

        Headroom above the maximum, so a rising reading does not immediately
        peg; a floor, so a reading near zero does not produce a meaningless
        scale; and never beyond what the instrument can do.
        """
        if not self.autorange_button.isChecked():
            return

        seen_v = self._extremes["v_max"]
        seen_i = self._extremes["i_max"]
        # Fall back to the live readings when min/max tracking is off, so the
        # two buttons are independent.
        if seen_v is None:
            seen_v = self.voltage_gauge.current_value
        if seen_i is None:
            seen_i = self.current_gauge.current_value

        v_range = self._nice_range(seen_v, self.instrument_max_voltage, floor=1.0)
        i_range = self._nice_range(seen_i, self.instrument_max_current, floor=0.1)

        self.voltage_gauge.max_value = v_range
        self.current_gauge.max_value = i_range
        self.axis_y_voltage.setRange(0, v_range)
        self.axis_y_current.setRange(0, i_range)
        self.voltage_gauge.update()
        self.current_gauge.update()

    @staticmethod
    def _nice_range(seen: float, instrument_max: float, floor: float) -> float:
        """A round-ish top of scale a little above `seen`."""
        import math

        target = max(abs(seen) * 1.25, floor)
        if target >= instrument_max:
            return instrument_max

        # Round up to a readable multiple of a power of ten, so the gauge's
        # ten divisions land on sensible numbers rather than 3.7 volts each.
        # Finer than the usual 1/2/5 because the point here is resolution: on
        # 1/2/5 a 5 V reading jumps to a 10 V scale and gains almost nothing.
        exponent = math.floor(math.log10(target))
        base = 10 ** exponent
        for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
            if target <= step * base:
                return min(step * base, instrument_max)
        return instrument_max

    def _create_digital_display(self) -> QWidget:
        """Create digital display mode.

        One panel with the two readings side by side, filling the same space
        the analog gauges and the graph get. It was two short bars stacked in
        a tall panel, so the digital mode used a fraction of the room the other
        two modes used, and the numbers were small in an otherwise empty box.
        """
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QWidget()
        panel.setObjectName("digitalPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # The black ground belongs to the panel, so the two readouts sit on one
        # continuous face rather than as two boxes with a seam between them.
        panel.setStyleSheet(
            "QWidget#digitalPanel { background-color: black; border-radius: 6px; }"
            # Inset from the top and bottom so the rule reads as a separator
            # between the two readings rather than as a border cutting the
            # panel into halves.
            "QWidget#digitalDivider { background-color: #3f4a3f; margin: 16px 0; }"
        )

        readings = QHBoxLayout(panel)
        readings.setContentsMargins(12, 12, 12, 12)
        readings.setSpacing(12)

        self.voltage_display = FittedReadout("0.000 V")
        readings.addWidget(self.voltage_display, 1)

        # A plain widget rather than a QFrame VLine: a frame draws itself from
        # the palette, which the dark sheet supplies, and the result is all
        # but invisible on black. A background colour is under our control.
        self.digital_divider = QWidget()
        self.digital_divider.setObjectName("digitalDivider")
        self.digital_divider.setFixedWidth(8)
        self.digital_divider.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        readings.addWidget(self.digital_divider)

        self.current_display = FittedReadout("0.000 A")
        readings.addWidget(self.current_display, 1)

        outer.addWidget(panel)
        return widget

    def _create_analog_display(self) -> QWidget:
        """Create analog gauge display mode."""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        self.voltage_gauge = AnalogGauge("Voltage", 0, 60, "V")
        layout.addWidget(self.voltage_gauge)

        self.current_gauge = AnalogGauge("Current", 0, 16, "A")
        layout.addWidget(self.current_gauge)

        return widget

    def _create_graph_display(self) -> QWidget:
        """Create graph display mode."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Create chart
        self.chart = QChart()
        self.chart.setTitle("Voltage and Current vs Time")
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        # QChart defaults to a white card, which sat as a bright rectangle in
        # the middle of the dark application. Its built-in dark theme colours
        # the plot area, the gridlines and the legend together; the title and
        # axis text it does not reach, so those are set from the palette.
        self.chart.setTheme(
            QChart.ChartTheme.ChartThemeDark if get_theme_setting() == "dark"
            else QChart.ChartTheme.ChartThemeLight
        )

        # Create series
        self.voltage_series = QLineSeries()
        self.voltage_series.setName("Voltage (V)")
        self.chart.addSeries(self.voltage_series)

        self.current_series = QLineSeries()
        self.current_series.setName("Current (A)")
        self.chart.addSeries(self.current_series)

        # Create axes
        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Time (s)")
        self.axis_x.setRange(0, 100)
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)

        self.axis_y_voltage = QValueAxis()
        self.axis_y_voltage.setTitleText("Voltage (V)")
        self.axis_y_voltage.setRange(0, 60)
        self.chart.addAxis(self.axis_y_voltage, Qt.AlignmentFlag.AlignLeft)

        self.axis_y_current = QValueAxis()
        self.axis_y_current.setTitleText("Current (A)")
        self.axis_y_current.setRange(0, 16)
        self.chart.addAxis(self.axis_y_current, Qt.AlignmentFlag.AlignRight)

        # The theme leaves the title and the axis labels at their default
        # colour, which is near-black and unreadable on the dark card.
        _c = dialog_palette()
        self.chart.setTitleBrush(QColor(_c["text"]))
        if self.chart.legend():
            self.chart.legend().setLabelColor(QColor(_c["text"]))
        for axis in (self.axis_x, self.axis_y_voltage, self.axis_y_current):
            axis.setLabelsColor(QColor(_c["text"]))
            axis.setTitleBrush(QColor(_c["text"]))

        # Attach series to axes
        self.voltage_series.attachAxis(self.axis_x)
        self.voltage_series.attachAxis(self.axis_y_voltage)
        self.current_series.attachAxis(self.axis_x)
        self.current_series.attachAxis(self.axis_y_current)

        # Create chart view, with the live readings across its top
        self.chart_view = ChartWithReadouts(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.chart_view)

        # Add clear button at bottom right
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        clear_button = QPushButton("Clear Graph")
        clear_button.setMaximumWidth(120)
        clear_button.clicked.connect(self._clear_graph)
        button_layout.addWidget(clear_button)
        layout.addLayout(button_layout)

        return widget

    def _set_controls_enabled(self, enabled: bool):
        """Enable or disable the controls that send commands.

        Readings stay live either way: not holding the lock means you cannot
        change the instrument, not that you cannot watch it.
        """
        for name in ("voltage_dial", "voltage_spinbox", "current_dial",
                     "current_spinbox", "output_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setEnabled(enabled)

    def _apply_lock_status(self, status: Optional[dict]):
        """Render a lock status and gate the controls to match."""
        if status is None:
            self.lock_status_widget.update_status(None)
            self.manage_lock_button.setEnabled(False)
            self._had_control = False
            return

        mine = bool(self.client) and self.client.holds_lock(status)
        self.lock_status_widget.update_status(status, is_mine=mine)
        self.manage_lock_button.setEnabled(True)
        self._set_controls_enabled(mine)

        # Say so when control is taken away mid-session. Controls greying out
        # with no explanation is the thing this feature exists to stop, and
        # losing a lock to an override or an expiry is exactly when it happens.
        if self._had_control and not mine:
            from client.ui.equipment_lock_dialog import describe_holder

            holder = (describe_holder(status) if status.get("locked")
                      else "no one - it expired")
            self.status_message.emit(
                f"Control of this instrument has passed to {holder}"
            )
            logger.warning(f"Lost the lock on the selected equipment to {holder}")
        self._had_control = mine

    @qasync.asyncSlot()
    async def _poll_lock_status(self):
        """Re-read the lock off the GUI thread."""
        if not (self.client and self.selected_equipment):
            return
        if self._lock_poll_in_flight:
            return
        self._lock_poll_in_flight = True
        try:
            status = await call_blocking(
                self.client.get_lock_status, self.selected_equipment.equipment_id
            )
            self._apply_lock_status(status)
        except Exception as exc:
            logger.debug(f"Could not read lock status: {exc}")
        finally:
            self._lock_poll_in_flight = False

    def _refresh_lock_status(self):
        """Ask for a lock refresh now, without blocking the caller."""
        if not (self.client and self.selected_equipment):
            self._apply_lock_status(None)
            return
        self._poll_lock_status()

    def _show_lock_dialog(self):
        """Open the take/release/override dialog for the selected equipment."""
        if not (self.client and self.selected_equipment):
            return
        from client.ui.equipment_lock_dialog import EquipmentLockDialog

        dialog = EquipmentLockDialog(
            self.client,
            self.selected_equipment.equipment_id,
            getattr(self.selected_equipment, "name", ""),
            self,
        )
        dialog.exec()

        # The dialog may have taken or given up control.
        self._refresh_lock_status()
        try:
            status = self.client.get_lock_status(
                self.selected_equipment.equipment_id
            )
            self._set_controls_enabled(self.client.holds_lock(status))
        except Exception:
            pass

    def _on_equipment_selected(self):
        """Handle equipment selection."""
        selected_items = self.equipment_list_widget.selectedItems()
        if not selected_items:
            # Release lock on previously selected equipment
            if self.selected_equipment and self.client:
                try:
                    self.client.release_lock(self.selected_equipment.equipment_id)
                    logger.info(f"Released lock on {self.selected_equipment.equipment_id}")
                except Exception as e:
                    logger.error(f"Error releasing lock: {e}")
            self.selected_equipment = None
            self._stop_data_acquisition()
            # Clear the strip too, or it keeps naming a lock on equipment that
            # is no longer selected.
            self._apply_lock_status(None)
            return

        equipment_id = selected_items[0].data(Qt.ItemDataRole.UserRole)

        # Release lock on previously selected equipment
        if self.selected_equipment and self.selected_equipment.equipment_id != equipment_id and self.client:
            try:
                self.client.release_lock(self.selected_equipment.equipment_id)
                logger.info(f"Released lock on {self.selected_equipment.equipment_id}")
            except Exception as e:
                logger.error(f"Error releasing lock: {e}")

        # Find equipment in list
        for equipment in self.equipment_list:
            if equipment.equipment_id == equipment_id:
                self.selected_equipment = equipment
                self.equipment_info_label.setText(
                    f"{equipment.name} - {equipment.manufacturer} {equipment.model}"
                )

                # Take the lock for control, without taking it from anyone.
                #
                # This used to force-release whatever it found first and then
                # acquire, so selecting equipment silently stole control from
                # whoever had it -- which made the lock meaningless in the GUI
                # and unattributable when it mattered. Overriding is now a
                # deliberate act in the lock dialog, with the holder named.
                if self.client:
                    try:
                        status = self.client.get_lock_status(equipment_id)
                    except Exception as e:
                        logger.error(f"Could not read lock status: {e}")
                        status = {}

                    if status.get("locked") and not self.client.holds_lock(status):
                        from client.ui.equipment_lock_dialog import describe_holder

                        holder = describe_holder(status)
                        logger.info(
                            f"{equipment_id} is locked by {holder}; read-only"
                        )
                        self._set_controls_enabled(False)
                    else:
                        try:
                            self.client.acquire_lock(
                                equipment_id, lock_mode="exclusive"
                            )
                            logger.info(f"Acquired exclusive lock on {equipment_id}")
                            self._set_controls_enabled(True)
                        except Exception as e:
                            logger.error(f"Error acquiring lock: {e}")
                            self._set_controls_enabled(False)

                    self._refresh_lock_status()

                # Get equipment status to configure controls based on capabilities
                try:
                    status = self.client.get_equipment_status(equipment_id)
                    capabilities = status.get("capabilities", {})
                    max_voltage = capabilities.get("max_voltage", 60.0)
                    max_current = capabilities.get("max_current", 5.0)
                    # Kept so auto-range has something to go back to.
                    self.instrument_max_voltage = max_voltage
                    self.instrument_max_current = max_current
                    self.voltage_decimals = capabilities.get("voltage_decimals", 2)
                    self.current_decimals = capabilities.get("current_decimals", 3)

                    # Re-range the controls without commanding the instrument.
                    #
                    # setMaximum() clamps a value that no longer fits, and Qt
                    # emits valueChanged for that clamp. Those signals are
                    # wired to _send_voltage_command / _send_current_command,
                    # so lowering a ceiling on a device switch used to command
                    # the instrument that had just been selected: picking the
                    # 5 A 1685B after the 25 A 9205B clamped the carried-over
                    # setpoint to 5.0 and sent it as set_current -- the
                    # 1685B's full scale, from a value the user never typed.
                    # Block the widgets across the whole re-range, then show
                    # what the instrument itself reports.
                    ranged_widgets = (
                        self.voltage_dial,
                        self.voltage_spinbox,
                        self.current_dial,
                        self.current_spinbox,
                    )
                    for widget in ranged_widgets:
                        widget.blockSignals(True)
                    try:
                        # Update voltage controls
                        self.voltage_dial.setMaximum(int(max_voltage * 10))
                        self.voltage_spinbox.setMaximum(max_voltage)
                        self.voltage_gauge.max_value = max_voltage

                        # Update current controls
                        self.current_dial.setMaximum(int(max_current * 10))
                        self.current_spinbox.setMaximum(max_current)
                        self.current_gauge.max_value = max_current

                        self._show_setpoints(equipment_id)
                    finally:
                        for widget in ranged_widgets:
                            widget.blockSignals(False)

                    logger.info(f"Configured controls for {equipment.name}: "
                                f"max_voltage={max_voltage}V, max_current={max_current}A")
                except Exception as e:
                    logger.error(f"Error configuring controls from capabilities: {e}")
                    # Use defaults if status fetch fails
                    pass

                self.equipment_selected.emit(equipment_id)
                # Start reading data
                self._start_data_acquisition()
                break

    def _show_setpoints(self, equipment_id: str):
        """Show the instrument's own setpoints on the controls.

        Called with the range widgets' signals already blocked. Without it the
        panel keeps whatever the previously selected instrument was set to,
        clamped into the new one's range, which reads like a measurement from
        the new instrument but is not one.
        """
        if not self.client:
            return

        try:
            result = self.client.send_command(
                equipment_id, "get_setpoints", {"channel": 1}
            )
            if not result.get("success"):
                raise RuntimeError(result.get("error") or "command failed")
            setpoints = result.get("data") or {}
        except Exception as e:
            # Not fatal. The caller still has the widgets blocked, so the panel
            # commands nothing either way; it just keeps showing the old number.
            logger.warning(
                f"Could not read setpoints from {equipment_id}; the panel may "
                f"show a stale setpoint until it is next changed: {e}"
            )
            return

        voltage = setpoints.get("voltage")
        current = setpoints.get("current")

        if voltage is not None:
            self.voltage_spinbox.setValue(voltage)
            self.voltage_dial.setValue(int(voltage * 10))
        if current is not None:
            self.current_spinbox.setValue(current)
            self.current_dial.setValue(int(current * 10))

    def _on_voltage_dial_changed(self, value):
        """Handle voltage dial change."""
        voltage = value / 10.0
        self.voltage_spinbox.blockSignals(True)
        self.voltage_spinbox.setValue(voltage)
        self.voltage_spinbox.blockSignals(False)
        self._send_voltage_command(voltage)

    def _on_voltage_spinbox_changed(self, value):
        """Handle voltage spinbox change."""
        self.voltage_dial.blockSignals(True)
        self.voltage_dial.setValue(int(value * 10))
        self.voltage_dial.blockSignals(False)
        self._send_voltage_command(value)

    def _on_current_dial_changed(self, value):
        """Handle current dial change."""
        current = value / 10.0
        self.current_spinbox.blockSignals(True)
        self.current_spinbox.setValue(current)
        self.current_spinbox.blockSignals(False)
        self._send_current_command(current)

    def _on_current_spinbox_changed(self, value):
        """Handle current spinbox change."""
        self.current_dial.blockSignals(True)
        self.current_dial.setValue(int(value * 10))
        self.current_dial.blockSignals(False)
        self._send_current_command(value)

    def _on_output_toggled(self, checked):
        """Handle output button toggle."""
        if checked:
            self.output_button.setText("Output: ON")
            self._send_output_command(True)
        else:
            self.output_button.setText("Output: OFF")
            self._send_output_command(False)

    def _readings_interval_ms(self) -> int:
        """The selected rate as a timer interval, never zero."""
        rate = max(self.refresh_spinbox.value(), 0.1)
        return int(1000 / rate)

    def _on_refresh_changed(self, value):
        """Handle refresh rate change.

        Updates how often voltage and current readings are queried from
        the equipment. All readings are fetched together in a single call.
        """
        self.readings_timer.setInterval(self._readings_interval_ms())

        # Remembered, because it is a bench preference rather than
        # something to re-choose every launch.
        try:
            from client.utils.settings import SettingsManager

            SettingsManager().set_reading_rate(value)
        except Exception as e:
            logger.debug(f"Could not save the reading rate: {e}")

    def _on_display_mode_changed(self, mode):
        """Handle display mode change."""
        if mode == "digital":
            self.digital_display.show()
            self.analog_display.hide()
            self.graph_display.hide()
        elif mode == "analog":
            self.digital_display.hide()
            self.analog_display.show()
            self.graph_display.hide()
        elif mode == "graph":
            self.digital_display.hide()
            self.analog_display.hide()
            self.graph_display.show()

    @qasync.asyncSlot(float)
    async def _send_voltage_command(self, voltage: float):
        """Send voltage command to equipment."""
        if not self.selected_equipment or not self.client:
            return

        try:
            await call_blocking(
                self.client.send_command,
                self.selected_equipment.equipment_id,
                "set_voltage",
                {"voltage": voltage, "channel": 1}
            )
        except Exception as e:
            logger.error(f"Error sending voltage command: {e}")

    @qasync.asyncSlot(float)
    async def _send_current_command(self, current: float):
        """Send current command to equipment."""
        if not self.selected_equipment or not self.client:
            return

        try:
            await call_blocking(
                self.client.send_command,
                self.selected_equipment.equipment_id,
                "set_current",
                {"current": current, "channel": 1}
            )
        except Exception as e:
            logger.error(f"Error sending current command: {e}")

    @qasync.asyncSlot(bool)
    async def _send_output_command(self, enabled: bool):
        """Send output enable/disable command."""
        if not self.selected_equipment or not self.client:
            return

        try:
            # Mark that we just sent a command - don't let readings overwrite button for 2 seconds
            self._last_output_command_time = time.time()

            await call_blocking(
                self.client.send_command,
                self.selected_equipment.equipment_id,
                "set_output",
                {"enabled": enabled, "channel": 1}
            )
            logger.info(f"Set output to {'ON' if enabled else 'OFF'}")
        except Exception as e:
            logger.error(f"Error sending output command: {e}")

    def _start_data_acquisition(self):
        """Start acquiring data from selected equipment."""
        if not self.selected_equipment:
            return

        # The list now includes instruments the server remembers but has
        # not opened. Polling one 404s at the reading rate, and that churn
        # was enough to stop the connect task ever being entered:
        # "Cannot enter into task ... while another task is being
        # executed". So the tab that cannot read it also must not try.
        if not self._selected_is_connected():
            self._stop_data_acquisition()
            self._show_not_connected()
            return

        # Delay starting the timer to give the equipment time to settle after lock acquisition
        # This helps prevent empty serial responses from the BK power supply.
        #
        # Start at the rate that is actually selected. This passed 1000 ms
        # flat, so every equipment switch quietly dropped the readings to
        # 1 Hz while the spinbox still said 10 -- the display and the
        # behaviour disagreeing, which is worse than either being wrong.
        QTimer.singleShot(500, lambda: self.readings_timer.start(
            self._readings_interval_ms()
        ))

        # Poll the lock at 5s. Slower than the readings on purpose: it is a
        # server query rather than a serial one, and the countdown only has to
        # look alive. It matters mostly for noticing control being taken away.
        self.lock_timer.start(5000)

    def _selected_is_connected(self) -> bool:
        """Whether the server currently holds the selected instrument open."""
        equipment = self.selected_equipment
        if not equipment:
            return False
        status = getattr(equipment, "connection_status", None)
        # An older server sends no status at all and only lists what is open,
        # so treat the absence as connected rather than refusing to work.
        return status is None or status == ConnectionStatus.CONNECTED

    def _show_not_connected(self):
        """Say why there are no readings, rather than showing stale ones."""
        self.voltage_display.setText("--")
        self.current_display.setText("--")
        self.voltage_gauge.set_value(0)
        self.current_gauge.set_value(0)
        self.status_message.emit(
            "Not connected. Connect it on the Equipment tab to read it."
        )

    def _stop_data_acquisition(self):
        """Stop acquiring data."""
        self.readings_timer.stop()
        self.lock_timer.stop()

    @qasync.asyncSlot()
    async def _update_readings(self):
        """Update voltage and current readings from equipment.

        Uses a single get_readings() call to update both voltage and current,
        preventing serial port overload from multiple simultaneous commands.
        """
        if not self.selected_equipment or not self.client:
            return

        # Belt and braces: the timer should already be stopped for an
        # instrument the server has not opened, but a tick in flight when
        # the selection changed would otherwise 404 and, worse, keep the
        # loop too busy for the connect task to start.
        if not self._selected_is_connected():
            self._stop_data_acquisition()
            return

        # The 1 Hz timer can outpace a slow server, so skip ticks while a
        # request is still in flight instead of queueing them up.
        if self._readings_in_flight:
            return

        self._readings_in_flight = True
        try:
            # Get all readings in one call (sends 3 serial commands: GETD, GOUT, GETS)
            readings = await call_blocking(
                self.client.get_readings, self.selected_equipment.equipment_id
            )

            # Extract values
            voltage_actual = readings.get("voltage_actual", 0.0)
            voltage_set = readings.get("voltage_set", 0.0)
            current_actual = readings.get("current_actual", 0.0)
            current_set = readings.get("current_set", 0.0)

            # Update voltage control knobs to show setpoint (without triggering callbacks)
            self.voltage_dial.blockSignals(True)
            self.voltage_spinbox.blockSignals(True)
            self.voltage_dial.setValue(int(voltage_set * 10))
            self.voltage_spinbox.setValue(voltage_set)
            self.voltage_dial.blockSignals(False)
            self.voltage_spinbox.blockSignals(False)

            # Update voltage displays with actual measured values
            self.voltage_display.setText(f"{voltage_actual:.{self.voltage_decimals}f} V")
            self.voltage_gauge.set_value(voltage_actual)

            # Update current control knobs to show setpoint (without triggering callbacks)
            self.current_dial.blockSignals(True)
            self.current_spinbox.blockSignals(True)
            self.current_dial.setValue(int(current_set * 10))
            self.current_spinbox.setValue(current_set)
            self.current_dial.blockSignals(False)
            self.current_spinbox.blockSignals(False)

            # Update current displays with actual measured values
            self.current_display.setText(f"{current_actual:.{self.current_decimals}f} A")
            self.current_gauge.set_value(current_actual)

            # The graph carries the same two numbers across its top, so the
            # mode that shows the trend still shows the present value.
            self._track_extremes(voltage_actual, current_actual)
            self._apply_auto_range()

            self.chart_view.set_readings(
                voltage_actual, current_actual,
                self.voltage_decimals, self.current_decimals,
            )

            # Update graph data
            timestamp = len(self.voltage_data)
            self.voltage_data.append(voltage_actual)
            self.current_data.append(current_actual)
            self.time_data.append(timestamp)

            # Update output button state (only if we haven't sent a command recently)
            # This prevents readings from overwriting user's button clicks
            time_since_command = time.time() - self._last_output_command_time
            if time_since_command > 2.0:  # Wait 2 seconds after command before updating
                output_enabled = readings.get("output_enabled", False)
                self.output_button.blockSignals(True)
                self.output_button.setChecked(output_enabled)
                self.output_button.setText("Output: ON" if output_enabled else "Output: OFF")
                self.output_button.blockSignals(False)

            # Update mode indicators
            if readings.get("in_cv_mode"):
                self.cv_indicator.setText("CV: ON")
                self.cv_indicator.setStyleSheet("QLabel { background-color: green; color: white; padding: 5px; }")
                self.cc_indicator.setText("CC: OFF")
                self.cc_indicator.setStyleSheet("QLabel { background-color: gray; color: white; padding: 5px; }")
            elif readings.get("in_cc_mode"):
                self.cc_indicator.setText("CC: ON")
                self.cc_indicator.setStyleSheet("QLabel { background-color: orange; color: white; padding: 5px; }")
                self.cv_indicator.setText("CV: OFF")
                self.cv_indicator.setStyleSheet("QLabel { background-color: gray; color: white; padding: 5px; }")

            # Update graph visualization
            self._update_graph()

        except Exception as e:
            logger.error(f"Error updating readings: {e}")
        finally:
            self._readings_in_flight = False

    def _update_graph(self):
        """Update the graph with current data."""
        self.voltage_series.clear()
        self.current_series.clear()

        for i, v in enumerate(self.voltage_data):
            self.voltage_series.append(i, v)

        for i, c in enumerate(self.current_data):
            self.current_series.append(i, c)

        # Update x-axis range
        if self.time_data:
            self.axis_x.setRange(max(0, len(self.time_data) - 100), len(self.time_data))

    def _clear_graph(self):
        """Clear all graph data."""
        # Clear data storage
        self.voltage_data.clear()
        self.current_data.clear()
        self.time_data.clear()

        # Clear chart series
        self.voltage_series.clear()
        self.current_series.clear()

        # Reset x-axis
        self.axis_x.setRange(0, 100)

        logger.info("Graph data cleared")

    @qasync.asyncSlot()
    async def refresh_equipment_list(self):
        """Refresh the equipment list from server."""
        if not self.client:
            return

        try:
            equipment_list = await call_blocking(self.client.list_equipment)
            self.equipment_list = [Equipment.from_api_dict(eq) for eq in equipment_list]

            # Update list widget. Repopulating clears the selection, and the
            # list now refreshes on its own, so put the highlight back on the
            # instrument being controlled rather than leave it looking idle.
            selected_id = (
                self.selected_equipment.equipment_id
                if self.selected_equipment else None
            )
            self.equipment_list_widget.clear()
            for equipment in self.equipment_list:
                if equipment.connection_status == ConnectionStatus.CONNECTED:
                    item = QListWidgetItem(
                        f"{equipment.name} ({equipment.equipment_type.value})"
                    )
                    item.setData(Qt.ItemDataRole.UserRole, equipment.equipment_id)
                    self.equipment_list_widget.addItem(item)
                    if equipment.equipment_id == selected_id:
                        self.equipment_list_widget.setCurrentItem(item)

        except Exception as e:
            logger.error(f"Error refreshing equipment list: {e}")

    def showEvent(self, event):
        """Bring the list up to date whenever this tab comes to the front.

        Instruments are connected on the Equipment tab. This list only
        changed when the operator pressed Refresh, so a supply connected a
        moment ago was missing from the Control tab until they did.
        """
        super().showEvent(event)
        if self.client:
            self.refresh_equipment_list()

    def set_client(self, client: LabLinkClient):
        """Set the API client."""
        self.client = client
        self.refresh_equipment_list()

    def wheelEvent(self, event):
        """Handle mouse wheel events over dials."""
        # This allows scrolling over dials to change values
        widget = self.childAt(event.position().toPoint())
        if isinstance(widget, QDial):
            delta = event.angleDelta().y()
            current_value = widget.value()
            step = 1 if delta > 0 else -1
            widget.setValue(current_value + step)
            event.accept()
        else:
            event.ignore()
