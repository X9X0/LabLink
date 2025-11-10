"""Enhanced data acquisition panel for LabLink GUI."""

import logging
import asyncio
import time
from typing import Optional, Dict, List, Set
from collections import deque
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox, QComboBox,
    QSpinBox, QDoubleSpinBox, QFormLayout, QCheckBox, QLineEdit,
    QTabWidget, QTextEdit, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QEvent, QObject

from api.client import LabLinkClient
from models import (
    AcquisitionMode, AcquisitionState, TriggerType, TriggerEdge,
    ExportFormat, AcquisitionConfig, TriggerConfig
)

try:
    from ui.widgets.plot_widget import PlotWidget
    HAS_PLOT_WIDGET = True
except ImportError:
    HAS_PLOT_WIDGET = False

logger = logging.getLogger(__name__)


class AcquisitionWebSocketSignals(QObject):
    """Qt signals for WebSocket callbacks (thread-safe)."""

    acquisition_data_received = pyqtSignal(str, dict)  # acquisition_id, data_point
    stream_started = pyqtSignal(str)  # acquisition_id
    stream_stopped = pyqtSignal(str)  # acquisition_id


class CircularBuffer:
    """Circular buffer for efficient plot data management.

    Maintains a fixed-size rolling buffer of data points for real-time plotting.
    Automatically discards oldest data when buffer is full.
    """

    def __init__(self, max_size: int = 1000):
        """Initialize circular buffer.

        Args:
            max_size: Maximum number of data points to store
        """
        self.max_size = max_size
        self.data: Dict[str, deque] = {}  # channel -> deque of values
        self.timestamps: deque = deque(maxlen=max_size)
        self._sample_count = 0

    def add_point(self, timestamp: float, values: Dict[str, float]):
        """Add data point to buffer.

        Args:
            timestamp: Timestamp of data point
            values: Dictionary mapping channel names to values
        """
        self.timestamps.append(timestamp)

        for channel, value in values.items():
            if channel not in self.data:
                # Initialize channel buffer with max size
                self.data[channel] = deque(maxlen=self.max_size)
            self.data[channel].append(value)

        self._sample_count += 1

    def get_channel_data(self, channel: str) -> tuple[List[float], List[float]]:
        """Get timestamps and values for a specific channel.

        Args:
            channel: Channel name

        Returns:
            Tuple of (timestamps, values) lists
        """
        if channel not in self.data:
            return [], []

        return list(self.timestamps), list(self.data[channel])

    def get_all_channels(self) -> List[str]:
        """Get list of all channel names in buffer.

        Returns:
            List of channel names
        """
        return list(self.data.keys())

    def clear(self):
        """Clear all data from buffer."""
        self.data.clear()
        self.timestamps.clear()
        self._sample_count = 0

    def get_sample_count(self) -> int:
        """Get total number of samples added (including discarded).

        Returns:
            Total sample count
        """
        return self._sample_count


