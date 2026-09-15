# Rigol Vector Network Analyzers (RSA3000N/RSA5000N VNA mode, DNA6000)

Driver: `server/equipment/rigol_vna.py` (`RigolVNABase` -> `RigolRSAN`, `RigolDNA6000`).
Mock: `server/equipment/mock/mock_vna.py` (`MockVNA`, `MOCK::VNA::n`, model `MockVNA-6000`).
Type `EquipmentType.VECTOR_NETWORK_ANALYZER`, id prefix `vna_`, data model `NetworkAnalyzerData`.

## Models

| Class | Model | Frequency | Ports / parameters | Points | Source power | IF BW | Source |
|-------|-------|-----------|--------------------|--------|--------------|-------|--------|
| `RigolRSAN` | RSA3015N | 100 kHz – 1.5 GHz | S11, S21 (reflection + TG transmission) | 101–10001 | -40..0 dBm | 1 kHz–10 MHz (1-3-10) | VNA Programming Guide 2020: `[:SENSe]:FREQuency:CENTer/STOP` remarks (Fmax per model), `:SWEep:POINts`, `:SOURce:POWer`, `:BANDwidth` |
| `RigolRSAN` | RSA3030N | 100 kHz – 3 GHz | same | same | same | same | same |
| `RigolRSAN` | RSA3045N | 100 kHz – 4.5 GHz | same | same | same | same | same |
| `RigolRSAN` | RSA5032N | 100 kHz – 3.2 GHz | same | same | same | same | same |
| `RigolRSAN` | RSA5065N | 100 kHz – 6.5 GHz | same | same | same | same | same |
| `RigolDNA6000` | DNA6082 / DNA6084 | 5 kHz – 8.5 GHz | 2 / 4 ports (S11..S22 / S11..S44) | 1–100001 | -40..+10 dBm | 1 Hz–10 MHz | DNA6000 Programming Guide "Content Conventions" table, `:SENSe<cn>:SWEep:POINts`, `:SOURce<cn>:POWer`, `:SENSe<cn>:BANDwidth` |
| `RigolDNA6000` | DNA6142 / DNA6144 | 5 kHz – 14 GHz | 2 / 4 | same | same | same | same |
| `RigolDNA6000` | DNA6202 / DNA6204 | 5 kHz – 20 GHz | 2 / 4 | same | same | same | same |
| `RigolDNA6000` | DNA6262 / DNA6264 | 5 kHz – 26.5 GHz | 2 / 4 | same | same | same | same |
| `RigolDNA6000` | DNA6xxx-R | as base model | as base model | same | same | same | DNA6000-R Series Programming Guide (same table, `-R` suffix) |

Markers: 8 on the RSA-N (`:CALCulate:MARKer<n>`), 16 on the DNA6000. Traces: 4 on the RSA-N (`:DISPlay:TRACe<n>`), any existing `<mn>` on the DNA6000.

## Command vocabulary (both classes)

