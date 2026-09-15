# Rigol DSG RF Signal Generators (DSG800 / DSG3000 / DSG3000B / DSG5000)

Driver: `server/equipment/rigol_rf_generator.py` — `RigolDSGBase` with thin
family classes `RigolDSG800`, `RigolDSG3000` (also covers the DSG3000B rows)
and `RigolDSG5000`. Equipment type `RF_SIGNAL_GENERATOR`, id prefix `rfgen_`,
readings model `RFGeneratorData`. Mock: `server/equipment/mock/mock_rf_generator.py`
(`MockRFGenerator`, resource `MOCK::RFGEN::0`, model `MockRFGEN-830`).

The rating row is picked from the model field of `*IDN?`; the class only sets
the default used before identification.

## Model table

| Model | Family | Frequency | Level setting range | Channels | IQ | Pulse mod. | Source |
|-------|--------|-----------|---------------------|----------|----|------------|--------|
| DSG815 | DSG800 | 9 kHz – 1.5 GHz | -110 … +20 dBm | 1 | option DSG800-IQ | option DSG800-PUM | DSG800 Programming Guide `[:SOURce]:FREQuency`/`:LEVel`; DSG800 Data Sheet |
| DSG821 / DSG821A | DSG800 | 9 kHz – 2.1 GHz | -110 … +20 dBm | 1 | option | option | DSG800 Data Sheet |
| DSG830 | DSG800 | 9 kHz – 3 GHz | -110 … +20 dBm | 1 | option | option | DSG800 Programming Guide |
| DSG836 / DSG836A | DSG800 | 9 kHz – 3.6 GHz | -110 … +20 dBm | 1 | option | option | DSG800 Data Sheet |
| DSG3030 | DSG3000 | 9 kHz – 3 GHz | -140 … +25 dBm | 1 | option IQ-DSG3000 | standard | DSG3000 Programming Guide + Data Sheet |
| DSG3060 | DSG3000 | 9 kHz – 6 GHz | -140 … +25 dBm | 1 | option | standard | DSG3000 Programming Guide + Data Sheet |
| DSG3065B | DSG3000B | 9 kHz – 6.5 GHz | -130 … +27 dBm | 1 | no | standard | DSG3000B Programming Guide model table |
| DSG3065B-IQ | DSG3000B | 9 kHz – 6.5 GHz | -130 … +27 dBm | 1 | yes (50 MHz – 6.5 GHz) | standard | DSG3000B Programming Guide |
| DSG3136B | DSG3000B | 9 kHz – 13.6 GHz | -130 … +27 dBm | 1 | no | standard | DSG3000B Programming Guide |
| DSG3136B-IQ | DSG3000B | 9 kHz – 13.6 GHz | -130 … +27 dBm | 1 | yes | standard | DSG3000B Programming Guide |
| DSG5122 / 5124 / 5126 / 5128 | DSG5000 | 9 kHz – 12 GHz | -30 … +25 dBm | 2 / 4 / 6 / 8 | no | option DSG5000-PUL | DSG5000 Programming Guide "Content Conventions", `[:SOURce][:RF]:LEVel` |
| DSG5202 / 5204 / 5206 / 5208 | DSG5000 | 9 kHz – 20 GHz | -30 … +25 dBm | 2 / 4 / 6 / 8 | no | option | DSG5000 Programming Guide |

Notes on the table:

* The task brief listed "DSG3030B/DSG3060B". No such models exist in the
  manuals; the DSG3000B family is DSG3065B and DSG3136B (each with an -IQ
  variant). Those are the rows implemented.
* DSG3000: the programming guide gives `:LEVel` a range of -140 … +20 dBm, the
  data sheet a *setting* range up to +25 dBm (1 MHz – 3 GHz). The driver uses
  the wider data-sheet limit so it does not refuse settings the front panel
  accepts; the instrument still clips per its own frequency-dependent table.
* Setting ranges, not specified ranges: e.g. the DSG800 guarantees only
  +13 dBm but accepts +20 dBm.

