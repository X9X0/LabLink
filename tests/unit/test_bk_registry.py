"""Tests for the B&K Precision model registry and its resolvers.

The cases here are drawn from the ``*IDN?`` examples printed in B&K's own
programming manuals, which is where the awkward forms come from.
"""

import pytest

from equipment.bk_registry import (CATEGORY_TO_EQUIPMENT_TYPE,
                                   DRIVEN_CATEGORIES, MODELS,
                                   PROTOCOL_FIXED, PROTOCOL_PROPRIETARY,
                                   PROTOCOL_SCPI, PROTOCOL_SIGLENT, USB_CDC,
                                   USB_TMC, candidate_bauds, catalog,
                                   default_baud, equipment_type_for,
                                   is_bk_manufacturer, is_drivable,
                                   resolve_idn, resolve_model, usb_mode)


class TestManufacturerRecognition:
    """B&K spells its own name six ways across the published manuals."""

    @pytest.mark.parametrize("spelling", [
        "B&K Precision",
        "B&KPrecision",
        "B&KPRECISION",
        "B&K PRECISION",
        "BK Precision",
        "BK",
        "b&k precision",
        "  B&K Precision  ",
    ])
    def test_recognizes_every_published_spelling(self, spelling):
        assert is_bk_manufacturer(spelling)

    @pytest.mark.parametrize("other", [
        "Rigol Technologies", "Keysight", "Siglent Technologies",
        "Tektronix", "", None, "BKAV", "Precision",
    ])
    def test_rejects_other_manufacturers(self, other):
        assert not is_bk_manufacturer(other)


class TestModelResolution:
    """A B&K instrument reports its SKU; the manuals are written per family."""

    @pytest.mark.parametrize("reported,family", [
        # Straight from *IDN? examples in the manuals.
        ("9241", "9240"),
        ("9140", "9140"),
        ("2682", "2680"),
        ("BK1823B", "1820B"),
        ("2569B-MSO", "2560B"),
        ("549XC", "5490C"),
        ("169XB", "1696B"),
        ("MR40003", "MR"),
        ("MPS1102", "MPS"),
        ("DML1102", "DML"),
        ("BCS6402", "BCS"),
        ("BA6011", "BA6010"),
        ("HMRxxxx", "HMR"),
        ("4063B", "4060B"),
        ("9833B", "9830B"),
        ("2194", "2194"),
        ("DAQ3120", "DAQ3120"),
        # Forms a user might type or a catalogue might carry.
        ("9140 Series", "9140"),
        ("B&K Precision 9130B", "9130B"),
        ("HVL-1000-25", "HVL"),
        ("894/895", "894"),
        ("MDL4U001", "MDL4U"),
        ("MDL505", "MDL"),
        ("8612", "8600"),
        ("1687B", "1685B"),
        ("1902B", "1900B"),
        ("9104", "9103"),
    ])
    def test_resolves_sku_to_family(self, reported, family):
        resolved = resolve_model(reported)
        assert resolved is not None, f"{reported} did not resolve"
        assert resolved.key == family

    @pytest.mark.parametrize("foreign", [
        "DS1054Z", "MSO2072A", "DL3021A", "DS1102D", "DP832", "34450A",
        "SDS1104X-E", "HMC8043", "CP210x UART Bridge", "FT232 USB-UART",
        "Unknown", "Serial Device (ASRL)", "", None,
    ])
    def test_does_not_claim_other_vendors_models(self, foreign):
        """A false positive is worse than a miss: it picks the wrong driver."""
        assert resolve_model(foreign) is None

    def test_longer_prefix_wins(self):
        """MDL4U and MDL4UB both start with MDL; the most specific must win."""
        assert resolve_model("MDL4UB001").key == "MDL4UB"
        assert resolve_model("MDL4U002").key == "MDL4U"
        assert resolve_model("MDL200").key == "MDL"

    def test_suffix_must_match_for_a_decade_hit(self):
        """2194 is its own family, not a 2190D; 9816B is not a 9810."""
        assert resolve_model("2194").key == "2194"
        assert resolve_model("9816B").key == "9816B"
        assert resolve_model("9814").key == "9814"


class TestIdnParsing:
    """End-to-end: an *IDN? reply in, a family out."""

    def test_parses_and_resolves(self):
        fields, model = resolve_idn(
            "B&KPrecision,9241,614D21108,0.30_0825A-0.18_0824A"
        )
        assert fields["manufacturer"] == "B&KPrecision"
        assert fields["serial_number"] == "614D21108"
        assert fields["firmware_version"] == "0.30_0825A-0.18_0824A"
        assert model is not None and model.key == "9240"

    def test_bare_bk_manufacturer(self):
        fields, model = resolve_idn("BK,2682,538A19101,1.2.9.2.a")
        assert model is not None and model.key == "2680"

    def test_other_manufacturer_resolves_to_nothing(self):
        fields, model = resolve_idn("Rigol Technologies,DS1054Z,X,1.0")
        assert fields["model"] == "DS1054Z"
        assert model is None

    def test_empty_idn_is_not_an_error(self):
        fields, model = resolve_idn("")
        assert model is None
        assert fields["manufacturer"] is None


