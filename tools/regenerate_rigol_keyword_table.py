"""Freeze what the Rigol manuals say about the keywords we send.

The manuals live outside the repo. This reads them once and writes the
documented spelling of every keyword each driver actually uses, so the
test can check against the manual without the manual being mounted.
"""
import collections
import json
import os
import re
import sys

ROOT = "//wsl.localhost/Ubuntu/home/stevecap/Manuals"
MANUALS = f"{ROOT}/Rigol/_text_extracted"
BK_MANUALS = f"{ROOT}/BK/_text_extracted"
OUT = "tests/unit/data/rigol_documented_keywords.json"

COVERAGE = {
    "rigol_electronic_load.py": ["DL3000"],
    "rigol_power_supply.py": ["DP800", "DP900", "DP2000", "DP1308A",
                              "DP1116A", "DP700"],
    "rigol_multimeter.py": ["DM3058", "DM3068"],
    "rigol_multimeter_dm858.py": ["DM858"],
    "rigol_function_generator.py": ["DG1000Z", "DG2000", "DG4000", "DG5000",
                                    "DG6000", "DG800", "DG900", "DG5000PRO",
                                    "DG800PRO"],
    # Exactly the families _LEGACY_KEYWORDS gives this class: DS1054Z /
    # DS1074Z / DS1104Z, DS1052D/E and DS1102D/E, and the
    # MSO2072A/DS2072A group. Not DS1000B, DS1000CA, DS6000 or MSO4000
    # -- those were a guess of mine, and the DS1000B guide spells the
    # single-trigger command :SINGLe where every model this driver
    # actually drives spells it :SINGle. Widening the map beyond what a
    # driver claims does not add coverage, it invents disagreement.
    "rigol_scope.py": ["DS1000Z", "DS1000D", "DS2000A"],
    "rigol_modern_scope.py": ["MSO5000", "MSO7000", "MSO8000", "DS8000",
                              "DS70000", "DS80000", "DHO", "DHO800",
                              "DHO_MHO5000", "MHO900", "MHO2000"],
    "rigol_spectrum_analyzer.py": ["DSA800", "DSA1000", "DSA700", "RSA3000",
                                   "RSA5000"],
    "rigol_rf_generator.py": ["DSG3000", "DSG800", "DSG5000", "DSG3000B"],
    "rigol_vna.py": ["DNA6000", "RSAN"],
    "rigol_daq.py": ["M300"],
}

#: IEEE 488.2 common commands. Spelled with a leading * and always
#: three letters; they are not in the SCPI tree and have no long form.
COMMON = {"IDN", "RST", "CLS", "OPC", "OPT", "TST", "TRG", "WAI",
          "ESR", "ESE", "SRE", "STB", "PSC", "RCL", "SAV"}

# Colon-joined keywords, with or without a leading colon: the Rigol
# drivers write ":OUTP:PROT:CLE", the B&K ones "OUTP:PROT:CLE".
# Matching only the first form made the first B&K audit see 2 keywords
# instead of 23, and report a clean bill of health it had not earned.
#   :KEYWORD[:KEYWORD...]   -- Rigol style, and single-word commands
#                              like :RUN, :STOP, :CLE, :AUT
#   KEYWORD:KEYWORD[...]    -- B&K style, no leading colon
# The second alternative demands an inner colon; without that it would
# match every capitalised word in the file.
LITERAL = re.compile(
    r'["\']('
    r'[:*][A-Za-z][A-Za-z0-9]*(?::[A-Za-z][A-Za-z0-9]*)*'
    r'|[A-Za-z][A-Za-z0-9]*(?::[A-Za-z][A-Za-z0-9]*)+'
    r')\??["\' ]')
