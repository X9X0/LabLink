"""A front-panel view of a Rigol bench oscilloscope, laid out like the instrument.

Drawn from the DS1000Z / DS1000Z-E "Front Panel Overview" figures and the
"Front Panel Function Overview" text of the user guides: measurement
softkeys down the left of the screen, function softkeys to its right, the
common keys (CLEAR, AUTO, RUN/STOP, SINGLE) across the top, the
multifunction knob and menu keys, then the VERTICAL, HORIZONTAL and TRIGGER
control areas with their knobs, and the input BNCs along the bottom.

Knobs turn with the mouse wheel while the pointer is over them, and click
to "press" -- several front-panel knobs are also buttons: HORIZONTAL
POSITION press resets the horizontal position, TRIGGER LEVEL press resets
the level to zero, the SCALE knobs press to toggle fine adjustment. This
widget only reports what the operator did; the oscilloscope panel decides
what to send.
"""

import math
from typing import Dict, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

CHANNEL_COLOURS = ["#F8FC00", "#00FCF8", "#F800F8", "#0080FF"]
RUN_YELLOW = "#f0c419"
STOP_RED = "#d0342c"


class KnobWidget(QWidget):
    """A rotary knob that turns with the wheel and presses with a click.

    ``turned(steps)`` is positive for clockwise. One wheel notch is one step,
    so scrolling behaves like the detents on the instrument. Dragging round
    the knob turns it too. ``pressed`` is a left click without a drag.
    """

    turned = pyqtSignal(int)
    pressed = pyqtSignal()

    def __init__(self, label: str = "", pushable: bool = True, diameter: int = 54, parent=None):
        super().__init__(parent)
        self.label = label
        self.pushable = pushable
        self._angle = 0.0
        self._hover = False
        self._drag_start: Optional[QPointF] = None
        self._drag_angle: Optional[float] = None
        self._dragged = False
        self._lit = False
        self.setFixedSize(diameter, diameter + 16)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        tip = f"{label}: scroll to turn" + (", click to press" if pushable else "")
        self.setToolTip(tip)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_lit(self, lit: bool):
        self._lit = bool(lit)
        self.update()

    # -- input --------------------------------------------------------------

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            event.ignore()
            return
        steps = int(math.copysign(max(1, abs(delta) // 120), delta))
        self._angle = (self._angle + 18 * steps) % 360
        self.turned.emit(steps)
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position()
            self._drag_angle = self._pointer_angle(event.position())
            self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None and self._drag_angle is not None:
            angle = self._pointer_angle(event.position())
            diff = (angle - self._drag_angle + 540) % 360 - 180
            if abs(diff) >= 18:
                steps = int(diff // 18) if diff > 0 else -int(-diff // 18)
                self._drag_angle = (self._drag_angle + 18 * steps) % 360
                self._angle = (self._angle + 18 * steps) % 360
                self._dragged = True
                self.turned.emit(steps)
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            if not self._dragged and self.pushable:
                self.pressed.emit()
            self._drag_start = None
            self._drag_angle = None
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def _pointer_angle(self, pos: QPointF) -> float:
        c = self._centre()
        return math.degrees(math.atan2(pos.y() - c.y(), pos.x() - c.x()))

    def _centre(self) -> QPointF:
        d = min(self.width(), self.height() - 16)
        return QPointF(self.width() / 2, d / 2 + 2)

    # -- paint --------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = min(self.width(), self.height() - 16) - 4
        c = self._centre()
        rect = QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

        painter.setPen(QPen(QColor("#2a2a2a"), 1.5))
        painter.setBrush(QColor("#7a7a7a") if self._hover else QColor("#5c5c5c"))
        painter.drawEllipse(rect)
        inner = rect.adjusted(d * 0.12, d * 0.12, -d * 0.12, -d * 0.12)
        painter.setBrush(QColor("#3a3a3a"))
        painter.drawEllipse(inner)
        if self._lit:
            painter.setPen(QPen(QColor("#39FF14"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(-2, -2, 2, 2))

        # Indicator line at the current angle (12 o'clock is 0).
        a = math.radians(self._angle - 90)
        r_out, r_in = d / 2 - 3, d / 2 - d * 0.28
        painter.setPen(QPen(QColor("#f2f2f2"), 2.5))
        painter.drawLine(QPointF(c.x() + r_in * math.cos(a), c.y() + r_in * math.sin(a)),
                         QPointF(c.x() + r_out * math.cos(a), c.y() + r_out * math.sin(a)))
        if self.pushable:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#9a9a9a"))
            painter.drawEllipse(c, d * 0.08, d * 0.08)

        painter.setPen(QColor("#dddddd"))
        painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
        painter.drawText(QRectF(0, self.height() - 15, self.width(), 14),
                         Qt.AlignmentFlag.AlignCenter, self.label)
        painter.end()


class PanelKey(QPushButton):
    """A front-panel key that can be lit in a colour, as the real ones are."""

    def __init__(self, text: str, colour: Optional[str] = None, parent=None, enabled: bool = True):
        super().__init__(text, parent)
        self._colour = colour
        self._lit = False
        self.setFixedSize(52, 26)
        self.setEnabled(enabled)
        font = QFont("Arial", 7, QFont.Weight.Bold)
        self.setFont(font)
        self._restyle()

    def set_lit(self, lit: bool, colour: Optional[str] = None):
        self._lit = bool(lit)
        if colour:
            self._colour = colour
        self._restyle()

    def is_lit(self) -> bool:
        return self._lit

    def _restyle(self):
        if self._lit and self._colour:
            self.setStyleSheet(f"QPushButton {{ background-color: {self._colour}; color: black; "
                               f"border: 1px solid #222; border-radius: 4px; }}")
        else:
            border = f"border: 2px solid {self._colour};" if self._colour else "border: 1px solid #333;"
            self.setStyleSheet(f"QPushButton {{ background-color: #3c3c3c; color: #e8e8e8; {border} "
                               f"border-radius: 4px; }} QPushButton:disabled {{ color: #777; }}")


class FrontPanelView(QWidget):
    """The instrument's control surface. Reports actions; commands nothing."""

    #: A channel key was pressed (1-based).
    channel_key = pyqtSignal(int)
    #: Knob turns, in detent steps, positive clockwise.
    vertical_position = pyqtSignal(int)
    vertical_scale = pyqtSignal(int)
    horizontal_position = pyqtSignal(int)
    horizontal_scale = pyqtSignal(int)
    trigger_level = pyqtSignal(int)
    #: Knob presses.
    vertical_position_pressed = pyqtSignal()
    vertical_scale_pressed = pyqtSignal()
    horizontal_position_pressed = pyqtSignal()
    horizontal_scale_pressed = pyqtSignal()
    trigger_level_pressed = pyqtSignal()
    #: Named keys: CLEAR, AUTO, RUN_STOP, SINGLE, FORCE, MODE.
    key = pyqtSignal(str)

    def __init__(self, num_channels: int = 4, parent=None):
        super().__init__(parent)
        self.num_channels = num_channels
        self.channel_keys: Dict[int, PanelKey] = {}
        self._selected_channel = 1
        self.setObjectName("scopeFrontPanel")
        self.setStyleSheet(
            "QWidget#scopeFrontPanel { background-color: #4a4d52; border-radius: 10px; }"
            "QLabel { color: #e0e0e0; }"
            "QFrame#screenBezel { background-color: #101010; border: 3px solid #2b2b2b; border-radius: 6px; }"
        )
        self._build()

    # -- layout -----------------------------------------------------------

    def _build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        # Measurement softkeys, down the left of the screen.
        left = QVBoxLayout()
        left.addWidget(self._softkey("MENU"))
        for _ in range(5):
            left.addWidget(self._softkey(""))
        left.addWidget(self._softkey("▲"))
        left.addWidget(self._softkey("▼"))
        left.addStretch()
        outer.addLayout(left)

        # The screen: the owner puts the live trace here.
        self.screen = QFrame()
        self.screen.setObjectName("screenBezel")
        self.screen.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.screen_layout = QVBoxLayout(self.screen)
        self.screen_layout.setContentsMargins(6, 6, 6, 6)
        outer.addWidget(self.screen, 1)

        # Function softkeys, to the right of the screen.
        right_soft = QVBoxLayout()
        right_soft.addWidget(self._softkey("▲"))
        for _ in range(5):
            right_soft.addWidget(self._softkey(""))
        right_soft.addWidget(self._softkey("▼"))
        right_soft.addStretch()
        outer.addLayout(right_soft)

        # The control area.
        controls = QVBoxLayout()
        controls.setSpacing(6)

        top = QHBoxLayout()
        self.multifunction = KnobWidget("", pushable=True, diameter=40)
        self.multifunction.setToolTip("Multifunction knob: not driven remotely")
        top.addWidget(self.multifunction)
        top.addStretch()
        self.clear_key = PanelKey("CLEAR")
        self.auto_key = PanelKey("AUTO")
        self.run_stop_key = PanelKey("RUN\nSTOP", colour=RUN_YELLOW)
        self.single_key = PanelKey("SINGLE")
        for key, name in ((self.clear_key, "CLEAR"), (self.auto_key, "AUTO"),
                          (self.run_stop_key, "RUN_STOP"), (self.single_key, "SINGLE")):
            key.clicked.connect(lambda _=False, n=name: self.key.emit(n))
            top.addWidget(key)
        controls.addLayout(top)

        menu_row = QGridLayout()
        for i, name in enumerate(("Measure", "Acquire", "Storage", "Cursor", "Display", "Utility")):
            k = PanelKey(name, enabled=False)
            k.setToolTip(f"{name} menu: use the standard view")
            menu_row.addWidget(k, i // 3, i % 3)
        help_key = PanelKey("Help", colour="#2e8b57", enabled=False)
        menu_row.addWidget(help_key, 0, 3)
        controls.addLayout(menu_row)

        areas = QHBoxLayout()
        areas.setSpacing(8)
        areas.addWidget(self._vertical_area())
        areas.addWidget(self._horizontal_area())
        areas.addWidget(self._trigger_area())
        controls.addLayout(areas)

        bnc = QHBoxLayout()
        for n in range(1, 5):
            lab = QLabel(f"◎ CH{n}")
            lab.setStyleSheet(f"QLabel {{ color: {CHANNEL_COLOURS[n - 1]}; font-weight: bold; }}")
            lab.setVisible(n <= self.num_channels)
            bnc.addWidget(lab)
        ext = QLabel("◎ EXT TRIG")
        bnc.addWidget(ext)
        bnc.addStretch()
        controls.addLayout(bnc)
        controls.addStretch()
        outer.addLayout(controls)

    def _softkey(self, text: str) -> PanelKey:
        key = PanelKey(text, enabled=False)
        key.setFixedSize(30, 20)
        key.setToolTip("Softkey: use the standard view")
        return key

    def _vertical_area(self) -> QWidget:
        box = QGroupBoxLike("VERTICAL")
        grid = box.grid
        for n in range(1, 5):
            key = PanelKey(f"CH{n}", colour=CHANNEL_COLOURS[n - 1])
            key.clicked.connect(lambda _=False, ch=n: self.channel_key.emit(ch))
            key.setVisible(n <= self.num_channels)
            self.channel_keys[n] = key
            grid.addWidget(key, n - 1, 0)
        self.v_position = KnobWidget("POSITION", pushable=True)
        self.v_position.setToolTip("VERTICAL POSITION: scroll to move the trace; click to reset to zero")
        self.v_position.turned.connect(self.vertical_position)
        self.v_position.pressed.connect(self.vertical_position_pressed)
        grid.addWidget(self.v_position, 0, 1, 2, 1)
        self.v_scale = KnobWidget("SCALE", pushable=True)
        self.v_scale.setToolTip("VERTICAL SCALE: scroll for volts/div; click to toggle fine steps")
        self.v_scale.turned.connect(self.vertical_scale)
        self.v_scale.pressed.connect(self.vertical_scale_pressed)
        grid.addWidget(self.v_scale, 2, 1, 2, 1)
        math_key = PanelKey("MATH", enabled=False)
        ref_key = PanelKey("REF", enabled=False)
        grid.addWidget(math_key, 4, 0)
        grid.addWidget(ref_key, 4, 1)
        return box

    def _horizontal_area(self) -> QWidget:
        box = QGroupBoxLike("HORIZONTAL")
        grid = box.grid
        self.h_position = KnobWidget("POSITION", pushable=True)
        self.h_position.setToolTip("HORIZONTAL POSITION: scroll to move the trigger point; click to reset to zero")
        self.h_position.turned.connect(self.horizontal_position)
        self.h_position.pressed.connect(self.horizontal_position_pressed)
        grid.addWidget(self.h_position, 0, 0)
        menu_key = PanelKey("MENU", enabled=False)
        grid.addWidget(menu_key, 1, 0)
        self.h_scale = KnobWidget("SCALE", pushable=True)
        self.h_scale.setToolTip("HORIZONTAL SCALE: scroll for s/div; click to toggle fine steps")
        self.h_scale.turned.connect(self.horizontal_scale)
        self.h_scale.pressed.connect(self.horizontal_scale_pressed)
        grid.addWidget(self.h_scale, 2, 0)
        return box

    def _trigger_area(self) -> QWidget:
        box = QGroupBoxLike("TRIGGER")
        grid = box.grid
        self.mode_key = PanelKey("MODE")
        self.mode_key.setToolTip("Trigger sweep: Auto → Normal → Single")
        self.mode_key.clicked.connect(lambda: self.key.emit("MODE"))
        grid.addWidget(self.mode_key, 0, 0)
        self.sweep_label = QLabel("Auto  Normal  Single")
        self.sweep_label.setFont(QFont("Arial", 7))
        grid.addWidget(self.sweep_label, 1, 0)
        self.t_level = KnobWidget("LEVEL", pushable=True)
        self.t_level.setToolTip("TRIGGER LEVEL: scroll to move the level; click to reset to zero")
        self.t_level.turned.connect(self.trigger_level)
        self.t_level.pressed.connect(self.trigger_level_pressed)
        grid.addWidget(self.t_level, 2, 0)
        menu_key = PanelKey("MENU", enabled=False)
        grid.addWidget(menu_key, 3, 0)
        self.force_key = PanelKey("FORCE")
        self.force_key.clicked.connect(lambda: self.key.emit("FORCE"))
        grid.addWidget(self.force_key, 4, 0)
        return box

    # -- state shown on the panel -------------------------------------------

    def set_screen(self, widget: QWidget):
        """Put the live trace behind the bezel."""
        while self.screen_layout.count():
            item = self.screen_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        self.screen_layout.addWidget(widget)

    def set_num_channels(self, n: int):
        self.num_channels = max(1, min(4, int(n)))
        for ch, key in self.channel_keys.items():
            key.setVisible(ch <= self.num_channels)

    def set_selected_channel(self, channel: int):
        self._selected_channel = channel
        for ch, key in self.channel_keys.items():
            key.set_lit(key.is_lit(), CHANNEL_COLOURS[ch - 1])
        self.v_position.set_lit(True)
        self.v_scale.set_lit(True)
        self.v_position.setToolTip(f"VERTICAL POSITION (CH{channel}): scroll to move; click to reset to zero")
        self.v_scale.setToolTip(f"VERTICAL SCALE (CH{channel}): scroll for volts/div; click to toggle fine steps")

    def selected_channel(self) -> int:
        return self._selected_channel

    def set_channel_enabled(self, channel: int, enabled: bool):
        key = self.channel_keys.get(channel)
        if key is not None:
            key.set_lit(enabled, CHANNEL_COLOURS[channel - 1])

    def set_running(self, running: Optional[bool]):
        """RUN/STOP lights yellow when running and red when stopped."""
        if running is None:
            self.run_stop_key.set_lit(False)
        else:
            self.run_stop_key.set_lit(True, RUN_YELLOW if running else STOP_RED)

    def set_sweep(self, sweep: Optional[str]):
        sweep = (sweep or "").upper()
        parts = []
        for name in ("Auto", "Normal", "Single"):
            parts.append(f"[{name}]" if sweep.startswith(name.upper()[:3]) else name)
        self.sweep_label.setText("  ".join(parts))


class QGroupBoxLike(QFrame):
    """A titled control area drawn like the panel's screened outlines."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("controlArea")
        self.setStyleSheet(
            "QFrame#controlArea { border: 1px solid #9aa0a6; border-radius: 6px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 7, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        self.grid = QGridLayout()
        self.grid.setSpacing(4)
        layout.addLayout(self.grid)
