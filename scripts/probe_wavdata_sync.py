"""Is the DS1000Z :WAV:DATA? read one response behind? Server stopped.

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /opt/lablink/scripts/probe_wavdata_sync.py:/tmp/s.py:ro \
      lablink-server:latest python /tmp/s.py
    docker start lablink-server

scripts/probe_wavdata_paths.py found that on a fresh session the first two
:WAV:DATA? reads time out and the third returns 1200 valid bytes in 0.02 s --
the same call, so the difference is not the code path. That looks like the
reads running behind the instrument's answers rather than the instrument
failing to answer.

This alternates the source channel between reads. CH1, CH2 and CH3 hold
visibly different traces, so if a read asking for CH<n> returns the bytes
belonging to the previous request, the source is desynchronised and the
server would be drawing a stale trace whenever it appears to work at all.
Each cycle prints the requested channel, the outcome, and a fingerprint of
the payload (mean sample code) to compare against the preamble's channel.
"""
import os
import statistics
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
CYCLES = int(os.environ.get("CYCLES", "8"))


def main():
    rm = pyvisa.ResourceManager("@py")
    inst = rm.open_resource(RESOURCE)
    inst.timeout = 10000
    print("IDN:", inst.query("*IDN?").strip())
    print("trigger:", inst.query(":TRIG:STAT?").strip())

    shown = [ch for ch in (1, 2, 3, 4)
             if inst.query(f":CHAN{ch}:DISP?").strip() == "1"]
    print("displayed channels:", shown)
    if len(shown) < 2:
        print("NOTE: fewer than two channels displayed; the desync test needs two.")

    # A per-channel fingerprint taken while everything is known-good, to
    # compare the payloads against later.
    print()
    print(f"{'cycle':>5} {'asked':>5} {'result':>9} {'secs':>6} {'bytes':>6} "
          f"{'mean':>7} {'stdev':>7}  first 8 sample codes")
    for i in range(CYCLES):
        ch = shown[i % len(shown)] if shown else 1
        inst.write(f":WAV:SOUR CHAN{ch}")
        inst.write(":WAV:MODE NORM")
        inst.write(":WAV:FORM BYTE")
        try:
            inst.query(":WAV:PRE?")
        except Exception as e:
            print(f"{i:5d} {ch:5d}  PRE? failed: {type(e).__name__}")
            continue
        t = time.time()
        try:
            data = bytes(inst.query_binary_values(":WAV:DATA?", datatype="B",
                                                  container=bytes))
            dt = time.time() - t
            mean = statistics.fmean(data)
            sd = statistics.pstdev(data)
            print(f"{i:5d} {ch:5d} {'OK':>9} {dt:6.2f} {len(data):6d} "
                  f"{mean:7.1f} {sd:7.1f}  {list(data[:8])}")
        except Exception as e:
            dt = time.time() - t
            print(f"{i:5d} {ch:5d} {'TIMEOUT':>9} {dt:6.2f} {'':6s} "
                  f"{'':7s} {'':7s}  {type(e).__name__}")

    print()
    print("A source desync shows up as a payload whose fingerprint belongs to")
    print("the channel asked for in the PREVIOUS cycle.")
    inst.close()


if __name__ == "__main__":
    main()
