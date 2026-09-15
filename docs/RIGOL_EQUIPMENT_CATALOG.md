# Rigol Equipment Catalogue and LabLink Compatibility

Scraped from <https://www.rigolna.com/support/downloads/> on 2026-09-15. The page embeds its whole
catalogue inline, grouped by document type. Files are downloaded to `~/Manuals/Rigol/<Family>/<Type>/`
and indexed in:

- `docs/rigol/downloads_catalog.json` — every document (title, type, URL, local path)
- `docs/rigol/programming_guide_inventory.json` — per programming guide: models named, `*IDN?` example,
  interfaces, SCPI subsystems, and a per-class command probe matrix

| Document type | Count |
|---------------|-------|
| Programming guides | 75 (74 unique; the DSA832E guide is the DSA800E guide) |
| User manuals | 178 |
| Service manuals | 74 |
| Datasheets | 71 |
| Specifications | 23 |

All Rigol instruments identify as `Rigol Technologies,<model>,<serial>,<firmware>` (older firmware
upper-cases the vendor). USB VID is `0x1AB1` throughout. Every family from DG1000Z onward supports
USB-TMC and LAN (VXI-11, most also raw socket on port 5555 and LXI); GPIB and RS-232 vary by model.

## How LabLink classifies and drives them now

`server/discovery/vendor_models.py` maps model prefixes to a device type before the loose keyword rules
run, so `DSA815` is a spectrum analyzer rather than a scope, and `DHO804`, `MHO5074`, `DM858`,
`DNA6000` classify at all. `server/equipment/manager.py` maps model strings to drivers.

Equipment types added on 2026-09-15 so nothing lands in `unknown`: `spectrum_analyzer` (now in the shared
enum too), `rf_signal_generator` (DSG), `vector_network_analyzer` (DNA6000, RSA3000N/5000N) and
`data_acquisition` (M300). They exist in the shared, client and discovery enums, the connect dialog,
the discovery API's supported-type list and the default safety limits.

## Compatibility matrix

Legend for **Command tree**: guides in the same group answer the same core commands (verified by
probing each guide's text for the canonical commands LabLink's drivers use; see the inventory JSON).

### Oscilloscopes (`EquipmentType.OSCILLOSCOPE`)

| Family (guide) | Models | Command tree | LabLink today | Action |
|---|---|---|---|---|
| DS1000Z | DS1054Z, DS1074Z(-S), DS1104Z(-S) | **Modern SCPI** (`:WAV:DATA?`, `:WAV:PRE?`, `:MEAS:ITEM`, `:TIM:MAIN:SCAL`) | `RigolDS1104` — now aliased to the whole 4-channel family | done |
| DS1000Z-E | DS1202Z-E | Modern SCPI, 2 channels | none (DS1104 driver assumes 4 ch) | add a 2-channel subclass |
| MSO2000A / DS2000A | MSO2072A…MSO2302A(-S), DS2072A…DS2302A | Modern SCPI + `BUS<n>`, `CALCulate` | `RigolMSO2072A` — now aliased to the family | done |
| DS/MSO4000(E) | DS4014E, DS4024E, MSO4000 | Modern SCPI (same shape as DS2000A) | none | alias to MSO2072A-style driver after channel-count check |
| DS6000 | DS6062, DS6064, DS6102, DS6104 | Modern SCPI | none | same |
| MSO5000 / MSO5000-E | MSO5072…MSO5354, MSO5152-E | Modern SCPI + `DVM`, `COUNter`, `POWer`, `HISTogram`, `SEARch`, `BODeplot` | none | **priority**: one `RigolModernScope` base + model table |
| MSO7000 / DS7000 | MSO/DS7014…7054 | Modern SCPI (MSO5000 superset) | none | same base |
| MSO8000 / MSO8000A | MSO8064…8204 | Modern SCPI + `JITTer`, `EYE`, `CLOCk` | none | same base |
| DS8000-R | DS8034-R, DS8104-R, DS8204-R | Modern SCPI (rack) | none | same base |
| DHO800 / DHO900 | DHO802…DHO924S | Modern SCPI + `AUToset`, `SAVE`, `NAVigate` | none | **priority** (most common current bench scope) |
| DHO1000 / DHO4000 ("DHO" guide) | DHO1072…DHO4804 | Modern SCPI | none | same base |
| DHO/MHO5000 | DHO/MHO5xxx | Modern SCPI | none | same base |
| MHO900, MHO98, MHO2000 | mixed-signal DHO variants | Modern SCPI | none | same base |
| DS70000 / DS80000 | high-end | Modern SCPI + `COMPliance`, `EYE` | none | same base, later |
| DS1000D / DS1000E | DS1052E, DS1102E, DS1052D, DS1102D | **Legacy** (`:MEAS:VPP?`, `:TIM:SCAL`, no `:WAV:PRE?`) | `RigolDS1102D` | alias DS1052E/DS1102E/DS1052D |
| DS1000B | DS1074B, DS1104B, DS1204B | Legacy variant (has `:WAV:PRE?`, `KEY` commands) | none | low priority |
| DS1000CA / DS1000C / DS1000M | DS1062CA…DS1302CA | Legacy (proprietary `KEY`, `INFO`, `BEEP`) | none | low priority |

