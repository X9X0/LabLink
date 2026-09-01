"""Tests for B&K auto-detection: *IDN? inference and the serial probe."""

from unittest.mock import MagicMock

import pytest

from discovery.bk_serial_probe import (_device_from_probe, _probe_port_blocking,
                                       find_serial_ports)
from discovery.models import (ConnectionStatus, DeviceType, DiscoveredDevice,
                              DiscoveryConfig, DiscoveryMethod)
from discovery.visa_scanner import VISAScanner


@pytest.fixture
def scanner():
    return VISAScanner(DiscoveryConfig())


def _device(manufacturer=None, model=None, **kw):
    return DiscoveredDevice(
        device_id="d", resource_name="USB0::INSTR",
        discovery_method=DiscoveryMethod.VISA,
        manufacturer=manufacturer, model=model, **kw,
    )


class TestDeviceTypeInference:
    """The registry answers the type question before heuristics guess at it."""

    @pytest.mark.parametrize("manufacturer,model,expected", [
        ("B&KPrecision", "9241", DeviceType.POWER_SUPPLY),
        ("B&K Precision", "9130B", DeviceType.POWER_SUPPLY),
        ("BK Precision", "MDL252", DeviceType.ELECTRONIC_LOAD),
        ("BK", "2682", DeviceType.MULTIMETER),
        ("BK Precision", "2510B", DeviceType.OSCILLOSCOPE),
        ("B&K Precision", "4063B", DeviceType.FUNCTION_GENERATOR),
        # No LabLink type for these, but they are still B&K.
        ("B&K Precision", "DAS701", DeviceType.UNKNOWN),
        ("B&KPRECISION", "BA8100", DeviceType.UNKNOWN),
    ])
    def test_bk_models_resolve_through_the_registry(
        self, scanner, manufacturer, model, expected
    ):
        assert scanner._infer_device_type(
            {"manufacturer": manufacturer, "model": model}
        ) == expected

    def test_a_bk_load_is_not_mistaken_for_an_oscilloscope(self, scanner):
        """"DML" contains "dm"; the keyword heuristics used to reach first."""
        assert scanner._infer_device_type(
            {"manufacturer": "B&K Precision", "model": "DML1102"}
        ) == DeviceType.ELECTRONIC_LOAD

    def test_other_manufacturers_still_use_the_heuristics(self, scanner):
        assert scanner._infer_device_type(
            {"manufacturer": "Rigol Technologies", "model": "MSO2072A"}
        ) == DeviceType.OSCILLOSCOPE


class TestRegistryEnrichment:
    """A discovered B&K device carries its family facts into the UI."""

    def test_normalizes_the_manufacturer_spelling(self, scanner):
        device = _device("B&KPrecision", "9241")
        scanner._apply_bk_registry(device)
        assert device.manufacturer == "B&K Precision"
        assert device.metadata["reported_manufacturer"] == "B&KPrecision"

    def test_records_the_family_and_its_interfaces(self, scanner):
        device = _device("BK Precision", "9241")
        scanner._apply_bk_registry(device)
        assert device.metadata["bk_family"] == "9240"
        assert device.metadata["bk_family_name"] == "9240 Series"
        assert device.metadata["usb_mode"] == "cdc"
        assert device.metadata["driver_supported"] is True
        assert "LAN" in device.capabilities

    def test_flags_a_family_with_no_driver(self, scanner):
        device = _device("B&K Precision", "2190D")
        scanner._apply_bk_registry(device)
        assert device.metadata["bk_family"] == "2190D"
        assert device.metadata["driver_supported"] is False

    def test_raises_confidence_on_a_registry_hit(self, scanner):
        device = _device("B&K Precision", "9241", confidence_score=0.9)
        scanner._apply_bk_registry(device)
        assert device.confidence_score == 0.95

    def test_leaves_other_manufacturers_untouched(self, scanner):
        device = _device("Rigol Technologies", "DS1054Z", confidence_score=0.9)
        scanner._apply_bk_registry(device)
        assert device.manufacturer == "Rigol Technologies"
        assert device.confidence_score == 0.9
        assert "bk_family" not in device.metadata

    def test_an_undocumented_bk_model_is_still_normalized(self, scanner):
        """A model with no published manual keeps its identity, minus a family."""
        device = _device("B&K PRECISION", "9999Z")
        scanner._apply_bk_registry(device)
        assert device.manufacturer == "B&K Precision"
        assert "bk_family" not in device.metadata


