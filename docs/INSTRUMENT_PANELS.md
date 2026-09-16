# Instrument Panels

The Control tab (`client/ui/control_panel.py`) is a shell: an equipment list, a
lock strip, the selected instrument's name, and a `QStackedWidget` holding one
panel per instrument type. The panels live in `client/ui/instruments/` and
follow one contract, `InstrumentPanel` (`client/ui/instruments/base.py`).

## Why it is shaped this way

The tab used to be one 1900-line widget that drove everything as a power
supply. Two shipped bugs came from that: the 404 storm (2.1.4) and the 501
storm (2.2.1). One panel polled every instrument for volts and amps, so an
instrument that could not answer was asked anyway, several times a second,
until the event loop starved and *other* instruments stopped connecting. A
panel that declares what it polls, and stops itself on a permanent refusal,
removes the bug class rather than patching it a third time.

Panels are self-contained -- their own client, their own timer -- so detaching
one into its own window (issue #248) is reparenting, not a rewrite.

## The contract

```python
class MyPanel(InstrumentPanel):
    POLLS = POLL_READINGS          # or POLL_MEASUREMENTS, POLL_STATE, None
    DEFAULT_INTERVAL_MS = 500      # this panel's own cadence
    SETTINGS_TYPE = "oscilloscope" # key the operator's rate override is kept under

    def _build_ui(self): ...                       # widgets; place self._create_rate_control() somewhere
    def configure(self, capabilities): ...         # range controls from get_equipment_status()
    async def poll(self): ...                      # fetch what POLLS says; raise on fault
    def set_controls_enabled(self, enabled): ...   # gate command widgets (lock strip)
    def show_not_connected(self): ...              # blank readouts, say why
    def show_unsupported(self): ...                # blank readouts, say why
    def clear_instrument(self): ...                # on deselect
```

What the base class does for you:

| Concern | Behaviour |
|---|---|
| Binding | `set_instrument(equipment, client)` stops the old poll, reads capabilities synchronously, calls `configure()` |
| Starting | `start()` refuses when `POLLS is None`, no instrument is bound, or the server does not hold it open (`is_connected()`); otherwise waits `SETTLE_MS` (500 ms) on a child timer, then runs `poll_timer` at `interval_ms()` |
| Stopping | `stop()` halts both timers; `is_polling()` reports either |
| Ticks | `_poll` skips a tick while one is in flight (`inflight.claim_slot`), calls `poll()`, and interprets failures |
| 404 | instrument gone: stop, `mark_disconnected()`, `show_not_connected()`, emit `equipment_gone(id)` |
| 501 / 405 | this instrument cannot do this: stop, `show_unsupported()` |
| 500 / 503 / timeout | transient: keep polling |
| Cadence | `set_rate_hz()` / `set_interval_ms()` apply at once; `_create_rate_control()` gives a spinbox wired to them; overrides are remembered per `SETTINGS_TYPE` via `SettingsManager.get_reading_rate_for` |
| Commands | `await self.send("set_voltage", {...})` runs `client.send_command` off the GUI thread and raises on `success: false` |
| Messages | `status_message` reaches the main window's status bar through the shell |

The shell only ever calls `set_instrument`, `start`, `stop`, `set_controls_enabled`
and reads `status_message` / `equipment_gone`. It never assumes an instrument
can answer anything.

## The registry

`client/ui/instruments/registry.py` maps `EquipmentType` to a panel class.
`panel_class_for(type)` answers `GenericInstrumentPanel` for anything unmapped
or unrecognised, never `PowerSupplyPanel`. Register a new panel in
`_register_defaults()`:

```python
register_panel(EquipmentType.OSCILLOSCOPE, OscilloscopePanel)
```

The shell keeps one instance per panel class and reuses it, so switching
between two supplies keeps the graph history.

## Panels

| Type | Panel | Polls | Default |
|---|---|---|---|
| `power_supply` | `PowerSupplyPanel` | `readings` (`GET /equipment/{id}/readings`) | 100 ms |
| `oscilloscope` | `OscilloscopePanel` | `measurements` (`get_measurements`), plus the waveform on its own timer (`get_waveform_data`, decimated to 600 points) | 500 ms / 1000 ms |
| `electronic_load` | `ElectronicLoadPanel` | `readings` (`ElectronicLoadData`) | 200 ms |
| `multimeter` | `MultimeterPanel` | `readings` (`MultimeterData`), plus `get_statistics` while a statistic math function is selected | 200 ms |
| `function_generator` | `FunctionGeneratorPanel` | `state` (`get_readings {channel}` + `get_counter` where fitted) | 1000 ms |
| `rf_signal_generator` | `RFGeneratorPanel` | `state` (`get_readings`) | 1000 ms |
| everything else | `GenericInstrumentPanel` | `state` (`get_state` command) | 2000 ms |

### OscilloscopePanel

Front-panel layout: the live trace and a measurements table on the left;
Run / Stop / Single / Force / Auto, per-channel vertical controls (enable,
scale, offset, coupling, Apply), horizontal (scale, offset) and edge trigger
(source, level, slope, sweep) on the right. Channel rows and trigger sources
follow `capabilities["num_channels"]`. On binding it reads `get_state` once
and puts the scope's own settings on the controls with signals blocked, so
selecting a scope never commands it.

Commands sent: `set_channel {channel, enabled, scale, offset, coupling}`,
`set_timebase {scale, offset}`, `set_trigger {source, level, slope, sweep}`,
`trigger_run`, `trigger_stop`, `trigger_single`, `force_trigger`,
`autoscale`, `get_measurements {channel}`, `get_waveform_data {channel, points}`.
The trace axes come from the returned data: time from the sample times, volts
as ±4 divisions of the largest enabled channel scale, as on the instrument.
A driver that answers `Unknown command` for `get_waveform_data` is asked once;
the trace timer stops and the panel says so.

The legacy DS1000Z / MSO2000A / DS1000D drivers (`server/equipment/rigol_scope.py`)
did not have `get_waveform_data`, `set_trigger`, `get_state`, `get_measurement`
or `get_readings`; `LegacyScopeExtras` adds them with the same names and
shapes as `rigol_modern_scope`, so the bench DS1054Z gets a live trace.

### ElectronicLoadPanel

Mode (CC/CV/CR/CP), one setpoint whose unit and ceiling follow the mode
(`max_current` / `max_voltage` / `max_power` from capabilities), an Input
ON/OFF button, and three readouts (V, A, W). The setpoint is sent on Apply as
`set_mode {mode}` followed by `set_current` / `set_voltage` / `set_resistance`
/ `set_power`, so a device switch can never command the instrument. On
binding the load's own mode, setpoint and input state are read from
`/readings` onto the controls, silently.

### MultimeterPanel

One large readout with the instrument's annunciators (function, AUTO or the
range, rate) and an optional secondary display. Function, range (Auto plus
the per-function table from `capabilities["ranges"]`), rate, secondary
function and math are combo boxes that command immediately (`set_function`,
`set_range` / `set_auto_range`, `set_rate`, `set_secondary_function` /
`clear_secondary_function`, `set_math_function`); a Null button sends
`set_rel_offset {offset: "CURR"}`. While MIN/MAX/AVERAGE/TOTAL is selected the
poll also fetches `get_statistics`. Overload reads `OVLD`, as on the meter.

