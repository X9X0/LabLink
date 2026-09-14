"""The readings have to be readable, and have to mean what they say.

Three separate faults met in the digital display. It was two short bars in a
tall panel, so it used a fraction of the space the analog and graph modes
used. Its font was set with ``setFont(QFont("Arial", 48))``, which a Qt
stylesheet overrides -- and the application sheet sets
``QWidget { font-size: 9pt }``, so the code said 48pt and the screen showed
12px. And the numbers were printed to a fixed number of places regardless of
what the instrument resolves, so a supply sending hundredths was displayed as
0.300 A.

The graph mode showed no present value at all: a trend with no reading.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication

    from client.ui.control_panel import ChartWithReadouts, FittedReadout
    from client.ui.theme import dialog_palette, get_app_stylesheet

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 is required for readout tests"
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    # The application sheet is the thing that used to silently win.
    app.setStyleSheet(get_app_stylesheet("dark"))
    yield app


def settled(widget, app, width, height):
    widget.resize(width, height)
    widget.show()
    for _ in range(3):
        app.processEvents()
    return widget


class TestTheFontActuallyApplies:
    """The regression that made 48pt render at 12px."""

    def test_a_plain_label_loses_its_font_to_the_stylesheet(self, qapp):
        """Stated as a fact about Qt, so the fix's reason stays visible.

        If this ever fails, Qt changed and FittedReadout can go back to
        setFont.
        """
        from PyQt6.QtWidgets import QLabel

        label = QLabel("12.34 V")
        label.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        label.show()
        qapp.processEvents()

        assert label.fontMetrics().height() < 30, (
            "setFont now survives the application stylesheet; the workaround "
            "in FittedReadout is no longer needed"
        )

    def test_the_readout_keeps_its_size(self, qapp):
        readout = settled(FittedReadout("12.34 V"), qapp, 600, 200)
        assert readout.fontMetrics().height() > 40, (
            "the readout is being shrunk by the application sheet again"
        )

    def test_the_size_is_set_through_the_widgets_own_stylesheet(self, qapp):
        """Which is the only way that beats the application sheet."""
        readout = settled(FittedReadout("12.34 V"), qapp, 600, 200)
        assert "font-size" in readout.styleSheet()


class TestItFillsTheBox:
    def test_a_taller_box_gets_larger_text(self, qapp):
        short = settled(FittedReadout("1.00 V"), qapp, 900, 80)
        tall = settled(FittedReadout("1.00 V"), qapp, 900, 400)
        assert tall._point_size > short._point_size

    def test_a_long_reading_still_fits_across(self, qapp):
        """Width has to bind too, or the digits run off the panel."""
        readout = settled(FittedReadout("-123.456 V"), qapp, 300, 400)
        advance = readout.fontMetrics().horizontalAdvance(readout.text())
        assert advance <= readout.width(), "the reading overflows its box"

    def test_it_does_not_grow_without_limit(self, qapp):
        readout = settled(FittedReadout("1 V"), qapp, 4000, 3000)
        assert readout._point_size <= FittedReadout.MAX_POINT_SIZE

    def test_it_stays_legible_in_a_tiny_box(self, qapp):
        readout = settled(FittedReadout("1.00 V"), qapp, 40, 10)
        assert readout._point_size >= FittedReadout.MIN_POINT_SIZE

    def test_setting_new_text_refits(self, qapp):
        """Readings change constantly; a stale fit would clip them."""
        readout = settled(FittedReadout("1 V"), qapp, 300, 200)
        readout.setText("-123.456 V")
        qapp.processEvents()
        advance = readout.fontMetrics().horizontalAdvance(readout.text())
        assert advance <= readout.width()


class TestTheDigitalPanelSeparatesTheTwoReadings:
    """One black face carrying two numbers needs a rule between them, or at a
    glance it reads as one long reading."""

    @pytest.fixture
    def panel(self, qapp):
        from client.ui.control_panel import ControlPanel

        control = ControlPanel(client=None)
        control._refresh_lock_status = lambda: None
        control.resize(1300, 820)
        control.show()
        control._on_display_mode_changed("digital")
        for _ in range(4):
            control.layout().activate()
            qapp.processEvents()
        return control

    def test_the_divider_sits_between_the_readings(self, panel):
        volts, divider, amps = (
            panel.voltage_display, panel.digital_divider, panel.current_display
        )
        assert volts.x() + volts.width() <= divider.x()
        assert divider.x() + divider.width() <= amps.x()

    def test_it_is_a_rule_not_a_column(self, panel):
        """It must not take space the digits need."""
        assert panel.digital_divider.width() <= 4

    def test_it_is_actually_painted(self, panel, qapp):
        """A QFrame VLine draws from the palette and vanishes on black, which
        is why this is a plain widget with a background colour."""
        divider = panel.digital_divider
        image = panel.digital_display.grab().toImage()

        middle = image.pixelColor(
            divider.x() + divider.width() // 2,
            divider.y() + divider.height() // 2,
        ).name()
        assert middle != "#000000", "the divider is invisible against the panel"

    def test_it_is_inset_from_the_top_and_bottom(self, panel):
        """Full height would read as a border cutting the panel in two."""
        divider = panel.digital_divider
        image = panel.digital_display.grab().toImage()
        x = divider.x() + divider.width() // 2

        top = image.pixelColor(x, divider.y() + 1).name()
        middle = image.pixelColor(x, divider.y() + divider.height() // 2).name()
        bottom = image.pixelColor(x, divider.y() + divider.height() - 2).name()

        assert middle != "#000000"
        assert top == "#000000", "the rule reaches the top edge"
        assert bottom == "#000000", "the rule reaches the bottom edge"


class TestTheChartCarriesTheReadings:
    @pytest.fixture
    def view(self, qapp):
        from PyQt6.QtCharts import QChart

        view = ChartWithReadouts(QChart())
        return settled(view, qapp, 800, 400)

    def test_both_readings_are_shown(self, view):
        view.set_readings(4.77, 0.3, 2, 2)
        assert view.voltage_readout.text() == "Volts: 4.77"
        assert view.current_readout.text() == "Amps: 0.30"

    def test_they_sit_a_quarter_in_from_each_edge(self, view, qapp):
        view.set_readings(4.77, 0.3, 2, 2)
        qapp.processEvents()

        for readout, want in (
            (view.voltage_readout, 0.25),
            (view.current_readout, 0.75),
        ):
            centre = (readout.x() + readout.width() / 2) / view.width()
            assert centre == pytest.approx(want, abs=0.02), (
                f"{readout.text()} sits at {centre:.0%}, not {want:.0%}"
            )

    def test_they_sit_across_the_top(self, view):
        view.set_readings(4.77, 0.3, 2, 2)
        assert view.voltage_readout.y() < view.height() * 0.2

    def test_they_move_when_the_view_is_resized(self, view, qapp):
        """Children are positioned by hand, so nothing repositions them."""
        view.set_readings(4.77, 0.3, 2, 2)
        settled(view, qapp, 1400, 400)

        centre = (view.current_readout.x() + view.current_readout.width() / 2)
        assert centre / view.width() == pytest.approx(0.75, abs=0.02)

    def test_a_long_reading_cannot_slide_off_the_edge(self, view, qapp):
        view.set_readings(-1234.5678, -1234.5678, 4, 4)
        settled(view, qapp, 320, 300)

        for readout in (view.voltage_readout, view.current_readout):
            assert readout.x() >= 0
            assert readout.x() + readout.width() <= view.width()

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_the_colours_come_from_the_palette(self, theme):
        """No single pair reads on both cards, so they must be themed."""
        palette = dialog_palette(theme)
        assert "chart_voltage" in palette
        assert "chart_current" in palette
        assert palette["chart_voltage"] != palette["chart_current"], (
            "the two readings must be told apart at a glance"
        )


class TestTheDecimalsFollowTheInstrument:
    def test_the_places_asked_for_are_the_places_shown(self, qapp):
        from PyQt6.QtCharts import QChart

        view = settled(ChartWithReadouts(QChart()), qapp, 800, 400)

        view.set_readings(4.7, 0.3, 1, 1)
        assert view.voltage_readout.text() == "Volts: 4.7"

        view.set_readings(4.7, 0.3, 3, 3)
        assert view.voltage_readout.text() == "Volts: 4.700"

    def test_a_supply_that_sends_hundredths_is_not_shown_thousandths(self, qapp):
        """The 1685B resolves to 0.01 A; 0.300 A claims a digit it never sent."""
        from PyQt6.QtCharts import QChart

        view = settled(ChartWithReadouts(QChart()), qapp, 800, 400)
        view.set_readings(4.77, 0.30, 2, 2)

        assert view.current_readout.text() == "Amps: 0.30"
        assert not view.current_readout.text().endswith("0.300")
