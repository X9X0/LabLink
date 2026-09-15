"""Tests for the Rigol DL3000 electronic load model table and drivers.

Runs against a scripted fake VISA instrument that answers the DL3000
Programming Guide command tree; no hardware needed.
"""

import math
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("..")

from equipment.rigol_electronic_load import (DL3000_MODELS,  # noqa: E402
                                             RigolDL3000Base, RigolDL3021A,
                                             RigolDL3031A,
                                             lookup_dl3000_model)
from shared.models.equipment import EquipmentType  # noqa: E402


class ScriptedDL3000:
    """Minimal DL3000 SCPI simulator."""

    def __init__(self, model="DL3031A"):
        self.model = model
        self.session = 1
        self.timeout = 10000
        self.writes = []
        self.queries = []
        self.func = "CC"
        self.setpoints = {"CURR": "0", "VOLT": "0", "RES": "0", "POW": "0"}
        self.ranges = {"CURR": "6", "VOLT": "150", "RES": "15000"}
        self.input = "0"
        self.meas = {"VOLT": "12.500", "CURR": "5.0000", "POW": "62.500", "RES": "2.5000"}

    def close(self):
        pass

    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.strip().upper()
        if c.startswith(":SOUR:FUNC "):
            self.func = c.split()[1]
        elif c.startswith(":SOUR:INP:STAT "):
            self.input = "1" if c.split()[1] in ("ON", "1") else "0"
        elif c.startswith(":SOUR:") and ":LEV:IMM " in c:
            key = c.split(":")[2]
            self.setpoints[key] = c.split()[1]
        elif c.startswith(":SOUR:") and ":RANG " in c:
            key = c.split(":")[2]
            arg = c.split()[1]
            hi = {"CURR": "60" if "3031" in self.model else "40", "VOLT": "150", "RES": "15000"}[key]
            lo = {"CURR": "6" if "3031" in self.model else "4", "VOLT": "15", "RES": "15"}[key]
            self.ranges[key] = {"MIN": lo, "MAX": hi, "DEF": lo if key == "CURR" else hi}.get(arg, arg)
        elif c in ("*RST", "*CLS"):
            self.func = "CC"
            self.input = "0"

    def query(self, cmd):
        self.queries.append(cmd)
        c = cmd.strip().upper()
        if c == "*IDN?":
            return f"RIGOL TECHNOLOGIES,{self.model},DL3A123456789,00.01.03"
        if c == ":SOUR:FUNC?":
            return self.func
        if c == ":SOUR:INP:STAT?":
            return self.input
        if c.startswith(":SOUR:") and c.endswith(":LEV:IMM?"):
            return self.setpoints[c.split(":")[2]]
        if c.startswith(":SOUR:") and c.endswith(":RANG?"):
            return self.ranges[c.split(":")[2]]
        if c.startswith(":MEAS:") and c.endswith("?"):
            return self.meas[c[len(":MEAS:"):-1]]
        if c == ":SYSTEM:ERROR?":
            return '0,"No error"'
        raise AssertionError(f"Unscripted query: {cmd}")


def make_driver(cls, model, resource="USB0::0x1AB1::0x0E11::DL3A123456789::INSTR"):
    inst = ScriptedDL3000(model)
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return cls(rm, resource), inst


# --------------------------------------------------------------------------- #
# Model table
# --------------------------------------------------------------------------- #


def test_model_table_ratings():
    assert DL3000_MODELS["DL3021"].max_current == 40.0
    assert DL3000_MODELS["DL3021"].max_power == 200.0
    assert DL3000_MODELS["DL3021A"].max_voltage == 150.0
    assert DL3000_MODELS["DL3031"].max_current == 60.0
    assert DL3000_MODELS["DL3031"].max_power == 350.0
    assert DL3000_MODELS["DL3031A"].low_current_range == 6.0
    assert DL3000_MODELS["DL3041"].max_voltage == 200.0
    assert lookup_dl3000_model("dl3021a").model == "DL3021A"
    assert lookup_dl3000_model("DL3031") .model == "DL3031"
    assert lookup_dl3000_model("DL9999") is None
    assert lookup_dl3000_model(None) is None


