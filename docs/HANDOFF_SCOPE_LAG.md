# Handoff: DS1054Z panel shows no trace and lags — bench findings and next steps

Written 2026-09-16 by the WSL-side Claude session, for a Claude session on the
Windows side of the same machine. Everything below was measured on the bench,
not inferred, unless marked *open*.

## Ground rules (from the operator)

- All work stays on `feature/instrument-panels`. Never continue
  `feature/rigol-equipment-drivers`; never break `main`.
- Do **not** bump `VERSION` for fixes-in-progress. Bump only when a usable
  improvement lands ("chill with the version bumps").
- Less guessing: read logs and measure before changing code. The server log
  now names slow commands (see "Log lines to look for").
- The Windows install `C:\LabLinkTest` is updated only through the in-app
  *Update Client* button. The Pi is updated through the in-app update, which
  tracks a branch. Do not edit either install by hand.
- Keep the test suite green: `venv/bin/python -m pytest tests -q --ignore=tests/hardware`
  (2361 passed, 51 skipped, 1 xfailed at commit `43183db`).

## The bench

| Thing | Value |
|---|---|
| Lab server (Pi) | `192.168.91.191`, hostname `lablink-pi-test`, API `:8000`, SSH user `admin` (password known to the operator; the ed25519 key on the Windows machine works; an RSA key added from WSL is "accepted" by sshd but login is still refused — *open*, unimportant) |
| Server runtime | Docker, containers `lablink-server` (image `lablink-server:latest`, privileged, `/dev/bus/usb` mapped, restart `unless-stopped`) and `lablink-web`; compose at `/opt/lablink/docker-compose.yml`; code at `/app` inside the container |
| Server version | 2.4.1 = `feature/instrument-panels` @ `43183db` (checked via `GET /api/system/version` and `/app/VERSION`) |
| Windows client | `192.168.91.122`, `C:\LabLinkTest`, writes `lablink_client.log` in its working directory |
| Instruments | `ps_56fdd3df` B&K 1685B (serial `ASRL/dev/ttyUSB0`), `ps_36509eb5` B&K 9205B (USB), `scope_a62f42e9` Rigol DS1054Z `USB0::6833::1230::DS1ZA171409212::0::INSTR`, firmware 00.04.03 |
| Stack in container | PyVISA 1.16.2, PyVISA-py 0.8.1, pyusb 1.3.1. Kernel `usbtmc` module is loaded on the host but the container claims the device through libusb |

Useful commands on the Pi:

```bash
docker logs --tail 3000 lablink-server 2>&1 | grep -E "waited|took|VI_ERROR_TMO" | tail -50
docker logs lablink-server 2>&1 | grep VI_ERROR_TMO | grep -oE "Error querying (binary )?'[^']+'" | sort | uniq -c | sort -rn
docker inspect -f '{{.State.StartedAt}}' lablink-server
```

`scripts/probe_ds1000z.py` is the direct probe used below. It needs the
server stopped (the container holds the USB interface). Run it as:

```bash
docker stop -t 10 lablink-server
docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
  -v /opt/lablink/scripts/probe_ds1000z.py:/tmp/p.py:ro lablink-server:latest python /tmp/p.py
docker start lablink-server
```

(The copy at `/tmp/scope_probe.py` on the Pi is from this session and may be
gone after a reboot; the repo copy is the one to use.)

## What was measured

1. **Supplies are fine.** `GET /api/equipment/<ps>/readings` answers in
   0.03–0.07 s for both supplies.
2. **The scope answers valid SCPI instantly.** Direct probe (server stopped):
   `*IDN?`, `:CHANn:DISP?`, `:TRIG:STAT?`, `:TIM:MAIN:SCAL?`, `:WAV:PRE?`,
   `:MEAS:ITEM? VAVG,CHAN1`, `:MEAS:ITEM? VPP,CHAN1`, `:MEAS:ITEM? FREQ,CHAN1`
   and `:MEAS:VPP?` all return in ≈0 ms. At probe time CH1–CH3 were on, CH4
   off, trigger STOP, 5 ns/div.