class AutoCloseComboBox(QComboBox):
    """Custom QComboBox that closes automatically after selection.

    Note: Due to PyQt6/platform limitations, this uses standard QComboBox behavior.
    The popup will close when you click outside of it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Use standard QComboBox - the auto-close behavior appears to be
        # a platform-specific Qt issue that cannot be reliably fixed across
        # all environments without breaking mouse hover functionality


class AcquisitionPanel(QWidget):
    """Enhanced panel for data acquisition control and visualization."""

    # Signals
    acquisition_started = pyqtSignal(str)  # acquisition_id
    acquisition_stopped = pyqtSignal(str)  # acquisition_id

    def __init__(self, parent=None):
        """Initialize acquisition panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.active_sessions: Dict[str, Dict] = {}  # acquisition_id -> session info
        self.current_acquisition_id: Optional[str] = None

        # WebSocket streaming state
        self.ws_signals = AcquisitionWebSocketSignals()
        self.streaming_acquisitions: Set[str] = set()  # Track acquisitions with active streams
        self.plot_buffers: Dict[str, CircularBuffer] = {}  # acquisition_id -> CircularBuffer

        # Streaming quality metrics
        self.stream_start_time: Optional[float] = None
        self.stream_data_count: int = 0
        self.last_data_time: Optional[float] = None

        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.setInterval(2000)  # 2 seconds

        self._setup_ui()
        self._connect_ws_signals()

    def _setup_ui(self):
        """Set up user interface."""
        main_layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Data Acquisition & Logging</h2>")
        main_layout.addWidget(header)

        # Create splitter for top and bottom sections
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top section: Configuration and sessions
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)

        # Left: Configuration
        config_widget = self._create_config_section()
        top_layout.addWidget(config_widget, stretch=3)

        # Right: Active sessions
        sessions_widget = self._create_sessions_section()
        top_layout.addWidget(sessions_widget, stretch=2)

        splitter.addWidget(top_widget)

        # Bottom section: Tabs for visualization, statistics, and data
        self.tabs = QTabWidget()

        # Visualization tab
        self.viz_tab = self._create_visualization_tab()
        self.tabs.addTab(self.viz_tab, "Visualization")

        # Statistics tab
        self.stats_tab = self._create_statistics_tab()
        self.tabs.addTab(self.stats_tab, "Statistics")

        # Data tab
        self.data_tab = self._create_data_tab()
        self.tabs.addTab(self.data_tab, "Data")

        splitter.addWidget(self.tabs)

        # Set splitter proportions
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)

    def _create_config_section(self) -> QWidget:
        """Create acquisition configuration section."""
        group = QGroupBox("Acquisition Configuration")
        layout = QFormLayout()

        # Equipment selection
        self.equipment_combo = AutoCloseComboBox()
        layout.addRow("Equipment:", self.equipment_combo)

        # Session name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Optional session name")
        layout.addRow("Name:", self.name_edit)

        # Acquisition mode
        self.mode_combo = AutoCloseComboBox()
        self.mode_combo.addItems([mode.value for mode in AcquisitionMode])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addRow("Mode:", self.mode_combo)

        # Sample rate
        self.sample_rate_spin = QDoubleSpinBox()
        self.sample_rate_spin.setRange(0.001, 1000000)
        self.sample_rate_spin.setValue(1000)
        self.sample_rate_spin.setDecimals(3)
        self.sample_rate_spin.setSuffix(" Hz")
        layout.addRow("Sample Rate:", self.sample_rate_spin)

        # Duration (for single-shot and limited continuous)
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.1, 86400)  # Up to 24 hours
        self.duration_spin.setValue(10)
        self.duration_spin.setDecimals(1)
        self.duration_spin.setSuffix(" s")
        layout.addRow("Duration:", self.duration_spin)

        # Number of samples (for single-shot)
        self.num_samples_spin = QSpinBox()
        self.num_samples_spin.setRange(1, 10000000)
        self.num_samples_spin.setValue(1000)
        self.num_samples_spin.setEnabled(False)
        layout.addRow("Num Samples:", self.num_samples_spin)

        # Channels
        self.channels_edit = QLineEdit("CH1")
        self.channels_edit.setPlaceholderText("e.g., CH1,CH2 or voltage,current")
        layout.addRow("Channels:", self.channels_edit)

        # Trigger type
        self.trigger_type_combo = AutoCloseComboBox()
        self.trigger_type_combo.addItems([t.value for t in TriggerType])
        self.trigger_type_combo.currentTextChanged.connect(self._on_trigger_changed)
        layout.addRow("Trigger Type:", self.trigger_type_combo)

        # Trigger level (for level/edge triggers)
        self.trigger_level_spin = QDoubleSpinBox()
        self.trigger_level_spin.setRange(-1000, 1000)
        self.trigger_level_spin.setValue(0)
        self.trigger_level_spin.setDecimals(3)
        self.trigger_level_spin.setEnabled(False)
        layout.addRow("Trigger Level:", self.trigger_level_spin)

        # Trigger edge
        self.trigger_edge_combo = AutoCloseComboBox()
        self.trigger_edge_combo.addItems([e.value for e in TriggerEdge])
        self.trigger_edge_combo.setEnabled(False)
        layout.addRow("Trigger Edge:", self.trigger_edge_combo)

        # Trigger channel
        self.trigger_channel_edit = QLineEdit()
        self.trigger_channel_edit.setPlaceholderText("Channel for trigger")
        self.trigger_channel_edit.setEnabled(False)
        layout.addRow("Trigger Channel:", self.trigger_channel_edit)

        # Buffer size
        self.buffer_size_spin = QSpinBox()
        self.buffer_size_spin.setRange(100, 10000000)
        self.buffer_size_spin.setValue(10000)
        layout.addRow("Buffer Size:", self.buffer_size_spin)

        # Auto-export checkbox
        self.auto_export_check = QCheckBox("Auto-export on completion")
        layout.addRow("", self.auto_export_check)

        # Export format
        self.export_format_combo = AutoCloseComboBox()
        self.export_format_combo.addItems([f.value for f in ExportFormat])
        self.export_format_combo.setEnabled(False)
        layout.addRow("Export Format:", self.export_format_combo)

        self.auto_export_check.toggled.connect(
            lambda checked: self.export_format_combo.setEnabled(checked)
        )

        # Control buttons
        button_layout = QHBoxLayout()

        self.create_btn = QPushButton("Create Session")
        self.create_btn.clicked.connect(self.create_session)
        button_layout.addWidget(self.create_btn)

        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_acquisition)
        self.start_btn.setEnabled(False)
        button_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_acquisition)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.pause_acquisition)
        self.pause_btn.setEnabled(False)
        button_layout.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("Resume")
        self.resume_btn.clicked.connect(self.resume_acquisition)
        self.resume_btn.setEnabled(False)
        button_layout.addWidget(self.resume_btn)

        layout.addRow("", button_layout)

        group.setLayout(layout)
        return group

    def _create_sessions_section(self) -> QWidget:
        """Create active sessions section."""
        group = QGroupBox("Active Sessions")
        layout = QVBoxLayout()

        # Sessions list
        self.sessions_list = QListWidget()
        self.sessions_list.itemClicked.connect(self._on_session_selected)
        layout.addWidget(self.sessions_list)

        # Session action buttons
        btn_layout = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_sessions)
        btn_layout.addWidget(refresh_btn)

        export_btn = QPushButton("Export...")
        export_btn.clicked.connect(self.export_current_session)
        btn_layout.addWidget(export_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self.delete_current_session)
        btn_layout.addWidget(delete_btn)

        layout.addLayout(btn_layout)

        # Auto-refresh checkbox
        self.auto_refresh_check = QCheckBox("Auto-refresh")
        self.auto_refresh_check.setChecked(True)
        self.auto_refresh_check.toggled.connect(self._toggle_auto_refresh)
        layout.addWidget(self.auto_refresh_check)

        # Session info display
        self.session_info_text = QTextEdit()
        self.session_info_text.setReadOnly(True)
        self.session_info_text.setMaximumHeight(100)
        layout.addWidget(QLabel("Session Info:"))
        layout.addWidget(self.session_info_text)

        group.setLayout(layout)
        return group

    def _create_visualization_tab(self) -> QWidget:
        """Create visualization tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        if HAS_PLOT_WIDGET:
            self.plot_widget = PlotWidget()
            self.plot_widget.setYLabel("Value")
            self.plot_widget.setXLabel("Sample")
            layout.addWidget(self.plot_widget)
        else:
            label = QLabel("<i>Visualization widget not available</i>")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)

        return widget

    def _create_statistics_tab(self) -> QWidget:
        """Create statistics tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Statistics table
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(3)
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value", "Unit"])
        self.stats_table.horizontalHeader().setStretchLastSection(False)
        self.stats_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.stats_table)

        # Statistics control buttons
        btn_layout = QHBoxLayout()

        rolling_btn = QPushButton("Rolling Stats")
        rolling_btn.clicked.connect(self.show_rolling_stats)
        btn_layout.addWidget(rolling_btn)

        fft_btn = QPushButton("FFT Analysis")
        fft_btn.clicked.connect(self.show_fft_analysis)
        btn_layout.addWidget(fft_btn)

        trend_btn = QPushButton("Trend Analysis")
        trend_btn.clicked.connect(self.show_trend_analysis)
        btn_layout.addWidget(trend_btn)

        quality_btn = QPushButton("Data Quality")
        quality_btn.clicked.connect(self.show_quality_metrics)
        btn_layout.addWidget(quality_btn)

        layout.addLayout(btn_layout)

        return widget

    def _create_data_tab(self) -> QWidget:
        """Create data display tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Data table
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(4)
        self.data_table.setHorizontalHeaderLabels(["Timestamp", "Channel", "Value", "Unit"])
        layout.addWidget(self.data_table)

        # Data controls
        btn_layout = QHBoxLayout()

        load_data_btn = QPushButton("Load Data")
        load_data_btn.clicked.connect(self.load_acquisition_data)
        btn_layout.addWidget(load_data_btn)

        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(10, 1000000)
        self.max_points_spin.setValue(1000)
        self.max_points_spin.setPrefix("Max points: ")
        btn_layout.addWidget(self.max_points_spin)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        return widget

    def _on_mode_changed(self, mode: str):
        """Handle acquisition mode change."""
        is_single_shot = mode == "single_shot"
        self.num_samples_spin.setEnabled(is_single_shot)
        self.duration_spin.setEnabled(True)  # Always enabled

    def _on_trigger_changed(self, trigger_type: str):
        """Handle trigger type change."""
        needs_level = trigger_type in ["level", "edge"]
        needs_edge = trigger_type == "edge"
        needs_channel = trigger_type in ["level", "edge"]

        self.trigger_level_spin.setEnabled(needs_level)
        self.trigger_edge_combo.setEnabled(needs_edge)
        self.trigger_channel_edit.setEnabled(needs_channel)

    def _on_session_selected(self, item: QListWidgetItem):
        """Handle session selection."""
        acquisition_id = item.data(Qt.ItemDataRole.UserRole)
        self.current_acquisition_id = acquisition_id

        if acquisition_id in self.active_sessions:
            session = self.active_sessions[acquisition_id]
            self._update_session_info(session)
            self._update_control_buttons(session.get("state", "idle"))

    def _update_session_info(self, session: Dict):
        """Update session info display."""
        info_text = f"""
