"""The five timing groups a SPD channel holds.

The guide: "The timer works in the Independent mode, and can save five
timing setups, each of which is independent from each other. You can
set any voltage/current value within the range as you want. The timer
supports consecutive output, and the longest time of each group is
10000s."

So a channel's timer is five rows of voltage, current and seconds, run
one after another. The instrument holds them itself -- they survive a
disconnection, and they can be set from the front panel -- so this
dialog reads what is there before offering to change it. Editing a
sequence blind and sending it over whatever was stored is how an
operator loses a setup they had spent time on.

Two conditions the guide states and the instrument does not enforce
are worth having in front of whoever is typing:

  * The timer is ignored in series and parallel mode. The instrument
    accepts the command and does nothing.
  * Switching the output off while the timer runs pauses the
    countdown rather than ending it, and it picks up where it left off
    when the output comes back on.
"""

import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox,
                             QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QTableWidget, QVBoxLayout)

logger = logging.getLogger(__name__)

#: The groups a channel holds. Fixed by the instrument: five, always.
GROUPS = (1, 2, 3, 4, 5)

#: Longest a single group can hold, per the guide.
MAX_SECONDS = 10000.0


class TimerDialog(QDialog):
    """Edit one channel's five timing groups."""

    def __init__(self, channel: int, max_voltage: float = 32.0,
                 max_current: float = 3.2, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._max_voltage = max_voltage
        self._max_current = max_current
        self.setWindowTitle("CH%d timer" % channel)
        # Not modal, for the same reason the list editor is not: the
        # operator wants to watch the readings while setting this up.
        self.setModal(False)
        self._build_ui()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        layout = QVBoxLayout(self)

        blurb = QLabel(
            "Five groups, run one after another. Each holds its voltage "
            "and current for its time, and the timer switches itself off "
            "when the last one finishes.\n\n"
            "The timer only runs in independent mode. Switching the "
            "output off pauses the countdown rather than ending it."
        )
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        self.table = QTableWidget(len(GROUPS), 3)
        self.table.setHorizontalHeaderLabels(
            ["Voltage (V)", "Current (A)", "Time (s)"])
        self.table.setVerticalHeaderLabels(
            ["Group %d" % g for g in GROUPS])
        # Row height from the widget that has to fit in it, not a
        # number: it differs by theme and by display scaling, and a row
        # shorter than its contents clips them with no other sign.
        self.table.verticalHeader().setDefaultSectionSize(self._row_height())
        header = self.table.horizontalHeader()
        for column in range(3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)

        for row, _group in enumerate(GROUPS):
            self.table.setCellWidget(
                row, 0, self._spin(0.0, self._max_voltage, 3, 0.1))
            self.table.setCellWidget(
                row, 1, self._spin(0.0, self._max_current, 3, 0.1))
            self.table.setCellWidget(
                row, 2, self._spin(0.0, MAX_SECONDS, 1, 1.0))
            self.table.setRowHeight(row, self._row_height())
        for row in range(len(GROUPS)):
            for column in range(3):
                self.table.cellWidget(row, column).valueChanged.connect(
                    self._show_total)
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.total_label = QLabel("")
        row.addWidget(self.total_label)
        row.addStretch()
        self.reread_button = QPushButton("Re-read from supply")
        self.reread_button.setToolTip(
            "Fetch the groups the instrument is holding now, discarding "
            "anything changed here.")
        row.addWidget(self.reread_button)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.send_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.send_button.setText("Send to supply")
        layout.addWidget(buttons)

        self._show_total()

    @staticmethod
    def _row_height() -> int:
        """Tall enough for a spin box on this platform, with room."""
        probe = QDoubleSpinBox()
        return max(probe.sizeHint().height() + 8, 30)

    def _spin(self, minimum: float, maximum: float, decimals: int,
              step: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setSingleStep(step)
        box.setKeyboardTracking(False)
        return box

    # ------------------------------------------------------------------ #
    # Contents
    # ------------------------------------------------------------------ #

    def steps(self) -> List[Dict[str, Any]]:
        """The five groups as the driver wants them."""
        out = []
        for row, group in enumerate(GROUPS):
            out.append({
                "group": group,
                "voltage": self.table.cellWidget(row, 0).value(),
                "current": self.table.cellWidget(row, 1).value(),
                "seconds": self.table.cellWidget(row, 2).value(),
            })
        return out

    def load(self, steps) -> None:
        """Show what the instrument is holding.

        A group the supply could not report is left at zero rather than
        guessed at, and a group whose value is outside what this model
        can take is clamped -- the boxes would clamp it anyway, so the
        only choice is whether the operator is told.
        """
        adjusted = []
        by_group = {}
        for entry in steps or []:
            if isinstance(entry, dict) and entry.get("group") is not None:
                by_group[int(entry["group"])] = entry

        for row, group in enumerate(GROUPS):
            entry = by_group.get(group) or {}
            for column, key in enumerate(("voltage", "current", "seconds")):
                box = self.table.cellWidget(row, column)
                value = entry.get(key)
                box.blockSignals(True)
                if value is None:
                    box.setValue(0.0)
                else:
                    value = float(value)
                    if value > box.maximum() or value < box.minimum():
                        adjusted.append("group %d %s" % (group, key))
                    box.setValue(value)
                box.blockSignals(False)
        self._show_total()
        if adjusted:
            self.complain(
                "The supply reported values this model cannot take, so "
                "they were clamped:\n\n  " + "\n  ".join(adjusted),
                title="Timer", fatal=False)

    def _show_total(self) -> None:
        """How long the whole sequence runs, which is the number an
        operator is actually deciding."""
        total = sum(step["seconds"] for step in self.steps())
        used = [s for s in self.steps() if s["seconds"] > 0]
        if not used:
            self.total_label.setText(
                "No group holds for any time, so the timer would finish "
                "at once.")
            return
        self.total_label.setText(
            "%d group(s), %s in total" % (len(used), _spell(total)))

    # ------------------------------------------------------------------ #
    # Messages
    # ------------------------------------------------------------------ #

    def complain(self, text: str, title: str = "Timer",
                 fatal: bool = True) -> None:
        """Say what went wrong, without blocking the caller's loop."""
        if fatal:
            QMessageBox.critical(self, title, text)
        else:
            QMessageBox.information(self, title, text)


def _spell(seconds: float) -> str:
    """Seconds as something readable, since 10000 is the limit and
    "10000 s" tells an operator less than "2 h 46 m"."""
    seconds = float(seconds)
    if seconds < 60:
        return "%gs" % round(seconds, 1)
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return "%dm %02ds" % (minutes, round(rest))
    hours, minutes = divmod(int(minutes), 60)
    return "%dh %02dm %02ds" % (hours, minutes, round(rest))