class TestSerialProbe:
    """USB-CDC and legacy supplies are invisible to a normal VISA scan."""

    def test_scpi_reply_identifies_the_family(self):
        device = _device_from_probe({
            "port": "/dev/ttyUSB0", "baudrate": 9600, "protocol": "scpi",
            "idn": "B&KPrecision,9141,614D21108,1.06-1.04",
        })
        assert device.manufacturer == "B&K Precision"
        assert device.model == "9141"
        assert device.device_type == DeviceType.POWER_SUPPLY
        assert device.metadata["bk_family"] == "9140"
        assert device.metadata["baudrate"] == 9600
        assert device.resource_name == "ASRL/dev/ttyUSB0::INSTR"

    def test_another_vendors_instrument_on_the_port_is_ignored(self):
        assert _device_from_probe({
            "port": "/dev/ttyUSB0", "baudrate": 9600, "protocol": "scpi",
            "idn": "Rigol Technologies,DP832,X,1.0",
        }) is None

    def test_gmax_reply_identifies_the_legacy_family_and_its_limits(self):
        """These supplies have no *IDN?; GMAX is the only thing they answer."""
        device = _device_from_probe({
            "port": "/dev/ttyUSB1", "baudrate": 9600, "protocol": "fixed",
            "gmax": "180050",
        })
        assert device.device_type == DeviceType.POWER_SUPPLY
        assert device.metadata["max_voltage"] == 18.0
        assert device.metadata["max_current"] == 5.0
        # GMAX carries no model number, so confidence stays honest.
        assert device.confidence_score < 0.8
        assert "pick the exact model" in device.metadata["note"]

    def test_usb_only_filtering_skips_the_hosts_built_in_uarts(self):
        """A Linux host lists 32 empty /dev/ttyS* devices; sweeping them is waste."""
        usb_ports = find_serial_ports(usb_only=True)
        all_ports = find_serial_ports(usb_only=False)
        assert len(usb_ports) <= len(all_ports)
        assert not any(p.startswith("/dev/ttyS") and p[9:].isdigit()
                       for p in usb_ports)

    def test_an_unopenable_port_gives_up_immediately(self):
        """Trying six baud rates on a port that will not open is pointless."""
        assert _probe_port_blocking("/dev/does-not-exist", (9600,), 0.1) is None


class FakeFixedWidthInstrument:
    """A stand-in for a 1902B on a CP2102, framed the way the real one is.

    Faithful in the one respect that matters: it parses on CR and treats LF as
    an ordinary character, so anything written without a terminating CR is
    held as an unterminated command and the next write is read as a
    continuation of it.
    """

    def __init__(self, gmax=b"605160"):
        self.gmax = gmax
        self._command = b""       # what the instrument has accumulated
        self._out = b""           # what it has queued for us to read
        self.closed = False

    # -- the pyserial surface the probe uses --------------------------------
    def write(self, data: bytes) -> int:
        for byte in data:
            char = bytes([byte])
            if char == b"\r":
                self._execute(self._command)
                self._command = b""
            else:
                self._command += char
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        # Clears our end of the link only — never the instrument's command
        # buffer, which is exactly the trap this test exists for.
        self._out = b""

    def read_until(self, expected: bytes) -> bytes:
        index = self._out.find(expected)
        if index == -1:
            out, self._out = self._out, b""   # a real port would time out here
            return out
        end = index + len(expected)
        out, self._out = self._out[:end], self._out[end:]
        return out

    def close(self):
        self.closed = True

    def _execute(self, command: bytes) -> None:
        if command == b"GMAX":
            self._out += self.gmax + b"\r" + b"OK\r"
        elif command == b"":
            pass          # an empty command is discarded silently
        # Anything else — including "*IDN?\nGMAX" — is rejected in silence.


