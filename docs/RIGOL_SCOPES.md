# Rigol Oscilloscopes (modern SCPI tree)

Driver: `server/equipment/rigol_modern_scope.py` (`RigolModernScopeBase` + one thin
subclass per family). Tests: `tests/hardware/test_rigol_modern_scope.py`.
Every model below identifies itself as `RIGOL TECHNOLOGIES,<model>,<serial>,<firmware>`
and is matched against `MODEL_TABLE` after `*IDN?`, so channel counts and limits are
right even when the generic base class is used.

Sources are the programming guides in `~/Manuals/Rigol/_text_extracted/` and the
datasheets in `~/Manuals/Rigol/<family>/Datasheet/`. The legacy DS1000D/E, DS1000B/CA
and DS2000A trees are **not** covered here (see `rigol_scope.py`).

The **DS1000Z** family — DS1054Z, DS1074Z, DS1104Z and MSO1000Z — is also in
`rigol_scope.py`, driven by `RigolDS1104`. They share one command tree, so the
class named for the DS1104Z drives all of them; what differs is bandwidth, which
`ds1000z_specs()` reads out of the model name (Rigol encodes it there: `DS1`, the
bandwidth in tens of MHz, the channel count, `Z`). Do not confuse this family
with the two-channel **DS1000Z-E**, which is a different instrument on the modern
tree and is covered in the table below.

## Families and models

| Class | Family key | Models (analog ch / digital ch, bandwidth, max sample rate, max memory) | Guide |
|---|---|---|---|
| `RigolDHO800` | `DHO800` | DHO802 (2+EXT, 70 MHz), DHO804 (4, 70 MHz), DHO812 (2+EXT, 100 MHz), DHO814 (4, 100 MHz); 1.25 GSa/s, 25 Mpts. DHO914/914S (4+16, 125 MHz), DHO924/924S (4+16, 250 MHz); 1.25 GSa/s, 50 Mpts | DHO800/DHO900 Programming Guide |
| `RigolDHO1000` | `DHO1000` | DHO1072/1074 (2/4, 70 MHz), DHO1102/1104 (2/4, 100 MHz), DHO1202/1204 (2/4, 200 MHz); 2 GSa/s, 50 Mpts std / 100 Mpts opt. DHO4204 (200 MHz), DHO4404 (400 MHz), DHO4804 (800 MHz); 4 ch, 4 GSa/s, 250 Mpts std / 500 Mpts opt | DHO Programming Guide (DHO1000/DHO4000) |
| `RigolDHO5000` | `DHO5000` | DHO5054 (4), DHO5058 (8) 500 MHz; DHO5104 (4), DHO5108 (8) 1 GHz; MHO5054 (4+16), MHO5056 (6+16) 500 MHz; MHO5104 (4+16), MHO5106 (6+16) 1 GHz; 4 GSa/s, 500 Mpts | DHO/MHO5000 Series Programming Guide |
| `RigolMHO900` | `MHO900` | MHO934 (350 MHz), MHO954 (500 MHz), MHO984 (800 MHz): 4+16, 4 GSa/s, 100 Mpts std / 500 Mpts opt. MHO98 (1 GHz, 4+16, 4 GSa/s, 500 Mpts). MHO2024 (200 MHz), MHO2034 (350 MHz): 4+16, 2 GSa/s, 500 Mpts | MHO900, MHO98, MHO2000 Programming Guides |
| `RigolMSO5000` | `MSO5000` | MSO5072/5074 (2/4+16, 70 MHz), MSO5102/5104 (100 MHz), MSO5204 (4, 200 MHz), MSO5354 (4, 350 MHz); 8 GSa/s, 100 Mpts std / 200 Mpts opt. MSO5152-E (2+16, 150 MHz, 4 GSa/s, 100 Mpts opt) | MSO5000 / MSO5000-E Programming Guide |
| `RigolMSO7000` | `MSO7000` | MSO7014/7024/7034/7054 (4+16) and DS7014/7024/7034/7054 (4): 100/200/350/500 MHz, 10 GSa/s, 500 Mpts opt | MSO7000/DS7000 Programming Guide |
| `RigolMSO8000` | `MSO8000` | MSO8064 (600 MHz), MSO8104 (1 GHz), MSO8204 (2 GHz); MSO8074A (750 MHz), MSO8154A (1.5 GHz), MSO8204A (2 GHz), MSO8304A (3 GHz): 4+16, 10 GSa/s, 500 Mpts | MSO8000 / MSO8000A Programming Guides |
| `RigolDS8000R` | `DS8000R` | DS8034-R (350 MHz, 5 GSa/s), DS8104-R (1 GHz), DS8204-R (2 GHz) 10 GSa/s: 4 ch + EXT, 500 Mpts | DS8000-R Programming Guide |
| `RigolDS4000` | `DS4000` | DS4014E (100 MHz), DS4024E (200 MHz): 4 ch, 2 GSa/s, 14 Mpts. DS4012..DS4054 / MSO4012..MSO4054: 2/4 ch (+16 on MSO), 100-500 MHz, 4 GSa/s, 140 Mpts | DS4000E Programming Guide (non-E models assumed identical) |
| `RigolDS6000` | `DS6000` | DS6062 (2, 600 MHz), DS6064 (4, 600 MHz), DS6102 (2, 1 GHz), DS6104 (4, 1 GHz): 5 GSa/s, 140 Mpts | DS6000 Programming Manual (CHM) |
| `RigolDS70000` | `DS70000` | DS70304 (3 GHz), DS70504 (5 GHz): 4 ch + EXT, 20 GSa/s, 500 Mpts std / 2 Gpts opt | DS70000 Series Programming Guide |
| `RigolDS80000` | `DS80000` | DS80604 (6 GHz), DS80804 (8 GHz), DS81004 (10 GHz), DS81304 (13 GHz): 4 ch, 40 GSa/s, 500 Mpts std / 4 Gpts opt | DS80000 Series Programming Guide |
| `RigolDS1000ZE` | `DS1000ZE` | DS1102Z-E (100 MHz), DS1202Z-E (200 MHz): 2 ch, 1 GSa/s, 24 Mpts | DS1000Z-E Programming Guide |