3. **`:MEAS:VAV?` is not a DS1000Z command.** It times out (10 s VISA timeout)
   every time: 100 timeouts in the container's first 27 minutes. The DS1000Z
   programming guide has no `:MEASure:VAV`; the documented form is
   `:MEASure:ITEM? <item>,<source>` (items VMAX VMIN VPP VTOP VBASe VAMP
   VAVG VRMS OVERshoot PREShoot MARea MPARea PERiod FREQuency RTIMe FTIMe
   PWIDth NWIDth PDUTy NDUTy …). `:MEAS:VPP?` and `:MEAS:FREQ?` happen to work
   undocumented, which is why only `vavg` shows up.
   Source: `server/equipment/rigol_scope.py`, class `RigolDS1104`,
   `get_measurements()` — it writes `:MEAS:SOUR CHANn` then queries
   `:MEAS:VPP?`, `:MEAS:VMAX?`, `:MEAS:VMIN?`, `:MEAS:VAV?`, `:MEAS:VRMS?`,
   `:MEAS:FREQ?`, `:MEAS:PER?`. The panel's default "Basic" set is
   `vpp, vavg, freq`, so every 2 s poll pays one 10 s timeout.
4. **`:WAV:DATA?` fails inside the server, 62 of 62 attempts, and works
   directly.** The server path is `BaseEquipment._query_binary` →
   `instrument.query_binary_values(":WAV:DATA?", datatype="B")` and it timed
   out every time (`Error querying binary ':WAV:DATA?': VI_ERROR_TMO`). The
   direct probe with the *same* call and the same pyvisa-py stack returned
   1200 bytes in 0.01 s (also with `chunk_size` 1 MiB). `write(':WAV:DATA?')`
   followed by `read_raw()` timed out in the probe. `instrument.clear()` is
   unsupported by pyvisa-py USBTMC (`VI_ERROR_NSUP_OPER`), so there is no
   device-clear recovery path.
   *Open:* why the identical call fails in the server. Differences to
   check: the server's session has `timeout = 10000` and no
   `read_termination` (same as the probe); the server's binary read runs in
   a thread-pool executor; in the server it is always preceded, on the same
   session, by a `:MEAS:VAV?` that the scope never answered; the scope was
   RUNning during most of the failures and STOPped during the probe.
   Reproduce through the server itself with the Windows client closed:
   ```bash
   curl -s -X POST -H 'Content-Type: application/json' \
     -d '{"command_id":"probe1","equipment_id":"scope_a62f42e9","action":"get_waveform_data","parameters":{"channel":1,"points":600}}' \
     http://192.168.91.191:8000/api/equipment/scope_a62f42e9/command
   ```
   (`Command` requires `command_id`, `equipment_id`, `action`, `parameters`;
   read-only actions need no `session_id`.) Do this *after* fixing item 3, so
   the session is not poisoned by an unanswered query first.
