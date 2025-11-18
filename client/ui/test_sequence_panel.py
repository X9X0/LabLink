"""Test sequence builder panel for LabLink GUI."""

import asyncio
import json
import logging
from typing import Dict, List, Optional

import qasync
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from client.api.client import LabLinkClient

logger = logging.getLogger(__name__)


class TestSequenceWebSocketSignals(QObject):
    """Qt signals for WebSocket callbacks (thread-safe)."""

    execution_started = pyqtSignal(dict)  # Test execution started
    execution_progress = pyqtSignal(dict)  # Progress update
    execution_completed = pyqtSignal(dict)  # Test execution completed
    execution_failed = pyqtSignal(dict)  # Test execution failed
    step_completed = pyqtSignal(dict)  # Individual step completed


# Step type definitions
STEP_TYPES = [
    "setup",
    "command",
    "measurement",
    "delay",
    "validation",
    "sweep",
    "conditional",
    "loop",
    "cleanup",
]

VALIDATION_OPERATORS = ["==", "!=", "<", "<=", ">", ">=", "in_range", "out_of_range"]


class StepEditorDialog(QDialog):
    """Dialog for editing a test step."""

    def __init__(self, step_data: Optional[Dict] = None, parent=None):
        """Initialize step editor dialog.

        Args:
            step_data: Existing step data to edit (None for new step)
            parent: Parent widget
        """
        super().__init__(parent)
        self.step_data = step_data or {}
        self.setWindowTitle("Edit Test Step")
        self.resize(600, 500)
        self._setup_ui()

        # Load existing data if editing
        if step_data:
            self._load_step_data(step_data)

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Basic information
        basic_group = QGroupBox("Basic Information")
        basic_layout = QFormLayout()

        self.name_edit = QLineEdit()
        basic_layout.addRow("Step Name:", self.name_edit)

        self.step_type_combo = QComboBox()
        self.step_type_combo.addItems(STEP_TYPES)
        self.step_type_combo.currentTextChanged.connect(self._on_step_type_changed)
        basic_layout.addRow("Step Type:", self.step_type_combo)

        self.description_edit = QLineEdit()
        basic_layout.addRow("Description:", self.description_edit)

        self.equipment_id_edit = QLineEdit()
        basic_layout.addRow("Equipment ID:", self.equipment_id_edit)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # Step-specific configuration (changes based on step type)
        self.config_group = QGroupBox("Step Configuration")
        self.config_layout = QFormLayout()
        self.config_group.setLayout(self.config_layout)
        layout.addWidget(self.config_group)

        # Advanced options
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QFormLayout()

        self.critical_check = QCheckBox()
        self.critical_check.setChecked(True)
        advanced_layout.addRow("Critical (abort on fail):", self.critical_check)

        self.retry_check = QCheckBox()
        advanced_layout.addRow("Retry on failure:", self.retry_check)

        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(0, 10)
        advanced_layout.addRow("Max retries:", self.max_retries_spin)

        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Initialize with default step type
        self._on_step_type_changed(STEP_TYPES[0])

    def _on_step_type_changed(self, step_type: str):
        """Update configuration form based on step type.

        Args:
            step_type: Selected step type
        """
        # Clear existing configuration widgets
        while self.config_layout.rowCount() > 0:
            self.config_layout.removeRow(0)

        # Store references to config widgets
        self.config_widgets = {}

        if step_type == "command":
            self.config_widgets["command"] = QLineEdit()
            self.config_layout.addRow("SCPI Command:", self.config_widgets["command"])

            self.config_widgets["expected_response"] = QLineEdit()
            self.config_layout.addRow(
                "Expected Response:", self.config_widgets["expected_response"]
            )

        elif step_type == "measurement":
            self.config_widgets["measurement_type"] = QLineEdit()
            self.config_layout.addRow(
                "Measurement Type:", self.config_widgets["measurement_type"]
            )

            self.config_widgets["command"] = QLineEdit()
            self.config_layout.addRow(
                "Measurement Command:", self.config_widgets["command"]
            )

        elif step_type == "delay":
            self.config_widgets["delay_seconds"] = QDoubleSpinBox()
            self.config_widgets["delay_seconds"].setRange(0, 3600)
            self.config_widgets["delay_seconds"].setSingleStep(0.1)
            self.config_widgets["delay_seconds"].setSuffix(" seconds")
            self.config_layout.addRow("Delay:", self.config_widgets["delay_seconds"])

        elif step_type == "validation":
            self.config_widgets["validation_operator"] = QComboBox()
            self.config_widgets["validation_operator"].addItems(VALIDATION_OPERATORS)
            self.config_layout.addRow(
                "Operator:", self.config_widgets["validation_operator"]
            )

            self.config_widgets["validation_value"] = QDoubleSpinBox()
            self.config_widgets["validation_value"].setRange(-1e9, 1e9)
            self.config_widgets["validation_value"].setDecimals(6)
            self.config_layout.addRow("Value:", self.config_widgets["validation_value"])

            self.config_widgets["tolerance_percent"] = QDoubleSpinBox()
            self.config_widgets["tolerance_percent"].setRange(0, 100)
            self.config_widgets["tolerance_percent"].setSuffix(" %")
            self.config_layout.addRow(
                "Tolerance:", self.config_widgets["tolerance_percent"]
            )

        elif step_type == "sweep":
            self.config_widgets["sweep_parameter"] = QLineEdit()
            self.config_layout.addRow(
                "Parameter:", self.config_widgets["sweep_parameter"]
            )

            self.config_widgets["sweep_start"] = QDoubleSpinBox()
            self.config_widgets["sweep_start"].setRange(-1e9, 1e9)
            self.config_widgets["sweep_start"].setDecimals(3)
            self.config_layout.addRow("Start:", self.config_widgets["sweep_start"])

            self.config_widgets["sweep_stop"] = QDoubleSpinBox()
            self.config_widgets["sweep_stop"].setRange(-1e9, 1e9)
            self.config_widgets["sweep_stop"].setDecimals(3)
            self.config_layout.addRow("Stop:", self.config_widgets["sweep_stop"])

            self.config_widgets["sweep_points"] = QSpinBox()
            self.config_widgets["sweep_points"].setRange(2, 1000)
            self.config_layout.addRow("Points:", self.config_widgets["sweep_points"])

            self.config_widgets["measurement_type"] = QLineEdit()
            self.config_layout.addRow(
                "Measurement:", self.config_widgets["measurement_type"]
            )

        elif step_type == "loop":
            self.config_widgets["loop_count"] = QSpinBox()
            self.config_widgets["loop_count"].setRange(1, 1000)
            self.config_layout.addRow("Loop Count:", self.config_widgets["loop_count"])

            self.config_widgets["loop_start_step"] = QSpinBox()
            self.config_widgets["loop_start_step"].setRange(1, 1000)
            self.config_layout.addRow(
                "Start Step:", self.config_widgets["loop_start_step"]
            )

        elif step_type == "conditional":
            self.config_widgets["condition_expression"] = QLineEdit()
            self.config_layout.addRow(
                "Condition:", self.config_widgets["condition_expression"]
            )

            self.config_widgets["if_true_step"] = QSpinBox()
            self.config_widgets["if_true_step"].setRange(1, 1000)
            self.config_layout.addRow(
                "If True, goto:", self.config_widgets["if_true_step"]
            )

            self.config_widgets["if_false_step"] = QSpinBox()
            self.config_widgets["if_false_step"].setRange(1, 1000)
            self.config_layout.addRow(
                "If False, goto:", self.config_widgets["if_false_step"]
            )

        elif step_type in ["setup", "cleanup"]:
            self.config_widgets["command"] = QLineEdit()
            self.config_layout.addRow("SCPI Command:", self.config_widgets["command"])

    def _load_step_data(self, step_data: Dict):
        """Load step data into form.

        Args:
            step_data: Step data to load
        """
        self.name_edit.setText(step_data.get("name", ""))
        self.description_edit.setText(step_data.get("description", ""))
        self.equipment_id_edit.setText(step_data.get("equipment_id", ""))

        step_type = step_data.get("step_type", "setup")
        idx = self.step_type_combo.findText(step_type)
        if idx >= 0:
            self.step_type_combo.setCurrentIndex(idx)

        # Load advanced options
        self.critical_check.setChecked(step_data.get("critical", True))
        self.retry_check.setChecked(step_data.get("retry_on_fail", False))
        self.max_retries_spin.setValue(step_data.get("max_retries", 0))

        # Load step-specific configuration
        for key, widget in self.config_widgets.items():
            value = step_data.get(key)
            if value is not None:
                if isinstance(widget, QLineEdit):
                    widget.setText(str(value))
                elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                    widget.setValue(value)
                elif isinstance(widget, QComboBox):
                    idx = widget.findText(str(value))
                    if idx >= 0:
                        widget.setCurrentIndex(idx)

    def get_step_data(self) -> Dict:
        """Get step data from form.

        Returns:
            Step data dictionary
        """
        step_data = {
            "name": self.name_edit.text(),
            "step_type": self.step_type_combo.currentText(),
            "description": self.description_edit.text() or None,
            "equipment_id": self.equipment_id_edit.text() or None,
            "critical": self.critical_check.isChecked(),
            "retry_on_fail": self.retry_check.isChecked(),
            "max_retries": self.max_retries_spin.value(),
        }

        # Add step-specific configuration
        for key, widget in self.config_widgets.items():
            if isinstance(widget, QLineEdit):
                value = widget.text()
                step_data[key] = value if value else None
            elif isinstance(widget, QSpinBox):
                step_data[key] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                step_data[key] = widget.value()
            elif isinstance(widget, QComboBox):
                step_data[key] = widget.currentText()

        return step_data


