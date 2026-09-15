# Rigol M300 Data Acquisition / Switch Mainframe

Driver: `server/equipment/rigol_daq.py` (`RigolM300`). Mock: `server/equipment/mock/mock_daq.py`
(`MockDAQ`, `MOCK::DAQ::n`, model `MockDAQ-300`: MC3120 in slots 1 and 2, MC3416 actuator in slot 3).
Type `EquipmentType.DATA_ACQUISITION`, id prefix `daq_`, data model `DataAcquisitionData`.
Reference: RIGOL "M300 Programming Guide" (Agilent 34970A-style SCPI). `*IDN?` -> `RIGOL TECHNOLOGIES,M300,<serial>,<fw>`.

## Mainframe and modules

Five slots; channel numbers are `SCC` (slot 1..5, channel 01..64). `SYSTem:CTYPe? <slot>00` reports
`RIGOL TECHNOLOGIES,<module>,<serial>,<fw>` (`RIGOL TECHNOLOGIES,0,0,0` when empty).

| Module | Description | Notes |
|--------|-------------|-------|
| MC3065 | DMM module | required for multiplexer scans (`INSTrument:DMM:INSTalled?`) |
| MC3120 | 20-ch multiplexer | DCV ACV 2WR 4WR TEMP FREQ PER; 4-wire pairs n / n+10 |
| MC3132 | 32-ch multiplexer | as MC3120; 4-wire pairs n / n+16 |
| MC3164 | 64-ch single-ended multiplexer | no 4-wire, no current, no FRTD |
| MC3324 | 20 voltage + 4 current channels | channels 21..24 are DCI/ACI only |
| MC3416 | 16-ch actuator | `ROUTe:CLOSe` = NO side, `ROUTe:OPEN` = NC side |
| MC3534 | multifunction | 1-4 DIO, 5-8 totalizer, 9-12 DAC (not driven by this driver) |
| MC3648 | 4x8 matrix | channel = row/column, e.g. `126` |

Standard ranges: DCV/ACV 200 mV..300 V; DCI/ACI 200 uA..1 A; RES/FRES 200 Ohm..100 MOhm; FREQ/PER
"range" is ignored (resolution = gate time 1 ms..1 s). Reading memory 100 000 readings; overload = `±9.9E+37`.

## Command vocabulary

| Command | SCPI |
|---------|------|
| `get_modules()` | `SYSTem:CTYPe? 100..500`, `INSTrument:DMM:INSTalled?` |
| `configure_channel(channel, function, range, resolution, sensor, sensor_type)` | `CONFigure:VOLTage:DC [range[,res],](@ch)`, `:VOLTage:AC`, `:CURRent:DC/AC`, `:RESistance`, `:FRESistance`, `:FREQuency`, `:PERiod`, `CONFigure:TEMPerature TCouple|THERmistor|RTD|FRTD,<type>,1,DEF,(@ch)` |
| `get_configuration(channels)` | `CONFigure? (@list)` -> `"VOLT +2.000000E+01,+6.000000E-06"` |
| `set_scan_list(channels)` / `get_scan_list()` | `ROUTe:SCAN (@101:110)` / `ROUTe:SCAN?` -> `#214(@203,204,205)` |
| `scan(wait=True)` -> `DataAcquisitionData` | `READ?` (wait) or `INITiate` (no wait, then `fetch()` = `FETCh?`) |
| `read_channel(channel)` | `ROUTe:SCAN (@ch)`, `READ?`, then restores the scan list |
| `close_channel` / `open_channel` / `get_closed_channels` | `ROUTe:CLOSe (@..)`, `ROUTe:OPEN (@..)`, `ROUTe:CLOSe? (@..)` |
| `set_trigger(source, count, interval)` / `get_trigger()` / `trigger()` / `abort()` | `TRIGger:SOURce IMMediate|TIMer|BUS|EXTernal|ABSolute|ALARm1..4`, `TRIGger:COUNt <n>|INFinity`, `TRIGger:TIMer <s>`, `*TRG`, `ABORt` |
| `set_temperature_unit(unit, channels)` | `UNIT:TEMPerature C|F|K[,(@..)]` |
| `get_data_points()` / `remove_data(n)` | `DATA:POINts?` / `DATA:REMove? n` |
| `set_dmm_enabled(enabled)` | `INSTrument:DMM ON|OFF` |
| `get_readings()` | last scan (or a new one) |
| `get_measurement(channel)` | channel `101` / `CH101` / `@101`; channels in the scan list share one `READ?` per polling cycle, others use `read_channel` |
| `get_measurements()`, `get_state()`, `reset()` (`*RST`), `get_error()` (`SYSTem:ERRor?`) | |

Channel list helpers: `format_channel_list(["101","102"])` -> `(@101,102)`, `format_channel_list("101:110")` -> `(@101:110)`,
`expand_channel_list("(@101:103,301)")` -> `["101","102","103","301"]`.

## Quirks

- `CONFigure ...,(@list)` **replaces** the scan list with `(@list)`; the driver re-sends `ROUTe:SCAN` with the
  user's list after every `configure_channel`.
- The mainframe stores and scans channels in ascending slot/channel order whatever order was given; readings from
  `READ?`/`FETCh?` are mapped onto the sorted scan list. On connect the driver forces
  `FORMat:READing:UNIT|TIME|CHANnel|ALARm OFF` so the response is plain numbers.
- `ROUTe:CLOSe/OPEN` on a multiplexer channel that is in the scan list is an instrument error; the driver rejects it.
- `INITiate` clears the previous readings; `FETCh?` blocks until the scan completes (driver raises the VISA timeout to 60 s).
- `TRIGger:COUNt? ` returns `9.90000200E+37` for INFinity (reported as `"INFINITY"`).
- RS-232 default baud rate is not stated in the guide; the driver assumes 9600 8N1 (`SERIAL_BAUD`).
- `*RST` clears the scan list and channel configuration; `SYSTem:PRESet` keeps the scan list.
