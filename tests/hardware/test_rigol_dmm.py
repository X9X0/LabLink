"""Tests for the Rigol DM3058 / DM3058E / DM3068 multimeter drivers.

These run against a scripted fake VISA instrument that answers the RIGOL
command set the way the programming guides document it, so no hardware
is needed. Mark ``requires_hardware`` tests separately if you add any.
"""

import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("..")

from equipment.rigol_multimeter import (RigolDM3058, RigolDM3058E,  # noqa: E402
                                        RigolDM3068, normalize_function,
                                        parse_reading)
from shared.models.equipment import (ConnectionType, EquipmentType,  # noqa: E402
                                     MultimeterFunction)


class ScriptedDMM:
    """Minimal DM3058/DM3068 SCPI simulator (RIGOL command set)."""

    FUNCTION_MAP = {
        "VOLTAGE:DC": "DCV",
        "VOLTAGE:AC": "ACV",
        "CURRENT:DC": "DCI",
        "CURRENT:AC": "ACI",
        "RESISTANCE": "2WR",
        "FRESISTANCE": "4WR",
        "FREQUENCY": "FREQ",
        "PERIOD": "PERI",
        "CAPACITANCE": "CAP",
        "CONTINUITY": "CONT",
        "DIODE": "DIODE",
    }
    READINGS = {
        "DCV": "4.999871e+00",
        "ACV": "1.234500e-01",
        "DCI": "1.000210e-01",
        "ACI": "5.001000e-02",
        "2WR": "9.9E37",  # overload
        "4WR": "9.998700e+02",
        "FREQ": "1.000012e+03",
        "PERI": "9.999880e-04",
        "CAP": "1.002000e-07",
        "CONT": "8.888000e+03",
        "DIODE": "6.512000e-01",
    }
    MEASURE_ROOT_TO_FUNC = {
        "VOLTAGE:DC": "DCV",
        "VOLTAGE:AC": "ACV",
        "CURRENT:DC": "DCI",
        "CURRENT:AC": "ACI",
        "RESISTANCE": "2WR",
        "FRESISTANCE": "4WR",
        "FREQUENCY": "FREQ",
        "PERIOD": "PERI",
        "CAPACITANCE": "CAP",
        "CONTINUITY": "CONT",
        "DIODE": "DIODE",
    }

    def __init__(self, model="DM3058", cmdset="RIGOL"):
        self.model = model
        self.session = 1  # makes BaseEquipment._is_instrument_valid() happy
        self.timeout = 10000
        self.writes = []
        self.queries = []
        self.cmdset = cmdset
        self.func = "DCV"
        self.func2 = None
        self.ranges = {"DCV": 2, "ACV": 2, "DCI": 3, "ACI": 1, "2WR": 3, "4WR": 3,
                       "FREQ": 2, "PERI": 2, "CAP": 2}
        self.rate = "S"
        self.trig_source = "AUTO"
        self.trig_interval = "400" if model.startswith("DM3058") else "4.00000000E-01"
        self.single = "1"
        self.math = "NONE"
        self.beeper = "1"
        self.impedance = "10M"
        # serial attributes pyvisa exposes
        self.baud_rate = None
        self.read_termination = None
        self.write_termination = None

    def close(self):
        pass

    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.strip().upper()
        if c.startswith("CMDSET "):
            self.cmdset = c.split()[1]
        elif c.startswith(":FUNCTION2:CLEAR"):
            self.func2 = None
        elif c.startswith(":FUNCTION2:"):
            self.func2 = self.FUNCTION_MAP[c[len(":FUNCTION2:"):]]
        elif c.startswith(":FUNCTION:"):
            self.func = self.FUNCTION_MAP[c[len(":FUNCTION:"):]]
        elif c.startswith(":MEASURE:VOLTAGE:DC:IMPEDANCE "):
            self.impedance = c.split()[1]
        elif c.startswith(":MEASURE:") and ":FILTER" not in c and "RANGE" not in c:
            root, _, arg = c[len(":MEASURE:"):].partition(" ")
            func = self.MEASURE_ROOT_TO_FUNC[root]
            if func in self.ranges and arg.isdigit():
                self.ranges[func] = int(arg)
            elif arg == "MIN":
                self.ranges[func] = 0
        elif c.startswith(":RATE:"):
            self.rate = c.split()[1]
        elif c.startswith(":TRIGGER:SOURCE "):
            self.trig_source = c.split()[1]
        elif c.startswith(":TRIGGER:AUTO:INTERVAL "):
            self.trig_interval = c.split()[1]
        elif c.startswith(":TRIGGER:SINGLE "):
            self.single = c.split()[1]
        elif c.startswith(":CALCULATE:FUNCTION "):
            self.math = c.split()[1]
        elif c.startswith("SYSTEM:BEEPER:STATE "):
            self.beeper = "1" if c.split()[1] in ("ON", "1") else "0"

    def query(self, cmd):
        self.queries.append(cmd)
        c = cmd.strip().upper()
        if c == "*IDN?":
            return f"Rigol Technologies,{self.model},DM3A020080808,01.01.00.02.00.00"
        if c == "CMDSET?":
            return self.cmdset
        if c == ":FUNCTION?":
            return self.func
        if c == ":FUNCTION2:ON?":
            return "1" if self.func2 else "0"
        if c == ":FUNCTION2?":
            return self.func2 or ""
        if c == ":FUNCTION2:VALUE2?":
            return self.READINGS[self.func2]
        if c.startswith(":MEASURE:") and c.endswith(":RANGE?"):
            func = self.MEASURE_ROOT_TO_FUNC[c[len(":MEASURE:"):-len(":RANGE?")]]
            return str(self.ranges[func])
        if c == ":MEASURE:VOLTAGE:DC:IMPEDANCE?":
            return self.impedance
        if c.startswith(":MEASURE:") and c.endswith("?"):
            func = self.MEASURE_ROOT_TO_FUNC[c[len(":MEASURE:"):-1]]
            return self.READINGS[func]
        if c.startswith(":RATE:"):
            if self.model.startswith("DM3058"):
                return self.rate  # DM3058 answers F / M / S
            return {"F": "FAST", "M": "MEDIUM", "S": "SLOW"}[self.rate]
        if c == ":TRIGGER:SOURCE?":
            return self.trig_source
        if c == ":TRIGGER:AUTO:INTERVAL?":
            return self.trig_interval
        if c == ":TRIGGER:SINGLE?":
            return self.single
        if c == ":CALCULATE:FUNCTION?":
            return self.math
        if c == ":CALCULATE:STATISTIC:MIN?":
            return "4.990000e+00"
        if c == ":CALCULATE:STATISTIC:MAX?":
            return "5.010000e+00"
        if c == ":CALCULATE:STATISTIC:AVERAGE?":
            return "5.000000e+00"
        if c == ":CALCULATE:STATISTIC:COUNT?":
            return "252"
        if c == ":CALCULATE:REL:OFFSET?":
            return "3.302190e-01"
        if c == "SYSTEM:BEEPER:STATE?":
            return self.beeper
        if c == "SYSTEM:ERROR?":
            return '0,"No error"'
        if c == "*TST?":
            return "0"
        if c == ":SYSTEM:SERIAL?":
            return "DM3A020100823"
        if c == ":UTILITY:INTERFACE:RS232:BAUD?":
            return "9600"
        if c == ":UTILITY:INTERFACE:RS232:PARITY?":
            return "NONE8BITS"
        if c == ":UTILITY:INTERFACE:LAN:DHCP?":
            return "ON"
        if c == ":UTILITY:INTERFACE:LAN:IP?":
            return "172.16.3.32"
        if c == ":UTILITY:INTERFACE:LAN:MASK?":
            return "255.255.255.0"
        if c == ":UTILITY:INTERFACE:LAN:GATEWAY?":
            return "172.16.3.1"
        if c == ":UTILITY:INTERFACE:GPIB:ADDRESS?":
            return "7"
        raise AssertionError(f"Unscripted query: {cmd}")


