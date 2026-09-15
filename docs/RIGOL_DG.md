# Rigol DG Function / Arbitrary Waveform Generators

Driver: `server/equipment/rigol_function_generator.py`
Mock: `server/equipment/mock/mock_function_generator.py` (`MockFunctionGenerator`, `MOCK::FGEN::n`, model `MockFGEN-1062Z`)
Tests: `tests/hardware/test_rigol_function_generator.py`, `tests/test_mock_function_generator.py`
Equipment type: `EquipmentType.FUNCTION_GENERATOR`, id prefix `fgen_`, readings model `FunctionGeneratorData`.

Sources: RIGOL programming guides for DG1000Z, DG800, DG900, DG2000, DG4000 (CHM), DG5000 (CHM),
DG800 Pro/DG900 Pro, DG5000 Pro and DG6000 (`~/Manuals/Rigol/_text_extracted/`), plus the series
datasheets (`~/Manuals/Rigol/DG*/Datasheet/`).

## Classes

| Class | Models | Tree | Notes |
|-------|--------|------|-------|
| `RigolDG1000Z` | DG1022Z, DG1032Z, DG1062Z | classic | float `:TRACe:DATA VOLATILE` upload, sample-rate arb mode |
| `RigolDG800` | DG811, DG812, DG821, DG822, DG831, DG832 | classic | odd models single channel; DAC16 binary upload only |
| `RigolDG900` | DG952, DG972, DG992 | classic | DAC16 binary upload only |
| `RigolDG2000` | DG2052, DG2072, DG2102 | classic | DG900 + LAN; DAC16 upload |
| `RigolDG4000` | DG4062, DG4102, DG4162, DG4202 | classic (old) | `:MOD` node mandatory, `:PHASe:INITiate`, no channel node on `:TRACe:DATA`, pulse apply has `<delay>` not `<phase>` |
| `RigolDG5000` | DG5071/5072, DG5101/5102, DG5251/5252, DG5351/5352 | classic (old) | as DG4000; no counter; odd models single channel |
| `RigolDG800Pro` | DG821 Pro, DG822 Pro, DG852 Pro, DG902 Pro, DG912 Pro, DG922 Pro | Pro | one guide covers both series |
| `RigolDG5000Pro` | DG5252/5254/5258 Pro, DG5352/5354/5358 Pro, DG5502/5504/5508 Pro | Pro | 2/4/8 channels, no counter |
| `RigolDG6000` | DG6052, DG6054, DG6102, DG6104 | Pro | 2/4 channels, no counter |

Not implemented:
- **DG70000** - a sequencer-centric AWG (`:SOURce<n>:TRACe`/`:FUNCtion:SEQuence` only, no `:APPLy`,
  amplitude/offset defined per waveform segment). It needs its own driver class, not a subclass here.
- **Legacy DG1000 (DG1022/DG1022A)** - non-SCPI style command set (`FUNC SIN`, `FREQ 1000`, `OUTP ON`
  without the `:SOURce<n>` tree, single `*IDN?`-less responses). Different enough that sharing this driver
  would only add `if model` branches.

## Model table

Frequency limits are the continuous-mode upper limit per waveform (lower limit 1 uHz everywhere).
Amplitude limits are into 50 Ohm; HighZ doubles them. "Arb" is the volatile waveform memory.

