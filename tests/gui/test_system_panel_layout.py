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


class TestItNamesWhatAnUpdateWillInterrupt:
    """An output left enabled stays enabled with nothing watching it, which
    on a bench is worth saying before starting rather than after."""

    def _panel(self, qapp, items):
        class Client:
            host = "192.168.91.191"

            def list_equipment(self):
                return items

        panel = SystemPanel()
        panel.client = Client()
        return panel

    @pytest.mark.asyncio
    async def test_open_instruments_are_named(self, qapp):
        panel = self._panel(qapp, [
            {"id": "a", "manufacturer": "B&K", "model": "1685B", "connected": True},
        ])
        assert await panel._instruments_in_use() == ["B&K 1685B"]

    @pytest.mark.asyncio
    async def test_remembered_but_closed_ones_are_not_in_use(self, qapp):
        """They are listed for convenience; no port is held open."""
        panel = self._panel(qapp, [
            {"id": "a", "manufacturer": "B&K", "model": "1685B", "connected": False},
        ])
        assert await panel._instruments_in_use() == []

    @pytest.mark.asyncio
    async def test_an_unreachable_server_is_not_fatal(self, qapp):
        """Not knowing must not block the update that would fix it."""
        class Broken:
            host = "x"

            def list_equipment(self):
                raise RuntimeError("server down")

        panel = SystemPanel()
        panel.client = Broken()
        assert await panel._instruments_in_use() == []

class TestConnectingUsesTheModelsOwnFieldNames:
    """The client model and the server payload name things differently.

    The dataclass has resource_name and equipment_type; the JSON has
    resource_string and type. Asking the dataclass for the server names
    raised AttributeError, which the UI reported as "Connection failed:
    'Equipment' object has no attribute 'resource_string'" -- a message that
    reads like the instrument refused, not like our own bug.

    It stayed hidden while a 404 storm on the readings timer kept the connect
    task from ever being entered.
    """

    def test_the_attributes_asked_for_exist(self):
        """Every attribute the panel reads off the model must be on it.

        This checked only ``connect_equipment``, via
        ``inspect.getsource`` on the method. Two things then let the same
        mistake ship again in ``remove_equipment``: it aliases
        ``eq = self.selected_equipment`` and read ``eq.resource_string``, and
        it is wrapped in ``@qasync.asyncSlot()``, so walking the class's
        functions reaches the decorator's wrapper rather than the handler.

        The Remove button therefore raised AttributeError inside an async
        slot, which logs and swallows it: the button silently did nothing.

        So this reads the module's own source, which no decorator can hide,
        and follows the alias.
        """
        import re
        from pathlib import Path

        from client.models.equipment import Equipment
        import client.ui.equipment_panel as panel_module

        source = Path(panel_module.__file__).read_text(encoding="utf-8")
        available = set(Equipment.__dataclass_fields__) | {
            name for name in dir(Equipment) if not name.startswith("__")
        }

        asked = set(re.findall(r"self\.selected_equipment\.(\w+)", source))
        for alias in set(re.findall(r"^\s*(\w+)\s*=\s*self\.selected_equipment\s*$",
                                    source, re.MULTILINE)):
            asked |= set(re.findall(rf"\b{alias}\.(\w+)\b", source))

        missing = {a for a in asked if a not in available}
        assert not missing, (
            f"the panel reads {sorted(missing)} off the selected instrument, "
            f"which Equipment does not have; it has "
            f"{sorted(set(Equipment.__dataclass_fields__))}"
        )

    def test_a_remembered_instrument_can_be_connected(self):
        """The whole point of remembering one is being able to open it."""
        from client.models.equipment import Equipment

        remembered = Equipment.from_api_dict({
            "id": "ps_36509eb5",
            "manufacturer": "B&K Precision",
            "model": "9205B",
            "type": "power_supply",
            "resource_string": "USB0::11975::37376::800886011797210043::0::INSTR",
            "connected": False,
        })

        # These three are what the connect call passes on.
        assert remembered.resource_name.startswith("USB0::")
        assert remembered.equipment_type is not None
        assert remembered.model == "9205B"
