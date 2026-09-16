"""Does :WAV:DATA? depend on transfer size? Server stopped.

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /opt/lablink/scripts/probe_wavdata_chunks.py:/tmp/c.py:ro \
      lablink-server:latest python /tmp/c.py
    docker start lablink-server

Where this comes from: :WAV:DATA? timed out on 12 of 13 reads across
scripts/probe_wavdata_paths.py and scripts/probe_wavdata_sync.py, and the one
success returned 1200 valid bytes in 0.02 s. It is not the code path (raw
pyvisa and the driver both fail), not the thread, not a stale-session effect
(:WAV:PRE? answers correctly before every attempt), and not RUN vs STOP.

What is left is the transfer itself. The host kernel logs
`bulk endpoint 0x3 has invalid maxpacket 64` for this DS1054Z -- the scope
misreports its bulk-in packet size -- and a NORMal-mode screen read is
1200 bytes of payload plus an 11-byte IEEE header, so it spans several USB
packets. This sweeps the two things that change how that read is split:

  * pyvisa's ``chunk_size`` (how much the host asks for per USBTMC transfer)
  * the payload itself, via RAW-mode ``:WAV:STARt``/``:WAV:STOP`` windows

If small payloads read reliably and large ones do not, the fix is to read the
trace in windows rather than in one transfer.
"""
import os
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
CHUNKS = [512, 1024, 4096, 20480, 1024 * 1024]
WINDOWS = [100, 600, 1200, 6000]
TRIES = 2


def attempt(inst, label):
    t = time.time()
    try:
        data = bytes(inst.query_binary_values(":WAV:DATA?", datatype="B",
                                              container=bytes))
        print(f"  {label:38s} OK      {len(data):7d} bytes  ({time.time() - t:5.2f}s)")
        return len(data)
    except Exception as e:
        print(f"  {label:38s} {type(e).__name__:7s} {'':7s}        ({time.time() - t:5.2f}s)")
        return 0


def main():
    rm = pyvisa.ResourceManager("@py")
    inst = rm.open_resource(RESOURCE)
    inst.timeout = 10000
    print("IDN:", inst.query("*IDN?").strip())
    print("trigger:", inst.query(":TRIG:STAT?").strip(),
          "  mdep:", inst.query(":ACQ:MDEP?").strip())
    inst.write(":WAV:SOUR CHAN1")
    inst.write(":WAV:FORM BYTE")

    print()
    print("A. NORMal mode (1200-byte screen read) by chunk_size")
    inst.write(":WAV:MODE NORM")
    for chunk in CHUNKS:
        inst.chunk_size = chunk
        inst.query(":WAV:PRE?")
        ok = sum(bool(attempt(inst, f"chunk_size={chunk}")) for _ in range(TRIES))
        print(f"     -> {ok}/{TRIES} succeeded at chunk_size={chunk}")

    print()
    print("B. RAW mode by window size (chunk_size back to the default 20480)")
    inst.chunk_size = 20480
    inst.write(":WAV:MODE RAW")
    for points in WINDOWS:
        inst.write(":WAV:STAR 1")
        inst.write(f":WAV:STOP {points}")
        try:
            inst.query(":WAV:PRE?")
        except Exception as e:
            print(f"  window {points}: PRE? failed {type(e).__name__}")
            continue
        ok = sum(bool(attempt(inst, f"window 1..{points}")) for _ in range(TRIES))
        print(f"     -> {ok}/{TRIES} succeeded for {points} points")

    inst.write(":WAV:MODE NORM")
    inst.close()


if __name__ == "__main__":
    main()
