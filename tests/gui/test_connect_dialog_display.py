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