class TestInterfaceFacts:
    """The USB mode is the fact that decides whether a device is findable."""

    def test_usb_cdc_models_are_serial_ports(self):
        """VISA never enumerates these; they need a baud rate instead."""
        for model in ("9140", "9130B", "2840", "1685B", "9103", "2194"):
            assert usb_mode(model) == USB_CDC, model

    def test_usbtmc_models_go_through_visa(self):
        for model in ("8600", "MDL", "9115", "894", "9830B"):
            assert usb_mode(model) == USB_TMC, model

    def test_1820b_runs_at_115200_not_9600(self):
        """The one model in the legacy line that is not a 9600 device."""
        assert default_baud("1823B") == 115200
        assert default_baud("1902B") == 9600

    def test_candidate_bauds_lead_with_the_documented_rate(self):
        assert candidate_bauds("1823B")[0] == 115200
        assert candidate_bauds("9130B")[0] == 9600
        # An unknown model still gets a sensible sweep.
        assert 9600 in candidate_bauds("no-such-model")

    def test_interfaces_are_listed_in_bring_up_order(self):
        assert resolve_model("8600").interfaces == [
            "RS-232", "USBTMC", "GPIB", "LAN"
        ]

    def test_fixed_width_models_have_no_idn(self):
        """Discovery has to fall back to a GMAX probe for these."""
        assert not resolve_model("1685B").supports_idn
        assert not resolve_model("9104").supports_idn
        assert resolve_model("9130B").supports_idn


class TestDrivability:
    """Identified and drivable are different questions."""

    def test_scpi_supplies_loads_and_meters_are_drivable(self):
        for model in ("9140", "9130B", "MDL", "8600", "2840", "5490C", "MR"):
            assert is_drivable(resolve_model(model)), model

    def test_siglent_and_proprietary_models_are_not_drivable(self):
        """Assuming SCPI against these fails silently, so refuse up front."""
        assert resolve_model("2190D").protocol == PROTOCOL_SIGLENT
        assert not is_drivable(resolve_model("2190D"))
        assert resolve_model("HPS").protocol == PROTOCOL_PROPRIETARY
        assert not is_drivable(resolve_model("HPS"))

    def test_categories_without_a_lablink_type_are_not_drivable(self):
        for model in ("DAS701", "BA8100", "RFM3000", "5335B", "894"):
            assert not is_drivable(resolve_model(model)), model

    def test_fixed_width_families_with_a_driver(self):
        for model in ("1685B", "1902B", "9103", "1696"):
            resolved = resolve_model(model)
            assert resolved.protocol == PROTOCOL_FIXED
            assert is_drivable(resolved), model

    def test_the_1820b_is_a_counter_not_a_supply(self):
        """B&K's own matrix files it under power supplies; its manual does not.

        The 1820B manual documents single-letter counter commands (R, S?, I?),
        so driving it as a supply would send commands it has no concept of.
        """
        resolved = resolve_model("BK1823B")
        assert resolved.category == "counter"
        assert not is_drivable(resolved)


class TestCatalog:
    """The catalogue is what the API and the connect dialog consume."""

    def test_every_family_serialises(self):
        entries = catalog()
        assert len(entries) == len(MODELS)
        for entry in entries:
            assert entry["key"]
            assert entry["manufacturer"] == "B&K Precision"
            assert entry["protocol"] in {
                PROTOCOL_SCPI, PROTOCOL_SIGLENT, PROTOCOL_FIXED,
                PROTOCOL_PROPRIETARY,
            }
            assert isinstance(entry["interfaces"], list)
            assert isinstance(entry["supported"], bool)

    def test_supported_entries_map_to_a_lablink_type(self):
        for entry in catalog():
            if entry["supported"]:
                assert entry["equipment_type"] in {
                    "power_supply", "electronic_load", "multimeter",
                }

    def test_driven_categories_have_an_equipment_type(self):
        for category in DRIVEN_CATEGORIES:
            assert category in CATEGORY_TO_EQUIPMENT_TYPE

    def test_every_sku_resolves_back_to_its_own_family(self):
        """No SKU may be claimed by a family other than the one listing it."""
        for key, model in MODELS.items():
            for sku in model.skus:
                assert resolve_model(sku).key == key, f"{sku} -> not {key}"

    def test_family_keys_resolve_to_themselves(self):
        for key in MODELS:
            assert resolve_model(key).key == key

    def test_equipment_type_for_matches_the_category_map(self):
        for model in MODELS.values():
            assert equipment_type_for(model) == CATEGORY_TO_EQUIPMENT_TYPE.get(
                model.category
            )
