"""Tests for the Rigol DM858 / DM858E multimeter driver.

A scripted fake instrument answers the standard-SCPI DMM tree documented in
the DM858 Series Programming Guide; no hardware needed.
"""

import math
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("..")

from server.equipment.rigol_multimeter_dm858 import (RigolDM858, RigolDM858E,  # noqa: E402
                                              normalize_function,
                                              parse_reading, parse_readings)
from shared.models.equipment import (ConnectionType, EquipmentType,  # noqa: E402
                                     MultimeterFunction)


class ScriptedDM858:
    """Minimal DM858 SCPI simulator."""

    FUNC_KEYWORDS = {
        "VOLTAGE:DC": "VOLT", "VOLTAGE:AC": "VOLT:AC", "CURRENT:DC": "CURR", "CURRENT:AC": "CURR:AC",
        "RESISTANCE": "RES", "FRESISTANCE": "FRES", "FREQUENCY": "FREQ", "PERIOD": "PER",
        "CAPACITANCE": "CAP", "CONTINUITY": "CONT", "DIODE": "DIOD", "TEMPERATURE": "TEMP",
    }
    # SENSe sub-tree -> short function code
    SENSE_ROOTS = {
        "VOLTAGE:DC": "VOLT", "VOLTAGE:AC": "VOLT:AC", "CURRENT:DC": "CURR", "CURRENT:AC": "CURR:AC",
        "RESISTANCE": "RES", "FRESISTANCE": "FRES", "FREQUENCY": "FREQ", "PERIOD": "PER",
        "CAPACITANCE": "CAP",
    }
    READINGS = {
        "VOLT": "4.99987100E+00", "VOLT:AC": "1.23450000E-01", "CURR": "1.00021000E-01",
        "CURR:AC": "5.00100000E-02", "RES": "9.90000000E+37", "FRES": "9.99870000E+02",
        "FREQ": "1.00001200E+03", "PER": "9.99988000E-04", "CAP": "1.00200000E-07",
        "CONT": "8.88800000E+03", "DIOD": "6.51200000E-01", "TEMP": "2.31500000E+01",
    }

    def __init__(self, model="DM858"):
        self.model = model
        self.session = 1
        self.timeout = 10000
        self.writes = []
        self.queries = []
        self.func = "VOLT"
        self.ranges = {"VOLT": 10.0, "VOLT:AC": 10.0, "CURR": 1.0, "CURR:AC": 1.0, "RES": 100e3,
                       "FRES": 100e3, "FREQ": 10.0, "PER": 10.0, "CAP": 1e-6}
        self.auto = {k: True for k in self.ranges}
        self.nplc = {"VOLT": 20.0, "CURR": 20.0, "RES": 20.0, "FRES": 20.0}
        self.resolution = {"VOLT": 1e-4, "CURR": 1e-5, "RES": 1e-2, "FRES": 1e-2}
        self.null_state = {k: False for k in self.ranges}
        self.null_value = {k: 0.0 for k in self.ranges}
        self.null_auto = {k: False for k in self.ranges}
        self.secondary = {k: "OFF" for k in self.ranges}
        self.trig_source = "IMM"
        self.trig_count = 1
        self.sample_count = 1
        self.memory = []
        self.scale_state = False
        self.scale_func = "DB"
        self.avg_state = False
        self.limit_state = False
        self.limits = [0.0, 0.0]
        self.questionable = 0
        self.beeper = "1"
        self.temp_unit = "C"
        self.config_extra = ""
        self.aborted = 0

    def close(self):
        pass

    def _root(self, c):
        """Return (short func code, remainder) for a SENSe:<func>:... command."""
        body = c[len("SENSE:"):]
        for root in sorted(self.SENSE_ROOTS, key=len, reverse=True):
            if body.startswith(root + ":"):
                return self.SENSE_ROOTS[root], body[len(root) + 1:]
        raise AssertionError(f"Unscripted SENSe root in {c}")

    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.strip().upper()
        head, _, arg = c.partition(" ")
        if c == "*RST":
            writes, queries = self.writes, self.queries
            self.__init__(self.model)
            self.writes, self.queries = writes, queries
            return
        if c == "*CLS":
            return
        if c == "*TRG":
            if self.trig_source == "BUS":
                self.memory.extend([self.READINGS[self.func]] * self.sample_count)
            return
        if c in ("INITIATE", "INITIATE:IMMEDIATE"):
            if self.trig_source == "IMM":
                self.memory.extend([self.READINGS[self.func]] * self.sample_count)
            return
        if c == "ABORT":
            self.aborted += 1
            return
        if head == "SENSE:FUNCTION":
            self.func = self.FUNC_KEYWORDS[arg.strip('"')]
            return
        if head.startswith("CONFIGURE:"):
            kw = head[len("CONFIGURE:"):]
            self.func = self.FUNC_KEYWORDS[kw]
            self.config_extra = arg
            if arg and self.func in self.ranges:
                first = arg.split(",")[0]
                if first == "AUTO":
                    self.auto[self.func] = True
                elif first not in ("MIN", "MAX", "DEF"):
                    self.ranges[self.func] = float(first)
                    self.auto[self.func] = False
            return
        if head.startswith("SENSE:"):
            func, rest = self._root(head)
            if rest == "RANGE":
                if arg == "MIN":
                    self.ranges[func] = 0.1
                elif arg == "MAX":
                    self.ranges[func] = 1000.0
                else:
                    self.ranges[func] = float(arg)
                self.auto[func] = False
            elif rest == "VOLTAGE:RANGE":
                self.ranges[func] = float(arg)
                self.auto[func] = False
            elif rest in ("RANGE:AUTO", "VOLTAGE:RANGE:AUTO"):
                self.auto[func] = arg in ("ON", "1")
            elif rest == "NPLC":
                assert func in self.nplc, f"NPLC not documented for {func}"
                assert float(arg) in (0.4, 5.0, 20.0), f"invalid NPLC {arg}"
                self.nplc[func] = float(arg)
            elif rest == "RESOLUTION":
                self.resolution[func] = float(arg)
            elif rest == "NULL:STATE":
                self.null_state[func] = arg in ("ON", "1")
            elif rest == "NULL:VALUE":
                self.null_value[func] = float(arg)
            elif rest == "NULL:VALUE:AUTO":
                self.null_auto[func] = arg in ("ON", "1")
                if self.null_auto[func]:
                    self.null_value[func] = float(self.READINGS[func])
            elif rest == "SECONDARY":
                allowed = {
                    "VOLT": {"OFF", "CALCULATE:DATA"}, "CURR": {"OFF", "CALCULATE:DATA"},
                    "RES": {"OFF", "CALCULATE:DATA"}, "FRES": {"OFF", "CALCULATE:DATA"},
                    "CAP": {"OFF", "CALCULATE:DATA"},
                    "VOLT:AC": {"OFF", "CALCULATE:DATA", "FREQUENCY", "PERIOD"},
                    "CURR:AC": {"OFF", "CALCULATE:DATA", "FREQUENCY", "PERIOD"},
                    "FREQ": {"OFF", "CALCULATE:DATA", "VOLTAGE:AC"},
                    "PER": {"OFF", "CALCULATE:DATA", "VOLTAGE:AC"},
                }
                val = arg.strip('"')
                assert val in allowed[func], f"{val} not allowed as secondary for {func}"
                self.secondary[func] = {"CALCULATE:DATA": "CALC:DATA", "FREQUENCY": "FREQ",
                                        "PERIOD": "PER", "VOLTAGE:AC": "VOLT:AC", "OFF": "OFF"}[val]
            else:
                raise AssertionError(f"Unscripted SENSe write: {cmd}")
            return
        if head == "TRIGGER:SOURCE":
            self.trig_source = {"IMMEDIATE": "IMM", "BUS": "BUS", "EXTERNAL": "EXT"}[arg]
        elif head == "TRIGGER:COUNT":
            self.trig_count = int(arg)
        elif head == "SAMPLE:COUNT":
            self.sample_count = int(arg)
        elif head == "CALCULATE:SCALE:FUNCTION":
            self.scale_func = arg
        elif head == "CALCULATE:SCALE:STATE":
            self.scale_state = arg in ("ON", "1")
        elif head.startswith("CALCULATE:SCALE:DB") and head.endswith(":REFERENCE"):
            self.db_ref = float(arg)
        elif head == "CALCULATE:AVERAGE:STATE":
            self.avg_state = arg in ("ON", "1")
        elif c == "CALCULATE:AVERAGE:CLEAR":
            pass
        elif head == "CALCULATE:LIMIT:STATE":
            self.limit_state = arg in ("ON", "1")
        elif head == "CALCULATE:LIMIT:LOWER":
            self.limits[0] = float(arg)
        elif head == "CALCULATE:LIMIT:UPPER":
            self.limits[1] = float(arg)
        elif c == "CALCULATE:LIMIT:CLEAR":
            self.questionable = 0
        elif head == "SYSTEM:BEEPER:STATE":
            self.beeper = "1" if arg in ("ON", "1") else "0"
        elif c == "SYSTEM:BEEPER:IMMEDIATE":
            pass
        elif head == "UNIT:TEMPERATURE":
            self.temp_unit = arg
        elif head == "HCOPY:SDUMP:DATA:FORMAT":
            pass
        else:
            raise AssertionError(f"Unscripted write: {cmd}")

    def query(self, cmd):
        self.queries.append(cmd)
        c = cmd.strip().upper()
        if c == "*IDN?":
            return f"RIGOL TECHNOLOGIES,{self.model},DM8A241234567,00.01.02"
        if c == "SENSE:FUNCTION?":
            return f'"{self.func}"'
        if c == "CONFIGURE?":
            if self.func in self.ranges:
                return f"{self.func} {self.ranges[self.func]:.8E},{self.resolution.get(self.func, 1e-4):.8E}"
            if self.func == "TEMP":
                return f"TEMP {self.config_extra}"
            return self.func
        if c == "READ?":
            assert self.trig_source == "IMM", "READ? would block without an immediate trigger"
            return self.READINGS[self.func]
        if c == "FETCH?":
            return ",".join(self.memory)
        if c == "DATA:POINTS?":
            return str(len(self.memory))
        if c.startswith("DATA:REMOVE? "):
            n = int(c.split()[1].split(",")[0])
            out, self.memory = self.memory[:n], self.memory[n:]
            return ",".join(out)
        if c == "DATA:LAST?":
            return self.memory[-1] if self.memory else self.READINGS[self.func]
        if c == "SENSE:DATA2?":
            sec = self.secondary[self.func]
            return {"FREQ": self.READINGS["FREQ"], "PER": self.READINGS["PER"],
                    "VOLT:AC": self.READINGS["VOLT:AC"], "CALC:DATA": self.READINGS[self.func]}[sec]
        if c.startswith("SENSE:"):
            func, rest = self._root(c[:-1])
            if rest in ("RANGE", "VOLTAGE:RANGE"):
                return f"{self.ranges[func]:.8E}"
            if rest in ("RANGE:AUTO", "VOLTAGE:RANGE:AUTO"):
                return "1" if self.auto[func] else "0"
            if rest == "NPLC":
                return f"{self.nplc[func]:.8E}"
            if rest == "RESOLUTION":
                return f"{self.resolution[func]:.8E}"
            if rest == "NULL:STATE":
                return "1" if self.null_state[func] else "0"
            if rest == "NULL:VALUE":
                return f"{self.null_value[func]:.8E}"
            if rest == "SECONDARY":
                return f'"{self.secondary[func]}"'
            raise AssertionError(f"Unscripted SENSe query: {cmd}")
        if c == "TRIGGER:SOURCE?":
            return self.trig_source
        if c == "TRIGGER:COUNT?":
            return str(self.trig_count)
        if c == "SAMPLE:COUNT?":
            return str(self.sample_count)
        if c == "CALCULATE:SCALE:STATE?":
            return "1" if self.scale_state else "0"
        if c == "CALCULATE:SCALE:FUNCTION?":
            return self.scale_func
        if c.startswith("CALCULATE:SCALE:DB") and c.endswith(":REFERENCE?"):
            return f"{self.db_ref:.8E}"
        if c == "CALCULATE:AVERAGE:STATE?":
            return "1" if self.avg_state else "0"
        if c == "CALCULATE:AVERAGE:MINIMUM?":
            return "4.99000000E+00"
        if c == "CALCULATE:AVERAGE:MAXIMUM?":
            return "5.01000000E+00"
        if c == "CALCULATE:AVERAGE:AVERAGE?":
            return "5.00000000E+00"
        if c == "CALCULATE:AVERAGE:SDEVIATION?":
            return "3.00000000E-03"
        if c == "CALCULATE:AVERAGE:COUNT?":
            return "252"
        if c == "CALCULATE:LIMIT:STATE?":
            return "1" if self.limit_state else "0"
        if c == "STATUS:QUESTIONABLE:CONDITION?":
            return str(self.questionable)
        if c == "SYSTEM:BEEPER:STATE?":
            return self.beeper
        if c == "UNIT:TEMPERATURE?":
            return self.temp_unit
        if c == "SYSTEM:ERROR?":
            return '+0,"No error"'
        if c == "SYSTEM:VERSION?":
            return "1999.0"
        raise AssertionError(f"Unscripted query: {cmd}")