| Model | Ch | Sine | Square | Ramp | Pulse | Arb | Harmonic | Vpp max (50 Ohm) | Sample rate | Arb points | Counter |
|-------|----|------|--------|------|-------|-----|----------|------------------|-------------|------------|---------|
| DG811/812 | 1/2 | 10 MHz | 5 MHz | 200 kHz | 5 MHz | 5 MHz | 5 MHz | 10 V (<=10 MHz), 5 V (<=30 MHz), 2.5 V | 125 MSa/s | 2 M (8 M opt) | yes |
| DG821/822 | 1/2 | 25 MHz | 10 MHz | 500 kHz | 10 MHz | 10 MHz | 10 MHz | same | 125 MSa/s | 2 M | yes |
| DG831/832 | 1/2 | 35 MHz | 10 MHz | 1 MHz | 10 MHz | 10 MHz | 15 MHz | same | 125 MSa/s | 2 M | yes |
| DG952 / DG2052 | 2 | 50 MHz | 15 MHz | 1.5 MHz | 15 MHz | 15 MHz | 20 MHz | 10 / 5 / 2.5 / 1 V at 10 / 30 / 60 / 100 MHz | 250 MSa/s | 16 M | yes |
| DG972 / DG2072 | 2 | 70 MHz | 20 MHz | 1.5 MHz | 20 MHz | 20 MHz | 20 MHz | same | 250 MSa/s | 16 M | yes |
| DG992 / DG2102 | 2 | 100 MHz | 25 MHz | 2 MHz | 25 MHz | 20 MHz | 25 MHz | same | 250 MSa/s | 16 M | yes |
| DG1022Z | 2 | 25 MHz | 25 MHz | 500 kHz | 15 MHz | 10 MHz | 10 MHz | 10 / 5 / 2.5 V at 10 / 30 / 60 MHz | 200 MSa/s | 2 M (16 M opt) | yes |
| DG1032Z | 2 | 30 MHz | 25 MHz | 500 kHz | 15 MHz | 10 MHz | 10 MHz | same | 200 MSa/s | 8 M | yes |
| DG1062Z | 2 | 60 MHz | 25 MHz | 1 MHz | 25 MHz | 20 MHz | 20 MHz | same | 200 MSa/s | 8 M | yes |
| DG4062 | 2 | 60 MHz | 25 MHz | 1 MHz | 15 MHz | 15 MHz | 30 MHz | 10 / 5 / 2.5 / 1 V at 20 / 70 / 120 / 200 MHz | 500 MSa/s | 16 k | yes |
| DG4102 | 2 | 100 MHz | 40 MHz | 3 MHz | 25 MHz | 25 MHz | 50 MHz | same | 500 MSa/s | 16 k | yes |
| DG4162 | 2 | 160 MHz | 50 MHz | 4 MHz | 40 MHz | 40 MHz | 80 MHz | same | 500 MSa/s | 16 k | yes |
| DG4202 | 2 | 200 MHz | 60 MHz | 5 MHz | 50 MHz | 50 MHz | 100 MHz | same | 500 MSa/s | 16 k | yes |
| DG5071/5072 | 1/2 | 70 MHz | 70 MHz | 3 MHz | 50 MHz | 50 MHz | 70 MHz | 10 V (5 mVpp min) | 1 GSa/s | 512 k | no |
| DG5101/5102 | 1/2 | 100 MHz | 100 MHz* | 3 MHz* | 50 MHz | 50 MHz | 100 MHz | 10 V | 1 GSa/s | 512 k | no |
| DG5251/5252 | 1/2 | 250 MHz | 120 MHz* | 5 MHz* | 50 MHz | 50 MHz | 250 MHz | 10 V | 1 GSa/s | 512 k | no |
| DG5351/5352 | 1/2 | 350 MHz | 120 MHz | 5 MHz | 50 MHz | 50 MHz | 250 MHz | 10 V | 1 GSa/s | 512 k | no |
| DG821/822 Pro | 1/2 | 25 MHz | 20 MHz | 1 MHz | 10 MHz | 10 MHz | 10 MHz | 10 / 5 / 2 V at 50 / 100 / 200 MHz | 625 MSa/s | 2 M (8 M opt) | yes |
| DG852 Pro | 2 | 50 MHz | 40 MHz | 1 MHz | 25 MHz | 15 MHz | 25 MHz | same | 625 MSa/s | 2 M | yes |
| DG902 Pro | 2 | 70 MHz | 60 MHz | 3 MHz | 50 MHz | 30 MHz | 35 MHz | same | 1.25 GSa/s | 16 M (32 M opt) | yes |
| DG912 Pro | 2 | 150 MHz | 60 MHz | 5 MHz | 50 MHz | 50 MHz | 75 MHz | same | 1.25 GSa/s | 16 M | yes |
| DG922 Pro | 2 | 200 MHz | 60 MHz | 5 MHz | 50 MHz | 50 MHz | 100 MHz | same | 1.25 GSa/s | 16 M | yes |
| DG5252/5254/5258 Pro | 2/4/8 | 250 MHz | 170 MHz** | 5 MHz | 120 MHz | 100 MHz | 125 MHz | 10 / 5 / 2 / 1 V at 100 / 250 / 350 / 500 MHz | 2.5 GSa/s | 64 M (128 M opt) | no |
| DG5352/5354/5358 Pro | 2/4/8 | 350 MHz | 170 MHz** | 5 MHz | 120 MHz | 100 MHz | 175 MHz | same | 2.5 GSa/s | 64 M | no |
| DG5502/5504/5508 Pro | 2/4/8 | 500 MHz | 170 MHz** | 5 MHz | 120 MHz | 100 MHz | 250 MHz | same | 2.5 GSa/s | 64 M | no |
| DG6052/6054 | 2/4 | 500 MHz (HBW) | 300 MHz (HBW) | 5 MHz | 120 MHz | 100 MHz | 175 MHz | same; HighZ 20 / 10 / 4 / 2 V | 2.5 GSa/s | 256 M (512 M opt) | no |
| DG6102/6104 | 2/4 | 1 GHz (HBW) | 300 MHz (HBW) | 5 MHz | 120 MHz | 100 MHz | 250 MHz | same | 2.5 GSa/s | 256 M | no |

