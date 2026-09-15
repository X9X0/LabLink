"""Tests for Rigol model-prefix classification and driver aliasing."""

import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("..")

from discovery.models import DeviceType  # noqa: E402
from discovery.vendor_models import infer_rigol_device_type  # noqa: E402
from discovery.visa_scanner import VISAScanner  # noqa: E402
from equipment.manager import EquipmentManager  # noqa: E402
from equipment.rigol_scope import RigolDS1104, RigolMSO2072A  # noqa: E402
from shared.models.equipment import EquipmentType  # noqa: E402


@pytest.mark.unit
@pytest.mark.parametrize(
    "model,expected",
    [
        ("DS1054Z", DeviceType.OSCILLOSCOPE),
        ("Rigol DS1202Z-E", DeviceType.OSCILLOSCOPE),
        ("MSO5074", DeviceType.OSCILLOSCOPE),
        ("DHO804", DeviceType.OSCILLOSCOPE),
        ("MHO5074", DeviceType.OSCILLOSCOPE),
        ("DSA815", DeviceType.SPECTRUM_ANALYZER),
        ("RSA5065-TG", DeviceType.SPECTRUM_ANALYZER),
        ("DNA6000", DeviceType.VECTOR_NETWORK_ANALYZER),
        ("DSG836", DeviceType.RF_SIGNAL_GENERATOR),
        ("DG1062Z", DeviceType.FUNCTION_GENERATOR),
        ("DP832A", DeviceType.POWER_SUPPLY),
        ("DL3031A", DeviceType.ELECTRONIC_LOAD),
        ("DM3058E", DeviceType.MULTIMETER),
        ("DM858", DeviceType.MULTIMETER),
        ("RSA5065N", DeviceType.VECTOR_NETWORK_ANALYZER),
        ("M300", DeviceType.DATA_ACQUISITION),
        ("34461A", None),
        ("", None),
        (None, None),
    ],
)
def test_infer_rigol_device_type(model, expected):
    assert infer_rigol_device_type(model) == expected


@pytest.mark.unit
def test_other_vendor_is_not_classified_by_rigol_table():
    assert infer_rigol_device_type("DS1054Z", manufacturer="Keysight") is None
    assert infer_rigol_device_type("DS1054Z", manufacturer="Rigol Technologies") == DeviceType.OSCILLOSCOPE


@pytest.mark.unit
def test_visa_scanner_uses_vendor_table_before_keywords():
    scanner = VISAScanner.__new__(VISAScanner)
    info = {"manufacturer": "Rigol Technologies", "model": "DSA815"}
    # "dsa815" contains "ds" which the keyword rules would call an oscilloscope
    assert scanner._infer_device_type(info) == DeviceType.SPECTRUM_ANALYZER
    info = {"manufacturer": "Rigol Technologies", "model": "DHO924S"}
    assert scanner._infer_device_type(info) == DeviceType.OSCILLOSCOPE
    # keyword fallback still works for other vendors
    info = {"manufacturer": "Keysight", "model": "34461A Multimeter"}
    assert scanner._infer_device_type(info) == DeviceType.MULTIMETER


@pytest.mark.unit
def test_manager_aliases_scope_families():
    manager = EquipmentManager()
    manager.resource_manager = MagicMock()
    make = lambda m: manager._create_equipment_instance("USB0::x::INSTR", EquipmentType.OSCILLOSCOPE, m)
    for model in ("DS1054Z", "DS1074Z", "DS1104Z", "Rigol DS1000Z"):
        assert isinstance(make(model), RigolDS1104), model
    for model in ("MSO2072A", "MSO2302A", "DS2202A", "DS2000A"):
        assert isinstance(make(model), RigolMSO2072A), model
    # 2-channel DS1202Z-E must not get the 4-channel driver
    from equipment.rigol_modern_scope import RigolDS1000ZE

    assert isinstance(make("DS1202Z-E"), RigolDS1000ZE)