def make_driver(cls, model, resource="USB0::0x1AB1::0x0C94::DM8A241234567::INSTR"):
    inst = ScriptedDM858(model)
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return cls(rm, resource), inst


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_normalize_function_aliases():
    assert normalize_function("VOLT") == "DCV"
    assert normalize_function('"VOLT:AC"') == "ACV"
    assert normalize_function("CURR") == "DCI"
    assert normalize_function("diod") == "DIODE"
    assert normalize_function("TEMP") == "TEMP"
    assert normalize_function("4wr") == "FRES"
    assert normalize_function(MultimeterFunction.CAP) == "CAP"
    with pytest.raises(ValueError):
        normalize_function("LUMINOSITY")


def test_parse_reading_and_block():
    assert parse_reading("4.99987100E+00") == pytest.approx(4.999871)
    assert parse_reading("9.90000000E+37") is None
    assert parse_reading("") is None
    block = parse_readings("-4.98748741E-01,-4.35163427E-01,9.9E37")
    assert block[0] == pytest.approx(-0.498748741) and block[2] is None and len(block) == 3


# --------------------------------------------------------------------------- #
# Identification / model table
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls,model,max_i,cap_max,memory,rate",
    [
        (RigolDM858, "DM858", 10.0, 10e-3, 500_000, 125.0),
        (RigolDM858E, "DM858E", 3.0, 1e-3, 20_000, 80.0),
    ],
)
async def test_identification(cls, model, max_i, cap_max, memory, rate):
    dmm, inst = make_driver(cls, model)
    await dmm.connect()
    assert dmm.connected is True
    info = await dmm.get_info()
    assert info.type == EquipmentType.MULTIMETER
    assert info.id.startswith("dmm_")
    assert info.manufacturer == "RIGOL TECHNOLOGIES"
    assert info.model == model
    assert info.serial_number == "DM8A241234567"
    assert info.connection_type == ConnectionType.USB
    status = await dmm.get_status()
    assert status.connected is True
    assert status.firmware_version == "00.01.02"
    caps = status.capabilities
    assert caps["digits"] == 5.5
    assert caps["function"] == "DCV"
    assert caps["max_current"] == max_i
    assert caps["ranges"]["DCI"][-1] == max_i and caps["ranges"]["ACI"][-1] == max_i
    assert caps["ranges"]["CAP"][-1] == pytest.approx(cap_max)
    assert caps["ranges"]["DCV"] == [0.1, 1.0, 10.0, 100.0, 1000.0]
    assert caps["ranges"]["RES"][-1] == 50e6
    assert caps["memory_points"] == memory
    assert caps["readings_per_second"] == rate
    assert caps["rate_nplc"] == {"FAST": 0.4, "MEDIUM": 5.0, "SLOW": 20.0}
    assert "TEMP" in caps["functions"]
    assert caps["supports_acquisition"] is True


