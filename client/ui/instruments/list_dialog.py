"""The list sequence editor, in a dialog of its own.

A list is a profile the instrument runs itself: each step has a level,
a dwell and a slew rate, and the load walks them on its own clock.
Dwell goes down to 50 microseconds, which is the whole point -- a test
sequence step is a host-side sleep and an HTTP round trip, so anything
under about a tenth of a second can only be done here.

In a dialog rather than the panel because a list is configuration, not
monitoring. It is built, sent, armed, and then the operator watches
the ordinary readouts while it runs; a step table sitting on the panel
would cost the readouts their height for something looked at once.
"""

import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QSpinBox,
                             QTableWidget, QTableWidgetItem, QVBoxLayout)

logger = logging.getLogger(__name__)

#: What the instrument will accept, from the programming guide.
#:
#: The minimum of two steps is the load's, not ours: ":SOURce:LIST:STEP
#: ... Its range is from 2 to 512". A one-step list is not a list.
MIN_STEPS = 2
MAX_STEPS = 512
MAX_CYCLES = 99999

#: Dwell per step, in seconds. The lower bound is what makes a list
#: worth having: 50us is three orders of magnitude below anything the
#: host can time.
MIN_WIDTH = 0.00005
MAX_WIDTH = 3600.0

#: Regulation laws a list can run under, and the unit its levels carry.
LIST_MODES = (("CC", "A"), ("CV", "V"), ("CR", "Ohm"), ("CP", "W"))


