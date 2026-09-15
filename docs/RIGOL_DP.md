# Rigol DP-Series Power Supplies

Driver: `server/equipment/rigol_power_supply.py` (`RigolDPBase` + one subclass per family).
Tests: `tests/hardware/test_rigol_power_supply.py` (scripted fake instrument, no hardware).

Sources: the six programming guides under `~/Manuals/Rigol/_text_extracted/` (DP800 is the
primary reference) plus the DP700/DP900/DP2000 datasheets and DP1308A/DP1116A spec sheets.

## Families and interfaces

| Class          | Models                                             | Interfaces                                   | Tree          |
|----------------|----------------------------------------------------|----------------------------------------------|---------------|
| `RigolDP800`   | DP811/A, DP813/A, DP821/A, DP822/A, DP831/A, DP832/A | USB, LAN, RS-232, GPIB (LAN/RS-232 optional on non-A) | modern        |
| `RigolDP700`   | DP711, DP712                                       | RS-232 only                                  | modern        |
| `RigolDP900`   | DP932A, DP932U, DP932E                             | USB, LAN, RS-232 (not on DP932U)             | modern        |
| `RigolDP2000`  | DP2031                                             | USB, LAN, RS-232, GPIB (USB adaptor)         | modern        |
| `RigolDP1308A` | DP1308A                                            | USB, LAN, GPIB                               | 2009 (older)  |
| `RigolDP1116A` | DP1116A                                            | USB, LAN, GPIB                               | 2010 (older)  |

RS-232 defaults: 9600 baud, 8 data bits, no parity, 1 stop bit; commands end with `\r\n`
(DP800 guide, "Remote Control"). The driver configures this whenever the VISA resource is
`ASRL...`/`COM...`. USB-TMC / VXI-11 use `\n`.

`*IDN?` → `<manufacturer>,<model>,<serial>,<firmware>`. Manufacturer is `RIGOL TECHNOLOGIES`
on DP700/DP800 and `Rigol Technologies` on DP900/DP2000/DP1308A/DP1116A (the DP1116A pads the
fields with spaces). After `*IDN?` the driver looks the reported model up in `MODEL_TABLE`
and switches to that model's limits **and** family dialect, so the limits are right even when
the generic class (or the wrong family class) was instantiated.

## Command table (what the driver sends)

`<ch>` is `CH<n>` on DP700/800/900/2000, `P6V|P25V|N25V` on DP1308A and omitted on DP1116A.
Bracketed leaves are omitted where the family lacks them (see quirks).