@pytest.mark.asyncio
async def test_idn_picks_model_row():
    """A RigolDM858 instance talking to a DM858E adopts the 3 A row."""
    dmm, inst = make_driver(RigolDM858, "DM858E")
    await dmm.connect()
    assert dmm.RANGES["DCI"][-1] == 3.0
    with pytest.raises(ValueError):
        await dmm.set_range(5.0, function="DCI")  # 5 A exceeds 3 A on the DM858E
    dmm2, _ = make_driver(RigolDM858E, "DM858")
    await dmm2.connect()
    assert dmm2.RANGES["DCI"][-1] == 10.0


# --------------------------------------------------------------------------- #
# Function / range / rate
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_set_function_and_measure():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    reading = await dmm.measure("FRES")
    assert 'SENSe:FUNCtion "FRESistance"' in inst.writes
    assert reading.function == "FRES" and reading.unit == "Ohm"
    assert reading.value == pytest.approx(999.87)
    assert reading.overload is False
    assert reading.range_full_scale == pytest.approx(100e3) and reading.range_index == 3
    assert reading.auto_range is True
    assert reading.rate == "SLOW"
    n = inst.writes.count('SENSe:FUNCtion "FRESistance"')
    await dmm.measure("FRES")
    assert inst.writes.count('SENSe:FUNCtion "FRESistance"') == n  # not re-sent
    assert await dmm.get_function() == "FRES"
    assert await dmm.get_mode() == "FRES"


