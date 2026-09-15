"""Tests for the Rigol M300 data acquisition / switch driver.

A scripted fake answers the 34970A-style SCPI documented in the "M300
Programming Guide"; anything unscripted raises so the failing test names
the command the driver sent.
"""

import math
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("..")

from server.equipment.rigol_daq import (RigolM300, expand_channel_list,  # noqa: E402
                                 format_channel_list, normalize_channel,
                                 normalize_function,
                                 parse_channel_list_response, parse_reading)
from shared.models.data import DataAcquisitionData  # noqa: E402
from shared.models.equipment import ConnectionType, EquipmentType  # noqa: E402


class ScriptedM300:
    """M300 with MC3120 in slot 1, MC3324 in slot 2, MC3416 in slot 4."""

    MODULES = {1: "MC3120", 2: "MC3324", 4: "MC3416"}
    # Simulated signals per channel
    SIGNALS = {"101": 1.0785e-1, "102": 2.4886e-3, "103": 9.9e37, "104": 4.0487e-2, "105": 3.3e-3,
               "110": 26.326, "201": 5.5, "221": 0.25}

    def __init__(self, model="M300"):
        self.model = model
        self.session = 1
        self.timeout = 15000
        self.writes = []
        self.queries = []
        self.read_termination = None
        self.write_termination = None
        self.baud_rate = None
        self.scan = []
        self.closed = set()
        self.trig = {"source": "IMM", "count": "+1.00000000E+00", "timer": "+0.000000000E+00"}
        self.config = {}
        self.temp_unit = {}
        self.formats = {}
        self.memory = []

    def close(self):
        pass

    def _chans(self, text):
        return expand_channel_list(text)

    def write(self, cmd):
        self.writes.append(cmd)
        c = cmd.strip()
        u = c.upper()
        head, _, arg = u.partition(" ")
        if head.startswith("FORMAT:READING:"):
            self.formats[head] = arg
        elif head == "ROUTE:SCAN":
            self.scan = sorted(self._chans(arg), key=int)
        elif head == "ROUTE:CLOSE":
            for ch in self._chans(arg):
                if ch in self.scan:
                    raise RuntimeError("channel in scan list")
                self.closed.add(ch)
        elif head == "ROUTE:OPEN":
            for ch in self._chans(arg):
                self.closed.discard(ch)
        elif head.startswith("CONFIGURE:"):
            func = head[len("CONFIGURE:"):]
            params, _, chlist = arg.rpartition("(")
            chans = self._chans("(" + chlist)
            for ch in chans:
                self.config[ch] = (func, params.rstrip(","))
            self.scan = sorted(chans, key=int)  # CONFigure overwrites the scan list
        elif head == "TRIGGER:SOURCE":
            self.trig["source"] = arg[:3] if not arg.startswith("ALAR") else arg[:5]
        elif head == "TRIGGER:COUNT":
            self.trig["count"] = "9.90000200E+37" if arg.startswith("INF") else f"{float(arg):+.8E}"
        elif head == "TRIGGER:TIMER":
            self.trig["timer"] = f"{float(arg):+.9E}"
        elif head == "UNIT:TEMPERATURE":
            unit, _, chlist = arg.partition(",")
            for ch in (self._chans(chlist) if chlist else self.scan):
                if self.config.get(ch, ("",))[0] != "TEMPERATURE":
                    raise RuntimeError("not a temperature channel")
                self.temp_unit[ch] = unit
        elif head in ("INITIATE", "ABORT", "*TRG", "*RST", "INSTRUMENT:DMM"):
            if head == "*RST":
                self.scan = []
                self.config = {}
        else:
            raise AssertionError(f"Unscripted write: {cmd}")

    def _reading(self, ch):
        v = self.SIGNALS.get(ch, 0.0)
        if self.config.get(ch, ("",))[0] == "TEMPERATURE" and self.temp_unit.get(ch) == "F":
            v = v * 9 / 5 + 32
        return f"{v:+.9E}"

    def query(self, cmd):
        self.queries.append(cmd)
        u = cmd.strip().upper()
        if u == "*IDN?":
            return f"RIGOL TECHNOLOGIES,{self.model},M300123123123,07.08.00.01.00.00.17"
        if u.startswith("SYSTEM:CTYPE? "):
            slot = int(u.split()[1]) // 100
            model = self.MODULES.get(slot)
            return f"RIGOL TECHNOLOGIES,{model},MM3D00000000{slot},00.01.01.01" if model else "RIGOL TECHNOLOGIES,0,0,0"
        if u == "INSTRUMENT:DMM:INSTALLED?":
            return "1"
        if u == "INSTRUMENT:DMM?":
            return "1"
        if u == "ROUTE:SCAN?":
            body = f"(@{','.join(self.scan)})"
            return f"#2{len(body):02d}{body}"
        if u in ("READ?", "FETCH?"):
            if not self.scan:
                raise RuntimeError("scan list empty")
            self.memory = [self._reading(ch) for ch in self.scan]
            return ",".join(self.memory)
        if u.startswith("ROUTE:CLOSE? "):
            return ",".join("1" if ch in self.closed else "0" for ch in self._chans(u.split(" ", 1)[1]))
        if u == "TRIGGER:SOURCE?":
            return self.trig["source"]
        if u == "TRIGGER:COUNT?":
            return self.trig["count"]
        if u == "TRIGGER:TIMER?":
            return self.trig["timer"]
        if u.startswith("CONFIGURE? "):
            out = []
            for ch in self._chans(u.split(" ", 1)[1]):
                func, params = self.config.get(ch, ("VOLTAGE:DC", "AUTO"))
                if func == "TEMPERATURE":
                    probe, stype = params.split(",")[:2]
                    out.append(f'"TEMP {probe},{stype}"')
                else:
                    short = {"VOLTAGE:DC": "VOLT", "VOLTAGE:AC": "VOLT:AC", "RESISTANCE": "RES",
                             "FRESISTANCE": "FRES", "CURRENT:DC": "CURR", "FREQUENCY": "FREQ"}[func]
                    rng = params.split(",")[0] if params and params != "AUTO" else "2.000000E+01"
                    out.append(f'"{short} {float(rng):+.6E},+6.000000E-06"')
            return ",".join(out)
        if u == "DATA:POINTS?":
            return f"+{len(self.memory)}"
        if u.startswith("DATA:REMOVE? "):
            n = int(u.split()[1])
            out, self.memory = self.memory[:n], self.memory[n:]
            return ",".join(out)
        if u == "SYSTEM:ERROR?":
            return '+0,"No error"'
        raise AssertionError(f"Unscripted query: {cmd}")


