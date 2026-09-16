"""Which command makes the DS1054Z beep while the scope panel polls? Server stopped.

Mount the working tree's driver over the image's copy, so this is the real
code path and not an imitation of it:

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /tmp/rigol_scope.py:/app/server/equipment/rigol_scope.py:ro \
      -v /tmp/probe_panel_beep.py:/tmp/p.py:ro \
      lablink-server:latest python /tmp/p.py
    docker start lablink-server

Reported from the bench: with the scope panel running, the DS1054Z beeps about
twice a second while the trace updates normally between beeps. A DS1000Z beeps
when it refuses a command, so something the panel sends is being refused --
and it cannot be anything that breaks the data, because the panel works.

scripts/probe_window_order.py ruled out the first guess: an inverted
:WAV:STARt/:WAV:STOP window is accepted silently, both orders, no errors.

So this replays what the panel actually does, in the order it does it, and
reads :SYST:ERR? after every driver call -- the queue is drained first so any
error found belongs to the call that just ran. The panel's cycle is:
``get_trigger_status`` and ``get_measurements`` on the 500 ms poll
(client/ui/instruments/oscilloscope.py, ``poll``), ``get_waveform_data`` once
per *enabled channel* on the 1 s trace timer (``_poll_trace``), plus
``get_state`` on selection. Three channels are displayed on this bench, so a
trace tick is three waveform reads, not one.
"""
import asyncio
import os
import sys

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
CYCLES = int(os.environ.get("CYCLES", "3"))
sys.path.insert(0, "/app")


async def drain(scope, label=""):
    """Empty the error queue, returning what was in it."""
    seen = []
    for _ in range(16):
        try:
            err = (await scope._query(":SYST:ERR?")).strip()
        except Exception as e:
            seen.append(f"<{type(e).__name__}>")
            break
        if err.split(",")[0].lstrip("+") == "0":
            break
        seen.append(err)
    if label and seen:
        print(f"    {label}: {seen}")
    return seen


async def step(scope, name, coro_factory):
    """Run one panel operation, then report any error it provoked."""
    try:
        result = await coro_factory()
        ok = "ok"
    except Exception as e:
        result = None
        ok = f"FAILED {type(e).__name__}: {str(e)[:40]}"
    errors = await drain(scope)
    flag = "  <-- BEEPS" if errors else ""
    detail = ""
    if isinstance(result, dict):
        detail = f"{len(result)} field(s)"
        if "num_samples" in result:
            detail = f"{result['num_samples']} samples"
    elif result is not None:
        detail = str(result)[:28]
    print(f"  {name:38s} {ok:10s} {detail:16s} {errors if errors else ''}{flag}")
    return errors


async def run():
    from server.equipment.rigol_scope import RigolDS1104

    rm = pyvisa.ResourceManager("@py")
    scope = RigolDS1104(rm, RESOURCE)
    await scope.connect()
    print("connected:", scope.model, " block size:", scope.trace_block_points)
    await drain(scope, "queue at start (leftovers, not attributable)")

    shown = []
    for ch in range(1, scope.num_channels + 1):
        try:
            if (await scope._query(f":CHAN{ch}:DISP?")).strip() in ("1", "ON"):
                shown.append(ch)
        except Exception:
            pass
    print("displayed channels:", shown or "[none - the panel would fetch nothing]")
    await drain(scope)

    was_running = (await scope.get_trigger_status()).strip().upper() != "STOP"
    await drain(scope)

    offenders = {}
    try:
        print()
        print("get_state, as the panel does once on selection")
        errs = await step(scope, "get_state", lambda: scope.get_state())
        if errs:
            offenders["get_state"] = errs

        # The panel was reported beeping after the operator pressed Start, so
        # run the whole cycle in both acquisition states. A DS1000Z reads the
        # *screen* in NORMal mode, and a screen that is being repainted by a
        # live acquisition is a different thing to read from a frozen one.
        for state in ("STOP", "RUN"):
            print()
            print(f"===== acquisition {state} =====")
            await scope._write(f":{state}")
            await asyncio.sleep(1.0)
            await drain(scope, f":{state} itself")

            for cycle in range(CYCLES):
                print()
                print(f"--- {state} cycle {cycle + 1}: the 500 ms poll, then a trace tick")
                errs = await step(scope, "get_trigger_status",
                                  lambda: scope.get_trigger_status())
                if errs:
                    offenders[f"{state}: get_trigger_status"] = errs

                errs = await step(
                    scope, "get_measurements vpp/vavg/freq",
                    lambda: scope.get_measurements(channel=1,
                                                   items=["vpp", "vavg", "freq"]))
                if errs:
                    offenders[f"{state}: get_measurements"] = errs

                errs = await step(scope, "get_readings",
                                  lambda: scope.get_readings(1))
                if errs:
                    offenders[f"{state}: get_readings"] = errs

                for ch in shown:
                    errs = await step(
                        scope, f"get_waveform_data CH{ch}",
                        lambda c=ch: scope.get_waveform_data(channel=c, points=600))
                    if errs:
                        offenders[f"{state}: get_waveform_data CH{ch}"] = errs
    finally:
        print()
        if offenders:
            print("REFUSED COMMANDS, by the call that sent them:")
            for name, errs in offenders.items():
                print(f"  {name}: {errs}")
        else:
            print("No call was refused in either acquisition state. The beep is "
                  "not a rejected command from the panel's cycle; look at what "
                  "else the client sends, or at the beeper setting.")
        # Leave the acquisition as it was found.
        await scope._write(":RUN" if was_running else ":STOP")
        print(f"acquisition left {'RUNning' if was_running else 'STOPped'}, as found")
        await scope.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