| LabLink command               | SCPI (modern tree)                                   | DP1308A / DP1116A                          |
|-------------------------------|------------------------------------------------------|--------------------------------------------|
| `set_voltage(voltage, channel)` | `:SOURce<n>:VOLTage <v>`                           | `:INSTrument:NSELect <n>` then `:VOLTage <v>` (no NSEL on DP1116A) |
| `set_current(current, channel)` | `:SOURce<n>:CURRent <i>`                           | as above with `:CURRent`                   |
| `apply(channel, voltage, current)` | `:APPLy <ch>,<v>[,<i>]`                         | `:APPLy P6V,<v>,<i>` / `:APPLy <v>,<i>`    |
| `get_setpoints(channel)`      | `:SOURce<n>:VOLTage?`, `:SOURce<n>:CURRent?`         | `:VOLTage?` → `P6V,Limit Voltage,5.0000V` (last number is used) |
| `set_output(enabled, channel)` | `:OUTPut:STATe <ch>,ON\|OFF` (`channel=None` → all channels) | `:OUTPut:STATe P6V,ON` / `:OUTPut:STATe ON` |
| `get_output(channel)`         | `:OUTPut:STATe? <ch>` → `ON\|OFF`                    | same                                       |
| `get_readings(channel)`       | `:MEASure:ALL? <ch>` → `V,I,P`; `:OUTPut:CVCC? <ch>` → `CV\|CC\|UR` | three `:MEASure:VOLTage\|CURRent\|POWEr?` queries; CV/CC inferred |
| `get_measurement(channel)`    | `:MEASure:VOLTage? <ch>` / `:CURRent?` / `:POWEr?`   | same, no channel on DP1116A                |
| `set_ovp(voltage, channel, enabled)` | `:OUTPut:OVP:VALue <ch>,<v>`, `:OUTPut:OVP:STATe <ch>,ON\|OFF` | `:OUTPut:OVP <ch>,<v>`, `:OUTPut:OVP:STATe <ch>,ON` |
| `set_ocp(current, channel, enabled)` | `:OUTPut:OCP:VALue ...`, `:OUTPut:OCP:STATe ...`  | `:OUTPut:OCP <ch>,<i>`                     |
| `get_protection(channel)`     | `...:VALue?`, `...:STATe?`, `:OUTPut:OVP\|OCP:QUES? <ch>` → `YES\|NO` | no trip query (`tripped: None`)  |
| `clear_protection(channel)`   | `:OUTPut:OVP:CLEAR <ch>`, `:OUTPut:OCP:CLEAR <ch>`   | not available → `ValueError`               |
| `set_tracking(mode, channel)` | DP800: `:OUTPut:TRACk <ch>,ON\|OFF`, `:SYSTem:TRACKMode SYNC\|INDE`; DP900/2000: `:OUTPut:TRACk ON\|OFF`, `:SYSTem:TMODe SYNC\|INDE` | DP1308A: `:OUTPut:TRACk P25V\|N25V\|OFF`; DP1116A/DP700: none |
| `set_pair(mode)`              | `:OUTPut:PAIR OFF\|SERies\|PARallel` (DP900/DP2000 only) | –                                      |
| `set_range(range)` / `get_range()` | `:OUTPut:RANGe P8V\|P20V\|P40V\|LOW\|HIGH` (DP811/DP813), `?` → `20V/10A` | DP1116A: `:OUTPut:RANGe 16V\|32V` |
| `set_sense(enabled, channel)` | DP800: `:OUTPut:SENSe <ch>,ON`; DP2000: `:SYSTem:SENSe <ch>,ON` | –                                    |
| `get_error()`                 | `:SYSTem:ERRor?` → `-113,"Undefined header..."` (`[:NEXT]` optional on DP900/2000) | no error queue query → code `None` |
| `set_beeper(enabled)`         | `:SYSTem:BEEPer:STATe ON\|OFF`                       | not supported                              |
| `set_remote(enabled)`         | `:SYSTem:REMote` / `:SYSTem:LOCal`                   | same                                       |
| `get_version()`, `get_options()`, `get_otp()` | `:SYSTem:VERSion?`, `*OPT?`, `:SYSTem:OTP?` | `*OPT?`, `:SYSTem:OTP?` only        |
| `reset()`, `self_test()`      | `*RST`, `*TST?` → `0`                                | `*TST?` → `Pass`                           |
| `get_state()`                 | setpoints, output, OVP/OCP per channel + tracking/pair/range | same                               |

Acquisition channel names accepted by `get_measurement`: `CH1`, `1`, `CH1:V`, `CH1:I`, `CH1:P`
(also `V`/`I`/`P` alone for CH1). Default quantity is voltage. Unparseable replies return NaN.

Negative channels (DP831 CH3, DP1308A N25V) are programmed with negative values, as in the
guides' OVP tables (`-1mV to -33V`). The driver accepts a positive magnitude and negates it.

## Per-model limits

Settable maxima (what the driver validates against) and OVP/OCP maxima. Rated power is
rated V × rated A.

