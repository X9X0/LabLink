"""Tests for the B&K drivers and the registry-driven driver dispatch.

The fixed-width tests are the important ones: that protocol has no error
queue and no query syntax, so a wrongly scaled field is accepted silently and
the supply simply sources the wrong thing.
"""

from unittest.mock import MagicMock, patch

import pytest

from equipment.bk_power_supply import (DIALECT_1685B, DIALECT_PRESET_INDEXED,
                                       DIALECT_STANDARD, BK1685B, BK1687B,
                                       BK1696, BK1902B, BK9103, BK9104,
                                       BK9130B, BK9206B, BKPowerSupplyBase,
                                       dialect_for)
from equipment.bk_scpi import (BK9130Series, BKSCPIElectronicLoad,
                               BKSCPIMultimeter, BKSCPIPowerSupply)
from equipment.manager import EquipmentManager
from shared.models.equipment import EquipmentType


@pytest.fixture
def manager():
    manager = EquipmentManager()
    manager.resource_manager = MagicMock()
    return manager


class TestFixedWidthScaling:
    """Field scaling is not uniform across the fixed-width family."""

    def test_1685b_carries_two_decimals_for_current(self):
        """The 1685B manual is explicit, and it is alone in the family.

        Encoding 2.5 A at one decimal sends CURR025, which a 1685B reads as
        0.25 A — a tenfold error the protocol cannot report.
        """
        supply = BK1685B(MagicMock(), "ASRL/dev/ttyUSB0::INSTR")
        assert supply.dialect is DIALECT_1685B
        assert supply._encode_current(2.5) == "250"
        assert supply._encode_voltage(1.0) == "010"

    def test_1687b_and_1902b_carry_one_decimal(self):
        for cls in (BK1687B, BK1902B):
            supply = cls(MagicMock(), "ASRL/dev/ttyUSB0::INSTR")
            assert supply.dialect is DIALECT_STANDARD
            assert supply._encode_current(2.5) == "025"

    def test_voltage_encoding_matches_the_manual_example(self):
        """The manual's own example: VOLT010 sets 1.0 V."""
        supply = BK1902B(MagicMock(), "ASRL1::INSTR")
        assert supply._encode_voltage(1.0) == "010"

    def test_an_unencodable_value_is_refused_not_truncated(self):
        """An over-wide field shifts every character after it."""
        supply = BK1685B(MagicMock(), "ASRL1::INSTR")
        with pytest.raises(ValueError, match="field is 3 wide"):
            supply._encode_current(99.0)  # 9900 at two decimals
        with pytest.raises(ValueError, match="non-negative"):
            supply._encode_voltage(-1.0)

    def test_gets_decoding_follows_the_dialect(self):
        assert BK1685B(MagicMock(), "ASRL1::INSTR")._decode_setpoints(
            "025051"
        ) == (2.5, 0.51)
        assert BK1902B(MagicMock(), "ASRL1::INSTR")._decode_setpoints(
            "025051"
        ) == (2.5, 5.1)

    def test_short_gets_reply_is_rejected(self):
        supply = BK1902B(MagicMock(), "ASRL1::INSTR")
        with pytest.raises(ValueError, match="Invalid GETS"):
            supply._decode_setpoints("025")


class TestPresetIndexedDialect:
    """The 9103/9104 are fixed-width, but not the 1685B's fixed-width."""

    def test_sout_polarity_is_inverted_relative_to_the_1685b(self):
        """On a 1685B SOUT0 enables the output; on a 9103 it disables it."""
        assert BK1685B(MagicMock(), "ASRL1::INSTR").dialect.sout_on == "0"
        assert BK9103(MagicMock(), "ASRL1::INSTR").dialect.sout_on == "1"

    def test_four_digit_two_decimal_fields(self):
        """The manual's example: VOLT01000 sets 10.00 V on preset 0."""
        supply = BK9103(MagicMock(), "ASRL1::INSTR")
        assert supply.dialect is DIALECT_PRESET_INDEXED
        assert supply._encode_voltage(10.0) == "1000"
        assert supply._encode_current(1.0) == "0100"
        # A GETS reply of 1000 0100 is 10.00 V and 1.00 A.
        assert supply._decode_setpoints("10000100") == (10.0, 1.0)

    def test_9104_has_its_own_limits(self):
        assert BK9104(MagicMock(), "ASRL1::INSTR").max_voltage == 84.0
        assert BK9103(MagicMock(), "ASRL1::INSTR").max_voltage == 42.0

    def test_dialect_for_picks_by_model(self):
        assert dialect_for("1685B") is DIALECT_1685B
        assert dialect_for("1902B") is DIALECT_STANDARD
        assert dialect_for("9104") is DIALECT_PRESET_INDEXED


