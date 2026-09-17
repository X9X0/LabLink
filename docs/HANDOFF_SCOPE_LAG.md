# DS1054Z panel: no trace and a minutes-deep queue — found, fixed, verified

Started 2026-09-16 by the WSL-side session as a handoff; continued and closed
the same day by the Windows-side session. Everything below was measured on the
bench, not inferred, unless marked *open*.

**Status:** all three original causes fixed, plus a fourth found by the
operator after deployment -- the windowed USB read made the instrument beep
twice a second. All four are fixed on `feature/instrument-panels` and verified
against the bench DS1054Z, over both USB and LAN. The recommended link for
this scope is now **LAN**: one read per trace instead of three, no window
writes, no beeping. Not yet verified: the panel itself in the running Windows
client. `VERSION` deliberately not bumped.

## Ground rules (from the operator)

- All work stays on `feature/instrument-panels`. Never continue
  `feature/rigol-equipment-drivers`; never break `main`.
- Do **not** bump `VERSION` for fixes-in-progress. Bump only when a usable
  improvement lands ("chill with the version bumps").
- Less guessing: read logs and measure before changing code.
- The Windows install `C:\LabLinkTest` is updated only through the in-app
  *Update Client* button. The Pi is updated through the in-app update, which
  tracks a branch. Do not edit either install by hand.
- Keep the test suite green: `python -m pytest tests -q --ignore=tests/hardware`.

## The bench

| Thing | Value |
|---|---|
| Lab server (Pi) | `192.168.91.191`, hostname `lablink-pi-test`, API `:8000`, SSH user `admin` (the ed25519 key on the Windows machine works) |
| Server runtime | Docker, containers `lablink-server` (image `lablink-server:latest`, privileged, `/dev/bus/usb` mapped) and `lablink-web`; compose at `/opt/lablink/docker-compose.yml`; code at `/app` in the container |
| Server version | 2.4.1 = `feature/instrument-panels` @ `43183db` at the time of these measurements |
| Windows client | `192.168.91.122`, `C:\LabLinkTest` |
| Instruments | `ps_56fdd3df` B&K 1685B (`ASRL/dev/ttyUSB0`), `ps_36509eb5` B&K 9205B (USB), `scope_a62f42e9` Rigol DS1054Z `USB0::6833::1230::DS1ZA171409212::0::INSTR`, firmware 00.04.03 |
| Stack in container | PyVISA 1.16.2, PyVISA-py 0.8.1, pyusb 1.3.1, libusb (the kernel `usbtmc` module is loaded but binds nothing — there is no `/dev/usbtmc0`) |

Useful commands on the Pi:

```bash
docker logs --tail 3000 lablink-server 2>&1 | grep -E "waited|took|VI_ERROR_TMO|refusing" | tail -50
docker logs lablink-server 2>&1 | grep VI_ERROR_TMO | grep -oE "Error querying (binary )?'[^']+'" | sort | uniq -c | sort -rn
docker inspect -f '{{.State.StartedAt}}' lablink-server
```

## The three causes

### 1. `:MEAS:VAV?` is not a DS1000Z command — fixed

It timed out every time: 100 timeouts in the container's first 27 minutes, one
per measurement poll. The DS1000Z programming guide has no `:MEASure:VAV`; the
documented form is `:MEASure:ITEM? <item>,<source>`. `:MEAS:VPP?` and
`:MEAS:FREQ?` happen to answer undocumented, which is why the panel's "Basic"
set (`vpp, vavg, freq`) lost exactly one number and paid 10 s for it.

Fixed in `RigolDS1104.get_measurements`: every item now goes out as
`:MEAS:ITEM? <ITEM>,CHAN<n>`, which names its own source, so the `:MEAS:SOUR`
write is gone too. A failing item no longer aborts the rest of the set.

Measured after the fix, through the driver: `{'vpp': 0.564, 'vavg': 0.1194248,
'freq': 105263200.0}` in **0.01 s**.

