# Handoff — per-instrument control panels

> **Status (2026-09-15, branch `feature/instrument-panels`, VERSION 2.4.0):**
> all five phases are implemented and green (2648 tests). The shell, contract,
> registry and all nine panels are in `client/ui/instruments/`; see
> `docs/INSTRUMENT_PANELS.md`. What remains is the bench verification in the
> "Verification" section below -- the DS1054Z live trace, both supplies
> behaving as before, hidden panels stopping, a clean log -- which needs the
> branch running on the Lab Server and the Windows client, moved there with
> the in-app Update Client button.

**To:** the session on `/home/stevecap/Lablink` (SKL Robotics Enterprise,
Claude Fable 5.1), which has `~/Manuals/Rigol/` locally.
**From:** the Windows session on `C:\dev\LabLink`.
**Why hand over:** the work needs the Rigol manuals for panel layout.
`docs/rigol/downloads_catalog.json` records 420 of 421 documents as
downloaded, but every `local_path` is `~/Manuals/Rigol/...` — that tree exists
on your machine, not this one. Everything else needed is in the repo.

---

## Where things stand

`main` is at **v2.3.2**, everything pushed, 2494 tests passing. Eight releases
went out today: 2.1.3 → 2.3.2. Your Rigol work is **merged into main** (v2.3.0)
after review.

Two checkouts on the Windows machine, with strictly separate jobs:

- `C:\dev\LabLink` — development, stays on `main`.
- `C:\LabLinkTest` — **the real install**, pinned to a release tag. All of
  Steve's shortcuts point at it.

> **The one rule that matters.** Never `git pull`, `checkout` or `reset` inside
> the install. Earlier today `C:\LabLinkTest` was found on
> `feature/rigol-equipment-drivers` at VERSION 0.28.0 — 306 commits behind —
> because that branch was developed *inside the install*. It rolled Steve's
> bench back to 1.0.1-era code with the Rigol drivers on top. Restored to
> v2.2.0 by hand. Work in a clone; Steve moves the install with the in-app
> Update Client button.

Your `feature/rigol-equipment-drivers` branch is now 11 commits behind main
(you merged the rebased tree in `f2ad676`). **Branch fresh from `main`** for
this work rather than continuing it.

## What review found in the Rigol work

Fixed on main already — listed so they are not reintroduced. The drivers
themselves reviewed well: the DP limit checking is careful (per-channel
limits, NaN/inf rejected, raises rather than silently clamping, negative
channels handled), and 330 of the new protocol-level tests genuinely run.

1. **A B&K instrument was dispatched to a Rigol driver.** B&K's `RFM3000`
   contains `M300`, the Rigol DAQ keyword, and the keyword registry is
   consulted before the B&K one. Keyword matching is now anchored at a word
   boundary (`_keyword_matches`), checked against all 332 B&K model strings.
   Only the leading edge can be anchored — keywords mix whole names (`M300`)
   with family prefixes (`DSG3`, which must match `DSG3060`).
2. **A DS1054Z reported 100 MHz.** It is driven by `RigolDS1104` — correct,
   they share a command tree — but it inherited that model's capability block.
   `ds1000z_specs()` now reads bandwidth and channel count from the model name.
3. **`time.time()` for a duration** in `rigol_daq`. The repo requires a
   monotonic clock (`tests/unit/test_elapsed_time.py` enforces it).
4. **A hardcoded `== 7`** in the default-profiles test, which your four
   multimeter profiles broke. It counts the defaults now.

Also: the branch left `VERSION` at 2.2.0 while adding `[Unreleased]` notes, so
`/api` reported the same version for main and the branch and they could not be
told apart. Bump `VERSION` when a branch changes behaviour.

## The bench

- `192.168.91.191` — "Lab Server". **Rigol DS1054Z** (`1ab1:04ce`, serial
  DS1ZA171409212, fw 00.04.03) on `/dev/usbtmc0`, plus B&K **1685B**
  (`ASRL/dev/ttyUSB0::INSTR`) and **9205B** (USB). Reach it over SSH as
  `admin` with the key at `~/.ssh/id_ed25519`, or password.
