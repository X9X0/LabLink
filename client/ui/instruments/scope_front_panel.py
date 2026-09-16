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
        self._lit_colour = "#39FF14"
        self.setFixedSize(diameter + 8, diameter + 22)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        tip = f"{label}: scroll to turn" + (", click to press" if pushable else "")
        self.setToolTip(tip)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_lit(self, lit: bool, colour: Optional[str] = None):
        self._lit = bool(lit)
        if colour:
            self._lit_colour = colour
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
        d = min(self.width(), self.height() - 20)
        return QPointF(self.width() / 2, d / 2 + 2)

    # -- paint --------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = min(self.width(), self.height() - 20) - 8
        c = self._centre()
        rect = QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

        enabled = self.isEnabled()
        painter.setPen(QPen(QColor("#222222"), 1.5))
        if not enabled:
            painter.setBrush(QColor("#4c4c4c"))
        else:
            painter.setBrush(QColor("#8a8a8a") if self._hover else QColor("#6a6a6a"))
        painter.drawEllipse(rect)
        # Grip ridges round the rim, as on the moulded knobs.
        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        for i in range(24):
            a = math.radians(i * 15)
            painter.drawLine(QPointF(c.x() + (d / 2 - 1) * math.cos(a), c.y() + (d / 2 - 1) * math.sin(a)),
                             QPointF(c.x() + (d / 2 - 4) * math.cos(a), c.y() + (d / 2 - 4) * math.sin(a)))
        inner = rect.adjusted(d * 0.16, d * 0.16, -d * 0.16, -d * 0.16)
        painter.setPen(QPen(QColor("#2a2a2a"), 1))
        painter.setBrush(QColor("#3a3a3a"))
        painter.drawEllipse(inner)
        if self._lit and enabled:
            painter.setPen(QPen(QColor(self._lit_colour), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(-3, -3, 3, 3))

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

        painter.setPen(QColor("#e6e6e6"))
        painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(0, self.height() - 18, self.width(), 16),
                         Qt.AlignmentFlag.AlignCenter, self.label)
        painter.end()


class PanelKey(QPushButton):
    """A front-panel key that can be lit in a colour, as the real ones are.

    Keys are sized from their own label, never to a fixed box: the first
    version fixed every key at 52x26 and "RUN/STOP" rendered as "RUI TO".
    """

    #: Point size of the key legends; the whole panel is drawn at this scale.
    POINT_SIZE = 9

    def __init__(self, text: str, colour: Optional[str] = None, parent=None,
                 enabled: bool = True, min_width: int = 0):
        super().__init__(text, parent)
        self._colour = colour
        self._lit = False
        self.setEnabled(enabled)
        self.setFont(QFont("Arial", self.POINT_SIZE, QFont.Weight.Bold))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._size_to_text(min_width)
        self._restyle()

    def _size_to_text(self, min_width: int):
        metrics = self.fontMetrics()
        lines = self.text().split("\n") or [""]
        text_width = max(metrics.horizontalAdvance(line) for line in lines)
        self.setMinimumWidth(max(min_width, text_width + 18))
        self.setFixedHeight(metrics.height() * len(lines) + 12)

    def set_lit(self, lit: bool, colour: Optional[str] = None):
        self._lit = bool(lit)
        if colour:
            self._colour = colour
        self._restyle()

    def is_lit(self) -> bool:
        return self._lit

    def _restyle(self):
        if self._lit and self._colour:
            self.setStyleSheet(
                f"QPushButton {{ background-color: {self._colour}; color: black; "
                f"border: 1px solid #222; border-radius: 4px; padding: 2px 6px; }}"
            )
        else:
            border = f"border: 2px solid {self._colour};" if self._colour else "border: 1px solid #262626;"
            self.setStyleSheet(
                f"QPushButton {{ background-color: #3c3c3c; color: #ececec; {border} "
                f"border-radius: 4px; padding: 2px 6px; }}"
                f"QPushButton:hover {{ background-color: #4a4a4a; }}"
                f"QPushButton:pressed {{ background-color: #2a2a2a; }}"
                f"QPushButton:disabled {{ color: #8a8a8a; border-color: #333; }}"
            )


