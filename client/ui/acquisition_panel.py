"""Enhanced data acquisition panel for LabLink GUI."""

import logging
from typing import Optional, Dict, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox, QComboBox,
    QSpinBox, QDoubleSpinBox, QFormLayout, QCheckBox, QLineEdit,
    QTabWidget, QTextEdit, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

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

        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.setInterval(2000)  # 2 seconds

        self._setup_ui()

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
        self.equipment_combo = QComboBox()
        layout.addRow("Equipment:", self.equipment_combo)

        # Session name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Optional session name")
        layout.addRow("Name:", self.name_edit)

        # Acquisition mode
        self.mode_combo = QComboBox()
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
        self.trigger_type_combo = QComboBox()
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
        self.trigger_edge_combo = QComboBox()
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
        self.export_format_combo = QComboBox()
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
        self.refresh_equipment()
        self.refresh_sessions()

        if self.auto_refresh_check.isChecked():
            self.refresh_timer.start()

    def refresh_equipment(self):
        """Refresh equipment list."""
        if not self.client:
            return

        try:
            equipment_list = self.client.list_equipment()
            self.equipment_combo.clear()
            for eq in equipment_list:
                self.equipment_combo.addItem(
                    f"{eq.get('name', 'Unknown')} ({eq.get('equipment_type', '')})",
                    eq.get("equipment_id")
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
                self.sessions_list.addWidget(item)

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
        except Exception as e:
            logger.error(f"Error starting acquisition: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start:\n{str(e)}")

    def stop_acquisition(self):
        """Stop data acquisition."""
        if not self.current_acquisition_id:
            return

        try:
            result = self.client.stop_acquisition(self.current_acquisition_id)
            if result.get("success"):
                QMessageBox.information(self, "Success", "Acquisition stopped")
                self.acquisition_stopped.emit(self.current_acquisition_id)
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

            data_points = result.get("data", [])
            self.data_table.setRowCount(len(data_points))

            for row, point in enumerate(data_points):
                self.data_table.setItem(row, 0, QTableWidgetItem(str(point.get("timestamp", ""))))
                self.data_table.setItem(row, 1, QTableWidgetItem(str(point.get("channel", ""))))
                self.data_table.setItem(row, 2, QTableWidgetItem(str(point.get("value", ""))))
                self.data_table.setItem(row, 3, QTableWidgetItem(str(point.get("unit", ""))))

            logger.info(f"Loaded {len(data_points)} data points")

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load data:\n{str(e)}")

    def show_rolling_stats(self):
        """Show rolling statistics."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            result = self.client.get_acquisition_rolling_stats(self.current_acquisition_id)
            channels = result.get("channels", [])

            self.stats_table.setRowCount(0)
            for channel_stats in channels:
                channel = channel_stats.get("channel", "?")
                self._add_stat_row(f"{channel} - Mean", channel_stats.get("mean", 0), "")
                self._add_stat_row(f"{channel} - Std Dev", channel_stats.get("std_dev", 0), "")
                self._add_stat_row(f"{channel} - Min", channel_stats.get("min", 0), "")
                self._add_stat_row(f"{channel} - Max", channel_stats.get("max", 0), "")
                self._add_stat_row(f"{channel} - RMS", channel_stats.get("rms", 0), "")
                self._add_stat_row(f"{channel} - P2P", channel_stats.get("peak_to_peak", 0), "")

        except Exception as e:
            logger.error(f"Error getting rolling stats: {e}")
            QMessageBox.critical(self, "Error", f"Failed to get statistics:\n{str(e)}")

    def show_fft_analysis(self):
        """Show FFT analysis."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            result = self.client.get_acquisition_fft(self.current_acquisition_id)
            channels = result.get("channels", [])

            self.stats_table.setRowCount(0)
            for channel_fft in channels:
                channel = channel_fft.get("channel", "?")
                self._add_stat_row(f"{channel} - Fundamental Freq", channel_fft.get("fundamental_frequency", 0), "Hz")
                self._add_stat_row(f"{channel} - THD", channel_fft.get("thd", 0), "%")
                self._add_stat_row(f"{channel} - SNR", channel_fft.get("snr", 0), "dB")

        except Exception as e:
            logger.error(f"Error getting FFT analysis: {e}")
            QMessageBox.critical(self, "Error", f"Failed to get FFT:\n{str(e)}")

    def show_trend_analysis(self):
        """Show trend analysis."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            result = self.client.get_acquisition_trend(self.current_acquisition_id)
            channels = result.get("channels", [])

            self.stats_table.setRowCount(0)
            for channel_trend in channels:
                channel = channel_trend.get("channel", "?")
                self._add_stat_row(f"{channel} - Trend", channel_trend.get("trend", "unknown"), "")
                self._add_stat_row(f"{channel} - Slope", channel_trend.get("slope", 0), "")
                self._add_stat_row(f"{channel} - Confidence", channel_trend.get("confidence", 0), "")

        except Exception as e:
            logger.error(f"Error getting trend analysis: {e}")
            QMessageBox.critical(self, "Error", f"Failed to get trend:\n{str(e)}")

    def show_quality_metrics(self):
        """Show data quality metrics."""
        if not self.current_acquisition_id:
            QMessageBox.warning(self, "No Session", "Please select a session first")
            return

        try:
            result = self.client.get_acquisition_quality(self.current_acquisition_id)
            channels = result.get("channels", [])

            self.stats_table.setRowCount(0)
            for channel_quality in channels:
                channel = channel_quality.get("channel", "?")
                self._add_stat_row(f"{channel} - Quality Grade", channel_quality.get("quality_grade", "unknown"), "")
                self._add_stat_row(f"{channel} - Noise Level", channel_quality.get("noise_level", 0), "")
                self._add_stat_row(f"{channel} - Stability", channel_quality.get("stability_score", 0), "")
                self._add_stat_row(f"{channel} - Outlier Ratio", channel_quality.get("outlier_ratio", 0), "%")

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
