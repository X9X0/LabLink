"""A health row has to say which instrument it is about.

The health payload is keyed by equipment id and carries nothing else
identifying, so the table read as "ps_56fdd3df" and "ps_36509eb5" -- opaque on
a bench with more than one supply on it. The make and model live on the
equipment list instead, so the panel joins the two client-side. Doing it
server-side would have widened the health model and tied every client to a
matching server.

The join is best effort: losing it costs two descriptive columns, and must
never cost the health table itself.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication


    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GUI_AVAILABLE, reason="PyQt6 is required for panel tests"
)

if GUI_AVAILABLE:
    from client.ui.diagnostics_panel import DiagnosticsPanel

HEALTH = {
    "ps_56fdd3df": {
        "health_status": "degraded", "health_score": 89.3,
        "connection_status": "pass", "communication_status": "pass",
        "performance_status": "warn",
    },
    "ps_36509eb5": {
        "health_status": "healthy", "health_score": 100.0,
        "connection_status": "pass", "communication_status": "pass",
        "performance_status": "pass",
    },
}


class FakeClient:
    """Shapes taken from the live server, including its "id" spelling."""

    def __init__(self, equipment=None, fail_list=False):
        self._equipment = equipment if equipment is not None else [
            {"id": "ps_56fdd3df", "manufacturer": "BK Precision", "model": "1685B"},
            {"id": "ps_36509eb5", "manufacturer": "B&K Precision", "model": "9205B"},
        ]
        self._fail_list = fail_list

    def get_all_equipment_health(self):
        return dict(HEALTH)

    def list_equipment(self):
        if self._fail_list:
            raise RuntimeError("server refused")
        return self._equipment


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    return DiagnosticsPanel()


def refresh(panel):
    """Drive one refresh to completion.

    The panel's refresh is a coroutine now: the health query asks the server
    to benchmark every instrument, which measured 20.5s against two serial
    supplies on the bench, and running that on the GUI thread froze the
    window. Called as a plain method it would only ever create a coroutine
    and drop it, so these tests would pass against an empty table.
    """
    slot = type(panel).refresh
    return asyncio.run(getattr(slot, "__wrapped__", slot)(panel))


def headers(table):
    return [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]


def cell(table, row, column):
    item = table.item(row, column)
    return item.text() if item else None


def row_for(table, equipment_id):
    for r in range(table.rowCount()):
        if cell(table, r, 0) == equipment_id:
            return r
    raise AssertionError(f"{equipment_id} is not in the table")


class TestTheColumnsExist:
    def test_make_and_model_are_shown(self, panel):
        assert "Make" in headers(panel.health_table)
        assert "Model" in headers(panel.health_table)

    def test_they_sit_next_to_the_equipment_id(self, panel):
        """Reading left to right should identify the instrument first."""
        assert headers(panel.health_table)[:3] == ["Equipment", "Make", "Model"]

    def test_the_health_columns_are_all_still_there(self, panel):
        assert headers(panel.health_table) == [
            "Equipment", "Make", "Model", "Health Status", "Score",
            "Connection", "Communication", "Performance",
        ]


class TestTheRowsAreIdentified:
    def test_each_row_names_its_instrument(self, panel):
        panel.set_client(FakeClient())
        refresh(panel)

        row = row_for(panel.health_table, "ps_56fdd3df")
        assert cell(panel.health_table, row, 1) == "BK Precision"
        assert cell(panel.health_table, row, 2) == "1685B"

    def test_the_health_still_lines_up_with_the_right_row(self, panel):
        """The columns shifted by two; the wrong health against a name is
        worse than no name at all."""
        panel.set_client(FakeClient())
        refresh(panel)

        row = row_for(panel.health_table, "ps_56fdd3df")
        assert cell(panel.health_table, row, 3) == "degraded"
        assert cell(panel.health_table, row, 4) == "89.3"
        assert cell(panel.health_table, row, 7) == "warn"

        row = row_for(panel.health_table, "ps_36509eb5")
        assert cell(panel.health_table, row, 3) == "healthy"
        assert cell(panel.health_table, row, 4) == "100.0"

    def test_the_status_cell_is_still_coloured(self, panel):
        """apply_status_colors moved column; it must have moved with it."""
        panel.set_client(FakeClient())
        refresh(panel)

        row = row_for(panel.health_table, "ps_36509eb5")
        item = panel.health_table.item(row, 3)
        from client.ui.theme import status_palette

        expected = status_palette()["healthy"]
        assert item.background().color().name() == expected[0]
        assert item.foreground().color().name() == expected[1]

    def test_the_id_keeps_the_full_description_as_a_tooltip(self, panel):
        panel.set_client(FakeClient())
        refresh(panel)

        row = row_for(panel.health_table, "ps_56fdd3df")
        assert panel.health_table.item(row, 0).toolTip() == "BK Precision 1685B"


class TestTheJoinIsForgiving:
    def test_the_other_spelling_of_the_id_is_accepted(self, panel):
        """The list endpoint says "id"; others say "equipment_id"."""
        panel.set_client(FakeClient(equipment=[
            {"equipment_id": "ps_56fdd3df", "manufacturer": "BK", "model": "1685B"},
        ]))
        refresh(panel)

        row = row_for(panel.health_table, "ps_56fdd3df")
        assert cell(panel.health_table, row, 2) == "1685B"

    def test_equipment_missing_from_the_list_leaves_the_row_readable(self, panel):
        panel.set_client(FakeClient(equipment=[]))
        refresh(panel)

        row = row_for(panel.health_table, "ps_56fdd3df")
        assert cell(panel.health_table, row, 1) == ""
        assert cell(panel.health_table, row, 3) == "degraded", \
            "the health must survive an unidentifiable instrument"

    def test_a_failed_lookup_does_not_cost_the_health_table(self, panel):
        """The health is what the operator came to read."""
        panel.set_client(FakeClient(fail_list=True))
        refresh(panel)

        assert panel.health_table.rowCount() == len(HEALTH)
        row = row_for(panel.health_table, "ps_36509eb5")
        assert cell(panel.health_table, row, 3) == "healthy"
        assert cell(panel.health_table, row, 4) == "100.0"

    def test_missing_fields_do_not_become_the_word_none(self, panel):
        panel.set_client(FakeClient(equipment=[
            {"id": "ps_56fdd3df", "manufacturer": None, "model": None},
        ]))
        refresh(panel)

        row = row_for(panel.health_table, "ps_56fdd3df")
        assert cell(panel.health_table, row, 1) == ""
        assert cell(panel.health_table, row, 2) == ""
