"""Does the driver's own get_waveform_data return a trace now? Server stopped.

Mount the working tree's driver over the image's copy so this exercises the
real code path -- BaseEquipment._query_binary, the I/O lock, the executor --
and not a hand-rolled imitation of it:

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /tmp/rigol_scope.py:/app/server/equipment/rigol_scope.py:ro \
      -v /tmp/probe_driver_trace.py:/tmp/d.py:ro \
      lablink-server:latest python /tmp/d.py
    docker start lablink-server

Expected, if the windowed read in LegacyScopeExtras._read_trace_in_blocks is
right: 1200 samples, three :WAV:DATA? reads, about a second, with the scope
left in whatever run state it was found in.
"""
import asyncio
import os
import sys
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
sys.path.insert(0, "/app")


async def run():
    from server.equipment.rigol_scope import RigolDS1104

    rm = pyvisa.ResourceManager("@py")
    scope = RigolDS1104(rm, RESOURCE)
    await scope.connect()
    print("connected:", scope.model, "block size:", scope.trace_block_points)
    print("before:", await scope.get_readings(1))

    try:
        for attempt in (1, 2, 3):
            t = time.time()
            try:
                data = await scope.get_waveform_data(channel=1)
                dt = time.time() - t
                v = data["voltage"]
                print(f"  attempt {attempt}: {data['num_samples']} samples in {dt:.2f}s"
                      f"  first={v[0]:+.4f}V  last={v[-1]:+.4f}V"
                      f"  min={min(v):+.4f}  max={max(v):+.4f}")
            except Exception as e:
                print(f"  attempt {attempt}: FAIL {type(e).__name__}: {str(e)[:60]}"
                      f"  ({time.time() - t:.2f}s)")

        print("decimated to 600, the way the panel asks for it:")
        t = time.time()
        try:
            data = await scope.get_waveform_data(channel=1, points=600)
            print(f"  {data['num_samples']} samples in {time.time() - t:.2f}s"
                  f"  x_increment={data['x_increment']:.3e}")
        except Exception as e:
            print(f"  FAIL {type(e).__name__}: {str(e)[:60]}")

        print("measurements, the other half of the fix:")
        t = time.time()
        try:
            meas = await scope.get_measurements(channel=1, items=["vpp", "vavg", "freq"])
            print(f"  {meas}  ({time.time() - t:.2f}s)")
        except Exception as e:
            print(f"  FAIL {type(e).__name__}: {str(e)[:60]}")

        print("after:", await scope.get_readings(1))
    finally:
        await scope.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
