# Rigol Spectrum / Real-Time Spectrum Analyzers

Driver: `server/equipment/rigol_spectrum_analyzer.py` (`RigolSABase` + one subclass per family).
Mock: `server/equipment/mock/mock_spectrum_analyzer.py` (`MockSpectrumAnalyzer`, `MOCK::SA::0`).
Tests: `tests/hardware/test_rigol_spectrum_analyzer.py`, `tests/test_mock_spectrum_analyzer.py`.
Equipment type `EquipmentType.SPECTRUM_ANALYZER`, id prefix `sa_`, readings model `SpectrumData`.

Sources: `~/Manuals/Rigol/_text_extracted/` DSA800 / DSA800E / DSA700 / DSA1000 / DSA1000A
programming guides, RSA3000 / RSA3000E / RSA5000 programming manuals, RSA800 / RSA6000 programming
guides, and the family datasheets under `~/Manuals/Rigol/<FAMILY>/Datasheet/`. The option guides
(ADM, EMI, PNOISE, VSA, BLE, LoRa, PULSE) exist but are not used by this driver.

## Model table

| Class | Model | Frequency | Min RBW | Max points | TG | RTSA | Screenshot query | Notes |
|-------|-------|-----------|---------|-----------:|----|------|------------------|-------|
| `RigolDSA800` | DSA705 | 100 kHz – 500 MHz | 100 Hz | 601 (fixed) | no | no | no | no `:SENSe:SWEep:POINts` |
| `RigolDSA800` | DSA710 | 100 kHz – 1 GHz | 100 Hz | 601 (fixed) | no | no | no | |
| `RigolDSA800` | DSA815 / DSA815-TG | 9 kHz – 1.5 GHz | 10 Hz | 3001 | -TG | no | no | preamp is the PA-DSA815 option (table says no preamp) |
| `RigolDSA800` | DSA832 / DSA832-TG | 9 kHz – 3.2 GHz | 10 Hz | 3001 | -TG | no | no | |
| `RigolDSA800` | DSA875 / DSA875-TG | 9 kHz – 7.5 GHz | 10 Hz | 3001 | -TG | no | no | |
| `RigolDSA800` | DSA832E / DSA832E-TG | 9 kHz – 3.2 GHz | 10 Hz | 3001 | -TG | no | no | no TG power-sweep commands |
| `RigolDSA1000` | DSA1030 / DSA1030-TG | 9 kHz – 3 GHz | 100 Hz | 3001 | -TG | no | no | atten 0–50 dB, RLEV to +30 dBm, TG -20..0 dBm |
| `RigolDSA1000` | DSA1030A / DSA1030A-TG | 9 kHz – 3 GHz | 10 Hz | 3001 | -TG | no | no | |
| `RigolRSA3000` | RSA3015E / -TG, RSA3030E / -TG | 9 kHz – 1.5 / 3 GHz | 1 Hz | 10001 | -TG | 10 MHz | no | modes SA, RTSA, VSA, EMI |
| `RigolRSA3000` | RSA3015N, RSA3030 / -TG / N, RSA3045 / -TG / N | 9 kHz – 1.5 / 3 / 4.5 GHz | 1 Hz | 10001 | -TG | 40 MHz (B40) | no | modes SA, RTSA |
| `RigolRSA5000` | RSA5032 / -TG / N, RSA5065 / -TG / N | 9 kHz – 3.2 / 6.5 GHz | 1 Hz | 10001 | -TG | 25 MHz (40 MHz B40) | no | modes SA, RTSA |
| `RigolRSA800` | RSA804 / RSA808 / RSA814 | 5 kHz – 4.5 / 8.5 / 14 GHz | 1 Hz | 10001 | built in | 40 MHz | `:MMEMory:STORe:SCReen:DATA?` | 2023 tree, ASCII traces only |
| `RigolRSA6000` | RSA6085 / RSA6140 / RSA6265 | 5 kHz – 8.5 / 14 / 26.5 GHz | 1 Hz | 10001 | RSA6000-TG only | 80 MHz (200 MHz opt) | `:MMEMory:STORe:SCReen:DATA?` | same tree as RSA800 |

