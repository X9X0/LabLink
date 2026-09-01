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
