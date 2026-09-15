"""Tests for the mock RF signal generator."""

import sys

import pytest

sys.path.append("..")

from equipment.mock.mock_rf_generator import MockRFGenerator  # noqa: E402
from shared.models.data import RFGeneratorData  # noqa: E402
from shared.models.equipment import EquipmentType  # noqa: E402


@pytest.fixture
async def gen():
    g = MockRFGenerator(None, "MOCK::RFGEN::0")
    await g.connect()
    yield g
    await g.disconnect()


@pytest.mark.asyncio
async def test_identity(gen):
    info = await gen.get_info()
    assert info.type == EquipmentType.RF_SIGNAL_GENERATOR
    assert info.id.startswith("rfgen_")
    assert info.model == "MockRFGEN-830"
    assert info.resource_string == "MOCK::RFGEN::0"
    status = await gen.get_status()
    assert status.connected is True
    assert status.capabilities["mock"] is True
    assert status.capabilities["frequency_max"] == 3e9
    assert status.capabilities["supports_acquisition"] is True
    assert "AM" in status.capabilities["modulation_types"]


@pytest.mark.asyncio
async def test_frequency_level_output(gen):
    assert await gen.set_frequency(1e9) == 1e9
    assert await gen.get_frequency() == 1e9
    with pytest.raises(ValueError):
        await gen.set_frequency(4e9)
    with pytest.raises(ValueError):
        await gen.set_frequency(1.0)
    assert await gen.set_level(-20) == -20.0
    assert await gen.set_level(48.99, unit="dBmV") == pytest.approx(2.0, abs=0.01)
    with pytest.raises(ValueError):
        await gen.set_level(25)
    with pytest.raises(ValueError):
        await gen.set_level(1, unit="parsecs")
    assert await gen.set_level_unit("V") == "V"
    assert await gen.get_level_unit() == "V"
    assert await gen.set_output(True) is True
    assert await gen.get_output() is True
    assert await gen.set_output(False) is False
    with pytest.raises(ValueError):
        await gen.set_frequency(1e9, channel=2)


@pytest.mark.asyncio
async def test_modulation(gen):
    am = await gen.set_modulation("AM", True, depth=40, frequency=1e3, waveform="square")
    assert am["enabled"] is True and am["depth"] == 40.0 and am["waveform"] == "SQUA"
    assert await gen.get_modulation_master() is True
    fm = await gen.set_modulation("fm", True, deviation=5e3, source="EXT")
    assert fm["deviation"] == 5e3 and fm["source"] == "EXT"
    pulse = await gen.set_modulation("PULSE", True, period=1e-3, width=100e-6, polarity="INV")
    assert pulse["polarity"] == "INVERSE" and pulse["width"] == 100e-6
    iq = await gen.set_modulation("IQ", True)
    assert iq["enabled"] is True
    with pytest.raises(ValueError):
        await gen.set_modulation("AM", True, depth=101)
    with pytest.raises(ValueError):
        await gen.set_modulation("SSB", True)
    with pytest.raises(ValueError):
        await gen.set_modulation("AM", True, bogus=1)
    await gen.set_modulation("AM", False)
    assert (await gen.get_modulation("AM"))["enabled"] is False
    assert await gen.get_modulation_master() is True  # untouched when disabling


@pytest.mark.asyncio
async def test_readings_and_measurement(gen):
    await gen.set_frequency(915e6)
    await gen.set_level(-7)
    await gen.set_output(True)
    r = await gen.get_readings()
    assert isinstance(r, RFGeneratorData)
    assert r.frequency == 915e6 and r.level == -7.0 and r.output_enabled is True
    assert r.modulation_enabled is False and r.alc_enabled is True
    await gen.set_modulation("AM", True, depth=50)
    r = await gen.get_readings()
    assert r.modulation_enabled is True and r.modulation_type == "AM"
    assert r.modulation_parameters["depth"] == 50.0
    assert (await gen.get_measurement("FREQ"))["value"] == 915e6
    assert (await gen.get_measurement("LEVEL"))["value"] == -7.0
    assert (await gen.get_measurement("CH1"))["quantity"] == "level"
    assert (await gen.get_measurement("OUTPUT"))["value"] == 1.0
    with pytest.raises(ValueError):
        await gen.get_measurement("TEMP")
    meas = await gen.get_measurements()
    assert meas["frequency"] == 915e6 and meas["level_unit"] == "dBm"


@pytest.mark.asyncio
async def test_sweep_alc_and_trigger(gen):
    sw = await gen.set_sweep("FREQ", start_frequency=1e6, stop_frequency=1e9, points=101, dwell=0.02, continuous=False)
    assert sw["enabled"] is True and sw["state"] == "FREQ" and sw["points"] == 101 and sw["mode"] == "SING"
    with pytest.raises(ValueError):
        await gen.set_sweep("FREQ", stop_frequency=9e9)
    with pytest.raises(ValueError):
        await gen.set_sweep("UP")
    await gen.execute_sweep()
    assert gen.sweeps_executed == 1
    await gen.trigger("SWEEP")
    assert gen.triggers == ["SWEEP"]
    with pytest.raises(ValueError):
        await gen.trigger("COFFEE")
    assert await gen.set_alc(False) == "OFF"
    assert await gen.set_alc(mode="AUTO") == "AUTO"
    with pytest.raises(ValueError):
        await gen.set_alc(mode="SOMETIMES")
    assert (await gen.set_sweep("OFF"))["enabled"] is False


@pytest.mark.asyncio
async def test_execute_command_state_reset_errors(gen):
    assert await gen.execute_command("set_frequency", {"frequency": 2.45e9}) == 2.45e9
    await gen.execute_command("set_output", {"enabled": True})
    state = await gen.execute_command("get_state", {})
    assert state["frequency"] == 2.45e9 and state["output_enabled"] is True
    assert "AM" in state["modulations"] and state["sweep"]["enabled"] is False
    with pytest.raises(ValueError):
        await gen.execute_command("fly_to_the_moon", {})
    gen.set_simulated_error("Settings conflict")
    err = await gen.execute_command("get_error", {})
    assert err["code"] == -1 and err["message"] == "Settings conflict"
    assert (await gen.get_error())["code"] == 0
    await gen.execute_command("reset", {})
    assert await gen.get_output() is False and await gen.get_frequency() == 3e9
    lf = await gen.set_lf_output(True, frequency=2e3, shape="square")
    assert lf["enabled"] is True and lf["shape"] == "SQUA"
    assert await gen.get_options() == "IQ,PUM,PUG"


@pytest.mark.asyncio
async def test_disconnected_rejects_commands():
    g = MockRFGenerator()
    with pytest.raises(RuntimeError):
        await g.execute_command("get_readings", {})
