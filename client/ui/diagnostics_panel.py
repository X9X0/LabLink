"""Diagnostics panel for LabLink GUI."""

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from client.api.client import LabLinkClient

logger = logging.getLogger(__name__)


class DiagnosticsPanel(QWidget):
    """Panel for equipment diagnostics and health monitoring."""

    def __init__(self, parent=None):
        """Initialize diagnostics panel."""
        super().__init__(parent)

        self.client: Optional[LabLinkClient] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h2>Equipment Diagnostics</h2>")
        layout.addWidget(header)

        # Health table
        self.health_table = QTableWidget()
        self.health_table.setColumnCount(6)
        self.health_table.setHorizontalHeaderLabels(
            [
                "Equipment",
                "Health Status",
                "Score",
                "Connection",
                "Communication",
                "Performance",
            ]
        )
        self.health_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.health_table)

        # Buttons
        button_layout = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        button_layout.addWidget(refresh_btn)

        run_diagnostics_btn = QPushButton("Run Full Diagnostics")
        run_diagnostics_btn.clicked.connect(self.run_full_diagnostics)
        button_layout.addWidget(run_diagnostics_btn)

        benchmark_btn = QPushButton("Run Benchmark")
        benchmark_btn.clicked.connect(self.run_benchmark)
        button_layout.addWidget(benchmark_btn)

        pi_diagnostics_btn = QPushButton("Run Pi Diagnostics")
        pi_diagnostics_btn.clicked.connect(self.run_pi_diagnostics)
        pi_diagnostics_btn.setToolTip("Run comprehensive diagnostic script on the Raspberry Pi server")
        button_layout.addWidget(pi_diagnostics_btn)

        usb_diagnostics_btn = QPushButton("USB Device Diagnostics")
        usb_diagnostics_btn.clicked.connect(self.run_usb_diagnostics)
        usb_diagnostics_btn.setToolTip("Diagnose USB connection issues and unreadable serial numbers")
        button_layout.addWidget(usb_diagnostics_btn)

        layout.addLayout(button_layout)

    def set_client(self, client: LabLinkClient):
        """Set API client."""
        self.client = client

    def refresh(self):
        """Refresh diagnostics data."""
        if not self.client:
            return

        try:
            health_data = self.client.get_all_equipment_health()
            self.health_table.setRowCount(len(health_data))

            row = 0
            for eq_id, health in health_data.items():
                self.health_table.setItem(row, 0, QTableWidgetItem(eq_id))

                # Health status with color
                status = health.get("health_status", "unknown")
                status_item = QTableWidgetItem(status)

                if status == "healthy":
                    status_item.setBackground(QColor(200, 255, 200))
                elif status == "degraded":
                    status_item.setBackground(QColor(255, 255, 200))
                elif status == "warning":
                    status_item.setBackground(QColor(255, 230, 200))
                elif status == "critical":
                    status_item.setBackground(QColor(255, 200, 200))

                self.health_table.setItem(row, 1, status_item)

                # Health score
                score = health.get("health_score", 0)
                self.health_table.setItem(row, 2, QTableWidgetItem(f"{score:.1f}"))

                # Component statuses
                self.health_table.setItem(
                    row, 3, QTableWidgetItem(health.get("connection_status", ""))
                )
                self.health_table.setItem(
                    row, 4, QTableWidgetItem(health.get("communication_status", ""))
                )
                self.health_table.setItem(
                    row, 5, QTableWidgetItem(health.get("performance_status", ""))
                )

                row += 1

        except Exception as e:
            logger.error(f"Error refreshing diagnostics: {e}")

    def run_full_diagnostics(self):
        """Run full diagnostic report."""
        if not self.client:
            QMessageBox.warning(
                self, "Not Connected", "Please connect to a server first"
            )
            return

        try:
            report = self.client.generate_diagnostic_report()

            # Show summary
            overall_health = report.get("overall_health", "unknown")
            total_tests = report.get("total_tests", 0)
            passed_tests = report.get("passed_tests", 0)
            failed_tests = report.get("failed_tests", 0)

            message = f"Diagnostic Report:\n\n"
            message += f"Overall Health: {overall_health}\n"
            message += (
                f"Tests: {passed_tests}/{total_tests} passed, {failed_tests} failed\n\n"
            )

            if report.get("critical_issues"):
                message += "Critical Issues:\n"
                for issue in report["critical_issues"]:
                    message += f"  - {issue}\n"

            QMessageBox.information(self, "Diagnostic Report", message)

            self.refresh()

        except Exception as e:
            logger.error(f"Error running diagnostics: {e}")
            QMessageBox.critical(self, "Error", f"Diagnostics failed: {str(e)}")

    def run_benchmark(self):
        """Run performance benchmark on selected equipment."""
        if not self.client:
            QMessageBox.warning(
                self, "Not Connected", "Please connect to a server first"
            )
            return

        # Get selected equipment from table
        selected_rows = self.health_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select an equipment from the table to benchmark",
            )
            return

        # Get equipment ID from first column of selected row
        row = selected_rows[0].row()
        equipment_id = self.health_table.item(row, 0).text()

        try:
            # Run benchmark (returns benchmark dict directly)
            benchmark = self.client.run_benchmark(equipment_id)

            if benchmark:
                # Format benchmark results
                message = f"Performance Benchmark for {equipment_id}:\n\n"
                message += f"Overall Score: {benchmark.get('performance_score', 0):.1f}/100\n\n"

                message += "Command Latency:\n"
                latencies = benchmark.get("command_latency_ms", {})
                for cmd, latency in latencies.items():
                    if latency >= 0:
                        message += f"  {cmd}: {latency:.2f} ms\n"
                    else:
                        message += f"  {cmd}: FAILED\n"

                throughput = benchmark.get("throughput_commands_per_sec", 0)
                if throughput > 0:
                    message += f"\nThroughput: {throughput:.2f} commands/sec\n"

                cpu = benchmark.get("cpu_usage_percent")
                memory = benchmark.get("memory_usage_mb")
                if cpu is not None:
                    message += f"CPU Usage: {cpu:.1f}%\n"
                if memory is not None:
                    message += f"Memory Usage: {memory:.1f} MB\n"

                QMessageBox.information(self, "Benchmark Results", message)

                # Refresh health data
                self.refresh()
            else:
                QMessageBox.warning(
                    self,
                    "Benchmark Failed",
                    f"Could not run benchmark on {equipment_id}",
                )

        except Exception as e:
            logger.error(f"Error running benchmark: {e}")
            QMessageBox.critical(self, "Error", f"Benchmark failed: {str(e)}")

    def run_pi_diagnostics(self):
        """Run comprehensive Pi diagnostic script on the server."""
        if not self.client:
            QMessageBox.warning(
                self, "Not Connected", "Please connect to a server first"
            )
            return

        try:
            # Show progress dialog
            from PyQt6.QtWidgets import QProgressDialog
            progress = QProgressDialog(
                "Running Pi diagnostics...\nThis may take up to 60 seconds.",
                "Cancel",
                0, 0,
                self
            )
            progress.setWindowTitle("Pi Diagnostics")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()

            # Process events to show the dialog
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

            # Run diagnostics
            result = self.client.run_pi_diagnostics()

            progress.close()

            # Create and show results dialog
            from PyQt6.QtWidgets import QDialog, QTextEdit, QVBoxLayout
            dialog = QDialog(self)
            dialog.setWindowTitle("Raspberry Pi Diagnostics")
            dialog.resize(900, 700)

            layout = QVBoxLayout(dialog)

            # Add output in a scrollable text area
            output_text = QTextEdit()
            output_text.setReadOnly(True)
            output_text.setFontFamily("Monospace")
            output_text.setFontPointSize(9)
            output_text.setText(result.get("output", "No output"))
            layout.addWidget(output_text)

            # Add status info
            from PyQt6.QtWidgets import QLabel
            success = result.get("success", False)
            return_code = result.get("return_code", -1)
            status_text = f"Status: {'✓ Success' if success else '✗ Failed'} (exit code: {return_code})"
            status_label = QLabel(status_text)
            if success:
                status_label.setStyleSheet("color: green; font-weight: bold; padding: 5px;")
            else:
                status_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
            layout.addWidget(status_label)

            # Add buttons
            from PyQt6.QtWidgets import QDialogButtonBox, QHBoxLayout, QPushButton
            button_layout = QHBoxLayout()

            # Copy to clipboard button
            copy_btn = QPushButton("Copy to Clipboard")
            def copy_output():
                from PyQt6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(result.get("output", ""))
                QMessageBox.information(dialog, "Copied", "Diagnostic output copied to clipboard")
            copy_btn.clicked.connect(copy_output)
            button_layout.addWidget(copy_btn)

            # Save to file button
            save_btn = QPushButton("Save to File")
            def save_output():
                from PyQt6.QtWidgets import QFileDialog
                from datetime import datetime
                default_name = f"pi-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
                filename, _ = QFileDialog.getSaveFileName(
                    dialog,
                    "Save Diagnostic Output",
                    default_name,
                    "Text Files (*.txt);;All Files (*)"
                )
                if filename:
                    try:
                        with open(filename, 'w') as f:
                            f.write(result.get("output", ""))
                        QMessageBox.information(dialog, "Saved", f"Diagnostics saved to:\n{filename}")
                    except Exception as e:
                        QMessageBox.critical(dialog, "Error", f"Failed to save file:\n{str(e)}")
            save_btn.clicked.connect(save_output)
            button_layout.addWidget(save_btn)

            button_layout.addStretch()

            # Close button
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            dialog.exec()

        except Exception as e:
            logger.error(f"Error running Pi diagnostics: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to run Pi diagnostics:\n\n{str(e)}\n\n"
                "Make sure the diagnose-pi.sh script is installed on the server."
            )

    def run_usb_diagnostics(self):
        """Run USB device diagnostics to troubleshoot connection issues."""
        if not self.client:
            QMessageBox.warning(
                self, "Not Connected", "Please connect to a server first"
            )
            return

        # Ask user for resource string
        from PyQt6.QtWidgets import QInputDialog, QComboBox, QDialog, QVBoxLayout, QLabel

        # Get list of discovered devices to help user choose
        try:
            devices_response = self.client.discover_devices()
            devices = devices_response.get("devices", [])

            # Create dialog with device selection
            dialog = QDialog(self)
            dialog.setWindowTitle("Select Device for USB Diagnostics")
            dialog.resize(600, 200)

            layout = QVBoxLayout(dialog)

            layout.addWidget(QLabel("Select a device to diagnose:"))

            device_combo = QComboBox()
            for device in devices:
                resource_name = device.get("resource_name", "")
                if resource_name.startswith("USB"):
                    # Show resource name and any available device info
                    label = resource_name
                    if device.get("manufacturer"):
                        label += f" ({device['manufacturer']})"
                    device_combo.addItem(label, resource_name)

            if device_combo.count() == 0:
                device_combo.addItem("No USB devices found", "")

            layout.addWidget(device_combo)

            # Add manual entry option
            layout.addWidget(QLabel("\nOr enter a resource string manually:"))
            from PyQt6.QtWidgets import QLineEdit
            manual_input = QLineEdit()
            manual_input.setPlaceholderText("e.g., USB0::11975::37376::800886011797210043::0::INSTR")
            layout.addWidget(manual_input)

            # Buttons
            from PyQt6.QtWidgets import QDialogButtonBox
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Use manual input if provided, otherwise use selected device
                resource_string = manual_input.text().strip()
                if not resource_string:
                    resource_string = device_combo.currentData()

                if not resource_string:
                    QMessageBox.warning(self, "No Device", "Please select or enter a device")
                    return

                # Run diagnostics
                try:
                    diagnostics = self.client.run_usb_diagnostics(resource_string)

                    # Format and display results
                    message = f"USB Device Diagnostics\n"
                    message += f"{'=' * 50}\n\n"
                    message += f"Resource String: {diagnostics.get('resource_string', 'N/A')}\n\n"

                    usb_info = diagnostics.get('usb_info')
                    if usb_info:
                        message += f"USB Information:\n"
                        message += f"  Vendor ID:  {usb_info.get('vendor_id', 'N/A')}\n"
                        message += f"  Product ID: {usb_info.get('product_id', 'N/A')}\n"
                        message += f"  Serial Number: {usb_info.get('serial_number', 'N/A')}\n\n"

                    message += f"Serial Readable: {'Yes' if diagnostics.get('serial_readable') else 'No'}\n\n"

                    issues = diagnostics.get('issues', [])
                    if issues:
                        message += f"Issues Detected:\n"
                        for issue in issues:
                            message += f"  • {issue}\n"
                        message += "\n"

                    recommendations = diagnostics.get('recommendations', [])
                    if recommendations:
                        message += f"Recommendations:\n"
                        for rec in recommendations:
                            message += f"  • {rec}\n"

                    # Show results in a scrollable dialog
                    from PyQt6.QtWidgets import QTextEdit
                    result_dialog = QDialog(self)
                    result_dialog.setWindowTitle("USB Diagnostics Results")
                    result_dialog.resize(700, 500)

                    result_layout = QVBoxLayout(result_dialog)

                    text_edit = QTextEdit()
                    text_edit.setReadOnly(True)
                    text_edit.setPlainText(message)
                    text_edit.setFontFamily("Monospace")
                    result_layout.addWidget(text_edit)

                    close_btn = QPushButton("Close")
                    close_btn.clicked.connect(result_dialog.accept)
                    result_layout.addWidget(close_btn)

                    result_dialog.exec()

                except Exception as e:
                    logger.error(f"Error running USB diagnostics: {e}")
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Failed to run USB diagnostics:\n\n{str(e)}"
                    )

        except Exception as e:
            logger.error(f"Error preparing USB diagnostics: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to prepare USB diagnostics:\n\n{str(e)}"
            )
