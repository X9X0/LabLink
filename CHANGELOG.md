# Changelog

All notable changes to LabLink will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.4.0] - 2026-09-15

Per-instrument control panels, phase 1: the shell and the contract.

### ✨ Added

- **The Control tab hosts one panel per instrument type.** `ControlPanel` is
  now a shell -- equipment list, lock strip, selection, and the connection
  resolution built for multi-server -- around a `QStackedWidget`. Which panel
  appears is decided by a registry keyed on `EquipmentType`
  (`client/ui/instruments/registry.py`); a type with no panel of its own gets
  `GenericInstrumentPanel` (identity plus the driver's `get_state` snapshot),
  and never the power-supply dials. A DS1054Z no longer sees voltage and
  current controls it has no concept of.
- **Each panel declares what it polls and how fast** (`InstrumentPanel.POLLS`,
  `DEFAULT_INTERVAL_MS`) and owns its timer, started when it becomes current
  and stopped when replaced. The refresh-rate control moved into the panel
  and the operator's override is remembered per equipment type
  (`SettingsManager.get_reading_rate_for`), so choosing 5 Hz for a supply does
  not also drive a scope at 5 Hz.
- **Permanent refusals stop polling in the base class.** A 404 means the
  instrument is gone; 501 or 405 mean it cannot answer this panel's poll. Both
  stop the timer; a 500, 503 or timeout does not. This is the contract that
  replaces the fixes for the 2.1.4 (404) and 2.2.1 (501) storms, and
  `tests/gui/test_instrument_panel_contract.py` is its regression guard.
- `PowerSupplyPanel` (`client/ui/instruments/power_supply.py`): the existing
  supply UI moved out of the shell unchanged in behaviour -- dials, output,
  CV/CC, digital/analog/graph displays, min/max and auto-range.
- `client/ui/instruments/widgets.py`: `FittedReadout`, `AnalogGauge`,
  `ChartWithReadouts` and `nice_range` shared by every panel (still importable
  from `client.ui.control_panel`).
- `docs/INSTRUMENT_PANELS.md`: the contract and how to add a panel.

### 🐛 Fixed

- A panel's settle delay before the first poll was a `QTimer.singleShot` with
  a lambda holding the panel, which could fire into a widget that had since
  been deselected or destroyed. It is a child timer now, stopped by `stop()`
  and gone with its parent.
- `tests/unit/test_settings.py` constructed a second `QApplication` when GUI
  tests earlier in the run had already made one, which is a segfault at the
  next Qt call rather than an error. It reuses the existing instance.

### 📝 Changed

- The GUI tests that reached into `ControlPanel` for supply controls
  (`test_readouts`, `test_panel_reranging`, `test_readings_stop_on_404`,
  `test_analog_gauge`, `test_multi_server_equipment_list`,
  `test_equipment_lock_ui`) now construct `PowerSupplyPanel` directly or go
  through `ControlPanel.current_panel`.

---


## [2.3.2] - 2026-09-15

### 🐛 Fixed

- **After a server update the client had to be restarted before equipment
  showed as connected.** Refreshing waited on a single-flight guard: a boolean
  set before the request and cleared in a `finally`. qasync destroys pending
  tasks when the event loop is disturbed -- which a server update does by
  definition, since the server goes away mid-request -- and a task destroyed
  mid-await never runs its `finally`. The flag stayed set for the life of the
  process, so every later refresh returned at the guard and the list could
  never update again. The guard now records when the work started rather than
  that it is happening, and a slot still held long past any plausible round
  trip is taken anyway: the worst case is one overlapping refresh instead of a
  frozen panel. Applied to the equipment list, the Control tab's list, and the
  readings request, where a destroyed task would have stopped the numbers with
  nothing on screen to say why.

---


## [2.3.1] - 2026-09-15

### 🐛 Fixed

- **A bench that was already connected could not be reconnected.** After a
  server update the scope and both supplies refused to connect while the
  server was still holding all three open and serving readings from them.
  `connect` always opened the resource again, so pressing Connect asked
  libusb to claim an interface the server itself was holding; it answered
  `[Errno 16] Resource busy` and the API returned 500 -- a refusal that reads
  like broken hardware and is really the server colliding with itself. An
  instrument that is already open is returned as it stands, and an entry that
  is present but no longer connected is dropped first, since there a real
  open is wanted.
- **A websocket stream retried a command the instrument does not have.** A
  scope asked for `get_readings` logged "Unknown command" twice a second,
  indefinitely. Every pass sends the same command, so what fails once fails
  always; the stream stops now.
- **A timestamp in a broadcast disconnected the client.** `send_json` uses a
  plain `json.dumps`, which cannot encode the datetime in every readings
  payload, and the failure was raised inside the per-connection loop -- so a
  serialisation bug was read as the client hanging up and the websocket was
  dropped. The message is encoded once, before any connection is touched.

---




## [2.3.0] - 2026-09-15

### Added
- **Rigol digital multimeter drivers** (`server/equipment/rigol_multimeter.py`): `RigolDM3058`, `RigolDM3058E`
  and `RigolDM3068` built on a shared `RigolDMMBase`, implemented from the RIGOL DM3058/DM3068 programming
  guides (RIGOL command set). Full remote control: function selection (DCV/ACV/DCI/ACI/2W+4W resistance,
  frequency, period, capacitance, continuity, diode), manual/auto range, FAST/MEDIUM/SLOW rate, DC input
  impedance, AC filter, dual display, trigger source/interval/sample count, math (REL, statistics,
  pass/fail), beeper/brightness, interface settings read-back, `*TST?` self test, error queue.
- **Self-identification**: `*IDN?` parsing, USB VID/PID table entries for DM3058 (`1ab1:09c4`) and DM3068
  (`1ab1:0c94`), and multimeter-aware device-type inference in the VISA and mDNS scanners.
- **Acquisition & streaming**: multimeters implement `get_measurement(channel)`, `get_readings()` and
  `get_measurements()`, so acquisition sessions can name channels by function (`DCV,RES`) and the
  WebSocket `readings` stream works unchanged. New shared `MultimeterData` model and
  `MultimeterFunction` enum.
- **MockMultimeter** (`MOCK::DMM::n`) with the same command surface, registered in the default mock set,
  plus four default multimeter profiles.
- Tests: `tests/hardware/test_rigol_dmm.py` (scripted SCPI simulator), `tests/test_mock_multimeter.py`,
  and a DM3058/DM3068 case in `tests/unit/test_new_drivers.py`.
- Docs: `docs/RIGOL_DMM.md` protocol and driver notes.
- **Rigol catalogue scrape** (2026-09-15): all 421 documents on rigolna.com/support/downloads indexed (420 downloaded) in
  `docs/rigol/downloads_catalog.json`; 75 programming guides mined into
  `docs/rigol/programming_guide_inventory.json`; compatibility matrix and implementation order in
  `docs/RIGOL_EQUIPMENT_CATALOG.md`.
- `server/discovery/vendor_models.py`: prefix-anchored Rigol model table used by the VISA and mDNS
  scanners, so DSA/RSA/DSG/DHO/MHO/DNA/DM858 models classify correctly. USB PIDs harvested from the
  user guides (DG 0x0642, DSA 0x0960, DSG 0x0992/0x099C/0x0993, DP1116A 0x0E10, M300 0x0C80) added to
  the USB hardware table.
- Existing scope drivers now accept the whole family they already speak to: `RigolDS1104` for
  DS1054Z/DS1074Z/DS1104Z, `RigolMSO2072A` for all MSO2000A/DS2000A models.

- **Rigol family drivers** built from the scraped catalogue (each with a scripted-instrument test suite and a protocol doc in `docs/`):
  - `rigol_power_supply.py`: `RigolDPBase` + DP800/DP700/DP900/DP2000/DP1308A/DP1116A (21-model limits table, dialect table) — `docs/RIGOL_DP.md`
  - `rigol_modern_scope.py`: `RigolModernScopeBase` + 13 families (DHO800…DS80000, DS1000Z-E), 93-row model table, RAW chunked waveform transfer, screenshots — `docs/RIGOL_SCOPES.md`
  - `rigol_function_generator.py`: `RigolDGBase` (DG800/900/1000Z/2000/4000/5000) + `RigolDGProBase` (DG800/900 Pro, DG5000 Pro, DG6000), arb upload, modulation/sweep/burst, counter — `docs/RIGOL_DG.md`
  - `rigol_spectrum_analyzer.py`: `RigolSABase` + DSA800/DSA1000/RSA3000/RSA5000/RSA800/RSA6000, ASCII + REAL,32 trace parsing, markers, TG, RTSA mode — `docs/RIGOL_SA.md`
  - `rigol_rf_generator.py`: `RigolDSGBase` + DSG800/DSG3000(B)/DSG5000 — `docs/RIGOL_DSG.md`
  - `rigol_multimeter_dm858.py`: `RigolDM858`/`RigolDM858E` (standard SCPI DMM tree) — `docs/RIGOL_DM858.md`
  - `rigol_electronic_load.py`: `RigolDL3000Base` model table, `RigolDL3031A`, acquisition hook
  - `rigol_vna.py`: `RigolVNABase` + `RigolRSAN` (RSA3000N/5000N) and `RigolDNA6000` — `docs/RIGOL_VNA.md`
  - `rigol_daq.py`: `RigolM300` (scan lists, module detection, switch control) — `docs/RIGOL_M300.md`
- New equipment types `spectrum_analyzer` (shared enum), `rf_signal_generator`, `vector_network_analyzer`, `data_acquisition` end to end (shared/client/discovery enums, connect dialog, discovery API, safety defaults).
- New mocks: `MockFunctionGenerator` (`MOCK::FGEN::n`), `MockSpectrumAnalyzer` (`MOCK::SA::n`), `MockRFGenerator` (`MOCK::RFGEN::n`), `MockVNA` (`MOCK::VNA::n`), `MockDAQ` (`MOCK::DAQ::n`); all in the default mock set.
- Shared data models `FunctionGeneratorData`, `SpectrumData`, `RFGeneratorData`, `NetworkAnalyzerData`, `DataAcquisitionData`.
- `equipment/manager.py`: keyword-driver registry (`KEYWORD_DRIVER_CLASSES` / `MODEL_KEYWORDS`) replaces per-model `elif` chains for new families.
- `docs/DRIVER_AUTHORING.md`: the driver contract, integration hooks and per-class command vocabularies.
- Local manual archive: `~/Manuals/_archive/Rigol-manuals-2026-09-15.tar.gz` + SHA-256 manifest.

### Changed
- Model list in the connect dialog, `SUPPORTED_MANUFACTURERS`, default safety limits (`multimeter`),
  and the default `LABLINK_MOCK_EQUIPMENT_TYPES` now include multimeters.

### Fixed
- `BaseEquipment._query_binary()` passed `datatype=` as a keyword to `run_in_executor` and always raised `TypeError`.
- `BaseEquipment._determine_connection_type()` reported serial resources such as
  `ASRL/dev/ttyUSB0::INSTR` as USB because the path contains "USB"; serial is now matched first.
- Device-type inference could never classify Rigol `DM30xx` model strings as multimeters.

---

## [2.2.1] - 2026-09-15

### 🐛 Fixed

- **Selecting an oscilloscope on the Control tab stopped the other instruments
  connecting.** The tab drives power supplies, so it polls for volts and amps;
  a scope has no setpoints and the server answers 501 Not Implemented -- five
  times a second, forever. That storm saturates the event loop and starves the
  connect task, so the supplies on the same bench then fail to connect, which
  looks like an unrelated fault and is how it was found. The 2.1.4 fix stopped
  this for a missing instrument but treated every other status as transient,
  on the reasoning that a 5xx means the server is unwell and a supply should
  read through it. True of 500 and 503; not of 501, which is a permanent
  statement about the instrument. The two stay separate: a missing instrument
  is marked disconnected, while one that simply has no setpoints is left
  connected and says so, since calling a healthy scope disconnected would be a
  lie the Equipment tab repeats.

---

## [2.2.0] - 2026-09-14

One client, several benches. Built and tested against two Raspberry Pis with a
supply on each.

### ✨ Added

- **Connect to several servers at once.** The client held exactly one
  connection: connecting to a second Pi replaced the first, and its
  instruments vanished from the Equipment tab until you switched back. A test
  spanning two benches meant working the dropdown. The Equipment and Control
  tabs now fan out over every connected server and merge the results into one
  list, with the bench named on each row -- and only once there is more than
  one server, since on a single-Pi bench that suffix is noise on every row.
- **Any instrument can be driven without touching the dropdown.** Every
  reading, setpoint, lock and command resolves the connection from the
  selected instrument. Routing by the dropdown instead is the difference
  between setting 12 V on the supply you clicked and setting it on another
  bench.

### 🐛 Fixed

- **Tokens were stored under fixed keys rather than per server**, so a second
  login overwrote the first and the next start offered one server's token to
  the other. Single-server use hides this completely. Tokens are now keyed by
  host and port, and an existing unkeyed pair is adopted by the first server
  that asks, so upgrading does not read as a logout.
- **Equipment ids are only unique within a server.** Two Pis can mint the
  same one -- both test Pis report a 1902B, and the rows are identical apart
  from the bench. Selection and lookups now use a composite key, so the right
  instrument is selected rather than whichever was listed first.
- **One unreachable server no longer costs the others.** The fan-out is
  concurrent, so three switched-off servers cost one connect timeout rather
  than three; a server that does not answer contributes no rows and a
  tooltip rather than a modal dialog; and a refresh will not start while the
  previous one is still out, since a fan-out can outlast the five-second tab
  refresh.

### 📝 Changed

- **Disconnecting a server disconnects that server**, rather than whichever
  connection happened to be active.

---


## [2.1.5] - 2026-09-14

### 🐛 Fixed

- **The Disconnect button did nothing, and had done since v1.3.0.** That
  release made the handler a coroutine without marking it as a Qt slot, so
  clicking built a coroutine object and discarded it -- no request, no dialog,
  no error, not even a log line. Nothing on screen distinguishes a slot that
  silently never ran from one that ran and had nothing to do, which is how it
  survived four minor releases. An audit of every signal connection in the
  client found this was the only one, and that audit is now a test.

### 📝 Changed

- **The equipment details read as a table.** The grid gave neither column a
  stretch, so Qt split the spare width evenly and every value began at the
  halfway mark, a hand's width from the caption naming it. The captions now
  take their natural width and the values sit beside them.

---


## [2.1.4] - 2026-09-14

### 🐛 Fixed

- **A client could not connect to an instrument after the server updated.**
  The server issues a new equipment id each time it opens an instrument, so
  restarting it -- which every update does -- invalidates the id the client is
  still holding. The readings loop logged the resulting 404 and carried on,
  asking for a dead id ten times a second. That storm is not just noise in the
  log: it saturates the event loop and starves the connect task, so the
  reconnect that would have cleared it appears to hang instead. The symptom is
  an updated server, a healthy supply, and no way to reach it. A 404 now stops
  the readings, drops the cached "connected" status that would otherwise
  restart the timer on the next tick, and refreshes the equipment list.
  Timeouts and server faults still retry, since one slow serial reply should
  not stop a supply reading.

---


## [2.1.3] - 2026-09-14

Bench work. Everything here came from running the client against a real
Raspberry Pi with a B&K Precision 1685B and 9205B attached, and most of it
would not have been found any other way.

### ✨ Added

- **The bench survives a restart.** The equipment list lived only in memory, so
  every container restart emptied it -- and an upgrade restarts containers. The
  server now records what it has identified in `data/equipment_inventory.json`
  on the docker volume, and lists those alongside the instruments it currently
  holds open. Identity is remembered; connections are not, so nothing opens a
  port at boot and an instrument someone else is using is listed rather than
  seized. This matters most for a 1685B, which does not answer `*IDN?` at all:
  rediscovery means inferring it from a USB serial bridge, and two bridges look
  alike.
- **Min/Max tracking on the Control tab**, which is how a transient the live
  number skips past gets noticed. It prints to the resolution the instrument
  actually reports.
- **Auto Range** for the analog and graph modes. A 5 A supply sitting at 0.3 A
  uses a sixteenth of the dial, where a 10 mA change moves the needle about a
  pixel. The scale grows to fit what has been seen and holds there rather than
  falling back as the reading drops, which made a steady supply look like a
  climbing one.
- **The update warns what it will interrupt**, naming the instruments that are
  connected and will be dropped while the server restarts. An output left
  enabled stays enabled with nothing watching it.
- **The SSH host is offered from the connection**, with the SSH user remembered
  per server once an update has worked.

### 🐛 Fixed

- **Selecting equipment silently dropped the reading rate to 1 Hz** while the
  control still read 10 Hz. It restarted the timer at a hardcoded interval; a
  display that disagrees with the behaviour is worse than either being wrong.
  The rate is also remembered between sessions now.
- **The version and branch pickers could not see anything new.** Both listed
  only what the clone already had, so a release or a commit pushed five minutes
  earlier never appeared however many times Refresh was pressed. They fetch on
  the button now -- and only on the button: fetching on the five-second
  refresh, which is what the first attempt did, hitched the window every few
  seconds.
- **Connecting to an instrument failed with `'Equipment' object has no
  attribute 'resource_string'`.** The client model calls it `resource_name`;
  the code asked for the server's spelling. It had been hidden behind a 404
  storm that kept the connect task from ever being entered.
- **The Control tab polled instruments the server had not opened**, 404ing at
  the reading rate.
- **A background refresh raised modal error dialogs** from a five-second timer,
  interrupting the operator to report something unactionable -- and during an
  update not even a fault, since the server is down because we asked it to be.

### 📝 Changed

- **The analog display is a panel meter now**, after a Simpson Model 29: a
  shallow arc with the pivot low in the case, which spreads the scale over the
  full width and gives far more travel per unit than a round dial in the same
  box. It fills the window like the other two modes, where it used to sit at
  its minimum with room to spare. The case follows the theme -- grey bezel in
  both, cream card and black pointer in light, black card and green pointer in
  dark -- with the graduations and lettering printed in the same ink as the
  pointer.
- **The update log fills the window** instead of staying ten lines tall with a
  third of the screen empty beneath it.

---


## [2.1.2] - 2026-09-14

A deployed LabLink can now update itself. Until this release a Pi could not:
`/opt/lablink` was never a git checkout, so `lablink-update.sh` -- which
already did exactly the right thing -- had nothing to fetch into, and the
client's "Update Remote Server" button never touched the remote at all.

### 🐛 Fixed

- **"Update Remote Server" updated no remote.** It checked the ref out in the
  *local* clone, then ran `docker compose` on the remote in a directory named
  by the local git root -- so it moved the laptop's code and told the Pi to
  `cd C:/LabLinkTest`, which fails on the first command. It now drives the
  remote's own `lablink-update.sh` over SSH, takes the remote path as a field
  defaulting to `/opt/lablink`, and leaves this machine's checkout alone.
- **`lablink-update.sh` could not take a release.** It only handled branches,
  and `git pull origin v2.1.1` is not a thing; it now pulls only when HEAD is
  on a branch. It also prompted "Rebuild anyway?" with no way to answer over
  SSH, hanging the run forever, and it rebuilt stale code when the checkout
  failed while reporting success. It stops now.

### 📝 Changed

- **The image builder clones instead of unpacking a tarball**, and installs
  git, which it never did. An image built the old way produced a server that
  could only ever be reinstalled.
- **The deploy wizard clones from GitHub by default.** The deployed server
  gets a checkout and can update itself, and far less crosses the wire since
  the remote pulls directly. Sending the working tree is still available for
  testing uncommitted changes, now labelled as producing a server that cannot
  update itself rather than leaving that a surprise.
- **SSH is expected to work without a password.** The update runs with output
  captured, so a password prompt could never be answered; it now fails
  immediately and says so instead of blocking.

---


## [2.1.1] - 2026-09-14

The client self-update, finished. 2.1.0 shipped the pieces; running one on a
real install found the rest, and this is the first version whose update button
takes you somewhere and brings you back.

### 🐛 Fixed

- **The update button closed the client and left it closed.** It marked the
  update and called `sys.exit(0)`, on the theory that "the launcher should
  detect the flag" -- nothing watches for it, so the update sat unapplied
  until somebody started the client again by hand, while the dialog promised
  the application would restart. It restarts now.
- **The restart itself could not work from a shortcut.** The Start Menu and
  desktop entries go through `lablink_launch.pyw`, which sets `sys.argv[0]` to
  the module name `client.main` and hands it to `runpy`. The restart rebuilt
  that as `python client.main`, which Python reads as a file path and refuses
  with `can't open file`. A path is now run as a path and a module as
  `-m <module>`, from the checkout directory so it resolves wherever the
  shortcut started from.
- **A server update moved the client's own code.** Both server updates call
  `checkout_git_ref`, which operates on this clone -- the one the client runs
  from -- so updating a server changed the client too, and an older version
  downgraded the running client as a side effect. The remote path did it as
  readily as the local one: updating the Pi over SSH checked a ref out on the
  laptop first. Both now check the direction, warn with the commit count, and
  default to No.
- **A tag checkout left the UI unable to say what was running.**
  `git branch --show-current` prints nothing on a detached HEAD, so the status
  bar and the branch picker went blank at the moment the question mattered
  most -- right after an update moved the code. `describe_head` names the
  branch, or the tag, or the commit.

### 📝 Changed

- **The update button says something the instant it is pressed.** Checking the
  update direction fetches first, which is seconds on a slow link, and until
  it returned the button looked ignored -- so it got pressed again.
- **The update dialog describes what you see.** It said the application would
  close and reopen twice. It does restart twice, but the process in between
  applies the checkout and re-execs before it builds a window, so what a user
  sees is one close and one reopen. A test now pins that the update stays
  ahead of the window, because the alternative is the old UI flashing up
  mid-update.

---


## [2.1.0] - 2026-09-14

Everything since 2.0.0, which was 179 commits of work that never had a release
to sit in. The bulk of it is the Windows installer, the desktop client's
self-update, and a set of instrument-control faults found by running the client
against a real bench: a B&K Precision 1685B and a 9205B on one Raspberry Pi.

No breaking changes. Upgrading is a pull.

### ✨ Added

- **Console-free Windows launch.** Three Start Menu entries (client, launcher,
  server) plus a desktop shortcut, none of which flash a console window, and an
  uninstaller.
- **A scriptable installer.** `install-client.ps1` takes `-InstallPath`,
  `-NoShortcuts`, `-NoDesktopShortcut`, `-Unattended` and
  `-ReplaceExistingShortcuts`, so an install can be exercised against a
  throwaway directory instead of a real one.
- **OVP and OCP controls** for supplies whose drivers implement them, and
  visibly absent for the fixed-width models that have no such commands (#117).
- **Equipment locks are visible and attributable.** The holder is named, taking
  control is deliberate rather than automatic, and the strip stays live so an
  operator is told when control is taken away.
- **The operator chooses what an instrument is left doing** on disconnect
  rather than inheriting a default (#198).
- **A native Pi image builder and SD card writer on Windows**, including
  identifying a card by inserting it, and accepting a new host key after a Pi
  is reimaged.
- **USB diagnostics that actually inspect the bus.**
- **The launcher says which LabLink it is about to start** — version and branch
  (#191).
- **Make and Model columns on the Diagnostics health table.** Rows read as
  `ps_56fdd3df` before, which on a bench with two supplies identified nothing.
- **Live voltage and current across the top of the graph**, so the mode showing
  the trend also shows the present value.
- **Commit hashes in the update picker.** A branch name does not say which code
  it is; two installs both "on main" can be a week apart.

### 🐛 Fixed

- **Selecting an instrument could command it.** Re-ranging the controls for a
  newly selected supply clamped the previous one's setpoint into the new range,
  and Qt emits `valueChanged` for that clamp — straight into `set_current`.
  Choosing the 5 A 1685B after the 25 A 9205B sent the 1685B its full-scale
  current, from a number nobody typed.
- **Readings claimed precision the instrument never sent.** A supply resolving
  to 0.01 A was displayed as `0.300 A`. Capabilities now carry the resolution
  and the client prints to it.
- **The digital readout rendered at 12px while the code asked for 48pt.** A Qt
  stylesheet beats `setFont`, and the application sheet sets
  `QWidget { font-size: 9pt }`. The readouts now fill their panel.
- **Status colours made the status unreadable.** Pale fills with no text colour
  left the dark theme's own pale text on them at about 1.2:1; "healthy" was
  effectively invisible. Every pair now clears WCAG AA.
- **The client self-update never came back.** It flushed `sys.stdout` while
  running under `pythonw.exe`, where there is no console and `sys.stdout` is
  `None` — after the new code was checked out and the flag cleared.
- **An "update" could silently install an older client.** The picker offers
  tags beside branches, and selecting the only tag moved an install 174 commits
  backwards without a word. It now says so, with the count, defaulting to No.
- **The WebSocket never authenticated.** The server closes `/ws` with 4001
  unless the token is a query parameter, and the client never sent one, so on a
  secured server the socket retried every five seconds indefinitely.
- **Sessions went quietly unauthorized.** Access tokens last 30 minutes and
  nothing refreshed them mid-session, so half an hour in every authenticated
  call began failing while the window still showed a connection.
- **The advertised one-liner install could never have worked**, and a UTF-8 BOM
  would have broken it again.
- **Every install dirtied the clone**, which then blocked `uninstall -Force`.
- **The installer declared success over an environment that could not import.**
- **`verify-install` hung forever on a message box nobody could see.**
- **A scoped uninstall removed shortcuts it did not create.**
- **The 9205B carried another model's limits** (#116).
- **Discovery and the health monitor fought connected instruments for the
  wire** (#166).
- **Locale-dependent file and console I/O broke on Windows** (#192).
- **Two unreachable alarm endpoints**, found by making their tests real.
- **Default profiles reset on every boot** instead of seeding once.
- **Three code paths reported success for work they had not done.**

### 📝 Changed

- **One blue.** Panels that styled their own buttons used a different blue from
  the application sheet; those local rules are gone, so the accent is defined
  once.
- **The system panel follows the theme.** It carried 46 colour literals and no
  theme import, so in dark mode its section boxes stayed near-white with pale
  text over them. The login dialog had the same fault.
- **The chart follows the theme** instead of rendering a white card inside a
  dark application.
- **One spelling of the manufacturer.** The fixed-width drivers said
  "BK Precision" where the registry says "B&K Precision", which became visible
  once the health table gained a manufacturer column.
- **`#Requires -Version 5.1` is armed.** It had a space after the `#`, making it
  a comment, so nothing checked the PowerShell version at all.

---


## [2.0.0] - 2026-09-01

A deliberate compatibility break. It exists to move the entire dependency stack
to current releases in one step, and it was validated end to end on real
hardware — a Raspberry Pi 5 running a freshly built image with a B&K Precision
1902B attached.

**Upgrading from 1.x? Read [docs/BREAKING_CHANGES_2.0.md](docs/BREAKING_CHANGES_2.0.md) first.**

### 💥 Breaking

- **Python 3.12 is now the minimum** (was 3.11; `setup.py` still claimed 3.8).
  Forced by numpy 2.5 and scipy 1.18, which both require it. The server is
  unaffected in practice — it runs in Docker on `python:3.13-slim`. The desktop
  client runs natively and does need 3.12+.
- **Every user is logged out on upgrade.** Access tokens are now bound to a
  server-side session, which is what makes logout and password change able to
  revoke them. Tokens issued by 1.x carry no `session_id` and are refused.
- **SSH deployment no longer accepts `ssh-rsa` (RSA/SHA-1) host keys.** paramiko
  5.0.0 removes them, fixing PYSEC-2026-2858. A device offering only an
  `ssh-rsa` host key can no longer be deployed to; regenerate its host keys with
  `sudo ssh-keygen -A`. Current Raspberry Pi OS is unaffected.
- **The WebSocket port is retired.** `/ws` has always been a route on the API
  server; `LABLINK_WS_PORT` configured a port nothing ever bound. It is now
  accepted and ignored so an existing `.env` does not break startup.
- **Pi images are built on Debian Trixie** (13) instead of Bookworm (12).

### ✨ Added

- Live hardware acceptance suite (`tests/hardware/test_live_pi.py`) — 29 tests
  covering deployment, SSH, the auth lifecycle, equipment discovery and
  readings, WebSocket auth and file-descriptor stability. Skipped unless
  configured, so CI is unaffected.
- B&K Precision auto-detection: a model registry covering 30 families, generic
  SCPI drivers, and a serial probe that finds instruments VISA cannot enumerate
  (USB-CDC models, and legacy supplies that answer no `*IDN?`).
- `scripts/diagnose_bk_discovery.py`, a layer-by-layer discovery diagnostic that
  reports which stage dropped an instrument.
- Pi images can be built from any git branch (`LABLINK_BRANCH`) and from either
  Raspberry Pi OS Lite or Full (`PI_OS_VARIANT`), both exposed in the client's
  image-builder wizard.
- Persistent failed-login tracking, so account lockout survives a restart.
- OAuth2 `state` is now verified and single-use, closing a login-CSRF hole.

### 🐛 Fixed

- **Device discovery returned zero devices on any established install.** A
  function-local `datetime` import in `lifespan()` turned a nested discovery
  callback's reference into an unbound closure, so every scan raised.
- **MFA backup codes could never be verified.** Hashing kept the code as
  generated while verification stripped the hyphen and upper-cased it, so the
  two never matched and account recovery was impossible. Codes stored before
  this release remain unusable and must be regenerated.
- **Every backup failed.** `create_backup()` verified the backup before
  registering it, so verification always raised "Backup not found" — and
  verification is on by default. Backup IDs could also collide within the same
  second, silently overwriting metadata.
- **Pi images shipped a hardcoded application admin password.** The build-time
  `LABLINK_ADMIN_PASSWORD` never reached the first-boot script, which fell back
  to a built-in default and echoed it to the system journal.
- **A file-descriptor leak in `DatabaseManager`** — 13 methods closed their
  connection only on success. Measured at 200 leaked descriptors across 200
  failing calls.
- **Blocking SQLite calls stalled the event loop** across four subsystems.
- **The GUI froze during live monitoring.** Timer-driven polling called the
  synchronous HTTP client directly on the Qt thread.
- **SSH host-key acceptance was unreachable on non-standard ports**, so a host
  could never be trusted through the deploy wizard.
- **`server/.env` was tracked in git and baked into the server image**, where it
  overrode host configuration invisibly.
- The firmware update endpoint returned 500; a bare ASRL port listing outranked
  a real instrument identification; and the JWT secret was regenerated on every
  restart when unset, invalidating all tokens.

### 📝 Changed

- Every dependency pinned to a current release: numpy 2.5.2, pandas 3.0.5,
  scipy 1.18.1, paramiko 5.0.0, websockets 17.1, bcrypt 5.0.0, psutil 7.2.2,
  PyQt6 6.11.0, pytest 9.1.1, pyvisa 1.16.2, FastAPI 0.141.1. `pip-audit`
  reports no known vulnerabilities across the full stack.
- Pi images are ~35% faster to burn: a flat 2GB of padding that first-boot
  filesystem growth immediately superseded is now 256MB.
- CI covers Python 3.12 and 3.13.
- The test suite went from ~95 failures and a run that hung indefinitely to
  **1127 passing**. Many tests had drifted out of sync with the code; others
  silently skipped themselves for features that were implemented, which is how
  several of the bugs above survived.

### 🔒 Security

- Access tokens are revocable; logout, password change and admin reset take
  effect immediately rather than leaving a token valid for up to 7 days.
- OAuth2 `state` verification, persistent lockout, and a JWT secret that
  survives restarts.
- `sudo` removed from the server runtime image; environment files can no longer
  be baked into images.

---

## [1.2.4] - 2025-12-09

### ✨ Added
- **Issue #157**: Windows installation improvements
  - Added `install-client.bat` wrapper for one-click installation (handles PowerShell execution policy)
  - Comprehensive Windows installation guide (WINDOWS_INSTALL.md) with troubleshooting
  - Added `lablink-client.bat` launcher script for easy client execution
  - All three installation methods documented (batch wrapper, PowerShell direct, remote install)

### 🐛 Fixed
- **Issue #157**: Fixed PowerShell execution policy blocking Windows installation
  - Windows users no longer see "scripts is disabled on this system" error
  - Batch wrapper automatically bypasses execution policy for installation
  - Updated documentation to explain Windows security features and solutions

### 📝 Changed
- Updated `.gitignore` to exclude `.claude/` and `*.log` files
- Updated README.md with prominent Windows installation section
- Fixed documentation to show correct launcher script paths

---


## [1.2.3] - 2025-12-08

### 🐛 Fixed
- **Issue #155**: Fixed server discovery performance issues (~50% discovery rate)
  - Servers now properly broadcast themselves via mDNS/Zeroconf on startup
  - Added mDNS server broadcasting to main.py startup lifecycle
  - Improved hostname detection to use FQDN when available
  - Discovery should now find ~100% of LabLink servers on local network
  - Properly stops mDNS service during shutdown to prevent resource leaks

---


## [1.2.2] - 2025-12-07

### 🐛 Fixed
- **Issue #126**: Fixed Pi deployment systemd service conflicts after SSH Docker deployment
  - Automatically cleans up old Python-mode `lablink.service` that conflicts with Docker deployment
  - Creates and activates `lablink-docker.service` for proper container auto-start on boot
  - Service now properly shows "active (exited)" state after deployment
  - Containers auto-start on reboot via systemd service

### ✨ Added
- **Production-Standard Deployment Path**: Docker deployments now default to `/opt/lablink` (follows Linux FHS)
  - Automatic sudo support for `/opt` paths (creates directory, sets ownership)
  - Smart path switching when toggling between Docker/Python deployment modes
  - Tar upload to `/tmp` for `/opt` paths to avoid permission issues
- **Service Status Indicator**: Clean status display in deployment wizard
  - Real-time service health monitoring (Unknown → Checking → Operational/Not Running)
  - Color-coded status: green (operational), red (not running), orange (checking), gray (unknown)
  - Automatic verification after deployment completes
- **Improved Diagnostic Script**: Added clarifications for SSH deployments
  - "Expected if this is an SSH Docker deployment" for missing first-boot log
  - "Expected if this is an SSH deployment" for first-boot setup not complete
  - Reduces confusion about expected missing components in SSH deployments

### 📝 Changed
- **Deployment Wizard UX**: Simplified and streamlined deployment interface
  - Removed verbose systemctl output window
  - Added compact service status indicator below deployment log
  - Reduced wizard height (880px → 600px) for cleaner interface
  - Deployment logs remain scrollable for full history
- **Default Paths by Mode**:
  - Docker mode: `/opt/lablink` (production)
  - Python mode: `/home/<username>/lablink` (development)
  - Automatic path updates when switching deployment modes

### 🔧 Technical Details
- Service type: oneshot with RemainAfterExit=yes
- Service dependencies: docker.service, network-online.target
- Diagnostic script handles both Pi image and SSH deployment methods
- Parses systemctl output including ANSI color codes

---

## [1.2.1] - 2025-12-07

### 🔒 Security
- **Fixed 13 Dependabot security vulnerabilities** (5 high, 7 medium, 1 low)
- **requests** 2.31.0 → 2.32.4: Fixed CVE-2024-47081 (.netrc credentials leak), CVE-2024-35195 (Session verify=False persistence)
- **aiohttp** 3.9.1 → 3.12.14: Fixed 6 CVEs including:
  - CVE-2024-23334 (High): Directory traversal vulnerability
  - CVE-2024-30251 (High): DoS on malformed POST requests
  - CVE-2024-52304 (Medium): Request smuggling via chunk extensions
  - CVE-2024-27306 (Medium): XSS on static file index pages
  - CVE-2024-23829 (Medium): HTTP parser lenient separators
  - CVE-2025-53643 (Low): Request/Response smuggling via chunked trailers
- **node-forge** 1.2.1 → 1.3.3: Fixed 3 CVEs:
  - CVE-2025-12816 (High): ASN.1 Validator Desynchronization
  - CVE-2025-66031 (High): ASN.1 Unbounded Recursion
  - CVE-2025-66030 (Medium): ASN.1 OID Integer Truncation
- **glob** 10.4.2 → 10.5.0: Fixed CVE-2025-64756 (High): Command injection via -c/--cmd
- **Removed scapy** 2.5.0: Pickle deserialization RCE vulnerability with no patch available (package unused in codebase)

### 📝 Changed
- **Dependabot Configuration**: Implemented dependency grouping to reduce PR spam
  - Groups minor/patch updates into single PRs per ecosystem
  - Security updates remain separate for visibility
  - Major version updates isolated for careful review
  - Reduced PR limits: Python (10→5), Docker (5→3), GitHub Actions (5→3)
- **Repository Cleanup**: Closed 29 legacy Dependabot PRs and deleted 36 obsolete branches
- **NPM Security**: npm audit shows 0 vulnerabilities after updates

### 📚 Documentation
- Added comprehensive security update documentation (`docs/security/SECURITY_UPDATE_2025-12-06.md`)
- Documented all CVE fixes with references and impact assessment
- Updated Dependabot configuration with detailed grouping strategy

---


## [1.2.0] - 2025-12-06

### ✨ Added
- **Server Update System**: Complete update management with stable/development modes (#114, #118, #119)
  - Git-based version tracking and branch management
  - Client-driven update workflow (client manages server updates)
  - Automatic and manual Docker rebuild options
  - Local and remote (SSH) server update support
  - Progress tracking with visual feedback
- **Smart Branch Filtering**: Intelligent branch display system (#120)
  - Filters out dependabot and automated branches by default
  - Shows only active branches (commits in last 3 months)
  - Sorts branches by most recent commit
  - "Show all branches" toggle for complete view
- **UI Consolidation**: Merged duplicate server update sections (#120)
  - Single unified "Server Updates" interface
  - Reduced window height by 30-40%
  - Progress bar for local and remote update operations
- **Enhanced Dropdown Visibility**: System-wide dropdown menu styling improvements (#120)
  - Light blue hover states for better readability
  - Consistent black text for maximum contrast
- **Version Management System**:
  - Single-source versioning from VERSION file
  - Automated version bump script (`scripts/bump_version.py`)
  - Comprehensive versioning documentation

### 🐛 Fixed
- SSH deployment wizard Next button not working (#121)
- Multiple device discovery issues (#108)
- Client login crash on connection (#106)
- Ubuntu deployment configuration issues (#105)

### 📝 Changed
- Version system unified across all components (server, client, launcher)
- Copyright updated to © 2025
- All components now read from single VERSION file
- CHANGELOG retroactively completed with full project history

### 📚 Documentation
- Created `docs/VERSIONING.md` - Complete version management guide
- Updated all documentation to reflect v1.2.0
- Standardized copyright notices

---

## [1.0.1] - 2025-11-28

### ✨ Added
- **Equipment Control Panel**: Interactive control interface for equipment (#104)
- **GUI System Launcher**: Comprehensive launcher with health checks and diagnostics (#70-74)
  - Environment compatibility checking
  - Dependency verification and installation
  - LED status indicators
  - One-click server/client launching
  - Easter egg debug mode with branch selector
  - Dark theme support
  - Auto-close functionality for launch messages
- **Raspberry Pi Image Builder**: Automated Pi system image creation (#75-76)
  - SD card writer GUI tools
  - One-click deployment system
- **Waveform Analysis Tools**: Advanced signal processing and analysis (#79)
- **Automated Test Sequence Builder**: Visual test automation system (#80)
- **Remote Firmware Update**: Over-the-air firmware update capability (#81)
- **Equipment Diagnostics System**: Comprehensive equipment health monitoring (#84-87)
- **WebSocket Integration Completion**: Real-time event streaming across all panels (#77)
- **Multi-Server Management**: Support for managing multiple server instances
- Rigol DS1102D oscilloscope support
- Async equipment discovery improvements
- Equipment profile visual styling and UI enhancements

### 🐛 Fixed
- Equipment readings 404 errors (#99, #100)
- BK Precision equipment reading issues (#101)
- Disconnect UI improvements (#102)
- Client-server communication on Raspberry Pi (#88-91)
- Pi discovery service improvements (#92)
- Deterministic equipment ID generation to prevent 404 errors
- Optional aiohttp import to fix CI tests
- Equipment control panel crash on missing equipment
- Various UI styling and border definition issues

### 📝 Changed
- Updated Ubuntu setup and deployment guides (#68-69)
- Enhanced launcher title bar and UI polish (#74)
- Improved testing infrastructure and GUI launcher reliability (#70-73)
- Optimized package checking performance in launcher
- Improved visual definition with borders and styling

### 📚 Documentation
- Comprehensive Ubuntu 24.04 setup guide
- Deployment wizard documentation
- Launcher usage guides

---

## [1.0.0] - 2025-11-14

### 🎉 **First Production Release!**

LabLink v1.0.0 is the first production-ready release of the Laboratory Equipment Link management system. This release includes comprehensive test coverage, security hardening, performance benchmarking, and production-ready features for managing laboratory equipment via a unified API.

---

### ✨ Major Features

#### Equipment Management
- **Universal Equipment Interface**: Unified API for controlling diverse lab equipment
- **Multi-Vendor Support**: Oscilloscopes, power supplies, electronic loads, spectrum analyzers
  - Rigol: DS1102D, DS1104Z, DL3021A, MSO5000 series
  - BK Precision: 1685B, 9130B, 9205B, 9206B, 1902B
- **Equipment Discovery**: Automatic network equipment discovery via VISA, Zeroconf, and GPIB
- **Real-time Monitoring**: Live equipment status updates via WebSocket
- **Command History**: Complete audit trail with execution times
- **Equipment Profiles**: Save/load configurations

#### PyQt6 GUI Client
- **Modern Desktop Application**: Full-featured Qt6 client
- **Real-Time Dashboards**:
  - Equipment monitoring panel
  - Data acquisition panel with live plotting
  - Alarm management panel
  - Scheduled operations panel
  - System diagnostics panel
- **Cross-Platform**: Windows, Linux, macOS support
- **Dark/Light Themes**: User-selectable themes
- **WebSocket Streaming**: <100ms latency for real-time events

#### Data Acquisition & Analysis
- **Multi-Channel Acquisition**: Simultaneous data collection from multiple sources
- **Buffering System**: Configurable circular and sliding window buffers
- **Export Formats**: CSV, JSON, HDF5, NPY, MAT
- **Waveform Analysis**: FFT, filtering, resampling, peak detection
- **Live Visualization**: Real-time plotting with PyQtGraph
- **Automated Testing**: Sequence builder for test automation

#### Security & Authentication
- **🔒 Multi-Factor Authentication (MFA/2FA)**: TOTP-based 2FA with QR code provisioning
- **🔐 Role-Based Access Control (RBAC)**: Granular permissions system
- **🔑 OAuth2 Integration**: Google, GitHub, Microsoft authentication
- **📱 API Key Authentication**: Long-lived keys for automation
- **🛡️ Session Management**: Secure session handling with invalidation
- **🚨 Login Attempt Tracking**: Automatic account lockout
- **🔒 Password Security**: Bcrypt hashing with configurable work factors

#### Data Management
- **SQLite Database**: Embedded database for equipment data and logs
- **Backup System**: Automated and on-demand backups with compression
- **Configuration Management**: Centralized configuration for all services
- **Command Logging**: Complete history of all equipment interactions
- **Database Integration**: Full CRUD operations with migrations

#### API & Integration
- **RESTful API**: Comprehensive REST API with OpenAPI/Swagger documentation
- **WebSocket Support**: Real-time bidirectional communication
- **MQTT Integration**: IoT device integration via MQTT protocol
- **Mobile-Ready**: 100% mobile-compatible API (validation complete)
- **Equipment Abstraction**: Vendor-agnostic equipment control layer

#### Advanced Features
- **Alarm & Notification System**:
  - Multiple notification channels (Email, Webhook, SMS)
  - Configurable alarm conditions
  - Alarm history and acknowledgment
  - WebSocket real-time alerts
- **Scheduled Operations**:
  - Cron-based job scheduling
  - APScheduler integration
  - Job history and status tracking
  - Pause/resume/cancel controls
- **Performance Monitoring**:
  - System metrics collection (CPU, memory, network)
  - Equipment performance tracking
  - Historical trend analysis
  - Threshold-based alerting
- **Calibration Management**:
  - Equipment calibration tracking
  - Calibration schedule management
  - Certificate storage and retrieval
- **Equipment Locking**:
  - Multi-user access control
  - Exclusive/observer session modes
  - Lock timeout handling

---

### 🔒 Security

#### Phase 3: Production Hardening (Completed)

**Vulnerability Fixes:**
- **FIXED**: FastAPI ReDoS vulnerability (PYSEC-2024-38) - Upgraded to v0.115.0+
- **FIXED**: Starlette DoS vulnerability (GHSA-f96h-pmfr-66vw) - Fixed via FastAPI upgrade
- **FIXED**: Starlette file upload DoS (GHSA-2c2j-9gv5-cj73) - Fixed via FastAPI upgrade
- **DOCUMENTED**: pip 24.0 vulnerability (dev/CI only, acceptable risk)
- **DOCUMENTED**: ecdsa timing attack (orphaned dependency, not used)

**Security Enhancements:**
- ✅ Security scans now **BLOCKING** in CI/CD pipeline
- ✅ Automated vulnerability detection with pip-audit
- ✅ Comprehensive security best practices documentation
- ✅ Secure defaults for all authentication mechanisms
- ✅ Security audit process established

**Security Documentation:**
- `docs/security/best_practices.md` - 587 lines of security guidelines
- `docs/security/phase3_security_audit.md` - Complete vulnerability assessment
- Covers: Dependency management, secure coding, auth/authz, data protection, API security, secrets management, CI/CD security, deployment security, incident response

---

### 🧪 Testing & Quality

#### Phase 2: Test Coverage Sprint (Completed)

**Test Suite:**
- **499 tests passing** (core + integration + performance)
- **54 tests skipped** (hardware-dependent, expected)
- **10 performance benchmarks** (all passing)
- **Test coverage**: 52-54% overall, 70%+ on critical paths
  - Security modules: ✅ Well-tested
  - Data models: ✅ Well-tested
  - Database managers: ✅ Well-tested
  - API endpoints: ✅ Tested
  - Hardware drivers: ⚠️ Skipped (requires equipment)

**Test Categories:**
- ✅ Unit tests (component isolation)
- ✅ Integration tests (cross-module workflows)
- ✅ API tests (endpoint validation)
- ✅ Performance benchmarks (baseline metrics)
- ✅ Security tests (auth, RBAC, MFA)
- ✅ Model validation tests (Pydantic)
- ✅ Database tests (CRUD operations)
- ✅ WebSocket tests (real-time events)

**CI/CD Pipeline:**
- ✅ GitHub Actions automated testing
- ✅ Dependency scanning (Dependabot)
- ✅ Security scanning (pip-audit)
- ✅ Code quality checks
- ✅ Test coverage reporting

**Testing Infrastructure:**
- Mock equipment utilities for testing without hardware
- Comprehensive test fixtures and factories
- Property-based testing with Hypothesis
- Async test support with pytest-asyncio

---

### ⚡ Performance

**Baseline Metrics Established:**
- Equipment control latency: <50ms
- API response time: <100ms (95th percentile)
- WebSocket message latency: <100ms
- Database query time: <10ms (simple), <100ms (complex)
- Data acquisition throughput: 10,000+ samples/second
- Memory usage: <200MB baseline, <500MB under load

**Profiling Infrastructure:**
- cProfile integration for performance analysis
- Memory profiling with tracemalloc
- Critical path identification
- Bottleneck detection

---

### 🔧 Deployment & Operations

**Deployment Options:**
- **Docker**: Multi-container deployment with docker-compose
- **Native**: Direct installation on Linux/Windows/macOS
- **Raspberry Pi**: Dedicated Pi server deployment
- **Hybrid**: Mix of deployment methods

**Docker Support:**
- Server container with VISA/USB support
- Web dashboard container (Nginx)
- Health checks and auto-restart
- Volume mounting for data persistence
- Network configuration for equipment access

**Raspberry Pi Support:**
- Optimized for Raspberry Pi 4/5
- Hardware access (USB, GPIO, Serial)
- Automatic service startup
- SD card image builder
- Remote deployment wizard

**Configuration:**
- Environment-based configuration (.env)
- Configuration validation with Pydantic
- Secure secrets management
- Hot-reload support for development

---

### 📚 Documentation

**Comprehensive Documentation:**
- ✅ `README.md` - Project overview and quick start (updated to v1.0.0)
- ✅ `CHANGELOG.md` (this file) - Version history
- ✅ `TESTING.md` - Testing guide and standards
- ✅ `TESTING_INFRASTRUCTURE.md` - Test infrastructure details
- ✅ `DEPLOYMENT.md` - Deployment instructions
- ✅ `ROADMAP.md` - Project roadmap and planning
- ✅ `SAFETY_SYSTEM.md` - Safety features documentation
- ✅ `LOCK_SYSTEM.md` - Equipment locking guide
- ✅ `MOCK_EQUIPMENT_GUIDE.md` - Testing without hardware
- ✅ `docs/security/best_practices.md` - Security guidelines
- ✅ `docs/security/phase3_security_audit.md` - Security audit
- ✅ `docs/USER_GUIDE.md` - End-user documentation
- ✅ API documentation (OpenAPI/Swagger) - Interactive API docs

**Code Documentation:**
- Comprehensive inline documentation
- Type hints throughout codebase
- Docstrings for all public APIs
- Architecture decision records

---

### 🎯 Quality Metrics

| Metric | Value | Status |
|--------|-------|--------|
| **Test Coverage** | 52-54% | ✅ Acceptable |
| **Tests Passing** | 499/553 (90%) | ✅ Good |
| **Security Vulnerabilities** | 0 critical, 0 high | ✅ Secure |
| **API Endpoints** | 150+ | ✅ Comprehensive |
| **Documentation Pages** | 20+ | ✅ Well-documented |
| **Performance Benchmarks** | 10/10 passing | ✅ Performant |

---

### 🚀 Getting Started

```bash
# Quick Start (Ubuntu/Debian)
git clone https://github.com/X9X0/LabLink.git
cd LabLink
python3 setup.py --auto

# Start server
cd server && python3 main.py

# Start client (in new terminal)
python3 client/main.py

# Or use the GUI launcher
python3 lablink.py
```

**Docker Quick Start:**
```bash
docker-compose up -d
```

**Raspberry Pi Quick Start:**
```bash
# Use the deployment wizard
python3 lablink.py  # Select "Deploy to Raspberry Pi"
```

---

### 📦 Dependencies

**Server:**
- Python 3.10+
- FastAPI 0.115.0+
- PyVISA 1.13.0+
- NumPy 1.24.0+
- WebSockets 12.0+
- APScheduler 3.10.0+

**Client:**
- Python 3.10+
- PyQt6 6.6.0+
- PyQtGraph 0.13.0+
- Matplotlib 3.8.0+

**Development:**
- pytest 7.4.0+
- black (code formatting)
- isort (import sorting)
- pip-audit (security scanning)

---

### ⚠️ Breaking Changes

None - This is the first production release.

---

### 🔄 Migration Guide

This is the first production release. For future upgrades, see version-specific upgrade guides.

---

### 🙏 Acknowledgments

LabLink v1.0.0 represents months of development effort and represents a mature, production-ready laboratory equipment management system.

**Key Contributors:**
- System architecture and design
- Equipment driver development
- Security hardening
- Testing infrastructure
- Documentation

**Technologies:**
- FastAPI - Modern, fast web framework
- PyQt6 - Professional desktop GUI framework
- PyVISA - VISA instrument control
- SQLite - Embedded database
- WebSocket - Real-time communication
- Docker - Containerized deployment

---

## [0.27.0] - 2025-11-13

### ✨ Added
- **Multi-Factor Authentication (MFA/2FA)**:
  - TOTP-based two-factor authentication
  - QR code generation for authenticator apps
  - Backup codes for account recovery
  - MFA enforcement options (optional/required)
  - MFA status tracking and management
- **OAuth2 Authentication Providers**:
  - Google OAuth2 integration
  - GitHub OAuth2 integration
  - Microsoft OAuth2 integration
  - Social login support
- **JWT Authentication in PyQt6 Client**:
  - Token-based authentication
  - Automatic token refresh
  - Secure token storage
- Web dashboard real-time updates with Chart.js
- Equipment profile management UI in web dashboard
- Enhanced web dashboard with live data visualization

### 🐛 Fixed
- Authentication token handling
- Session persistence issues
- OAuth2 callback handling

### 📝 Changed
- Updated ROADMAP to reflect v0.26.0 and v0.27.0 completion
- Repository documentation cleanup
- README updated to v0.27.0

### 🔒 Security
- Implemented secure token storage
- Added MFA security layer
- OAuth2 security best practices

---

## [0.26.0] - 2025-11-13

### ✨ Added
- **Enhanced Web Dashboard**:
  - Real-time WebSocket updates
  - Chart.js live data visualization
  - Equipment profile management UI
  - Interactive equipment control interface
  - Responsive design for mobile/tablet
- Equipment status monitoring
- Live data plotting in web interface

---

## [0.24.0] - 2025-11-13

### ✨ Added
- **MVP Web Dashboard**:
  - Login and authentication system
  - API client integration
  - Equipment control interface
  - Foundation for web-based management
- Web dashboard foundation with login/auth

### 📝 Changed
- Updated ROADMAP for v0.24.0 MVP Web Dashboard

---

## [0.23.0] - 2025-11-13

### ✨ Added
- **Advanced Security System**:
  - Role-based access control (RBAC) foundation
  - API key authentication
  - Session management improvements
  - Security audit logging

---

## [0.22.0] - 2025-11-13

### ✨ Added
- **Equipment Discovery System**:
  - Automatic VISA equipment detection
  - Zeroconf/mDNS service discovery
  - GPIB device scanning
  - Network equipment discovery
  - USB device enumeration

---

## [0.21.0] - 2025-11-13

### ✨ Added
- **Backup & Restore System**:
  - Database backup with compression
  - Configuration backup
  - Automated backup scheduling
  - Point-in-time restore capability
  - Backup verification

---

## [0.20.0] - 2025-11-13

### ✨ Added
- **Automated Test Sequences**:
  - Test sequence builder
  - Step-by-step test execution
  - Test result logging
  - Pass/fail criteria evaluation
  - Test report generation
- Mock equipment utilities for testing
- Auto-registration for mock devices

### 🐛 Fixed
- Test sequence execution order
- Mock equipment initialization

### 📝 Changed
- Updated ROADMAP with v0.19.0 and v0.20.0

---

## [0.19.0] - 2025-11-13

### ✨ Added
- **Enhanced Calibration Management**:
  - Calibration certificate storage
  - Calibration schedule tracking
  - Due date notifications
  - Calibration history
  - Certificate upload/download

---

## [0.18.0] - 2025-11-13

### ✨ Added
- **Database Integration System**:
  - SQLite database backend
  - Equipment configuration storage
  - Data acquisition history
  - Command logging
  - User session tracking
  - Database migrations support

---

## [0.17.0] - 2025-11-13

### ✨ Added
- **Data Analysis Pipeline System**:
  - Signal filtering (lowpass, highpass, bandpass)
  - Resampling and decimation
  - Peak detection algorithms
  - Statistical analysis
  - Data transformation utilities

---

## [0.16.0] - 2025-11-13

### ✨ Added
- **Waveform Capture & Analysis System**:
  - Oscilloscope waveform capture
  - FFT analysis
  - Waveform storage
  - Export to multiple formats
  - Waveform comparison tools

---

## [0.15.0] - 2025-11-13

### ✨ Added
- **Enhanced WebSocket Features**:
  - Equipment event streaming
  - Alarm event broadcasting
  - Scheduler job notifications
  - Connection management
  - Reconnection handling

---

## [0.14.0] - 2025-11-13

### ✨ Added
- **Scheduled Operations with Full Integration**:
  - Enhanced job scheduler
  - Recurring job support
  - Job dependency management
  - Execution history
  - Error handling and retry logic

---

## [0.13.0] - 2025-11-13

### ✨ Added
- **Performance Monitoring System**:
  - CPU usage tracking
  - Memory monitoring
  - Network statistics
  - Equipment performance metrics
  - Historical performance data
  - Performance alerts

---

## [0.12.0] - 2025-11-13

### ✨ Added
- **Comprehensive Equipment Diagnostics System**:
  - Self-test capabilities
  - Health check endpoints
  - Diagnostic logging
  - Error code interpretation
  - Equipment status monitoring

---

## [0.11.0] - 2025-11-13

### ✨ Added
- **Enhanced Alarm & Notification System**:
  - Multiple notification channels
  - Email notifications
  - Webhook notifications
  - SMS notifications (via webhook)
  - Alarm acknowledgment
  - Alarm history tracking

### 📝 Changed
- Updated roadmap for v0.11.0 completion

---

## [0.10.1] - 2025-11-13

### ✨ Added
- Enhanced logging capabilities
- Log analysis utilities
- User identification in logs

### 📝 Changed
- Updated roadmap for v0.10.1 logging completion

---

## [0.10.0] - 2025-11-08

### ✨ Added
- **Equipment Diagnostics System**:
  - Equipment health monitoring
  - Diagnostic status reporting
  - Self-test functions
  - Error detection and reporting

---

## [0.9.0] - 2025-11-08

### ✨ Added
- **Scheduled Operations System**:
  - Job scheduling with APScheduler
  - Cron-based schedules
  - One-time and recurring jobs
  - Job management API
  - Execution history

---

## [0.8.0] - 2025-11-08

### ✨ Added
- **Alarm & Notification Systems**:
  - Alarm condition monitoring
  - Threshold-based alerts
  - Alarm configuration
  - Notification delivery

---

## [0.7.0] - 2025-11-08

### ✨ Added
- **Advanced Logging System**:
  - Structured logging
  - Log rotation
  - Multiple log levels
  - Log file management

---

## [0.6.0] - 2025-11-08

### ✨ Added
- **Data Acquisition & Logging System**:
  - Continuous data acquisition
  - Triggered acquisition modes
  - Data buffering (circular, sliding window)
  - Multi-format export (CSV, JSON, HDF5, NPY, MAT)
  - 26 API endpoints for acquisition management
- PyQt6 GUI Client (Phase 3):
  - Equipment monitoring panel
  - Data acquisition panel
  - Connection management
  - Real-time plotting
- Multi-instrument synchronization UI
- Comprehensive acquisition demo

### 📝 Changed
- Integrated client with server Data Acquisition System

---

## [0.5.0] - 2025-11-08

### ✨ Added
- **Equipment Management**:
  - Equipment lock/session management
  - Exclusive and observer session modes
  - Multi-user access control
- **Equipment State Management**:
  - State capture and restore
  - State comparison
  - State versioning
- **Safety System**:
  - Voltage/current/power limits
  - Emergency stop
  - Safety interlocks
- Rigol DS1102D oscilloscope driver

### 🐛 Fixed
- Multiple acquisition demo bug fixes
- Equipment readings endpoint corrections
- Alarm route ordering
- Equipment display field names
- Acquisition router prefix issues

---

## [0.4.0] - 2025-11-08

### ✨ Added
- Automated setup script and quick start guide
- Comprehensive testing and verification scripts
- Project summary documentation

### 🐛 Fixed
- PEP 668 externally-managed environment handling
- Virtual environment detection
- Pip installation and detection
- Missing dependencies (pydantic-settings, psutil)
- Python path configuration

---

## [0.3.0] - 2025-11-08

### ✨ Added
- Deployment infrastructure
- Package build simulation and validation
- Comprehensive development roadmap

### 📝 Changed
- Updated README with implementation status

---

## [0.2.0] - 2025-11-08

### ✨ Added
- **Core LabLink Server Functionality**:
  - RESTful API foundation
  - Equipment driver architecture
  - Basic equipment control
  - Command execution system
  - Equipment status monitoring

---

## [0.1.0] - 2025-11-08

### 🎉 Initial Release

- **Project Setup**:
  - Repository initialization
  - Basic project structure
  - Initial documentation
  - .gitignore configuration
  - Development environment setup

---

## Version History Summary

| Version | Date | Type | Description |
|---------|------|------|-------------|
| **1.2.0** | 2025-12-06 | Minor | Update system, UI consolidation, version management |
| **1.0.1** | 2025-11-28 | Patch | GUI launcher, diagnostics, post-release fixes |
| **1.0.0** | 2025-11-14 | Major | **First Production Release** |
| **0.27.0** | 2025-11-13 | Minor | MFA, OAuth2, enhanced security |
| **0.26.0** | 2025-11-13 | Minor | Enhanced web dashboard with real-time |
| **0.24.0** | 2025-11-13 | Minor | MVP web dashboard |
| **0.23.0** | 2025-11-13 | Minor | Advanced security system |
| **0.22.0** | 2025-11-13 | Minor | Equipment discovery |
| **0.21.0** | 2025-11-13 | Minor | Backup & restore |
| **0.20.0** | 2025-11-13 | Minor | Automated test sequences |
| **0.19.0** | 2025-11-13 | Minor | Enhanced calibration |
| **0.18.0** | 2025-11-13 | Minor | Database integration |
| **0.17.0** | 2025-11-13 | Minor | Data analysis pipeline |
| **0.16.0** | 2025-11-13 | Minor | Waveform analysis |
| **0.15.0** | 2025-11-13 | Minor | Enhanced WebSocket |
| **0.14.0** | 2025-11-13 | Minor | Scheduled operations |
| **0.13.0** | 2025-11-13 | Minor | Performance monitoring |
| **0.12.0** | 2025-11-13 | Minor | Equipment diagnostics |
| **0.11.0** | 2025-11-13 | Minor | Enhanced alarms |
| **0.10.1** | 2025-11-13 | Patch | Enhanced logging |
| **0.10.0** | 2025-11-08 | Minor | Equipment diagnostics |
| **0.9.0** | 2025-11-08 | Minor | Scheduled operations |
| **0.8.0** | 2025-11-08 | Minor | Alarm system |
| **0.7.0** | 2025-11-08 | Minor | Advanced logging |
| **0.6.0** | 2025-11-08 | Minor | Data acquisition |
| **0.5.0** | 2025-11-08 | Minor | Equipment/state/safety management |
| **0.4.0** | 2025-11-08 | Minor | Setup automation |
| **0.3.0** | 2025-11-08 | Minor | Deployment infrastructure |
| **0.2.0** | 2025-11-08 | Minor | Core server functionality |
| **0.1.0** | 2025-11-08 | Minor | Initial release |

---

**Total Versions:** 30
**Development Timeline:** 2025-11-08 to 2025-12-06 (28 days)
**Major Milestones:** 2 (v1.0.0, v1.2.0)
**Production-Ready:** v1.0.0+

---

**Copyright:** © 2025 LabLink Project
**License:** MIT
**Repository:** https://github.com/X9X0/LabLink
