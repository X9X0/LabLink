"""Tests for the Rigol model catalogue exposed through the models API."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.equipment import rigol_registry  # noqa: E402


@pytest.mark.unit
def test_catalog_covers_every_registered_driver():
    from server.equipment import manager

    keys = {e["driver"] for e in rigol_registry.catalog()}
    for cls in manager.KEYWORD_DRIVER_CLASSES:
        assert cls.__name__ in keys, cls.__name__
    for legacy in ("RigolDS1104", "RigolMSO2072A", "RigolDS1102D", "RigolDL3021A", "RigolDM3058", "RigolDM3068"):
        assert legacy in keys


@pytest.mark.unit
def test_every_entry_has_skus_and_a_type():
    valid_types = {
        "oscilloscope", "power_supply", "electronic_load", "multimeter", "function_generator",
        "spectrum_analyzer", "rf_signal_generator", "vector_network_analyzer", "data_acquisition",
    }
    for entry in rigol_registry.catalog():
        assert entry["skus"], entry["key"]
        assert entry["equipment_type"] in valid_types, entry["key"]
        assert entry["manufacturer"] == "Rigol"
        assert entry["supported"] is True


@pytest.mark.unit
def test_skus_drop_family_prefixes_and_spelling_variants():
    by_key = {e["key"]: e for e in rigol_registry.catalog()}
    assert "DSG3" not in by_key["DSG3000"]["skus"]
    assert "DG822 Pro" in by_key["DG800Pro"]["skus"]
    assert "DG822PRO" not in by_key["DG800Pro"]["skus"]
    assert "DG822-PRO" not in by_key["DG800Pro"]["skus"]
    assert by_key["M300"]["skus"] == ["M300"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "model,key",
    [
        ("Rigol Technologies,DSA815-TG", "DSA800"),
        ("DG822 Pro", "DG800Pro"),
        ("DS1054Z", "DS1104"),
        ("RSA3030N", "RSAN"),
        ("DP832A", "DP800"),
        ("MHO5104", "DHO5000"),
        ("34461A", None),
    ],
)
def test_resolve_model(model, key):
    entry = rigol_registry.resolve_model(model)
    assert (entry["key"] if entry else None) == key
