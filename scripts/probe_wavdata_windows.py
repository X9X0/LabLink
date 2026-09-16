"""Can the 1200-point screen trace be read in windows? Server stopped.

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /opt/lablink/scripts/probe_wavdata_windows.py:/tmp/w.py:ro \
      lablink-server:latest python /tmp/w.py
    docker start lablink-server

scripts/probe_wavdata_threshold.py measured the wall: any single reply from
this DS1054Z of >=500 bytes times out, while <=492 bytes reads fine, in
multiple packets. The scope declares wMaxPacketSize 64 on both bulk endpoints
where USB 2.0 high speed requires 512, and the Pi's kernel says so
(`bulk endpoint 0x82 has invalid maxpacket 64`). A NORMal screen read is
1212 bytes, so it can never succeed over libusb; that is the whole reason the
panel shows no trace.

The fix has to split the read. This checks the two ways of doing that:

  A. NORMal mode honouring :WAV:STARt/:WAV:STOP. If it does, the trace can be
     read in three 400-point windows with the scope left RUNning -- no change
     to what the operator sees on the front panel. This is the one we want.
  B. RAW mode windows, which need the acquisition STOPped. Works, but the
     driver would have to stop and restart the scope around every trace.

Both are stitched back together and checked for length and for continuity at
the seams.
"""
import os
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
WINDOW = 400


def read_block(inst):
    """One :WAV:DATA? as raw bytes, IEEE header stripped."""
    inst.write(":WAV:DATA?")
    data = inst.read_raw()
    if not data.startswith(b"#"):
        raise ValueError(f"no IEEE header: {data[:16]!r}")
    ndigits = int(data[1:2])
    length = int(data[2:2 + ndigits])
    payload = data[2 + ndigits:2 + ndigits + length]
    if len(payload) != length:
        raise ValueError(f"short block: header says {length}, got {len(payload)}")
    return payload


def windowed(inst, total=1200, window=WINDOW):
    out = bytearray()
    t = time.time()
    for start in range(1, total + 1, window):
        stop = min(start + window - 1, total)
        inst.write(f":WAV:STAR {start}")
        inst.write(f":WAV:STOP {stop}")
        block = read_block(inst)
        print(f"     {start:5d}..{stop:<5d} {len(block):5d} bytes")
        out.extend(block)
    print(f"     stitched {len(out)} bytes in {time.time() - t:.2f}s")
    return bytes(out)


def seams(data, window=WINDOW):
    """Step sizes at the window boundaries vs. the typical step inside one."""
    if len(data) < window + 2:
        return "too short to check"
    inside = [abs(data[i + 1] - data[i]) for i in range(0, window - 1)]
    typical = sorted(inside)[len(inside) // 2]
    out = []
    for b in range(window, len(data), window):
        out.append(f"at {b}: step {abs(data[b] - data[b - 1])}")
    return f"median step inside a window {typical}; " + ", ".join(out)


def main():
    rm = pyvisa.ResourceManager("@py")
    inst = rm.open_resource(RESOURCE)
    inst.timeout = 5000
    print("IDN:", inst.query("*IDN?").strip())

    # A timebase with a real signal shape on it, so seams are visible.
    inst.write(":TIM:MAIN:SCAL 0.001")
    inst.write(":RUN")
    time.sleep(1.5)
    inst.write(":WAV:SOUR CHAN1")
    inst.write(":WAV:FORM BYTE")

    print()
    print("A. NORMal mode with :WAV:STARt/:WAV:STOP, scope left RUNning")
    inst.write(":WAV:MODE NORM")
    print("   preamble:", inst.query(":WAV:PRE?").strip())
    try:
        data = windowed(inst, 1200, WINDOW)
        print(f"   -> {len(data)} bytes; {seams(data)}")
        print("   NORMal windows work: the trace can be read without stopping.")
    except Exception as e:
        print(f"   FAILED: {type(e).__name__}: {str(e)[:70]}")
        try:
            inst.query(":SYST:ERR?")
        except Exception:
            pass
        print("   -> NORMal ignores the window; only RAW can be split.")

    print()
    print("B. RAW mode windows, acquisition STOPped")
    inst.write(":STOP")
    time.sleep(0.3)
    inst.write(":WAV:MODE RAW")
    print("   preamble:", inst.query(":WAV:PRE?").strip())
    try:
        data = windowed(inst, 1200, WINDOW)
        print(f"   -> {len(data)} bytes; {seams(data)}")
    except Exception as e:
        print(f"   FAILED: {type(e).__name__}: {str(e)[:70]}")

    print()
    print("putting the bench back: 5 ns/div, NORMal, STOPped")
    inst.write(":WAV:MODE NORM")
    inst.write(":TIM:MAIN:SCAL 5e-09")
    print("timebase now:", inst.query(":TIM:MAIN:SCAL?").strip())
    inst.close()


if __name__ == "__main__":
    main()