`*` interpolated - the DG5000 datasheet PDF only contains the 70 MHz column as text and the CHM guide
only gives DG5352 examples. `**` with fast transition enabled; 120 MHz otherwise and in modulation/burst.
Sine limits for DG6000 are for the HBW output type (SND/AMP: 350 / 500 MHz).

Validation: `set_frequency`/`apply` check against the waveform column; `set_amplitude`/`apply` check Vpp
against the tier that matches the set frequency and the cached load (`INF` -> HighZ table). Vrms/dBm
values are not range checked. Offsets are limited to half the maximum Vpp for the load.

## Command table

`<n>` is the channel. All classic-tree commands are sent with the optional nodes spelled out where the
guides mark them optional (`:VOLTage` rather than `:VOLTage:LEVel:IMMediate:AMPLitude`, etc.) so the same
string is valid on both platforms.

| LabLink command | Classic tree (DG800/900/1000Z/2000, DG4000/5000) | Pro tree (DG800/900 Pro, DG5000 Pro, DG6000) |
|-----------------|--------------------------------------------------|----------------------------------------------|
| `apply(channel, waveform, frequency, amplitude, offset, phase)` | `:SOURce<n>:APPLy:{SINusoid\|SQUare\|RAMP\|PULSe\|USER\|HARMonic} f,a,o,p`; `:APPLy:NOISe a,o`; `:APPLy:DC 1,1,o` | `:APPLy:ARBitrary` instead of USER; `:APPLy:NOISe DEF,a,o`; `:APPLy:DC DEF,DEF,o` |
| `get_readings(channel)` | `:SOURce<n>:APPLy?` -> `"SQU,1.000000E+03,2.000000E+00,3.000000E+00,4.000000E+00"` + `:OUTPut<n>?`, `:OUTPut<n>:LOAD?`, `:VOLTage:UNIT?`, modulation/sweep/burst state, duty or symmetry | same; ON/OFF answers are 0/1; `:APPLy?` names are PULS/NOIS/ARB/HARM/SEQ |
| `set_waveform` / `get_waveform` | `:SOURce<n>:FUNCtion {SINusoid\|SQUare\|RAMP\|PULSe\|NOISe\|DC\|USER\|HARMonic}` | `... ARB` instead of USER (DC is not a `:FUNCtion` value) |
| `set_frequency` / `get_frequency` | `:SOURce<n>:FREQuency <Hz>` | same |
| `set_amplitude(amplitude, unit)` | `:SOURce<n>:VOLTage <v>` (unit via `:VOLTage:UNIT {VPP\|VRMS\|DBM}`) | same |
| `set_offset` | `:SOURce<n>:VOLTage:OFFSet <V>` | same |
| `set_phase` | `:SOURce<n>:PHASe <deg>` (0..360 on classic, -360..360 on Pro; driver accepts -360..360) | same |
| `set_duty_cycle` | `:SOURce<n>:FUNCtion:SQUare:DCYCle <%>` (square) / `:SOURce<n>:PULSe:DCYCle <%>` (pulse) | pulse: `:SOURce<n>:FUNCtion:PULSe:DCYCle` |
| `set_symmetry` | `:SOURce<n>:FUNCtion:RAMP:SYMMetry <%>` | same |
| `set_pulse(width, duty_cycle, rise_time, fall_time)` | `:SOURce<n>:PULSe:{WIDTh\|DCYCle\|TRANsition:LEADing\|TRANsition:TRAiling}` | `:SOURce<n>:FUNCtion:PULSe:{...}` |
| `set_output(enabled, channel)` | `:OUTPut<n> ON\|OFF`, query returns ON/OFF | query returns 1/0 |
| `set_load(impedance)` | `:OUTPut<n>:LOAD {1..10000\|INFinity}`; query 9.9E+37 (DG1000Z tree) or `INFINITY` (DG4000/5000) for HighZ | query 9.9E+37 for HighZ |
| `set_polarity` | `:OUTPut<n>:POLarity {NORMal\|INVerted}` | same |
| `set_modulation(enabled, modulation_type, depth, deviation, frequency, source, shape)` | `:SOURce<n>:MOD:TYPe {AM\|FM\|PM\|ASK\|FSK\|PSK\|PWM}`, `:MOD:AM:DEPTh`, `:MOD:FM:DEViation`, `:MOD:PM:DEViation`, `:MOD:PWM:DEViation:DCYCle`, `:MOD:<T>:INTernal:FREQuency` (`:INTernal:RATE` for ASK/FSK/PSK), `:MOD:<T>:SOURce`, `:MOD:<T>:INTernal:FUNCtion`, `:MOD:STATe ON\|OFF` | no `:MOD` node and no `:MOD:TYPe`: `:SOURce<n>:AM:DEPTh`, `:FM:DEViation`, ..., enable with `:SOURce<n>:<AM\|FM\|PM\|ASKey\|FSKey\|PSKey\|PWM>:STATe ON`; `get_modulation` polls every `:<T>:STATe?` |
| `set_sweep(enabled, start, stop, time, spacing)` | `:SOURce<n>:FREQuency:STARt/STOP`, `:SWEep:TIME <s>`, `:SWEep:SPACing {LINear\|LOGarithmic\|STEp}`, `:SWEep:STATe` | same |
| `set_burst(enabled, mode, cycles, period, phase)` | `:SOURce<n>:BURSt:MODE {TRIGgered\|INFinity\|GATed}`, `:BURSt:NCYCles`, `:BURSt:INTernal:PERiod`, `:BURSt:PHASe`, `:BURSt:STATe` | `:BURSt:MODE {TRIGgered\|GATed}` only; INFinity is mapped to `TRIGgered` + `:BURSt:NCYCles INFinity` |
| `trigger_burst` | `:SOURce<n>:BURSt:TRIGger` | `:TRIGger<n>:IMMediate` |
| `upload_arbitrary(points, channel)` | see below | see below |
| `set_arb_sample_rate(rate)` | DG1000Z only: `:SOURce<n>:FUNCtion:ARBitrary:MODE SRATe`, `:FUNCtion:ARBitrary:SRATe <Sa/s>` | raises (Pro sets rates per sequence / advanced arb) |
| `sync_phase(channel)` | `:SOURce<n>:PHASe:SYNChronize` (DG800/900/1000Z/2000; `:PHASe:INITiate` is the alias) / `:SOURce<n>:PHASe:INITiate` (DG4000/5000) | `:SOURce<n>:PHASe:SYNChronize` |
| `set_counter(enabled)` / `get_counter()` | `:COUNter:STATe ON\|OFF` (query returns RUN/STOP/SINGLE/OFF), `:COUNter:MEASure?` -> `freq,period,duty,+width,-width` (all zeros when off -> NaN) | `:COUNter:STATe` answers 0/1; same `:MEASure?` format. DG5000, DG5000 Pro, DG6000 have no counter |
| `get_measurement(channel)` | `COUNTER[:FREQ\|PERIOD\|DUTY\|PWIDTH\|NWIDTH]`, `CH<n>[:FREQ]`, `CH<n>:AMPL`, `CH<n>:OFFS`, `CH<n>:PHASE`, `CH<n>:OUTPUT` | same |
| `set_beeper` / `beep` | `:SYSTem:BEEPer:STATe ON\|OFF`, `:SYSTem:BEEPer` | same |
| `get_error` | `:SYSTem:ERRor?` -> `-113,"Undefined header; keyword cannot be found"` | same |
| `reset` / `self_test` / `clear_errors` | `*RST`, `*TST?`, `*CLS` | same |

