"""Find the beeping command by ear. Run this yourself and listen to the scope.

The operator runs this one, because the signal being measured is audible and
the scope is on their bench. Each phase is announced before it starts, runs for
a few seconds, and is followed by silence, so a beep can be attributed to the
phase it happened in.

Why by ear: three probes have now failed to find a refused command
(scripts/probe_window_order.py, probe_panel_beep.py, probe_stream_collision.py
-- inverted windows, every panel call in both acquisition states, and both
pollers at once, all with a clean :SYST:ERR? queue). A DS1000Z can beep without
enqueuing an error, in which case no amount of reading the error queue will
ever show it. So this drives one operation at a time and lets the ear do the
detecting.

Run it from the Pi with the server stopped and the LabLink client closed:

    docker stop -t 10 lablink-server && \
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /tmp/rigol_scope.py:/app/server/equipment/rigol_scope.py:ro \
      -v /tmp/probe_beep_bisect.py:/tmp/b.py:ro \
      lablink-server:latest python -u /tmp/b.py ; \
    docker start lablink-server

Note the -u: unbuffered, so the phase banners appear as they happen rather
than all at the end.

Then say which phase numbers beeped. Any error queue contents are reported
too, so if the beep does turn out to be a refusal we learn that as well.
"""
import asyncio
import os
import sys

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
PHASE_SECONDS = float(os.environ.get("PHASE_SECONDS", "6"))
QUIET_SECONDS = float(os.environ.get("QUIET_SECONDS", "4"))
sys.path.insert(0, "/app")


async def drain(scope):
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


async def phase(scope, number, title, operation, repeat_delay=0.1):
    """Announce, run one operation on repeat, then go quiet."""
    print(f"\n=== PHASE {number}: {title}")
    print(f"    starting now, {PHASE_SECONDS:.0f}s -- LISTEN", flush=True)
    await drain(scope)

    done = asyncio.Event()
    count = [0]
    failures = []

    async def loop():
        while not done.is_set():
            try:
                await operation()
                count[0] += 1
            except Exception as e:
                failures.append(f"{type(e).__name__}: {str(e)[:40]}")
            await asyncio.sleep(repeat_delay)

    task = asyncio.create_task(loop())
    await asyncio.sleep(PHASE_SECONDS)
    done.set()
    await asyncio.gather(task, return_exceptions=True)

    errors = await drain(scope)
    print(f"    PHASE {number} done: {count[0]} operations"
          + (f", {len(failures)} failed ({failures[0]})" if failures else ""))
    if errors:
        print(f"    error queue: {errors[:6]}")
    print(f"    ...silence for {QUIET_SECONDS:.0f}s. Did phase {number} beep?",
          flush=True)
    await asyncio.sleep(QUIET_SECONDS)
    return number, title, errors


async def run():
    from server.equipment.rigol_scope import RigolDS1104

    rm = pyvisa.ResourceManager("@py")
    scope = RigolDS1104(rm, RESOURCE)
    await scope.connect()

    channels = []
    for ch in range(1, scope.num_channels + 1):
        if (await scope._query(f":CHAN{ch}:DISP?")).strip() in ("1", "ON"):
            channels.append(ch)
    was_running = (await scope.get_trigger_status()).strip().upper() != "STOP"

    print(f"scope: {scope.model}, channels displayed {channels}, "
          f"acquisition {'RUN' if was_running else 'STOP'}")
    print(f"leftover errors cleared: {await drain(scope)}")
    print("\nEach phase is announced, runs, then goes quiet. Note which phases beep.")
    print("Phases 2-8 run with the acquisition as found; 9-10 force RUN.",
          flush=True)

    results = []
    try:
        results.append(await phase(
            scope, 1, "nothing at all (baseline -- should be silent)",
            lambda: asyncio.sleep(0.2)))

        results.append(await phase(
            scope, 2, ":TRIG:STAT? only (the RUN/STOP lamp)",
            lambda: scope.get_trigger_status()))

        results.append(await phase(
            scope, 3, "get_readings (:TRIG:STAT?, :TIM:MAIN:SCAL?, :CHAN1:SCAL?)",
            lambda: scope.get_readings(1)))

        results.append(await phase(
            scope, 4, "get_measurements vpp/vavg/freq (:MEAS:ITEM?)",
            lambda: scope.get_measurements(channel=1,
                                           items=["vpp", "vavg", "freq"])))

        results.append(await phase(
            scope, 5, "get_measurements ALL seven items",
            lambda: scope.get_measurements(channel=1)))

        results.append(await phase(
            scope, 6, "windowed trace read, CH1 only (the fix)",
            lambda: scope.get_waveform_data(channel=1, points=600), 0.3))

        results.append(await phase(
            scope, 7, f"windowed trace read, every displayed channel {channels}",
            lambda: asyncio.gather(*[
                scope.get_waveform_data(channel=c, points=600) for c in channels]),
            0.3))

        results.append(await phase(
            scope, 8, "get_waveform, the Equipment tab stream's call, at 10 Hz",
            lambda: scope.get_waveform(channel=1), 0.1))

        print("\n--- forcing the acquisition to RUN for the last two phases")
        await scope._write(":RUN")
        await asyncio.sleep(1.0)

        results.append(await phase(
            scope, 9, "RUNning: windowed trace read, every displayed channel",
            lambda: asyncio.gather(*[
                scope.get_waveform_data(channel=c, points=600) for c in channels]),
            0.3))

        results.append(await phase(
            scope, 10, "RUNning: the panel and the stream together",
            lambda: asyncio.gather(
                scope.get_measurements(channel=1, items=["vpp", "vavg", "freq"]),
                scope.get_waveform_data(channel=1, points=600),
                scope.get_waveform(channel=1),
            ), 0.1))
    finally:
        await scope._write(":RUN" if was_running else ":STOP")
        print(f"\nacquisition left {'RUNning' if was_running else 'STOPped'}, as found")
        print("\nSUMMARY (error queue per phase; the ear is the other half)")
        for number, title, errors in results:
            mark = f"{len(errors)} refused" if errors else "queue clean"
            print(f"  phase {number:2d}  {mark:14s} {title}")
        print("\nTell Claude which phase numbers beeped.", flush=True)
        await scope.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
