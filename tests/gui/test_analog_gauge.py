"""The analog meter, as a panel meter rather than a rounded rectangle.

Two things were wrong with the old gauge. It was pinned near its minimum size
while the window had room to spare, which on a needle instrument costs real
resolution -- the travel *is* the reading. And it was a generic round dial,
where a moving-coil meter puts a shallow arc across the top and pivots low,
spreading the scale over the full width of the case.

The colours come from the theme because a meter is a physical object: it keeps
its own case rather than dissolving into the panel. Graduations, numerals and
lettering are printed in the same ink as the pointer, which is asserted here
rather than left to two values happening to agree.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication, QSizePolicy


    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 is required for gauge tests"
)

if GUI_AVAILABLE:
    import client.ui.theme as theme_module
    from client.ui.instruments import AnalogGauge, PowerSupplyPanel


def _relative_luminance(hex_colour):
    hex_colour = hex_colour.lstrip("#")
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        for c in channels
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a, b):
    high, low = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def themed(monkeypatch):
    """Paint the gauge under a named theme."""
    def use(mode):
        monkeypatch.setattr(theme_module, "get_theme_setting", lambda: mode)
        gauge = AnalogGauge("Voltage", 0, 18, "V")
        gauge.resize(440, 300)
        gauge.show()
        gauge.set_value(4.77)
        gauge._load_theme()
        return gauge
    return use


class TestItGrowsWithTheWindow:
    def test_the_gauge_expands(self, qapp):
        assert (AnalogGauge().sizePolicy().verticalPolicy()
                == QSizePolicy.Policy.Expanding)

    def test_a_bigger_window_gives_a_bigger_meter(self, qapp):
        panel = PowerSupplyPanel()
        panel._on_display_mode_changed("analog")

        sizes = []
        for width, height in ((1200, 700), (1900, 1200)):
            panel.resize(width, height)
            panel.show()
            for _ in range(3):
                panel.layout().activate()
                qapp.processEvents()
            sizes.append(panel.voltage_gauge.height())

        assert sizes[1] > sizes[0], (
            f"the meter stayed {sizes[1]}px tall when the window grew"
        )


class TestTheCaseFollowsTheTheme:
    @pytest.mark.parametrize("mode,face_is_dark", [("light", False), ("dark", True)])
    def test_the_card_inverts(self, qapp, themed, mode, face_is_dark):
        gauge = themed(mode)
        assert (gauge.FACE.lightness() < 128) is face_is_dark

    def test_the_bezel_stays_grey_in_both(self, qapp, themed):
        """It is a case, not a background: it should not vanish into the panel."""
        for mode in ("light", "dark"):
            gauge = themed(mode)
            red, green, blue = gauge.BEZEL.red(), gauge.BEZEL.green(), gauge.BEZEL.blue()
            assert max(red, green, blue) - min(red, green, blue) < 12, (
                f"{mode} bezel {gauge.BEZEL.name()} is not grey"
            )
            assert 40 < gauge.BEZEL.lightness() < 200, "not a mid grey"

    def test_the_pointer_is_black_in_light_and_green_in_dark(self, qapp, themed):
        assert themed("light").NEEDLE.lightness() < 60
        dark_needle = themed("dark").NEEDLE
        assert dark_needle.green() > dark_needle.red()
        assert dark_needle.green() > dark_needle.blue()

    @pytest.mark.parametrize("mode", ["light", "dark"])
    def test_the_printing_matches_the_pointer(self, qapp, themed, mode):
        """One ink, so they cannot drift apart."""
        gauge = themed(mode)
        assert gauge.INK.name() == gauge.NEEDLE.name()

    @pytest.mark.parametrize("mode", ["light", "dark"])
    def test_the_scale_is_readable_on_the_card(self, qapp, themed, mode):
        gauge = themed(mode)
        ratio = contrast(gauge.FACE.name(), gauge.INK.name())
        assert ratio >= 4.5, f"{mode}: scale at {ratio:.2f}:1 on its own face"

    @pytest.mark.parametrize("mode", ["light", "dark"])
    def test_the_case_is_painted_not_inherited(self, qapp, themed, mode):
        """Sampled off the widget, away from the rounded corners."""
        gauge = themed(mode)
        image = gauge.grab().toImage()
        assert image.pixelColor(220, 5).name() == gauge.BEZEL.name()


class TestItReadsLikeAMeter:
    def test_the_needle_sweeps_from_left_to_right(self, qapp):
        gauge = AnalogGauge("Voltage", 0, 18, "V")
        assert gauge._angle_for(0) > gauge._angle_for(18), (
            "the pointer runs backwards"
        )

    def test_the_arc_is_shallow_rather_than_a_full_dial(self, qapp):
        """A moving-coil meter sweeps about 130 degrees, not 270."""
        assert 90 <= AnalogGauge.SWEEP <= 160

    def test_the_pivot_sits_low_in_the_case(self, qapp):
        """Which is what spreads the scale across the width."""
        gauge = AnalogGauge("Voltage", 0, 18, "V")
        gauge.resize(440, 300)
        face = gauge._face_rect()
        _, pivot_y, _ = gauge._pivot_and_radius(face)

        assert pivot_y > face.center().y(), "the pivot is not below centre"

    def test_a_value_past_full_scale_does_not_leave_the_dial(self, qapp):
        gauge = AnalogGauge("Voltage", 0, 18, "V")
        gauge.set_value(999)
        assert gauge._angle_for(gauge.current_value) >= (
            AnalogGauge.START_ANGLE - AnalogGauge.SWEEP
        )

    def test_units_are_spelled_out(self, qapp):
        assert AnalogGauge("Voltage", 0, 18, "V")._unit_caption() == "VOLTS"
        assert AnalogGauge("Current", 0, 5, "A")._unit_caption() == "AMPS"

    def test_a_zero_span_does_not_divide_by_zero(self, qapp):
        """Auto-range can floor a scale; it must not crash the paint."""
        gauge = AnalogGauge("Voltage", 0, 0, "V")
        gauge.resize(200, 160)
        gauge.set_value(0)
        gauge.grab()  # would raise if the paint path divided by the span