def make_driver(cls, model, resource="USB0::0x1AB1::0x0C94::DM3A020080808::INSTR", **kw):
    inst = ScriptedDMM(model, **kw)
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return cls(rm, resource), inst


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_normalize_function_aliases():
    assert normalize_function("vdc") == "DCV"
    assert normalize_function("2WR") == "RES"
    assert normalize_function("4wr") == "FRES"
    assert normalize_function("PERI") == "PER"
    assert normalize_function(MultimeterFunction.CAP) == "CAP"
    with pytest.raises(ValueError):
        normalize_function("TEMPERATURE_OF_THE_SUN")


def test_parse_reading():
    assert parse_reading("8.492853E-01") == pytest.approx(0.8492853)
    assert parse_reading("  4.999871e+00 \n") == pytest.approx(4.999871)
    assert parse_reading("9.9E37") is None
    assert parse_reading("") is None
    assert parse_reading("1.5V") == pytest.approx(1.5)


# --------------------------------------------------------------------------- #
# Identification
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls,model,digits",
    [(RigolDM3058, "DM3058", 5.5), (RigolDM3058E, "DM3058E", 5.5), (RigolDM3068, "DM3068", 6.5)],
)
async def test_identification(cls, model, digits):
    dmm, inst = make_driver(cls, model)
    await dmm.connect()
    assert dmm.connected is True

    info = await dmm.get_info()
    assert info.type == EquipmentType.MULTIMETER
    assert info.id.startswith("dmm_")
    assert info.manufacturer == "Rigol Technologies"
    assert info.model == model
    assert info.serial_number == "DM3A020080808"
    assert info.connection_type == ConnectionType.USB

    status = await dmm.get_status()
    assert status.connected is True
    assert status.firmware_version == "01.01.00.02.00.00"
    assert status.capabilities["digits"] == digits
    assert "DCV" in status.capabilities["functions"]
    assert status.capabilities["function"] == "DCV"
    assert status.capabilities["command_set"] == "RIGOL"


