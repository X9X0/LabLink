"""Discovery has to place a Siglent, not just name it.

The connect dialog offered "Siglent Technologies SPD3303X-E (unknown)"
for a supply that had answered *IDN? perfectly. Manufacturer and model
were right; the equipment type was not, and without a type the device
cannot be connected.

The cause was that the keyword heuristics in _infer_device_type are
the last resort, and not one of their tokens appears in "SPD3303X-E" --
no "ps", no "dp", no "power supply". Nothing consulted the Siglent
registry, so a correctly identified instrument fell through to
UNKNOWN.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.discovery.models import (DeviceType, DiscoveredDevice,
                                     DiscoveryMethod)
from server.discovery.visa_scanner import VISAScanner


def scanner():
    return VISAScanner.__new__(VISAScanner)


def device(manufacturer="Siglent Technologies", model="SPD3303X-E"):
    resource = "USB0::62700::5168::SPD3XJGCA01014::0::INSTR"
    return DiscoveredDevice(
        device_id=resource,
        discovery_method=DiscoveryMethod.VISA,
        resource_name=resource,
        manufacturer=manufacturer,
        model=model,
    )


class TestTheTypeIsInferred:
    @pytest.mark.parametrize("model,expected", [
        ("SPD3303X-E", DeviceType.POWER_SUPPLY),
        ("SPD3303X", DeviceType.POWER_SUPPLY),
        ("SPD1168X", DeviceType.POWER_SUPPLY),
        ("SDL1020X", DeviceType.ELECTRONIC_LOAD),
        ("SDM3065X", DeviceType.MULTIMETER),
        ("SDS1104X-E", DeviceType.OSCILLOSCOPE),
        ("SDG2042X", DeviceType.FUNCTION_GENERATOR),
        ("SSA3021X", DeviceType.SPECTRUM_ANALYZER),
        ("SNA5000A", DeviceType.VECTOR_NETWORK_ANALYZER),
    ])
    def test_each_family_lands_on_its_type(self, model, expected):
        got = scanner()._infer_device_type(
            {"manufacturer": "Siglent Technologies", "model": model})
        assert got == expected

    def test_the_bench_supply_is_a_power_supply(self):
        """The one that shipped as "unknown"."""
        got = scanner()._infer_device_type(
            {"manufacturer": "Siglent Technologies", "model": "SPD3303X-E"})
        assert got == DeviceType.POWER_SUPPLY
        assert got != DeviceType.UNKNOWN

    def test_an_uncatalogued_sku_is_still_placed(self):
        """By Siglent's prefix scheme, so a model nobody has entered
        is still connectable as the right kind of instrument."""
        got = scanner()._infer_device_type(
            {"manufacturer": "Siglent Technologies", "model": "SPD9999Q"})
        assert got == DeviceType.POWER_SUPPLY

    def test_an_atten_badged_siglent_is_placed(self):
        """USB vendor id 0xF4EC is still registered to Atten, so that
        is what some VISA layers report."""
        got = scanner()._infer_device_type(
            {"manufacturer": "Atten Electronics", "model": "SPD3303X"})
        assert got == DeviceType.POWER_SUPPLY

    @pytest.mark.parametrize("manufacturer,model,expected", [
        ("RIGOL TECHNOLOGIES", "DL3021A", DeviceType.ELECTRONIC_LOAD),
        ("B&K Precision", "9205B", DeviceType.POWER_SUPPLY),
    ])
    def test_other_vendors_are_unaffected(self, manufacturer, model, expected):
        got = scanner()._infer_device_type(
            {"manufacturer": manufacturer, "model": model})
        assert got == expected


class TestTheDeviceIsEnriched:
    def test_the_manufacturer_is_normalised(self):
        found = device(manufacturer="Atten Electronics")
        scanner()._apply_siglent_registry(found)
        assert found.manufacturer == "Siglent Technologies"
        assert found.metadata["reported_manufacturer"] == "Atten Electronics"

    def test_the_family_and_protocol_are_recorded(self):
        found = device()
        scanner()._apply_siglent_registry(found)
        assert found.metadata["siglent_family"] == "SPD3000X"
        assert found.metadata["protocol"] == "scpi"
        assert found.metadata["driver_supported"] is True

    def test_confident_identification_is_marked_as_such(self):
        """The connect dialog highlights devices with confirmed
        identification, and this one was not highlighted."""
        found = device()
        scanner()._apply_siglent_registry(found)
        assert found.confidence_score >= 0.95

    def test_a_family_with_no_driver_says_so_and_why(self):
        found = device(model="SDS1104X-E")
        scanner()._apply_siglent_registry(found)
        assert found.metadata["driver_supported"] is False
        assert "short-form" in found.metadata["driver_note"]

    def test_a_non_siglent_device_is_left_alone(self):
        found = device(manufacturer="RIGOL TECHNOLOGIES", model="DL3021A")
        scanner()._apply_siglent_registry(found)
        assert found.manufacturer == "RIGOL TECHNOLOGIES"
        assert "siglent_family" not in found.metadata
