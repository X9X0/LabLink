"""Why does :WAV:DATA? time out inside the LabLink server but not in a direct
probe? Run this with the server stopped; it tries the same read four ways in
one process on one session, so the only variable is the code path.

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /opt/lablink/scripts/probe_wavdata_paths.py:/tmp/w.py:ro \
      lablink-server:latest python /tmp/w.py
    docker start lablink-server

Variants, in order:
  1. raw, container=bytes          -- exactly what scripts/probe_ds1000z.py does
  2. raw, container=list           -- exactly what BaseEquipment._query_binary does
  3. raw, container=list, in a thread-pool executor (the server runs it there)
  4. the driver itself: RigolDS1104.get_waveform_data through _query_binary

Each variant re-sends the :WAV:SOUR/:WAV:MODE/:WAV:FORM setup and :WAV:PRE?
first, so every one starts from the same instrument state. See
docs/HANDOFF_SCOPE_LAG.md item 4.
"""
import asyncio
import functools
import os
import sys
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
sys.path.insert(0, "/app")


def report(label, fn):
    t = time.time()
    try:
        data = fn()
        if isinstance(data, dict):
            detail = f"{data.get('num_samples')} samples, first={data['voltage'][0]:+.4f} V"
        else:
            detail = f"{len(data)} bytes, head={bytes(data[:12])!r}"
        print(f"  {label:44s} OK   {detail}  ({time.time() - t:.2f}s)")
        return True
    except Exception as e:
        print(f"  {label:44s} FAIL {type(e).__name__}: {str(e)[:60]}  ({time.time() - t:.2f}s)")
        return False


def setup(inst, ch=1):
    inst.write(f":WAV:SOUR CHAN{ch}")
    inst.write(":WAV:MODE NORM")
    inst.write(":WAV:FORM BYTE")
    return inst.query(":WAV:PRE?").strip()


def main():
    rm = pyvisa.ResourceManager("@py")
    inst = rm.open_resource(RESOURCE)
    inst.timeout = 10000            # the server's timeout, not the probe's 5 s
    print("IDN:", inst.query("*IDN?").strip())
    print("trigger:", inst.query(":TRIG:STAT?").strip(),
          " chunk_size:", inst.chunk_size)

    disp = {ch: inst.query(f":CHAN{ch}:DISP?").strip() for ch in (1, 2, 3, 4)}
    ch = next((c for c, d in disp.items() if d == "1"), 1)
    print(f"reading CH{ch} (displayed: {[c for c, d in disp.items() if d == '1']})")

    print("1. raw, container=bytes (the direct probe's call)")
    print("   preamble:", setup(inst, ch))
    report("query_binary_values(container=bytes)",
           lambda: bytes(inst.query_binary_values(":WAV:DATA?", datatype="B",
                                                  container=bytes)))

    print("2. raw, container=list (the server's call)")
    print("   preamble:", setup(inst, ch))
    report("query_binary_values(datatype='B')",
           lambda: bytes(inst.query_binary_values(":WAV:DATA?", datatype="B")))

    print("3. same call, but on a thread-pool executor thread")
    print("   preamble:", setup(inst, ch))

    async def in_executor():
        loop = asyncio.get_event_loop()
        return bytes(await loop.run_in_executor(
            None,
            functools.partial(inst.query_binary_values, ":WAV:DATA?", datatype="B"),
        ))

    report("run_in_executor(query_binary_values)",
           lambda: asyncio.new_event_loop().run_until_complete(in_executor()))

    inst.close()

    print("4. the driver's own get_waveform_data")
    try:
        from server.equipment.rigol_scope import RigolDS1104
        rm2 = pyvisa.ResourceManager("@py")
        scope = RigolDS1104(rm2, RESOURCE)

        async def via_driver():
            await scope.connect()
            try:
                return await scope.get_waveform_data(channel=ch, points=600)
            finally:
                await scope.disconnect()

        report("RigolDS1104.get_waveform_data",
               lambda: asyncio.new_event_loop().run_until_complete(via_driver()))
    except Exception as e:
        print(f"  driver path unavailable: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