def make_driver(resource="USB0::0x1AB1::0x0C80::M300123123123::INSTR"):
    inst = ScriptedM300()
    rm = MagicMock()
    rm.open_resource = MagicMock(return_value=inst)
    return RigolM300(rm, resource), inst


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_channel_list_helpers():
    assert format_channel_list(["101", "102"]) == "(@101,102)"
    assert format_channel_list("101:110") == "(@101:110)"
    assert format_channel_list([101, 102, 103, 301]) == "(@101:103,301)"
    assert format_channel_list("(@101:103,301,406:408)") == "(@101:103,301,406:408)"
    assert expand_channel_list("101:103,301") == ["101", "102", "103", "301"]
    assert expand_channel_list(["CH101", "@102", 103]) == ["101", "102", "103"]
    assert parse_channel_list_response("#214(@203,204,205)") == ["203", "204", "205"]
    assert parse_channel_list_response("#210(@)") == []
    assert normalize_channel(" ch205 ") == "205"
    with pytest.raises(ValueError):
        normalize_channel("601")  # slot 6 does not exist
    with pytest.raises(ValueError):
        normalize_channel("1")
    with pytest.raises(ValueError):
        expand_channel_list("101:205")  # range across slots
    assert normalize_function("volt:dc") == "DCV" and normalize_function("4WR") == "FRES"
    assert normalize_function("temperature") == "TEMP"
    with pytest.raises(ValueError):
        normalize_function("PRESSURE")
    assert parse_reading("+1.078752633E-01") == pytest.approx(0.1078752633)
    assert parse_reading("+9.90000000E+37") is None
    assert parse_reading('+2.63260000E+01 C') == pytest.approx(26.326)