# --------------------------------------------------------------------------- #
# Identification picks the row from *IDN?
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls,model,max_i,max_p,low_i",
    [
        (RigolDL3021A, "DL3021", 40.0, 200.0, 4.0),
        (RigolDL3021A, "DL3021A", 40.0, 200.0, 4.0),
        (RigolDL3031A, "DL3031", 60.0, 350.0, 6.0),
        (RigolDL3031A, "DL3031A", 60.0, 350.0, 6.0),
    ],
)
async def test_identification(cls, model, max_i, max_p, low_i):
    load, inst = make_driver(cls, model)
    await load.connect()
    info = await load.get_info()
    assert info.type == EquipmentType.ELECTRONIC_LOAD
    assert info.id.startswith("load_")
    assert info.manufacturer == "RIGOL TECHNOLOGIES"
    assert info.model == model
    assert info.serial_number == "DL3A123456789"
    status = await load.get_status()
    assert status.connected is True
    assert status.firmware_version == "00.01.03"
    caps = status.capabilities
    assert caps["max_voltage"] == 150.0
    assert caps["max_current"] == max_i
    assert caps["max_power"] == max_p
    assert caps["current_ranges"] == [low_i, max_i]
    assert caps["modes"] == ["CC", "CV", "CR", "CP"]
    assert caps["supports_acquisition"] is True
    assert load.spec.model == model


@pytest.mark.asyncio
async def test_idn_overrides_class_default():
    """A DL3021A driver instance connected to a DL3031A adopts the 60 A row."""
    load, inst = make_driver(RigolDL3021A, "DL3031A")
    assert load.max_current == 40.0  # class default before connecting
    await load.connect()
    assert load.max_current == 60.0 and load.max_power == 350.0
    await load.set_current(55.0)  # valid on a DL3031A, invalid on a DL3021A
    assert ":SOUR:CURR:LEV:IMM 55.0" in inst.writes


@pytest.mark.asyncio
async def test_unknown_model_keeps_class_defaults():
    load, inst = make_driver(RigolDL3031A, "DL3099X")
    await load.connect()
    assert load.model == "DL3099X"
    assert load.spec.model == "DL3031A"
    assert load.max_current == 60.0


def test_dl3021a_is_thin_subclass():
    assert issubclass(RigolDL3021A, RigolDL3000Base)
    assert issubclass(RigolDL3031A, RigolDL3000Base)
    assert RigolDL3021A.MODEL == "DL3021A" and RigolDL3031A.MODEL == "DL3031A"


# --------------------------------------------------------------------------- #
# Setpoint validation against the model row
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_setpoint_validation_dl3021a():
    load, inst = make_driver(RigolDL3021A, "DL3021A")
    await load.connect()
    await load.set_mode("cc")
    assert ":SOUR:FUNC CC" in inst.writes
    await load.set_current(40.0)
    with pytest.raises(ValueError):
        await load.set_current(40.01)
    await load.set_voltage(150.0)
    with pytest.raises(ValueError):
        await load.set_voltage(150.5)
    await load.set_power(200.0)
    with pytest.raises(ValueError):
        await load.set_power(200.5)
    await load.set_resistance(15000.0)
    with pytest.raises(ValueError):
        await load.set_resistance(15001.0)
    with pytest.raises(ValueError):
        await load.set_resistance(0.05)  # below the 0.08 Ohm low-range limit
    with pytest.raises(ValueError):
        await load.set_resistance(0.0)
    with pytest.raises(ValueError):
        await load.set_mode("CW")


