# Rigol DM858 / DM858E Digital Multimeter

Driver: `server/equipment/rigol_multimeter_dm858.py` — `RigolDM858` and thin
subclass `RigolDM858E`. Equipment type `MULTIMETER`, id prefix `dmm_`, readings
model `MultimeterData`. Same LabLink command names as the DM3058/DM3068 driver
(`rigol_multimeter.py`) so panels and profiles work unchanged; the mock for
this class is the existing `MockMultimeter` (`MOCK::DMM::n`).

The model row is picked from `*IDN?` (`RIGOL TECHNOLOGIES,<model>,<serial>,<sw>`);
"DM858E" is matched before "DM858".

## Model table

| Model | Digits | Interfaces | Max current range | Max capacitance range | Reading memory | Reading rate | Source |
|-------|--------|------------|-------------------|-----------------------|----------------|--------------|--------|
| DM858 | 5 ½ | USB, LAN (LXI) | 10 A | 10 mF | 500,000 | 125 rdg/s | DM858 Programming Guide (CONFigure/DATA notes), DM858 Series Data Sheet |
| DM858E | 5 ½ | USB, LAN | 3 A | 1 mF | 20,000 | 80 rdg/s | same |

Range tables (full scale, from the `CONFigure:<func>` parameter tables):

| Function | Ranges |
|----------|--------|
| DCV | 100 mV, 1 V, 10 V, 100 V, 1000 V |
| ACV (also FREQ/PER input voltage range) | 100 mV, 1 V, 10 V, 100 V, 750 V |
| DCI / ACI | 100 µA, 1 mA, 10 mA, 100 mA, 1 A, 10 A (DM858) or 3 A (DM858E) |
| RES / FRES | 100 Ω, 1 kΩ, 10 kΩ, 100 kΩ, 1 MΩ, 10 MΩ, 50 MΩ |
| CAP | 1 nF, 10 nF, 100 nF, 1 µF, 10 µF, 100 µF, 1 mF, 10 mF (DM858 only) |
| CONT / DIODE / TEMP | fixed |

Rate ↔ integration time (guide Table 3.14): FAST = 0.4 PLC (1000 ppm),
MEDIUM = 5 PLC (100 ppm), SLOW = 20 PLC (10 ppm). Only DCV, DCI, RES and FRES
have an `NPLC` command.

## LabLink command table

