# DS1054Z panel: no trace and a minutes-deep queue — found, fixed, verified

Started 2026-09-16 by the WSL-side session as a handoff; continued and closed
the same day by the Windows-side session. Everything below was measured on the
bench, not inferred, unless marked *open*.

**Status:** all three causes found and fixed on `feature/instrument-panels`.
The two driver fixes and the queue bound are verified against the bench
DS1054Z, including through a full server instance. Not yet verified: the panel
itself in the running Windows client, which needs the in-app *Update Server* /
*Update Client* buttons to deploy. `VERSION` deliberately not bumped.

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