| Model            | Ch | Rated        | Max set V / A | Max OVP / OCP | Notes                        | Source            |
|------------------|----|--------------|---------------|---------------|------------------------------|-------------------|
| DP832 / DP832A   | 1  | 30 V / 3 A   | 32 / 3.2      | 33 / 3.3      | tracking CH1+CH2             | DP800 T2-1, T2-2  |
|                  | 2  | 30 V / 3 A   | 32 / 3.2      | 33 / 3.3      |                              |                   |
|                  | 3  | 5 V / 3 A    | 5.3 / 3.2     | 5.5 / 3.3     |                              |                   |
| DP831 / DP831A   | 1  | 8 V / 5 A    | 8.4 / 5.3     | 8.8 / 5.5     |                              | DP800 T2-1, T2-2  |
|                  | 2  | 30 V / 2 A   | 32 / 2.1      | 33 / 2.2      | tracking CH2+CH3             |                   |
|                  | 3  | −30 V / 2 A  | −32 / 2.1     | −33 / 2.2     | negative                     |                   |
| DP822 / DP822A   | 1  | 20 V / 5 A   | 21 / 5.3      | 22 / 5.5      |                              | DP800 T2-1, T2-2  |
|                  | 2  | 5 V / 16 A   | 5.3 / 16.4    | 5.5 / 16.8    | remote sense                 |                   |
| DP821 / DP821A   | 1  | 60 V / 1 A   | 63 / 1.05     | 66 / 1.1      |                              | DP800 T2-1, T2-2  |
|                  | 2  | 8 V / 10 A   | 8.4 / 10.5    | 8.8 / 11      | remote sense                 |                   |
| DP813 / DP813A   | 1  | P8V: 8 V / 20 A; P20V: 20 V / 10 A | 8.4 / 21; 21 / 10.5 | 8.8 / 22; 22 / 11 | dual range, sense | DP800 T2-1, T2-2, `:OUTPut:RANGe` |
| DP811 / DP811A   | 1  | P20V: 20 V / 10 A; P40V: 40 V / 5 A | 21 / 10.5; 42 / 5.3 | 22 / 11; 44 / 5.5 | dual range, sense | DP800 T2-1, T2-2, `:OUTPut:RANGe` |
| DP711            | 1  | 30 V / 5 A   | 32 / 5.3      | 33 / 5.5      | RS-232 only                  | DP700 §1, `:APPLy`, `:OUTPut:OVP/OCP:VALue` |
| DP712            | 1  | 50 V / 3 A   | 53 / 3.2      | 55 / 3.3      | RS-232 only                  | DP700 §1, `:APPLy`, `:OUTPut:OVP/OCP:VALue` |
| DP932A / DP932U  | 1,2 | 32 V / 3 A  | 33.6 / 3.15   | 35.2 / 3.3    | tracking CH1+CH2, series/parallel pair | DP900 T4.9, T4.33 |
|                  | 3  | 6 V / 3 A    | 6.3 / 3.15    | 6.6 / 3.3     |                              |                   |
| DP932E           | 1,2 | 30 V / 3 A  | 31.5 / 3.15   | 33 / 3.3      | tracking, pair               | DP900 T4.9, T4.33 |
|                  | 3  | 6 V / 3 A    | 6.3 / 3.15    | 6.6 / 3.3     |                              |                   |
| DP2031           | 1,2 | 32 V / 3 A  | 32 / 3        | 35.2 / 3.3    | tracking, pair, sense        | DP2000 T4.9, T4.33 |
|                  | 3  | 6 V / 5 A    | 6 / 5         | 6.6 / 5.5     | optional 6 V/10 A range (DP2000-10A) not remotely switchable; then CH1/2 become 32 V/2 A | |
| DP1308A          | 1 (P6V)  | 6 V / 5 A  | 6.3 / 5.25  | 6.5 / 5.5     |                              | DP1308A `[SOURce:]`, `OUTPut:OVP/OCP` |
|                  | 2 (P25V) | 25 V / 1 A | 26.25 / 1.05 | 27 / 1.2     | tracking P25V+N25V           |                   |
|                  | 3 (N25V) | −25 V / 1 A | −26.25 / 1.05 | −27 / 1.2  | negative                     |                   |
| DP1116A          | 1  | 16V: 16 V / 10 A; 32V: 32 V / 5 A | 16.8 / 10.5; 33.6 / 5.25 | 35.2 / 11 (both) | dual range | DP1116A `APPLy`, `OUTPut:RANGe/OVP/OCP` |

