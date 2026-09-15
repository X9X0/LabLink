"""Tests for the mock vector network analyzer."""

import math

import numpy as np
import pytest

from server.equipment.mock.mock_vna import MockVNA
from shared.models.data import NetworkAnalyzerData
from shared.models.equipment import EquipmentType


@pytest.fixture
async def vna():
    dev = MockVNA()
    await dev.connect()
    dev.set_noise(0.0)
    yield dev
    await dev.disconnect()


class TestMockVNA:
    @pytest.mark.asyncio
    async def test_connect_info_status(self, vna):
        info = await vna.get_info()
        assert info.type == EquipmentType.VECTOR_NETWORK_ANALYZER
        assert info.id.startswith("vna_")
        assert info.model == "MockVNA-6000" and info.resource_string == "MOCK::VNA::0"
        status = await vna.get_status()
        assert status.connected is True
        caps = status.capabilities
        assert caps["mock"] is True and caps["ports"] == 2 and caps["supports_acquisition"] is True
        assert caps["parameters"] == ["S11", "S12", "S21", "S22"]
        assert caps["sweep"]["points"] == 201

    @pytest.mark.asyncio
    async def test_s11_is_a_50_ohm_match(self, vna):
        trace = await vna.get_trace(1)
        assert isinstance(trace, NetworkAnalyzerData)
        assert trace.parameter == "S11" and trace.format == "MLOG" and trace.unit == "dB"
        assert len(trace.values) == 201 == len(trace.frequencies)
        assert trace.values == pytest.approx([-20.0] * 201, abs=1e-9)
        await vna.set_format(1, "SWR")
        swr = await vna.get_trace(1)
        assert swr.values[0] == pytest.approx(1.1 / 0.9)
        await vna.set_format(1, "smith")
        smith = await vna.get_trace(1)
        assert abs(complex(smith.values[10], smith.secondary_values[10])) == pytest.approx(0.1)
        vna.set_simulated_return_loss(-30.0)
        await vna.set_format(1, "MLOG")
        assert (await vna.get_trace(1)).values[0] == pytest.approx(-30.0)
        with pytest.raises(ValueError):
            vna.set_simulated_return_loss(3.0)

    @pytest.mark.asyncio
    async def test_s21_low_pass_and_cutoff_hook(self, vna):
        await vna.set_sweep(start=1e6, stop=1e9, points=1001)
        s21 = await vna.get_trace(2)
        assert s21.parameter == "S21"
        at_fc = float(np.interp(100e6, s21.frequencies, s21.values))
        assert at_fc == pytest.approx(-3.01, abs=0.05)
        assert s21.values[0] == pytest.approx(0.0, abs=1e-3)
        assert s21.values[-1] < -55  # 3rd order: ~ -60 dB one decade above cutoff
        vna.set_simulated_cutoff(500e6)
        s21 = await vna.get_trace(2)
        assert float(np.interp(500e6, s21.frequencies, s21.values)) == pytest.approx(-3.01, abs=0.05)
        assert float(np.interp(100e6, s21.frequencies, s21.values)) > -0.1
        vna.set_simulated_cutoff(100e6, order=1)
        s21 = await vna.get_trace(2)
        assert s21.values[-1] == pytest.approx(-20.0, abs=0.1)
        with pytest.raises(ValueError):
            vna.set_simulated_cutoff(0)

    @pytest.mark.asyncio
    async def test_sweep_setup_and_limits(self, vna):
        sweep = await vna.set_sweep(start=10e6, stop=2e9, points=401, power=0.0, if_bandwidth=1e4)
        assert sweep["start_frequency"] == 10e6 and sweep["stop_frequency"] == 2e9
        assert sweep["points"] == 401 and sweep["power_dbm"] == 0.0 and sweep["if_bandwidth"] == 1e4
        sweep = await vna.set_center_span(1e9, 200e6)
        assert sweep["start_frequency"] == 900e6 and sweep["stop_frequency"] == 1.1e9
        for bad in ({"start": 1e9, "stop": 1e6}, {"points": 1}, {"power": 20}, {"if_bandwidth": 0.1}):
            with pytest.raises(ValueError):
                await vna.set_sweep(**bad)
        with pytest.raises(ValueError):
            await vna.set_start_stop(1e3, 1e6)  # below 5 kHz
        assert await vna.set_continuous(False) is False
        assert await vna.sweep_single() is True and vna.sweep_count == 1

    @pytest.mark.asyncio
    async def test_parameters_formats_and_traces(self, vna):
        assert await vna.set_parameter(1, "s22") == "S22"
        assert await vna.get_parameter(1) == "S22"
        with pytest.raises(ValueError):
            await vna.set_parameter(1, "S33")
        with pytest.raises(ValueError):
            await vna.set_parameter(5, "S11")  # trace does not exist yet
        traces = await vna.create_trace("S12")
        assert traces[-1] == {"trace": 3, "parameter": "S12", "name": "CH1_S12_3"}
        assert await vna.set_format(3, "phase") == "PHAS"
        phase = await vna.get_trace(3)
        assert phase.unit == "deg" and -180 <= min(phase.values) and max(phase.values) <= 180
        with pytest.raises(ValueError):
            await vna.set_format(3, "SLOG")  # RSA-N only format
        raw = await vna.get_complex_trace(2)
        assert len(raw["real"]) == 201 and raw["parameter"] == "S21"

    @pytest.mark.asyncio
    async def test_markers(self, vna):
        mk = await vna.set_marker(1, frequency=100e6, trace=2)
        assert mk["frequency"] == 100e6 and mk["value"] == pytest.approx(-3.01, abs=0.05) and mk["unit"] == "dB"
        mk = await vna.marker_search(2, "MIN", trace=2)
        assert mk["frequency"] == 1e9 and mk["value"] < -55
        mk = await vna.marker_search(3, "PEAK", trace=2)
        assert mk["frequency"] == 1e6
        with pytest.raises(ValueError):
            await vna.get_marker(9)  # never enabled
        with pytest.raises(ValueError):
            await vna.set_marker(17)

    @pytest.mark.asyncio
    async def test_calibration_flow(self, vna):
        assert await vna.get_correction() is False
        start = await vna.calibrate_start("BASIC", s_param="S11")
        assert start["method"] == "BAS" and start["standards"] == ["OPEN", "SHORT", "LOAD", "THRU"]
        await vna.calibrate_acquire("open")
        await vna.calibrate_acquire("SHORT")
        with pytest.raises(ValueError):
            await vna.calibrate_save()  # LOAD missing
        await vna.calibrate_acquire("LOAD")
        assert await vna.calibrate_save() is True
        assert await vna.get_correction() is True
        assert await vna.set_correction(False) is False
        with pytest.raises(ValueError):
            await vna.calibrate_acquire("OPEN")  # no calibration in progress
        await vna.calibrate_start("RESPONSE")
        assert await vna.calibrate_abort() is True and vna.cal_method is None
        with pytest.raises(ValueError):
            await vna.calibrate_start("WIZARDRY")

    @pytest.mark.asyncio
    async def test_get_measurement_channel_semantics(self, vna):
        s11 = await vna.get_measurement("S11:MIN")
        assert s11["value"] == pytest.approx(-20.0) and s11["parameter"] == "S11" and s11["unit"] == "dB"
        s21 = await vna.get_measurement("S21:MAX")
        assert s21["value"] == pytest.approx(0.0, abs=1e-3) and s21["frequency"] == 1e6
        at = await vna.get_measurement("S21:AT:100e6")
        assert at["value"] == pytest.approx(-3.01, abs=0.05)
        fmin = await vna.get_measurement("S21:MIN_FREQ")
        assert fmin["value"] == 1e9 and fmin["unit"] == "Hz"
        default = await vna.get_measurement("TRACE1:MIN")
        assert default["trace"] == 1 and not math.isnan(default["value"])
        await vna.set_marker(1, frequency=250e6, trace=2)
        mk = await vna.get_measurement("MARKER1")
        assert mk["frequency"] == 250e6 and mk["marker"] == 1
        # S12 has no trace yet: trace 1 is re-defined on demand
        s12 = await vna.get_measurement("S12:MEAN")
        assert s12["parameter"] == "S12" and (await vna.get_parameter(1)) == "S12"
        with pytest.raises(ValueError):
            await vna.get_measurement("S21:MEDIAN")

    @pytest.mark.asyncio
    async def test_execute_command_dispatch_state_reset(self, vna):
        readings = await vna.execute_command("get_readings", {})
        assert isinstance(readings, NetworkAnalyzerData) and readings.trace == 1
        meas = await vna.execute_command("get_measurements", {"channel": 2})
        assert meas["parameter"] == "S21" and meas["max"] == pytest.approx(0.0, abs=1e-3) and meas["points"] == 201
        assert await vna.execute_command("set_rf_output", {"enabled": False}) is False
        assert await vna.execute_command("set_mode", {"mode": "VNA"}) == "VNA"
        state = await vna.execute_command("get_state", {})
        assert state["rf_output"] is False and state["traces"][2]["parameter"] == "S21"
        assert (await vna.execute_command("get_error", {}))["code"] == 0
        assert await vna.execute_command("self_test", {}) is True
        with pytest.raises(ValueError):
            await vna.execute_command("fly_to_the_moon", {})
        await vna.execute_command("set_sweep", {"points": 51})
        await vna.execute_command("reset", {})
        assert (await vna.get_sweep())["points"] == 201 and vna.rf_output is True
        await vna.disconnect()
        with pytest.raises(RuntimeError):
            await vna.execute_command("get_readings", {})