# --------------------------------------------------------------------------- #
# Identification / modules
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_identification_and_modules():
    daq, inst = make_driver()
    await daq.connect()
    assert daq.connected is True
    info = await daq.get_info()
    assert info.type == EquipmentType.DATA_ACQUISITION
    assert info.id.startswith("daq_")
    assert info.manufacturer == "RIGOL TECHNOLOGIES" and info.model == "M300"
    assert info.serial_number == "M300123123123"
    assert info.connection_type == ConnectionType.USB
    # connect configures plain numeric readings and inventories the slots
    assert "FORMat:READing:UNIT OFF" in inst.writes and "FORMat:READing:CHANnel OFF" in inst.writes
    assert "SYSTem:CTYPe? 100" in inst.queries and "SYSTem:CTYPe? 500" in inst.queries
    modules = await daq.get_modules()
    assert set(modules) == {1, 2, 4}
    assert modules[1]["model"] == "MC3120" and modules[1]["channels"] == 20 and modules[1]["kind"] == "mux"
    assert modules[2]["model"] == "MC3324" and "DCI" in modules[2]["functions"]
    assert modules[4]["model"] == "MC3416" and modules[4]["kind"] == "actuator"
    status = await daq.get_status()
    caps = status.capabilities
    assert status.firmware_version == "07.08.00.01.00.00.17"
    assert caps["slots"] == [1, 2, 3, 4, 5] and caps["modules"]["1"]["model"] == "MC3120"
    assert caps["dmm_installed"] is True and "TEMP" in caps["functions"]
    assert caps["supports_acquisition"] is True


@pytest.mark.asyncio
async def test_serial_connection_configures_port():
    daq, inst = make_driver(resource="ASRL/dev/ttyUSB1::INSTR")
    await daq.connect()
    assert inst.baud_rate == 9600 and inst.data_bits == 8
    assert (await daq.get_info()).connection_type == ConnectionType.SERIAL


# --------------------------------------------------------------------------- #
# Configuration / scan list / scanning
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_configure_channel_builds_commands_and_restores_scan_list():
    daq, inst = make_driver()
    await daq.connect()
    assert await daq.set_scan_list("101:105") == ["101", "102", "103", "104", "105"]
    assert "ROUTe:SCAN (@101:105)" in inst.writes
    cfg = await daq.configure_channel("101:104", "DCV", range=20, resolution="DEF")
    assert "CONFigure:VOLTage:DC 20,DEF,(@101:104)" in inst.writes
    assert cfg["function"] == "DCV" and cfg["unit"] == "V" and cfg["channels"] == ["101", "102", "103", "104"]
    # CONFigure overwrote the scan list with (@101:104); the driver put ours back
    assert inst.writes[-1] == "ROUTe:SCAN (@101:105)" and inst.scan == ["101", "102", "103", "104", "105"]
    await daq.configure_channel("105", "RES")
    assert "CONFigure:RESistance (@105)" in inst.writes
    await daq.configure_channel(["110"], "TEMP", sensor="TC", sensor_type="K")
    assert "CONFigure:TEMPerature TCouple,K,1,DEF,(@110)" in inst.writes
    await daq.configure_channel("201", "ACV", resolution=0.001)
    assert "CONFigure:VOLTage:AC AUTO,0.001,(@201)" in inst.writes
    await daq.configure_channel("221", "DCI", range=1)
    assert "CONFigure:CURRent:DC 1,(@221)" in inst.writes
    with pytest.raises(ValueError):
        await daq.configure_channel("201", "DCI")  # MC3324 current only on 21..24
    with pytest.raises(ValueError):
        await daq.configure_channel("101", "DCI")  # MC3120 has no current channels
    with pytest.raises(ValueError):
        await daq.configure_channel("115", "FRES")  # 4-wire uses 1..10 on an MC3120
    with pytest.raises(ValueError):
        await daq.configure_channel("401", "DCV")  # actuator, not a multiplexer
    with pytest.raises(ValueError):
        await daq.configure_channel("110", "TEMP", sensor="TC", sensor_type="Q")