| Command | Parameters | SCPI |
|---------|------------|------|
| `set_function` / `get_function` | `function` DCV/ACV/DCI/ACI/RES/FRES/FREQ/PER/CAP/CONT/DIODE/TEMP | `[SENSe]:FUNCtion "<VOLT:DC\|VOLT:AC\|CURR:DC\|CURR:AC\|RES\|FRES\|FREQ\|PER\|CAP\|CONT\|DIOD\|TEMP>"` (does not reset range) |
| `configure` / `get_configuration` | `function`, `range`, `resolution` | `CONFigure:<func> [range[,res]]`, `CONFigure?` (resets range/trigger params) |
| `set_range` / `get_range` | `range` index, value, MIN/MAX/DEF/AUTO; `function` | `[SENSe]:<func>:RANGe`, `:RANGe:AUTO?`; FREQ/PER use `:FREQuency:VOLTage:RANGe` |
| `set_auto_range` | `enabled`, `function` | `[SENSe]:<func>:RANGe:AUTO ON\|OFF` |
| `set_rate` / `get_rate` | `rate` FAST/MEDIUM/SLOW (F/M/S) | `[SENSe]:<func>:NPLC 0.4\|5\|20` |
| `set_nplc` | `nplc` 0.4/5/20 | same |
| `set_resolution` | `resolution` | `[SENSe]:<func>:RESolution` (DCV, DCI, RES, FRES) |
| `set_temperature_sensor` | `probe_type` FRTD/RTD/FTHERMISTOR/THERMISTOR/TCOUPLE, `sensor_type` 385…392 / 2200…30000 / B E J K N R S T | `CONFigure:TEMPerature <probe>,<type>` |
| `set_temperature_unit` | `unit` C/F/K | `UNIT:TEMPerature` |
| `measure` / `get_readings` | `function`, `include_range` | `READ?` (+ range/NPLC queries) → `MultimeterData` |
| `get_measurement` | `channel` = `CH1`/`1`/`MAIN` (active function), `CH2`/`SECONDARY`, or a function name | acquisition hook; overload → NaN |
| `get_measurements` | — | `{<FUNC>: value, <FUNC>_unit, overload, [secondary]}` |
| `read_samples` | `count` ≤ 2000, `function`, `interval_s` | `TRIGger:SOURce BUS` + `SAMPle:COUNt` + `INITiate` + `*TRG` + `FETCh?` (trigger source restored); with `interval_s` > 0 loops `READ?` |
| `set_secondary_function` / `clear_secondary_function` / `get_secondary_function` | `function` FREQ/PER (main ACV/ACI), ACV (main FREQ/PER), RAW (pre-math value) | `[SENSe]:<func>:SECondary "<FREQuency\|PERiod\|VOLTage:AC\|CALCulate:DATA\|OFF>"`, `[SENSe]:DATA2?` |
| `set_trigger_source` / `get_trigger_source` | `source` IMM (AUTO), BUS (SINGLE), EXT | `TRIGger:SOURce IMMediate\|BUS\|EXTernal` |
| `set_trigger_count` / `get_trigger_count` | `count` 1..1000 | `TRIGger:COUNt` |
| `set_sample_count` / `get_sample_count` | `count` 1..2000 | `SAMPle:COUNt` |
| `trigger` / `initiate` / `fetch` / `abort` | — | `*TRG`, `INITiate`, `FETCh?`, `ABORt` |
| `get_data_points` / `remove_data` / `get_last_reading` | `count`, `wait` | `DATA:POINts?`, `DATA:REMove? <n>[,WAIT]`, `DATA:LAST?` |
| `set_math_function` / `get_math_function` | NONE, REL (NULL), DB, DBM, MIN/MAX/AVERAGE/TOTAL (statistics), PF (LIMIT) | `[SENSe]:<func>:NULL:STATe`, `CALCulate:SCALe:FUNCtion/STATe`, `CALCulate:AVERage:STATe`, `CALCulate:LIMit:STATe` — selecting one switches the others off |
| `set_statistics` / `clear_statistics` / `get_statistics` | `enabled` | `CALCulate:AVERage:STATe/CLEar`, `:MINimum? :MAXimum? :AVERage? :SDEViation? :COUNt?` |
| `set_rel_offset` | `offset` value or CURR/MIN/MAX/DEF, `enabled` | `[SENSe]:<func>:NULL:VALue`, `:NULL:VALue:AUTO ON` for CURR, `:NULL:STATe` |
| `set_limits` / `get_limit_result` | `lower`, `upper`, `enabled` | `CALCulate:LIMit:LOWer/UPPer/STATe/CLEar`; result from `STATus:QUEStionable:CONDition?` bits 11/12 → PASS / FAIL_LOW / FAIL_HIGH / FAIL |
| `set_db_reference` | `reference`, `dbm` | `CALCulate:SCALe:DB:REFerence` / `:DBM:REFerence` |
| `set_beeper` / `beep` | `enabled` | `SYSTem:BEEPer:STATe`, `SYSTem:BEEPer:IMMediate` |
| `get_screenshot` | `image_format` BMP/PNG | `HCOPy:SDUMp:DATA:FORMat`, `HCOPy:SDUMp:DATA?` |
| `get_scpi_version` | — | `SYSTem:VERSion?` |
| `reset` / `get_error` / `clear_errors` / `self_test` / `get_state` | — | `*RST`, `SYSTem:ERRor?`, `*CLS`; `self_test` returns None (no `*TST?` documented) |

## Quirks and unverifiable items

* `READ?` blocks until the trigger condition is met. The driver keeps the
  source at IMMediate except inside `read_samples`, which switches to BUS,
  fires `*TRG` and restores the previous source (and `SAMPle:COUNt 1`).
* `CONFigure:<func>` resets range, resolution and trigger parameters to their
  defaults, so plain function switching uses `SENSe:FUNCtion`.
* `SENSe:FUNCtion?` returns a quoted short form (`"VOLT"`, `"CURR:AC"`,
  `"DIOD"`); `CONFigure?` returns e.g. `VOLT 1.00000000E+01,1.00000000E-03`,
  `TEMP FRTD,385` or just `CONT`.
* No `TRIGger:DELay`, `TRIGger:AUTO:INTErval` or display-brightness command
  exists in the guide, so `set_trigger_interval` / `set_display_brightness`
  from the DM3058 driver have no DM858 equivalent. `OUTPut:TRIGger:SLOPe`
  sets the polarity of the VM-complete *output*, not the trigger input.
* Limit pass/fail is not returned by a query; the driver decodes bits 11
  ("Lower Limit Failed") and 12 ("Upper Limit Failed") of the Questionable
  Data condition register. Bits are latched until `CALCulate:LIMit:CLEar`.
* AC functions, FREQ/PER, CAP, CONT, DIODE and TEMP have no selectable rate;
  `set_rate` raises ValueError for them and `MultimeterData.rate` is None.
* The guide documents both `[SENSe]:FRESistance:NPLC` (header) and
  `SENSe:FRESistance:DC:NPLC` (example); the header form is used.
* Interfaces: the guide's LAN/LXI commands apply to the family; whether the
  DM858E ships with LAN was not verifiable from the data sheet text and both
  models are listed as USB + LAN.
* `SYSTem:ERRor?` returns `+0,"No error"` when the queue is empty; `*RST` does
  **not** clear the error queue (only `*CLS` does).
* Overload is reported as 9.9E37 (standard SCPI); the driver maps it to
  `value=None`, `overload=True` (NaN in `get_measurement`).