## Pro platform differences (summary)

- Modulation is enabled per type (`:SOURce<n>:AM:STATe`); there is no `:MOD:STATe` / `:MOD:TYPe`. Only one
  modulation is active at a time; the driver reads the active type by polling each `:STATe?`.
- Pulse parameters moved under `:FUNCtion:PULSe`. Duty cycle range 0.01..99.99 %.
- `:FUNCtion` accepts `ARB` (built-in arbs selected with `:FUNCtion:ARBitrary <name>`); classic uses `USER`.
- Burst modes are TRIGgered/GATed; infinite bursts use `:BURSt:NCYCles INFinity`. Manual trigger is
  `:TRIGger<n>[:IMMediate]`; trigger source/slope/delay live under `:TRIGger<n>` too.
- Boolean queries return 0/1 instead of ON/OFF; numeric replies have 16 digits; phase range -360..360.
- `*IDN?` manufacturer is upper case (`RIGOL TECHNOLOGIES`); model strings contain a space (`DG822 Pro`),
  the driver normalises them (`DG822PRO`) for the model table.
- DG5000 Pro / DG6000 have 2/4/8 channels, `:SOURce<n>` accepts up to 8, and no counter subsystem.
- The Pro `:APPLy:NOISe` and `:APPLy:DC` take four parameters with `DEF` placeholders.
- Sweep time goes to 250 000 s (500 s on the classic tree); burst count 1..1 000 000 in every trigger mode.

