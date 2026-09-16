"""Direct DS1000Z probe over pyvisa-py; run with the LabLink server stopped.

The server container holds the USB interface, so this must run in its place:

    docker stop -t 10 lablink-server
    docker run --rm --privileged --device /dev/bus/usb:/dev/bus/usb \
      -v /opt/lablink/scripts/probe_ds1000z.py:/tmp/p.py:ro lablink-server:latest python /tmp/p.py
    docker start lablink-server

Prints each query with its reply and elapsed time, then tries three ways of
reading :WAV:DATA?. See docs/HANDOFF_SCOPE_LAG.md for what it found on 2026-09-16.
"""
import time, pyvisa
rm = pyvisa.ResourceManager('@py')
inst = rm.open_resource(__import__("os").environ.get("SCOPE_RESOURCE", "USB0::6833::1230::DS1ZA171409212::0::INSTR"))
inst.timeout = 5000
def q(cmd):
    t = time.time()
    try:
        r = inst.query(cmd).strip(); print(f"{cmd:28s} -> {r!r}  ({time.time()-t:.2f}s)")
        return r
    except Exception as e:
        print(f"{cmd:28s} -> FAIL {type(e).__name__}: {str(e)[:60]}  ({time.time()-t:.2f}s)")
q('*IDN?')
disp = {ch: q(f':CHAN{ch}:DISP?') for ch in (1, 2, 3, 4)}
q(':TRIG:STAT?'); q(':TIM:MAIN:SCAL?'); q(':ACQ:MDEP?'); q(':WAV:SOUR?'); q(':WAV:MODE?'); q(':WAV:FORM?')
q(':MEAS:ITEM? VAVG,CHAN1'); q(':MEAS:ITEM? VPP,CHAN1'); q(':MEAS:ITEM? FREQ,CHAN1')
q(':MEAS:VPP?'); q(':MEAS:VAV?')
src = next((ch for ch, d in disp.items() if d == '1'), 1)
print(f"--- waveform read from CH{src} (displayed channels: {[c for c,d in disp.items() if d=='1']})")
inst.write(f':WAV:SOUR CHAN{src}'); inst.write(':WAV:MODE NORM'); inst.write(':WAV:FORM BYTE')
q(':WAV:PRE?')
for label, fn in (
    ("query_binary_values B", lambda: bytes(inst.query_binary_values(':WAV:DATA?', datatype='B', container=bytes))),
    ("query_binary_values B (chunk 1M)", lambda: (setattr(inst, 'chunk_size', 1024*1024), bytes(inst.query_binary_values(':WAV:DATA?', datatype='B', container=bytes)))[1]),
    ("write + read_raw", lambda: (inst.write(':WAV:DATA?'), inst.read_raw())[1]),
):
    t = time.time()
    try:
        data = fn(); print(f"{label:34s} OK  {len(data)} bytes, head={data[:12]!r}  ({time.time()-t:.2f}s)")
    except Exception as e:
        print(f"{label:34s} FAIL {type(e).__name__}: {str(e)[:70]}  ({time.time()-t:.2f}s)")
        try: inst.clear(); print("   (device clear sent)")
        except Exception as e2: print("   clear failed:", e2)
q('*IDN?')
inst.close()
