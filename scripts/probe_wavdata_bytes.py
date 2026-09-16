"""What does the DS1000Z actually put on the wire for :WAV:DATA?? Server stopped.

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /opt/lablink/scripts/probe_wavdata_bytes.py:/tmp/b.py:ro \
      lablink-server:latest python /tmp/b.py
    docker start lablink-server

scripts/probe_wavdata_chunks.py found that NORMal-mode reads (1200 bytes) time
out at every chunk_size, while RAW-mode reads always complete -- but return
only 15 bytes whatever window is asked for. 15 bytes is not a trace, so before
rewriting the driver around RAW windows we need to see the bytes themselves.

This bypasses query_binary_values and reads the reply as-is, so the IEEE header
is visible: a DS1000Z screen dump should begin b'#9000001200'.
"""
import os
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)


def raw_read(inst, label):
    t = time.time()
    try:
        inst.write(":WAV:DATA?")
        data = inst.read_raw()
        dt = time.time() - t
        print(f"  {label:26s} {len(data):7d} bytes in {dt:5.2f}s")
        print(f"       head: {data[:40]!r}")
        print(f"       tail: {data[-8:]!r}")
        return data
    except Exception as e:
        print(f"  {label:26s} FAIL {type(e).__name__} in {time.time() - t:5.2f}s: "
              f"{str(e)[:50]}")
        return b""


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
    print("A. NORMal mode, read_raw")
    inst.write(":WAV:MODE NORM")
    print("   preamble:", inst.query(":WAV:PRE?").strip())
    raw_read(inst, "NORM attempt 1")
    raw_read(inst, "NORM attempt 2 (retry)")

    print()
    print("B. RAW mode, read_raw, 1..1200")
    inst.write(":WAV:MODE RAW")
    inst.write(":WAV:STAR 1")
    inst.write(":WAV:STOP 1200")
    print("   preamble:", inst.query(":WAV:PRE?").strip())
    raw_read(inst, "RAW 1..1200")

    print()
    print("C. RAW mode after an explicit :STOP and a fixed memory depth")
    inst.write(":STOP")
    inst.write(":ACQ:MDEP 12000")
    print("   mdep now:", inst.query(":ACQ:MDEP?").strip())
    inst.write(":WAV:MODE RAW")
    inst.write(":WAV:STAR 1")
    inst.write(":WAV:STOP 1200")
    print("   preamble:", inst.query(":WAV:PRE?").strip())
    raw_read(inst, "RAW 1..1200 (mdep 12k)")

    print()
    print("D. any error the scope is holding")
    for _ in range(3):
        try:
            err = inst.query(":SYST:ERR?").strip()
            print("   :SYST:ERR? ->", err)
            if err.startswith("0,") or err.startswith("+0,"):
                break
        except Exception as e:
            print("   :SYST:ERR? failed:", type(e).__name__)
            break

    inst.write(":WAV:MODE NORM")
    inst.write(":ACQ:MDEP AUTO")
    inst.close()


if __name__ == "__main__":
    main()
