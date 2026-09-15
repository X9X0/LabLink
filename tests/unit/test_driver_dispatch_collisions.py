"""A model keyword must not claim another vendor's instrument.

Driver selection matches upper-case substrings of the model name, in a fixed
order, first hit wins. That is workable but sharp in two ways, and both are
guarded here because neither fails loudly -- the instrument simply gets the
wrong driver and misbehaves later, at the bench.

**Across vendors.** B&K's RFM3000 contains "M300", which is the Rigol M300
data acquisition keyword, so a B&K instrument was dispatched to a Rigol
driver. The keyword registry is consulted before the B&K one, so Rigol won.
Matching is now anchored to a word boundary at the leading edge.

**Within Rigol.** Several families are prefixes of each other: RSA3030N is a
VNA while RSA3030 is a spectrum analyser, DM858E is not DM858, and the "Pro"
platforms share a stem with the classic ones. These depend on the *order* of
KEYWORD_DRIVER_CLASSES, which nothing else checks.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.equipment import bk_registry  # noqa: E402
from server.equipment.manager import (  # noqa: E402
    find_keyword_driver, _keyword_matches)


def _every_bk_model():
    """Every model string the B&K registry documents."""
    models = set()
    for name in dir(bk_registry):
        value = getattr(bk_registry, name)
        if isinstance(value, dict):
            models |= {k for k in value if isinstance(k, str)}
    return models


class TestNoBKInstrumentGetsARigolDriver:
    def test_the_whole_bk_catalogue_is_clear(self):
        stolen = {
            model: find_keyword_driver(model.upper()).__name__
            for model in sorted(_every_bk_model())
            if find_keyword_driver(model.upper()) is not None
        }

        assert not stolen, f"B&K models claimed by Rigol drivers: {stolen}"

    def test_the_one_that_was_actually_wrong(self):
        """RFM3000 contains M300. This is the regression."""
        assert find_keyword_driver("RFM3000") is None

    @pytest.mark.parametrize("model", ["1685B", "9205B", "1902B"])
    def test_the_supplies_on_the_bench(self, model):
        assert find_keyword_driver(model) is None


class TestKeywordsMatchModelNamesNotFragments:
    def test_a_keyword_at_the_start_matches(self):
        assert _keyword_matches("M300", "M300")

    def test_a_keyword_after_a_separator_matches(self):
        """Some servers report "RIGOL M300" rather than a bare model."""
        assert _keyword_matches("M300", "RIGOL M300")

    def test_a_keyword_buried_in_a_longer_word_does_not(self):
        assert not _keyword_matches("M300", "RFM3000")

    def test_a_family_prefix_still_matches_its_models(self):
        """Keywords are a mix of whole names and prefixes; prefixes must work."""
        assert _keyword_matches("DSG3", "DSG3060")
        assert _keyword_matches("DHO8", "DHO814")


class TestFamiliesThatArePrefixesOfEachOther:
    @pytest.mark.parametrize("model,expected", [
        # A VNA whose name contains a spectrum analyser's.
        ("RSA3030N", "RigolRSAN"),
        ("RSA3030", "RigolRSA3000"),
        # An E variant that is a different instrument from the base model.
        ("DM858E", "RigolDM858E"),
        ("DM858", "RigolDM858"),
        # Ordinary families, to catch an ordering change breaking the common case.
        ("DP832", "RigolDP800"),
        ("DP712", "RigolDP700"),
        ("DG1062Z", "RigolDG1000Z"),
        ("DSA815", "RigolDSA800"),
        ("MSO5074", "RigolMSO5000"),
        ("DL3031A", "RigolDL3031A"),
    ])
    def test_the_more_specific_family_wins(self, model, expected):
        driver = find_keyword_driver(model)

        assert driver is not None, f"{model} matched no driver at all"
        assert driver.__name__ == expected