## Arbitrary waveform upload formats

All formats take normalised floats in -1..1 (1 = +amplitude/2 + offset). Values outside the range are
clipped, NaN/inf are rejected. The driver constant `ARB_UPLOAD_FORMAT` selects the encoding.

| Format | Families | Command | Limits |
|--------|----------|---------|--------|
| `FLOAT` | DG1000Z | `:SOURce<n>:TRACe:DATA VOLATILE,<f>,<f>,...` (`[:TRACe]` and `[:DATA]` optional) | 8..16384 points per command; the channel switches to the volatile arb automatically. Also documented: `:DATA:DAC VOLATILE,<0..16383>,...` (decimal DAC codes) and `:DATA:DAC16 VOLATILE,<CON\|END>,#<block>` |
| `DAC16` | DG800, DG900, DG2000 | `:SOURce<n>:TRACe:DATA:DAC16 VOLATILE,<CON\|END>,#<d><len><binary>` - the only arb download command in these guides | 2 bytes per point, codes 0x0000..0x3FFF (14 bit), 8..16384 points (16 B..32 kB) per packet, `CON` for all but the last packet; the driver pads short uploads by repeating the last sample. Byte order is not stated in the guides; the driver uses little-endian (`DAC16_BYTE_ORDER`) |
| `FLOAT_CH0` | DG4000, DG5000 | `:TRACe:DATA VOLATILE,<f>,...` (no channel node) | 1..16384 points, targets the channel currently selected on the front panel; DG4000 memory is 16 kpts, DG5000 512 kpts editable. Also documented: `:DATA:DAC`, `:DATA:DAC16` (16 kpts binary), `:DATA:POINts`, `:DATA:VALue` |
| `PRO` | DG800/900 Pro, DG5000 Pro, DG6000 | `:SOURce<n>:TRACe:DATA:DAC16 VOLTage,<HEADer\|CONTinue\|END>,<f>,<f>,...` | Guide recommends <=20 kB per packet; the driver sends 2048 floats per packet, `END` alone for a single packet, `HEADer`/`CONTinue`/`END` otherwise. `CODE` (-32768..32767 integers) and `BIN` (2 bytes/point IEEE block) types also exist. Persistent files: `:MMEMory:TRACe:ARB:DATA <name.arb>,<flag>,<floats>` then `:MMEMory:LOAD:DATA <n>,<file>` |

After a DG1000Z / DG800-tree upload the instrument switches the channel to the volatile waveform; on the
Pro platform call `set_waveform("ARB")` or `apply(waveform="ARB", ...)` if the channel is not already in
Arb mode.

## Unverified / contradictions

- DAC16 byte order (all classic guides omit it).
- DG1000Z minimum amplitude: datasheet 1.0 mVpp vs programming guide 2 mVpp (guide value used).
- DG5000 per-waveform limits for the 100 / 250 MHz models (interpolated, see table).
- Whether Pro `:TRACe:DATA:DAC16 VOLTage,...` selects the volatile waveform automatically (the guide does
  not say; the driver does not send a follow-up `:FUNCtion ARB`).
- DG4000 `:APPLy:CUSTom` (documented alongside `:APPLy:USER`; the driver uses `USER`, which both the
  DG4000 and DG5000 guides document).
- `*IDN?` model strings for Pro units are assumed to be `DGxxx Pro`; `normalize_model()` accepts
  `DG822Pro`, `DG822 Pro` and `DG822-Pro`.
