"""Tests for the mock function / arbitrary waveform generator."""

import math

import pytest

from server.equipment.mock.mock_function_generator import MockFunctionGenerator
from shared.models.data import FunctionGeneratorData
from shared.models.equipment import EquipmentType


@pytest.fixture
async def fgen():
    gen = MockFunctionGenerator()
    await gen.connect()
    yield gen
    await gen.disconnect()


class TestMockFunctionGeneratorStandalone:
    @pytest.mark.asyncio
    async def test_connect_info_status(self, fgen):
        info = await fgen.get_info()
        assert info.type == EquipmentType.FUNCTION_GENERATOR
        assert info.id.startswith("fgen_")
        assert info.model == "MockFGEN-1062Z"
        assert info.resource_string == "MOCK::FGEN::0"
        status = await fgen.get_status()
        assert status.connected is True
        caps = status.capabilities
        assert caps["channels"] == 2
        assert caps["mock"] is True
        assert caps["has_counter"] is True
        assert caps["supports_acquisition"] is True
        assert caps["outputs"] == {1: False, 2: False}

    @pytest.mark.asyncio
    async def test_not_connected_raises(self):
        gen = MockFunctionGenerator()
        with pytest.raises(RuntimeError):
            await gen.execute_command("get_readings", {"channel": 1})
        with pytest.raises(RuntimeError):
            await gen.get_readings(1)
        with pytest.raises(RuntimeError):
            await gen.set_output(True, 1)
        with pytest.raises(RuntimeError):
            await gen.get_counter()

    @pytest.mark.asyncio
    async def test_default_state_matches_rigol_power_on(self, fgen):
        data = await fgen.get_readings(1)
        assert isinstance(data, FunctionGeneratorData)
        assert data.waveform == "SIN"
        assert data.frequency == 1000.0
        assert data.amplitude == 5.0
        assert data.amplitude_unit == "VPP"
        assert data.offset == 0.0
        assert data.phase == 0.0
        assert data.output_enabled is False
        assert data.load_impedance == "50"
        assert data.modulation is None
        assert data.sweep_enabled is False and data.burst_enabled is False

    @pytest.mark.asyncio
    async def test_apply_and_readings(self, fgen):
        data = await fgen.apply(channel=2, waveform="square", frequency=2e3, amplitude=1.0, offset=0.5, phase=90)
        assert data.channel == 2
        assert data.waveform == "SQU"
        assert data.frequency == 2000.0
        assert data.amplitude == 1.0
        assert data.offset == 0.5
        assert data.phase == 90.0
        assert data.duty_cycle == 50.0
        # Channel 1 is untouched
        assert (await fgen.get_readings(1)).waveform == "SIN"
        dc = await fgen.apply(channel=1, waveform="DC", offset=1.2)
        assert dc.waveform == "DC" and dc.frequency is None and dc.offset == 1.2
        ramp = await fgen.apply(channel=1, waveform="ramp", frequency=100)
        assert ramp.symmetry == 50.0

    @pytest.mark.asyncio
    async def test_setters_are_deterministic(self, fgen):
        assert await fgen.set_waveform("pulse", channel=1) == "PULS"
        assert await fgen.set_frequency(1e6, channel=1) == 1e6
        assert await fgen.set_amplitude(2.5, channel=1) == 2.5
        assert await fgen.set_offset(0.25, channel=1) == 0.25
        assert await fgen.set_phase(-45, channel=1) == -45.0
        assert await fgen.set_duty_cycle(20, channel=1) == 20.0
        pulse = await fgen.get_pulse(1)
        assert pulse["duty_cycle"] == 20.0
        assert pulse["width"] == pytest.approx(0.2e-6)
        assert await fgen.set_symmetry(30, channel=1) == 30.0
        assert await fgen.set_output(True, channel=1) is True
        assert await fgen.get_output(1) is True
        assert await fgen.set_load("HighZ", channel=1) == "INF"
        assert await fgen.set_load(600, channel=1) == "600"
        assert await fgen.set_polarity("inv", channel=1) == "INVERTED"
        readings = await fgen.get_readings(1)
        assert readings.waveform == "PULS" and readings.duty_cycle == 20.0
        assert readings.output_enabled is True and readings.load_impedance == "600"

    @pytest.mark.asyncio
    async def test_amplitude_unit_conversion(self, fgen):
        await fgen.set_amplitude(2.0, channel=1)
        assert await fgen.set_amplitude_unit("VRMS", channel=1) == "VRMS"
        assert await fgen.get_amplitude(1) == pytest.approx(2.0 / (2 * math.sqrt(2)))
        assert await fgen.set_amplitude_unit("VPP", channel=1) == "VPP"
        assert await fgen.get_amplitude(1) == pytest.approx(2.0)
        await fgen.set_load("INF", channel=1)
        with pytest.raises(ValueError):
            await fgen.set_amplitude_unit("DBM", channel=1)

    @pytest.mark.asyncio
    async def test_limits_are_enforced(self, fgen):
        with pytest.raises(ValueError):
            await fgen.apply(waveform="SIN", frequency=61e6)
        with pytest.raises(ValueError):
            await fgen.apply(waveform="RAMP", frequency=2e6)
        with pytest.raises(ValueError):
            await fgen.apply(waveform="SIN", frequency=1e6, amplitude=11.0)
        with pytest.raises(ValueError):
            await fgen.apply(waveform="SIN", frequency=50e6, amplitude=3.0)
        await fgen.set_load("INF")
        await fgen.apply(waveform="SIN", frequency=1e6, amplitude=20.0)
        with pytest.raises(ValueError):
            await fgen.set_offset(11.0)
        with pytest.raises(ValueError):
            await fgen.set_phase(361)
        with pytest.raises(ValueError):
            await fgen.set_load(20000)
        with pytest.raises(ValueError):
            await fgen.set_frequency(1e3, channel=3)
        with pytest.raises(ValueError):
            await fgen.set_duty_cycle(150)

    @pytest.mark.asyncio
    async def test_modulation_sweep_burst_state(self, fgen):
        mod = await fgen.set_modulation(True, "AM", depth=50, frequency=200)
        assert mod == {"enabled": True, "type": "AM", "frequency": 200.0, "depth": 50.0}
        assert (await fgen.get_readings(1)).modulation == "AM"
        sweep = await fgen.set_sweep(True, start=1e3, stop=1e4, time=2, spacing="log")
        assert sweep["enabled"] is True and sweep["spacing"] == "LOG"
        # Sweep on switches modulation off (as the instrument does)
        assert (await fgen.get_modulation())["enabled"] is False
        readings = await fgen.get_readings(1)
        assert readings.sweep_enabled is True and readings.modulation is None
        burst = await fgen.set_burst(True, mode="ncycle", cycles=5, period=0.02, phase=10, channel=2)
        assert burst == {"enabled": True, "mode": "TRIG", "cycles": 5, "period": 0.02, "phase": 10.0}
        assert (await fgen.get_readings(2)).burst_enabled is True
        await fgen.trigger_burst(2)
        assert fgen.burst_trigger_count == 1
        fm = await fgen.set_modulation(True, "FM", deviation=500, channel=2)
        assert fm["deviation"] == 500.0
        assert (await fgen.get_burst(2))["enabled"] is False
        with pytest.raises(ValueError):
            await fgen.set_modulation(True, "AM", depth=200)
        with pytest.raises(ValueError):
            await fgen.set_burst(True, mode="SIDEWAYS")

    @pytest.mark.asyncio
    async def test_arbitrary_upload_and_phase_sync(self, fgen):
        points = [math.sin(2 * math.pi * i / 64) for i in range(64)]
        result = await fgen.upload_arbitrary(points, channel=2)
        assert result["points"] == 64 and result["channel"] == 2
        assert fgen.channels[2]["arb_points"] == pytest.approx(points)
        assert (await fgen.get_readings(2)).waveform == "ARB"
        clipped = await fgen.upload_arbitrary([2.0] * 8, channel=1)
        assert clipped["points"] == 8 and fgen.channels[1]["arb_points"] == [1.0] * 8
        with pytest.raises(ValueError):
            await fgen.upload_arbitrary([0.0] * 4)
        assert await fgen.set_arb_sample_rate(1e6, channel=2) == 1e6
        await fgen.sync_phase(1)
        assert fgen.phase_sync_count == 1
        await fgen.set_modulation(True, "AM", channel=1)
        with pytest.raises(ValueError):
            await fgen.sync_phase(1)

    @pytest.mark.asyncio
    async def test_counter_and_acquisition_hook(self, fgen):
        counter = await fgen.get_counter()
        assert counter["enabled"] is False and math.isnan(counter["frequency"])
        assert await fgen.set_counter(True) is True
        fgen.set_simulated_counter(12345.0, duty_cycle=25.0)
        counter = await fgen.get_counter()
        assert counter["frequency"] == 12345.0
        assert counter["period"] == pytest.approx(1 / 12345.0)
        assert counter["duty_cycle"] == 25.0
        assert counter["positive_width"] == pytest.approx(0.25 / 12345.0)

        m = await fgen.get_measurement("COUNTER")
        assert m["value"] == 12345.0 and m["unit"] == "Hz"
        m = await fgen.get_measurement("COUNTER:DUTY")
        assert m["value"] == 25.0 and m["unit"] == "%"
        await fgen.apply(channel=1, waveform="SIN", frequency=777.0, amplitude=1.5, offset=0.2, phase=30)
        assert (await fgen.get_measurement("CH1:FREQ"))["value"] == 777.0
        assert (await fgen.get_measurement("1"))["value"] == 777.0
        m = await fgen.get_measurement("CH1:AMPL")
        assert m["value"] == 1.5 and m["unit"] == "VPP"
        assert (await fgen.get_measurement("CH1:OFFS"))["value"] == 0.2
        assert (await fgen.get_measurement("CH1:PHASE"))["value"] == 30.0
        assert (await fgen.get_measurement("CH1:OUTPUT"))["value"] == 0.0
        with pytest.raises(ValueError):
            await fgen.get_measurement("CH1:NOPE")
        streams = await fgen.get_measurements(1)
        assert streams["frequency"] == 777.0 and streams["counter_frequency"] == 12345.0

    @pytest.mark.asyncio
    async def test_execute_command_dispatch(self, fgen):
        data = await fgen.execute_command("apply", {"channel": 1, "waveform": "SQU", "frequency": 100})
        assert isinstance(data, FunctionGeneratorData) and data.waveform == "SQU"
        assert await fgen.execute_command("set_output", {"enabled": True, "channel": 1}) is True
        assert (await fgen.execute_command("get_readings", {"channel": 1})).output_enabled is True
        assert (await fgen.execute_command("get_measurement", {"channel": "CH1:FREQ"}))["value"] == 100.0
        state = await fgen.execute_command("get_state", {})
        assert state["channels"][1]["waveform"] == "SQU" and state["channels"][1]["output"] is True
        assert (await fgen.execute_command("get_error", {}))["code"] == 0
        assert await fgen.execute_command("set_beeper", {"enabled": False}) is False
        with pytest.raises(ValueError, match="Unknown command"):
            await fgen.execute_command("levitate", {})

    @pytest.mark.asyncio
    async def test_reset_restores_defaults(self, fgen):
        await fgen.apply(channel=1, waveform="SQU", frequency=5e3, amplitude=2.0)
        await fgen.set_output(True, 1)
        await fgen.set_counter(True)
        await fgen.reset()
        data = await fgen.get_readings(1)
        assert data.waveform == "SIN" and data.frequency == 1000.0 and data.amplitude == 5.0
        assert data.output_enabled is False
        assert fgen.counter_enabled is False
        assert fgen.connected is True

    @pytest.mark.asyncio
    async def test_set_output_for_disconnect_safety(self, fgen):
        await fgen.set_output(True, channel=1)
        await fgen.set_output(True, channel=2)
        assert hasattr(fgen, "set_output") and not hasattr(fgen, "set_input")
        assert await fgen.set_output(False, channel=1) is False
        assert await fgen.set_output(False, channel=2) is False
        assert (await fgen.get_status()).capabilities["outputs"] == {1: False, 2: False}