@pytest.mark.asyncio
async def test_connect_forces_rigol_command_set():
    dmm, inst = make_driver(RigolDM3058, "DM3058", cmdset="AGILENT")
    await dmm.connect()
    assert "CMDSET RIGOL" in inst.writes
    assert inst.cmdset == "RIGOL"


@pytest.mark.asyncio
async def test_connect_does_not_switch_when_already_rigol():
    dmm, inst = make_driver(RigolDM3058, "DM3058", cmdset="RIGOL")
    await dmm.connect()
    assert not any(w.upper().startswith("CMDSET ") for w in inst.writes)


@pytest.mark.asyncio
async def test_serial_connection_configures_port():
    dmm, inst = make_driver(RigolDM3058E, "DM3058E", resource="ASRL/dev/ttyUSB0::INSTR")
    await dmm.connect()
    assert inst.baud_rate == 9600
    assert inst.data_bits == 8
    assert inst.write_termination == "\r\n"
    assert inst.read_termination == "\n"
    info = await dmm.get_info()
    assert info.connection_type == ConnectionType.SERIAL


@pytest.mark.asyncio
async def test_model_specific_capabilities():
    dm3058, _ = make_driver(RigolDM3058, "DM3058")
    dm3068, _ = make_driver(RigolDM3068, "DM3068")
    await dm3058.connect()
    await dm3068.connect()
    c58 = (await dm3058.get_status()).capabilities
    c68 = (await dm3068.get_status()).capabilities
    # DM3058 ACI starts at 20 mA, DM3068 at 200 uA
    assert c58["ranges"]["ACI"][0] == pytest.approx(20e-3)
    assert c68["ranges"]["ACI"][0] == pytest.approx(200e-6)
    # DM3068 capacitance goes to 100 mF, DM3058 to 10 mF
    assert c68["ranges"]["CAP"][-1] == pytest.approx(100e-3)
    assert c58["ranges"]["CAP"][-1] == pytest.approx(10e-3)
    assert c68["rate_readings_per_second"]["FAST"] == 2500.0
    assert c58["rate_readings_per_second"]["FAST"] == 123.0
    assert "LAN" in c58["interfaces"]
    e, _ = make_driver(RigolDM3058E, "DM3058E")
    await e.connect()
    assert "LAN" not in (await e.get_status()).capabilities["interfaces"]