@pytest.mark.asyncio
async def test_scan_maps_readings_in_ascending_order_and_flags_overload():
    daq, inst = make_driver()
    await daq.connect()
    await daq.configure_channel("101:105", "DCV")
    await daq.set_scan_list(["105", "103", "101", "102", "104"])  # order is irrelevant
    assert await daq.get_scan_list() == ["101", "102", "103", "104", "105"]
    data = await daq.scan()
    assert isinstance(data, DataAcquisitionData)
    assert "READ?" in inst.queries
    assert data.scan_list == ["101", "102", "103", "104", "105"]
    assert data.readings["101"] == pytest.approx(0.10785)
    assert data.readings["102"] == pytest.approx(2.4886e-3)
    assert math.isnan(data.readings["103"])  # +9.9E+37 overload
    assert data.units["101"] == "V" and data.functions["104"] == "DCV"
    assert data.installed_modules == {"1": "MC3120", "2": "MC3324", "4": "MC3416"}
    # get_readings returns the cached scan without talking to the instrument
    n = inst.queries.count("READ?")
    assert (await daq.get_readings()) is data
    assert inst.queries.count("READ?") == n
    pending = await daq.scan(wait=False)
    assert "INITiate" in inst.writes and pending.readings == {}
    fetched = await daq.fetch()
    assert "FETCh?" in inst.queries and fetched.readings["101"] == pytest.approx(0.10785)
    assert await daq.get_data_points() == 5
    assert await daq.remove_data(2) == pytest.approx([0.10785, 2.4886e-3])


@pytest.mark.asyncio
async def test_temperature_units_and_read_channel():
    daq, inst = make_driver()
    await daq.connect()
    await daq.set_scan_list("101:102")
    await daq.configure_channel("110", "TEMP", sensor="TC", sensor_type="K")
    single = await daq.read_channel("110")
    assert single["value"] == pytest.approx(26.326) and single["unit"] == "C" and single["function"] == "TEMP"
    # read_channel temporarily scanned (@110) and restored the scan list
    assert "ROUTe:SCAN (@110)" in inst.writes and inst.writes[-1] == "ROUTe:SCAN (@101,102)"
    assert await daq.set_temperature_unit("F", "110") == "F"
    assert "UNIT:TEMPerature F,(@110)" in inst.writes
    single = await daq.read_channel(110)
    assert single["unit"] == "F" and single["value"] == pytest.approx(26.326 * 9 / 5 + 32)
    with pytest.raises(ValueError):
        await daq.set_temperature_unit("R", "110")
    cfg = await daq.get_configuration("101,110")
    assert cfg["101"]["function"] == "DCV" and cfg["101"]["range"] == 20.0
    assert cfg["110"]["function"] == "TEMP" and cfg["110"]["sensor"] == "TCOUPLE" and cfg["110"]["unit"] == "F"