@pytest.fixture
def fake_instrument(monkeypatch):
    """Patch pyserial so the probe opens the fake instrument instead."""
    import serial

    instrument = FakeFixedWidthInstrument()
    monkeypatch.setattr(serial, "Serial", lambda **kwargs: instrument)
    return instrument


class TestLegacyProbeFraming:
    """A fixed-width supply must survive the SCPI attempt that precedes it."""

    def test_gmax_is_heard_after_a_failed_idn_probe(self, fake_instrument):
        """The regression: *IDN? leaves a fragment that swallows GMAX.

        *IDN?\n has no CR, so the instrument holds it mid-command. Unless the
        probe closes that fragment out, GMAX arrives appended to it, the
        instrument rejects the pair, and the port reads as dead at every baud
        rate — which is exactly what a real 1902B did.
        """
        result = _probe_port_blocking("/dev/ttyUSB0", (9600,), 0.1)

        assert result is not None, "the probe went deaf after its SCPI attempt"
        assert result["protocol"] == "fixed"
        assert result["gmax"] == "605160"

    def test_the_fragment_is_actually_cleared_not_just_tolerated(
        self, fake_instrument
    ):
        """Assert the mechanism, so a future rewrite cannot regress it quietly."""
        _probe_port_blocking("/dev/ttyUSB0", (9600,), 0.1)
        assert fake_instrument._command == b"", (
            "the instrument was left holding an unterminated command"
        )

    def test_gmax_becomes_a_device_with_the_units_real_limits(
        self, fake_instrument
    ):
        result = _probe_port_blocking("/dev/ttyUSB0", (9600,), 0.1)
        device = _device_from_probe(result)
        # 605160 is a live 1902B: 60.5 V and 16.0 A of headroom over its
        # 60 V / 15 A rating.
        assert device.metadata["max_voltage"] == 60.5
        assert device.metadata["max_current"] == 16.0
        assert device.device_type == DeviceType.POWER_SUPPLY