# --------------------------------------------------------------------------- #
# Control
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_set_function_and_measure():
    dmm, inst = make_driver(RigolDM3058, "DM3058")
    await dmm.connect()

    reading = await dmm.measure("FRES")
    assert ":FUNCtion:FRESistance" in inst.writes
    assert reading.function == "FRES"
    assert reading.unit == "Ohm"
    assert reading.value == pytest.approx(999.87)
    assert reading.overload is False
    assert reading.range_index == 3
    assert reading.range_full_scale == pytest.approx(200e3)
    assert reading.rate == "SLOW"

    # Same function again must not re-send the FUNCtion command
    n = inst.writes.count(":FUNCtion:FRESistance")
    await dmm.measure("FRES")
    assert inst.writes.count(":FUNCtion:FRESistance") == n


@pytest.mark.asyncio
async def test_overload_reading_is_flagged():
    dmm, inst = make_driver(RigolDM3068, "DM3068")
    await dmm.connect()
    reading = await dmm.measure("RES")
    assert reading.overload is True
    assert reading.value is None


@pytest.mark.asyncio
async def test_set_range_by_value_index_and_keyword():
    dmm, inst = make_driver(RigolDM3058, "DM3058")
    await dmm.connect()
    await dmm.set_function("DCV")

    rng = await dmm.set_range(200.0)
    assert inst.writes[-1] == ":MEASure:VOLTage:DC 3"
    assert rng["index"] == 3 and rng["full_scale"] == 200.0 and rng["auto_range"] is False

    rng = await dmm.set_range(0)
    assert inst.writes[-1] == ":MEASure:VOLTage:DC 0"
    assert rng["full_scale"] == pytest.approx(0.2)

    rng = await dmm.set_range("AUTO")
    assert ":MEASure AUTO" in inst.writes
    assert rng["auto_range"] is True

    with pytest.raises(ValueError):
        await dmm.set_range(5000.0)  # above 1000 V


@pytest.mark.asyncio
async def test_set_range_on_continuity_sets_threshold():
    dmm, inst = make_driver(RigolDM3058, "DM3058")
    await dmm.connect()
    result = await dmm.set_range(100, function="CONT")
    assert ":MEASure:CONTinuity 100" in inst.writes
    assert result["threshold_ohms"] == 100


@pytest.mark.asyncio
async def test_rate_normalisation_on_both_models():
    for cls, model in ((RigolDM3058, "DM3058"), (RigolDM3068, "DM3068")):
        dmm, inst = make_driver(cls, model)
        await dmm.connect()
        assert await dmm.set_rate("FAST") == "FAST"
        assert inst.writes[-1] == ":RATE:VOLTage:DC F"
        assert await dmm.set_rate("m") == "MEDIUM"
        assert await dmm.get_rate() == "MEDIUM"
        with pytest.raises(ValueError):
            await dmm.set_rate("TURBO")


@pytest.mark.asyncio
async def test_trigger_interval_uses_model_units():
    dm3058, i58 = make_driver(RigolDM3058, "DM3058")
    dm3068, i68 = make_driver(RigolDM3068, "DM3068")
    await dm3058.connect()
    await dm3068.connect()

    await dm3058.set_trigger_interval(0.05)
    assert ":TRIGger:AUTO:INTErval 50" in i58.writes  # milliseconds
    assert await dm3058.set_trigger_interval(0.4) == pytest.approx(0.4)

    await dm3068.set_trigger_interval(0.05)
    assert ":TRIGger:AUTO:INTErval 0.05" in i68.writes  # seconds
    assert await dm3068.set_trigger_interval(0.4) == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_trigger_source_and_sample_count():
    dmm, inst = make_driver(RigolDM3058, "DM3058")
    await dmm.connect()
    assert await dmm.set_trigger_source("BUS") == "SINGLE"  # Agilent alias
    assert await dmm.set_sample_count(20) == 20
    await dmm.trigger()
    assert ":TRIGger:SINGle:TRIGgered" in inst.writes
    with pytest.raises(ValueError):
        await dmm.set_sample_count(5000)  # DM3058 max is 2000
    dm3068, _ = make_driver(RigolDM3068, "DM3068")
    await dm3068.connect()
    assert await dm3068.set_sample_count(5000) == 5000


