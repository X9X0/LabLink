"""Does the windowed trace read leave the scope's window inverted? Server stopped.

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /tmp/probe_window_order.py:/tmp/o.py:ro \
      lablink-server:latest python /tmp/o.py
    docker start lablink-server

The first version of LegacyScopeExtras._read_trace_in_blocks set the new
:WAV:STARt before the new :WAV:STOP. Reading forward, that leaves start past
the still-old stop for as long as it takes the next write to arrive, which is
out of range -- and a DS1000Z refuses an out-of-range value with a beep. The
trace still arrived, because the window is valid again before :WAV:DATA? is
sent, so nothing failed and nothing logged. The only symptom was the bench
DS1054Z beeping about twice a second, once per inverted write, while the panel
updated happily between the beeps.

This sends both orders and reads :SYST:ERR? after every single write, so the
rejection is attributed to the exact command that caused it. Expected: two
errors per trace for the old order, none for the new one, and 1200 bytes
either way.
"""
import os
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
TOTAL = 1200
BLOCK = 400


def drain(inst):
    """Empty the error queue, returning what was in it."""
    seen = []
    for _ in range(12):
        try:
            err = inst.query(":SYST:ERR?").strip()
        except Exception as e:
            seen.append(f"<{type(e).__name__}>")
            break
        if err.split(",")[0].lstrip("+") == "0":
            break
        seen.append(err)
    return seen


def write_checked(inst, cmd, errors):
    """Write one command and note any error it provoked."""
    inst.write(cmd)
    err = inst.query(":SYST:ERR?").strip()
    if err.split(",")[0].lstrip("+") != "0":
        errors.append((cmd, err))
        print(f"    {cmd:18s} -> REFUSED {err}")
    else:
        print(f"    {cmd:18s} -> ok")


def read_blocks(inst, stop_first, label):
    """One full windowed trace read, counting rejected commands."""
    print(f"  {label}")
    errors = []
    got = bytearray()

    # Reset to the whole screen, as the driver does before the preamble.
    write_checked(inst, f":WAV:STOP {TOTAL}", errors)
    write_checked(inst, ":WAV:STAR 1", errors)
    inst.query(":WAV:PRE?")

    start = 1
    while start <= TOTAL:
        stop = min(start + BLOCK - 1, TOTAL)
        pair = ([f":WAV:STOP {stop}", f":WAV:STAR {start}"] if stop_first
                else [f":WAV:STAR {start}", f":WAV:STOP {stop}"])
        for cmd in pair:
            write_checked(inst, cmd, errors)
        block = bytes(inst.query_binary_values(":WAV:DATA?", datatype="B",
                                               container=bytes))
        got.extend(block)
        start = stop + 1

    print(f"    -> {len(got)} bytes, {len(errors)} command(s) refused")
    return len(got), errors


def main():
    rm = pyvisa.ResourceManager("@py")
    inst = rm.open_resource(RESOURCE)
    inst.timeout = 10000
    print("IDN:", inst.query("*IDN?").strip())
    print("cleared at start:", drain(inst))
    inst.write(":WAV:SOUR CHAN1")
    inst.write(":WAV:MODE NORM")
    inst.write(":WAV:FORM BYTE")

    print()
    print("A. the order that shipped: new :WAV:STARt before new :WAV:STOP")
    a_bytes, a_errors = read_blocks(inst, stop_first=False,
                                    label="STAR then STOP")
    print("    queue after:", drain(inst))

    print()
    print("B. the corrected order: :WAV:STOP first")
    time.sleep(0.5)
    b_bytes, b_errors = read_blocks(inst, stop_first=True,
                                    label="STOP then STAR")
    print("    queue after:", drain(inst))

    print()
    print(f"A: {a_bytes} bytes, {len(a_errors)} refused "
          f"{[c for c, _ in a_errors]}")
    print(f"B: {b_bytes} bytes, {len(b_errors)} refused "
          f"{[c for c, _ in b_errors]}")
    print("VERDICT:", "B is silent and A is not -- the fix is right"
          if len(b_errors) == 0 and len(a_errors) > 0
          else "not the expected difference; look again before shipping")

    inst.close()


if __name__ == "__main__":
    main()
