"""Display widgets shared by the instrument panels.

Moved out of control_panel.py so every panel -- supply, load, multimeter --
draws its numbers, meters and traces with the same parts rather than each
growing its own.
"""

import math

from PyQt6.QtCharts import QChartView
from PyQt6.QtCore import QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from client.ui.theme import dialog_palette


class FittedReadout(QLabel):
    """A readout whose text is sized to fill the box it is given.

    Two things made the digital display unreadable. The obvious one is that it
    was two short bars while the analog and graph modes filled the panel. The
    other is that ``setFont(QFont("Arial", 48))`` never took effect at all: a
    Qt stylesheet beats setFont, and the application sheet sets
    ``QWidget { font-size: 9pt }``, so the readout rendered at 12px while the
    code said 48pt. Anything that sets a size here has to do it through this
    widget's own stylesheet, which is what ``_apply_font_size`` does.

    Sizing on every resize, rather than at one fixed point size, is what makes
    "fills the box" true at more than one window size.
    """

    #: Fraction of the box height one line of digits should occupy.
    HEIGHT_RATIO = 0.62

    #: Never grow past this, or a maximised window turns the reading into
    #: wallpaper and the decimals stop being scannable at a glance.
    MAX_POINT_SIZE = 200

    MIN_POINT_SIZE = 8

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._point_size = None
        self._apply_font_size(self.MIN_POINT_SIZE)

    def _apply_font_size(self, point_size: int):
        if point_size == self._point_size:
            return
        self._point_size = point_size
        # Colours stay with the panel; only the size is this widget's business.
        self.setStyleSheet(
            f"QLabel {{ background-color: transparent; color: #39FF14; "
            f"font-family: Arial; font-weight: bold; "
            f"font-size: {point_size}pt; }}"
        )

    def _fit(self):
        """Largest point size whose text fits the current box, both ways."""
        text = self.text() or "0"
        available_h = max(self.height() - 8, 1)
        available_w = max(self.width() - 16, 1)

        target = int(available_h * self.HEIGHT_RATIO)
        size = max(self.MIN_POINT_SIZE, min(self.MAX_POINT_SIZE, target))

        # Point size sets the line height; the string still has to fit across.
        # Shrink until it does rather than letting Qt elide or clip it.
        while size > self.MIN_POINT_SIZE:
            font = QFont("Arial", size, QFont.Weight.Bold)
            if QFontMetrics(font).horizontalAdvance(text) <= available_w:
                break
            size -= 1

        self._apply_font_size(size)

    def setText(self, text):
        super().setText(text)
        self._fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class ChartWithReadouts(QChartView):
    """A chart view carrying a live voltage and current reading across its top.

    The numbers are children of the view rather than a row above it, so they
    sit on the chart's own face where the reading belongs -- next to the trace
    it describes, not on the panel behind it. Qt lays out children only when
    something asks it to, so the positions are recomputed on every resize.
    """

    #: Horizontal placement, as a fraction of the view's width. A quarter in
    #: from each edge keeps both clear of the chart title in the middle.
    LEFT_FRACTION = 0.25
    RIGHT_FRACTION = 0.75

    #: Down from the top, as a fraction of height -- level with the title.
    TOP_FRACTION = 0.07

    #: Point size when there is room for it, and the floor when there is not.
    #: A reading is never elided to fit: half a number looks like a whole one
    #: and would be misread, so the text shrinks instead.
    POINT_SIZE = 16
    MIN_POINT_SIZE = 7

    def __init__(self, chart, parent=None):
        super().__init__(chart, parent)

        self.voltage_readout = QLabel("Volts: 0.000", self)
        self.current_readout = QLabel("Amps: 0.000", self)

        _c = dialog_palette()
        for readout, colour in (
            # Close to the series colours, so each number reads as belonging
            # to its trace, but chosen against the card the chart theme paints
            # rather than copied from the line: the series blue sits at 4.3:1
            # on the dark card, which is below what is comfortably readable.
            (self.voltage_readout, _c["chart_voltage"]),
            (self.current_readout, _c["chart_current"]),
        ):
            readout.setProperty("colour", colour)
            self._set_point_size(readout, self.POINT_SIZE)
            readout.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            readout.adjustSize()

    def _set_point_size(self, readout, point_size):
        if readout.property("pointSize") == point_size:
            return
        readout.setProperty("pointSize", point_size)
        colour = readout.property("colour")
        readout.setStyleSheet(
            f"QLabel {{ background-color: transparent; color: {colour}; "
            f"font-family: Arial; font-weight: bold; "
            f"font-size: {point_size}pt; }}"
        )

    def _fit(self, readout):
        """Shrink until the reading fits its half of the view."""
        available = max(self.width() // 2 - 16, 1)
        size = self.POINT_SIZE
        while size > self.MIN_POINT_SIZE:
            self._set_point_size(readout, size)
            readout.adjustSize()
            if readout.width() <= available:
                break
            size -= 1
        else:
            self._set_point_size(readout, self.MIN_POINT_SIZE)
            readout.adjustSize()

    def _place(self):
        top = int(self.height() * self.TOP_FRACTION)

        for readout, fraction in (
            (self.voltage_readout, self.LEFT_FRACTION),
            (self.current_readout, self.RIGHT_FRACTION),
        ):
            self._fit(readout)
            # Centred on the fraction, then clamped so a long reading cannot
            # slide off either edge of the view.
            x = int(self.width() * fraction) - readout.width() // 2
            x = max(4, min(x, self.width() - readout.width() - 4))
            readout.move(x, top)
            readout.raise_()

    def set_readings(self, voltage: float, current: float,
                     voltage_decimals: int = 3, current_decimals: int = 3):
        self.voltage_readout.setText(f"Volts: {voltage:.{voltage_decimals}f}")
        self.current_readout.setText(f"Amps: {current:.{current_decimals}f}")
        self._place()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place()


class AnalogGauge(QWidget):
    """A panel meter in the manner of a Simpson Model 29.

    The shape is doing work, not decoration. A moving-coil meter puts a
    shallow arc across the top and pivots the needle from low down, which
    spreads the scale over the full width of the case and gives far more
    travel per unit than a round dial squeezed into the same box. The fine
    minor ticks are what let you read between the numbers, which is the whole
    reason to watch a needle rather than a number.

    It draws to whatever rectangle it is given, so the meter grows with the
    window the way the digital and graph modes do.
    """

    #: The arc, in degrees as QPainter measures them: zero at three o-clock,
    #: counter-clockwise positive. A shallow sweep across the top.
    START_ANGLE = 155
    SWEEP = 130

    #: Fallbacks only. The real colours come from the theme at paint time, so
    #: switching theme restyles the meter without rebuilding the panel.
    BEZEL = QColor("#6e6e6e")
    FACE = QColor("#f2efe6")
    INK = QColor("#141414")
    NEEDLE = QColor("#101010")
    DANGER = QColor("#8c1c13")
    #: Min/max pointers. Amber rather than the face's own ink: at an
    #: opacity low enough not to compete with the needle, ink was
    #: quiet enough to be missed. A different hue reads as a
    #: different kind of mark, which is what it is.
    MARKER = QColor("#c87800")

    def __init__(self, title="", min_value=0, max_value=100, unit="", parent=None):
        """Initialize analog gauge.

        Args:
            title: Gauge title
            min_value: Minimum value
            max_value: Maximum value
            unit: Unit of measurement
            parent: Parent widget
        """
        super().__init__(parent)
        self.title = title
        self.min_value = min_value
        self.max_value = max_value
        self.unit = unit
        self.current_value = 0.0
        #: Lowest and highest reading to mark on the face, or None for
        #: neither. Set from the panel's Min/Max tracking; see
        #: :meth:`set_markers`.
        self.min_marker = None
        self.max_marker = None

        self.setMinimumSize(220, 170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_value(self, value: float):
        """Set the current value and update display."""
        self.current_value = max(self.min_value, min(self.max_value, value))
        self.update()

    def set_markers(self, lowest=None, highest=None):
        """Mark the extremes seen, or pass nothing to clear them.

        Drawn as two thin pointers just outside the graduations, the way
        a maximum-demand indicator sits on a real meter: readable at a
        glance, and quiet enough that the needle is still the thing the
        eye goes to. Out-of-scale values are pinned to the ends rather
        than dropped, so a marker never silently disappears.
        """
        def on_scale(value):
            if value is None:
                return None
            return max(self.min_value, min(self.max_value, float(value)))

        self.min_marker = on_scale(lowest)
        self.max_marker = on_scale(highest)
        self.update()

    # -- geometry ---------------------------------------------------------

    def _face_rect(self):
        """The card inside the bezel."""
        margin = max(6, int(min(self.width(), self.height()) * 0.05))
        return self.rect().adjusted(margin, margin, -margin, -margin)

    def _pivot_and_radius(self, face):
        """Where the needle turns, and how far the scale sits from it.

        The pivot sits low so the arc rides high in the case, as it does on
        the real instrument.
        """
        pivot_x = face.center().x()
        pivot_y = face.bottom() - int(face.height() * 0.16)
        radius = min(face.width() * 0.46, face.height() * 0.80)
        return pivot_x, pivot_y, radius

    def _angle_for(self, value):
        span = self.max_value - self.min_value
        fraction = 0.0 if span <= 0 else (value - self.min_value) / span
        fraction = max(0.0, min(1.0, fraction))
        return self.START_ANGLE - fraction * self.SWEEP

    def _load_theme(self):
        """Take the case colours from the palette.

        A panel meter is a physical object, so it keeps its own case rather
        than dissolving into the panel: a grey bezel in both themes, with a
        cream card and a black pointer in light, and a black card and a green
        pointer in dark.
        """
        try:
            from client.ui.theme import dialog_palette

            palette = dialog_palette()
        except Exception:
            return  # the class fallbacks are already sensible

        self.BEZEL = QColor(palette.get("meter_bezel", self.BEZEL))
        self.FACE = QColor(palette.get("meter_face", self.FACE))
        self.NEEDLE = QColor(palette.get("meter_needle", self.NEEDLE))
        self.DANGER = QColor(palette.get("meter_danger", self.DANGER))
        self.MARKER = QColor(palette.get("meter_marker", self.MARKER))

        # Graduations, numerals and lettering are printed in the same ink as
        # the pointer, so it is one value rather than two that have to be kept
        # agreeing with each other.
        self.INK = QColor(self.NEEDLE)

    def paintEvent(self, event):
        self._load_theme()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._draw_case(painter)
        face = self._face_rect()
        pivot_x, pivot_y, radius = self._pivot_and_radius(face)

        self._draw_scale(painter, pivot_x, pivot_y, radius)
        self._draw_legends(painter, face, pivot_x, pivot_y, radius)
        # Before the needle, so the needle passes over a marker rather
        # than being obscured by one.
        self._draw_markers(painter, pivot_x, pivot_y, radius)
        self._draw_needle(painter, pivot_x, pivot_y, radius)
        painter.end()

    # -- the parts --------------------------------------------------------

    def _draw_case(self, painter):
        """Bezel, then the card inside it, then the two bezel screws."""
        corner = max(8, int(min(self.width(), self.height()) * 0.07))
        painter.setPen(QPen(self.BEZEL.lighter(135), 2))
        painter.setBrush(self.BEZEL)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), corner, corner)

        face = self._face_rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.FACE)
        painter.drawRoundedRect(face, corner // 2, corner // 2)

        # The screws are most of what makes this read as a panel meter rather
        # than a rounded rectangle.
        screw = max(2, int(face.width() * 0.012))
        # The screws are hardware, not print, so they take the case colour
        # rather than the ink -- otherwise they turn green in dark mode.
        painter.setBrush(self.BEZEL.lighter(150))
        for x in (face.left() + int(face.width() * 0.16),
                  face.right() - int(face.width() * 0.16)):
            painter.drawEllipse(QPoint(x, face.top() + int(face.height() * 0.10)),
                                screw, screw)

    def _draw_scale(self, painter, pivot_x, pivot_y, radius):
        """Major ticks with numbers, and the minor ticks you read between."""
        majors = 6
        minors_per_major = 5
        total = majors * minors_per_major

        number_size = max(6, int(radius * 0.085))
        painter.setFont(QFont("Arial", number_size))

        for step in range(total + 1):
            fraction = step / total
            angle = math.radians(self.START_ANGLE - fraction * self.SWEEP)
            is_major = step % minors_per_major == 0

            outer = radius
            inner = radius - (radius * (0.11 if is_major else 0.06))
            width = max(1, int(radius * (0.016 if is_major else 0.008)))

            # The top of the scale is where a supply is working hardest, so
            # the last fifth is marked the way the instrument marks it.
            over = fraction > 0.8
            painter.setPen(QPen(self.DANGER if over else self.INK, width))
            painter.drawLine(
                int(pivot_x + inner * math.cos(angle)),
                int(pivot_y - inner * math.sin(angle)),
                int(pivot_x + outer * math.cos(angle)),
                int(pivot_y - outer * math.sin(angle)),
            )

            if is_major:
                value = self.min_value + (self.max_value - self.min_value) * fraction
                label_radius = radius - radius * 0.22
                x = pivot_x + label_radius * math.cos(angle)
                y = pivot_y - label_radius * math.sin(angle)
                painter.setPen(self.INK)
                text = f"{value:g}" if value == int(value) else f"{value:.1f}"
                box = int(radius * 0.32)
                painter.drawText(
                    int(x - box / 2), int(y - number_size), box, number_size * 2,
                    Qt.AlignmentFlag.AlignCenter, text,
                )

        painter.setPen(QPen(self.INK, max(1, int(radius * 0.010))))
        arc_box = QRect(int(pivot_x - radius), int(pivot_y - radius),
                        int(radius * 2), int(radius * 2))
        painter.drawArc(arc_box, int((self.START_ANGLE - self.SWEEP) * 16),
                        int(self.SWEEP * 16))

    def _draw_legends(self, painter, face, pivot_x, pivot_y, radius):
        """DIRECT CURRENT above, the unit below, and the maker mark."""
        painter.setPen(self.INK)

        small = max(5, int(radius * 0.065))
        painter.setFont(QFont("Arial", small))
        painter.drawText(
            face.adjusted(0, int(face.height() * 0.06), 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "DIRECT CURRENT",
        )

        unit_size = max(7, int(radius * 0.13))
        painter.setFont(QFont("Arial", unit_size, QFont.Weight.Bold))
        painter.drawText(
            QRect(face.left(), pivot_y - int(radius * 0.36), face.width(),
                  unit_size * 2),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self._unit_caption(),
        )

        script = QFont("Segoe Script", max(6, int(radius * 0.085)))
        script.setItalic(True)
        painter.setFont(script)
        painter.drawText(
            QRect(face.left(), pivot_y - int(radius * 0.17), face.width(),
                  int(radius * 0.24)),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "LabLink",
        )

        tiny = max(4, int(radius * 0.055))
        painter.setFont(QFont("Arial", tiny))
        painter.drawText(
            face.adjusted(int(face.width() * 0.06), 0, 0,
                          -int(face.height() * 0.06)),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
            "MODEL 29",
        )

    def _unit_caption(self):
        """VOLTS and AMPS, spelled out as the instrument spells them."""
        spelled = {"V": "VOLTS", "A": "AMPS", "W": "WATTS"}
        return spelled.get(self.unit, (self.title or self.unit).upper())

    def _draw_markers(self, painter, pivot_x, pivot_y, radius):
        """The min and max pointers, outside the graduations.

        Kept deliberately quiet. These are reference marks, not the
        reading: a hairline at reduced opacity with a small solid
        triangle at the arc, in the same ink as the print so it belongs
        to the face rather than sitting on top of it. The needle is
        still what the eye lands on.

        They ride just outside the tick band -- the majors reach in to
        0.89 of the radius -- so they cannot be mistaken for
        graduations, and both markers share one style because their
        positions already say which is which.
        """
        for value in (self.min_marker, self.max_marker):
            if value is None:
                continue
            angle = math.radians(self._angle_for(value))
            cos_a, sin_a = math.cos(angle), math.sin(angle)

            outer = radius * 1.005
            inner = radius * 0.90

            ink = QColor(self.MARKER)
            ink.setAlpha(150)
            painter.setPen(QPen(ink, max(1, int(radius * 0.012))))
            painter.drawLine(
                QPoint(int(pivot_x + inner * cos_a), int(pivot_y - inner * sin_a)),
                QPoint(int(pivot_x + outer * cos_a), int(pivot_y - outer * sin_a)),
            )

            # A small triangle at the outer end, pointing in at the
            # scale, which is what makes it read as a pointer rather
            # than an extra tick.
            size = max(2, int(radius * 0.045))
            tip_x = pivot_x + inner * cos_a
            tip_y = pivot_y - inner * sin_a
            base_x = pivot_x + outer * cos_a
            base_y = pivot_y - outer * sin_a
            across_x = -sin_a * size * 0.5
            across_y = -cos_a * size * 0.5
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            painter.drawPolygon(
                QPoint(int(tip_x), int(tip_y)),
                QPoint(int(base_x + across_x), int(base_y + across_y)),
                QPoint(int(base_x - across_x), int(base_y - across_y)),
            )

    def _draw_needle(self, painter, pivot_x, pivot_y, radius):
        """A tapered pointer, with the counterweight stub behind the pivot."""
        angle = math.radians(self._angle_for(self.current_value))
        length = radius * 0.94
        half_width = max(1.5, radius * 0.018)

        tip = QPointF(pivot_x + length * math.cos(angle),
                      pivot_y - length * math.sin(angle))
        across = angle + math.pi / 2
        left = QPointF(pivot_x + half_width * math.cos(across),
                       pivot_y - half_width * math.sin(across))
        right = QPointF(pivot_x - half_width * math.cos(across),
                        pivot_y + half_width * math.sin(across))
        tail = QPointF(pivot_x - radius * 0.10 * math.cos(angle),
                       pivot_y + radius * 0.10 * math.sin(angle))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.NEEDLE)
        painter.drawPolygon(QPolygonF([tip, left, tail, right]))

        hub = max(3, int(radius * 0.045))
        painter.setBrush(self.NEEDLE.darker(140))
        painter.drawEllipse(QPoint(int(pivot_x), int(pivot_y)), hub, hub)


def nice_range(seen: float, instrument_max: float, floor: float) -> float:
    """A round-ish top of scale a little above ``seen``.

    Headroom above the reading, so a rising value does not immediately peg; a
    floor, so a reading near zero does not produce a meaningless scale; and
    never beyond what the instrument can do.

    Rounded up to a readable multiple of a power of ten, so a gauge's ten
    divisions land on sensible numbers rather than 3.7 volts each. Finer than
    the usual 1/2/5 because the point is resolution: on 1/2/5 a 5 V reading
    jumps to a 10 V scale and gains almost nothing.
    """
    target = max(abs(seen) * 1.25, floor)
    if target >= instrument_max:
        return instrument_max

    exponent = math.floor(math.log10(target))
    base = 10 ** exponent
    for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if target <= step * base:
            return min(step * base, instrument_max)
    return instrument_max
