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
| everything else | `GenericInstrumentPanel` | `state` (`get_state` command) | 2000 ms |

Planned, in order (see `docs/HANDOFF_INSTRUMENT_PANELS.md`): oscilloscope with a
live trace, electronic load, multimeter, function generator, RF generator,
spectrum analyzer, VNA, data acquisition. Each panel's controls follow its
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
