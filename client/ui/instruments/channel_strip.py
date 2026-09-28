"""One channel of a multi-channel supply: its controls.

A supply with three channels keeps the bands the single-channel panel
has always had -- controls, then the display-mode selector, then the
readings -- and repeats per channel only what belongs to a channel.
This is that repeated part: a dial and a box for volts, the same for
amps, the channel's own output switch and its own CV/CC indicator.

The readings are not here. They live in a MeasurementViews per
channel, side by side under one shared selector, so digital, analog
and graph all still work and there is one selector to keep in step
rather than three.

Not every channel is programmable. The SPD3303X-E's CH3 is a fixed
2.5 / 3.3 / 5 V rail chosen by a switch on the front panel: remote
control can turn it on and off and nothing else. It answers none of
the measurement queries, and it does not refuse them -- it never
replies, so asking costs a full read timeout. Its column carries the
switch and says why there is nothing else, which leaves the room
above it free for whatever the supply as a whole needs.
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDial, QDoubleSpinBox, QGroupBox, QHBoxLayout,
                             QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                             QWidget)

logger = logging.getLogger(__name__)

#: Dials carry integers, so a setpoint is scaled by this to keep one
#: decimal of resolution on the dial. The box keeps the rest.
DIAL_SCALE = 10


class ChannelStrip(QGroupBox):
    """One supply channel's controls, as a column."""

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
        super().__init__("CH%d" % number, parent)
        self.number = number
        self.programmable = programmable
        self._note = note
        #: The last value reported or sent per setpoint, so losing
        #: focus does not re-send one that has not moved.
        self._committed = {"voltage": None, "current": None}
        self.voltage_dial = None
        self.current_dial = None
        self.voltage_spinbox = None
        self.current_spinbox = None
        self.cv_indicator = None
        self.cc_indicator = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        self._build()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        if self.programmable:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(self._build_setpoint("voltage", "Voltage (V)", 32.0))
            row.addWidget(self._build_setpoint("current", "Current (A)", 3.2))
            layout.addLayout(row)
        else:
            note = QLabel(self._note or "This channel reports no readings.")
            note.setWordWrap(True)
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setStyleSheet("color: palette(mid);")
            layout.addWidget(note, 1)

        self.output_button = QPushButton("Output off")
        self.output_button.setCheckable(True)
        self.output_button.setToolTip(
            "Switch CH%d on and off. Each channel has its own." % self.number)
        self.output_button.clicked.connect(
            lambda on: self.output_toggled.emit(self.number, bool(on)))
        layout.addWidget(self.output_button)

        if self.programmable:
            layout.addWidget(self._build_mode())

    def _build_setpoint(self, what: str, label: str,
                        maximum: float) -> QGroupBox:
        group = QGroupBox(label.split()[0] + " Control")
        inner = QVBoxLayout(group)
        inner.setContentsMargins(4, 4, 4, 4)

        dial = QDial()
        dial.setMinimum(0)
        dial.setMaximum(int(maximum * DIAL_SCALE))
        dial.setNotchesVisible(True)
        dial.setWrapping(False)
        dial.valueChanged.connect(
            lambda ticks, w=what: self._on_dial(w, ticks))
        inner.addWidget(dial)

        row = QHBoxLayout()
        row.addWidget(QLabel(label + ":"))
        box = QDoubleSpinBox()
        box.setDecimals(3)
        box.setRange(0.0, maximum)
        box.setSingleStep(0.1)
        box.setKeyboardTracking(False)
        box.editingFinished.connect(
            lambda w=what: self._commit(w, self._box(w).value()))
        row.addWidget(box)
        inner.addLayout(row)

        if what == "voltage":
            self.voltage_dial, self.voltage_spinbox = dial, box
        else:
            self.current_dial, self.current_spinbox = dial, box
        return group

    def _build_mode(self) -> QWidget:
        row = QWidget()
        inner = QHBoxLayout(row)
        inner.setContentsMargins(0, 0, 0, 0)
        self.cv_indicator = QLabel("CV")
        self.cc_indicator = QLabel("CC")
        for widget in (self.cv_indicator, self.cc_indicator):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner.addWidget(widget)
        self.show_mode(False, False)
        return row

    # ------------------------------------------------------------------ #
    # Operator input
    # ------------------------------------------------------------------ #

    def _box(self, what: str):
        return (self.voltage_spinbox if what == "voltage"
                else self.current_spinbox)

    def _dial(self, what: str):
        return self.voltage_dial if what == "voltage" else self.current_dial

    def _on_dial(self, what: str, ticks: int):
        """A dial turn is a setpoint, and it shows on the box."""
        value = ticks / DIAL_SCALE
        box = self._box(what)
        if box is not None:
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)
        self._commit(what, value)

    def _commit(self, what: str, value: float):
        """Report a setpoint, but only if it actually moved.

        editingFinished fires whenever the box loses focus, not only
        when something was typed -- so tabbing past a field, or the
        panel being shown and then losing focus, commanded the
        instrument with the value already in the box. Harmless-looking
        until it re-sends a setpoint somebody had deliberately changed
        on the front panel.
        """
        value = float(value)
        last = self._committed.get(what)
        if last is not None and abs(last - value) < self.EPSILON:
            return
        self._committed[what] = value
        self.setpoint_committed.emit(self.number, what, value)

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

    # ------------------------------------------------------------------ #
    # Showing what the instrument says. None of this commands anything.
    # ------------------------------------------------------------------ #

    def show_setpoints(self, voltage=None, current=None):
        """Put the instrument's own setpoints on the controls.

        Blocked, because these are wired to send: showing what the
        supply reports must not turn into commanding it back.
        """
        for what, value in (("voltage", voltage), ("current", current)):
            if value is None:
                continue
            box, dial = self._box(what), self._dial(what)
            if box is None:
                continue
            box.blockSignals(True)
            box.setValue(float(value))
            box.blockSignals(False)
            if dial is not None:
                dial.blockSignals(True)
                dial.setValue(int(round(float(value) * DIAL_SCALE)))
                dial.blockSignals(False)
            self._committed[what] = float(value)

    def show_output(self, on: bool):
        self.output_button.blockSignals(True)
        self.output_button.setChecked(bool(on))
        self.output_button.setText("Output on" if on else "Output off")
        self.output_button.blockSignals(False)

    def show_mode(self, cv: bool, cc: bool):
        if self.cv_indicator is None:
            return
        for widget, lit, name in ((self.cv_indicator, cv, "CV"),
                                  (self.cc_indicator, cc, "CC")):
            widget.setText("%s: %s" % (name, "ON" if lit else "OFF"))
            widget.setStyleSheet(
                "font-weight: bold;" if lit else "color: palette(mid);")

    def blank(self):
        self.show_mode(False, False)

    # ------------------------------------------------------------------ #
    # Ranging
    # ------------------------------------------------------------------ #

    def set_ranges(self, max_voltage: float, max_current: float,
                   voltage_decimals: int = 3, current_decimals: int = 3):
        """Range the controls without commanding anything.

        setMaximum clamps a value that no longer fits and Qt emits the
        change, and these are wired to send -- the single-channel
        panel learned that the hard way, switching instruments and
        commanding the one just selected.
        """
        for what, maximum, places in (
            ("voltage", max_voltage, voltage_decimals),
            ("current", max_current, current_decimals),
        ):
            box, dial = self._box(what), self._dial(what)
            if box is None:
                continue
            box.blockSignals(True)
            box.setDecimals(places)
            box.setRange(0.0, float(maximum))
            box.blockSignals(False)
            if dial is not None:
                dial.blockSignals(True)
                dial.setMaximum(int(float(maximum) * DIAL_SCALE))
                dial.blockSignals(False)

    def set_controls_enabled(self, enabled: bool):
        for widget in (self.voltage_spinbox, self.current_spinbox,
                       self.voltage_dial, self.current_dial,
                       self.output_button):
            if widget is not None:
                widget.setEnabled(enabled)