Common limits from the guides: RBW max 1 MHz (DSA) / 10 MHz (RSA); attenuation 0–30 dB (DSA800),
0–50 dB (DSA1000, RSA); reference level -100..+20 dBm (DSA800), -100..+30 (DSA1000), -170..+30 (RSA);
TG level -40..0 dBm (DSA800, RSA), -20..0 dBm (DSA1030-TG); markers 1–4 (DSA), 1–8 (RSA); traces 1–3
(DSA, trace 4 is the math trace), 1–6 (RSA).

`has_tracking_generator` follows the `*IDN?` model string (`...-TG`). If the instrument reports the
base model although the TG is fitted, call `set_tracking_generator_fitted(True)`. TG commands raise
`ValueError` on models without a TG.

## Command vocabulary (LabLink name -> SCPI)

| Command | Parameters | SCPI (all families unless noted) |
|---------|------------|----------------------------------|
| `set_frequency` | `center`, `span` (Hz) | `:SENSe:FREQuency:CENTer`, `:SENSe:FREQuency:SPAN`; span 0 -> `:SENSe:FREQuency:SPAN 0` (DSA) / `:SENSe:FREQuency:SPAN:ZERO` (RSA) |
| `set_start_stop` | `start`, `stop` | `:SENSe:FREQuency:STARt` / `:STOP` |
| `set_full_span`, `set_zero_span`, `get_frequency` | | `:SENSe:FREQuency:SPAN:FULL`, zero-span as above, `CENTer?/SPAN?/STARt?/STOP?` |
| `set_rbw` | `rbw` Hz or `"AUTO"`, `auto` | `:SENSe:BANDwidth:RESolution[:AUTO]` (full form works on DSA1000 too) |
| `set_vbw` | `vbw`, `auto` | `:SENSe:BANDwidth:VIDeo[:AUTO]` |
| `set_reference_level` | `level` dBm | `:DISPlay:WINdow:TRACe:Y:SCALe:RLEVel` |
| `set_attenuation` | `db`, `auto` | `:SENSe:POWer:RF:ATTenuation[:AUTO]` |
| `set_preamp` | `enabled` | `:SENSe:POWer:RF:GAIN:STATe` (ValueError when the table says no preamp) |
| `set_unit` | `DBM/DBMV/DBUV/V/W` | `:UNIT:POWer` |
| `set_sweep` | `points`, `time` (s or `"AUTO"`), `continuous` | `:SENSe:SWEep:POINts`, `:SENSe:SWEep:TIME[:AUTO]`, `:INITiate:CONTinuous` |
| `single_sweep` | `timeout_s` | `:INITiate:CONTinuous OFF`, `:INITiate:IMMediate`, `*OPC?`, then poll `:STATus:OPERation:CONDition?` bit 3 (SWEeping) where present (not RSA800/6000) |
| `trigger_sweep`, `set_continuous` | | `:INITiate:IMMediate`, `:INITiate:CONTinuous` |
| `set_detector` | `detector`, `trace` | `:SENSe:DETector:FUNCtion` (DSA, RSA3000/5000) or `:SENSe:DETector:TRACe<n>` (RSA800/6000). Values POSITIVE, NEGATIVE, NORMAL, SAMPLE, RMS, VAVERAGE, QPEAK |
| `set_trace_mode` | `trace`, `mode` | `:TRACe<n>:MODE WRITe|MAXHold|MINHold|VIEW|BLANk|VIDeoavg|POWeravg` (DSA; `AVERAGE` maps to VIDeoavg); `:TRACe<n>:MODE`/`:TYPE WRITe|AVERage|MAXHold|MINHold` (RSA) with VIEW/BLANK emulated via `:TRACe<n>:DISPlay:STATe` and `:TRACe<n>:UPDate:STATe` |
| `set_average` | `count`, `trace`, `enabled` | `:TRACe:AVERage:COUNt` + `:RESet` (DSA) / `:SENSe:AVERage:COUNt` + `:CLEar` (RSA), then trace mode AVERAGE |
| `set_data_format` | `ASCII`, `REAL,32` (+ `REAL,64`, `INTEGER,32` on RSA3000/5000) | `:FORMat:TRACe:DATA`, `:FORMat:BORDer SWAPped` for binary. Not available on RSA800/6000 |
| `get_trace` | `trace`, `sweep` | `:TRACe:DATA? TRACE<n>` plus frequency/bandwidth/amplitude/detector queries -> `SpectrumData` |
| `get_readings` | | `get_trace(1)` |
| `peak_search` | `marker`, `trace` | `:CALCulate:MARKer<n>:STATe ON`, `:CALCulate:MARKer<n>:MAXimum:MAX` |
| `next_peak` | `marker`, `direction` NEXT/LEFT/RIGHT/MIN | `:CALCulate:MARKer<n>:MAXimum:NEXT|LEFT|RIGHt`, `:MINimum` |
| `set_marker` | `marker`, `frequency`, `mode`, `trace` | `:CALCulate:MARKer<n>:X`, `:MODE POSition|DELTa|BAND|SPAN` (DSA) / `POSition|DELTa|FIXed|OFF` (RSA), `:TRACe` |
| `get_marker` | `marker` | `:CALCulate:MARKer<n>:STATe? / X? / Y? / MODE?` |
| `marker_off`, `all_markers_off` | | `:CALCulate:MARKer<n>:STATe OFF`, `:CALCulate:MARKer:AOFF` |
| `marker_to_center` | `marker`, `peak` | `:CALCulate:MARKer<n>:SET:CENTer` (after `MAXimum:MAX` when `peak=True`; equivalent to DSA `:PEAK:SET:CF`) |
| `set_peak_search_mode` | `MAXIMUM`/`PARAMETER` | `:CALCulate:MARKer<n>:PEAK:SEARch:MODE` (DSA) / `:CALCulate:MARKer:PEAK:SEARch:MODE` (RSA) |
| `set_tracking_generator` | `enabled`, `level` | `:OUTPut:STATe` + `:SOURce:POWer:LEVel:IMMediate:AMPLitude` (DSA) / `:OUTPut:EXTernal:STATe` + `:SOURce:EXTernal:POWer:LEVel:IMMediate:AMPLitude` (RSA) |
| `set_output` | `enabled` | manager disconnect hook: turns the TG off when fitted, no-op otherwise |
| `measure_channel_power` | `bandwidth`, `span` | DSA: `:CONFigure:CHPower`, `:SENSe:CHPower:BANDwidth:INTegration`, `:READ:CHPower?` -> `power,density`. RSA800/6000: `:INSTrument:SELect GPSA_CHPower`, `:FETCh:CHPower1?`, `:FETCh:CHPower:DENSity1?`. RSA3000/5000: no CHPower commands in the guides -> trace integration (`method: trace_integration`) |
| `measure_obw` | `percent` | `:CONFigure:OBWidth`, `:SENSe:OBWidth:PERCent`, `:READ:OBWidth?` (RSA800/6000: mode `GPSA_OBW` + `:FETCh:OBWidth?`) |
| `set_mode` / `get_mode` | `GPSA`/`SA`, `RTSA`, (+`VSA`, `EMI` on RSA3000E; long list on RSA800/6000) | `:INSTrument:SELect`, followed by `*OPC?` (guides recommend 8 s after switching). DSA raises ValueError |
| `get_screenshot` | | `:MMEMory:STORe:SCReen:DATA?` (RSA800/6000 only; other families only save to a file on the instrument) |
| `get_measurement` | `channel` | acquisition hook, see below |
| `get_state`, `reset`, `get_error`, `clear_errors` | | snapshot dict, `*RST`, `:SYSTem:ERRor?`, `*CLS` |
| `set_input_impedance` (DSA1000 only) | `ohms` 50/75 | `:INPut:IMPedance` |