Unknown members of a known family fall back to a family row (`^DHO8\d\d`, `^MSO5\d{3}`, ...);
completely unknown models use the subclass defaults and guess the channel count from the
last digit of the model number.

### Manager registration keywords (most specific first)

| Class | Keywords |
|---|---|
| `RigolDS1000ZE` | `DS1202Z-E`, `DS1102Z-E`, `Z-E` |
| `RigolDS80000` | `DS81304`, `DS81004`, `DS80804`, `DS80604`, `DS80` (5-digit) |
| `RigolDS70000` | `DS70504`, `DS70304`, `DS70` (5-digit) |
| `RigolDS8000R` | `DS8204-R`, `DS8104-R`, `DS8034-R`, `-R` with `DS8` |
| `RigolMSO8000` | `MSO8304A`, `MSO8204A`, `MSO8154A`, `MSO8074A`, `MSO8204`, `MSO8104`, `MSO8064`, `MSO8` |
| `RigolMSO7000` | `MSO7054`, `MSO7034`, `MSO7024`, `MSO7014`, `DS7054`, `DS7034`, `DS7024`, `DS7014`, `MSO7`, `DS70xx` (4-digit) |
| `RigolMSO5000` | `MSO5152-E`, `MSO5354`, `MSO5204`, `MSO5104`, `MSO5102`, `MSO5074`, `MSO5072`, `MSO5` |
| `RigolDHO5000` | `MHO5106`, `MHO5104`, `MHO5056`, `MHO5054`, `DHO5108`, `DHO5104`, `DHO5058`, `DHO5054`, `MHO5`, `DHO5` |
| `RigolMHO900` | `MHO984`, `MHO954`, `MHO934`, `MHO98`, `MHO2034`, `MHO2024`, `MHO9`, `MHO2` |
| `RigolDHO1000` | `DHO4804`, `DHO4404`, `DHO4204`, `DHO1204`, `DHO1202`, `DHO1104`, `DHO1102`, `DHO1074`, `DHO1072`, `DHO4`, `DHO1` |
| `RigolDHO800` | `DHO924S`, `DHO924`, `DHO914S`, `DHO914`, `DHO814`, `DHO812`, `DHO804`, `DHO802`, `DHO9`, `DHO8` |
| `RigolDS6000` | `DS6104`, `DS6102`, `DS6064`, `DS6062`, `DS6` |
| `RigolDS4000` | `DS4024E`, `DS4014E`, `MSO40xx`, `DS40xx` (4-digit) |

