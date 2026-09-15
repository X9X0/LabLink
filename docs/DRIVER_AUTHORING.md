# Writing an Equipment Driver for LabLink

This is the contract every instrument driver follows. It was written while adding the Rigol families
listed in `docs/RIGOL_EQUIPMENT_CATALOG.md`; the reference implementation is
`server/equipment/rigol_multimeter.py` (read it first, it is the template).

## Where things live

| What | Path |
|------|------|
| Real drivers | `server/equipment/<vendor>_<class>.py` |
| Mock drivers | `server/equipment/mock/mock_<class>.py` (plain duck-typed classes, no base class) |
| Base class | `server/equipment/base.py` → `BaseEquipment` |
| Shared wire models | `shared/models/equipment.py` (`EquipmentType`, `EquipmentInfo`, `EquipmentStatus`), `shared/models/data.py` |
| Driver registration | `server/equipment/manager.py` `_create_equipment_instance()` and `server/equipment/__init__.py` |
| Discovery classification | `server/discovery/vendor_models.py`, `server/discovery/usb_hardware_db.py` |
| Manual text | `~/Manuals/Rigol/_text_extracted/<FAMILY>__<Guide>.txt` (PDF/CHM already converted) |
| Tests | `tests/hardware/test_<vendor>_<class>.py` (scripted fake instrument), `tests/unit/`, `tests/test_mock_*.py` |

Imports inside a driver must be only `from shared.models...` and relative `from .base import ...`, so the
module imports under both `equipment.x` and `server.equipment.x` (both are used by tests).

## BaseEquipment contract

```python
class MyDriver(BaseEquipment):
    async def get_info(self) -> EquipmentInfo      # required: parse *IDN?, type, id prefix
    async def get_status(self) -> EquipmentStatus  # required: connected, firmware, capabilities dict
    async def execute_command(self, command: str, parameters: dict) -> Any  # required: name -> method
```

Provided by the base: `connect()` (opens VISA resource, 10 s timeout, `*IDN?`, caches `get_info()`),
`disconnect()`, `_write(cmd)`, `_query(cmd) -> str`, `_query_binary(cmd) -> bytes` (all executor
offloaded, diagnostics recorded), `_ensure_connected()`, `get_error_code()/get_error_message()` (parse
`SYST:ERR?`), `clear_errors()` (`*CLS`), `run_self_test()`, `_determine_connection_type()`.

Override `connect()` only to configure RS-232 (copy the pattern in `rigol_multimeter.py`) or to send a
setup command such as a command-set switch. Keep the `self._lock`, `_is_connecting` handling.

Rules:
- `EquipmentInfo.id` comes from `generate_equipment_id(self.resource_string, "<prefix>_")`. Prefixes in
  use: `scope_`, `ps_`, `load_`, `dmm_`. New: `fgen_`, `sa_`, `rfgen_`, `vna_`, `daq_`.
- Parse `*IDN?` as `manufacturer,model,serial,firmware`; fall back to class defaults per field.
- Never name a method `set_input` or `set_output` unless it really controls the instrument's main
  output/input: `manager.disconnect_device()` calls them with `False` on disconnect (safe state).
  Generators and RF sources *should* implement `set_output(enabled, channel=1)` so disconnect turns
  outputs off. Measurement-only instruments must not define them.
- Model-specific facts (channel counts, ranges, limits) go in a class-level table or subclass constants,
  not in `if model ==` chains inside methods.
- Validate parameters and raise `ValueError` with a message that names the valid range.
- Every family gets a `capabilities` dict in `get_status()` with at least the model table fields, plus
  `"supports_acquisition": True/False`.

## Integration hooks (make these work and the rest of LabLink works)

| Hook | Used by | Contract |
|------|---------|----------|
| `get_readings()` | REST `GET /equipment/{id}/readings`, WebSocket `readings` stream, generic client display | return a pydantic model from `shared/models/data.py` (or a dict) |
| `get_measurement(channel: str) -> {"value": float, ...}` | acquisition engine (`server/acquisition/manager.py:_get_channel_value`) | `channel` is a free string the user typed; document the accepted names; return NaN for invalid/overload |
| `get_measurements(channel)` | WebSocket `measurements` stream | dict of name -> float |
| `get_waveform(channel)` | WebSocket `waveform` stream, scope UI | `WaveformData` + numpy array (see `rigol_scope.py`) |
| `get_state()` / `get_mode()` / `get_range()` | state capture/restore (`server/equipment/state.py`) | dicts of current settings |
| `execute_command` names | client panels, REST `POST /command`, test sequences | plain snake_case verbs; include `get_readings`, `get_measurement`, `get_state`, `reset`, `get_error` |

`execute_command` should be a dict dispatch `{name: bound method}` and call `handler(**parameters)`.

## Per-class command vocabularies

Use these names so panels and profiles can target any vendor's instrument of the same class.

