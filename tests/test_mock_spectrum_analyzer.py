"""Tests for the mock spectrum analyzer (standalone, no equipment manager)."""

import math

import pytest

from server.equipment.mock.mock_spectrum_analyzer import MockSpectrumAnalyzer
from shared.models.data import SpectrumData
from shared.models.equipment import EquipmentType


@pytest.fixture
async def sa():
    mock = MockSpectrumAnalyzer()
    await mock.connect()
    mock.set_noise(0.0)
    yield mock
    await mock.disconnect()


class TestLifecycle:
    async def test_connect_info_status(self, sa):
        info = await sa.get_info()
        assert info.type == EquipmentType.SPECTRUM_ANALYZER
        assert info.id.startswith("sa_")
        assert info.model == "MockSA-815"
        assert info.resource_string == "MOCK::SA::0"
        status = await sa.get_status()
        assert status.connected is True
        caps = status.capabilities
        assert caps["frequency_min"] == 9e3 and caps["frequency_max"] == 1.5e9
        assert caps["has_tracking_generator"] is True
        assert caps["supports_acquisition"] is True
        assert caps["mock"] is True

    async def test_not_connected_raises(self):
        mock = MockSpectrumAnalyzer()
        with pytest.raises(RuntimeError):
            await mock.get_trace()
        with pytest.raises(RuntimeError):
            await mock.set_frequency(center=1e6)
        with pytest.raises(RuntimeError):
            await mock.execute_command("get_readings", {})
        await mock.connect()
        await mock.disconnect()
        with pytest.raises(RuntimeError):
            await mock.get_readings()

    async def test_reset_keeps_signals(self, sa):
        sa.set_simulated_signal(300e6, -30.0)
        await sa.set_frequency(center=1e6, span=1e6)
        await sa.reset()
        assert sa.connected is True
        assert (await sa.get_frequency())["center"] == pytest.approx((9e3 + 1.5e9) / 2)
        assert 300e6 in sa.signals


class TestTrace:
    async def test_default_trace_shows_100mhz_tone(self, sa):
        data = await sa.get_trace(1)
        assert isinstance(data, SpectrumData)
        assert data.num_points == 601 and len(data.values) == 601
        assert data.start_frequency == pytest.approx(9e3)
        assert data.stop_frequency == pytest.approx(1.5e9)
        assert data.peak_amplitude == pytest.approx(-20.0, abs=0.5)
        assert data.peak_frequency == pytest.approx(100e6, abs=data.span / 600)
        assert data.unit == "dBm" and data.detector == "POSITIVE"
        assert data.rbw == 1e6

    async def test_noise_floor_follows_rbw(self, sa):
        sa.clear_simulated_signals()
        wide = await sa.get_trace(1)
        assert min(wide.values) == pytest.approx(-95.0, abs=0.01)  # 1 MHz RBW, 10 dB atten
        await sa.set_rbw(1000)
        narrow = await sa.get_trace(1)
        assert min(narrow.values) == pytest.approx(-125.0, abs=0.01)
        await sa.set_preamp(True)
        assert min((await sa.get_trace(1)).values) == pytest.approx(-135.0, abs=0.01)

    async def test_simulated_signal_and_span(self, sa):
        sa.clear_simulated_signals()
        sa.set_simulated_signal(433.92e6, -35.0)
        await sa.set_frequency(center=433.92e6, span=10e6)
        await sa.set_rbw(100e3)
        await sa.set_sweep(points=1001)
        data = await sa.get_trace(1)
        assert data.num_points == 1001
        assert data.peak_frequency == pytest.approx(433.92e6, abs=10e6 / 1000)
        assert data.peak_amplitude == pytest.approx(-35.0, abs=0.1)
        # Signal outside the span is not visible
        sa.set_simulated_signal(900e6, 0.0)
        data = await sa.get_trace(1)
        assert data.peak_amplitude == pytest.approx(-35.0, abs=0.1)

    async def test_trace_modes_and_units(self, sa):
        assert await sa.set_trace_mode(1, "MAXHOLD") == "MAXHOLD"
        first = await sa.get_trace(1)
        sa.set_simulated_signal(100e6, -40.0)
        held = await sa.get_trace(1)
        assert held.peak_amplitude == pytest.approx(first.peak_amplitude)
        await sa.set_trace_mode(1, "WRITE")
        fresh = await sa.get_trace(1)
        assert fresh.peak_amplitude == pytest.approx(-40.0, abs=0.5)
        assert await sa.set_trace_mode(2, "BLANK") == "BLANK"
        assert (await sa.get_trace(2)).num_points == 0
        assert await sa.set_unit("DBUV") == "dBuV"
        data = await sa.get_trace(1)
        assert data.unit == "dBuV" and data.peak_amplitude == pytest.approx(-40.0 + 106.99, abs=0.5)
        with pytest.raises(ValueError):
            await sa.set_trace_mode(9, "WRITE")

    async def test_readings_alias_and_data_format(self, sa):
        readings = await sa.get_readings()
        assert readings.trace == 1
        assert await sa.set_data_format("REAL,32") == "REAL,32"
        with pytest.raises(ValueError):
            await sa.set_data_format("REAL,64")