### Acquisition channels (`get_measurement(channel)`)

`PEAK` (default, trace-1 maximum), `PEAK_FREQ`, `MARKER1`..`MARKER<n>` (Y readout), `MARKER1_FREQ`,
`CHPOWER`, `TRACE<n>:MAX`, `TRACE<n>:MIN`, `TRACE<n>:MEAN`, `TRACE<n>:PEAK_FREQ`. Returns
`{"value", "unit", "channel", ...}` with NaN for an unavailable value.

## Trace data formats

`:TRACe:DATA? TRACE<n>` (all families). The reply format follows `:FORMat[:TRACe][:DATA]`:

| Family | ASCII reply | Binary |
|--------|-------------|--------|
| DSA800 / DSA800E / DSA700 / DSA1000 | `#9000009014 -1.390530e+01, -7.108871e+01, ...` — IEEE definite-length header (`#9` + 9-digit byte count) in front of the comma list (DSA800 guide 2-188). Some firmware omits the header; both parsed. Up to 601/3001 points. | `REAL,32`: `#9<len>` block of 4-byte floats. `:FORMat:BORDer` default `NORMal` = MSB first; the driver sends `SWAPped` and unpacks little-endian. |
| RSA3000 / RSA3000E / RSA5000 | bare comma list `-1.390530e+01, -7.108871e+01, ...` | `REAL,32`, `REAL,64`, `INTeger,32` blocks (`INTeger,32` scaling is undocumented; exposed as value/1000) |
| RSA800 / RSA6000 | bare comma list | none documented (no `:FORMat` command) |

