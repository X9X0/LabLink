"""Every branch of the USB diagnostics, including the ones hardware cannot show.

The failure this exists for -- a serial that reads `???` after long uptime --
cannot be summoned on demand, so the only way to cover it is to make the bus
behave that way. Each test here fakes one specific failure and asserts the
diagnosis names *that* cause and not the others; a report that lists every
possible cause every time is not a diagnosis.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.utils.usb_diagnostics import (diagnose_usb_device,  # noqa: E402
                                          log_usb_diagnostics)

# The bench 9205B. Vendor and product are decimal: 2ec7:9200.
REAL = "USB0::11975::37376::800886011797210043::0::INSTR"
UNREADABLE = "USB0::11975::37376::???::0::INSTR"


class _USBError(Exception):
    """Stands in for usb.core.USBError, which carries an errno."""

    def __init__(self, message, errno=None):
        super().__init__(message)
        self.errno = errno


class _NoBackendError(Exception):
    pass


def _fake_usb(find_result=None, find_raises=None):
    """A usb.core module that behaves however the test needs."""
    core = types.ModuleType("usb.core")
    core.USBError = _USBError
    core.NoBackendError = _NoBackendError

    def find(**kwargs):
        if find_raises is not None:
            raise find_raises
        return find_result

    core.find = find
    usb = types.ModuleType("usb")
    usb.core = core
    return {"usb": usb, "usb.core": core}


def _device(serial=None, raises=None):
    device = MagicMock()
    if raises is not None:
        type(device).serial_number = property(
            lambda self: (_ for _ in ()).throw(raises)
        )
    else:
        device.serial_number = serial
    return device


def _results(resource=REAL, **fake):
    with patch.dict(sys.modules, _fake_usb(**fake)):
        return diagnose_usb_device(resource)


def _joined(diag):
    return " ".join(diag["issues"] + diag["recommendations"]).lower()


class TestTheBusIsActuallyInspected:
    def test_a_healthy_device_reports_no_issues(self):
        diag = _results(find_result=_device(serial="800886011797210043"))

        assert diag["device_present"] is True
        assert diag["serial_readable"] is True
        assert diag["descriptor_serial"] == "800886011797210043"
        assert diag["issues"] == []
        assert diag["recommendations"] == []

    def test_the_vendor_and_product_ids_are_decimal(self):
        """`USB0::11975::37376::...` is lsusb's 2ec7:9200, not 0x11975."""
        seen = {}

        core_modules = _fake_usb(find_result=_device(serial="x"))

        def find(**kwargs):
            seen.update(kwargs)
            return _device(serial="x")

        core_modules["usb.core"].find = find

        with patch.dict(sys.modules, core_modules):
            diagnose_usb_device(REAL)

        assert seen == {"idVendor": 11975, "idProduct": 37376}


class TestEachCauseIsNamedSeparately:
    def test_a_stale_resource_string_is_distinguished_from_a_sick_device(self):
        """Issue #166's actual signature: ??? in the string, fine on the bus."""
        diag = _results(resource=UNREADABLE,
                        find_result=_device(serial="800886011797210043"))

        assert diag["device_present"] is True
        assert diag["serial_readable"] is True
        assert "stale" in _joined(diag)
        assert "discovery" in _joined(diag)
        # The instrument is fine, so nobody should be sent to the bench.
        assert "cable" not in _joined(diag)

    def test_an_absent_device_says_so_and_nothing_else(self):
        diag = _results(resource=UNREADABLE, find_result=None)

        assert diag["device_present"] is False
        assert "not on the usb bus" in _joined(diag)
        assert "stale" not in _joined(diag)
        assert "permission" not in _joined(diag)

    def test_permission_denied_is_not_blamed_on_the_instrument(self):
        diag = _results(resource=UNREADABLE,
                        find_result=_device(raises=_USBError("Access denied", errno=13)))

        assert diag["device_present"] is True
        assert diag["serial_readable"] is False
        assert "permission" in _joined(diag)
        assert "udev" in _joined(diag)
        assert "stale" not in _joined(diag)

    def test_a_device_with_no_serial_programmed(self):
        diag = _results(resource=UNREADABLE, find_result=_device(serial=""))

        assert diag["device_present"] is True
        assert "no serial number of its own" in _joined(diag)
        assert "permission" not in _joined(diag)

    def test_a_failed_descriptor_read_suggests_the_physical_layer(self):
        diag = _results(resource=UNREADABLE,
                        find_result=_device(raises=_USBError("pipe error", errno=32)))

        assert "could not be read" in _joined(diag)
        assert "replug" in _joined(diag)
        assert "permission" not in _joined(diag)

    def test_a_swapped_instrument_is_reported_as_a_mismatch(self):
        diag = _results(find_result=_device(serial="999999999999"))

        assert "swapped" in _joined(diag)
        assert diag["descriptor_serial"] == "999999999999"


class TestWhatItCannotSeeItDoesNotClaim:
    def test_no_backend_reports_that_nothing_was_observed(self):
        diag = _results(resource=UNREADABLE,
                        find_raises=_NoBackendError("no backend available"))

        assert diag["device_present"] is None
        assert "no libusb backend" in _joined(diag)
        # It must not attribute a cause it had no way to observe.
        assert "permission" not in _joined(diag).split("libusb")[0]
        assert "stale" not in _joined(diag)

    def test_pyusb_missing_is_reported_rather_than_guessed(self):
        with patch.dict(sys.modules, {"usb": None, "usb.core": None}):
            diag = diagnose_usb_device(UNREADABLE)

        assert diag["device_present"] is None
        assert diag["issues"]

    def test_a_non_usb_resource_is_declined_immediately(self):
        """The bench 1685B is ASRL; there is no descriptor to read."""
        diag = diagnose_usb_device("ASRL/dev/ttyUSB0::INSTR")

        assert diag["usb_info"] is None
        assert "not a usb device" in _joined(diag)
        assert diag["recommendations"] == []

    def test_a_malformed_resource_string_is_declined(self):
        diag = diagnose_usb_device("USB0::garbage")

        assert "invalid usb resource string" in _joined(diag)


class TestTheClientContractIsPreserved:
    """diagnostics_panel.py reads these keys; renaming them breaks the panel."""

    @pytest.mark.parametrize("key", [
        "resource_string", "has_serial", "serial_readable", "usb_info",
        "issues", "recommendations",
    ])
    def test_key_is_present(self, key):
        diag = _results(find_result=_device(serial="800886011797210043"))

        assert key in diag

    def test_usb_info_carries_what_the_panel_prints(self):
        diag = _results(find_result=_device(serial="800886011797210043"))

        assert set(diag["usb_info"]) >= {"vendor_id", "product_id", "serial_number"}


class TestLogging:
    def test_logging_a_diagnosis_does_not_raise(self, caplog):
        with patch.dict(sys.modules, _fake_usb(find_result=None)):
            log_usb_diagnostics(UNREADABLE)

        assert "USB Device Diagnostics" in caplog.text

    def test_logging_a_non_usb_resource_does_not_raise(self, caplog):
        """usb_info is None on this path; the old version indexed into it."""
        log_usb_diagnostics("ASRL/dev/ttyUSB0::INSTR")

        assert "N/A" in caplog.text