class TestSettings:
    async def test_frequency(self, sa):
        f = await sa.set_frequency(center=100e6, span=20e6)
        assert f == {"center": 100e6, "span": 20e6, "start": 90e6, "stop": 110e6}
        f = await sa.set_start_stop(1e6, 3e6)
        assert f["center"] == 2e6 and f["span"] == 2e6
        f = await sa.set_zero_span()
        assert f["span"] == 0.0
        f = await sa.set_full_span()
        assert f["start"] == pytest.approx(9e3) and f["stop"] == pytest.approx(1.5e9)
        with pytest.raises(ValueError):
            await sa.set_frequency(center=2e9)

    async def test_bandwidth_amplitude_sweep(self, sa):
        bw = await sa.set_rbw(2500)
        assert bw["rbw"] == 3000.0 and bw["rbw_auto"] is False  # snapped to 1-3-10
        assert (await sa.set_vbw(100))["vbw"] == 100.0
        with pytest.raises(ValueError):
            await sa.set_rbw(1)
        amp = await sa.set_reference_level(-30)
        assert amp["reference_level"] == -30.0
        amp = await sa.set_attenuation(20)
        assert amp["attenuation"] == 20.0 and amp["attenuation_auto"] is False
        with pytest.raises(ValueError):
            await sa.set_attenuation(40)
        sw = await sa.set_sweep(points=201, time=0.1, continuous=False)
        assert sw == {"points": 201, "time": 0.1, "time_auto": False, "continuous": False}
        assert await sa.single_sweep() is True
        assert sa.sweeps == 1

    async def test_detector_and_average(self, sa):
        assert await sa.set_detector("rms") == "RMS"
        assert await sa.get_detector() == "RMS"
        with pytest.raises(ValueError):
            await sa.set_detector("magic")
        avg = await sa.set_average(10)
        assert avg == {"count": 10, "trace": 1, "enabled": True}
        assert await sa.get_trace_mode(1) == "AVERAGE"

    async def test_tracking_generator(self, sa):
        tg = await sa.set_tracking_generator(True, level=-10)
        assert tg == {"enabled": True, "level": -10.0, "unit": "dBm"}
        with pytest.raises(ValueError):
            await sa.set_tracking_generator(True, level=5)
        assert (await sa.set_output(False))["enabled"] is False
        sa.has_tracking_generator = False
        with pytest.raises(ValueError):
            await sa.get_tracking_generator()
        assert await sa.set_output(False) is None

    async def test_mode_is_swept_only(self, sa):
        assert await sa.get_mode() == "GPSA"
        with pytest.raises(ValueError):
            await sa.set_mode("RTSA")


