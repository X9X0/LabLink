"""What the connect dialog puts in front of an operator.

Some instruments NUL-pad their USB descriptors and the padding
survives into the VISA resource string. Qt draws each NUL as an empty
box, so a Siglent SPD3303X-E appeared as

    USB0::62700::5168::SPD3XJGCA01014[][][][]::0::INSTR

and read as four mangled digits in the middle of the serial.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

from client.ui.connect_dialog import _printable


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])

#: Exactly as the bench supply enumerates.
PADDED = "USB0::62700::5168::SPD3XJGCA01014\x00\x00\x00\x00::0::INSTR"


class TestTheResourceStringIsReadable:
    def test_the_padding_does_not_reach_the_operator(self):
        assert _printable(PADDED) == (
            "USB0::62700::5168::SPD3XJGCA01014::0::INSTR")

    def test_no_control_characters_survive(self):
        assert not any(ord(c) < 32 for c in _printable(PADDED))

    @pytest.mark.parametrize("resource", [
        "USB0::6833::3601::DL3B268M00049::0::INSTR",
        "ASRL/dev/ttyUSB0::INSTR",
        "TCPIP0::192.168.91.37::inst0::INSTR",
    ])
    def test_an_ordinary_resource_string_is_untouched(self, resource):
        assert _printable(resource) == resource

    def test_spaces_are_kept(self):
        assert _printable("SDS800X HD") == "SDS800X HD"

    @pytest.mark.parametrize("given", ["", None])
    def test_nothing_is_handled(self, given):
        assert _printable(given) == ""


class TestConnectingUsesTheRealString:
    """Display only. The string sent to the server has to be the one
    the device was enumerated under, padding and all, because that is
    what opens it."""

    def test_the_stored_device_is_not_rewritten(self, qapp):
        from client.ui.connect_dialog import ConnectDeviceDialog
        from PyQt6.QtCore import Qt

        class StubClient:
            def get_supported_models(self, supported_only=True):
                raise RuntimeError("offline")

        devices = [{
            "resource_name": PADDED,
            "manufacturer": "Siglent Technologies",
            "model": "SPD3303X-E",
            "device_type": "power_supply",
            "confidence_score": 0.95,
        }]
        dialog = ConnectDeviceDialog(devices, StubClient())

        item = dialog.resource_list.item(0)
        assert "\x00" not in item.text(), "the padding reached the display"
        stored = item.data(Qt.ItemDataRole.UserRole)
        assert stored["resource_name"] == PADDED, (
            "the resource string was rewritten; it would no longer open")


def _device(model="SPD3303X-E", equipment_id=None, resource=None):
    return {
        "resource_name": resource or PADDED,
        "manufacturer": "Siglent Technologies",
        "model": model,
        "device_type": "power_supply",
        "confidence_score": 0.95,
        "metadata": {"equipment_id": equipment_id} if equipment_id else {},
    }


class _StubClient:
    def get_supported_models(self, supported_only=True):
        raise RuntimeError("offline")


def _dialog(devices):
    from client.ui.connect_dialog import ConnectDeviceDialog
    return ConnectDeviceDialog(devices, _StubClient())


class TestAlreadyConnectedDevicesAreNotOffered:
    """An instrument the server already holds open cannot be connected
    again -- pressing Connect hands back the id it already has -- so
    listing it alongside the ones you can connect is just confusing.
    """

    def test_a_connected_device_is_left_out(self, qapp):
        dialog = _dialog([
            _device(model="SPD3303X-E"),
            _device(model="DL3021A", equipment_id="load_b8929b78",
                    resource="USB0::6833::3601::DL3B268M00049::0::INSTR"),
        ])
        assert dialog.resource_list.count() == 1
        assert "SPD3303X-E" in dialog.resource_list.item(0).text()

    def test_it_says_what_it_left_out(self, qapp):
        dialog = _dialog([
            _device(model="SPD3303X-E"),
            _device(model="DL3021A", equipment_id="load_b8929b78",
                    resource="USB0::6833::3601::DL3B268M00049::0::INSTR"),
        ])
        assert len(dialog.already_connected) == 1
        assert len(dialog.all_devices) == 2

    def test_everything_connected_is_said_plainly(self, qapp):
        """Not an empty list with no explanation."""
        dialog = _dialog([
            _device(model="DL3021A", equipment_id="load_b8929b78"),
        ])
        assert dialog.resource_list.count() == 0
        assert not dialog.connect_btn.isEnabled()

    def test_connect_stays_available_when_there_is_something_to_connect(
            self, qapp):
        dialog = _dialog([_device()])
        assert dialog.connect_btn.isEnabled()

    def test_a_device_with_no_metadata_is_offered(self, qapp):
        """Absence of the marker means the server is not holding it."""
        device = _device()
        device.pop("metadata")
        dialog = _dialog([device])
        assert dialog.resource_list.count() == 1