### FunctionGeneratorPanel

Per channel: waveform, frequency, amplitude with its unit, offset, phase and
duty, sent together on Apply as `set_amplitude_unit` then `apply {channel,
waveform, frequency, amplitude, offset, phase}` then `set_duty_cycle` for
square/pulse. Output ON/OFF (`set_output`), load (`set_load`), and separate
Apply buttons for sweep (`set_sweep`), burst (`set_burst`) and modulation
(`set_modulation`). The channel list and waveform list come from
capabilities (`channels`, `waveforms`, `max_frequency`); the poll reads the
selected channel back and the frequency counter where the model has one,
asking for the counter once only when it does not.

### RFGeneratorPanel

Frequency with a unit selector and level in dBm each with a Set button, RF
ON/OFF, ALC, a modulation group (type from `capabilities["modulation_types"]`,
depth/deviation, rate, source) and a frequency step-sweep group, each with
its own Apply. Frequency is range-checked against the model's limits before
it is sent.

Planned, in order (see `docs/HANDOFF_INSTRUMENT_PANELS.md`): spectrum
analyzer, VNA, data acquisition. Each panel's controls follow its
driver family's `set_*` / `get_*` surface (`server/equipment/rigol_*.py`,
`bk_*.py`) and the family docs (`docs/RIGOL_*.md`).

## Shared widgets

`client/ui/instruments/widgets.py`: `FittedReadout` (text sized to its box,
through the widget's own stylesheet because the application sheet beats
`setFont`), `AnalogGauge` (the Simpson-style panel meter), `ChartWithReadouts`
(a chart view with live values across its top) and `nice_range` (a readable
top-of-scale above a reading). They remain importable from
`client.ui.control_panel` for older code.

## Tests

- `tests/gui/test_instrument_panel_contract.py` -- the registry rule, the
  polling contract (404 / 501 / 405 stop, transients do not, disconnected
  instruments are never polled, hidden panels stop), cadence defaults and
  per-type overrides, and the shell's dispatch.
- `tests/gui/test_oscilloscope_panel.py` -- the scope panel against a fake
  client: configuration from capabilities and `get_state`, the exact payload
  of every command, measurement polling, decimated trace fetching and axes,
  one-shot handling of a driver without waveforms.
- `tests/gui/test_function_generator_panel.py`, `tests/gui/test_rf_generator_panel.py`
  -- the generator panels: apply payload per waveform, unit-first ordering,
  counter asked once, frequency range checking, modulation and sweep payloads.
- `tests/gui/test_electronic_load_panel.py`, `tests/gui/test_multimeter_panel.py`
  -- the load and meter panels against fake clients: payloads, read-back on
  binding without commanding, readouts and annunciators, unsupported commands
  reported rather than retried.
- `tests/unit/test_legacy_scope_extras.py` -- the legacy drivers' new
  commands against a scripted DS1054Z, including waveform scaling and
  server-side decimation.
- `tests/gui/test_readouts.py`, `test_panel_reranging.py`,
  `test_readings_stop_on_404.py`, `test_analog_gauge.py` -- the supply panel's
  behaviour, constructed directly.
- `tests/gui/test_multi_server_equipment_list.py`,
  `tests/client/test_equipment_lock_ui.py` -- the shell: client resolution per
  server and lock gating reaching `current_panel`.

Panel tests construct the panel under `QT_QPA_PLATFORM=offscreen`, drive
asyncSlots through their `__wrapped__` coroutine with `asyncio.run`, and use a
fake client that records the commands sent. Every panel a test starts must be
stopped afterwards: a live timer on a widget that outlives its test is a
segfault waiting for the next module's Qt call.