# --------------------------------------------------------------------------- #
# Switching / trigger
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_switch_channels():
    daq, inst = make_driver()
    await daq.connect()
    await daq.set_scan_list("101:103")
    closed = await daq.close_channel("401:403")
    assert "ROUTe:CLOSe (@401:403)" in inst.writes
    assert closed == {"401": True, "402": True, "403": True}
    assert await daq.get_closed_channels() == ["401", "402", "403"]
    opened = await daq.open_channel(["402"])
    assert "ROUTe:OPEN (@402)" in inst.writes and opened == {"402": False}
    assert await daq.get_closed_channels("401:405") == ["401", "403"]
    await daq.close_channel("110")  # multiplexer relay outside the scan list is fine
    with pytest.raises(ValueError):
        await daq.close_channel("102")  # in the scan list


@pytest.mark.asyncio
async def test_trigger_configuration():
    daq, inst = make_driver()
    await daq.connect()
    trig = await daq.set_trigger("TIMER", count=10, interval=2.5)
    assert "TRIGger:SOURce TIMer" in inst.writes and "TRIGger:COUNt 10" in inst.writes
    assert "TRIGger:TIMer 2.5" in inst.writes
    assert trig == {"source": "TIM", "count": 10, "interval": 2.5}
    trig = await daq.set_trigger("BUS", count="INFINITY")
    assert "TRIGger:COUNt INFinity" in inst.writes and trig["count"] == "INFINITY" and trig["source"] == "BUS"
    await daq.trigger()
    assert "*TRG" in inst.writes
    await daq.abort()
    assert "ABORt" in inst.writes
    with pytest.raises(ValueError):
        await daq.set_trigger("LASER")
    with pytest.raises(ValueError):
        await daq.set_trigger("IMM", count=60000)


# --------------------------------------------------------------------------- #
# Acquisition hook / dispatch / state
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_measurement_shares_one_scan_per_cycle():
    daq, inst = make_driver()
    await daq.connect()
    await daq.configure_channel("101:103", "DCV")
    await daq.set_scan_list("101:103")
    m1 = await daq.get_measurement("101")
    m2 = await daq.get_measurement("CH102")
    m3 = await daq.get_measurement("@103")
    assert inst.queries.count("READ?") == 1
    assert m1["value"] == pytest.approx(0.10785) and m1["unit"] == "V" and m1["channel"] == "101"
    assert m2["value"] == pytest.approx(2.4886e-3)
    assert math.isnan(m3["value"]) and m3["overload"] is True
    await daq.get_measurement("101")  # second polling cycle -> new scan
    assert inst.queries.count("READ?") == 2
    other = await daq.get_measurement("110")  # not in the scan list -> individual read
    assert other["value"] == pytest.approx(26.326) and inst.queries.count("READ?") == 3
    assert inst.writes[-1] == "ROUTe:SCAN (@101:103)"


@pytest.mark.asyncio
async def test_execute_command_dispatch_state_and_reset():
    daq, inst = make_driver()
    await daq.connect()
    await daq.execute_command("configure_channel", {"channel": "101:102", "function": "DCV", "range": 2})
    assert await daq.execute_command("set_scan_list", {"channels": "101:102"}) == ["101", "102"]
    readings = await daq.execute_command("get_readings", {})
    assert isinstance(readings, DataAcquisitionData) and set(readings.readings) == {"101", "102"}
    meas = await daq.execute_command("get_measurements", {"channel": 1})
    assert meas["101"] == pytest.approx(0.10785) and meas["101_unit"] == "V"
    state = await daq.execute_command("get_state", {})
    assert state["scan_list"] == ["101", "102"] and state["channels"]["101"]["function"] == "DCV"
    assert state["trigger"]["source"] == "IMM" and state["modules"]["4"] == "MC3416"
    assert (await daq.execute_command("get_error", {}))["code"] == 0
    with pytest.raises(ValueError):
        await daq.execute_command("teleport", {})
    await daq.execute_command("reset", {})
    assert "*RST" in inst.writes
    assert await daq.get_scan_list() == []
    with pytest.raises(ValueError):
        await daq.scan()  # scan list empty after reset
