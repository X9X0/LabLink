"""Does the Equipment tab's waveform stream collide with the panel's trace read?

Server stopped; mount the working tree's driver over the image's copy:

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /tmp/rigol_scope.py:/app/server/equipment/rigol_scope.py:ro \
      -v /tmp/probe_stream_collision.py:/tmp/c.py:ro \
      lablink-server:latest python /tmp/c.py
    docker start lablink-server

Reported from the bench: after pressing Start Streaming, the DS1054Z beeps
about twice a second while the Control tab's trace keeps updating normally.

Ruled out already, each by measurement: an inverted :WAV:STARt/:WAV:STOP
window (accepted silently, scripts/probe_window_order.py), and every call the
Control tab panel makes, in both acquisition states, one at a time
(scripts/probe_panel_beep.py -- nothing refused).

What neither of those reproduced is *two* pollers at once. The Equipment tab's
Start Streaming button opens a waveform stream at interval_ms=100
(client/ui/equipment/oscilloscope_panel.py), and the server's stream loop
answers it with ``get_waveform`` (server/websocket_server.py, ``_stream_data``),
which rewrites :WAV:SOUR, :WAV:MODE and :WAV:FORM ten times a second. The
Control tab's trace read holds the I/O lock per exchange, not across the whole
windowed sequence, so the stream can land between two blocks and move the
waveform subsystem under it.

Three phases, each followed by a drained error queue:
  1. the panel's cycle alone      -- expected clean, as already measured
  2. the stream alone             -- 10 Hz get_waveform, nothing else
  3. both at once                 -- the reported configuration
"""
import asyncio
import os
import sys
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
SECONDS = float(os.environ.get("PHASE_SECONDS", "10"))
sys.path.insert(0, "/app")


async def drain(scope):
    """Empty the error queue, returning what was in it."""
    seen = []
    for _ in range(40):
        try:
            err = (await scope._query(":SYST:ERR?")).strip()
        except Exception as e:
            seen.append(f"<{type(e).__name__}>")
            break
        if err.split(",")[0].lstrip("+") == "0":
            break
        seen.append(err)
    return seen


async def panel_loop(scope, channels, stop, counts):
    """The Control tab: measurements twice a second, a trace per channel once."""
    while not stop.is_set():
        try:
            await scope.get_measurements(channel=1, items=["vpp", "vavg", "freq"])
            counts["measurements"] += 1
        except Exception as e:
            counts.setdefault("panel_errors", []).append(f"meas: {type(e).__name__}")
        for ch in channels:
            if stop.is_set():
                break
            try:
                await scope.get_waveform_data(channel=ch, points=600)
                counts["traces"] += 1
            except Exception as e:
                counts.setdefault("panel_errors", []).append(
                    f"trace CH{ch}: {type(e).__name__}")
        await asyncio.sleep(0.05)


async def stream_loop(scope, stop, counts):
    """The Equipment tab's stream: get_waveform every 100 ms."""
    while not stop.is_set():
        try:
            await scope.get_waveform(channel=1)
            counts["stream"] += 1
        except Exception as e:
            counts.setdefault("stream_errors", []).append(type(e).__name__)
        await asyncio.sleep(0.1)


async def phase(scope, name, channels, want_panel, want_stream):
    print()
    print(f"--- {name} ({SECONDS:.0f}s)")
    await drain(scope)
    stop = asyncio.Event()
    counts = {"measurements": 0, "traces": 0, "stream": 0}
    tasks = []
    if want_panel:
        tasks.append(asyncio.create_task(panel_loop(scope, channels, stop, counts)))
    if want_stream:
        tasks.append(asyncio.create_task(stream_loop(scope, stop, counts)))

    started = time.monotonic()
    await asyncio.sleep(SECONDS)
    stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.monotonic() - started

    errors = await drain(scope)
    print(f"    did: {counts['traces']} traces, {counts['measurements']} measurement "
          f"polls, {counts['stream']} stream reads in {elapsed:.1f}s")
    for key in ("panel_errors", "stream_errors"):
        if counts.get(key):
            shown = counts[key][:4]
            print(f"    {key}: {len(counts[key])} "
                  f"({', '.join(shown)}{' ...' if len(counts[key]) > 4 else ''})")
    if errors:
        print(f"    SCOPE REFUSED {len(errors)} command(s)  <-- BEEPS")
        for err in errors[:8]:
            print(f"      {err}")
    else:
        print("    scope error queue clean")
    return errors


async def run():
    from server.equipment.rigol_scope import RigolDS1104

    rm = pyvisa.ResourceManager("@py")
    scope = RigolDS1104(rm, RESOURCE)
    await scope.connect()
    print("connected:", scope.model, " block size:", scope.trace_block_points)

    channels = []
    for ch in range(1, scope.num_channels + 1):
        if (await scope._query(f":CHAN{ch}:DISP?")).strip() in ("1", "ON"):
            channels.append(ch)
    print("displayed channels:", channels)
    was_running = (await scope.get_trigger_status()).strip().upper() != "STOP"
    print("acquisition:", "RUN" if was_running else "STOP")
    print("leftovers cleared:", await drain(scope))

    try:
        a = await phase(scope, "1. panel alone", channels, True, False)
        b = await phase(scope, "2. stream alone", channels, False, True)
        c = await phase(scope, "3. panel AND stream together", channels, True, True)

        print()
        print("VERDICT")
        print(f"  panel alone : {len(a)} refused")
        print(f"  stream alone: {len(b)} refused")
        print(f"  both        : {len(c)} refused")
        if c and not a and not b:
            print("  -> only the combination is refused: the two pollers are "
                  "colliding on the waveform subsystem.")
        elif b and not a:
            print("  -> the stream alone is refused: get_waveform is the problem, "
                  "not the collision.")
        elif a:
            print("  -> the panel alone is refused, which the earlier one-at-a-time "
                  "probe did not show: rate matters.")
        else:
            print("  -> nothing refused in any phase; the beep is elsewhere.")
    finally:
        await scope._write(":RUN" if was_running else ":STOP")
        await scope.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
