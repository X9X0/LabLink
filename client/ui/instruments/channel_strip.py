"""One channel of a multi-channel supply, as a column.

A three-channel supply cannot be three copies of the single-channel
panel: the dials, min/max and the digital / analog / graph stack cost
more room than three of them have. A strip is what is left when you
keep only what has to be visible at a glance -- the three readings,
the two setpoints, the output switch and which law is regulating.

Not every channel is programmable. The SPD3303X-E's CH3 is a fixed
2.5 / 3.3 / 5 V rail chosen by a switch on the front panel: remote
control can turn it on and off and nothing else. It answers none of
the measurement queries, and it does not refuse them -- it never
replies at all, so asking costs a full read timeout. A strip for a
channel like that shows the switch and says why there are no numbers,
which is a better answer than three dashes.
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDoubleSpinBox, QGridLayout, QGroupBox, QLabel,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from client.ui.instruments.widgets import FittedReadout

logger = logging.getLogger(__name__)

#: The readings a strip shows, in the order they appear.
READOUTS = (
    ("voltage", "V", "#4a9eff"),
    ("current", "A", "#ff9d4a"),
    ("power", "W", "#7ed957"),
)


class ChannelStrip(QGroupBox):
    """One supply channel: readings above, controls below."""

    #: (channel, "voltage" | "current", value) when an operator commits
    #: a setpoint. The panel owns talking to the server; a strip only
    #: reports what was asked for.
    setpoint_committed = pyqtSignal(int, str, float)
    #: (channel, wanted)
    output_toggled = pyqtSignal(int, bool)

    #: Below this, a setpoint has not moved. Smaller than the finest
    #: step any of these supplies resolves.
    EPSILON = 1e-6

    def __init__(self, number: int, programmable: bool = True,
                 note: str = "", parent: Optional[QWidget] = None):
        super().__init__(f"CH{number}", parent)
        self.number = number
        self.programmable = programmable
        self._note = note
        self.readouts = {}
        #: The last value reported or sent per setpoint, so losing
        #: focus does not re-send one that has not moved.
        self._committed = {"voltage": None, "current": None}
        self.voltage_spinbox = None
        self.current_spinbox = None
        self.cv_indicator = None
        self.cc_indicator = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._build()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        if self.programmable:
            self._build_readouts(layout)
            self._build_setpoints(layout)
        else:
            self._build_note(layout)

        self.output_button = QPushButton("Output off")
        self.output_button.setCheckable(True)
        self.output_button.clicked.connect(
            lambda on: self.output_toggled.emit(self.number, bool(on)))
        layout.addWidget(self.output_button)

        if self.programmable:
            self._build_mode(layout)

    def _build_readouts(self, layout):
        # The readings take the stretch. Everything else here is a fixed
        # row, so shrinking the window takes it out of the digits last
        # rather than first.
        for key, unit, colour in READOUTS:
            readout = FittedReadout("--")
            readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            readout.setStyleSheet(f"color: {colour};")
            readout.setToolTip({"voltage": "Measured output voltage",
                                "current": "Measured output current",
                                "power": "Measured output power"}[key])
            self.readouts[key] = readout
            layout.addWidget(readout, 1)
        self._units = {k: u for k, u, _c in READOUTS}

    def _build_setpoints(self, layout):
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(3)

        grid.addWidget(QLabel("Set V:"), 0, 0)
        self.voltage_spinbox = QDoubleSpinBox()
        self.voltage_spinbox.setDecimals(3)
        self.voltage_spinbox.setRange(0.0, 32.0)
        self.voltage_spinbox.setKeyboardTracking(False)
        self.voltage_spinbox.editingFinished.connect(
            lambda: self._commit("voltage", self.voltage_spinbox.value()))
        grid.addWidget(self.voltage_spinbox, 0, 1)

        grid.addWidget(QLabel("Set A:"), 1, 0)
        self.current_spinbox = QDoubleSpinBox()
        self.current_spinbox.setDecimals(3)
        self.current_spinbox.setRange(0.0, 3.2)
        self.current_spinbox.setKeyboardTracking(False)
        self.current_spinbox.editingFinished.connect(
            lambda: self._commit("current", self.current_spinbox.value()))
        grid.addWidget(self.current_spinbox, 1, 1)

        layout.addLayout(grid)

    def _build_note(self, layout):
        """A channel with nothing to show says why, once."""
        note = QLabel(self._note or "This channel reports no readings.")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("color: palette(mid);")
        layout.addWidget(note, 1)

    def _build_mode(self, layout):
        row = QWidget()
        inner = QGridLayout(row)
        inner.setContentsMargins(0, 0, 0, 0)
        self.cv_indicator = QLabel("CV")
        self.cc_indicator = QLabel("CC")
        for column, widget in ((0, self.cv_indicator), (1, self.cc_indicator)):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner.addWidget(widget, 0, column)
        self.show_mode(False, False)
        layout.addWidget(row)

    # ------------------------------------------------------------------ #
    # Showing what the instrument says. None of this commands anything.
    # ------------------------------------------------------------------ #

    def _commit(self, what: str, value: float):
        """Report a setpoint, but only if it actually moved.

        editingFinished fires whenever the box loses focus, not only
        when something was typed -- so tabbing past a field, or the
        panel simply being shown and then losing focus, commanded the
        instrument with the value already in the box. Harmless-looking
        until it re-sends a setpoint the operator had deliberately
        changed on the front panel.
        """
        value = float(value)
        last = self._committed.get(what)
        if last is not None and abs(last - value) < self.EPSILON:
            return
        self._committed[what] = value
        self.setpoint_committed.emit(self.number, what, value)

    def show_readings(self, voltage=None, current=None, power=None):
        if not self.programmable:
            return
        for key, value, places in (("voltage", voltage, 3),
                                   ("current", current, 3),
                                   ("power", power, 2)):
            readout = self.readouts.get(key)
            if readout is None:
                continue
            if value is None:
                readout.setText("--")
            else:
                readout.setText(f"{value:.{places}f} {self._units[key]}")

    def is_being_edited(self) -> bool:
        """Whether the operator is part-way through typing into *this*
        channel.

        The panel-wide check is too coarse once there is more than one
        column: focus in CH1's voltage box would freeze CH2 and CH3's
        setpoints as well, and they are not being typed into.
        """
        from PyQt6.QtWidgets import QApplication

        focused = QApplication.focusWidget()
        if focused is None:
            return False
        return focused in (self.voltage_spinbox, self.current_spinbox)

    def show_setpoints(self, voltage=None, current=None):
        """Put the instrument's own setpoints on the boxes.

        Blocked, because these boxes are wired to send: showing what
        the supply reports must not turn into commanding it back.
        """
        for box, value in ((self.voltage_spinbox, voltage),
                           (self.current_spinbox, current)):
            if box is None or value is None:
                continue
            box.blockSignals(True)
            box.setValue(float(value))
            box.blockSignals(False)
            self._committed[
                "voltage" if box is self.voltage_spinbox else "current"
            ] = float(value)

    def show_output(self, on: bool):
        self.output_button.blockSignals(True)
        self.output_button.setChecked(bool(on))
        self.output_button.setText("Output on" if on else "Output off")
        self.output_button.blockSignals(False)

    def show_mode(self, cv: bool, cc: bool):
        if self.cv_indicator is None:
            return
        for widget, lit in ((self.cv_indicator, cv), (self.cc_indicator, cc)):
            widget.setStyleSheet(
                "font-weight: bold;" if lit else "color: palette(mid);")

    def blank(self):
        self.show_readings(None, None, None)
        self.show_mode(False, False)

    # ------------------------------------------------------------------ #
    # Ranging
    # ------------------------------------------------------------------ #

    def set_ranges(self, max_voltage: float, max_current: float,
                   voltage_decimals: int = 3, current_decimals: int = 3):
        """Range the boxes without commanding anything.

        setMaximum clamps a value that no longer fits and Qt emits the
        change, and these boxes are wired to send -- the single-channel
        panel learned that the hard way, switching instruments and
        commanding the one just selected.
        """
        for box, maximum, places in (
            (self.voltage_spinbox, max_voltage, voltage_decimals),
            (self.current_spinbox, max_current, current_decimals),
        ):
            if box is None:
                continue
            box.blockSignals(True)
            box.setDecimals(places)
            box.setRange(0.0, float(maximum))
            box.blockSignals(False)

    def set_controls_enabled(self, enabled: bool):
        for widget in (self.voltage_spinbox, self.current_spinbox,
                       self.output_button):
            if widget is not None:
                widget.setEnabled(enabled)