The modern tree is close enough that one base class with a per-model table (channel count, digital
channels, max sample rate, memory depth, bandwidth) covers 14 of the 17 scope guides. The existing
`RigolDS1104` already speaks it; refactoring it into that base is the recommended first step.

### Programmable DC power supplies (`EquipmentType.POWER_SUPPLY`)

| Family | Models | Command tree | LabLink today | Action |
|---|---|---|---|---|
| DP800 | DP811(A), DP813(A), DP821(A), DP822(A), DP831(A), DP832(A) | **DP SCPI**: `:APPLy`, `:OUTPut`, `:MEASure:ALL?`, `:INSTrument:NSELect`, `:OUTPut:OVP/OCP`, `:TIMEr`, `:RECorder`, `:MONItor` | none | **priority**: `RigolDPBase` + models |
| DP700 | DP711, DP712 | DP SCPI subset (RS-232 only) | none | same base |
| DP900 | DP932A/E… | DP SCPI + `:ANALyzer` | none | same base |
| DP2000 | DP2031… | DP SCPI + `:ANALyzer` | none | same base |
| DP1308A | DP1308A | Early DP SCPI (`:APPLy`, `:INSTrument`) | none | alias after check |
| DP1116A | DP1116A | Early DP SCPI (`:APPLy`, `:OUTPut`, `STORe/RECAll`) | none | alias after check |

All DP guides share `:APPLy CH<n>,<volt>,<curr>`, `:OUTPut CH<n>,ON|OFF`, `:MEASure[:VOLTage|CURRent|POWer|ALL]? CH<n>`
and OVP/OCP protection, which is exactly what the BK power-supply driver exposes to LabLink (`set_voltage`,
`set_current`, `set_output`, `get_readings`). One base class covers all six guides.

### Function / arbitrary waveform generators (`EquipmentType.FUNCTION_GENERATOR`)

No LabLink driver exists for this type yet; the client/UI already knows the enum.

| Family | Models | Command tree | Action |
|---|---|---|---|
| DG800, DG900, DG1000Z, DG2000 | DG811…DG832, DG952…DG992, DG1022Z…DG1062Z, DG2052…DG2102 | **DG SCPI**: `:SOURce<n>:APPLy:<shape>`, `:SOURce<n>:FREQuency/VOLTage/PHASe`, `:OUTPut<n>`, `:SOURce<n>:BURSt/MOD/SWEep`, `:COUNter` | **priority**: `RigolDGBase` covers all four guides |
| DG4000 | DG4062…DG4202 | Older DG SCPI (`:SOURce<n>:APPLy` present, `:TRACe` arb upload) | same base with quirks |
| DG5000 | DG5071…DG5352 | Older DG SCPI, `DIGItal` pattern option | later |
| DG800 Pro / DG900 Pro, DG5000 Pro, DG6000 | current "Pro" platform | New DG SCPI (`:SOURce<n>:...`, `INITiate`, `SYNChro`, `HCOPy`) | second base class |
| DG70000 | DG70004… | AWG-centric (`AWGControl`, `WLISt`, `SLISt`) | specialist, later |
| DG1000 (DG1022, DG1022A) | legacy | Non-SCPI-ish (`APPLy:SINusoid`, `FREQ`, `OUTP`; USB only) | low priority |

