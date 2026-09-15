"""A status colour must not eat the word it is colouring.

The health, alarm and discovery tables set a pale background on a cell -- pale
green for healthy, pale yellow for degraded -- and set no text colour. Under
the dark application sheet the text stayed #e0e0e0, so it landed on those
fills at roughly 1.2:1. "healthy" on pale green was effectively invisible: the
colour meant to convey the status destroyed the word carrying it.

So the rule is that a background is never set without its foreground, and both
come from status_palette(). These assert the contrast arithmetic rather than
trusting that the chosen colours look fine on one machine.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from client.ui.theme import (  # noqa: E402
    STATUS_LEVELS,
    status_palette,
)

#: WCAG 2.1 AA for body text. These cells carry single words at the default
#: table size, which is not "large text" under the guideline.
AA = 4.5

THEMES = ("light", "dark")


def _relative_luminance(hex_colour):
    hex_colour = hex_colour.lstrip("#")
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        for c in channels
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a, b):
    """WCAG contrast ratio between two hex colours, 1.0 to 21.0."""
    high, low = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class TestTheArithmeticIsRight:
    """Guard the helper before trusting what it says about the palette."""

    def test_black_on_white_is_the_maximum(self):
        assert contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)

    def test_a_colour_against_itself_is_the_minimum(self):
        assert contrast("#7f7f7f", "#7f7f7f") == pytest.approx(1.0, abs=0.01)

    def test_it_does_not_depend_on_argument_order(self):
        assert contrast("#c8ffc8", "#14532d") == pytest.approx(
            contrast("#14532d", "#c8ffc8")
        )


class TestEveryStatusIsReadable:
    @pytest.mark.parametrize("theme", THEMES)
    @pytest.mark.parametrize("level", STATUS_LEVELS)
    def test_the_pair_clears_wcag_aa(self, theme, level):
        background, foreground = status_palette(theme)[level]
        ratio = contrast(background, foreground)
        assert ratio >= AA, (
            f"{level} in {theme}: {foreground} on {background} is only "
            f"{ratio:.2f}:1, below the {AA}:1 needed to read it"
        )

    @pytest.mark.parametrize("theme", THEMES)
    def test_every_level_is_covered(self, theme):
        """A missing level silently falls through to no colouring at all."""
        assert set(status_palette(theme)) == set(STATUS_LEVELS)

    @pytest.mark.parametrize("theme", THEMES)
    def test_the_levels_are_distinguishable_from_each_other(self, theme):
        """Colour is the whole point; two statuses must not share a fill."""
        fills = [status_palette(theme)[level][0] for level in STATUS_LEVELS]
        assert len(set(fills)) == len(fills), f"duplicate fills in {theme}: {fills}"


class TestTheOldBugStaysFixed:
    def test_the_dark_sheet_text_on_the_light_fills_would_fail(self):
        """The regression itself, stated as arithmetic.

        This is what the code used to do: light-mode fills with the dark
        application sheet's #e0e0e0 text over them.
        """
        worst = max(
            contrast(status_palette("light")[level][0], "#e0e0e0")
            for level in STATUS_LEVELS
        )
        assert worst < AA, (
            "the old combination now passes, so this test no longer describes "
            "a bug and should be rewritten"
        )

    @pytest.mark.parametrize("theme", THEMES)
    def test_the_foreground_is_never_left_to_the_stylesheet(self, theme):
        """Every level supplies both halves; that is what makes it safe."""
        for level in STATUS_LEVELS:
            pair = status_palette(theme)[level]
            assert len(pair) == 2
            assert all(c.startswith("#") and len(c) == 7 for c in pair), pair


GUI = True
try:
    from PyQt6.QtWidgets import QApplication, QTableWidgetItem  # noqa: F401
except ImportError:
    GUI = False


@pytest.mark.skipif(not GUI, reason="PyQt6 is required")
class TestApplyingItToAnItem:
    @pytest.fixture(scope="class")
    def qapp(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        return QApplication.instance() or QApplication([])

    def test_it_sets_both_halves(self, qapp):
        from client.ui.theme import apply_status_colors

        item = QTableWidgetItem("healthy")
        assert apply_status_colors(item, "healthy", theme="dark") is True

        background, foreground = status_palette("dark")["healthy"]
        assert item.background().color().name() == background
        assert item.foreground().color().name() == foreground

    def test_an_unknown_status_is_left_alone(self, qapp):
        """Better uncoloured than a fill with unreadable default text."""
        from client.ui.theme import apply_status_colors

        item = QTableWidgetItem("banana")
        before = item.background().color().name()

        assert apply_status_colors(item, "banana", theme="dark") is False
        assert item.background().color().name() == before

    @pytest.mark.parametrize("theme", THEMES)
    def test_what_lands_on_the_item_is_readable(self, qapp, theme):
        """Close the loop: measure the colours actually on the widget."""
        from client.ui.theme import apply_status_colors

        for level in STATUS_LEVELS:
            item = QTableWidgetItem(level)
            apply_status_colors(item, level, theme=theme)
            ratio = contrast(
                item.background().color().name(),
                item.foreground().color().name(),
            )
            assert ratio >= AA, f"{level} in {theme} renders at {ratio:.2f}:1"