## LabLink command table

| Command | Parameters | SCPI |
|---------|------------|------|
| `set_frequency` / `get_frequency` | `frequency` Hz, `channel` | `[:SOURce][:RF<n>]:FREQuency` |
| `set_frequency_step` | `step` Hz | `[:SOURce]:FREQuency:STEP` (not DSG5000) |
| `set_level` / `get_level` | `level`, `unit` dBm/dBmV/dBuV/V/W, `channel` | `[:SOURce][:RF<n>]:LEVel <v>[unit]`; query always dBm |
| `set_level_step` | `step_db` | `[:SOURce]:LEVel:STEP` (not DSG5000) |
| `set_level_unit` / `get_level_unit` | `unit` | `:UNIT[:RF<n>]:POWer DBM\|DBMV\|DBUV\|V\|W` |
| `set_output` / `get_output` | `enabled`, `channel` | `:OUTPut[:STATe]`; DSG5000 `:RF<n>:OUTPut:STATe` |
| `set_all_outputs` | `enabled` | `:SOURce:RFALl:OUTPut:STATe` (DSG5000), loop elsewhere |
| `set_alc` / `get_alc` | `enabled` or `mode` OFF/ON/AUTO | `[:SOURce]:LEVel:ALC:MODE` — **DSG3000 only**; ValueError elsewhere, `get_alc` → None |
| `set_modulation` / `get_modulation` | `type` AM/FM/PM/PULSE/IQ, `enabled`, `master`, params below | see below |
| — AM | `depth` %, `frequency`, `source` INT/EXT, `waveform` SINE/SQUARE | `:AM:DEPTh / :AM:FREQuency / :AM:SOURce / :AM:WAVEform / :AM:STATe` |
| — FM | `deviation` Hz, `frequency`, `source`, `waveform` | `:FMPM:TYPE FM` (not DSG5000), `:FM:DEViation / :FM:FREQuency / :FM:SOURce / :FM:WAVEform / :FM:STATe` |
| — PM | `deviation` rad, `frequency`, `source`, `waveform` | `:FMPM:TYPE PM`, `:PM:DEViation …` |
| — PULSE | `period` s, `width` s, `source`, `polarity` NORMAL/INVERSE, `mode` SINGLE/TRAIN | `:PULM:PERiod / :PULM:WIDTh / :PULM:SOURce / :PULM:POLarity / :PULM:MODE / :PULM:STATe` |
| — IQ | `source` INT/EXT | `:IQ:MODe`, `:IQ:MODe:STATe` |
| `set_modulation_master` / `get_modulation_master` | `enabled` | `[:SOURce][:RF<n>]:MODulation:STATe` |
| `set_lf_output` | `enabled`, `frequency`, `level`, `shape` | `[:SOURce]:LFOutput:FREQuency/LEVel/SHAPe/STATe` (not DSG5000) |
| `set_sweep` / `get_sweep` | `mode` OFF/FREQ/LEVEL/BOTH, `start_frequency`, `stop_frequency`, `start_level`, `stop_level`, `points` 2..65535, `dwell` s, `sweep_type` STEP/LIST, `spacing` LIN/LOG, `shape` TRIANGLE/RAMP, `direction` FWD/REV, `continuous` | `:SWEep:STATe OFF\|FREQuency\|LEVel\|LEVel,FREQuency`, `:SWEep:TYPE`, `:SWEep:MODE CONTinue\|SINGle`, `:SWEep:STEP:STARt/STOP:FREQuency/LEVel`, `:SWEep:STEP:POINts/DWELl/SPACing/SHAPe`, `:SWEep:DIRection` |
| `execute_sweep` | `channel` | `:SWEep:EXECute` |
| `trigger` | `what` SWEEP/PULSE/IQ/ALL | `:TRIGger:SWEep:IMMediate`, `:TRIGger:PULSe:IMMediate` (DSG5000 `:TRIGger:RF<n>:PULM:IMMediate`), `:TRIGger:IQ:IMMediate`, `*TRG` |
| `get_readings` | `channel` | → `RFGeneratorData` (frequency, level dBm, output, first enabled modulation + parameters, ALC) |
| `get_measurement` | `channel` = `FREQ`, `LEVEL` (default; also `CH1`, `1`, ``), `OUTPUT`, or `CH<n>:FREQ` on DSG5000 | acquisition-engine hook, `{"value", "unit", "quantity", "channel"}` |
| `get_measurements` | `channel` | `{frequency, level, output_enabled}` |
| `get_state` | `channel` | frequency, level, unit, output, modulation master, ALC, every modulation, sweep |
| `preset` / `reset` | — | `:SYSTem:PRESet`; `reset` sends `*RST` on DSG3000/DSG5000 and `:SYSTem:PRESet` elsewhere |
| `get_error` | — | `:SYSTem:ERRor?` best effort (undocumented, see quirks) |
| `clear_errors` | — | `*CLS` on DSG3000/DSG5000 only; returns False elsewhere |
| `get_options` | — | `*OPT?` (DSG3000 only) |