`RigolMSO2072A` and `RigolDS1102D` still send the old per-item forms. That is
deliberate: the DS1000D/E *does* document `:MEAS:VAV?`, neither instrument is
on the bench, and their guides were not available to check. *Open, low
priority:* confirm the MSO2000A/DS2000A form and align it.

### 2. `:WAV:DATA?` could never work over this USB link — fixed

This was the reason the panel had no trace: 62 of 62 attempts failed. Every
hypothesis in the original handoff turned out to be wrong, and the real cause
is below them all.

Ruled out, each by measurement:

- **A poisoned session.** `:WAV:DATA?` fails on a freshly connected session
  that has never sent `:MEAS:VAV?`, with the client closed and the queue
  drained. The log for that attempt contains no `:MEAS` at all.
- **The code path.** Raw `pyvisa` in the container fails the same way as
  `BaseEquipment._query_binary`; `container=bytes` and `container=list` behave
  identically.
- **The thread.** Failing on the main thread and in a `run_in_executor`
  thread alike.
- **RUN vs STOP.** Fails identically in both, at 5 ns/div and at 1 ms/div.
- **`chunk_size`.** Fails at 512, 1024, 4096, 20480 and 1 MiB.
- **A rejected command.** With the error queue drained first, the whole NORMal
  setup (`:WAV:SOUR`, `:WAV:MODE NORM`, `:WAV:FORM BYTE`, `:WAV:PRE?`) returns
  `0,"No error"`, and after a timed-out `:WAV:DATA?` the only error is
  `-410,"Query INTERRUPTED"` — raised by the *next* command arriving while the
  scope still had an answer pending. The scope accepts the query and means to
  answer it.

The cause is the size of the reply. Sweeping RAW windows to vary only the
reply length gives a sharp, repeatable threshold:

| reply | result |
|---|---|
| 262 bytes (250 samples) | OK, 0.11 s |
| 462 bytes (450 samples) | OK, 0.39 s |
| **492 bytes (480 samples)** | **OK, 0.35 s** |
| **512 bytes (500 samples)** | **timeout, every time** |
| 612 bytes (600 samples) | timeout |
| 1212 bytes (1200 samples) | timeout |

And the reason, from the descriptors:

```
$ lsusb -d 1ab1:04ce -v
  bcdUSB 2.00
  bEndpointAddress 0x82  EP 2 IN   Transfer Type Bulk   wMaxPacketSize 0x0040  1x 64 bytes
  bEndpointAddress 0x03  EP 3 OUT  Transfer Type Bulk   wMaxPacketSize 0x0040  1x 64 bytes
$ dmesg | grep maxpacket
  usb 1-1.4: config 1 interface 0 altsetting 0 bulk endpoint 0x82 has invalid maxpacket 64
  usb 1-1.4: config 1 interface 0 altsetting 0 bulk endpoint 0x3 has invalid maxpacket 64
```

The scope declares a 64-byte bulk max packet where USB 2.0 high speed requires
512, and the kernel says so on plug-in. Reads up to 492 bytes work fine across
several packets; a reply that would cross 512 bytes never arrives. A NORMal
screen read is 1200 samples in a 1212-byte reply, so it could not ever have
worked, and no change to the command tree would have fixed it. The `dmesg`
line was in the original handoff as "a Rigol descriptor quirk, informational";
it was the whole answer.

**The fix:** `:WAV:STARt`/`:WAV:STOP` window the read in NORMal mode, not only
in RAW, so the screen can be fetched in blocks under the ceiling with the
scope left running. `LegacyScopeExtras._read_trace_in_blocks` reads 400
samples at a time (a 412-byte reply) and stitches them.

Measured after the fix, through `RigolDS1104.get_waveform_data`: **1200
samples in 0.93–1.12 s, three runs in a row**, scope left in the run state it
was found in. Through the server's own API with the fix mounted: HTTP 200 in
**1.02 s**, `num_samples: 600` decimated as the panel asks for it.