class TestProbeResultMerging:
    """What the client ends up showing, not just what the probe returned.

    The probe answering correctly is not enough: its result still has to
    survive being folded in beside whatever the other scanners produced.
    """

    @staticmethod
    def _visa_asrl_listing():
        """What VISA produces for a serial port it never opened.

        pyvisa enumerates ASRL resources from the device node, without
        exchanging a byte, so this carries no identification at all.
        """
        device = DiscoveredDevice(
            device_id="asrl_dev_ttyusb0_instr",
            resource_name="ASRL/dev/ttyUSB0::INSTR",
            discovery_method=DiscoveryMethod.VISA,
            manufacturer="Unknown",
            model="Serial Device (ASRL)",
            device_type=DeviceType.UNKNOWN,
            confidence_score=0.4,
        )
        device.metadata["note"] = "Does not respond to *IDN?"
        return device

    @staticmethod
    def _probed_1902b():
        """What the probe returns for the bench 1902B: a real GMAX exchange."""
        device = DiscoveredDevice(
            device_id="bkserial__dev_ttyusb0",
            resource_name="ASRL/dev/ttyUSB0::INSTR",
            discovery_method=DiscoveryMethod.USB,
            manufacturer="B&K Precision",
            model="Legacy fixed-width supply",
            device_type=DeviceType.POWER_SUPPLY,
            confidence_score=0.6,
        )
        device.capabilities = ["RS-232", "USB-CDC"]
        device.metadata.update({
            "serial_port": "/dev/ttyUSB0", "protocol": "fixed",
            "max_voltage": 60.5, "max_current": 16.0, "gmax": "605160",
        })
        return device

    def _merge(self, discovered, probed):
        from discovery.manager import DiscoveryManager
        count = DiscoveryManager._merge_serial_probe_results(discovered, probed)
        return count, discovered

    def test_an_identification_beats_a_bare_port_listing(self):
        """The regression: a real GMAX exchange lost to a file existing in /dev.

        VISA listing the port made it "known", so the probe's identification
        was dropped and the client showed "Unknown Serial Device" for a supply
        that had just told us it was a 60.5 V / 16 A B&K.
        """
        count, devices = self._merge(
            [self._visa_asrl_listing()], [self._probed_1902b()]
        )

        assert len(devices) == 1, "one instrument must not appear twice"
        assert count == 1, "the probe's contribution went uncounted"

        device = devices[0]
        assert device.manufacturer == "B&K Precision"
        assert device.device_type == DeviceType.POWER_SUPPLY
        assert device.confidence_score == 0.6
        assert device.metadata["max_voltage"] == 60.5

    def test_the_merged_entry_keeps_its_original_identity(self):
        """History and aliases are keyed on device_id; it must not move."""
        _, devices = self._merge(
            [self._visa_asrl_listing()], [self._probed_1902b()]
        )
        assert devices[0].device_id == "asrl_dev_ttyusb0_instr"
        assert devices[0].resource_name == "ASRL/dev/ttyUSB0::INSTR"
        # VISA's own metadata survives alongside the probe's.
        assert "note" in devices[0].metadata
        assert "gmax" in devices[0].metadata

    def test_a_real_visa_identification_still_wins(self):
        """The original rule holds where its premise does.

        On USB-TMC and TCPIP, VISA genuinely opened a session and read *IDN?.
        A probe must not overwrite that.
        """
        identified = DiscoveredDevice(
            device_id="usb_9130b", resource_name="ASRL/dev/ttyUSB0::INSTR",
            discovery_method=DiscoveryMethod.VISA,
            manufacturer="B&K Precision", model="9130B",
            device_type=DeviceType.POWER_SUPPLY, confidence_score=0.9,
        )
        count, devices = self._merge([identified], [self._probed_1902b()])

        assert len(devices) == 1
        assert count == 0, "the probe should have deferred"
        assert devices[0].model == "9130B"
        assert devices[0].confidence_score == 0.9

    def test_a_port_visa_cannot_see_is_added_outright(self):
        """The USB-CDC case: VISA enumerates none of them."""
        count, devices = self._merge([], [self._probed_1902b()])
        assert count == 1
        assert len(devices) == 1
        assert devices[0].device_type == DeviceType.POWER_SUPPLY

    def test_matching_falls_back_to_the_serial_port(self):
        """The two scanners need not spell the resource the same way."""
        listing = self._visa_asrl_listing()
        listing.resource_name = "ASRL3::INSTR"
        listing.metadata["serial_port"] = "/dev/ttyUSB0"

        count, devices = self._merge([listing], [self._probed_1902b()])
        assert len(devices) == 1, "the same instrument was listed twice"
        assert count == 1
        assert devices[0].device_type == DeviceType.POWER_SUPPLY


class TestSerialProbeIntegration:
    """The probe runs as part of a scan and merges with the other scanners."""

    @pytest.mark.asyncio
    async def test_scan_runs_the_probe_and_survives_no_ports(self):
        from discovery.manager import DiscoveryManager

        config = DiscoveryConfig(
            enable_visa_scan=False, enable_mdns=False,
            cache_discovered_devices=False,
        )
        result = await DiscoveryManager(config).scan()
        assert result.success
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_probe_can_be_turned_off(self):
        from discovery.manager import DiscoveryManager

        config = DiscoveryConfig(
            enable_visa_scan=False, enable_mdns=False,
            enable_serial_probe=False, cache_discovered_devices=False,
        )
        result = await DiscoveryManager(config).scan()
        assert result.success
        assert result.usb_count == 0