### RF signal generators (`EquipmentType.RF_SIGNAL_GENERATOR`)

| Family | Models | Command tree | Action |
|---|---|---|---|
| DSG800 | DSG815, DSG830 | `:SOURce:FREQuency`, `:SOURce:LEVel`, `:OUTPut`, AM/FM/ΦM, pulse | new `RigolDSGBase`; consider an `RF_GENERATOR` equipment type |
| DSG3000 / DSG3000B | DSG3030…DSG3136B | same + IQ | same base |
| DSG5000 | DSG5xxx | same | same base |

### Spectrum, real-time and vector network analyzers (`EquipmentType.SPECTRUM_ANALYZER`)

No driver exists; the discovery layer already has the type.

| Family | Models | Command tree | Action |
|---|---|---|---|
| DSA800 / DSA800E | DSA815, DSA832(E), DSA875 | **SA SCPI**: `:SENSe:FREQuency:CENTer/SPAN`, `:BANDwidth`, `:TRACe:DATA?`, `:CALCulate:MARKer`, `:UNIT:POWer`, `:FORMat:TRACe:DATA`, TG via `:OUTPut`/`:SOURce:POWer` | **priority**: `RigolSABase` |
| DSA700 | DSA705, DSA710 | SA SCPI (no TG) | same base |
| RSA3000 / RSA3000E | RSA3015E…RSA3045(-TG) | SA SCPI + `INSTrument:SELect` (GPSA/RTSA modes) | same base + mode select |
| RSA5000 | RSA5032, RSA5065(-TG) | same as RSA3000 | same base |
| RSA800 | RSA814… | same, plus option guides (ADM, EMI, PNOISE, VSA) | same base |
| RSA6000 | RSA6085, RSA6140, RSA6265 | same, plus ADM/BLE/EMI/LoRa/PNOISE/PULSE/VSA option guides | same base |
| DSA1000 / DSA1000A | DSA1030(A) | SA SCPI, older (`:FREQuency:CENTer`, `:TRACe`, no `:SENSe` prefix) | later |
| RSA3000N / RSA5000N (VNA) | RSA3015N…RSA5065N | VNA SCPI (`:CALCulate`, `:SENSe`, S-parameters) | `VECTOR_NETWORK_ANALYZER` driver |
| DNA6000 / DNA6000-R | vector network analyzers | VNA SCPI (`TAS`, `INITiate`) | separate driver |

### Electronic loads (`EquipmentType.ELECTRONIC_LOAD`)

| Family | Models | Command tree | LabLink today | Action |
|---|---|---|---|---|
| DL3000 | DL3021, DL3021A, DL3031, DL3031A | `:SOURce:CURRent/VOLTage/RESistance/POWer:LEVel:IMMediate`, `:SOURce:INPut:STATe`, `:SOURce:FUNCtion`, `:MEASure:VOLTage/CURRent/POWer?`, BATTery, LIST | `RigolDL3021A` | make limits a model table (DL3031A: 60 A / 350 W) and alias DL3021/DL3031(A) |

### Digital multimeters (`EquipmentType.MULTIMETER`)

| Family | Models | Command tree | LabLink today | Action |
|---|---|---|---|---|
| DM3058 / DM3058E, DM3068 | | RIGOL set (+ Agilent 34401A / Fluke 45 sets) | `RigolDM3058`, `RigolDM3058E`, `RigolDM3068` | done (see `docs/RIGOL_DMM.md`) |
| DM858 / DM858E | 5½-digit touchscreen | **Different**: standard SCPI DMM tree (`CONFigure`, `SENSe`, `READ?`, `DATA`, `CALCulate`), no RIGOL `:FUNCtion`/`:RATE` set | none | new `RigolDM858` driver (looks like the DM3068 Agilent-compatible set) |

### Data acquisition / switch

| Family | Models | Command tree | Action |
|---|---|---|---|
| M300 | M300 mainframe + MC3xxx modules | Agilent 34970A-style (`ROUTe`, `SENSe`, `CONFigure`, `DATA`, `MEASure`) | `DATA_ACQUISITION` type added; driver `RigolM300` |