5. **Abandoned requests pile up on the server.** The client's HTTP timeout is
   10 s, but the server keeps executing a request after the client gives up.
   With every measurement poll costing ≥10 s and every trace fetch ≥10 s, the
   scope's I/O-lock queue reached **~200 s** (`':TRIG:STAT?' waited 205.5s for
   the instrument`). That is why *every* scope request, including `/status`
   during selection, appeared to take 20–30 s, and why nothing on the panel
   updated. This is a design gap independent of the two bad commands.
6. **Client behaviour seen from the server:** in the two minutes before the
   probe the client was only polling `/api/locks/status/scope_a62f42e9` (the
   panel's polls had stopped, as designed after repeated failures) while the
   server was still draining the old queue.
7. Incidental: `GET /api/diagnostics/system` returns
   `'EquipmentManager' object has no attribute '_equipment'` (a bug in
   `server/api/diagnostics.py`). `dmesg` warns `bulk endpoint 0x3 has invalid
   maxpacket 64` for the DS1054Z — a Rigol descriptor quirk, informational.
   The serial 1685B answers `*IDN?`/`*OPC?`/`*STB?` with 2 s timeouts during
   the server's connect probing; harmless but noisy.

## Log lines to look for

`BaseEquipment` (commit `43183db`) warns when an exchange waits ≥2 s for the
instrument's lock or holds it ≥2 s:

```
USB0::…::INSTR: ':MEAS:VAV?' waited 155.5s for the instrument (queued behind other requests)
USB0::…::INSTR: ':MEAS:VAV?' took 10.0s on the instrument
```

"took 10.0s" is the VISA timeout: the instrument did not answer that
command. "waited" is queue depth. A healthy scope shows neither.

## What to do, in order

1. **Fix `RigolDS1104.get_measurements`** to use `:MEAS:ITEM? <ITEM>,CHAN<n>`
   for every item (`vpp→VPP, vmax→VMAX, vmin→VMIN, vavg→VAVG, vrms→VRMS,
   freq→FREQ, period→PER`) and drop the `:MEAS:SOUR` write. Update the fake
   instrument in `tests/unit/test_legacy_scope_extras.py`, which currently
   scripts the old `:MEAS:VPP?` forms (see its `query()`), and the assertion
   in `test_measurements_can_be_limited_to_the_items_asked_for`. The
   `RigolMSO2072A` and `RigolDS1102D` classes may share the pattern; check
   their guides (`~/Manuals/Rigol/_text_extracted/` on the WSL side, or
   `docs/RIGOL_SCOPES.md`) before touching them — the DS1000D/E *does* use
   `:MEAS:VAV?`.
2. **Chase `:WAV:DATA?`** with the reproduction above, client closed. If it
   works through the server once item 1 is in, the cause was the poisoned
   session and the fix is done. If not, compare `_query_binary` against the
   probe line by line (executor thread, `expect_termination`, `header_fmt`),
   and try `:WAV:DATA?` with the scope STOPped vs RUNning.
3. **Bound the server queue.** In `BaseEquipment._query/_write` (or the API
   layer) refuse a request whose client has disconnected, or when more than
   N requests are already waiting on that instrument (return 503 "busy").
   And in `client/ui/instruments/base.py` `_poll`, back off (double the
   interval, cap) after consecutive timeouts instead of re-queueing every
   tick. Without this, one bad command still turns into a 200 s backlog.
4. **Verify on the bench** per `docs/HANDOFF_INSTRUMENT_PANELS.md`
   "Verification": live trace on the DS1054Z in both views, supplies
   unchanged, hidden panels stop polling, clean server log (no "waited" /
   "took"), switching supply↔scope is instant (the selection path is
   non-blocking since `43183db`).
5. Only then consider a `VERSION` bump.

## What is already done on the branch (not yet bench-verified)

- Non-blocking selection: `set_instrument` binds at once, capabilities and
  the new `refresh_settings()` read-back run off the GUI thread; the shell's
  lock release/acquire runs in `_take_control()` off the GUI thread.
- Cheaper `get_readings` (no `:MEAS`), `get_measurements(items=…)`,
  `get_state` skips settings of channels that are off.
- Front-panel view redrawn at DS1000Z proportions with legend-sized keys.
- Slow-I/O warnings in `BaseEquipment` (the log lines above).
- Docs: `docs/INSTRUMENT_PANELS.md` ("Where a lag comes from").

## Files

- `server/equipment/rigol_scope.py` — `LegacyScopeExtras` (waveform,
  trigger, state, cheap readings), `RigolDS1104` (DS1000Z: measurements,
  run/stop/single/autoscale, `get_waveform_raw`).
- `server/equipment/base.py` — `_io_lock`, `_write/_query/_query_binary`,
  `_note_slow_io`, `_recover_usb_stall`, `SLOW_IO_WARN_SEC`.
- `client/ui/instruments/oscilloscope.py` — panel, `poll()`, `_poll_trace()`,
  `refresh_settings()`, front-panel handlers.
- `client/ui/instruments/base.py` — `InstrumentPanel`, `send(priority=)`,
  `commands_pending()`, `run_now_or_soon()`.
- `client/ui/control_panel.py` — shell, `_on_equipment_selected`,
  `_take_control`.
- `scripts/probe_ds1000z.py` — the direct probe.
