# Siglent

Siglent sells two protocols under one badge, and which one an
instrument speaks decides whether any driver can talk to it at all.
That is the first thing to know about this vendor and the reason
`server/equipment/siglent_registry.py` exists.

| Line | Instruments | Protocol |
|------|-------------|----------|
| SPD, SPS, SPE | Power supplies | Conventional SCPI |
| SDL | Electronic loads | Conventional SCPI |
| SDM | Multimeters | Conventional SCPI |
| SSA, SVA, SNA, SSG | Analysers, RF sources | Conventional SCPI |
| SDS, SHS | Oscilloscopes | Siglent short/long pairs |
| SDG | Generators | Siglent short/long pairs |

**Conventional SCPI** means the uppercase run in the published
spelling is the legal abbreviation, as IEEE 488.2 intends.

**Siglent short/long pairs** are published per command in an explicit
table and are not derivable from capitalisation: `BSWV` is the short
form of `BASIC_WAVE`, and a command reads `C1:BSWV WVTP,SINE`. Nothing
about the spelling tells you that. Assuming either dialect against the
other family fails, so the registry records which a family speaks and
discovery reports it.

## What LabLink drives

Only the SPD supplies, today. Everything else in the catalogue is
identified — named, categorised, and reported with the reason there is
no driver — but cannot be connected.

| Family | SKUs | Driver | Bench-verified |
|--------|------|--------|----------------|
| SPD3000X | SPD3303X, SPD3303X-E, SPD3303C | `SiglentSPD3303X` | SPD3303X-E |
| SPD1000X | SPD1168X, SPD1305X | `SiglentSPD1000X` | no |

`GET /api/equipment/models?manufacturer=Siglent` lists the whole
catalogue with `supported` and `verified` per family. `verified` means
a driver here has been run against the real command set rather than
written from the manual alone.

## Identification

Three things make a Siglent awkward to place, and the registry handles
each.

**The USB vendor id is not Siglent's.** `0xF4EC` is still registered to
Atten Electronics, so `lsusb` and some VISA layers report a Siglent as
*Atten*. `is_siglent_manufacturer` accepts both.

**The descriptors are NUL-padded**, and the padding survives into the
resource string:

```
USB0::62700::5168::SPD3XJGCA01014\x00\x00\x00\x00::0::INSTR
```

A serial carrying four NULs does not compare equal to the same serial
without them, which makes one instrument look like a different
instrument on every scan. `resolve_idn` strips them. The resource
string is left alone — padding and all — because that is what opens
the device; only the display is cleaned.

**The catalogue is larger than the driver collection and it grows.**
A model no entry names is placed by Siglent's own prefix scheme — SPD
is a supply, SDL a load, SDM a meter — so an instrument from a family
this registry has never heard of is still reported as the right *kind*
of instrument, with the right dialect, and never as drivable. Knowing
what kind of instrument it is says nothing about whether its command
set matches the one implemented.

## The SPD supplies

Command set from the **SPD3000X Quick Start (E02A)**. There is no
separate SPD programming guide — Siglent publishes the command list in
the quick start, which is easy to miss.

### The abbreviation that bites

The SPD line is conventional SCPI and Siglent spells it
`MEASure:POWEr`, so the legal short form is `MEAS:POWE?` — four
letters. `MEAS:POW?`, which every other supply in this tree uses and
which anyone would write from memory, is an undefined header. On the
bench:

```
MEASure:POWEr? CH1  -> '0.00'
MEASure:POWE?  CH1  -> '0.00'
MEAS:POW?      CH1  -> no reply at all, then
SYSTem:ERRor?       -> '-113,Undefined header,MEAS:POW?'
```

Note the failure: the supply does not answer and does not fault the
link. It simply never replies, so the caller waits out a full timeout
and the connection needs clearing before the next query works. **A
wrong keyword costs a stall, not an error.** Every keyword in the
driver is spelled out in full, and a test fails if `:POW?` is ever
sent.

`*CLS` is not sent either. It is not in the published command list,
and the documented penalty for an undefined header here is a stalled
link, so the error queue is drained by reading instead.

### The channel is part of the command

Three shapes for the same idea, and the third takes a comma:

```
CH1:VOLTage 5              set
MEASure:VOLTage? CH1       measure
OUTPut CH1,ON              switch
```

### CH3 is not a normal channel

On the SPD3303X it is a fixed 2.5 / 3.3 / 5 V rail selected by a switch
on the front panel. Remote control can switch it on and off and nothing
else: it answers none of the measurement queries, and it does not
refuse them — it never replies, so each attempt costs a full read
timeout. It has no bit in the status word either, so **its state cannot
be read back at all**. The panel shows what it was last told and says
so.

The instrument's own front panel does display CH3's voltage and
current. That is not reachable over SCPI.

### Series and parallel

`OUTPut:TRACK {0|1|2}` — independent, series, parallel.

| Mode | Rating | Load wiring |
|------|--------|-------------|
| Independent | 0-32 V / 0-3.2 A each | each channel's own terminals |
| Series | 0-60 V / 0-3.2 A | CH2 positive to CH1 negative |
| Parallel | 0-32 V / 0-6.4 A | CH1's terminals |