@pytest.mark.asyncio
async def test_overload_and_temperature():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    res = await dmm.measure("RES")
    assert res.overload is True and res.value is None
    cfg = await dmm.set_temperature_sensor("FRTD", "385")
    assert "CONFigure:TEMPerature FRTD,385" in inst.writes
    assert cfg == "TEMP FRTD,385"
    assert await dmm.set_temperature_unit("F") == "F"
    t = await dmm.measure("TEMP")
    assert t.function == "TEMP" and t.value == pytest.approx(23.15) and t.unit == "degF"
    assert t.range_full_scale is None and t.rate is None
    with pytest.raises(ValueError):
        await dmm.set_temperature_sensor("BIMETAL")
    with pytest.raises(ValueError):
        await dmm.set_temperature_sensor("TCOUPLE", "Z")
    with pytest.raises(ValueError):
        await dmm.set_range(1.0, function="TEMP")


@pytest.mark.asyncio
async def test_set_range_by_value_index_and_keyword():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    await dmm.set_function("DCV")
    rng = await dmm.set_range(100.0)
    assert inst.writes[-1] == "SENSe:VOLTage:DC:RANGe 1.00000000E+02"
    assert rng["index"] == 3 and rng["full_scale"] == 100.0 and rng["auto_range"] is False
    rng = await dmm.set_range(0)
    assert inst.writes[-1] == "SENSe:VOLTage:DC:RANGe 1.00000000E-01"
    assert rng["full_scale"] == pytest.approx(0.1)
    rng = await dmm.set_range(7.5)  # snaps up to the 10 V range
    assert inst.writes[-1] == "SENSe:VOLTage:DC:RANGe 1.00000000E+01"
    rng = await dmm.set_range("AUTO")
    assert "SENSe:VOLTage:DC:RANGe:AUTO ON" in inst.writes
    assert rng["auto_range"] is True
    with pytest.raises(ValueError):
        await dmm.set_range(5000.0)
    # FREQ range is the input voltage range
    rng = await dmm.set_range(1.0, function="FREQ")
    assert "SENSe:FREQuency:VOLTage:RANGe 1.00000000E+00" in inst.writes
    assert rng["unit"] == "Hz" and rng["full_scale"] == 1.0
    with pytest.raises(ValueError):
        await dmm.set_range(1, function="DIODE")


