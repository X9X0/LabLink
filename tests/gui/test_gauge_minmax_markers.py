"""The extremes belong on the meter face, not only in the readout.

Asked for from the bench: "for the analog gauges on both it would be
nice to have a min/max marker on the gauge face as well... it should be
subtle but readable when min/max mode is enabled."

The numbers were already printed beside the Min/Max button. The point
of the markers is reading them while watching the needle, which is the
reason to be in analog mode rather than digital in the first place --
so they have to be quiet enough that the needle is still what the eye
lands on, and they have to disappear when tracking is off rather than
sitting there looking current.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    import PyQt6.QtWidgets  # noqa: F401

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

if GUI_AVAILABLE:
    from PyQt6.QtWidgets import QApplication

    from client.ui.instruments import AnalogGauge, PowerSupplyPanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def gauge(qapp):
    made = AnalogGauge("Voltage", 0, 60, "V")
    yield made
    made.deleteLater()
    qapp.processEvents()


class TestTheMarkersAreHeld:
    def test_none_to_begin_with(self, gauge):
        assert gauge.min_marker is None and gauge.max_marker is None

    def test_setting_them_keeps_them(self, gauge):
        gauge.set_markers(2.5, 41.0)
        assert gauge.min_marker == pytest.approx(2.5)
        assert gauge.max_marker == pytest.approx(41.0)

    def test_clearing_them(self, gauge):
        gauge.set_markers(2.5, 41.0)
        gauge.set_markers(None, None)
        assert gauge.min_marker is None and gauge.max_marker is None

    def test_an_off_scale_marker_is_pinned_not_dropped(self, gauge):
        """A marker that silently vanished would be worse than a wrong one."""
        gauge.set_markers(-5.0, 900.0)
        assert gauge.min_marker == pytest.approx(0)
        assert gauge.max_marker == pytest.approx(60)

    def test_one_without_the_other(self, gauge):
        gauge.set_markers(None, 12.0)
        assert gauge.min_marker is None
        assert gauge.max_marker == pytest.approx(12.0)


class TestTheyAreDrawn:
    """Painting offscreen, so the assertion is that it paints at all and
    that the marker changes what comes out."""

    @staticmethod
    def _rendered(gauge):
        from PyQt6.QtGui import QImage, QPainter

        gauge.resize(240, 180)
        image = QImage(240, 180, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        gauge.render(painter)
        painter.end()
        return image

    def test_painting_with_markers_does_not_raise(self, gauge):
        gauge.set_value(30.0)
        gauge.set_markers(5.0, 55.0)
        self._rendered(gauge)           # must not raise

    def test_the_face_actually_changes(self, gauge):
        """Otherwise the marker is held and never reaches the glass."""
        gauge.set_value(30.0)
        gauge.set_markers(None, None)
        before = self._rendered(gauge)

        gauge.set_markers(5.0, 55.0)
        after = self._rendered(gauge)

        assert before != after, (
            "the markers are stored but nothing is drawn for them")

    def test_they_are_subtle_rather_than_dominant(self, gauge):
        """'Subtle but readable' -- so they must not repaint the face.

        Counted in changed pixels: two hairlines and two small
        triangles on a 240x180 meter is a small fraction of it. A
        marker drawn like a second needle would blow past this.
        """
        gauge.set_value(30.0)
        gauge.set_markers(None, None)
        before = self._rendered(gauge)
        gauge.set_markers(5.0, 55.0)
        after = self._rendered(gauge)

        changed = sum(
            1
            for y in range(before.height())
            for x in range(before.width())
            if before.pixel(x, y) != after.pixel(x, y)
        )
        total = before.width() * before.height()
        assert 0 < changed < total * 0.06, (
            f"markers changed {changed / total:.1%} of the face; they are "
            f"reference marks, not the reading")


class TestThePanelDrivesThem:
    @pytest.fixture
    def panel(self, qapp):
        made = PowerSupplyPanel()
        yield made
        made.deleteLater()
        qapp.processEvents()

    def test_tracking_off_means_no_markers(self, panel):
        panel.minmax_button.setChecked(False)
        panel._extremes = {"v_min": 1.0, "v_max": 9.0,
                           "i_min": 0.1, "i_max": 0.9}
        panel._mark_extremes_on_gauges()

        assert panel.voltage_gauge.min_marker is None
        assert panel.current_gauge.max_marker is None

    def test_tracking_on_puts_them_on_both_gauges(self, panel):
        panel.minmax_button.setChecked(True)
        panel._extremes = {"v_min": 1.0, "v_max": 9.0,
                           "i_min": 0.1, "i_max": 0.9}
        panel._mark_extremes_on_gauges()

        assert panel.voltage_gauge.min_marker == pytest.approx(1.0)
        assert panel.voltage_gauge.max_marker == pytest.approx(9.0)
        assert panel.current_gauge.min_marker == pytest.approx(0.1)
        assert panel.current_gauge.max_marker == pytest.approx(0.9)

    def test_switching_tracking_off_clears_the_face(self, panel):
        """A stale pair left sitting there would read as current."""
        panel.minmax_button.setChecked(True)
        panel._extremes = {"v_min": 1.0, "v_max": 9.0,
                           "i_min": 0.1, "i_max": 0.9}
        panel._mark_extremes_on_gauges()
        assert panel.voltage_gauge.max_marker is not None

        panel.minmax_button.setChecked(False)
        panel._on_minmax_toggled(False)

        assert panel.voltage_gauge.min_marker is None
        assert panel.voltage_gauge.max_marker is None

    def test_tracking_a_reading_reaches_the_gauge(self, panel):
        """End to end: the poll path, not just the helper."""
        panel.minmax_button.setChecked(True)
        panel._reset_extremes()

        panel._track_extremes(12.0, 1.5)
        panel._track_extremes(3.0, 0.2)

        assert panel.voltage_gauge.min_marker == pytest.approx(3.0)
        assert panel.voltage_gauge.max_marker == pytest.approx(12.0)
