"""Which command is the DS1000Z rejecting with -113? Server stopped.

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /opt/lablink/scripts/probe_wavdata_error.py:/tmp/e.py:ro \
      lablink-server:latest python /tmp/e.py
    docker start lablink-server

scripts/probe_wavdata_bytes.py left the scope holding -113 "Undefined header"
and -410 "Query INTERRUPTED". A query the scope never recognised would explain
the timeouts exactly: no reply is ever sent, so the read waits out the full
timeout. This drains the error queue first, then sends one command at a time
and reads the queue after each, so a -113 can be attributed to the command
that caused it.
"""
import os
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)


def drain(inst, label="queue"):
    seen = []
    for _ in range(12):
        try:
            err = inst.query(":SYST:ERR?").strip()
        except Exception as e:
            seen.append(f"<{type(e).__name__}>")
            break
        seen.append(err)
        if err.split(",")[0].lstrip("+") == "0":
            break
    print(f"   {label}: {seen}")


def step(inst, cmd, is_query=False, timeout_note=""):
    t = time.time()
    try:
        if is_query:
            reply = inst.query(cmd).strip()
            print(f"  {cmd:24s} -> {reply[:48]!r} ({time.time() - t:5.2f}s)")
        else:
            inst.write(cmd)
            print(f"  {cmd:24s} written ({time.time() - t:5.2f}s)")
    except Exception as e:
        print(f"  {cmd:24s} -> FAIL {type(e).__name__} ({time.time() - t:5.2f}s) {timeout_note}")
    drain(inst, "after")


def main():
    rm = pyvisa.ResourceManager("@py")
    inst = rm.open_resource(RESOURCE)
    inst.timeout = 10000
    print("IDN:", inst.query("*IDN?").strip())
    drain(inst, "queue at start")

    print()
    print("A. the NORMal setup, one command at a time")
    step(inst, ":WAV:SOUR CHAN1")
    step(inst, ":WAV:MODE NORM")
    step(inst, ":WAV:FORM BYTE")
    step(inst, ":WAV:PRE?", is_query=True)

    print()
    print("B. the read that times out -- error queue read straight after")
    t = time.time()
    try:
        inst.write(":WAV:DATA?")
        data = inst.read_raw()
        print(f"  :WAV:DATA? -> {len(data)} bytes ({time.time() - t:5.2f}s)")
    except Exception as e:
        print(f"  :WAV:DATA? -> FAIL {type(e).__name__} ({time.time() - t:5.2f}s)")
    drain(inst, "after :WAV:DATA?")

    print()
    print("C. the same read with the scope RUNning, then STOPped again")
    step(inst, ":RUN")
    time.sleep(1.0)
    step(inst, ":WAV:MODE NORM")
    t = time.time()
    try:
        inst.write(":WAV:DATA?")
        data = inst.read_raw()
        print(f"  :WAV:DATA? (RUN) -> {len(data)} bytes ({time.time() - t:5.2f}s)"
              f" head={data[:16]!r}")
    except Exception as e:
        print(f"  :WAV:DATA? (RUN) -> FAIL {type(e).__name__} ({time.time() - t:5.2f}s)")
    drain(inst, "after :WAV:DATA? (RUN)")
    step(inst, ":STOP")

    print()
    print("D. a slower timebase, where a screen read has real samples behind it")
    step(inst, ":TIM:MAIN:SCAL 0.001")
    step(inst, ":RUN")
    time.sleep(1.5)
    step(inst, ":STOP")
    step(inst, ":WAV:MODE NORM")
    step(inst, ":WAV:PRE?", is_query=True)
    t = time.time()
    try:
        inst.write(":WAV:DATA?")
        data = inst.read_raw()
        print(f"  :WAV:DATA? (1ms/div) -> {len(data)} bytes ({time.time() - t:5.2f}s)"
              f" head={data[:16]!r}")
    except Exception as e:
        print(f"  :WAV:DATA? (1ms/div) -> FAIL {type(e).__name__} ({time.time() - t:5.2f}s)")
    drain(inst, "after 1ms/div read")

    print()
    print("E. put the bench back the way it was found: 5 ns/div, STOPped")
    step(inst, ":TIM:MAIN:SCAL 5e-09")
    step(inst, ":TIM:MAIN:SCAL?", is_query=True)
    inst.close()


if __name__ == "__main__":
    main()