@pytest.mark.asyncio
async def test_rate_maps_to_nplc():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    assert await dmm.set_rate("FAST") == "FAST"
    assert inst.writes[-1] == "SENSe:VOLTage:DC:NPLC 0.4"
    assert await dmm.set_rate("m") == "MEDIUM"
    assert inst.writes[-1] == "SENSe:VOLTage:DC:NPLC 5"
    assert await dmm.set_rate("SLOW", function="FRES") == "SLOW"
    assert inst.writes[-1] == "SENSe:FRESistance:NPLC 20"
    assert await dmm.get_rate("FRES") == "SLOW"
    assert await dmm.set_nplc(5, function="RES") == 5.0
    with pytest.raises(ValueError):
        await dmm.set_nplc(1, function="RES")
    with pytest.raises(ValueError):
        await dmm.set_rate("TURBO")
    with pytest.raises(ValueError):
        await dmm.set_rate("FAST", function="ACV")  # no NPLC on AC functions
    assert await dmm.get_rate("ACV") is None
    assert await dmm.set_resolution(1e-3, function="DCV") == pytest.approx(1e-3)


@pytest.mark.asyncio
async def test_configure_command():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    cfg = await dmm.configure("ACV", range=10, resolution=1e-3)
    assert "CONFigure:VOLTage:AC 1.00000000E+01,1.00000000E-03" in inst.writes
    assert cfg.startswith("VOLT:AC 1.00000000E+01")
    assert await dmm.get_function() == "ACV"
    assert await dmm.configure("CONT") == "CONT"
    assert "CONFigure:CONTinuity" in inst.writes
    with pytest.raises(ValueError):
        await dmm.configure("CONT", range=1)