In series and parallel, CH1 and CH2 are linked internally into one
channel **controlled by CH1**, and in parallel CH2 only works in CC
mode. Because the mode decides how the operator's circuit should be
wired, changing it under a live output changes what their circuit is
connected to — the driver switches both outputs off first.

**The status word does not document series.** Bits 2 and 3 are one
field and the guide gives two of its four values: "01: Independent
mode; 10: Parallel mode". Asked on the bench:

```
OUTPut:TRACK 0 -> SYSTem:STATus? 0x4  bits 01  independent
OUTPut:TRACK 1 -> SYSTem:STATus? 0xc  bits 11  series
OUTPut:TRACK 2 -> SYSTem:STATus? 0x8  bits 10  parallel
```

`11` is series. `00` is still unknown and is reported as unknown.

### The timer

Five timing groups per channel, each a voltage, a current and how long
to hold them, run one after another. Longest per group is 10000 s.

```
TIMEr:SET CH1,2,3.000,0.500,2      group 2: 3 V, 0.5 A, 2 s
TIMEr:SET? CH1,2                   -> 3,0.5,2
TIMEr CH1,ON                       start
```

Two conditions the instrument does not enforce:

- **It only runs in independent mode.** "The timer function is invalid
  when the series mode or parallel mode is turn on." The instrument
  accepts the command and does nothing, so the driver refuses it.
- **Switching the output off pauses the countdown** rather than ending
  it, and it resumes when the output comes back on. The timer switches
  itself off when the time reaches zero.

**The time is whole seconds, and the guide does not say so.** It gives
only the maximum -- "the longest time of each group is 10000s" -- with
no minimum and no resolution. The instrument keeps an integer and
truncates:

```
asked  stored
0.9    0
1.0    1
1.6    1
2.5    2
9999   9999
10000  10000
```

So a second is the resolution and **one second is the shortest
interval a group can actually hold for**. A group set below that holds
for no time, which is a legal way to skip one but not a short one.

This is the SPD's limit, not a property of timers. It lives on the
driver class as `timer_seconds_decimals` / `min_timer_seconds` and is
reported through `get_status` capabilities, so the editor ranges
itself from the instrument. B&K's timing profiles are finer, and an
editor that hard-coded this family's resolution would refuse to offer
what those support.

**`TIMEr:SET` faults every time and obeys every time.** Every form of
the command queues `-103,Invalid separator`, including the one the
guide prints as its own example, and every form takes effect:

```
TIMEr:SET CH1,1,1.000,0.100,3  -> -103, stored 1.00,0.10,3
TIMEr:SET CH1,1,2,0.2,4        -> -103, stored 2.00,0.20,4
TIMER:SET CH1,1,3,0.3,6        -> -103, stored 3.00,0.30,6
TIMEr:SET CH1,1, 4, 0.4, 8     -> -103, stored 4.00,0.40,8
```

The error queue therefore cannot say whether a timing group was
accepted. A driver that believes it reports every group as refused
while every group lands. `set_timer_step` writes without the error
check and reads the group back instead, which is a better test than
the queue would have been.

`TIMEr:SET?` replies with a trailing comma -- `0.00,0.00,5,` -- and
with the voltage and current to two decimals and the time as a bare
integer, which is the format hinting at the truncation above.

There is **no remaining-time query** — the subsystem is `TIMEr:SET`,
`TIMEr:SET?` and `TIMEr`, and none of them reports progress. Bits 6 and
7 of the status word say whether a channel's timer is running, and that
is all the instrument will say. The panel's elapsed figure is counted
client-side and shown as an estimate.

### The status word

`SYSTem:STATus?` answers in hex and has to be read as bits.

| Bit | Meaning |
|-----|---------|
| 0 | CH1 CC (0 = CV) |
| 1 | CH2 CC (0 = CV) |
| 2-3 | coupling: 01 independent, 10 parallel, 11 series |
| 4 | CH1 output on |
| 5 | CH2 output on |
| 6 | CH1 timer running |
| 7 | CH2 timer running |
| 8 | CH1 showing the waveform screen |
| 9 | CH2 showing the waveform screen |

### The error queue answers in three shapes

```
'0,"No error"'
'+0, No error'
'-113,Undefined header,MEAS:POW?'
```

All three are parsed. The replies from this instrument are not uniform.

## Adding a Siglent driver

Follow [DRIVER_AUTHORING.md](DRIVER_AUTHORING.md), and additionally:

1. Add the family to `MODELS` in `siglent_registry.py`, with its
   protocol. Set `verified=True` only after running the driver against
   the real instrument.
2. Add the family key to `DRIVEN_FAMILIES`.
3. Map the model to the driver class in `spd_driver_for`, or add an
   equivalent for a new category.
4. `manager._create_siglent_instance` dispatches from there; nothing
   else in the manager needs changing.
5. Export the class from `server/equipment/__init__.py` and name the
   SKUs in `shared/constants/SUPPORTED_MANUFACTURERS`.

For a scope or generator, the protocol is the short/long pair dialect
and none of the SCPI helpers in this tree apply. Read the guide's
command table rather than assuming an abbreviation.

## Manuals

`tools/fetch_siglent_manuals.py` downloads what is public. The SPD
command set is in the quick start rather than a programming guide.
Manuals live outside the repository — see the paths in that tool.