@pytest.mark.asyncio
async def test_math_statistics_and_rel():
    dmm, inst = make_driver(RigolDM3058, "DM3058")
    await dmm.connect()
    assert await dmm.set_math_function("avg") == "AVERAGE"
    stats = await dmm.get_statistics()
    assert stats == {"min": 4.99, "max": 5.01, "average": 5.0, "count": 252.0}
    rel = await dmm.set_rel_offset(0.330219)
    assert ":CALCulate:REL:OFFSet 0.330219" in inst.writes
    assert ":CALCulate:REL:STATe ON" in inst.writes
    assert rel["enabled"] is True


@pytest.mark.asyncio
async def test_secondary_display():
    dmm, inst = make_driver(RigolDM3058, "DM3058")
    await dmm.connect()
    await dmm.set_function("ACV")
    assert await dmm.set_secondary_function("FREQ") == "FREQ"
    assert ":FUNCtion2:FREQuency" in inst.writes
    reading = await dmm.measure()
    assert reading.secondary_function == "FREQ"
    assert reading.secondary_value == pytest.approx(1000.012)
    assert reading.secondary_unit == "Hz"
    ch2 = await dmm.get_measurement("CH2")
    assert ch2["value"] == pytest.approx(1000.012)
    await dmm.clear_secondary_function()
    assert await dmm.get_secondary_function() is None

    # DM3068 only allows FREQ on the secondary display
    dm3068, _ = make_driver(RigolDM3068, "DM3068")
    await dm3068.connect()
    with pytest.raises(ValueError):
        await dm3068.set_secondary_function("DCV")


@pytest.mark.asyncio
async def test_dc_impedance_filter_and_beeper():
    dmm, inst = make_driver(RigolDM3068, "DM3068")
    await dmm.connect()
    assert await dmm.set_dc_impedance("10G") == "10G"
    with pytest.raises(ValueError):
        await dmm.set_dc_impedance("1M")
    assert await dmm.set_beeper(False) is False
    assert "SYSTem:BEEPer:STATe OFF" in inst.writes


# --------------------------------------------------------------------------- #
# Acquisition / streaming hooks
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_measurement_channel_semantics():
    dmm, inst = make_driver(RigolDM3058, "DM3058")
    await dmm.connect()
    main = await dmm.get_measurement("CH1")
    assert main["function"] == "DCV" and main["value"] == pytest.approx(4.999871)
    dci = await dmm.get_measurement("DCI")
    assert dci["function"] == "DCI" and dci["unit"] == "A"
    res = await dmm.get_measurement("RES")
    assert res["overload"] is True and res["value"] != res["value"]  # NaN
    with pytest.raises(ValueError):
        await dmm.get_measurement("CH2")  # secondary display off


@pytest.mark.asyncio
async def test_execute_command_dispatch_and_readings():
    dmm, inst = make_driver(RigolDM3058, "DM3058")
    await dmm.connect()
    readings = await dmm.execute_command("get_readings", {})
    assert readings.function == "DCV" and readings.unit == "V"
    meas = await dmm.execute_command("get_measurements", {"channel": 1})
    assert meas["DCV"] == pytest.approx(4.999871) and meas["DCV_unit"] == "V"
    block = await dmm.execute_command("read_samples", {"count": 5, "function": "DCV"})
    assert len(block["values"]) == 5 and block["stats"]["count"] == 5
    with pytest.raises(ValueError):
        await dmm.execute_command("fly_to_the_moon", {})


@pytest.mark.asyncio
async def test_state_error_selftest_and_interfaces():
    dmm, inst = make_driver(RigolDM3058, "DM3058")
    await dmm.connect()
    state = await dmm.execute_command("get_state", {})
    assert state["function"] == "DCV" and state["trigger_source"] == "AUTO"
    assert (await dmm.get_error())["code"] == 0
    assert await dmm.run_self_test() is True
    cfg = await dmm.get_interface_config()
    assert cfg["rs232_baud"] == "9600" and cfg["lan_ip"] == "172.16.3.32" and cfg["gpib_address"] == "7"
    e, _ = make_driver(RigolDM3058E, "DM3058E")
    await e.connect()
    cfg_e = await e.get_interface_config()
    assert "lan_ip" not in cfg_e and "gpib_address" not in cfg_e