class ListDialog(QDialog):
    """Build a list sequence and send it to the load."""

    def __init__(self, parent=None, max_current: float = 40.0):
        super().__init__(parent)
        self.setWindowTitle("List sequence")
        self.setModal(False)
        self._max_level = max_current
        self._build_ui()
        self._set_step_count(MIN_STEPS)

    # ------------------------------------------------------------------ #
    # Building
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        layout = QVBoxLayout(self)

        head = QGridLayout()
        head.addWidget(QLabel("Mode:"), 0, 0)
        self.mode_combo = QComboBox()
        for key, unit in LIST_MODES:
            self.mode_combo.addItem(f"{key}  ({unit})", key)
        self.mode_combo.currentIndexChanged.connect(self._relabel_columns)
        self.mode_combo.setToolTip(
            "The regulation law the list runs under. Separate from the\n"
            "panel's mode: a list in CC steps through currents whatever\n"
            "the load was doing before."
        )
        head.addWidget(self.mode_combo, 0, 1)

        head.addWidget(QLabel("Cycles:"), 0, 2)
        self.cycles_spin = QSpinBox()
        self.cycles_spin.setRange(0, MAX_CYCLES)
        self.cycles_spin.setValue(1)
        self.cycles_spin.setToolTip(
            "How many times the whole list runs. Zero repeats until "
            "something stops it."
        )
        head.addWidget(self.cycles_spin, 0, 3)

        head.addWidget(QLabel("When it ends:"), 0, 4)
        self.end_combo = QComboBox()
        self.end_combo.addItem("Hold the last step", True)
        self.end_combo.addItem("Switch the input off", False)
        self.end_combo.setToolTip(
            "What the input does once the last cycle finishes.")
        head.addWidget(self.end_combo, 0, 5)
        head.setColumnStretch(6, 1)
        layout.addLayout(head)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Level (A)", "Dwell (s)", "Slew (A/us)"])
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setToolTip(
            "One row per step. Dwell is how long the load holds that\n"
            "level; slew is how fast it gets there."
        )
        layout.addWidget(self.table)

        row = QHBoxLayout()
        self.add_button = QPushButton("Add step")
        self.add_button.clicked.connect(self._add_step)
        row.addWidget(self.add_button)

        self.remove_button = QPushButton("Remove step")
        self.remove_button.clicked.connect(self._remove_step)
        row.addWidget(self.remove_button)

        self.step_count_label = QLabel()
        row.addWidget(self.step_count_label)
        row.addStretch()
        layout.addLayout(row)

        self.buttons = QDialogButtonBox()
        self.send_button = self.buttons.addButton(
            "Send to load", QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._relabel_columns()

    # ------------------------------------------------------------------ #
    # The table
    # ------------------------------------------------------------------ #

    def _spin(self, minimum, maximum, decimals, value, step):
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setSingleStep(step)
        box.setValue(value)
        return box

    def _add_step(self):
        if self.table.rowCount() >= MAX_STEPS:
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setCellWidget(
            row, 0, self._spin(0.0, self._max_level, 3, 0.0, 0.1))
        # Dwell defaults to a tenth of a second: long enough to watch,
        # short enough to say this is not a host-timed sequence.
        self.table.setCellWidget(
            row, 1, self._spin(MIN_WIDTH, MAX_WIDTH, 5, 0.1, 0.01))
        self.table.setCellWidget(
            row, 2, self._spin(0.001, 100.0, 3, 0.5, 0.01))
        self._show_step_count()

    def _remove_step(self):
        if self.table.rowCount() <= MIN_STEPS:
            return
        chosen = self.table.currentRow()
        self.table.removeRow(chosen if chosen >= 0
                             else self.table.rowCount() - 1)
        self._show_step_count()

    def _set_step_count(self, count: int):
        while self.table.rowCount() < count:
            self._add_step()
        while self.table.rowCount() > count:
            self.table.removeRow(self.table.rowCount() - 1)
        self._show_step_count()

    def _show_step_count(self):
        count = self.table.rowCount()
        self.step_count_label.setText(f"{count} step(s)")
        self.remove_button.setEnabled(count > MIN_STEPS)
        self.add_button.setEnabled(count < MAX_STEPS)

    def _relabel_columns(self):
        """The levels are amps, volts, ohms or watts by mode."""
        mode = self.mode_combo.currentData() or "CC"
        unit = dict(LIST_MODES).get(mode, "A")
        self.table.setHorizontalHeaderLabels(
            [f"Level ({unit})", "Dwell (s)", f"Slew ({unit}/us)"])

    # ------------------------------------------------------------------ #
    # What the caller sends
    # ------------------------------------------------------------------ #

    def steps(self) -> List[Dict[str, float]]:
        """Every row, in order, numbered from 1 as the panel counts."""
        out = []
        for row in range(self.table.rowCount()):
            out.append({
                "step": row + 1,
                "level": self.table.cellWidget(row, 0).value(),
                "width": self.table.cellWidget(row, 1).value(),
                "slew": self.table.cellWidget(row, 2).value(),
            })
        return out

    def settings(self) -> Dict[str, Any]:
        return {
            "mode": self.mode_combo.currentData() or "CC",
            "cycles": self.cycles_spin.value(),
            "step_count": self.table.rowCount(),
            "hold_last": bool(self.end_combo.currentData()),
        }

    def load(self, settings: Dict[str, Any],
             steps: Optional[List[Dict[str, float]]] = None):
        """Show a list read back from the instrument."""
        index = self.mode_combo.findData(settings.get("mode"))
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        if settings.get("cycles") is not None:
            self.cycles_spin.setValue(int(settings["cycles"]))
        end = self.end_combo.findData(bool(settings.get("hold_last", True)))
        if end >= 0:
            self.end_combo.setCurrentIndex(end)

        if steps:
            self._set_step_count(max(len(steps), MIN_STEPS))
            for row, step in enumerate(steps):
                for column, key in ((0, "level"), (1, "width"), (2, "slew")):
                    if step.get(key) is not None:
                        self.table.cellWidget(row, column).setValue(
                            float(step[key]))
        self._show_step_count()

    def complain(self, text: str):
        """Say why a send failed, without blocking the caller's loop."""
        QMessageBox.critical(self, "List", text)
