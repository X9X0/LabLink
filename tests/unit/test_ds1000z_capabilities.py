"""A scope should report its own bandwidth, not its driver's namesake.

The DS1000Z family shares one command tree, so the DS1054Z and DS1074Z are
driven by the class named for the DS1104Z. Capabilities were hardcoded to the
DS1104Z's, so a DS1054Z -- a 50 MHz instrument -- reported 100 MHz. That is
not a cosmetic error: it invites trusting a measurement taken well outside
the analogue front end.

Rigol encodes both numbers in the model name, so they can be read rather than
assumed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.equipment.rigol_scope import ds1000z_specs  # noqa: E402


class TestBandwidthComesFromTheModelName:
    @pytest.mark.parametrize("model,bandwidth", [
        ("DS1054Z", 50),
        ("DS1074Z", 70),
        ("DS1104Z", 100),
        ("MSO1104Z", 100),
    ])
    def test_each_member_of_the_family(self, model, bandwidth):
        assert ds1000z_specs(model)["bandwidth_mhz"] == bandwidth

    def test_the_scope_on_the_bench(self):
        """A DS1054Z is 50 MHz. This is the regression."""
        assert ds1000z_specs("DS1054Z")["bandwidth_mhz"] == 50

    def test_channel_count_too(self):
        assert ds1000z_specs("DS1054Z")["num_channels"] == 4

    def test_a_model_reported_with_its_vendor(self):
        """Some instruments answer *IDN? with the vendor in the model field."""
        assert ds1000z_specs("RIGOL DS1054Z")["bandwidth_mhz"] == 50


class TestAnythingElseKeepsTheCallersDefaults:
    @pytest.mark.parametrize("model", ["DS1102E", "MSO2072A", "", None, "DP832"])
    def test_no_guess_is_made(self, model):
        """Returning None leaves the driver's own defaults in place."""
        assert ds1000z_specs(model) is None
