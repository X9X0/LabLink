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