class TestGetdScaling:
    """GETD is four digits of volts and four of amps, both at two decimals."""

    @pytest.mark.asyncio
    async def test_readings_match_the_manual_example(self):
        """The manual: 030201450 is 3.02 V and 1.45 A in CV mode."""
        supply = BK1685B(MagicMock(), "ASRL1::INSTR")
        replies = {"GETD": "030201450", "GOUT": "0", "GETS": "050051"}

        async def fake_query(command):
            return replies[command]

        with patch.object(supply, "_bk_query", side_effect=fake_query):
            readings = await supply.get_readings()

        assert readings.voltage_actual == pytest.approx(3.02)
        assert readings.current_actual == pytest.approx(1.45)
        assert readings.in_cv_mode is True
        assert readings.in_cc_mode is False
        assert readings.output_enabled is True

    @pytest.mark.asyncio
    async def test_output_state_follows_the_dialect_polarity(self):
        """GOUT mirrors SOUT, so its polarity is dialect-specific too."""
        supply = BK9103(MagicMock(), "ASRL1::INSTR")
        replies = {"GETD": "050001000", "GOUT": "0", "GETS": "05000100"}

        async def fake_query(command):
            return replies[command]

        with patch.object(supply, "_bk_query", side_effect=fake_query):
            readings = await supply.get_readings()

        # 0 means OFF on this dialect, the opposite of the 1685B.
        assert readings.output_enabled is False


class TestDriverDispatch:
    """The manager resolves a SKU to a family and picks a driver from it."""

    @pytest.mark.parametrize("model,expected", [
        # Hand-written drivers win over the generic one.
        ("9130B", BK9130B), ("9131B", BK9130B), ("9132B", BK9130B),
        ("BK Precision 1685B", BK1685B), ("1687B", BK1687B),
        ("1902B", BK1902B), ("9104", BK9104), ("9206B", BK9206B),
        ("1697", BK1696),
        # Everything else falls to the generic SCPI drivers.
        ("9241", BKSCPIPowerSupply), ("MR40003", BKSCPIPowerSupply),
        ("BCS6402", BKSCPIPowerSupply), ("9140", BKSCPIPowerSupply),
        ("MDL252", BKSCPIElectronicLoad), ("8612", BKSCPIElectronicLoad),
        ("2841", BKSCPIMultimeter), ("5493C", BKSCPIMultimeter),
    ])
    def test_dispatches_by_family(self, manager, model, expected):
        instance = manager._create_equipment_instance(
            "ASRL/dev/ttyUSB0::INSTR", EquipmentType.POWER_SUPPLY, model
        )
        assert isinstance(instance, expected)

    @pytest.mark.parametrize("model", [
        "2569B-MSO",   # a scope: identified, but no B&K scope driver
        "4053B",       # Siglent-style generator
        "DAS701",      # data recorder: no LabLink equipment type
        "HPS",         # proprietary subsystem commands
        "9814",        # fixed-width power meter, no driver
    ])
    def test_refuses_families_it_cannot_actually_drive(self, manager, model):
        """Better to refuse than to send SCPI at something that ignores it."""
        assert manager._create_equipment_instance(
            "TCPIP::192.168.1.50::INSTR", EquipmentType.POWER_SUPPLY, model
        ) is None

    def test_leaves_other_manufacturers_alone(self, manager):
        assert manager._create_bk_instance(
            "USB::INSTR", EquipmentType.OSCILLOSCOPE, "DS1054Z"
        ) is None

    def test_rigol_dispatch_still_works(self, manager):
        from equipment.rigol_scope import RigolDS1104

        instance = manager._create_equipment_instance(
            "USB::INSTR", EquipmentType.OSCILLOSCOPE, "DS1104Z"
        )
        assert isinstance(instance, RigolDS1104)

    def test_hand_written_drivers_are_registered_for_real_families(self):
        """A typo'd key here would silently fall through to the generic driver."""
        from equipment.bk_registry import resolve_model

        for sku in EquipmentManager._BK_SPECIFIC_DRIVERS:
            assert resolve_model(sku) is not None, sku


