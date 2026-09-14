"""The update log has to use the window it is given.

It was capped at 200px, so on a maximised window it stayed about ten lines
tall with a third of the screen empty beneath it -- while streaming a remote
build log, which is the one thing worth reading at that moment.

A size policy alone would not have fixed it: every sibling group had an equal
claim on the spare height, so the stretch factor is what actually hands it
over. Both are asserted, because either alone silently does nothing.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication, QSizePolicy

    from client.ui.system_panel import SystemPanel

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 is required for panel tests"
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    return SystemPanel()


def sized(panel, app, width, height):
    panel.resize(width, height)
    panel.show()
    for _ in range(3):
        panel.layout().activate()
        app.processEvents()
    return panel


class TestTheUpdateLogFillsTheWindow:
    def test_a_taller_window_gives_a_taller_log(self, panel, qapp):
        sized(panel, qapp, 1400, 800)
        short = panel.logs_text.height()

        sized(panel, qapp, 2000, 1400)
        tall = panel.logs_text.height()

        assert tall > short, (
            f"the log stayed {tall}px when the window grew by 600px"
        )

    def test_it_is_not_capped(self, panel, qapp):
        """setMaximumHeight(200) is what pinned it."""
        sized(panel, qapp, 2000, 1400)

        assert panel.logs_text.height() > 200, (
            "the log is still capped near 200px"
        )

    def test_it_takes_a_real_share_of_a_large_window(self, panel, qapp):
        sized(panel, qapp, 2000, 1400)

        share = panel.logs_text.height() / panel.height()
        assert share > 0.25, (
            f"the log is only {share:.0%} of the window; the spare height is "
            f"going somewhere else"
        )

    def test_it_does_not_collapse_in_a_small_window(self, panel, qapp):
        """Expanding in both directions, so it must still have a floor."""
        sized(panel, qapp, 900, 600)

        assert panel.logs_text.height() >= 100, "the log has been squeezed away"

    def test_both_halves_of_the_fix_are_present(self, panel):
        """A policy with no stretch factor, or the reverse, does nothing."""
        policy = panel.logs_text.sizePolicy()
        assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding

        import inspect

        source = inspect.getsource(SystemPanel._setup_ui)
        assert "layout.addWidget(logs_group, 1)" in source, (
            "the logs group has no stretch factor, so it cannot claim the space"
        )