KEYWORD = re.compile(r"^[A-Za-z]+$")
# A command path as a guide prints it. Both forms: Rigol leads with a
# colon (":SOURce:FUNCtion"), B&K often does not ("CONF:CURR:AC",
# "MEASure:VOLTage:AC"). Reading only the colon-led form left AC out of
# the B&K table and made a perfectly good keyword look like a
# truncation of ACQuire.
PATH = re.compile(
    r"(?:^|[\s(])(:?[A-Za-z][A-Za-z0-9\[\]]*(?::[A-Za-z][A-Za-z0-9\[\]]*){1,6}\??)")


def caps(word):
    return "".join(c for c in word if c.isupper())


def driver_keywords(path):
    """Keywords we send, and whether each came from a *common command."""
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    for m in LITERAL.finditer(src):
        command = m.group(1).split()[0]
        common = command.startswith("*")
        for part in command.lstrip(":*").rstrip("?").split(":"):
            part = part.strip("[]")
            if KEYWORD.match(part) and len(part) >= 2:
                yield part, common


def documented(families, manuals=None):
    """Mnemonics from the guides. families=None means every guide in
    that folder, which is how B&K is read: a series manual covers its
    siblings (the 8600 guide documents 8601, 8602, 8610 and 8614) and
    the registry names families the filenames do not."""
    manuals = manuals or MANUALS
    found = collections.defaultdict(set)
    allcaps = set()
    used = []
    for name in sorted(os.listdir(manuals)):
        if not name.endswith(".txt"):
            continue
        if families is not None and name.split("__", 1)[0] not in families:
            continue
        used.append(name)
        guide = os.path.join(manuals, name)
        with open(guide, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for path in PATH.findall(text):
            for part in (q.strip("[]") for q in
                         path.lstrip(":").rstrip("?").split(":")):
                if not KEYWORD.match(part) or len(part) < 2:
                    continue
                if re.match(r"^[A-Z]", part) and re.search(r"[a-z]", part):
                    found[caps(part).upper()].add(part)
                    found[part.upper()].add(part)
                elif part.isupper():
                    allcaps.add(part)
    for word in allcaps:
        found.setdefault(word, set()).add(word)
    return found, used


def main():
    if not os.path.isdir(MANUALS):
        print(f"manuals not reachable at {MANUALS}")
        return 1

    table = {}

    bk_docs, bk_guides = ({}, [])
    if os.path.isdir(BK_MANUALS):
        bk_docs, bk_guides = documented(None, BK_MANUALS)
    for driver in ("bk_scpi.py", "bk_power_supply.py",
                   "bk_electronic_load.py"):
        path = os.path.join("server/equipment", driver)
        if not os.path.exists(path) or not bk_guides:
            continue
        entries = {}
        for word, is_common in sorted(set(driver_keywords(path))):
            up = word.upper()
            if is_common and up in COMMON:
                entries[word] = {"common": True}
                continue
            entries[word] = {
                "documented": sorted(bk_docs.get(up, [])),
                "truncates": sorted({m for sps in bk_docs.values() for m in sps
                                     if m.upper().startswith(up)
                                     and len(up) < len(m)})[:6],
            }
        table[driver] = {"guides": bk_guides, "families": ["B&K SCPI"],
                         "keywords": entries}

    for driver, families in sorted(COVERAGE.items()):
        path = os.path.join("server/equipment", driver)
        if not os.path.exists(path):
            continue
        docs, used = documented(set(families))
        entries = {}
        for word, is_common in sorted(set(driver_keywords(path))):
            up = word.upper()
            if is_common and up in COMMON:
                entries[word] = {"common": True}
                continue
            spellings = sorted(docs.get(up, []))
            truncates = sorted({m for sps in docs.values() for m in sps
                                if m.upper().startswith(up) and len(up) < len(m)})
            entries[word] = {
                "documented": spellings,
                "truncates": truncates[:6],
            }
        table[driver] = {
            "guides": used,
            "families": sorted(families),
            "keywords": entries,
        }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=1, sort_keys=True)
        f.write("\n")
    total = sum(len(v["keywords"]) for v in table.values())
    print(f"wrote {OUT}: {len(table)} drivers, {total} keywords, "
          f"{sum(len(v['guides']) for v in table.values())} guides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
