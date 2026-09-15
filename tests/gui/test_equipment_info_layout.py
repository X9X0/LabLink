"""The equipment details read as a table, not as two columns pushed apart.

With neither grid column given a stretch, QGridLayout splits the spare width
evenly between them. The captions sat at the left and every value began at the
halfway mark, so reading "Model:" meant tracking across a hand's width of
empty space to reach the answer. The caption column should take its natural
width and the value column should absorb the rest.

The application stylesheet has to be applied for this to reproduce at all: a
bare panel lays the same grid out tightly and the bug is invisible. A test
that cannot see the bug it was written for is worse than no test, so the
sheet is applied here and `test_the_check_can_see_the_bug` puts the original
configuration back and asserts the measurement flags it.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from client.ui.equipment_panel import EquipmentPanel
    from client.ui.theme import get_app_stylesheet

    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 is required for layout tests"
)

VALUES = ("1902B", "power_supply", "B&K Precision", "1902B",
          "ASRL/dev/ttyUSB0::INSTR", "CONNECTED")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(get_app_stylesheet("dark"))
    return app


def _value_labels(panel):
    return (panel.name_label, panel.type_label, panel.manufacturer_label,
            panel.model_label, panel.resource_label, panel.status_label)


def _build(qapp, revert_to_original=False):
    panel = EquipmentPanel()
    grid = panel.model_label.parentWidget().layout()
    if revert_to_original:
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        for value in _value_labels(panel):
            value.setAlignment(Qt.AlignmentFlag.AlignLeft
                               | Qt.AlignmentFlag.AlignVCenter)
    for value, text in zip(_value_labels(panel), VALUES):
        value.setText(text)
    panel.resize(1900, 1000)
    panel.show()
    for _ in range(5):
        panel.layout().activate()
        qapp.processEvents()
    return panel


def _indent_fraction(panel):
    """How far across the group the values begin, as a fraction of its width."""
    group = panel.model_label.parentWidget()
    return panel.model_label.geometry().left() / group.width()


@pytest.fixture
def panel(qapp):
    return _build(qapp)


@pytest.mark.parametrize("index,attribute", list(enumerate(
    ["name_label", "type_label", "manufacturer_label",
     "model_label", "resource_label", "status_label"])))
def test_values_are_left_aligned(panel, index, attribute):
    alignment = getattr(panel, attribute).alignment()
    assert alignment & Qt.AlignmentFlag.AlignLeft, f"{attribute} is not left aligned"


def test_the_value_column_takes_the_slack(panel):
    """Not the caption column, which is what pushed the values to the middle."""
    grid = panel.model_label.parentWidget().layout()
    assert grid.columnStretch(1) > grid.columnStretch(0)


def test_values_start_beside_their_captions(panel):
    indent = _indent_fraction(panel)
    assert indent < 0.25, (
        f"values begin {indent:.0%} of the way across the panel"
    )


def test_the_check_can_see_the_bug(qapp):
    """Guard the guard: put the original layout back and confirm it fails."""
    original = _build(qapp, revert_to_original=True)
    indent = _indent_fraction(original)
    assert indent >= 0.25, (
        "the original layout measured as fine, so this check proves nothing "
        f"(values began {indent:.0%} across)"
    )
