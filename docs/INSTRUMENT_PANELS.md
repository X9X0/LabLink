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
    async def refresh_settings(self): ...          # read the instrument's own settings onto the controls
```

What the base class does for you:

| Concern | Behaviour |
|---|---|
| Binding | `set_instrument(equipment, client)` stops the old poll and binds at once; `_bind()` then reads capabilities off the GUI thread, calls `configure()`, and awaits `refresh_settings()`. Nothing in selection waits on the server: on a bench DS1000Z the synchronous version froze the window for twenty seconds |
| Read-back | `refresh_settings()` sends with `priority=False`, blocks widget signals while setting them, and is dropped if the selection has moved on. `run_now_or_soon()` schedules it under a running loop and runs it to completion in tests |
| Starting | `start()` refuses when `POLLS is None`, no instrument is bound, or the server does not hold it open (`is_connected()`); otherwise waits `SETTLE_MS` (500 ms) on a child timer, then runs `poll_timer` at `interval_ms()` |
| Stopping | `stop()` halts both timers; `is_polling()` reports either |
| Ticks | `_poll` skips a tick while one is in flight (`inflight.claim_slot`), calls `poll()`, and interprets failures |
| 404 | instrument gone: stop, `mark_disconnected()`, `show_not_connected()`, emit `equipment_gone(id)` |
| 501 / 405 | this instrument cannot do this: stop, `show_unsupported()` |
| 500 / 503 / timeout | transient: keep polling |
| Cadence | `set_rate_hz()` / `set_interval_ms()` apply at once; `_create_rate_control()` gives a spinbox wired to them; overrides are remembered per `SETTINGS_TYPE` via `SettingsManager.get_reading_rate_for` |
| Commands | `await self.send("set_voltage", {...})` runs `client.send_command` off the GUI thread and raises on `success: false`. An operator command (`priority=True`, the default) holds polls back until it has finished plus `COMMAND_COOLDOWN_S`; read-backs and polls pass `priority=False` |
| Messages | `status_message` reaches the main window's status bar through the shell |

The shell only ever calls `set_instrument`, `start`, `stop`, `set_controls_enabled`
and reads `status_message` / `equipment_gone`. It never assumes an instrument
can answer anything. Its own lock work (release the previous instrument's
lock, read this one's, acquire it) runs in `_take_control()` off the GUI
thread; the panel is read-only until the lock is ours, and polling starts
straight away because readings need no lock.

### Where a lag comes from

Every instrument request on the server queues on that instrument's I/O
lock. When a panel is slow, the server log now says why: `BaseEquipment`
warns when an exchange waits more than `SLOW_IO_WARN_SEC` (2 s) for the
lock (`'...' waited 4.1s for the instrument`) or holds the instrument that
long (`'...' took 10.0s on the instrument`, which at 10 s is the VISA
timeout: a command the instrument did not answer). Look for those two
lines before changing anything else.

A queue cannot now grow without limit. An instrument answers one caller at a
time and the server does not cancel a request whose client has given up, so a
command that stops answering used to turn every later request into a queue
entry -- the bench DS1054Z reached a 205 s queue, and selecting it in the list
looked like a hang. Past `BaseEquipment.MAX_QUEUED_EXCHANGES` (8) queued
requests, an exchange is refused with `InstrumentBusy` and the API answers
503 (`'...' refusing ':WAV:SOUR CHAN1' -- 8 requests already queued`). A panel
that sees a failed poll doubles its interval up to
`InstrumentPanel.POLL_BACKOFF_CAP_MS` (30 s) and returns to the operator's
cadence on the first good one, so a slow instrument is asked less often rather
than more. Backing off is not stopping: only a 404 or a 501 stops a timer.

### Min/max belongs to the instrument

`InstrumentPanel` keeps the extremes seen per equipment id and
restores them when that instrument comes back. They cannot live on the
readout widget: one panel serves every instrument of its type, and
`configure()` resets the readout on each switch -- deliberately,
because a scale held from a 25 A supply is wrong for a 5 A one. That
threw the extremes away with it.

`remember_extremes()` runs on the way out of `set_instrument`,
`restore_extremes()` after `configure()` on the way in. Reset is the
only thing that clears them: `MeasurementViews.extremes_reset` fires
when they are deliberately dropped and the panel drops its kept copy
too, or the old figures would reappear on the next switch.

Session-scoped, not written to disk. An extreme from a run days ago,
restored silently into a live panel, is a worse lie than an empty
Min/Max.

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
| `power_supply` | `PowerSupplyPanel` | `readings` (`GET /equipment/{id}/readings`), or `get_all_readings` for a multi-channel supply | 100 ms |
| `oscilloscope` | `OscilloscopePanel` | `measurements` (`get_measurements`), plus the waveform on its own timer (`get_waveform_data`, decimated to 600 points) | 500 ms / 1000 ms |
| `electronic_load` | `ElectronicLoadPanel` | `readings` (`ElectronicLoadData`) | 200 ms |
| `multimeter` | `MultimeterPanel` | `readings` (`MultimeterData`), plus `get_statistics` while a statistic math function is selected | 200 ms |
| `function_generator` | `FunctionGeneratorPanel` | `state` (`get_readings {channel}` + `get_counter` where fitted) | 1000 ms |
| `rf_signal_generator` | `RFGeneratorPanel` | `state` (`get_readings`) | 1000 ms |
| `spectrum_analyzer` | `SpectrumAnalyzerPanel` | `measurements` (`get_trace {trace: 1}`) | 1000 ms |
| `vector_network_analyzer` | `VNAPanel` | `measurements` (`get_trace {trace: 1}`) | 1000 ms |
| `data_acquisition` | `DAQPanel` | `readings` (`DataAcquisitionData`, the last scan) | 2000 ms |
| everything else (`unknown`) | `GenericInstrumentPanel` | `state` (`get_state` command) | 2000 ms |

### PowerSupplyPanel

One panel class serves every supply, because panels are chosen by
equipment type. It has **two bodies** and picks between them from
`capabilities["channels"]`.

**One channel** is the original layout, unchanged: voltage and current
dials with spin boxes, the output button, CV/CC indicators, the
refresh rate, and the digital / analog / graph stack. Four of the five
instruments on the bench are single-channel, so this is the case that
must not regress and most of the panel's tests are about it.

**More than one channel** lays the same ideas out in bands:

- **Controls** — a column per channel, each with its own dial and box
  for volts and amps, its own output switch, its own CV/CC indicator
  and its own timer. Nothing here is shared between channels. A
  channel that is not programmable has almost nothing in its column,
  which leaves the room above it free.
- **Shared bar** — one Display Mode selector, one Output Mode group
  (Independent / Series / Parallel with an indicator), one Min/Max,
  Reset and Auto Range, and the one Refresh Rate. Three selectors
  would be three things to keep in step; the refresh rate belongs to
  the poll, which is per instrument.
- **Readings** — one `MeasurementViews` per readable channel, side by
  side, each showing that channel's volts, amps and watts stacked.
  Built with `vertical=True, with_selector=False, with_tools=False`
  and driven from the shared bar through `set_mode`,
  `set_minmax_tracking` and `set_autorange`.

Channels can be hidden from the `Channels:` row. A hidden column gives
its width back — its stretch is dropped as well as its visibility, or
the layout keeps the space and the remaining readings stay the size
they were beside a gap. Hidden channels are remembered per instrument
(`SettingsManager.get_hidden_channels`), never against an empty
equipment id.

**Why one request per poll.** Measured against an SPD3303X-E, a
per-channel `get_readings` is ~83 ms and a bare status query ~73 ms,
so the hop dominates. Three sequential calls come to ~250 ms against a
100 ms poll. `get_all_readings` reads the status word once and shares
it across the channels.

**The indicator follows the instrument, not the button.** Changing the
coupling switches both outputs off and can be refused at several
points; a panel claiming a mode the supply is not in is worse than one
that waits to be told.

**A channel with no readback** — the SPD3303X's fixed CH3 — is absent
from the poll entirely. Its switch shows what it was commanded, which
is the only thing that will ever move it, and its tooltip says so.

Anything on this panel that reaches the server goes through
`_ready_to_send()` first. An `asyncSlot` invoked with no running event
loop does not raise, it aborts the interpreter, and a strip's signals
can arrive outside the loop: Qt fires `editingFinished` when a box
loses focus, which happens during teardown and in tests.

### OscilloscopePanel

Two views, switched at the top of the panel. **Standard** is grouped
controls; **Front panel** (`client/ui/instruments/scope_front_panel.py`) is
the instrument's own control surface laid out from the DS1000Z "Front Panel
Overview" figure -- softkeys either side of the screen (decorative), CLEAR /
AUTO / RUN-STOP / SINGLE, the multifunction knob and menu keys, and the
VERTICAL, HORIZONTAL and TRIGGER areas with real knobs. The live trace moves
behind the bezel. Knobs turn with the mouse wheel while hovered (one notch =
one detent) or by dragging round them, and click to press, with the presses
the instrument has: HORIZONTAL POSITION and TRIGGER LEVEL reset to zero,
VERTICAL POSITION to zero, the SCALE knobs toggle fine steps. Channel keys
select the channel the vertical knobs act on and, pressed again, turn it off;
RUN/STOP lights yellow running and red stopped; MODE cycles Auto → Normal →
Single. Menu keys and softkeys are shown but disabled -- their menus are the
standard view.

**Polling cost matters on this instrument.** Every automatic measurement is a
`:MEASure` query the DS1000Z may answer only after a full acquisition, so the
default set is Basic (Vpp, Vavg, Freq) at 2 s, with Off and All available.
Polls yield to operator commands (`InstrumentPanel.commands_pending`) and the
trace and measurement polls never overlap, so a knob turn is never queued
behind a background fetch. Server-side, `get_readings` on every scope driver
is a cheap status snapshot, not the measurement set: the Equipment tab's
readings stream polls it twice a second.

Standard-view layout: the live trace and a measurements table on the left;
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

That trace is read in windows, not in one go. The bench DS1054Z declares a
64-byte bulk max packet where USB 2.0 high speed requires 512, and over
pyvisa-py/libusb that gives a hard ceiling on one reply: 492 bytes arrives,
512 never does. A 1200-sample screen read is 1212 bytes, so it always timed
out and the panel had no trace at all. `:WAV:STARt`/`:WAV:STOP` window the
read in NORMal mode as well as RAW, so `LegacyScopeExtras._read_trace_in_blocks`
fetches `trace_block_points` (400) samples at a time and stitches them -- about
1 s for a full screen, with the scope left running. Windowing is opt-in per
family: only the DS1000Z has been measured, and the older DS1000D/E tree may
not window at all. See `docs/HANDOFF_SCOPE_LAG.md` for the measurements.

### ElectronicLoadPanel

Mode (CC/CV/CR/CP), one setpoint whose unit and ceiling follow the mode
(`max_current` / `max_voltage` / `max_power` from capabilities), an Input
ON/OFF button, and three readouts (V, A, W). The setpoint is sent on Apply as
`set_mode {mode}` followed by `set_current` / `set_voltage` / `set_resistance`
/ `set_power`, so a device switch can never command the instrument. On
binding the load's own mode, setpoint and input state are read from
`/readings` onto the controls, silently.

A setpoint knob sits beside the spin box, as on the supply. Battery
discharge has its own group, and **Edit list...** opens the list
sequence editor (`list_dialog.py`, JSON import and export) with **Run
list** beside it.

**Selecting `:FUNCtion:MODE LIST` arms a list; it does not start
one.** The guide gives no start command and never connects the list
to `:TRIGger`, but a load in LIST with its input on and the RUN bit
set will sit there indefinitely. `start_list` sets the trigger source
to BUS, selects the mode and fires `:TRIG`, in that order -- the
source is set before the mode, because changing it afterwards disarms
what it was meant to start.

Stopping is not the mirror of starting. `:SOUR:FUNC:MODE FIX` is
accepted and ignored while a list runs, so `stop_list` asserts the
regulation law instead, and honours `:LIST:END` -- a list that ends
on its own switches the input off, and one stopped by hand now does
the same rather than leaving the load sinking at the fixed setpoint.

The Run button follows the status register's RUN bit, and only
confirms a run this panel started: the bit stays up after a hand stop
and was already up from an earlier arming the first time the panel
read it.

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

### SpectrumAnalyzerPanel

The trace is the reading: each poll fetches trace 1 and draws it against
the start/stop it came with, the amplitude axis hung from the reference
level. Groups follow the analyzer's own: Frequency (center/span,
start/stop, full span), Bandwidth (RBW, VBW with Auto, detector), Amplitude
(reference level, attenuation with Auto, preamp), Sweep/Trace (continuous,
single, trace mode, GPSA/RTSA where the model has it), Marker 1 (peak
search, next peak, marker to center, set at frequency) and the tracking
generator group, shown only when `capabilities["has_tracking_generator"]`.

### VNAPanel

One trace against the stimulus frequencies the instrument reports. The
Stimulus group sends one `set_sweep {start, stop, points, power,
if_bandwidth}`; Parameter (S11…S22) and Format command immediately; Marker 1
and a calibration group (`calibrate_start` / `calibrate_acquire` /
`calibrate_save` / `calibrate_abort`, correction on/off). Two-value formats
draw the primary value and say so.

### DAQPanel

Modules fitted (from capabilities, refreshed from each scan), a channel
configuration group (channels such as `101, 102:110`, function, range or
temperature sensor and type → `configure_channel`), scan list and trigger
(`set_scan_list`, `set_trigger`), a Scan Now button, switch-module Close /
Open, and a readings table -- one row per channel with value, unit and
function -- filled from the last scan on each poll.

All nine instrument types now have a panel of their own; only `unknown`
falls back to the generic one. Each panel's controls follow its
driver family's `set_*` / `get_*` surface (`server/equipment/rigol_*.py`,
`bk_*.py`) and the family docs (`docs/RIGOL_*.md`).

## Shared widgets

`client/ui/instruments/channel_strip.py`: `ChannelStrip`, one supply
channel's controls as a column. It reports what was asked for
(`setpoint_committed`, `output_toggled`) and never talks to the server
itself. A setpoint is reported only when it has actually moved --
`editingFinished` fires whenever a box loses focus, not only when
something was typed, so tabbing past a field used to re-send whatever
was in it.

`client/ui/instruments/timer_dialog.py`: `TimerDialog`, the five
timing groups of a SPD channel. Reads the instrument before offering
to change anything, because it holds these itself and they can be set
from the front panel.

`client/ui/instruments/measurement_views.py`: `MeasurementViews`, the
Digital / Analog / Graph stack. `vertical`, `with_selector` and
`with_tools` let a panel place several side by side under one selector
and one set of tools; `set_mode`, `set_minmax_tracking` and
`set_autorange` drive them from outside. Every channel gets a visible
scale in graph mode -- a trace whose scale is not shown is a shape,
not a measurement. `extremes()` and `restore_extremes()` let a panel
keep min/max per instrument; see the contract above.

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
- `tests/gui/test_spectrum_analyzer_panel.py`, `tests/gui/test_vna_panel.py`,
  `tests/gui/test_daq_panel.py` -- the analyzer and DAQ panels: trace drawing
  and axes from the returned data, marker and calibration payloads, channel
  configuration and scan-list payloads, the readings table.
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