# --------------------------------------------------------------------------- #
# Trigger / memory / block reads
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_trigger_source_counts_and_memory():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    assert await dmm.set_trigger_source("SINGLE") == "BUS"  # LabLink alias
    assert "TRIGger:SOURce BUS" in inst.writes
    assert await dmm.set_trigger_source("AUTO") == "IMM"
    assert await dmm.set_trigger_source("EXT") == "EXT"
    with pytest.raises(ValueError):
        await dmm.set_trigger_source("TELEPATHY")
    assert await dmm.set_trigger_count(50) == 50
    with pytest.raises(ValueError):
        await dmm.set_trigger_count(1001)
    assert await dmm.set_sample_count(20) == 20
    with pytest.raises(ValueError):
        await dmm.set_sample_count(2001)
    await dmm.set_trigger_source("IMM")
    await dmm.initiate()
    assert await dmm.get_data_points() == 20
    block = await dmm.fetch()
    assert len(block) == 20 and block[0] == pytest.approx(4.999871)
    removed = await dmm.remove_data(5)
    assert len(removed) == 5 and await dmm.get_data_points() == 15
    assert await dmm.get_last_reading() == pytest.approx(4.999871)
    await dmm.trigger()
    assert "*TRG" in inst.writes
    await dmm.abort()
    assert inst.aborted == 1


@pytest.mark.asyncio
async def test_read_samples_uses_bus_trigger_and_restores_source():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    block = await dmm.read_samples(5, function="DCV")
    assert "TRIGger:SOURce BUS" in inst.writes
    assert "SAMPle:COUNt 5" in inst.writes
    assert "INITiate" in inst.writes and "*TRG" in inst.writes
    assert inst.writes[-1] == "TRIGger:SOURce IMMediate"  # restored
    assert inst.sample_count == 1
    assert len(block["values"]) == 5 and block["stats"]["count"] == 5
    assert block["stats"]["mean"] == pytest.approx(4.999871)
    # Interval mode loops over READ?
    n = inst.queries.count("READ?")
    block = await dmm.read_samples(3, interval_s=0.001)
    assert inst.queries.count("READ?") == n + 3
    with pytest.raises(ValueError):
        await dmm.read_samples(0)


# --------------------------------------------------------------------------- #
# Math / statistics / limits / secondary display
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_math_statistics_rel_and_limits():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    assert await dmm.set_math_function("avg") == "AVERAGE"
    assert "CALCulate:AVERage:STATe ON" in inst.writes
    stats = await dmm.get_statistics()
    assert stats == {"min": 4.99, "max": 5.01, "average": 5.0, "std": 0.003, "count": 252.0}
    await dmm.clear_statistics()
    assert "CALCulate:AVERage:CLEar" in inst.writes
    rel = await dmm.set_rel_offset(0.330219)
    assert "SENSe:VOLTage:DC:NULL:VALue 3.30219000E-01" in inst.writes
    assert "SENSe:VOLTage:DC:NULL:STATe ON" in inst.writes
    assert rel == {"offset": pytest.approx(0.330219), "enabled": True}
    assert await dmm.get_math_function() == "REL"
    rel = await dmm.set_rel_offset("CURR")
    assert "SENSe:VOLTage:DC:NULL:VALue:AUTO ON" in inst.writes
    assert rel["offset"] == pytest.approx(4.999871)
    assert await dmm.set_math_function("DBM") == "DBM"
    assert "CALCulate:SCALe:FUNCtion DBM" in inst.writes
    assert await dmm.set_db_reference(50, dbm=True) == 50.0
    assert await dmm.set_math_function("NONE") == "NONE"
    lim = await dmm.set_limits(4.9, 5.1)
    assert "CALCulate:LIMit:LOWer 4.90000000E+00" in inst.writes
    assert "CALCulate:LIMit:UPPer 5.10000000E+00" in inst.writes
    assert lim["enabled"] is True and await dmm.get_math_function() == "PF"
    assert await dmm.get_limit_result() == "PASS"
    inst.questionable = 1 << 12
    assert await dmm.get_limit_result() == "FAIL_HIGH"
    inst.questionable = 1 << 11
    assert await dmm.get_limit_result() == "FAIL_LOW"
    with pytest.raises(ValueError):
        await dmm.set_limits(5, 4)
    with pytest.raises(ValueError):
        await dmm.set_math_function("SQRT")