DP800 Table 2-1 note [1]: non-A DP800 models with the high-resolution option share the A-model
ranges, so both rows are identical here (the non-A OVP/OCP minimum is 10 mV instead of 1 mV,
which does not affect validation).

## Quirks between families

- **Channel parameter**: `CH<n>` (also `P8V`/`P30V`/... aliases on DP800/DP700) vs `P6V|P25V|N25V`
  on DP1308A vs none on DP1116A. `INSTrument:NSELect` exists on every multi-channel model
  (and on the single-channel DP700, where it is a no-op).
- **SOURce prefix**: DP700/800/900/2000 accept `:SOURce<n>:VOLTage`; DP1308A/DP1116A only
  `[SOURce:]VOLTage` on the *selected* channel, so the driver selects first.
- **Setpoint query replies**: DP1308A returns `P6V,Limit Voltage,5.0000V`; DP1116A returns
  values with unit suffixes (`16.000V`, `6.000A`); the others return bare numbers.
- **Measurements**: `:MEASure:ALL?` (V,I,P in one reply) only on the modern tree. DP900/DP2000
  spell it `:MEASure[:SCALar]:ALL[:DC]?`; the short form is identical.
- **CV/CC**: `:OUTPut:CVCC?` (alias `:OUTPut:MODE?`) only on the modern tree; the driver infers
  CV/CC from readings on DP1308A/DP1116A.
- **Protection**: level leaf is `:VALue` on the modern tree, absent on DP1308A/DP1116A
  (`OUTPut:OVP <v>`). Trip query `:QUES?`/`:ALAR?` and `:CLEAR` exist only on the modern tree
  (DP900/DP2000 spell it `CLEar`; long form `CLEAR` matches both). DP900/DP2000 add
  `:OUTPut:OCP:DELay` (not used).
- **Tracking**: DP800 is per channel (`:OUTPut:TRACk CH2,ON`) with `:SYSTem:TRACKMode` and
  `:SYSTem:ONOFFSync`; DP900/DP2000 are global (`:OUTPut:TRACk ON`) with `:SYSTem:TMODe` and
  `:SYSTem:SYNC`; DP1308A takes the channel to track (`OUTPut:TRACk P25V`) and answers
  `TRACK_P25_ON`. DP700/DP1116A/DP821/DP822/DP811/DP813 have none.
- **Series/parallel pairing** (`:OUTPut:PAIR`) exists only on DP900/DP2000.
- **Remote sense**: `:OUTPut:SENSe` on DP800 (DP821/DP822 CH2, DP811/DP813), `:SYSTem:SENSe` on
  DP2000, none elsewhere.
- **Error queue**: `:SYSTem:ERRor?` on the modern tree; DP1308A/DP1116A have no error query at
  all (`get_error()` returns code `None`), and `*TST?` answers `Pass`/`Error` instead of `0`.
- **Beeper**: `:SYSTem:BEEPer[:STATe]` on the modern tree; DP1308A/DP1116A only have
  `SYSTem:BEEPer[:IMMediate] ON|OFF` (not driven).
- **Timer / delay / monitor / recorder / analyzer** are documented for DP800 (options on non-A
  models), DP700 (timer), DP900/DP2000 (timer) but are not implemented in this driver.

## Manual inconsistencies noticed

- DP800 Table 2-1 lists DP832/DP832A CH3 as `0V to -5.3V` while the channel token is `P5V` and
  the datasheet rates it +5 V/3 A; the driver treats CH3 as a positive channel.
- DP800 `:INSTrument:NSELect` is documented as "only applicable to multi-channel models", while
  the DP700 guide documents it for the single-channel DP711/DP712.
- DP900 `:SYSTem:TMODe` is described as "functions the same as `:OUTPut:TRACk[:STATe]`" but
  takes `SYNC|INDE`; the driver maps ON/OFF to `:OUTPut:TRACk` and SYNC/INDE to `:SYSTem:TMODe`.
- DP1308A/DP1116A guides show `*IDN?` with different spacing (`Rigol Technologies, DP1116A, ...`);
  the parser strips whitespace around each field.