Order matters: `DS1202Z-E` must be tested before the legacy `DS1000Z` driver, `DS7054`
(4 digits) before `DS70504` (5 digits), `DS8104-R` before any plain `DS8`, and `MSO8204A`
before `MSO8204`.

## Command differences between families

| Topic | DHO800/900, DHO1000/4000, DHO/MHO5000, MHO900/98/2000, DS80000 | MSO5000(-E), MSO/DS7000, MSO8000(A), DS8000-R, DS70000 | DS1000Z-E | DS4000E, DS6000 |
|---|---|---|---|---|
| Front-panel AUTO | `:AUToset` (`:AUToscale` does **not** exist; `:SYSTem:AUToscale` only enables/disables the key) | `:AUToscale` | `:AUToscale` | `:AUToscale` |
| Measurements | `:MEASure:ITEM? <item>,<src>` (41 items incl. ACRMs; DS70000 adds THARea) | `:MEASure:ITEM? <item>,<src>` | `:MEASure:ITEM? <item>,<src>` (fewer items, `RDELay/FDELay/RPHase/FPHase` names) | per-item `:MEASure:VPP? [<chan>]`, `:MEASure:FREQuency? [<chan>]` ... (no `:MEASure:ITEM`) |
| Waveform modes | NORMal / MAXimum / RAW | same; MSO8000/A add `TRACe` (up to 1 Mpts of screen trace) | NORMal / MAXimum / RAW | NORMal / MAXimum / RAW |
| RAW read flow | `:WAV:STARt`/`:WAV:STOP` windows | `:WAV:STARt`/`:WAV:STOP` (MSO/DS7000 and DS8000-R also document `:WAV:POINts`) | `:WAV:STARt`/`:WAV:STOP`, max 250 000 BYTE / 125 000 WORD / 15 625 ASCii per read | `:WAV:POINts n`, `:WAV:RESet`, `:WAV:BEGin`, poll `:WAV:STATus?` (READ/IDLE) reading `:WAV:DATA?` each time, `:WAV:END` |
| NORMal points | 1000 | 1000 | 1200 | 1400 |
| `YINCrement` in NORMal mode (guide figure) | VerticalScale/7500 (see last note) | VerticalScale/25 | VerticalScale/25 | VerticalScale/32 (DS4000E) |
| Screenshot | `:DISPlay:DATA?[ BMP\|PNG\|JPG]` (default BMP) | `:DISPlay:DATA?` -> BMP (MSO5000/7000/DS8000-R) or PNG (MSO8000/A) | `:DISPlay:DATA? [<color>,<invert>,<format>]`, format BMP24/BMP8/PNG/JPEG/TIFF | `:DISPlay:DATA?` -> BMP, strip trailing `\n` |
| Digital channels | DHO900/MHO: `:LA:ENABle`, `:LA:DIGital:ENABle D<n>,ON`, `:LA:POD<n>:THReshold` | `:LA:STATe`, `:LA:DIGital:DISPlay D<n>,ON`, `:LA:POD<n>:THReshold` | none | MSO4000 only (not in the DS4000E guide) |
| Edge trigger sources | CHAN1-4(8), D0-D15 (MSO), EXT (DHO802/812, DHO1000+), ACLine (DHO1000+) | CHAN1-4, D0-D15, ACLine, EXT (7000/8000/DS8000-R) | CHAN1-2, `AC` | CHAN1-4, EXT, EXT5, ACLine |
| Acquisition types | NORMal, PEAK, AVERages, ULTRa | NORMal, AVERages, PEAK, HRESolution (7000: no HRESolution) | NORMal, AVERages, PEAK, HRESolution | NORMal, AVERages, PEAK, HRESolution |
| Memory depth argument | keywords (`1M`) or numbers; query returns scientific notation | keywords or numbers; MSO5000 query returns keyword (`1M`), MSO7000/DS8000-R return scientific | numbers only (12000...24000000), `AUTO` | numbers only (7000...140000000 by channel count), `AUTO` |
| Bandwidth limit | 20M (DHO800/1000); 20M/250M (DHO4000, 5000, MHO); 500M...12G (DS80000) | model dependent: 20M / 100M / 200M (MSO5000), 20M / 250M (7000, 8000), 20M/250M/500M (DS8000-R), 20M/250M/1G/2G (DS70000) | 20M | 20M/100M (DS4024E), 20M (DS4014E), 20M/250M (DS6000) |
| `:TRIGger:STATus?` | TD, WAIT, RUN, AUTO, STOP | same | same | DS6000 adds FIN |