@pytest.mark.asyncio
async def test_secondary_display():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    await dmm.set_function("ACV")
    assert await dmm.set_secondary_function("FREQ") == "FREQ"
    assert 'SENSe:VOLTage:AC:SECondary "FREQuency"' in inst.writes
    reading = await dmm.measure()
    assert reading.secondary_function == "FREQ"
    assert reading.secondary_value == pytest.approx(1000.012)
    assert reading.secondary_unit == "Hz"
    ch2 = await dmm.get_measurement("CH2")
    assert ch2["value"] == pytest.approx(1000.012) and ch2["unit"] == "Hz"
    assert await dmm.get_secondary_function() == "FREQ"
    await dmm.clear_secondary_function()
    assert 'SENSe:VOLTage:AC:SECondary "OFF"' in inst.writes
    assert await dmm.get_secondary_function() is None
    with pytest.raises(ValueError):
        await dmm.set_secondary_function("DCV")  # not allowed with ACV main
    await dmm.set_function("DCV")
    assert await dmm.set_secondary_function("RAW") == "RAW"
    assert 'SENSe:VOLTage:DC:SECondary "CALCulate:DATA"' in inst.writes
    assert (await dmm.measure()).secondary_unit == "V"
    with pytest.raises(ValueError):
        await dmm.set_secondary_function("FREQ")


# --------------------------------------------------------------------------- #
# Acquisition / dispatch / system
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_measurement_channel_semantics():
    dmm, inst = make_driver(RigolDM858, "DM858")
    await dmm.connect()
    main = await dmm.get_measurement("CH1")
    assert main["function"] == "DCV" and main["value"] == pytest.approx(4.999871)
    dci = await dmm.get_measurement("DCI")
    assert dci["function"] == "DCI" and dci["unit"] == "A"
    res = await dmm.get_measurement("RES")
    assert res["overload"] is True and math.isnan(res["value"])
    temp = await dmm.get_measurement("TEMP")
    assert temp["unit"] == "degC" and temp["value"] == pytest.approx(23.15)
    with pytest.raises(ValueError):
        await dmm.get_measurement("CH2")


@pytest.mark.asyncio
async def test_execute_command_dispatch_state_and_system():
    dmm, inst = make_driver(RigolDM858E, "DM858E")
    await dmm.connect()
    readings = await dmm.execute_command("get_readings", {})
    assert readings.function == "DCV" and readings.unit == "V"
    meas = await dmm.execute_command("get_measurements", {"channel": 1})
    assert meas["DCV"] == pytest.approx(4.999871) and meas["DCV_unit"] == "V"
    assert await dmm.execute_command("set_beeper", {"enabled": False}) is False
    assert "SYSTem:BEEPer:STATe OFF" in inst.writes
    await dmm.execute_command("beep", {})
    assert "SYSTem:BEEPer:IMMediate" in inst.writes
    state = await dmm.execute_command("get_state", {})
    assert state["model"] == "DM858E" and state["function"] == "DCV"
    assert state["trigger_source"] == "IMM" and state["sample_count"] == 1
    assert state["rate"] == "SLOW" and state["math_function"] == "NONE"
    assert state["secondary_function"] is None
    err = await dmm.execute_command("get_error", {})
    assert err["code"] == 0 and err["message"] == "No error"
    assert await dmm.execute_command("get_scpi_version", {}) == "1999.0"
    assert await dmm.execute_command("self_test", {}) is None  # no *TST? documented
    await dmm.execute_command("reset", {})
    assert "*RST" in inst.writes
    with pytest.raises(ValueError):
        await dmm.execute_command("fly_to_the_moon", {})