## Implementation status (2026-09-15)

All families in the matrix now have drivers except the legacy DS1000B/DS1000CA scopes, DG70000 and legacy
DG1000 generators (deliberately skipped, see the family docs). Drivers: `rigol_power_supply.py`,
`rigol_modern_scope.py`, `rigol_function_generator.py`, `rigol_spectrum_analyzer.py`, `rigol_rf_generator.py`,
`rigol_multimeter_dm858.py`, `rigol_electronic_load.py`, `rigol_vna.py`, `rigol_daq.py`. Registration is via
`MODEL_KEYWORDS` on each class and `KEYWORD_DRIVER_CLASSES` in `server/equipment/manager.py`.

## Original implementation order (for reference)

1. **Rigol DP power supplies** (DP800 first). Six guides, one command tree, and LabLink's power-supply
   UI, safety limits, profiles and acquisition hooks already exist for the BK drivers to copy from.
2. **Modern Rigol scope base class** covering DHO800/900, MSO5000, MSO7000, DS1000Z-E, DS/MSO4000,
   DS6000, MSO8000, DS8000-R and the DHO/MHO 1000–5000 lines. Refactor `RigolDS1104` onto it.
3. **DG function generators** (DG800/900/1000Z/2000). Requires the first `FUNCTION_GENERATOR` driver
   and a generator control panel/commands (`set_waveform`, `set_frequency`, `set_amplitude`, `set_output`).
4. **DSA/RSA spectrum analyzers** (DSA815 first). Requires trace-data acquisition (`:TRACe:DATA?`
   returns ASCII floats) and a spectrum display; the existing waveform plumbing can carry a trace.
5. **DM858** DMM, **DL3000** model table, **DSG** RF generators, then VNAs and M300.

## Download results

420 of 421 documents downloaded (1.9 GB) into 78 family folders under `~/Manuals/Rigol/`. The only
failure is the vendor's own link for the DS1000D/E User's Guide, which returns HTTP 400; the DS1000D/E
programming and service guides did download. Generic documents (declassification guides, accessory
manuals, solution datasheets) live in `_General/` and `_Accessories/`.

## USB product IDs harvested from the manuals

User guides quote example VISA resource strings. These PIDs were added to
`server/discovery/usb_hardware_db.py` (VID `0x1AB1`):

| PID | Family | Source |
|-----|--------|--------|
| 0x0642 | DG800, DG900, DG1000Z, DG2000 | four user guides agree |
| 0x0960 | DSA700, DSA800, DSA800E | DSA700 and DSA800 user guides |
| 0x0992 / 0x099C / 0x0993 | DSG3000 / DSG3000B / DSG5000 | user guides |
| 0x0E10 | DP1116A | user guide (serial in the example is a placeholder) |
| 0x0C80 | M300 | user guide |
| 0x0C94 | DM3068 | user guide (already present) |
| 0x04CE | DS1000Z | user guide (already present) |
| 0x0E11 | DL3000 **and** DP800 | both guides quote the same PID; the table keeps DL3021A, DP800 relies on `*IDN?` |
| 0x0640 | DG5000 (table says DG4000) | both guides quote the same PID |

Not added: DSG800 quotes `0x6666` and the RSA3000/RSA5000 guides quote `0xA4A9`, both of which look like
screenshot placeholders. Families whose guides show no resource string (DHO, MHO, MSO5000/7000/8000,
DP700/800/900/2000, DM3058, RSA6000, DNA) are still identified reliably through `*IDN?`.

## Gaps and caveats found while scraping

- Rigol's page serves several guides as `file.pdf`/`file.zip` with no descriptive name; the catalogue
  JSON keeps the page title so the local files are named sensibly.
- The DSA832E programming guide link is byte-identical to the DSA800E guide.
- `DG4000`, `DG5000`, `DS6000` and `DM3068` guides are CHM help files inside ZIPs; extract with `7z x`.
- Several user guides have damaged page trees (MuPDF "cannot find page" warnings) but still extract.
- Programming guides never state USB PIDs; see the harvest table above.