`set_output(False)` is what `manager.disconnect_device()` calls on disconnect.

## Quirks and unverifiable items

* **Query formats differ by family.** DSG800 and DSG3000B return "Number+Unit"
  strings (`:FREQ?` → `4.00000000MHz`, `:AM:FREQ?` → `20.00000kHz`,
  `:PULM:PER?` → `1.000000000s`); DSG3000 and DSG5000 return plain numbers
  (`4000000`). `parse_si()` handles both and is case-sensitive for the SI
  prefix (`mHz` = milli, `MHz` = mega — both appear in the guides).
* `:LEVel?` returns dBm regardless of `:UNIT:POWer`. The driver validates
  levels in dBm after converting dBmV/dBuV/V/W (50 Ω).
* **`:SYSTem:ERRor?` is not documented in any of the four guides.**
  `get_error()` tries it and returns `code=None` on failure. `*TST?` is not
  documented either; `run_self_test()` returns None.
* DSG800 and DSG3000B document only `*IDN?` and `*TRG` as IEEE-488.2 commands
  (no `*RST`, `*CLS`, `*OPC?`); DSG3000 and DSG5000 document `*RST`/`*CLS`.
* ALC (`:LEVel:ALC:MODE OFF|ON|AUTO`) exists only in the DSG3000 guide. The
  DSG800/DSG3000B/DSG5000 have no remote ALC control, so `RFGeneratorData.alc_enabled`
  is None for them.
* `:FMPM:TYPE FM|PM` selects which of FM/ΦM is active (DSG800/3000/3000B); the
  driver sends it before configuring FM or PM. The DSG5000 has no such command.
* DSG5000: every SOURce command carries `[:RF<n>]`; `:UNIT:RF<n>:POWer`;
  `:RFALl:*` addresses all channels. It has no `:FREQuency:STEP`, `:LEVel:STEP`,
  `:LFOutput` or `:IQ` subsystem.
* Pulse modulation on the DSG800 needs the DSG800-PUM option (train: DSG800-PUG);
  on the DSG5000 the DSG5000-PUL option; IQ on the DSG800 needs DSG800-IQ, on
  the DSG3000 IQ-DSG3000. The driver cannot detect missing options except via
  `*OPT?` on the DSG3000; the commands are simply ignored by the instrument.
* Sweep dwell: 20 ms – 100 s on DSG800/3000/3000B, 5 ms minimum on DSG5000 (data
  sheet); the driver accepts 5 ms as the lower bound.
* Return strings for `:SWEep:MODE?` (`CONT`/`SING`), `:PULM:POLarity?`
  (`NORMAL`/`INVERSE`) and `:AM:SOURce?` (`INT`/`EXT`) are taken from the
  DSG800 examples; other families may differ in length and are normalised
  by prefix.