Windowing is opt-in per family (`trace_block_points`, beside the existing
`WAVEFORM_POINTS`), set only on `RigolDS1104`. The DS1000D/E command tree is
older and may not window at all, so `RigolMSO2072A` and `RigolDS1102D` keep
the single read they have always used.

*Open, and worth knowing:* this ceiling applies to **every** reply from this
scope, not just waveforms. Nothing else the panel asks for comes close to 492
bytes today, but `:DISP:DATA?` (a screenshot) and `:SYST:SET?` never can work
over libusb here. Three ways out, none needed yet: bind the kernel `usbtmc`
driver instead of libusb, override the endpoint's `wMaxPacketSize` in pyusb,
or use LAN instead of USB.

### 3. Abandoned requests piled up without limit — fixed

The client's HTTP timeout is 10 s, but the server keeps executing a request
after the client gives up. With every measurement poll costing ≥10 s and every
trace fetch ≥10 s, the scope's I/O-lock queue reached **205 s**
(`':TRIG:STAT?' waited 205.5s for the instrument`). That is why *every* scope
request, including `/status` during selection, took 20–30 s. This was a design
gap independent of the two bad commands, and it is what turned them from a
missing number into a dead panel.

Fixed on both sides:

- **Server.** `BaseEquipment.MAX_QUEUED_EXCHANGES` (8) bounds the queue:
  past it, an exchange raises `InstrumentBusy` instead of joining the queue,
  and the API answers **503** rather than a 500 the client would retry.
  Nested exchanges are never refused — `_query` → `_ensure_connected` →
  `connect` → `_query` runs in the one task that already holds the lock, and
  refusing the inner call would break reconnection.
- **Client.** `InstrumentPanel._back_off()` doubles the poll interval, capped
  at 30 s, after each consecutive failed poll, and restores the operator's
  cadence on the first good one. Setting the cadence by hand clears the
  back-off; the remembered interval is never overwritten.

Measured, 20 concurrent trace fetches at one instrument:

```
503 0.035s   503 0.057s   503 0.057s   503 0.060s   503 0.064s
503 0.068s   503 0.070s   503 0.071s   503 0.071s   503 0.079s
503 0.529s   503 6.374s   200 7.857s   200 7.861s   200 7.865s
200 7.874s   200 7.882s   200 7.962s   200 7.968s   200 7.968s
```

Thirteen refused — eleven of them inside 80 ms — and seven served. The worst
wait is 7.9 s instead of a backlog minutes deep, and it drains. The whole test
server's log contains **zero** `VI_ERROR_TMO`, against 100 in the deployed
build's first 27 minutes.

One consequence to know: a trace read is three exchanges, so a burst can
refuse it partway (`refusing ':WAV:STAR 801'`). The request then fails with
503 rather than returning a short trace, and the client retries on its
back-off. Holding the I/O lock across all three blocks would make it atomic
but would also hold the instrument for a second, which is what `e7f0a54`
deliberately stopped doing — a front-panel press must not queue behind a poll.

## Solved: the beeping, and why LAN is the right link for this scope

**The beeping was the windowed read.** Every `:WAV:STOP` write makes the
DS1054Z beep and flash **"Stop point changed!"** on its own display. It is a
*notification*, not an error, so it never appears in `:SYST:ERR?` -- which is
why four probes that read the error queue all came back clean while the bench
beeped twice a second. The operator's eyes found it in one message. Recorded
here because the same blindness will recur: **this instrument reports some
conditions only on its own screen.**

**LAN removes the whole problem class.** Measured with USB unplugged:

| | USB (libusb) | LAN (VXI-11) |
|---|---|---|
| one reply | 492 bytes max | no ceiling found |
| 1200-sample screen | impossible in one read | **1200 bytes in 0.003 s**, 7/7 |
| reads per trace | 3 windowed | 1 |
| `:WAV:STOP` writes per trace | 4 | **0** |
| beeps | ~2/s | none |
| preamble | truncated over `/dev/usbtmc0` | all 10 fields |

The scope is at `192.168.91.37` (DHCP), reports `:LAN:STAT? CONFIGURED` and
advertises its own `TCPIP::192.168.91.37::INSTR`. Through the server:
`POST /api/equipment/connect` with `TCPIP0::192.168.91.37::inst0::INSTR`
connects it as a *new* equipment id (`scope_cee816af` -- the id is derived
from the resource string, so the USB and LAN ids differ; saved profiles and
locks naming the old one will not match).

**This model serves LAN for remote I/O only while USB is physically
unplugged.** That is why VXI-11 timed out on every resource spelling even with
the container stopped: the cable was still in. It is either/or, not both.

So the windowed read is now gated to the link that needs it
(`LegacyScopeExtras._trace_blocks`): USB blocks, LAN reads the trace whole.
A window left behind by an earlier session would silently truncate the trace
-- seen on the bench, 400 samples reported as a whole trace -- so the LAN path
corrects it when the preamble shows it is wrong, once, rather than writing the
window before every trace. Measured after the gate: first trace 2 window
writes, every trace after it none, 600 samples in 0.15--0.29 s, error queue
clean.

### Whose fault was what

Worth stating plainly, because the question was asked directly.