- `10.10.0.51`, `10.10.0.56` — test Pis, one supply each.
- USB hot-plug does not reach the container: `/dev/bus/usb` is bind-mounted at
  container start with private propagation, so an instrument plugged in later
  is invisible until the containers restart.

The scope answers through the merged code — verified with
`get_measurements` returning `{"vpp":1.52,"vmax":0.76,"vmin":-0.76}`.

---

## The task

The Control tab drives everything as if it were a power supply. A DS1054Z is
shown voltage and current dials it has no concept of.

Not only cosmetic: both bugs shipped today came from it — the 404 storm
(2.1.4) and the 501 storm (2.2.1) — because **one panel polls every instrument
as if it were a supply**, so an instrument that cannot answer is asked anyway,
several times a second, until the loop starves and *other* instruments stop
connecting. A contract where each panel declares what it polls removes that
bug class instead of patching it a third time.

`control_panel.py` is 1917 lines and 79 methods, holding the equipment list,
lock strip, client resolution and every supply control. Adding eight
instruments around that shape entrenches it.

### Decided with Steve

- All nine instrument types get real panels.
- The oscilloscope panel includes a **live waveform trace** from the start.
- **Each panel declares its own cadence**; the existing refresh-rate control
  overrides per instrument, remembered per type.
- Panels must be **self-contained** — own client, own timer — because #248
  (detaching panels into their own windows, so instruments can be watched side
  by side) then becomes reparenting rather than a rewrite.
- Layout should follow the real instruments, which is what the manuals are for.

### Design

**`ControlPanel` becomes a shell:** left equipment column, lock strip,
selection, client resolution (`_client_for`, already built for multi-server),
hosting a `QStackedWidget`. Nothing instrument-specific.

**`InstrumentPanel` base** (`client/ui/instruments/base.py`):

- `set_instrument(equipment, client)` — the panel holds its own client.
- `POLLS` — `readings` / `measurements` / `state` / nothing. The shell never
  assumes an instrument can answer.
- `DEFAULT_INTERVAL_MS` — supply 100 ms, scope measurements ~500 ms, DMM 200 ms.
- `start()` / `stop()` — the panel owns its timer, started when it becomes
  visible, stopped when replaced.
- `set_controls_enabled(bool)` — driven by the shell's lock strip.
- Permanent-refusal handling moves into the base: 404 means gone, 501/405 mean
  this instrument has no such capability; both stop polling, a transient error
  does not. See `_equipment_is_gone` / `_readings_unsupported` in
  `control_panel.py`.

**Registry** `EquipmentType` → panel class, with `GenericInstrumentPanel` as
fallback (identity, `get_state`, measurements) — never supply dials.

**Reuse, do not rebuild.** Move `FittedReadout`, `AnalogGauge` (the Simpson
meter), `ChartWithReadouts`, `_nice_range` / `_track_extremes` /
`_apply_auto_range`, `_readings_interval_ms` into
`client/ui/instruments/widgets.py` and share them.

**No server work.** Every driver already exposes `get_state`, `get_readings`,
`get_measurements`, `get_error`, `clear_errors` via `execute_command`, reached
through `client.send_command`. Command surfaces: scope 33, DMM 44, function
generator 47, spectrum analyser 48, RF generator 31, VNA 34, DAQ 26, supply 32,
load 20.

### The nine panels

Controls follow each family's `set_*`/`get_*` surface in
`server/equipment/rigol_*.py`, the family docs from your merge
(`docs/RIGOL_DP.md`, `RIGOL_SCOPES.md`, `RIGOL_DMM.md`, `RIGOL_DG.md`,
`RIGOL_SA.md`, `RIGOL_DSG.md`, `RIGOL_VNA.md`, `RIGOL_M300.md`), and the
manuals on your machine.

