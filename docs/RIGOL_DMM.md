# Rigol DM3058 / DM3058E / DM3068 Multimeters

Driver: `server/equipment/rigol_multimeter.py` (`RigolDMMBase`, `RigolDM3058`, `RigolDM3058E`, `RigolDM3068`).
Mock: `server/equipment/mock/mock_multimeter.py` (`MOCK::DMM::n`).
Source material: RIGOL *DM3058/DM3058E Programming Guide* (Nov 2021) and *DM3068 Programming Guide*
(CHM), plus the DM3068 User Guide remote-control chapter.

## Connecting

| Interface | Resource string | Notes |
|-----------|-----------------|-------|
| USB-TMC | `USB0::0x1AB1::0x0C94::DM3A020100823::INSTR` | VID `0x1AB1`. PID `0x0C94` = DM3068, `0x09C4` = DM3058/E. Auto-identified by the USB table and `*IDN?`. |
| LAN | `TCPIP::172.16.3.32::INSTR` | VXI-11; DM3068 is LXI-C (web page at the IP, login `rigol`/`rigol`). Not on DM3058E. |
| GPIB | `GPIB0::7::INSTR` | Default address 7 (`:UTILity:INTErface:GPIB:ADDRess`). Not on DM3058E. |
| RS-232 | `ASRL/dev/ttyUSB0::INSTR` | 9600 8N1 default, CR+LF terminated. The driver configures the port itself. |

`*IDN?` returns `Rigol Technologies,<model>,<serial>,<firmware>`; the equipment ID is `dmm_<hash>` and the
type is `multimeter`. On connect the driver sends `CMDSET RIGOL` if another command set was left active.

## Command surface

All commands go through `execute_command(name, parameters)` (REST `POST /equipment/{id}/command`).

| Command | Parameters | SCPI behind it |
|---------|------------|----------------|
| `set_function` / `get_function` | `function`: DCV, ACV, DCI, ACI, RES, FRES, FREQ, PER, CAP, CONT, DIODE | `:FUNCtion:<f>` / `:FUNCtion?` |
| `measure` | `function?` | `:MEASure:<f>?` → `MultimeterData` |
| `get_readings` | – | reading on the active function (used by WebSocket `readings` stream) |
| `get_measurement` | `channel`: `CH1`, `CH2`, or a function name | acquisition-engine hook, returns `{"value", "unit", "function", "overload"}` |
| `read_samples` | `count`, `function?`, `interval_s?` | N consecutive readings with min/max/mean/std |
| `set_range` / `get_range` / `set_auto_range` | `range`: index, full-scale value, `MIN`/`MAX`/`DEF`/`AUTO`; `function?` | `:MEASure:<f> <n>` / `:MEASure AUTO|MANU` / `:MEASure:<f>:RANGe?` |
| `set_rate` / `get_rate` | `rate`: FAST, MEDIUM, SLOW | `:RATE:<f> {F|M|S}` (DM3058 answers `F/M/S`, DM3068 `FAST/MEDIUM/SLOW`; both normalised) |
| `set_dc_impedance` | `impedance`: `10M` or `10G` | `:MEASure:VOLTage:DC:IMPEdance` |
| `set_filter` | `enabled`, `function?` (DCV/DCI) | `:MEASure:<f>:FILTer:STATe` |
| `set_continuity_threshold` | `threshold_ohms` 1..2000 | `:MEASure:CONTinuity <n>` |
| `set_secondary_function` / `clear_secondary_function` / `get_secondary_function` | `function` | `:FUNCtion2:<f>`, `:FUNCtion2:CLEar`, `:FUNCtion2:VALUe2?` |
| `set_trigger_source` / `get_trigger_source` | `source`: AUTO, SINGLE, EXT (Agilent BUS/IMM aliases accepted) | `:TRIGger:SOURce` |
| `set_trigger_interval` | `interval_s` | `:TRIGger:AUTO:INTErval` (ms on DM3058, s on DM3068 — handled) |
| `set_sample_count` / `get_sample_count` / `trigger` | `count` (≤2000 DM3058, ≤50000 DM3068) | `:TRIGger:SINGle`, `:TRIGger:SINGle:TRIGgered` |
| `set_external_trigger` | `edge`: RISE, FALL, HIGH, LOW | `:TRIGger:EXT` |
| `set_auto_hold` | `enabled`, `sensitivity?` 0..3 | `:TRIGger:AUTO:HOLD[:SENSitivity]` |
| `set_math_function` / `get_math_function` | NONE, REL, DB, DBM, MIN, MAX, AVERAGE, TOTAL, PF | `:CALCulate:FUNCtion` |
| `set_statistics` / `get_statistics` | `enabled` | `:CALCulate:STATistic:*` |
| `set_rel_offset` | `offset` (value or CURR/MIN/MAX/DEF), `enabled` | `:CALCulate:REL:*` |
| `set_limits` / `get_limit_result` | `lower`, `upper`, `enabled` | `:CALCulate:PF:*` |
| `set_beeper`, `set_display_brightness` | `enabled` / `level` 0..32 | `SYSTem:BEEPer:STATe`, `:SYSTem:DISPlay:BRIGht` |
| `set_command_set` / `get_command_set` | `name`: RIGOL, AGILENT, FLUKE | `CMDSET` (driver assumes RIGOL; switch only if you drive it raw) |
| `get_interface_config` | – | `:UTILity:INTErface:*` read-back (LAN/GPIB omitted on DM3058E) |
| `reset`, `self_test`, `get_error`, `clear_errors`, `get_state` | – | `*RST`, `*TST?`, `SYSTem:ERRor?`, `*CLS` |