@pytest.mark.asyncio
async def test_setpoint_validation_dl3031a():
    load, inst = make_driver(RigolDL3031A, "DL3031A")
    await load.connect()
    await load.set_current(60.0)
    await load.set_power(350.0)
    with pytest.raises(ValueError):
        await load.set_current(60.1)
    with pytest.raises(ValueError):
        await load.set_power(351.0)
    sp = await load.get_setpoint("CC")
    assert sp == {"mode": "CC", "setpoint": 60.0, "unit": "A"}


@pytest.mark.asyncio
async def test_ranges():
    load, inst = make_driver(RigolDL3031A, "DL3031A")
    await load.connect()
    assert await load.set_current_range("HIGH") == 60.0
    assert inst.writes[-1] == ":SOUR:CURR:RANG MAX"
    assert await load.set_current_range(3.0) == 6.0  # snaps to the low range
    assert inst.writes[-1] == ":SOUR:CURR:RANG 6"
    assert await load.set_voltage_range(15) == 15.0
    assert await load.set_resistance_range(100) == 15000.0
    with pytest.raises(ValueError):
        await load.set_current_range(61.0)
    ranges = await load.get_ranges()
    assert ranges == {"current_range": 6.0, "voltage_range": 15.0, "resistance_range": 15000.0}


# --------------------------------------------------------------------------- #
# Readings / acquisition hooks
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_readings_and_input():
    load, inst = make_driver(RigolDL3021A, "DL3021A")
    await load.connect()
    await load.set_mode("CV")
    await load.set_voltage(12.0)
    await load.set_input(True)
    assert ":SOUR:INP:STAT ON" in inst.writes
    readings = await load.get_readings()
    assert readings.mode == "CV"
    assert readings.setpoint == 12.0
    assert readings.voltage == 12.5 and readings.current == 5.0 and readings.power == 62.5
    assert readings.load_enabled is True
    assert await load.get_input() is True
    await load.set_input(False)
    assert ":SOUR:INP:STAT OFF" in inst.writes
    assert await load.get_input() is False


@pytest.mark.asyncio
async def test_get_measurement_channels():
    load, inst = make_driver(RigolDL3021A, "DL3021A")
    await load.connect()
    assert await load.get_measurement("V") == {"value": 12.5, "unit": "V", "quantity": "voltage"}
    assert (await load.get_measurement("I"))["value"] == 5.0
    assert (await load.get_measurement("P"))["value"] == 62.5
    assert (await load.get_measurement("R"))["value"] == 2.5
    assert (await load.get_measurement("CH1:CURR"))["unit"] == "A"
    assert (await load.get_measurement("power"))["quantity"] == "power"
    assert (await load.get_measurement(""))["quantity"] == "voltage"
    with pytest.raises(ValueError):
        await load.get_measurement("TEMP")
    inst.meas["POW"] = "garbage"
    assert math.isnan((await load.get_measurement("P"))["value"])
    meas = await load.get_measurements()
    assert meas["voltage"] == 12.5 and meas["resistance"] == 2.5


@pytest.mark.asyncio
async def test_get_state_and_execute_command():
    load, inst = make_driver(RigolDL3031A, "DL3031A")
    await load.connect()
    await load.execute_command("set_mode", {"mode": "CR"})
    await load.execute_command("set_resistance", {"resistance": 47.0})
    state = await load.execute_command("get_state", {})
    assert state["model"] == "DL3031A"
    assert state["mode"] == "CR" and state["setpoint"] == 47.0
    assert state["input_enabled"] is False
    assert state["current_range"] == 6.0
    meas = await load.execute_command("get_measurement", {"channel": "I"})
    assert meas["value"] == 5.0
    err = await load.execute_command("get_error", {})
    assert err["code"] == 0 and err["message"] == "No error"
    await load.execute_command("reset", {})
    assert "*RST" in inst.writes
    with pytest.raises(ValueError):
        await load.execute_command("fly_to_the_moon", {})