| Panel | Principal controls |
|---|---|
| `PowerSupplyPanel` | existing UI moved: V/I setpoints, output, CV/CC, digital/analog/graph, min/max, auto-range |
| `OscilloscopePanel` | per-channel enable/scale/offset/coupling, timebase, trigger, run/stop/single/force, measurements, **live trace** |
| `ElectronicLoadPanel` | mode (CC/CV/CR/CP), setpoint, ranges, input on/off, live V/I/P |
| `MultimeterPanel` | function, range/auto, rate, secondary display, math, large readout |
| `FunctionGeneratorPanel` | waveform, frequency, amplitude, offset, phase, duty/symmetry, load, output, burst/sweep/modulation |
| `RFGeneratorPanel` | frequency, level, output, modulation, sweep, ALC |
| `SpectrumAnalyzerPanel` | centre/span/start/stop, RBW/VBW, reference level, detector, markers, trace |
| `VNAPanel` | sweep, S-parameter, format, markers, calibration state |
| `DAQPanel` | module/channel configuration, scan list, scan control, per-channel readings |

Waveform: `get_waveform` on its own slower cadence, decimated server-side,
QtCharts as the supply graph does, axes from the returned preamble.

### Phasing

Each phase ends green and usable.

1. Shell + contract + registry + generic panel; `PowerSupplyPanel` extracted
   as the first real panel. No behaviour change for supplies. The 38 test
   references across 5 GUI files move to constructing `PowerSupplyPanel`
   directly — better testing than reaching into the shell.
2. `OscilloscopePanel` — controls and measurements, then the live trace.
   Verify against the DS1054Z.
3. `ElectronicLoadPanel`, `MultimeterPanel`.
4. `FunctionGeneratorPanel`, `RFGeneratorPanel`.
5. `SpectrumAnalyzerPanel`, `VNAPanel`, `DAQPanel`.

### Tests

- Registry: every `EquipmentType` maps to a panel; unmapped types get the
  generic one and **never** the supply panel.
- Polling contract: a panel polls only what it declares; 404/501/405 stop its
  timer; a transient error does not. This is the regression guard for both
  storms.
- Cadence: each panel's default is used; an override is remembered per type.
- Retarget `test_readouts.py`, `test_analog_gauge.py`,
  `test_panel_reranging.py` to `PowerSupplyPanel`.
- Per-panel tests against a fake client asserting the commands sent.

### Verification

1. Full suite (2494 today) plus new tests.
2. On `192.168.91.191`: the DS1054Z shows a scope panel with a live trace, not
   supply dials; both supplies behave exactly as before, auto-range and min/max
   included.
3. Switch between instruments and confirm a hidden panel stops polling and the
   supply resumes at its own rate.
4. Log stays clean — no repeated 404/501 with a scope selected.
5. Instruments on two servers still dispatch to the right panel and the right
   client.

## Conventions worth knowing

- Tests are named for the behaviour they protect and carry a docstring saying
  why the bug mattered; several assert they can still see the bug they were
  written for. A test that cannot fail against the old code is worse than none
  — two were caught being vacuous today.
- Check `$?` explicitly rather than piping test runs through `tail`; a red
  build was pushed that way once.
- `scripts/bump_version.py {major|minor|patch}` writes a CHANGELOG stub to
  fill in; it prompts, so pipe `echo y`.
- Releases: bump, fill the changelog, tag `vX.Y.Z`, push, `gh release create`.

## Open issues

- **#248** — detachable panels. This work is its precondition.
- **#247** — multi-server. First increment shipped in v2.2.0 (Equipment and
  Control tabs span all connected servers). Remaining: the equipment-scoped
  panels (Acquisition, Diagnostics, Test Sequence), **WebSocket streams per
  server** (only the active server's stream works today — relevant if panels
  move to streaming), the dropdown becoming connection management, and
  per-server backoff.
- Six dependabot PRs, two mobile majors, deliberately excluded from releases.