class TemplateDialog(QDialog):
    """Dialog for creating sequence from template."""

    def __init__(self, templates: List[str], parent=None):
        """Initialize template dialog.

        Args:
            templates: List of available template names
            parent: Parent widget
        """
        super().__init__(parent)
        self.templates = templates
        self.setWindowTitle("Create from Template")
        self.resize(500, 400)
        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Template selection
        template_label = QLabel("Select Template:")
        layout.addWidget(template_label)

        self.template_list = QListWidget()
        self.template_list.addItems(self.templates)
        self.template_list.currentRowChanged.connect(self._on_template_selected)
        layout.addWidget(self.template_list)

        # Template parameters
        self.params_group = QGroupBox("Template Parameters")
        self.params_layout = QFormLayout()

        self.equipment_id_edit = QLineEdit()
        self.params_layout.addRow("Equipment ID:", self.equipment_id_edit)

        # Voltage accuracy parameters
        self.test_points_edit = QLineEdit()
        self.test_points_edit.setPlaceholderText("e.g., 1.0, 2.5, 5.0, 10.0")
        self.params_layout.addRow("Test Points (comma-separated):", self.test_points_edit)

        # Frequency response parameters
        self.start_freq_spin = QDoubleSpinBox()
        self.start_freq_spin.setRange(0, 1e9)
        self.start_freq_spin.setSuffix(" Hz")
        self.params_layout.addRow("Start Frequency:", self.start_freq_spin)

        self.stop_freq_spin = QDoubleSpinBox()
        self.stop_freq_spin.setRange(0, 1e9)
        self.stop_freq_spin.setSuffix(" Hz")
        self.params_layout.addRow("Stop Frequency:", self.stop_freq_spin)

        self.params_group.setLayout(self.params_layout)
        layout.addWidget(self.params_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Initial state
        self._on_template_selected(0)

    def _on_template_selected(self, index: int):
        """Update parameter visibility based on selected template.

        Args:
            index: Selected template index
        """
        if index < 0 or index >= len(self.templates):
            return

        template_name = self.templates[index]

        # Show/hide parameters based on template
        if template_name == "voltage_accuracy":
            self.test_points_edit.setVisible(True)
            self.params_layout.labelForField(self.test_points_edit).setVisible(True)
            self.start_freq_spin.setVisible(False)
            self.params_layout.labelForField(self.start_freq_spin).setVisible(False)
            self.stop_freq_spin.setVisible(False)
            self.params_layout.labelForField(self.stop_freq_spin).setVisible(False)
        elif template_name == "frequency_response":
            self.test_points_edit.setVisible(False)
            self.params_layout.labelForField(self.test_points_edit).setVisible(False)
            self.start_freq_spin.setVisible(True)
            self.params_layout.labelForField(self.start_freq_spin).setVisible(True)
            self.stop_freq_spin.setVisible(True)
            self.params_layout.labelForField(self.stop_freq_spin).setVisible(True)

    def get_template_config(self) -> Dict:
        """Get template configuration.

        Returns:
            Template configuration dictionary
        """
        current_item = self.template_list.currentItem()
        if not current_item:
            return {}

        template_name = current_item.text()
        equipment_id = self.equipment_id_edit.text()

        config = {
            "template_name": template_name,
            "equipment_id": equipment_id,
        }

        if template_name == "voltage_accuracy":
            test_points_str = self.test_points_edit.text()
            if test_points_str:
                test_points = [
                    float(x.strip()) for x in test_points_str.split(",") if x.strip()
                ]
                config["test_points"] = test_points
        elif template_name == "frequency_response":
            config["start_freq"] = self.start_freq_spin.value()
            config["stop_freq"] = self.stop_freq_spin.value()

        return config


class TestSequencePanel(QWidget):
    """Panel for test sequence builder and management."""

    def __init__(self, parent=None):
        """Initialize test sequence panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None
        self.current_sequence: Dict = {}
        self.steps: List[Dict] = []
        self.execution_id: Optional[str] = None
        self.progress_timer: Optional[QTimer] = None

        # WebSocket streaming state
        self.ws_signals = TestSequenceWebSocketSignals()
        self.test_streaming_active = False

        self._setup_ui()
        self._connect_ws_signals()

    def _setup_ui(self):
        """Set up user interface."""
        main_layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Test Sequence Builder</h2>")
        main_layout.addWidget(header)

        # Create tabs for different views
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Builder tab
        self.builder_tab = QWidget()
        self._setup_builder_tab()
        self.tab_widget.addTab(self.builder_tab, "Build Sequence")

        # Execution tab
        self.execution_tab = QWidget()
        self._setup_execution_tab()
        self.tab_widget.addTab(self.execution_tab, "Execute & Monitor")

        # Templates tab
        self.templates_tab = QWidget()
        self._setup_templates_tab()
        self.tab_widget.addTab(self.templates_tab, "Templates")

    def _setup_builder_tab(self):
        """Set up the sequence builder tab."""
        layout = QVBoxLayout(self.builder_tab)

        # Sequence metadata
        metadata_group = QGroupBox("Sequence Information")
        metadata_layout = QFormLayout()

        self.sequence_name_edit = QLineEdit()
        metadata_layout.addRow("Sequence Name:", self.sequence_name_edit)

        self.sequence_desc_edit = QLineEdit()
        metadata_layout.addRow("Description:", self.sequence_desc_edit)

        self.sequence_category_combo = QComboBox()
        self.sequence_category_combo.addItems(
            ["acceptance", "characterization", "regression", "stress", "other"]
        )
        metadata_layout.addRow("Category:", self.sequence_category_combo)

        metadata_group.setLayout(metadata_layout)
        layout.addWidget(metadata_group)

        # Steps table
        steps_label = QLabel("<b>Test Steps</b>")
        layout.addWidget(steps_label)

        self.steps_table = QTableWidget()
        self.steps_table.setColumnCount(5)
        self.steps_table.setHorizontalHeaderLabels(
            ["#", "Name", "Type", "Equipment", "Config"]
        )
        self.steps_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.steps_table)

        # Step buttons
        step_buttons_layout = QHBoxLayout()

        add_step_btn = QPushButton("Add Step")
        add_step_btn.clicked.connect(self._add_step)
        step_buttons_layout.addWidget(add_step_btn)

        edit_step_btn = QPushButton("Edit Step")
        edit_step_btn.clicked.connect(self._edit_step)
        step_buttons_layout.addWidget(edit_step_btn)

        delete_step_btn = QPushButton("Delete Step")
        delete_step_btn.clicked.connect(self._delete_step)
        step_buttons_layout.addWidget(delete_step_btn)

        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._move_step_up)
        step_buttons_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._move_step_down)
        step_buttons_layout.addWidget(move_down_btn)

        step_buttons_layout.addStretch()
        layout.addLayout(step_buttons_layout)

        # Save/Load buttons
        save_load_layout = QHBoxLayout()

        save_btn = QPushButton("Save Sequence")
        save_btn.clicked.connect(self._save_sequence)
        save_load_layout.addWidget(save_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_sequence)
        save_load_layout.addWidget(clear_btn)

        export_btn = QPushButton("Export JSON")
        export_btn.clicked.connect(self._export_sequence)
        save_load_layout.addWidget(export_btn)

        save_load_layout.addStretch()
        layout.addLayout(save_load_layout)

    def _setup_execution_tab(self):
        """Set up the execution and monitoring tab."""
        layout = QVBoxLayout(self.execution_tab)

        # Execution controls
        controls_group = QGroupBox("Execution Controls")
        controls_layout = QVBoxLayout()

        # Equipment selection
        equipment_layout = QFormLayout()
        self.exec_equipment_edit = QLineEdit()
        equipment_layout.addRow("Equipment ID:", self.exec_equipment_edit)
        controls_layout.addLayout(equipment_layout)

        # Execution buttons
        exec_buttons = QHBoxLayout()

        self.execute_btn = QPushButton("Execute Sequence")
        self.execute_btn.clicked.connect(self._execute_sequence)
        exec_buttons.addWidget(self.execute_btn)

        self.abort_btn = QPushButton("Abort")
        self.abort_btn.clicked.connect(self._abort_execution)
        self.abort_btn.setEnabled(False)
        exec_buttons.addWidget(self.abort_btn)

        exec_buttons.addStretch()
        controls_layout.addLayout(exec_buttons)

        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # Progress display
        progress_group = QGroupBox("Execution Progress")
        progress_layout = QVBoxLayout()

        self.progress_label = QLabel("Ready to execute")
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)

        # Current step info
        self.current_step_label = QLabel("Current Step: --")
        progress_layout.addWidget(self.current_step_label)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # Results display
        results_group = QGroupBox("Execution Results")
        results_layout = QVBoxLayout()

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        results_layout.addWidget(self.results_text)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

    def _setup_templates_tab(self):
        """Set up the templates tab."""
        layout = QVBoxLayout(self.templates_tab)

        # Header
        header = QLabel("<h3>Available Test Templates</h3>")
        layout.addWidget(header)

        # Templates list
        self.templates_list = QListWidget()
        layout.addWidget(self.templates_list)

        # Template info
        self.template_info = QTextEdit()
        self.template_info.setReadOnly(True)
        self.template_info.setMaximumHeight(150)
        layout.addWidget(self.template_info)

        # Buttons
        template_buttons = QHBoxLayout()

        refresh_templates_btn = QPushButton("Refresh Templates")
        refresh_templates_btn.clicked.connect(self._load_templates)
        template_buttons.addWidget(refresh_templates_btn)

        use_template_btn = QPushButton("Create from Template")
        use_template_btn.clicked.connect(self._create_from_template)
        template_buttons.addWidget(use_template_btn)

        template_buttons.addStretch()
        layout.addLayout(template_buttons)

    def set_client(self, client: LabLinkClient):
        """Set API client.

        Args:
            client: LabLink API client
        """
        self.client = client
        self._load_templates()
        self._register_ws_handlers()

    def _connect_ws_signals(self):
        """Connect WebSocket signals to slot handlers."""
        self.ws_signals.execution_started.connect(self._on_execution_started)
        self.ws_signals.execution_progress.connect(self._on_execution_progress)
        self.ws_signals.execution_completed.connect(self._on_execution_completed)
        self.ws_signals.execution_failed.connect(self._on_execution_failed)
        self.ws_signals.step_completed.connect(self._on_step_completed)

    def _register_ws_handlers(self):
        """Register WebSocket message handlers with the client."""
        if not self.client or not self.client.ws_manager:
            return

        try:
            logger.info("Registering WebSocket test execution event handlers")
            if hasattr(self.client.ws_manager, "on_test_event"):
                self.client.ws_manager.on_test_event(self._ws_test_callback)
            logger.info("Registered WebSocket test handlers for test panel")
        except Exception as e:
            logger.warning(f"Could not register WebSocket test handlers: {e}")

    def _ws_test_callback(self, message: Dict):
        """WebSocket callback for test execution events.

        Args:
            message: WebSocket message with test event data
        """
        event_type = message.get("type")
        event_data = message.get("data", {})

        if event_type == "execution_started":
            self.ws_signals.execution_started.emit(event_data)
        elif event_type == "execution_progress":
            self.ws_signals.execution_progress.emit(event_data)
        elif event_type == "execution_completed":
            self.ws_signals.execution_completed.emit(event_data)
        elif event_type == "execution_failed":
            self.ws_signals.execution_failed.emit(event_data)
        elif event_type == "step_completed":
            self.ws_signals.step_completed.emit(event_data)

    def _on_execution_started(self, data: Dict):
        """Handle execution started event."""
        logger.info(f"Test execution started: {data.get('execution_id')}")
        self.progress_label.setText("Execution started...")
        self.execute_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)

    def _on_execution_progress(self, data: Dict):
        """Handle execution progress event."""
        current_step = data.get("current_step", 0)
        total_steps = data.get("total_steps", 1)
        progress = int((current_step / total_steps) * 100)
        self.progress_bar.setValue(progress)
        self.current_step_label.setText(f"Current Step: {current_step}/{total_steps}")

    def _on_execution_completed(self, data: Dict):
        """Handle execution completed event."""
        logger.info(f"Test execution completed: {data}")
        self.progress_label.setText("Execution completed!")
        self.progress_bar.setValue(100)
        self.execute_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)

        # Display results
        self._display_results(data)

    def _on_execution_failed(self, data: Dict):
        """Handle execution failed event."""
        logger.error(f"Test execution failed: {data}")
        self.progress_label.setText("Execution failed!")
        self.execute_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self._display_results(data)

    def _on_step_completed(self, data: Dict):
        """Handle step completed event."""
        step_num = data.get("step_number", "?")
        step_name = data.get("name", "Unknown")
        passed = data.get("passed", False)
        status_text = "PASSED" if passed else "FAILED"

        self.results_text.append(f"Step {step_num}: {step_name} - {status_text}")

    def _add_step(self):
        """Add a new test step."""
        dialog = StepEditorDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            step_data = dialog.get_step_data()
            step_data["step_number"] = len(self.steps) + 1
            self.steps.append(step_data)
            self._update_steps_table()

    def _edit_step(self):
        """Edit the selected test step."""
        current_row = self.steps_table.currentRow()
        if current_row < 0 or current_row >= len(self.steps):
            QMessageBox.warning(self, "No Selection", "Please select a step to edit.")
            return

        step_data = self.steps[current_row]
        dialog = StepEditorDialog(step_data, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_data = dialog.get_step_data()
            updated_data["step_number"] = current_row + 1
            self.steps[current_row] = updated_data
            self._update_steps_table()

    def _delete_step(self):
        """Delete the selected test step."""
        current_row = self.steps_table.currentRow()
        if current_row < 0 or current_row >= len(self.steps):
            QMessageBox.warning(self, "No Selection", "Please select a step to delete.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this step?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self.steps[current_row]
            # Renumber steps
            for i, step in enumerate(self.steps):
                step["step_number"] = i + 1
            self._update_steps_table()

    def _move_step_up(self):
        """Move the selected step up in the sequence."""
        current_row = self.steps_table.currentRow()
        if current_row <= 0:
            return

        self.steps[current_row], self.steps[current_row - 1] = (
            self.steps[current_row - 1],
            self.steps[current_row],
        )
        # Renumber
        for i, step in enumerate(self.steps):
            step["step_number"] = i + 1
        self._update_steps_table()
        self.steps_table.setCurrentCell(current_row - 1, 0)

    def _move_step_down(self):
        """Move the selected step down in the sequence."""
        current_row = self.steps_table.currentRow()
        if current_row < 0 or current_row >= len(self.steps) - 1:
            return

        self.steps[current_row], self.steps[current_row + 1] = (
            self.steps[current_row + 1],
            self.steps[current_row],
        )
        # Renumber
        for i, step in enumerate(self.steps):
            step["step_number"] = i + 1
        self._update_steps_table()
        self.steps_table.setCurrentCell(current_row + 1, 0)

    def _update_steps_table(self):
        """Update the steps table display."""
        self.steps_table.setRowCount(len(self.steps))

        for i, step in enumerate(self.steps):
            self.steps_table.setItem(i, 0, QTableWidgetItem(str(step["step_number"])))
            self.steps_table.setItem(i, 1, QTableWidgetItem(step.get("name", "")))
            self.steps_table.setItem(i, 2, QTableWidgetItem(step.get("step_type", "")))
            self.steps_table.setItem(
                i, 3, QTableWidgetItem(step.get("equipment_id", ""))
            )

            # Create a short config summary
            config_summary = self._get_config_summary(step)
            self.steps_table.setItem(i, 4, QTableWidgetItem(config_summary))

    def _get_config_summary(self, step: Dict) -> str:
        """Get a short summary of step configuration.

        Args:
            step: Step data

        Returns:
            Configuration summary string
        """
        step_type = step.get("step_type", "")

        if step_type == "command":
            return f"CMD: {step.get('command', '')}"
        elif step_type == "measurement":
            return f"MEAS: {step.get('measurement_type', '')}"
        elif step_type == "delay":
            return f"DELAY: {step.get('delay_seconds', 0)}s"
        elif step_type == "validation":
            op = step.get("validation_operator", "")
            val = step.get("validation_value", "")
            return f"VALID: {op} {val}"
        elif step_type == "sweep":
            param = step.get("sweep_parameter", "")
            start = step.get("sweep_start", "")
            stop = step.get("sweep_stop", "")
            return f"SWEEP: {param} [{start} to {stop}]"
        elif step_type == "loop":
            count = step.get("loop_count", "")
            return f"LOOP: {count}x"
        elif step_type == "conditional":
            cond = step.get("condition_expression", "")
            return f"IF: {cond}"
        else:
            return step.get("description", "")[:30]

    def _save_sequence(self):
        """Save the current sequence."""
        if not self.client:
            QMessageBox.warning(self, "No Connection", "Not connected to server.")
            return

        if not self.sequence_name_edit.text():
            QMessageBox.warning(self, "No Name", "Please enter a sequence name.")
            return

        if not self.steps:
            QMessageBox.warning(self, "No Steps", "Please add at least one step.")
            return

        sequence_data = {
            "name": self.sequence_name_edit.text(),
            "description": self.sequence_desc_edit.text() or None,
            "category": self.sequence_category_combo.currentText(),
            "steps": self.steps,
            "equipment_ids": list(
                set(
                    step.get("equipment_id")
                    for step in self.steps
                    if step.get("equipment_id")
                )
            ),
        }

        try:
            result = self.client.create_test_sequence(sequence_data)
            QMessageBox.information(
                self,
                "Success",
                f"Test sequence saved successfully!\nID: {result.get('sequence_id')}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save sequence: {e}")
            logger.error(f"Failed to save test sequence: {e}", exc_info=True)

    def _clear_sequence(self):
        """Clear the current sequence."""
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear the sequence?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.sequence_name_edit.clear()
            self.sequence_desc_edit.clear()
            self.steps.clear()
            self._update_steps_table()

    def _export_sequence(self):
        """Export sequence to JSON."""
        if not self.steps:
            QMessageBox.warning(
                self, "No Steps", "Please add steps before exporting."
            )
            return

        sequence_data = {
            "name": self.sequence_name_edit.text() or "Untitled",
            "description": self.sequence_desc_edit.text() or None,
            "category": self.sequence_category_combo.currentText(),
            "steps": self.steps,
        }

        json_str = json.dumps(sequence_data, indent=2)

        # Show in dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Sequence JSON")
        dialog.resize(600, 400)

        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setPlainText(json_str)
        layout.addWidget(text_edit)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    @qasync.asyncSlot()
    async def _execute_sequence(self):
        """Execute the current test sequence."""
        if not self.client:
            QMessageBox.warning(self, "No Connection", "Not connected to server.")
            return

        if not self.steps:
            QMessageBox.warning(self, "No Steps", "Please add steps to execute.")
            return

        equipment_id = self.exec_equipment_edit.text()
        if not equipment_id:
            QMessageBox.warning(
                self, "No Equipment", "Please specify an equipment ID."
            )
            return

        sequence_data = {
            "name": self.sequence_name_edit.text() or "Unnamed Sequence",
            "description": self.sequence_desc_edit.text() or None,
            "steps": self.steps,
            "equipment_ids": [equipment_id],
        }

        try:
            # Clear previous results
            self.results_text.clear()
            self.progress_bar.setValue(0)
            self.progress_label.setText("Starting execution...")

            result = self.client.execute_test_sequence(
                sequence_data, executed_by="user", environment={}
            )

            self.execution_id = result.get("execution_id")
            logger.info(f"Started test execution: {self.execution_id}")

            # Start polling for progress
            self._start_progress_polling()

        except Exception as e:
            QMessageBox.critical(self, "Execution Error", f"Failed to execute: {e}")
            logger.error(f"Failed to execute test sequence: {e}", exc_info=True)

    def _start_progress_polling(self):
        """Start polling for execution progress."""
        if self.progress_timer:
            self.progress_timer.stop()

        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._poll_execution_status)
        self.progress_timer.start(1000)  # Poll every 1 second

        self.execute_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)

    def _poll_execution_status(self):
        """Poll for execution status."""
        if not self.execution_id or not self.client:
            return

        try:
            status = self.client.get_execution_status(self.execution_id)

            # Update progress
            current_step = status.get("current_step", 0)
            total_steps = status.get("total_steps", 1)
            if total_steps > 0:
                progress = int((current_step / total_steps) * 100)
                self.progress_bar.setValue(progress)
                self.current_step_label.setText(
                    f"Current Step: {current_step}/{total_steps}"
                )

            # Check if completed
            exec_status = status.get("status", "")
            if exec_status in ["passed", "failed", "aborted", "error"]:
                self.progress_timer.stop()
                self.execute_btn.setEnabled(True)
                self.abort_btn.setEnabled(False)
                self._display_results(status)

        except Exception as e:
            logger.error(f"Failed to poll execution status: {e}")

    @qasync.asyncSlot()
    async def _abort_execution(self):
        """Abort the current execution."""
        if not self.execution_id or not self.client:
            return

        try:
            self.client.abort_test_execution(self.execution_id)
            self.progress_label.setText("Aborting execution...")
        except Exception as e:
            QMessageBox.critical(self, "Abort Error", f"Failed to abort: {e}")

    def _display_results(self, results: Dict):
        """Display execution results.

        Args:
            results: Execution results dictionary
        """
        self.results_text.clear()

        status = results.get("status", "unknown")
        self.results_text.append(f"<h3>Test Results</h3>")
        self.results_text.append(f"<b>Status:</b> {status.upper()}")
        self.results_text.append(
            f"<b>Total Steps:</b> {results.get('total_steps', 0)}"
        )
        self.results_text.append(
            f"<b>Passed Steps:</b> {results.get('passed_steps', 0)}"
        )
        self.results_text.append(
            f"<b>Failed Steps:</b> {results.get('failed_steps', 0)}"
        )
        self.results_text.append(f"<b>Pass Rate:</b> {results.get('pass_rate', 0):.1f}%")
        self.results_text.append(
            f"<b>Duration:</b> {results.get('duration_seconds', 0):.2f}s"
        )

        # Step details
        steps = results.get("steps", [])
        if steps:
            self.results_text.append("<h4>Step Details:</h4>")
            for step in steps:
                step_num = step.get("step_number", "?")
                step_name = step.get("name", "Unknown")
                step_status = step.get("status", "unknown")
                passed = step.get("passed", None)

                if passed is True:
                    status_color = "green"
                    status_text = "PASSED"
                elif passed is False:
                    status_color = "red"
                    status_text = "FAILED"
                else:
                    status_color = "gray"
                    status_text = step_status

                self.results_text.append(
                    f"<span style='color:{status_color};'>[{step_num}] {step_name}: {status_text}</span>"
                )

                # Show measured value if available
                if step.get("measured_value") is not None:
                    self.results_text.append(
                        f"   Measured: {step['measured_value']}"
                    )

                # Show error if any
                if step.get("error_message"):
                    self.results_text.append(
                        f"   <span style='color:red;'>Error: {step['error_message']}</span>"
                    )

    @qasync.asyncSlot()
    async def _load_templates(self):
        """Load available test templates."""
        if not self.client:
            return

        try:
            result = self.client.list_test_templates()
            templates = result.get("templates", [])

            self.templates_list.clear()
            self.templates_list.addItems(templates)

            # Show template info
            info_text = "<h4>Available Templates:</h4><ul>"
            if "voltage_accuracy" in templates:
                info_text += "<li><b>voltage_accuracy</b>: Test voltage accuracy at multiple points with tolerance validation</li>"
            if "frequency_response" in templates:
                info_text += "<li><b>frequency_response</b>: Sweep frequency range and measure amplitude response</li>"
            info_text += "</ul>"
            self.template_info.setHtml(info_text)

        except Exception as e:
            logger.error(f"Failed to load templates: {e}")

    @qasync.asyncSlot()
    async def _create_from_template(self):
        """Create a sequence from a template."""
        if not self.client:
            QMessageBox.warning(self, "No Connection", "Not connected to server.")
            return

        # Get templates
        try:
            result = self.client.list_test_templates()
            templates = result.get("templates", [])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load templates: {e}")
            return

        if not templates:
            QMessageBox.information(
                self, "No Templates", "No templates available on server."
            )
            return

        # Show template dialog
        dialog = TemplateDialog(templates, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        config = dialog.get_template_config()
        if not config:
            return

        # Create sequence from template
        try:
            sequence = self.client.create_from_template(
                template_name=config["template_name"],
                equipment_id=config["equipment_id"],
                test_points=config.get("test_points"),
                start_freq=config.get("start_freq"),
                stop_freq=config.get("stop_freq"),
            )

            # Load into builder
            self.sequence_name_edit.setText(sequence.get("name", ""))
            self.sequence_desc_edit.setText(sequence.get("description", ""))

            category = sequence.get("category", "acceptance")
            idx = self.sequence_category_combo.findText(category)
            if idx >= 0:
                self.sequence_category_combo.setCurrentIndex(idx)

            self.steps = sequence.get("steps", [])
            self._update_steps_table()

            # Switch to builder tab
            self.tab_widget.setCurrentIndex(0)

            QMessageBox.information(
                self, "Success", "Template loaded successfully into builder!"
            )

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to create from template: {e}"
            )
            logger.error(f"Failed to create from template: {e}", exc_info=True)

    def refresh(self):
        """Refresh panel data."""
        self._load_templates()