class TestSCPIDrivers:
    """The generic SCPI drivers take their limits from the registry."""

    def test_9130_channel_three_is_the_five_volt_rail(self):
        supply = BK9130Series(MagicMock(), "ASRL1::INSTR", model="9130B")
        assert supply.channel_max_voltage(1) == 30.0
        assert supply.channel_max_voltage(3) == 5.0

    def test_9130b_is_scpi_not_fixed_width(self):
        """It previously inherited the legacy base and read via GETD/GETS."""
        supply = BK9130B(MagicMock(), "ASRL1::INSTR")
        assert isinstance(supply, BKSCPIPowerSupply)
        assert not isinstance(supply, BKPowerSupplyBase)

    def test_9206b_is_scpi_not_fixed_width(self):
        supply = BK9206B(MagicMock(), "ASRL1::INSTR")
        assert isinstance(supply, BKSCPIPowerSupply)
        assert not isinstance(supply, BKPowerSupplyBase)

    def test_registry_supplies_channel_count_and_limits(self):
        supply = BKSCPIPowerSupply(MagicMock(), "TCPIP::x::INSTR", model="9140")
        assert supply.num_channels == 3
        assert supply.info.key == "9140"

    @pytest.mark.asyncio
    async def test_setters_reject_out_of_range_values(self):
        supply = BKSCPIPowerSupply(MagicMock(), "TCPIP::x::INSTR", model="9130B")
        with pytest.raises(ValueError):
            await supply.set_voltage(500.0)
        with pytest.raises(ValueError):
            await supply.set_current(-1.0)

    @pytest.mark.asyncio
    async def test_channel_selection_is_range_checked(self):
        supply = BKSCPIPowerSupply(MagicMock(), "TCPIP::x::INSTR", model="9130B")
        with pytest.raises(ValueError, match="Invalid channel"):
            await supply.set_voltage(5.0, channel=4)

    def test_single_channel_models_skip_channel_selection(self):
        """INST:NSEL is meaningless on a one-output supply."""
        supply = BKSCPIPowerSupply(MagicMock(), "TCPIP::x::INSTR", model="9240")
        assert supply.num_channels == 1

    def test_load_mode_names_are_normalized(self):
        load = BKSCPIElectronicLoad(MagicMock(), "TCPIP::x::INSTR", model="MDL")
        assert load._normalize_mode("cc") == "CC"
        assert load._normalize_mode("RESISTANCE") == "CR"
        assert load._normalize_mode("POWer") == "CP"
        with pytest.raises(ValueError):
            load._normalize_mode("banana")

    def test_meter_rejects_unknown_functions(self):
        meter = BKSCPIMultimeter(MagicMock(), "TCPIP::x::INSTR", model="2840")
        assert meter._mnemonic("resistance_4w") == "FRES"
        with pytest.raises(ValueError, match="unknown function"):
            meter._mnemonic("astrology")

    def test_absorbing_idn_fills_in_an_unknown_model(self):
        supply = BKSCPIPowerSupply(MagicMock(), "TCPIP::x::INSTR")
        supply._absorb_idn("B&KPrecision,9141,614D21108,1.06-1.04")
        assert supply.info.key == "9140"
        assert supply.model == "9141"
        assert supply._serial_number == "614D21108"
        assert supply._firmware_version == "1.06-1.04"
        assert supply.num_channels == 3

    def test_capabilities_report_the_registry_facts(self):
        supply = BKSCPIPowerSupply(MagicMock(), "TCPIP::x::INSTR", model="9140")
        caps = supply._capabilities()
        assert caps["family"] == "9140"
        assert caps["usb_mode"] == "cdc"
        assert "LAN" in caps["interfaces"]