| Command | RSA-N SCPI | DNA6000 SCPI |
|---------|-----------|--------------|
| `set_sweep(start, stop, points, power, if_bandwidth)` / `set_start_stop` / `set_center_span` / `set_points` / `set_power` / `set_if_bandwidth` / `get_sweep` | `:SENSe:FREQuency:STARt/STOP/CENTer/SPAN`, `:SENSe:SWEep:POINts`, `:SOURce:EXTernal:POWer:LEVel:IMMediate:AMPLitude`, `:SENSe:BANDwidth:RESolution` | `:SENSe<cn>:FREQuency:...`, `:SENSe<cn>:SWEep:POINts`, `:SOURce<cn>:POWer`, `:SENSe<cn>:BANDwidth` |
| `set_continuous(enabled)` | `:INITiate:CONTinuous` | `:INITiate:CONTinuous` |
| `sweep_single(wait)` / `trigger` | `:INITiate:IMMediate` + `*OPC?` | `:SENSe<cn>:SWEep:MODE SINGle` + `*OPC?` |
| `set_parameter(trace, s_param)` / `get_parameter` | `:CONFigure S11|S21` (mode-wide; S12/S22 rejected) | `:CALCulate<cn>:PARameter<mn>:DEFine S21` |
| `set_format(trace, fmt)` / `get_format` | `:DISPlay:TRACe<n>:FORMat` (S21 allows only MLOG/PHAS/GDEL/MLIN/UPH/PPH) | `:CALCulate<cn>:MEASure<mn>:FORMat` |
| `get_trace(trace, single)` -> `NetworkAnalyzerData` | `:TRACe<n>:DATA?` -> `(re,im)(re,im)...`, formatted numerically by `format_complex`; stimulus = linspace(start, stop) | `:DATA:FDATA?` (2 values/point for SMITh/POLar -> `secondary_values`), `:DATA:X?` (fallback `:SENSe<cn>:FREQuency:DATA?`) |
| `get_complex_trace(trace)` | `:TRACe<n>:DATA?` | `:CALCulate<cn>:MEASure<mn>:DATA:SDATA?` |
| `list_traces()` | traces 1..4 all carry `:CONFigure?` | `:CALCulate<cn>:PARameter:CATalog:EXTended? DEFine` (`CH1_S11_1,S11,...`) |
| `set_marker(marker, frequency, trace)` / `get_marker` / `marker_search(marker, MAX|MIN, trace)` | `:CALCulate:MARKer<n>:MODE POSition`, `:X`, `:Y?` (two values), `:MAXimum:MAX` / `:MINimum` | `:CALCulate<cn>:MEASure<mn>:MARKer<mk> ON`, `:X`, `:Y?` (`value,0`), `:FUNCtion:EXECute MAXimum|MINimum` |
| `calibrate_start(method)` | `SOL` -> `:CONFigure S11`; `THRU` -> `:CONFigure S21` | `:SENSe<cn>:CORRection:COLLect:METHod BASic|RESP|RPOWer|NONE` |
| `calibrate_acquire(standard)` | `:CALibration:S11:OPEN|SHORt|LOAD`, `:CALibration:S21:THROugh` | `:SENSe<cn>:CORRection:COLLect:ACQuire OPEN|SHORt|LOAD|THRU` |
| `calibrate_save()` / `calibrate_abort()` | `:CALibration:S11|S21:SAVE` / `:ABORt`; `calibrate_clear()` -> `:CALibration:CLEAr` | `:SENSe<cn>:CORRection:COLLect:SAVE` / `:METHod NONE` |
| `set_correction(enabled)` / `get_correction()` | not queryable (`get_correction` returns `None`; `set_correction(False)` clears) | `:SENSe<cn>:CORRection:STATe` |
| `set_mode(mode)` | `:INSTrument:SELect SA|RTSA|VSA|EMI|VNA` (8 s pause, done automatically on connect when not in VNA) | no-op |
| DNA only: `set_rf_output`, `set_trigger_source(IMM|EXT|MAN)`, `manual_trigger`, `abort`, `create_trace(s_param)` | — | `:OUTPut:STATe`, `:TRIGger:SOURce`, `:INITiate<cn>:IMMediate`, `:ABORt`, `:DISPlay:TRACe:NEW 0` |
| `get_readings()` | trace 1 | trace 1 |
| `get_measurement(channel)` | `S11:MIN`, `S21:MAX`, `S21:AT:<hz>`, `S21:MEAN`, `S21:PTP`, `S21:MIN_FREQ`, `TRACE1:MIN` (default), `MARKER1` | same |
| `get_state()`, `reset`, `get_error` | `*RST` then re-select VNA mode; `:SYSTem:ERRor?` | `*RST`; `:SYSTem:ERRor?` |

Formats: `MLOG` (dB), `MLIN`, `PHAS`/`UPH`/`PPH` (deg), `SWR`, `REAL`, `IMAG`, `GDEL` (s), `SMIT`/`POL`/`SADM` (two values per point).
RSA-N additionally `SLIN`, `SLOG`, `SCOM`, `PLIN`, `PLOG` on S11.

## Quirks / unverified

- RSA-N `:INITiate:IMMediate` is documented only as "sets the sweep type to Single"; the driver assumes it also starts one sweep (as on the spectrum analyzer) and waits with `*OPC?`.
- RSA-N has no stimulus-frequency query and no correction-state query; group delay is computed from unwrapped phase.
- DNA6000 `:SENSe<cn>:CORRection:COLLect[:ACQuire] <char>` documents `<char>` only as "String"; the OPEN/SHORt/LOAD/THRU spellings are an assumption.
- DNA6000 `<mn>` must already exist (`:DISPlay:TRACe:NEW` adds one); trace numbers are taken from the `CH1_S11_<n>` catalog names.
- `:FORM:DATA ASCII,0` is only in the non-R guide; it is the default, so the driver merely tries it.
- The DNA6000-R guide lists -40..+15 dBm only for segment-sweep power; the model table uses the -40..+10 dBm of `:SOURce<cn>:POWer`.
- Deep sweeps (100001 points) can exceed the 10 s VISA timeout; `sweep_single` raises it to 120 s while waiting on `*OPC?`.
