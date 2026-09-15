"""The panel an instrument gets when nothing more specific exists.

Identity, the driver's ``get_state`` snapshot, and nothing else. In
particular no volts-and-amps dials: showing a scope supply controls is the
mistake this whole package exists to remove.
"""

import logging
from typing import Any, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem, QVBoxLayout)

from client.ui.instruments.base import POLL_STATE, InstrumentPanel

logger = logging.getLogger(__name__)


class GenericInstrumentPanel(InstrumentPanel):
    """Identity plus a live view of whatever the driver reports as state."""

    POLLS = POLL_STATE
    DEFAULT_INTERVAL_MS = 2000
    SETTINGS_TYPE = "generic"

    def _build_ui(self):
        layout = QVBoxLayout(self)

        identity = QGroupBox("Instrument")
        form = QFormLayout(identity)
        self.name_label = QLabel("-")
        self.type_label = QLabel("-")
        self.model_label = QLabel("-")
        self.resource_label = QLabel("-")
        self.idn_label = QLabel("-")
        self.idn_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Name:", self.name_label)
        form.addRow("Type:", self.type_label)
        form.addRow("Model:", self.model_label)
        form.addRow("Resource:", self.resource_label)
        form.addRow("Identification:", self.idn_label)
        layout.addWidget(identity)

        state_group = QGroupBox("State")
        state_layout = QVBoxLayout(state_group)
        self.state_table = QTableWidget(0, 2)
        self.state_table.setHorizontalHeaderLabels(["Setting", "Value"])
        self.state_table.horizontalHeader().setStretchLastSection(True)
        self.state_table.verticalHeader().setVisible(False)
        self.state_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        state_layout.addWidget(self.state_table)
        self.state_note = QLabel("")
        state_layout.addWidget(self.state_note)
        layout.addWidget(state_group, 1)

        row = QHBoxLayout()
        row.addWidget(self._create_rate_control("How often to re-read the instrument's state"))
        row.addStretch()
        layout.addLayout(row)

    # -- binding ----------------------------------------------------------

    def configure(self, capabilities: Dict[str, Any]):
        e = self.equipment
        self.name_label.setText(e.name if e else "-")
        etype = getattr(getattr(e, "equipment_type", None), "value", None) or "-"
        self.type_label.setText(str(etype))
        self.model_label.setText(f"{e.manufacturer} {e.model}" if e else "-")
        self.resource_label.setText(getattr(e, "resource_name", "-") or "-")
        self.idn_label.setText(getattr(e, "idn", None) or "-")
        self.state_table.setRowCount(0)
        self.state_note.setText("")

    def clear_instrument(self):
        for label in (self.name_label, self.type_label, self.model_label,
                      self.resource_label, self.idn_label):
            label.setText("-")
        self.state_table.setRowCount(0)
        self.state_note.setText("")

    # -- polling ----------------------------------------------------------

    async def poll(self):
        try:
            state = await self.send("get_state", {})
        except RuntimeError as e:
            # The driver has no get_state. That is a fact about the driver,
            # not a fault, and it will not change by asking again.
            if "unknown command" in str(e).lower():
                self.stop()
                self.state_note.setText("This driver does not report a state snapshot.")
                return
            raise
        self._show_state(state)

    def _show_state(self, state):
        rows = list(self._flatten(state)) if isinstance(state, dict) else [("state", str(state))]
        self.state_table.setRowCount(len(rows))
        for i, (key, value) in enumerate(rows):
            self.state_table.setItem(i, 0, QTableWidgetItem(str(key)))
            self.state_table.setItem(i, 1, QTableWidgetItem(str(value)))

    @staticmethod
    def _flatten(mapping: Dict[str, Any], prefix: str = ""):
        for key, value in mapping.items():
            name = f"{prefix}{key}"
            if isinstance(value, dict):
                yield from GenericInstrumentPanel._flatten(value, f"{name}.")
            else:
                yield name, value

    def show_not_connected(self):
        self.state_table.setRowCount(0)
        self.state_note.setText("Not connected. Connect it on the Equipment tab to read it.")
        self.status_message.emit("Not connected. Connect it on the Equipment tab to read it.")

    def show_unsupported(self):
        self.state_table.setRowCount(0)
        self.state_note.setText("This instrument does not report a state snapshot.")