`get_trace` derives the frequency axis from `STARt?`/`STOP?` and the number of returned points
(so DSA700's fixed 601 points need no `POINts?` query), computes `peak_frequency` /
`peak_amplitude`, and fills `rbw`, `vbw`, `reference_level`, `attenuation`, `unit` (`:UNIT:POWer?`)
and `detector`.

## Family differences handled by constants

| Topic | DSA800 (incl. 800E/700) | DSA1000 | RSA3000 / RSA5000 | RSA800 / RSA6000 |
|-------|-------------------------|---------|-------------------|------------------|
| Zero span | `SPAN 0` | `SPAN 0` | `SPAN:ZERO` | `SPAN:ZERO` |
| RBW keyword | `BANDwidth[:RESolution]` | `BANDwidth:RESolution` (mandatory) | `BANDwidth|BWIDth[:RESolution]` | same as RSA3000 |
| Trace type | `TRACe<n>:MODE` 7 keywords | same | `MODE` or `TYPE`, 4 keywords, VIEW/BLANK via DISPlay/UPDate | `TYPE` only |
| Average count | `TRACe:AVERage:COUNt` | same | `SENSe:AVERage:COUNt` (also TRACe form) | `SENSe:AVERage:COUNt` |
| Detector | `DETector:FUNCtion` | same | `DETector:FUNCtion` or `DETector:TRACe<n>` | `DETector:TRACe<n>` only |
| Peak search mode | `MARKer<n>:PEAK:SEARch:MODE` | same | `MARKer:PEAK:SEARch:MODE` | same as RSA3000 |
| Marker modes | POSition, DELTa, BAND, SPAN | same | POSition, DELTa, FIXed, OFF | same |
| Markers / traces | 4 / 3 | 4 / 3 | 8 / 6 | 8 / 6 |
| TG tree | `OUTPut:STATe`, `SOURce:POWer...` | same | `OUTPut:EXTernal:STATe`, `SOURce:EXTernal:POWer...` | same as RSA3000 |
| Mode select | none | none | `INSTrument:SELect SA|RTSA` (+VSA|EMI on 3000E) | `INSTrument:SELect SA|RTSA|GPSA_TG|GPSA_CHPower|...` |
| Sweep complete | `*OPC?` + `STATus:OPERation:CONDition?` | same | same | `*OPC?` only |
| Channel power | `CONFigure/READ:CHPower` | same | not in guide -> trace integration | mode `GPSA_CHPower` + `FETCh:CHPower1?` |
| Binary traces | REAL,32 | REAL,32 | REAL,32/64, INT,32 | none |
| Screenshot | file only (`MMEMory:STORe:SCReen`) | file only | file only | `MMEMory:STORe:SCReen:DATA?` |
| Extra | `SYSTem:OPTions?` lists options | `INPut:IMPedance 50|75` | | |

## Things the guides leave open

- Whether `*IDN?` includes the `-TG` suffix on DSA/RSA TG variants. The driver trusts the model
  string and offers `set_tracking_generator_fitted()` as an override.
- DSA1000 does not show an example `:TRACe:DATA?` reply; the DSA800-style header is assumed and
  the parser accepts both forms.
- `:MMEMory:STORe:SCReen:DATA?` (RSA800/6000) is documented only as "Saves the screen data"; the
  driver returns the raw block bytes.
- RSA800 datasheet says sweep points 101–100,001 while the programming guide says 101–10,001; the
  driver enforces the guide's 10,001.
- DSA800 datasheet lists the preamplifier for DSA832/875/832E only; DSA815 is treated as no-preamp
  (the PA-DSA815 option exists, `SYSTem:OPTions?` would show it).
- `INTeger,32` trace scaling on RSA3000/5000 is not specified.
- `:INSTrument:SELect` completion: guides recommend an 8 s wait; the driver relies on `*OPC?` with
  a widened timeout and falls back to the fixed delay.