`MultimeterData` fields: `function`, `value` (None on overload), `unit`, `overload`, `range_index`,
`range_full_scale`, `auto_range`, `rate`, and `secondary_*`. Overload is detected as |reading| ≥ 9e37.

## Acquisition

Create an acquisition session with channels named by function, e.g. `channels: ["DCV", "RES"]`; the engine
calls `get_measurement(channel)` per sample and the driver switches function as needed (switching costs
~200 ms plus the meter's settling, so keep single-function channel lists for fast logging). `CH1` means
"whatever function is active", `CH2` the secondary display. Overloads are recorded as NaN.

Sustainable polling rates (readings/s at 50 Hz mains, from the manuals):

| Rate | DM3058 | DM3068 |
|------|--------|--------|
| FAST | 123 | 2500 |
| MEDIUM | 20 | 250 |
| SLOW | 2.5 | 0.5 |

The VISA round-trip, not the meter, limits practical acquisition to a few tens of readings per second over
USB and less over RS-232.

## Model differences handled by the driver

| Item | DM3058 / DM3058E | DM3068 |
|------|------------------|--------|
| Digits | 5½ | 6½ |
| ACI ranges | 20 mA, 200 mA, 2 A, 10 A | 200 µA … 10 A (6 ranges) |
| CAP ranges | 2 nF … 10 mF (6) | 2 nF … 100 mF (9) |
| `:RATE:*?` reply | `F` / `M` / `S` | `FAST` / `MEDIUM` / `SLOW` |
| `:TRIGger:AUTO:INTErval` unit | ms (integer) | s (real) |
| `:TRIGger:SINGle` max | 2000 | 50000 |
| Secondary display | DCV, ACV, DCI, ACI, FREQ, PER, RES, FRES, CAP | FREQ only (with ACV/ACI main) |
| Interfaces | USB, LAN, GPIB, RS-232 (E: USB, RS-232) | USB, LAN (LXI-C), GPIB, RS-232 |
| `:SYSTem:TYPE?/SERIal?/EDITion?` | – | yes (used as fallback identity) |

## Not implemented (by design)

- The Agilent 34401A and Fluke 45 compatibility command sets. The RIGOL set covers everything needed; the
  Agilent `INIT`/`FETCh?`/`SAMPle:COUNt` buffered readback could be added later for burst captures.
- The SENSOR (any-sensor / temperature) function: it cannot be enabled remotely on either meter.
