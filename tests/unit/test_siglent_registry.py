"""Identifying Siglent instruments from what they answer.

The registry exists because Siglent speaks two protocols, numbers its
models by SKU rather than family, and publishes a catalogue larger than
anyone's driver collection. Each of those is a way to mis-identify an
instrument that is answering perfectly well.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.siglent_registry import (PROTOCOL_SCPI,
                                               PROTOCOL_SIGLENT_SHORT,
                                               catalog, equipment_type_for,
                                               is_drivable,
                                               is_siglent_manufacturer,
                                               resolve_idn, resolve_model,
                                               why_not_drivable)

#: What the bench unit actually answers. 192.168.91.191, USB f4ec:1430.
BENCH_IDN = ("Siglent Technologies,SPD3303X-E,SPD3XJGCA01014,"
             "1.01.01.03.12R1 V6.2")


class TestTheBenchSupply:
    def test_the_real_idn_resolves(self):
        fields, family = resolve_idn(BENCH_IDN)
        assert fields["manufacturer"] == "Siglent Technologies"
        assert fields["model"] == "SPD3303X-E"
        assert fields["serial_number"] == "SPD3XJGCA01014"
        assert family is not None and family.key == "SPD3000X"

    def test_the_firmware_field_is_left_as_given(self):
        """It is "1.01.01.03.12R1 V6.2" -- software and hardware
        version in one comma-delimited field, space separated. Tidying
        that into something it is not would lose the hardware version.
        """
        fields, _ = resolve_idn(BENCH_IDN)
        assert fields["firmware_version"] == "1.01.01.03.12R1 V6.2"

    def test_the_family_is_marked_verified(self):
        """Only families a driver here has actually been run against."""
        _, family = resolve_idn(BENCH_IDN)
        assert family.verified

    def test_it_is_drivable_and_a_power_supply(self):
        _, family = resolve_idn(BENCH_IDN)
        assert is_drivable(family)
        assert equipment_type_for(family) == "power_supply"


class TestTheSuffixIsNotNoise:
    @pytest.mark.parametrize("model", ["SPD3303X", "SPD3303X-E", "spd3303x-e",
                                       "SPD3303X E", "  SPD3303X-E  "])
    def test_both_variants_reach_the_same_family(self, model):
        family = resolve_model(model)
        assert family is not None and family.key == "SPD3000X"

    def test_a_longer_sku_is_not_shadowed_by_a_shorter_one(self):
        """SPD3303X is a prefix of SPD3303X-E. Matching the short one
        first would resolve the -E to the wrong entry -- harmless here,
        because they share a family, and not harmless in general."""
        assert resolve_model("SPD3303X-E").key == "SPD3000X"


class TestTheTwoProtocols:
    """Siglent's supplies, loads and meters are conventional SCPI. Its
    scopes and generators are not -- they use published short/long
    pairs (BSWV for BASIC_WAVE) that no capitalisation rule predicts.
    Assuming either against the other fails.
    """

    @pytest.mark.parametrize("model", ["SPD3303X-E", "SDL1020X", "SDM3065X"])
    def test_the_instrument_lines_are_scpi(self, model):
        assert resolve_model(model).protocol == PROTOCOL_SCPI

    @pytest.mark.parametrize("model", ["SDS1104X-E", "SDG2042X", "SDS800X HD"])
    def test_the_scopes_and_generators_are_not(self, model):
        assert resolve_model(model).protocol == PROTOCOL_SIGLENT_SHORT

    def test_the_short_form_families_say_why_they_are_not_driven(self):
        family = resolve_model("SDS1104X-E")
        assert "short-form" in why_not_drivable(family)


class TestTheCatalogueIsBiggerThanTheDrivers:
    """A model no entry names still has to be identified. Answering
    "unknown" for an instrument that is replying correctly sends
    somebody looking for a cable fault.
    """

    @pytest.mark.parametrize("model,category", [
        ("SPD9999Q", "psu"),
        ("SDL9999X", "load"),
        ("SDM9999X", "dmm"),
        ("SSA9999X", "spectrum"),
        ("SNA9999A", "vna"),
    ])
    def test_an_unknown_sku_is_placed_by_its_prefix(self, model, category):
        family = resolve_model(model)
        assert family is not None, model
        assert family.category == category

    def test_a_prefix_match_carries_the_right_dialect(self):
        assert resolve_model("SDG9999X").protocol == PROTOCOL_SIGLENT_SHORT
        assert resolve_model("SPD9999X").protocol == PROTOCOL_SCPI

    def test_a_prefix_match_is_never_drivable(self):
        """Knowing what kind of instrument it is says nothing about
        whether its command set matches the one we implemented."""
        family = resolve_model("SPD9999Q")
        assert not is_drivable(family)
        assert not family.verified

    def test_a_prefix_match_says_it_was_guessed(self):
        assert "prefix" in resolve_model("SPD9999Q").notes.lower()


class TestItDoesNotClaimOtherVendors:
    @pytest.mark.parametrize("model", ["DL3021A", "DS1054Z", "9205B", "1902B",
                                       "DP832", "", None])
    def test_other_manufacturers_models_are_not_siglent(self, model):
        assert resolve_model(model) is None

    @pytest.mark.parametrize("idn", [
        "RIGOL TECHNOLOGIES,DL3021A,DL3B268M00049,00.01.05.00.01",
        "B&K Precision,9205B,800886011797210043,1.0",
    ])
    def test_another_vendors_idn_resolves_to_no_family(self, idn):
        _fields, family = resolve_idn(idn)
        assert family is None


class TestTheManufacturerField:
    @pytest.mark.parametrize("spelling", [
        "Siglent Technologies", "SIGLENT", "siglent technologies",
        "Siglent Technologies Co., Ltd",
        # The USB vendor id 0xF4EC is still registered to Atten, so
        # that is what lsusb and some VISA layers report.
        "Atten Electronics", "ATTEN",
    ])
    def test_every_spelling_seen_is_recognised(self, spelling):
        assert is_siglent_manufacturer(spelling)

    @pytest.mark.parametrize("spelling", ["RIGOL TECHNOLOGIES",
                                          "B&K Precision", "", None])
    def test_other_vendors_are_not(self, spelling):
        assert not is_siglent_manufacturer(spelling)


class TestTheNulPadding:
    """These instruments NUL-pad their USB descriptors, and the padding
    survives into the resource string. Seen on the bench:

        USB0::62700::5168::SPD3XJGCA01014\\x00\\x00\\x00\\x00::0::INSTR

    A serial carrying four NULs will not compare equal to the same
    serial without them, which is the sort of thing that makes an
    instrument look like a different instrument on every scan.
    """

    def test_nuls_are_stripped_from_the_serial(self):
        fields, _ = resolve_idn(
            "Siglent Technologies,SPD3303X-E,SPD3XJGCA01014\x00\x00\x00\x00,1.0")
        assert fields["serial_number"] == "SPD3XJGCA01014"

    def test_nuls_are_stripped_from_the_model(self):
        fields, family = resolve_idn(
            "Siglent Technologies,SPD3303X-E\x00\x00,SPD3XJGCA01014,1.0")
        assert fields["model"] == "SPD3303X-E"
        assert family is not None and family.key == "SPD3000X"


class TestTheCatalogueExport:
    def test_every_entry_is_serialisable_and_labelled(self):
        entries = catalog()
        assert entries
        for entry in entries:
            assert entry["key"] and entry["name"]
            assert entry["category_label"]
            # "supported", as the other registries spell it: the models
            # endpoint concatenates all three and filters on this key.
            assert isinstance(entry["supported"], bool)

    def test_only_the_spd_families_claim_a_driver(self):
        driven = {e["key"] for e in catalog() if e["supported"]}
        assert driven == {"SPD3000X", "SPD1000X"}


class TestTheConnectDialogsModelString:
    """The connect dialog offers "{manufacturer} {model}" as one
    string and sends that as the model.

    B&K's registry has always tolerated it, so B&K instruments
    connected. This one did not, and the server refused the connection
    with "Unsupported equipment model: Siglent Technologies
    SPD3303X-E" -- naming, as unsupported, the instrument it had just
    identified on the line above.
    """

    @pytest.mark.parametrize("given,expected", [
        ("Siglent Technologies SPD3303X-E", "SPD3000X"),
        ("Siglent Technologies SPD3303X", "SPD3000X"),
        ("SIGLENT SPD1168X", "SPD1000X"),
        ("Siglent Technologies Co., Ltd SDM3065X", "SDM3000"),
        ("Atten Electronics SPD3303X", "SPD3000X"),
        ("SIGLENT SDS1104X-E", "SDS1000X-E"),
    ])
    def test_a_manufacturer_prefix_is_tolerated(self, given, expected):
        family = resolve_model(given)
        assert family is not None, given
        assert family.key == expected

    def test_a_prefixed_unknown_sku_still_reaches_the_prefix_scheme(self):
        assert resolve_model("Siglent Technologies SPD9999Q").category == "psu"

    @pytest.mark.parametrize("given", ["Siglent", "SIGLENT",
                                       "Siglent Technologies", "Atten"])
    def test_a_manufacturer_on_its_own_resolves_to_nothing(self, given):
        """Stripping the name must not leave an empty string that then
        matches something."""
        assert resolve_model(given) is None

    @pytest.mark.parametrize("given", ["RIGOL TECHNOLOGIES DL3021A",
                                       "B&K Precision 9205B"])
    def test_other_vendors_are_still_not_claimed(self, given):
        assert resolve_model(given) is None


class TestItIsRegisteredEverywhere:
    """DRIVER_AUTHORING.md lists where a new driver has to be named.

    Missing one is not cosmetic: a family absent from the catalogue
    never reaches the connect dialog's model list, and a catalogue
    entry shaped differently from its neighbours makes the endpoint
    that concatenates all three raise or quietly drop it.
    """

    def test_the_catalogue_matches_the_others(self):
        """/api/equipment/models concatenates three registries and
        filters on `manufacturer` and `supported`."""
        from server.equipment.bk_registry import catalog as bk_catalog

        theirs = set(bk_catalog()[0])
        for entry in catalog():
            missing = theirs - set(entry)
            assert not missing, (entry["key"], sorted(missing))

    def test_every_entry_names_the_manufacturer(self):
        assert all(e["manufacturer"] == "Siglent Technologies"
                   for e in catalog())

    def test_the_supported_families_are_the_driven_ones(self):
        assert {e["key"] for e in catalog() if e["supported"]} == {
            "SPD3000X", "SPD1000X"}

    def test_the_drivers_are_exported(self):
        from server.equipment import (SiglentSPD, SiglentSPD1000X,
                                      SiglentSPD3303X)

        assert SiglentSPD and SiglentSPD3303X and SiglentSPD1000X

    def test_the_manufacturer_constant_names_the_skus(self):
        from shared.constants import SUPPORTED_MANUFACTURERS

        assert "SIGLENT" in SUPPORTED_MANUFACTURERS
        assert "SPD3303X-E" in SUPPORTED_MANUFACTURERS["SIGLENT"]

    def test_the_readme_lists_the_supply(self):
        """A supported instrument nobody can find is not much use."""
        import pathlib

        readme = pathlib.Path(__file__).resolve().parents[2] / "README.md"
        assert "SPD3303X" in readme.read_text(encoding="utf-8")

    def test_there_is_a_brand_document(self):
        import pathlib

        doc = (pathlib.Path(__file__).resolve().parents[2]
               / "docs" / "SIGLENT.md")
        said = doc.read_text(encoding="utf-8")
        # The two things a reader most needs from it.
        assert "BASIC_WAVE" in said, "the two protocols are not explained"
        assert "MEAS:POW?" in said, "the abbreviation trap is not recorded"
