"""The 9205B's limits must match the supply, not a neighbouring model (#116).

`BK9205B` carried `max_voltage = 120.0` and `max_current = 10.0`, with a
comment reading "Multi-range: 60V/10A or 120V/5A" -- figures belonging to
neither SKU in the series. B&K rates the 9205B at 60 V, 25 A, 600 W and the
9206B at 150 V, 10 A, 600 W.

Wrong in both directions at once: LabLink accepted commands for twice the
voltage the supply can produce, and refused 60% of the current it can deliver.
The power ceiling came from the generic 300 W power-supply default, halving a
600 W instrument.

The supply on the bench confirms the shape of it. `SOUR:VOLT? MAX` answered
48 with the setpoints at 12 V / 20 A -- a multi-range supply recalculates its
maxima per setting, so the rating is an envelope (V x A <= 600 W within 60 V
and 25 A), not a fixed pair. That is why the fix sets a power limit rather
than only correcting two numbers.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.equipment.bk_registry import resolve_model  # noqa: E402
from server.equipment.safety import (SafetyLimits,  # noqa: E402
                                     SafetyValidator, SafetyViolation)

# B&K's published ratings.
RATINGS = {
    "9205B": {"voltage": 60.0, "current": 25.0, "power": 600.0},
    "9206B": {"voltage": 150.0, "current": 10.0, "power": 600.0},
}


class TestTheRegistryMatchesTheDatasheet:
    @pytest.mark.parametrize("sku", sorted(RATINGS))
    def test_ratings(self, sku):
        model = resolve_model(sku)

        assert model is not None, f"{sku} does not resolve"
        assert model.max_voltage == RATINGS[sku]["voltage"]
        assert model.max_current == RATINGS[sku]["current"]
        assert model.max_power == RATINGS[sku]["power"]

    def test_the_two_skus_are_no_longer_one_row(self):
        """One row for both was the bug: they share a series, not ratings."""
        assert resolve_model("9205B").key != resolve_model("9206B").key

    @pytest.mark.parametrize("spelling", [
        "9205B", "9205", "B&K Precision 9205B", "bk9205b", " 9205B ",
    ])
    def test_the_forms_that_turn_up_in_idn_still_resolve(self, spelling):
        model = resolve_model(spelling)

        assert model is not None
        assert model.max_voltage == 60.0

    def test_the_bare_series_name_resolves_to_nothing(self):
        """"9200B" alone cannot say whether it means 60 V/25 A or 150 V/10 A.

        Returning either set of limits for an ambiguous name is precisely the
        defect being fixed, so it returns none and the caller falls back to a
        conservative default.
        """
        assert resolve_model("9200B") is None


class TestTheDriverCarriesTheRating:
    def test_the_9205b_driver_no_longer_says_120v(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "server" / "equipment" / "bk_power_supply.py"
        ).read_text(encoding="utf-8")
        block = source.split("class BK9205B", 1)[1].split("\n    async def ", 1)[0]

        assert "self.max_voltage = 60.0" in block
        assert "self.max_current = 25.0" in block
        assert "self.max_power = 600.0" in block
        assert "120.0" not in block, "the neighbouring model's voltage is back"

    def test_limits_prefer_the_instrument_rating_over_the_category_default(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "server" / "equipment" / "bk_power_supply.py"
        ).read_text(encoding="utf-8")

        assert 'max_power=getattr(self, "max_power", None) or default_limits.max_power' in source
        assert "max_power=default_limits.max_power," not in source


class TestTheEnvelopeIsEnforced:
    """600 W is the real constraint; the voltage/current pair alone is not."""

    @pytest.fixture
    def validator(self):
        return SafetyValidator(
            SafetyLimits(max_voltage=60.0, max_current=25.0, max_power=600.0),
            equipment_id="ps_9205b",
        )

    def test_the_full_rated_voltage_is_allowed(self, validator):
        validator.check_voltage(60.0)          # must not raise

    def test_above_the_rated_voltage_is_refused(self, validator):
        """It used to permit 120 V on a 60 V supply."""
        with pytest.raises(SafetyViolation):
            validator.check_voltage(120.0)

    def test_the_full_rated_current_is_allowed(self, validator):
        """25 A was refused outright while the limit claimed 10 A."""
        validator.check_current(25.0)          # must not raise

    def test_above_the_rated_current_is_refused(self, validator):
        with pytest.raises(SafetyViolation):
            validator.check_current(30.0)

    def test_the_full_rated_power_is_allowed(self, validator):
        """24 V at 25 A is 600 W exactly -- the supply's whole point.

        The generic 300 W default used before would have refused this.
        """
        validator.check_power(24.0 * 25.0)     # must not raise

    def test_beyond_the_envelope_is_refused(self, validator):
        """60 V and 25 A are each within rating; together they are 1500 W."""
        with pytest.raises(SafetyViolation, match="Power"):
            validator.check_power(60.0 * 25.0)

    def test_the_old_generic_ceiling_would_have_capped_this_supply(self):
        """Guards the reason for carrying a per-model rating at all."""
        generic = SafetyValidator(
            SafetyLimits(max_voltage=60.0, max_current=25.0, max_power=300.0),
            equipment_id="ps_generic",
        )

        with pytest.raises(SafetyViolation):
            generic.check_power(24.0 * 25.0)   # 600 W, well within the 9205B