- **Power supply** (`EquipmentType.POWER_SUPPLY`, model `PowerSupplyData`): `set_voltage(voltage, channel)`,
  `set_current(current, channel)`, `set_output(enabled, channel)`, `get_readings(channel)`,
  `get_setpoints(channel)`, `set_ovp(voltage, channel, enabled)`, `set_ocp(current, channel, enabled)`,
  `get_protection(channel)`, `clear_protection(channel)`, `set_tracking(mode)`, `get_measurement(channel)`
  where channel accepts `CH1`, `1`, `CH1:V`, `CH1:I`, `CH1:P`.
- **Oscilloscope** (`WaveformData`): mirror `rigol_scope.py`: `set_channel(channel, scale, offset, coupling, probe, bandwidth_limit, enabled)`,
  `set_timebase(scale, offset)`, `set_trigger(source, level, slope, mode)`, `run/stop/single/autoscale`,
  `get_waveform(channel)`, `get_measurements(channel)`, `get_measurement(channel)` (channel like `CH1:VPP`),
  `set_acquisition(mode, memory_depth, averages)`, `get_screenshot()` where supported.
- **Function generator** (`FunctionGeneratorData`): `apply(channel, waveform, frequency, amplitude, offset, phase)`,
  `set_waveform`, `set_frequency`, `set_amplitude(amplitude, unit)`, `set_offset`, `set_phase`, `set_duty_cycle`,
  `set_output(enabled, channel)`, `set_load(impedance, channel)`, `set_modulation(...)`, `set_sweep(...)`,
  `set_burst(...)`, `upload_arbitrary(points, channel)`, `get_readings(channel)`, `sync_phase()`,
  `get_counter()` if the model has a frequency counter.
- **Spectrum analyzer** (`SpectrumData`): `set_frequency(center, span)` / `set_start_stop(start, stop)`,
  `set_rbw`, `set_vbw`, `set_reference_level`, `set_attenuation(db, auto)`, `set_detector`, `set_sweep(points, time, continuous)`,
  `set_trace_mode(trace, mode)`, `get_trace(trace) -> SpectrumData`, `peak_search(marker)`, `set_marker(marker, frequency)`,
  `get_marker(marker)`, `set_tracking_generator(enabled, level)` when fitted, `get_readings()` returns the
  trace, `get_measurement(channel)` accepts `PEAK`, `PEAK_FREQ`, `MARKER1`, `CHPOWER`, `TRACE1:MAX`.
- **RF signal generator** (`RFGeneratorData`): `set_frequency`, `set_level(level, unit)`, `set_output(enabled)`,
  `set_modulation(type, enabled, **params)`, `set_alc(enabled)`, `get_readings()`.
- **VNA** (`NetworkAnalyzerData`): `set_sweep(start, stop, points, power)`, `set_parameter(trace, s_param)`,
  `set_format(trace, fmt)`, `get_trace(trace)`, `get_marker`, `calibrate_*` where the guide documents it.
- **Data acquisition** (`DataAcquisitionData`): `configure_channel(channel, function, range, resolution)`,
  `set_scan_list(channels)`, `scan()`, `read_channel(channel)`, `get_readings()`, `close_channel/open_channel`
  for switch modules, `get_modules()`.

## Mock drivers

One per equipment class (not per vendor). Same command names as the real driver, deterministic
simulated values with setter hooks (`set_simulated_*`), no VISA. Register in `mock/__init__.py`,
`equipment/__init__.py`, the mock branch of `manager._create_equipment_instance`, and
`mock_helper.DEFAULT_MOCK_EQUIPMENT` / `type_configs` / `list_mock_resource_strings`. Resource strings:
`MOCK::SCOPE::n`, `MOCK::PSU::n`, `MOCK::LOAD::n`, `MOCK::DMM::n`; new: `MOCK::FGEN::n`, `MOCK::SA::n`,
`MOCK::RFGEN::n`, `MOCK::VNA::n`, `MOCK::DAQ::n`.

## Tests

Copy `tests/hardware/test_rigol_dmm.py`: a `Scripted<Class>` fake instrument with `session = 1`,
`timeout`, `write()`, `query()` that answers the documented SCPI (raise `AssertionError` on anything
unscripted so the test tells you which command the driver sent), plus `make_driver(cls, model)`. Cover:
identification for every model class, one setter/getter per subsystem, the acquisition hook, the
`execute_command` dispatch incl. the unknown-command error, and one model-difference test. Run with
`venv/bin/python -m pytest tests/hardware/test_x.py -q -p no:cacheprovider`.

## Registration (done centrally, not by the driver author)

Report the model keywords each class should match, ordered most-specific first. They are added to
`manager._create_equipment_instance`, `equipment/__init__.py`, `shared/constants/SUPPORTED_MANUFACTURERS`,
`client/ui/connect_dialog.py` model list, `README.md` Supported Equipment, `CHANGELOG.md`.