class TestMarkers:
    async def test_peak_search_and_next(self, sa):
        sa.clear_simulated_signals()
        sa.set_simulated_signal(100e6, -20.0)
        sa.set_simulated_signal(400e6, -50.0)
        await sa.set_rbw(1e6)
        m = await sa.peak_search(1)
        assert m["enabled"] is True
        assert m["frequency"] == pytest.approx(100e6, abs=3e6)
        assert m["amplitude"] == pytest.approx(-20.0, abs=0.5)
        m = await sa.next_peak(1)
        assert m["frequency"] == pytest.approx(400e6, abs=3e6)
        assert m["amplitude"] == pytest.approx(-50.0, abs=0.5)
        m = await sa.next_peak(1, "LEFT")
        assert m["frequency"] == pytest.approx(100e6, abs=3e6)
        f = await sa.marker_to_center(1)
        assert f["center"] == pytest.approx(100e6, abs=3e6)

    async def test_set_get_off(self, sa):
        m = await sa.set_marker(2, frequency=100e6, mode="DELTA")
        assert m["mode"] == "DELTA" and m["frequency"] == 100e6
        assert m["amplitude"] == pytest.approx(-20.0, abs=0.5)
        await sa.marker_off(2)
        assert (await sa.get_marker(2))["enabled"] is False
        await sa.all_markers_off()
        assert all(not mk["enabled"] for mk in sa.markers.values())
        with pytest.raises(ValueError):
            await sa.get_marker(5)
        assert await sa.set_peak_search_mode("PARAMETER") == "PARAMETER"


class TestAcquisition:
    async def test_measurement_channels(self, sa):
        peak = await sa.get_measurement("PEAK")
        assert peak["value"] == pytest.approx(-20.0, abs=0.5) and peak["unit"] == "dBm"
        assert (await sa.get_measurement())["channel"] == "PEAK"
        pf = await sa.get_measurement("PEAK_FREQ")
        assert pf["value"] == pytest.approx(100e6, abs=3e6) and pf["unit"] == "Hz"
        await sa.peak_search(1)
        assert (await sa.get_measurement("MARKER1"))["value"] == pytest.approx(-20.0, abs=0.5)
        assert (await sa.get_measurement("MARKER1_FREQ"))["value"] == pytest.approx(100e6, abs=3e6)
        assert (await sa.get_measurement("TRACE1:MAX"))["value"] == pytest.approx(-20.0, abs=0.5)
        assert (await sa.get_measurement("TRACE1:MIN"))["value"] == pytest.approx(-95.0, abs=0.5)
        mean = (await sa.get_measurement("TRACE1:MEAN"))["value"]
        assert -95.0 < mean < -20.0
        chp = await sa.get_measurement("CHPOWER")
        assert not math.isnan(chp["value"])
        with pytest.raises(ValueError):
            await sa.get_measurement("MARKER9")
        with pytest.raises(ValueError):
            await sa.get_measurement("VOLTAGE")
        stream = await sa.get_measurements(1)
        assert stream["peak"] == pytest.approx(-20.0, abs=0.5) and stream["num_points"] == 601

    async def test_channel_power_of_single_tone(self, sa):
        sa.clear_simulated_signals()
        sa.set_simulated_signal(100e6, -20.0)
        await sa.set_frequency(center=100e6, span=5e6)
        await sa.set_rbw(30e3)
        await sa.set_sweep(points=1001)
        chp = await sa.measure_channel_power(bandwidth=1e6)
        # A CW tone's channel power equals its amplitude within a couple of dB
        assert chp["power"] == pytest.approx(-20.0, abs=2.5)
        assert chp["unit"] == "dBm"
        obw = await sa.measure_obw(99)
        assert 0 < obw["obw"] < 1e6

    async def test_execute_command_dispatch_and_state(self, sa):
        readings = await sa.execute_command("get_readings", {})
        assert isinstance(readings, SpectrumData)
        f = await sa.execute_command("set_frequency", {"center": 100e6, "span": 1e6})
        assert f["span"] == 1e6
        state = await sa.execute_command("get_state", {})
        assert state["frequency"]["center"] == 100e6
        assert state["tracking_generator"]["enabled"] is False
        assert (await sa.execute_command("get_error", {}))["code"] == 0
        with pytest.raises(ValueError):
            await sa.execute_command("fly_to_the_moon", {})
