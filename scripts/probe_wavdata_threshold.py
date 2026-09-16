"""Where exactly does a DS1000Z read stop working? Server stopped.

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /opt/lablink/scripts/probe_wavdata_threshold.py:/tmp/t.py:ro \
      lablink-server:latest python /tmp/t.py
    docker start lablink-server

lsusb says this scope declares wMaxPacketSize 64 on both bulk endpoints, which
is illegal for USB 2.0 high speed (it must be 512), and the Pi's kernel logs
`bulk endpoint 0x82 has invalid maxpacket 64` for it. Every exchange that works
today returns under 64 bytes (*IDN?, :WAV:PRE?, :MEAS:ITEM?); the one that
never works is the 1212-byte NORMal screen read.

This asks for RAW windows of growing size at a timebase slow enough to have
real samples behind them, so the reply length is the only thing changing. If
reads fail from the first size past 64 bytes, the mis-declared packet size is
the cause and no amount of driver rework will fix it over libusb.
"""
import os
import time

import pyvisa

RESOURCE = os.environ.get(
    "SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"
)
SIZES = [250, 300, 350, 400, 450, 480, 500, 512, 520, 550, 600, 250, 500]


def main():
    rm = pyvisa.ResourceManager("@py")
    inst = rm.open_resource(RESOURCE)
    inst.timeout = 5000
    print("IDN:", inst.query("*IDN?").strip())

    # A timebase with real memory behind it, and a stopped acquisition so RAW
    # reads are legal.
    inst.write(":TIM:MAIN:SCAL 0.001")
    inst.write(":RUN")
    time.sleep(1.5)
    inst.write(":STOP")
    time.sleep(0.3)
    inst.write(":WAV:SOUR CHAN1")
    inst.write(":WAV:FORM BYTE")
    inst.write(":WAV:MODE RAW")
    print("preamble:", inst.query(":WAV:PRE?").strip())
    print("mdep:", inst.query(":ACQ:MDEP?").strip())
    print()
    print(f"{'points':>7} {'reply':>7} {'result':>9} {'secs':>6}   note")

    for n in SIZES:
        inst.write(":WAV:STAR 1")
        inst.write(f":WAV:STOP {n}")
        t = time.time()
        try:
            inst.write(":WAV:DATA?")
            data = inst.read_raw()
            dt = time.time() - t
            # 11-byte IEEE header + payload + newline
            print(f"{n:7d} {len(data):7d} {'OK':>9} {dt:6.2f}   "
                  f"payload {max(len(data) - 12, 0)} bytes")
        except Exception as e:
            dt = time.time() - t
            print(f"{n:7d} {'-':>7} {'TIMEOUT':>9} {dt:6.2f}   {type(e).__name__}")
            # Clear the interrupted query so the next size starts clean.
            try:
                inst.query(":SYST:ERR?")
            except Exception:
                pass

    print()
    print("putting the bench back: 5 ns/div, NORMal, STOPped")
    inst.write(":WAV:MODE NORM")
    inst.write(":TIM:MAIN:SCAL 5e-09")
    print("timebase now:", inst.query(":TIM:MAIN:SCAL?").strip())
    inst.close()


if __name__ == "__main__":
    main()