class Softkey(QPushButton):
    """One of the blank grey menu softkeys beside the screen; not driven remotely."""

    def __init__(self, glyph: str = "", parent=None):
        super().__init__(glyph, parent)
        self.setEnabled(False)
        self.setFixedSize(26, 22)
        self.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        self.setToolTip("Softkey: menus are driven from the standard view")
        self.setStyleSheet(
            "QPushButton { background-color: #5a5d62; color: #d8d8d8; border: 1px solid #2c2c2c;"
            " border-radius: 3px; } QPushButton:disabled { color: #c8c8c8; }"
        )


class FrontPanelView(QWidget):
    """The instrument's control surface. Reports actions; commands nothing.

    Proportions follow the DS1000Z: the screen with its measurement softkeys
    on the left and function softkeys on the right takes the greater part of
    the width, the channel BNCs sit under it, and the control area on the
    right stacks the common keys, the menu keys, then the VERTICAL,
    HORIZONTAL and TRIGGER areas side by side. The control area is sized
    from its own keys and knobs and never shrinks below that, so the screen
    is what gives way when the window is narrow.
    """

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

    KNOB_DIAMETER = 58
    SMALL_KNOB_DIAMETER = 44

    def __init__(self, num_channels: int = 4, parent=None):
        super().__init__(parent)
        self.num_channels = num_channels
        self.channel_keys: Dict[int, PanelKey] = {}
        self.bnc_labels: Dict[int, QLabel] = {}
        self._selected_channel = 1
        self.setObjectName("scopeFrontPanel")
        # A plain QWidget paints no background of its own; without this the
        # grey body is never drawn and the legends sit on the window colour.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget#scopeFrontPanel { background-color: #4a4d52; border-radius: 10px; }"
            "QLabel { color: #e6e6e6; }"
            "QFrame#screenBezel { background-color: #101010; border: 3px solid #2b2b2b; border-radius: 6px; }"
        )
        self.setMinimumHeight(420)
        self._build()

    # -- layout -----------------------------------------------------------

    def _build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # Left: the display block -- softkeys, screen, softkeys; BNCs below.
        display_block = QVBoxLayout()
        display_block.setSpacing(8)
        screen_row = QHBoxLayout()
        screen_row.setSpacing(6)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.menu_softkey = Softkey("M")
        self.menu_softkey.setToolTip("MENU: measurement menu softkeys")
        left.addWidget(self.menu_softkey)
        for _ in range(5):
            left.addWidget(Softkey())
        left.addWidget(Softkey("▲"))
        left.addWidget(Softkey("▼"))
        left.addStretch()
        screen_row.addLayout(left)

        # The screen: the owner puts the live trace here.
        self.screen = QFrame()
        self.screen.setObjectName("screenBezel")
        self.screen.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.screen.setMinimumSize(320, 240)
        self.screen_layout = QVBoxLayout(self.screen)
        self.screen_layout.setContentsMargins(6, 6, 6, 6)
        screen_row.addWidget(self.screen, 1)

        right_soft = QVBoxLayout()
        right_soft.setSpacing(6)
        right_soft.addWidget(Softkey("▲"))
        for _ in range(5):
            right_soft.addWidget(Softkey())
        right_soft.addWidget(Softkey("▼"))
        right_soft.addStretch()
        screen_row.addLayout(right_soft)
        display_block.addLayout(screen_row, 1)

        # Input BNCs and the probe-compensation terminals, under the screen.
        bnc = QHBoxLayout()
        bnc.setSpacing(14)
        bnc.addSpacing(32)
        for n in range(1, 5):
            lab = QLabel(f"◎  CH{n}")
            lab.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            lab.setStyleSheet(f"QLabel {{ color: {CHANNEL_COLOURS[n - 1]}; }}")
            lab.setVisible(n <= self.num_channels)
            self.bnc_labels[n] = lab
            bnc.addWidget(lab)
        ext = QLabel("◎  EXT TRIG")
        ext.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        bnc.addWidget(ext)
        bnc.addStretch()
        comp = QLabel("⊓  Probe comp  ⊥")
        comp.setFont(QFont("Arial", 8))
        bnc.addWidget(comp)
        display_block.addLayout(bnc)
        outer.addLayout(display_block, 1)

        # Right: the control area, sized from its contents.
        controls_widget = QWidget()
        controls_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        controls = QVBoxLayout(controls_widget)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.multifunction = KnobWidget("", pushable=True, diameter=self.SMALL_KNOB_DIAMETER)
        self.multifunction.setToolTip("Multifunction knob: menus are driven from the standard view")
        self.multifunction.setEnabled(False)
        top.addWidget(self.multifunction, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch()
        self.clear_key = PanelKey("CLEAR")
        self.auto_key = PanelKey("AUTO")
        self.run_stop_key = PanelKey("RUN\nSTOP", colour=RUN_YELLOW)
        self.single_key = PanelKey("SINGLE")
        for key, name, tip in (
            (self.clear_key, "CLEAR", "Clear the display"),
            (self.auto_key, "AUTO", "Autoscale"),
            (self.run_stop_key, "RUN_STOP", "Run / stop acquisition"),
            (self.single_key, "SINGLE", "Single-shot acquisition"),
        ):
            key.setToolTip(tip)
            key.clicked.connect(lambda _=False, n=name: self.key.emit(n))
            top.addWidget(key, 0, Qt.AlignmentFlag.AlignVCenter)
        controls.addLayout(top)

        menu_row = QGridLayout()
        menu_row.setHorizontalSpacing(6)
        menu_row.setVerticalSpacing(6)
        self.menu_keys: Dict[str, PanelKey] = {}
        for i, name in enumerate(("Measure", "Acquire", "Storage", "Cursor", "Display", "Utility")):
            k = PanelKey(name, enabled=False, min_width=68)
            k.setToolTip(f"{name} menu: use the standard view")
            self.menu_keys[name] = k
            menu_row.addWidget(k, i // 3, i % 3)
        help_key = PanelKey("Help", colour="#2e8b57", enabled=False, min_width=60)
        menu_row.addWidget(help_key, 0, 3)
        menu_row.setColumnStretch(4, 1)
        controls.addLayout(menu_row)

        areas = QHBoxLayout()
        areas.setSpacing(8)
        areas.addWidget(self._vertical_area())
        areas.addWidget(self._horizontal_area())
        areas.addWidget(self._trigger_area())
        controls.addLayout(areas)
        controls.addStretch()

        outer.addWidget(controls_widget, 0)

    def _vertical_area(self) -> QWidget:
        box = QGroupBoxLike("VERTICAL")
        grid = box.grid
        for n in range(1, 5):
            key = PanelKey(f"CH{n}", colour=CHANNEL_COLOURS[n - 1], min_width=52)
            key.setToolTip(f"CH{n}: select; press again to switch the channel off")
            key.clicked.connect(lambda _=False, ch=n: self.channel_key.emit(ch))
            key.setVisible(n <= self.num_channels)
            self.channel_keys[n] = key
            grid.addWidget(key, n - 1, 0)
        self.v_position = KnobWidget("POSITION", pushable=True, diameter=self.KNOB_DIAMETER)
        self.v_position.setToolTip("VERTICAL POSITION: scroll to move the trace; click to reset to zero")
        self.v_position.turned.connect(self.vertical_position)
        self.v_position.pressed.connect(self.vertical_position_pressed)
        grid.addWidget(self.v_position, 0, 1, 2, 1, Qt.AlignmentFlag.AlignCenter)
        self.v_scale = KnobWidget("SCALE", pushable=True, diameter=self.KNOB_DIAMETER)
        self.v_scale.setToolTip("VERTICAL SCALE: scroll for volts/div; click to toggle fine steps")
        self.v_scale.turned.connect(self.vertical_scale)
        self.v_scale.pressed.connect(self.vertical_scale_pressed)
        grid.addWidget(self.v_scale, 2, 1, 2, 1, Qt.AlignmentFlag.AlignCenter)
        math_key = PanelKey("MATH", enabled=False, min_width=52)
        ref_key = PanelKey("REF", enabled=False, min_width=52)
        grid.addWidget(math_key, 4, 0)
        grid.addWidget(ref_key, 4, 1, Qt.AlignmentFlag.AlignCenter)
        return box

    def _horizontal_area(self) -> QWidget:
        box = QGroupBoxLike("HORIZONTAL")
        grid = box.grid
        self.h_position = KnobWidget("POSITION", pushable=True, diameter=self.KNOB_DIAMETER)
        self.h_position.setToolTip("HORIZONTAL POSITION: scroll to move the trigger point; click to reset to zero")
        self.h_position.turned.connect(self.horizontal_position)
        self.h_position.pressed.connect(self.horizontal_position_pressed)
        grid.addWidget(self.h_position, 0, 0, Qt.AlignmentFlag.AlignCenter)
        menu_key = PanelKey("MENU", enabled=False, min_width=56)
        grid.addWidget(menu_key, 1, 0, Qt.AlignmentFlag.AlignCenter)
        self.h_scale = KnobWidget("SCALE", pushable=True, diameter=self.KNOB_DIAMETER)
        self.h_scale.setToolTip("HORIZONTAL SCALE: scroll for s/div; click to toggle fine steps")
        self.h_scale.turned.connect(self.horizontal_scale)
        self.h_scale.pressed.connect(self.horizontal_scale_pressed)
        grid.addWidget(self.h_scale, 2, 0, Qt.AlignmentFlag.AlignCenter)
        grid.setRowStretch(3, 1)
        return box

    def _trigger_area(self) -> QWidget:
        box = QGroupBoxLike("TRIGGER")
        grid = box.grid
        self.mode_key = PanelKey("MODE", min_width=56)
        self.mode_key.setToolTip("Trigger sweep: Auto → Normal → Single")
        self.mode_key.clicked.connect(lambda: self.key.emit("MODE"))
        grid.addWidget(self.mode_key, 0, 0, Qt.AlignmentFlag.AlignCenter)
        self.sweep_label = QLabel("Auto  Normal  Single")
        self.sweep_label.setFont(QFont("Arial", 8))
        self.sweep_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self.sweep_label, 1, 0)
        self.t_level = KnobWidget("LEVEL", pushable=True, diameter=self.KNOB_DIAMETER)
        self.t_level.setToolTip("TRIGGER LEVEL: scroll to move the level; click to reset to zero")
        self.t_level.turned.connect(self.trigger_level)
        self.t_level.pressed.connect(self.trigger_level_pressed)
        grid.addWidget(self.t_level, 2, 0, Qt.AlignmentFlag.AlignCenter)
        menu_key = PanelKey("MENU", enabled=False, min_width=56)
        grid.addWidget(menu_key, 3, 0, Qt.AlignmentFlag.AlignCenter)
        self.force_key = PanelKey("FORCE", min_width=56)
        self.force_key.setToolTip("Force a trigger")
        self.force_key.clicked.connect(lambda: self.key.emit("FORCE"))
        grid.addWidget(self.force_key, 4, 0, Qt.AlignmentFlag.AlignCenter)
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
        for ch, lab in self.bnc_labels.items():
            lab.setVisible(ch <= self.num_channels)

    def set_selected_channel(self, channel: int):
        self._selected_channel = channel
        for ch, key in self.channel_keys.items():
            key.set_lit(key.is_lit(), CHANNEL_COLOURS[ch - 1])
        colour = CHANNEL_COLOURS[channel - 1]
        self.v_position.set_lit(True, colour)
        self.v_scale.set_lit(True, colour)
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
            "QFrame#controlArea { border: 1px solid #b0b6bc; border-radius: 6px; background-color: #45484d; }"
        )
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        title_label.setStyleSheet("QLabel { color: #f0f0f0; letter-spacing: 1px; }")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)
        layout.addLayout(self.grid)
        layout.addStretch()