Acquisition ID: {session.get('acquisition_id', 'N/A')}
Equipment: {session.get('equipment_id', 'N/A')}
State: {session.get('state', 'N/A')}
Mode: {session.get('config', {}).get('mode', 'N/A')}
Sample Rate: {session.get('config', {}).get('sample_rate', 'N/A')} Hz
Samples Collected: {session.get('sample_count', 0)}
        """.strip()
        self.session_info_text.setText(info_text)

    def _update_control_buttons(self, state: str):
        """Update control button states based on acquisition state."""
        self.start_btn.setEnabled(state in ["idle", "stopped"])
        self.stop_btn.setEnabled(state in ["acquiring", "waiting_trigger", "paused"])
        self.pause_btn.setEnabled(state == "acquiring")
        self.resume_btn.setEnabled(state == "paused")

    def _toggle_auto_refresh(self, enabled: bool):
        """Toggle auto-refresh of sessions."""
        if enabled:
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()

    def _auto_refresh(self):
        """Auto-refresh active sessions."""
        if self.client:
            self.refresh_sessions(silent=True)

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client
        self._register_ws_handlers()
        self.refresh_equipment()
        self.refresh_sessions()

        if self.auto_refresh_check.isChecked():
            self.refresh_timer.start()

    def _connect_ws_signals(self):
        """Connect WebSocket signals to slot handlers."""
        self.ws_signals.acquisition_data_received.connect(self._on_acquisition_data)
        self.ws_signals.stream_started.connect(self._on_stream_started)
        self.ws_signals.stream_stopped.connect(self._on_stream_stopped)

    def _register_ws_handlers(self):
        """Register WebSocket message handlers with the client."""
        if not self.client or not self.client.ws_manager:
            return

        try:
            self.client.ws_manager.on_acquisition_data(self._ws_acquisition_data_callback)
            logger.info("Registered WebSocket acquisition handlers for acquisition panel")
        except Exception as e:
            logger.warning(f"Could not register WebSocket handlers: {e}")

    def _ws_acquisition_data_callback(self, message: Dict):
        """WebSocket callback for acquisition data (runs in WebSocket thread).

        This emits a Qt signal for thread-safe GUI updates.

        Args:
            message: WebSocket message with acquisition data
        """
        acquisition_id = message.get("acquisition_id")
        data = message.get("data", {})

        if acquisition_id:
            # Emit signal to update GUI thread
            self.ws_signals.acquisition_data_received.emit(acquisition_id, data)

    def _on_acquisition_data(self, acquisition_id: str, data: Dict):
        """Handle acquisition data in GUI thread (thread-safe).

        Args:
            acquisition_id: ID of acquisition sending data
            data: Data point dictionary with timestamp and channel values
        """
        # Update streaming quality metrics
        current_time = time.time()
        self.stream_data_count += 1
        self.last_data_time = current_time

        # Only update if this is the selected acquisition
        if self.current_acquisition_id and self.current_acquisition_id == acquisition_id:
            # Initialize buffer if needed
            if acquisition_id not in self.plot_buffers:
                self.plot_buffers[acquisition_id] = CircularBuffer(max_size=1000)

            # Add data point to circular buffer
            timestamp = data.get("timestamp", current_time)
            values = data.get("values", {})

            self.plot_buffers[acquisition_id].add_point(timestamp, values)

            # Update plot with buffered data
            self._update_plot(acquisition_id)

    def _on_stream_started(self, acquisition_id: str):
        """Handle stream started notification.

        Args:
            acquisition_id: ID of acquisition with started stream
        """
        self.streaming_acquisitions.add(acquisition_id)
        self.stream_start_time = time.time()
        self.stream_data_count = 0
        self.last_data_time = None
        logger.info(f"Stream started for acquisition {acquisition_id}")

    def _on_stream_stopped(self, acquisition_id: str):
        """Handle stream stopped notification.

        Args:
            acquisition_id: ID of acquisition with stopped stream
        """
        self.streaming_acquisitions.discard(acquisition_id)
        logger.info(f"Stream stopped for acquisition {acquisition_id}")

    def _update_plot(self, acquisition_id: str):
        """Update plot with data from circular buffer.

        Args:
            acquisition_id: ID of acquisition to plot
        """
        if not HAS_PLOT_WIDGET:
            return

        buffer = self.plot_buffers.get(acquisition_id)
        if not buffer:
            return

        # Get all channels from buffer
        channels = buffer.get_all_channels()

        if not channels:
            return

        # Clear existing plots
        self.plot_widget.clear()

        # Plot each channel
        for channel in channels:
            timestamps, values = buffer.get_channel_data(channel)
            if timestamps and values:
                self.plot_widget.addCurve(timestamps, values, label=channel)

        # Update plot labels
        self.plot_widget.setTitle(f"Acquisition {acquisition_id[:8]}")

        # Update quality indicator
        if self.stream_start_time:
            elapsed = time.time() - self.stream_start_time
            data_rate = self.stream_data_count / elapsed if elapsed > 0 else 0
            latency = time.time() - self.last_data_time if self.last_data_time else 0

            quality_text = f"Data rate: {data_rate:.1f} Hz | Latency: {latency*1000:.0f} ms | Samples: {buffer.get_sample_count()}"
            self.plot_widget.setFooter(quality_text)

    async def _start_acquisition_stream(self, acquisition_id: str):
        """Start WebSocket stream for acquisition (async).

        Args:
            acquisition_id: ID of acquisition to stream from
        """
        if not self.client or not self.client.ws_manager or not self.client.ws_manager.connected:
            logger.debug("WebSocket not available - using polling fallback")
            return

        try:
            logger.info(f"Starting acquisition stream for {acquisition_id}")
            await self.client.start_acquisition_stream(
                acquisition_id=acquisition_id,
                stream_type="data",
                interval_ms=100  # 10 Hz update rate
            )
            self.ws_signals.stream_started.emit(acquisition_id)
            logger.info(f"Stream started successfully for {acquisition_id}")

        except Exception as e:
            logger.warning(f"Could not start acquisition stream: {e}")
            # Fall back to polling - no error shown to user

    async def _stop_acquisition_stream(self, acquisition_id: str):
        """Stop WebSocket stream for acquisition (async).

        Args:
            acquisition_id: ID of acquisition to stop streaming
        """
        if not self.client or not self.client.ws_manager:
            return

        try:
            logger.info(f"Stopping acquisition stream for {acquisition_id}")
            await self.client.stop_acquisition_stream(acquisition_id)
            self.ws_signals.stream_stopped.emit(acquisition_id)
            logger.info(f"Stream stopped for {acquisition_id}")

        except Exception as e:
            logger.warning(f"Could not stop acquisition stream: {e}")

    def refresh_equipment(self):
        """Refresh equipment list."""
        if not self.client:
            return

        try:
            equipment_list = self.client.list_equipment()
            self.equipment_combo.clear()
            for eq in equipment_list:
                self.equipment_combo.addItem(
                    f"{eq.get('model', 'Unknown')} ({eq.get('type', '')})",
                    eq.get("id")
                )
        except Exception as e:
            logger.error(f"Error refreshing equipment list: {e}")

    def refresh_sessions(self, silent: bool = False):
        """Refresh active acquisition sessions."""
        if not self.client:
            return

        try:
            sessions = self.client.list_acquisition_sessions()
            self.active_sessions.clear()
            self.sessions_list.clear()

            for session in sessions:
                acquisition_id = session.get("acquisition_id")
                self.active_sessions[acquisition_id] = session

                # Add to list
                state = session.get("state", "unknown")
                mode = session.get("config", {}).get("mode", "?")
                equipment = session.get("equipment_id", "?")
                name = session.get("config", {}).get("name") or acquisition_id[:8]

                item_text = f"{name} - {equipment} [{state}] ({mode})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, acquisition_id)
                self.sessions_list.addItem(item)

            if not silent:
                logger.info(f"Refreshed {len(sessions)} acquisition sessions")

        except Exception as e:
            if not silent:
                logger.error(f"Error refreshing sessions: {e}")

    def create_session(self):
        """Create new acquisition session."""
        if not self.client:
            QMessageBox.warning(self, "Not Connected", "Please connect to a server first")
            return

        equipment_id = self.equipment_combo.currentData()
        if not equipment_id:
            QMessageBox.warning(self, "No Equipment", "Please select equipment")
            return

        try:
            # Build trigger config
            trigger_config = TriggerConfig(
                trigger_type=TriggerType(self.trigger_type_combo.currentText()),
                level=self.trigger_level_spin.value() if self.trigger_level_spin.isEnabled() else None,
                edge=TriggerEdge(self.trigger_edge_combo.currentText()) if self.trigger_edge_combo.isEnabled() else None,
                channel=self.trigger_channel_edit.text() if self.trigger_channel_edit.isEnabled() else None
            )

            # Build acquisition config
            channels = [ch.strip() for ch in self.channels_edit.text().split(",")]
            config = AcquisitionConfig(
                equipment_id=equipment_id,
                name=self.name_edit.text() or None,
                mode=AcquisitionMode(self.mode_combo.currentText()),
                sample_rate=self.sample_rate_spin.value(),
                duration_seconds=self.duration_spin.value(),
                num_samples=self.num_samples_spin.value() if self.num_samples_spin.isEnabled() else None,
                channels=channels,
                trigger_config=trigger_config,
                buffer_size=self.buffer_size_spin.value(),
                auto_export=self.auto_export_check.isChecked(),
                export_format=ExportFormat(self.export_format_combo.currentText())
            )

            # Create session
            result = self.client.create_acquisition_session(equipment_id, config.to_dict())
            acquisition_id = result.get("acquisition_id")

            if acquisition_id:
                self.current_acquisition_id = acquisition_id
                QMessageBox.information(self, "Success", f"Session created: {acquisition_id}")
                self.refresh_sessions()
            else:
                QMessageBox.warning(self, "Error", "Failed to get acquisition ID from response")

        except Exception as e:
            logger.error(f"Error creating acquisition session: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create session:\n{str(e)}")

    def start_acquisition(self):
        """Start data acquisition."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select or create a session first")
            return

        try:
            result = self.client.start_acquisition(self.current_acquisition_id)
            if result.get("success"):
                QMessageBox.information(self, "Success", "Acquisition started")
                self.acquisition_started.emit(self.current_acquisition_id)
                self.refresh_sessions()

                # Auto-start WebSocket streaming for started acquisition
                asyncio.create_task(self._start_acquisition_stream(self.current_acquisition_id))
        except Exception as e:
            logger.error(f"Error starting acquisition: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start:\n{str(e)}")

    def stop_acquisition(self):
        """Stop data acquisition."""
        if not self.current_acquisition_id:
            return

        acquisition_id = self.current_acquisition_id

        try:
            # Stop streaming first
            if acquisition_id in self.streaming_acquisitions:
                asyncio.create_task(self._stop_acquisition_stream(acquisition_id))

            result = self.client.stop_acquisition(acquisition_id)
            if result.get("success"):
                QMessageBox.information(self, "Success", "Acquisition stopped")
                self.acquisition_stopped.emit(acquisition_id)
                self.refresh_sessions()
        except Exception as e:
            logger.error(f"Error stopping acquisition: {e}")
            QMessageBox.critical(self, "Error", f"Failed to stop:\n{str(e)}")

    def pause_acquisition(self):
        """Pause data acquisition."""
        if not self.current_acquisition_id:
            return

        try:
            result = self.client.pause_acquisition(self.current_acquisition_id)
            if result.get("success"):
                QMessageBox.information(self, "Success", "Acquisition paused")
                self.refresh_sessions()
        except Exception as e:
            logger.error(f"Error pausing acquisition: {e}")
            QMessageBox.critical(self, "Error", f"Failed to pause:\n{str(e)}")

    def resume_acquisition(self):
        """Resume paused acquisition."""
        if not self.current_acquisition_id:
            return

        try:
            result = self.client.resume_acquisition(self.current_acquisition_id)
            if result.get("success"):
                QMessageBox.information(self, "Success", "Acquisition resumed")
                self.refresh_sessions()
        except Exception as e:
            logger.error(f"Error resuming acquisition: {e}")
            QMessageBox.critical(self, "Error", f"Failed to resume:\n{str(e)}")

    def delete_current_session(self):
        """Delete currently selected session."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete acquisition session {self.current_acquisition_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                result = self.client.delete_acquisition_session(self.current_acquisition_id)
                if result.get("success"):
                    QMessageBox.information(self, "Success", "Session deleted")
                    self.current_acquisition_id = None
                    self.refresh_sessions()
            except Exception as e:
                logger.error(f"Error deleting session: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete:\n{str(e)}")

    def export_current_session(self):
        """Export data from current session."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            from PyQt6.QtWidgets import QFileDialog
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Acquisition Data",
                "",
                "CSV Files (*.csv);;HDF5 Files (*.h5);;NumPy Files (*.npy);;JSON Files (*.json)"
            )

            if filename:
                # Determine format from extension
                if filename.endswith('.csv'):
                    fmt = 'csv'
                elif filename.endswith('.h5'):
                    fmt = 'hdf5'
                elif filename.endswith('.npy'):
                    fmt = 'npy'
                else:
                    fmt = 'json'

                result = self.client.export_acquisition_data(
                    self.current_acquisition_id,
                    format=fmt,
                    filepath=filename
                )

                if result.get("success"):
                    QMessageBox.information(self, "Success", f"Data exported to {filename}")
        except Exception as e:
            logger.error(f"Error exporting data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to export:\n{str(e)}")

    def load_acquisition_data(self):
        """Load and display acquisition data."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            result = self.client.get_acquisition_data(
                self.current_acquisition_id,
                max_points=self.max_points_spin.value()
            )

            # API returns data in format: {channels: [...], data: {timestamps: [...], values: {CH1: [...]}}}
            channels = result.get("channels", [])
            data = result.get("data", {})
            timestamps = data.get("timestamps", [])
            values_by_channel = data.get("values", {})

            # Calculate total number of rows (timestamps * channels)
            total_rows = len(timestamps) * len(channels)
            self.data_table.setRowCount(total_rows)

            row = 0
            for i, timestamp in enumerate(timestamps):
                for channel in channels:
                    channel_values = values_by_channel.get(channel, [])
                    value = channel_values[i] if i < len(channel_values) else ""

                    self.data_table.setItem(row, 0, QTableWidgetItem(str(timestamp)))
                    self.data_table.setItem(row, 1, QTableWidgetItem(str(channel)))
                    self.data_table.setItem(row, 2, QTableWidgetItem(f"{value:.6f}" if isinstance(value, (int, float)) else str(value)))
                    self.data_table.setItem(row, 3, QTableWidgetItem("V"))  # Default unit
                    row += 1

            logger.info(f"Loaded {len(timestamps)} data points across {len(channels)} channels")

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load data:\n{str(e)}")

    def show_rolling_stats(self):
        """Show rolling statistics."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            # First get acquisition data to discover channels
            data_result = self.client.get_acquisition_data(
                self.current_acquisition_id,
                max_points=1
            )
            channels = data_result.get("channels", [])

            if not channels:
                QMessageBox.warning(self, "No Channels", "No channels found in acquisition data")
                return

            self.stats_table.setRowCount(0)

            # Get rolling stats for each channel
            for channel in channels:
                try:
                    result = self.client.get_acquisition_rolling_stats(
                        self.current_acquisition_id,
                        channel=channel
                    )
                    stats = result.get("stats", {})
                    self._add_stat_row(f"{channel} - Mean", stats.get("mean", 0), "")
                    self._add_stat_row(f"{channel} - Std Dev", stats.get("std", 0), "")
                    self._add_stat_row(f"{channel} - Min", stats.get("min", 0), "")
                    self._add_stat_row(f"{channel} - Max", stats.get("max", 0), "")
                    self._add_stat_row(f"{channel} - RMS", stats.get("rms", 0), "")
                    self._add_stat_row(f"{channel} - P2P", stats.get("peak_to_peak", 0), "")
                except Exception as channel_error:
                    logger.error(f"Error getting stats for channel {channel}: {channel_error}")

        except Exception as e:
            logger.error(f"Error getting rolling stats: {e}")
            QMessageBox.critical(self, "Error", f"Failed to get statistics:\n{str(e)}")

    def show_fft_analysis(self):
        """Show FFT analysis."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            # Get channels from session data
            data_result = self.client.get_acquisition_data(
                self.current_acquisition_id,
                max_points=1
            )
            channels = data_result.get("channels", [])

            if not channels:
                QMessageBox.warning(self, "No Channels", "No channels found in acquisition data")
                return

            self.stats_table.setRowCount(0)

            # Get FFT analysis for each channel
            for channel in channels:
                try:
                    result = self.client.get_acquisition_fft(
                        self.current_acquisition_id,
                        channel=channel
                    )
                    fft_data = result.get("fft", {})
                    self._add_stat_row(f"{channel} - Fundamental Freq", fft_data.get("fundamental_frequency", 0), "Hz")
                    self._add_stat_row(f"{channel} - THD", fft_data.get("thd", 0), "%")
                    self._add_stat_row(f"{channel} - SNR", fft_data.get("snr", 0), "dB")
                except Exception as channel_error:
                    logger.error(f"Error getting FFT for channel {channel}: {channel_error}")

        except Exception as e:
            logger.error(f"Error getting FFT analysis: {e}")
            QMessageBox.critical(self, "Error", f"Failed to get FFT:\n{str(e)}")

    def show_trend_analysis(self):
        """Show trend analysis."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            # Get channels from session data
            data_result = self.client.get_acquisition_data(
                self.current_acquisition_id,
                max_points=1
            )
            channels = data_result.get("channels", [])

            if not channels:
                QMessageBox.warning(self, "No Channels", "No channels found in acquisition data")
                return

            self.stats_table.setRowCount(0)

            # Get trend analysis for each channel
            for channel in channels:
                try:
                    result = self.client.get_acquisition_trend(
                        self.current_acquisition_id,
                        channel=channel
                    )
                    trend_data = result.get("trend", {})
                    self._add_stat_row(f"{channel} - Trend", trend_data.get("trend", "unknown"), "")
                    self._add_stat_row(f"{channel} - Slope", trend_data.get("slope", 0), "")
                    self._add_stat_row(f"{channel} - Confidence", trend_data.get("confidence", 0), "")
                except Exception as channel_error:
                    logger.error(f"Error getting trend for channel {channel}: {channel_error}")

        except Exception as e:
            logger.error(f"Error getting trend analysis: {e}")
            QMessageBox.critical(self, "Error", f"Failed to get trend:\n{str(e)}")

    def show_quality_metrics(self):
        """Show data quality metrics."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            # Get channels from session data
            data_result = self.client.get_acquisition_data(
                self.current_acquisition_id,
                max_points=1
            )
            channels = data_result.get("channels", [])

            if not channels:
                QMessageBox.warning(self, "No Channels", "No channels found in acquisition data")
                return

            self.stats_table.setRowCount(0)

            # Get quality metrics for each channel
            for channel in channels:
                try:
                    result = self.client.get_acquisition_quality(
                        self.current_acquisition_id,
                        channel=channel
                    )
                    quality_data = result.get("quality", {})
                    self._add_stat_row(f"{channel} - Quality Grade", quality_data.get("quality_grade", "unknown"), "")
                    self._add_stat_row(f"{channel} - Noise Level", quality_data.get("noise_level", 0), "")
                    self._add_stat_row(f"{channel} - Stability", quality_data.get("stability_score", 0), "")
                    self._add_stat_row(f"{channel} - Outlier Ratio", quality_data.get("outlier_ratio", 0), "%")
                except Exception as channel_error:
                    logger.error(f"Error getting quality for channel {channel}: {channel_error}")

        except Exception as e:
            logger.error(f"Error getting quality metrics: {e}")
            QMessageBox.critical(self, "Error", f"Failed to get quality:\n{str(e)}")

    def _add_stat_row(self, metric: str, value: float, unit: str):
        """Add row to statistics table."""
        row = self.stats_table.rowCount()
        self.stats_table.insertRow(row)
        self.stats_table.setItem(row, 0, QTableWidgetItem(metric))
        self.stats_table.setItem(row, 1, QTableWidgetItem(f"{value:.4f}" if isinstance(value, (int, float)) else str(value)))
        self.stats_table.setItem(row, 2, QTableWidgetItem(unit))

    def closeEvent(self, event):
        """Handle widget close event."""
        self.refresh_timer.stop()
        event.accept()