The driver hides these behind `FamilySpec` (autoset command, measurement style, RAW flow,
chunk size, screenshot query, LA commands, acquisition types). SCPI is case-insensitive,
so the driver sends the short mnemonics (`:TRIG:EDGE:SOUR`, `:TIM:MAIN:SCAL`, `:WAV:PRE?`)
which are valid on every family (DS4000/DS6000 print `EDGe`, MSO/DS7000 print `AUTOscale`,
both are the same command).

## Waveform transfer notes

* **Setup** (all families): `:WAV:SOUR CHANn`, `:WAV:MODE NORMal|RAW`, `:WAV:FORM BYTE`,
  then `:WAV:PRE?` -> `format,type,points,count,xincrement,xorigin,xreference,yincrement,yorigin,yreference`.
* **Scaling** (all families): `V = (code - YORigin - YREFerence) * YINCrement`,
  `t = XORigin + (i - XREFerence) * XINCrement`. NORMal mode `XINCrement = TimeScale/100`
  (screen), RAW mode `XINCrement = 1/SampleRate`.
* **Block format**: `#9<9 digit length><bytes>\n`. The driver reads with `write` + `read_raw`,
  parses the header itself (`parse_tmc_block`) and keeps reading until the announced length
  arrived, so it works over USB-TMC and raw-socket LXI alike. Instrument timeout is raised
  to 30 s during transfers and restored afterwards.
* **BYTE vs WORD**: BYTE is one code per point. On the 8-bit families WORD carries the code in
  the low byte with the high byte 0; the 12-bit DHO/MHO families use the full 16-bit code.
  None of the guides states the WORD byte order; the driver assumes little-endian. ASCii is
  not used (15 625 points per read on DS1000Z-E, slow everywhere).
* **RAW (memory) reads** require the STOP state; the driver checks `:TRIG:STAT?` and issues
  `:STOP` when necessary and leaves the scope stopped (call `run` afterwards). Memory is read
  in windows of `FamilySpec.max_points_per_read` (BYTE):
  * DS1000Z-E: 250 000 per read (documented).
  * MSO5000/7000/DS8000-R: the guides only say "the settable STARt/STOP range depends on the
    memory depth and the return format"; 250 000 is used as a safe window.
  * DHO/MHO/DS70000/DS80000/MSO8000: no per-read limit is documented (the examples read
    120 000 points in one `:WAV:DATA?`); 1 000 000 per window is used.
  * DS4000E/DS6000: `:WAV:POINts` sets the buffer size (up to the memory depth, 64 000 000 on
    DS6000), then `:WAV:RESet`, `:WAV:BEGin`, and `:WAV:DATA?` is polled with `:WAV:STATus?`
    until it reports IDLE; each returned block has its own TMC header and consecutive blocks
    are contiguous. The driver finishes with `:WAV:END`.
* **Timing**: NORMal reads are 1000-1400 bytes and complete in milliseconds. A 250 kpt BYTE
  window takes roughly 0.3-0.5 s over USB-TMC on MSO5000-class hardware; a full 500 Mpts
  record is thousands of windows and takes many minutes, so pass `points=` to
  `get_waveform(..., mode="RAW", points=N)` to cap the transfer. The DHO800/900 guide warns
  the instrument must not be operated while a RAW read is in progress.
* **MATH sources** only support NORMal mode; the driver forces it.
* **Digital sources** (`D0`..`D15`) always return BYTE data: in NORMal mode one byte per point
  is the line state; in RAW mode one byte is the state of the whole 8-bit pod (not decoded
  by the driver).