*The wall is the instrument's.* The DS1054Z declares `wMaxPacketSize 64` on
both bulk endpoints while running at USB 2.0 high speed, where the spec
requires 512, and the kernel says so unprompted. Two independent host stacks
fail on it differently: libusb stops completing replies past 492 bytes, and
the kernel `usbtmc` driver truncates every reply to one 52-byte packet and
never delivers the rest. No LabLink code is in that path. (Both stacks tested
are Linux; a stack that ignores the descriptor and assumes 512 may well work,
which would explain Rigol's own Windows software being fine over USB.)

*The cost was ours.* Three of the four faults here were LabLink's: a command
that does not exist on this family (`:MEAS:VAV?`), an unbounded queue that
turned one slow command into a 205 s backlog, and a workaround built on
undocumented NORM-mode windowing that was audible on the instrument and still
failed intermittently. And two architectural gaps made a device defect
expensive:

- **No transport abstraction.** The driver uses whatever resource string
  discovery handed it. This scope was reachable over LAN the whole time and
  nothing could prefer it, fall back to it, or even notice -- though the
  instrument reports its own `TCPIP::...::INSTR` when asked.
- **No transport-level diagnosis.** A 1212-byte read failed with a bare
  `VI_ERROR_TMO`. Everything needed to say "replies over ~492 bytes never
  complete on this link" was available, and nothing said it.

Worth doing, in that order: prefer LAN where an instrument advertises it, and
probe a link's reply-size limit once and record it against the device, so an
oversized read is refused immediately with a real message.

## How the beeping was found (kept for the method, not the conclusion)

Reported from the bench after `00faab6` was deployed: with the scope connected
and streaming started, the instrument beeps roughly twice a second while the
Control tab's trace updates normally between the beeps. The data is right; the
instrument is complaining about something.

A DS1000Z beeps when it refuses a command, so the first move was to find the
refused command. Three probes, all clean:

| Probe | Hypothesis | Result |
|---|---|---|
| `probe_window_order.py` | the windowed read leaves `:WAV:STARt` past `:WAV:STOP` between writes | **wrong** -- both orders accepted, 0 errors, 1200 bytes either way |
| `probe_panel_beep.py` | one of the panel's calls is refused | **wrong** -- `get_state`, `get_trigger_status`, `get_measurements`, `get_readings` and a windowed trace on all three displayed channels, three cycles, in *both* acquisition states: nothing refused |
| `probe_stream_collision.py` | the Equipment tab's 10 Hz `get_waveform` stream collides with the trace read between blocks | **wrong** -- panel alone, stream alone, and both together: queue clean in all three |

`ad3ae57` reordered the window writes to `:WAV:STOP` first on the strength of
the first hypothesis. The probe then showed an inverted window is accepted
silently, so **that commit does not fix the beeping** -- its message says it
does, and that is wrong. The reordering is kept because a window that is never
inverted is unambiguously in range whatever a future firmware does.

The lesson is the fifth probe, `scripts/probe_beep_bisect.py`: it drove one
operation at a time with announced phases for the operator to run *while
listening*, and it too reported nothing. What actually solved it was the
operator reading the scope's screen -- "stop point changed!" -- which named the
command in one line after four probes had failed. Every `:WAV:STOP` write does
it. The mistake underneath all four was assuming a beep implies an error-queue
entry; this instrument reports some conditions only on its own display, and no
amount of `:SYST:ERR?` will ever show those.

One loose end closed: the `-113 "Undefined header"` entries found in leftover
queues were probe commands of mine (`:LAN:GATE?`, `:SYST:COMM:LAN:IPAD?`,
`:LAN:APPL` -- none of which exist on this firmware), not the client's.

## How fast the trace can go, and why it stops there

The panel sat at ~1 Hz. It is now bounded by the instrument, at about
**8.5 distinct frames a second**, and no part of LabLink is the limit any
more. The route there, and the measurements, so nobody repeats it:

| change | effect |
|---|---|
| stop re-asserting `:WAV:SOUR/:MODE/:FORM` every fetch | 308 ms -> 37 ms |
| cache the axis scaling for 1 s | six exchanges -> three |
| push frames from the server instead of asking per frame | no HTTP round trip per frame |
| hold the cadence by deadline, not by sleeping after the work | a stall stops compounding |
| drop duplicate frames at the server | ~8.5 sent instead of 20-90 |

**The ceiling is the instrument.** Distinct `:WAV:DATA?` frames per second,
6 s samples: 7.7 at 1 ms/div, 8.5 at 200 us/div, 8.0 at 20 us/div, 7.7 at
1 us/div; 9.0 at memory depth AUTO, 8.0 at 12k, 8.4 at 120k; 8-9 both
triggered and free-running; 8-9 over VXI-11 and over a raw socket; and 8-9
whether the target cadence was 30, 60, 100 or 120 Hz. Reads themselves run
at 30-90 Hz -- with the acquisition STOPped, 89 reads/s and 0.2 unique/s --
so everything above ~10 Hz re-reads a buffer the scope has not refreshed.

**What did not help, measured:**

* *Target rate.* 30, 60, 100 and 120 Hz all yielded the same ~8.5 unique.
* *Raw socket vs VXI-11.* The socket halves the median (1.6 ms vs 4.5 ms)
  and leaves the tail alone: p90 was ~160 ms on both. An early 200-read
  sample suggested the socket fixed the tail as well; a longer run across
  the matrix showed it does not. **The ~150 ms stall is the instrument.**
* *Loading the Pi.* It sits at 1-5% CPU throughout. There is no work to
  move onto it.

**What is worth doing and is not done:** the frame is JSON floats, 32,636
bytes and 3.79 ms to build. As ADC codes plus scale factors it is 1,703
bytes and 0.04 ms -- 19x smaller and 95x cheaper, and it makes the Pi do
*less*, not more. At 8.5 frames/s that is 272 KiB/s against 14 KiB/s. Worth
doing for bandwidth and CPU; it will not make the trace look faster,
because the frames are not there to send.

### Bench notes for this scope

* LAN serves remote I/O only while **USB is physically unplugged**.
* The raw socket tolerates one session and frees it slowly: opening and
  closing repeatedly locks it out for tens of seconds, while one session
  held open ran 987 frames with no failure. Open once, keep it.
* A query sent within ~20 ms of a write is dropped; 50 ms is reliable.
* Socket framing desyncs about once every few hundred reads and never
  recovers on its own, which is what `RigolSocketSession` resynchronises.

## Log lines to look for

```
USB0::…::INSTR: ':MEAS:VAV?' waited 155.5s for the instrument (queued behind other requests)
USB0::…::INSTR: ':MEAS:VAV?' took 10.0s on the instrument
USB0::…::INSTR: refusing ':WAV:SOUR CHAN1' -- 8 requests already queued for this instrument
```

"took 10.0s" is the VISA timeout: the instrument did not answer that command.
"waited" is queue depth. "refusing" is the bound doing its job. A healthy
scope shows none of them.

## Verifying a deploy without poking the bench by hand

`tests/hardware/test_scope_lag_fixes.py` is every verification step that does
not need a mouse. It is env-gated and skips in a normal run:

```bash
LABLINK_PI_HOST=192.168.91.191 pytest tests/hardware/test_scope_lag_fixes.py -v
# add LABLINK_RUN_BURST=1 to also load one instrument with 20 concurrent fetches
```

It checks, in this order: the Pi is on the commit under test; the container is
healthy; the scope returns a full 600-point trace inside a time budget, three
times running, carrying a real signal; every measurement item answers inside a
budget; every open supply still reads in under 2 s; the log window shows none
of the four bad signatures; and, opt-in, a burst is refused rather than queued
and the instrument recovers straight afterwards.

The deploy check gates the rest. Against the pre-fix build the whole run is
**one failure in 4 s** naming the cause and the fix, rather than 198 s of
watching each request spend its VISA timeout. Against the fixed build it is
**10 passed in 57 s**, burst included. Both were measured while writing it.

It reads the same environment variables as `test_live_pi.py`, plus
`LABLINK_EXPECT_COMMIT` (default: the local `HEAD`), `LABLINK_CONTAINER`,
`LABLINK_REMOTE_DIR`, `LABLINK_API_PORT` and the time budgets. It connects the
scope and never disconnects anything -- closing a serial port resets a legacy
B&K and drops a live output -- and only reads supplies the server already has
open.

## What is left

0. **Connect this scope over LAN, not USB.** With USB physically unplugged,
   connect `TCPIP0::192.168.91.37::inst0::INSTR` (Equipment tab, or
   `POST /api/equipment/connect`). One transfer per trace, no window writes,
   no beeping. LAN serves remote I/O only while USB is unplugged on this model,
   and the equipment id differs from the USB one.

1. **Deploy, then run the checks above, then look at the panel.** Use the
   in-app *Update Server* and *Update Client*.

   **Set the update mode to "Development (all commits)" and pick
   `feature/instrument-panels` first.** In "Stable (VERSION releases)" mode the
   ref comes from the version selector (`client/ui/system_panel.py`,
   `_update_remote_server`), so the button would put the Pi on a release tag,
   silently moving it off the branch and deploying none of this. The server
   reports `update_mode: "stable"` and `tracked_branch: null` today. The first
   automated check catches it if it happens.

   What the checks cannot cover, and still needs eyes on the client: that the
   panel *draws* the trace in both views, that a hidden panel stops polling,
   that switching supply↔scope is instant, and that two servers still dispatch
   to the right panel (`docs/HANDOFF_INSTRUMENT_PANELS.md` "Verification"
   items 2, 3 and 5).
2. Only then consider a `VERSION` bump.
3. *Open, low priority:* the MSO2000A measurement form (cause 1); the reply
   ceiling on `:DISP:DATA?` if a screenshot feature is ever wanted (cause 2).
4. Incidental, still unfixed: `GET /api/diagnostics/system` returns
   `'EquipmentManager' object has no attribute '_equipment'` (a bug in
   `server/api/diagnostics.py`). The serial 1685B answers `*IDN?`/`*OPC?`/
   `*STB?` with 2 s timeouts during connect probing; harmless but noisy.
5. Unrelated, and it makes the suite look red: an untracked v2.0.0 checkout
   sits at `Lablink-Test/` inside the repo and is not gitignored, so
   `tests/unit/test_no_locale_dependent_io.py` walks it and fails on its files.
   Every offender it reports is from that copy; none are from the real tree.
   Delete it or ignore it.

## The probes

All are in `scripts/`, all run with the server stopped because the container
holds the USB interface, and all take `SCOPE_RESOURCE` from the environment:

```bash
docker stop -t 10 lablink-server
docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
  -v /tmp/<probe>.py:/tmp/p.py:ro lablink-server:latest python /tmp/p.py
docker start lablink-server
```

| Probe | What it answers |
|---|---|
| `probe_ds1000z.py` | The original survey: which SCPI answers, and how fast |
| `probe_wavdata_paths.py` | Is it the code path? (raw vs driver, thread vs not) |
| `probe_wavdata_sync.py` | Are the reads one answer behind? |
| `probe_wavdata_chunks.py` | Does `chunk_size` or the payload size matter? |
| `probe_wavdata_bytes.py` | What is actually on the wire, header and all |
| `probe_wavdata_error.py` | Which command is the scope rejecting? |
| `probe_wavdata_threshold.py` | Where exactly is the reply-size ceiling? |
| `probe_wavdata_windows.py` | Can the screen be read in windows? (the fix) |
| `probe_driver_trace.py` | Does the fixed driver return a trace? (mount the working tree over `/app`) |

To exercise a whole server with working-tree code without touching the
install, run a second container on another port with the changed files mounted
read-only, and stop the live one first so it releases the scope:

```bash
docker stop -t 10 lablink-server
docker run -d --name lablink-fixtest --privileged --device /dev/bus/usb:/dev/bus/usb \
  -p 8001:8000 -e LABLINK_ENABLE_EQUIPMENT_LOCKS=false \
  -v /tmp/fix/server/equipment/base.py:/app/server/equipment/base.py:ro \
  -v /tmp/fix/server/equipment/rigol_scope.py:/app/server/equipment/rigol_scope.py:ro \
  -v /tmp/fix/server/api/equipment.py:/app/server/api/equipment.py:ro \
  lablink-server:latest
# ... test against :8001 ...
docker rm -f lablink-fixtest && docker start lablink-server
```

## Files

- `server/equipment/rigol_scope.py` — `LegacyScopeExtras`
  (`_read_trace_in_blocks`, `trace_block_points`, waveform, trigger, state,
  cheap readings), `RigolDS1104` (DS1000Z: `:MEAS:ITEM?` measurements,
  run/stop/single/autoscale).
- `server/equipment/base.py` — `_io_lock` (now counting waiters),
  `InstrumentBusy`, `MAX_QUEUED_EXCHANGES`, `_refuse_if_busy`,
  `_write/_query/_query_binary`, `_note_slow_io`, `SLOW_IO_WARN_SEC`.
- `server/api/equipment.py` — `InstrumentBusy` → 503 on `/readings` and
  `/command`.
- `client/ui/instruments/base.py` — `InstrumentPanel`, `_poll`, `_back_off`,
  `_poll_succeeded`, `POLL_BACKOFF_CAP_MS`.
- `client/ui/instruments/oscilloscope.py` — panel, `poll()`, `_poll_trace()`.
- `tests/unit/test_legacy_scope_extras.py` — the `:MEAS:ITEM?` form, the
  windowed read, and a `ScriptedScope` that enforces the bench's 492-byte
  ceiling so a regression to one big read fails in CI, not on the bench.
- `tests/unit/test_instrument_queue_bound.py`,
  `tests/gui/test_poll_backoff.py` — the queue bound and the back-off.