## Integration hooks

* `get_waveform(channel, mode="NORMal", points=None, format="BYTE") -> WaveformData` (same
  shape as `rigol_scope.RigolDS1104`); the scaled samples of the last capture are in
  `driver.last_waveform["time"|"voltage"]`. `get_waveform_raw(channel)` returns the raw BYTE
  codes (what `server/waveform/manager.py` expects). `get_waveform_data(...)` returns a
  JSON-friendly dict with `time`/`voltage` lists.
* `get_measurements(channel)` -> `vpp, vmax, vmin, vavg, vrms, freq, period, rise_time,
  fall_time, positive_width, negative_width, duty_cycle` (NaN when the scope reports 9.9E37).
* `get_measurement(channel)` for the acquisition engine: `CH1`, `1`, `CHAN1`, `CH1:VPP`,
  `2:FREQ`, `CHAN3:RISE`, `MATH1:VRMS`, `D3:FREQ`. A bare channel means **VAVG** (mean of the
  record, the nearest thing to a DC voltmeter reading and what a slow logger usually wants);
  request `CH1:VRMS` explicitly for AC. Returns `{"value", "unit", "item", "source", "valid"}`.
* `set_channel`, `set_timebase`, `set_trigger`, `set_acquisition` write only the parameters
  given and return the read-back state; `get_state()` snapshots channels, timebase, trigger,
  acquisition (and LA state on MSO models).
* `autoscale()` sends the family's `:AUToset` or `:AUToscale` and returns the command used.

## Commands not confirmed / contradictions between the guides

* **MHO900 vs MHO2000/MHO98**: the MHO900 programming guide lists only CHANnel1-4 and MATH as
  `:WAVeform:SOURce` values although the MHO900 datasheet ships 16 digital channels
  (PLA2216) and the guide contains the `:LA:` subsystem; the MHO2000 guide lists D0-D15.
  The driver treats MHO900 as 4+16 and allows D-sources.
* **MSO8000A top model**: the MSO8000A programming guide (and the MSO8000 datasheet overview)
  name MSO8304A (3 GHz); the MSO8000A datasheet's model table stops at MSO8204A (2 GHz).
  Both are in the table.
* **DS70000 vs DS80000 AUTO**: both share the DHO-style tree, but DS70000 documents
  `:AUToscale` while DS80000 documents `:AUToset` (with the `:AUToset:PEAK/OPENch/...`
  sub-commands). Hence separate `RigolDS70000` / `RigolDS80000` families.
* **DS80000 channel count**: the datasheet overview says "2/4" channels, the model table says
  4 for every model; the programming guide lists CHANnel1-4. The driver uses 4.
* **MSO5000 `:DISPlay:DATA?`**: the MSO5000/MSO7000/DS8000-R guides document the bare query
  (BMP) whereas DS1000Z documents `[<color>,<invert>,<format>]`. The driver sends the bare
  query on those families; PNG output there is unconfirmed.
* **Per-read RAW limits** for MSO5000/7000/8000/DS8000-R/DHO/MHO are not stated (see above);
  the chunk sizes are conservative defaults, not documented maxima.
* **WORD byte order** is not stated in any guide (little-endian assumed).
* **MHO98 model string**: the MHO98 datasheet and user guide list the single order code
  "MHO98"; the exact `*IDN?` model field is unconfirmed, the table matches `^MHO98`.
* **DS/MSO4000 (non-E)** and **MSO4000 LA commands** are not covered by the guide on disk
  (DS4000E only); they are mapped to the DS4000E behaviour.
* **`:ACQuire:MDEPth?` return format** differs: MSO5000 returns the keyword (`1M`), MSO7000,
  DS8000-R and the DHO families return scientific notation, DS1000Z-E/DS4000E return the
  integer or `AUTO`. `get_acquisition()` parses all three.
* DHO NORMal-mode `YINCrement` is given as `Verticalscale/7500` in the DHO800 guide figure
  while the worked example preamble shows `4E-3` for a 1 V/div trace with YREFerence 128
  (i.e. 8-bit style codes). The driver does not rely on either; it uses the preamble values.
