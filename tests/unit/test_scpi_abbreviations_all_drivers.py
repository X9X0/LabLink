"""No driver may abbreviate a keyword it also spells out in full.

The rule, from the DL3000 Programming Guide 1-5 and identical across
every SCPI instrument we talk to:

    The letters in the commands are case-insensitive. ... If
    abbreviation is used, you must enter all the uppercase letters that
    exist in the command syntax.

So a keyword has exactly two legal spellings -- the whole mnemonic, or
its uppercase letters -- and nothing in between. ``:SYST`` and
``:SYSTem`` are both the error subsystem; ``:SYSTe`` is not a command.

Checking that against a manual needs the manual, and we drive fifteen
instruments. What does not need one: when a driver writes a keyword in
mixed case it has told us the full mnemonic, and any shorter spelling
of that same keyword, in the same slot, must then be exactly the
uppercase run.

Be clear about how weak that is. It would NOT have caught the bug that
prompted it. :MEASure:DISChargingTime? was written :MEAS:DISC? and the
long form appeared nowhere in the driver, so there was nothing to
compare against -- reverting the fix and running this file still gives
a clean pass. It catches a driver that contradicts itself, which is a
real thing that happens when one command is added beside another, and
nothing more.

The check that does catch it is the per-command table in
test_scpi_abbreviations.py, which pins each keyword against the
spelling the DL3000 guide prints. That one fails the moment DISC comes
back. Extending that protection to the other drivers means a table per
instrument, sourced from its manual, and those manuals are not in the
repo -- so for now those drivers have this cross-check and the bench.
"""

import glob
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

DRIVERS = sorted(glob.glob(os.path.join(
    os.path.dirname(__file__), "../../server/equipment/*.py")))

#: A string literal that looks like a SCPI command: starts with : or *.
LITERAL = re.compile(r'["\']([:*][A-Za-z0-9:*?\[\]]{2,}[^"\']*)["\']')
KEYWORD = re.compile(r"^[A-Za-z]+$")


def keywords_in(source: str):
    """Every keyword of every SCPI-looking literal in a driver."""
    for _slot, word in slotted_keywords(source):
        yield word


def slotted_keywords(source: str):
    """Each keyword with the slot it occupies in its command path.

    A slot is (depth, normalised parent). Comparing bare keywords is
    too loose: :TRIGger:SINGle:TRIGgered and the :TRIGger subsystem
    share a prefix and are different mnemonics, and so are
    :OUTPut:TRACk and :SYSTem:TRACKMode. Two spellings are only
    candidates for the same keyword when they sit in the same place
    under the same parent.

    The parent is normalised to its uppercase run so that :MEAS:... and
    :MEASure:... are recognised as the same parent -- without that, the
    one bug this is here to catch would slip through, since it was
    written :MEAS:DISC? beside :MEASure:DISChargingTime?.
    """
    for match in LITERAL.finditer(source):
        command = match.group(1).split()[0]
        parts = [p.strip("[]") for p in command.lstrip(":*").rstrip("?").split(":")]
        parts = [p for p in parts if KEYWORD.match(p) and len(p) >= 2]
        for depth, word in enumerate(parts):
            parent = caps(parts[depth - 1]).upper() if depth else ""
            yield (depth, parent), word


def caps(mnemonic: str) -> str:
    return "".join(c for c in mnemonic if c.isupper())


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


@pytest.mark.parametrize("path", DRIVERS, ids=[os.path.basename(p) for p in DRIVERS])
def test_no_keyword_is_half_abbreviated(path):
    """A spelling between the uppercase run and the whole mnemonic is
    not a command, and the instrument's usual answer is silence."""
    by_slot = {}
    for slot, word in slotted_keywords(read(path)):
        by_slot.setdefault(slot, set()).add(word)

    wrong = []
    for words in by_slot.values():
        longs = [w for w in words
                 if re.match(r"^[A-Z]", w) and re.search(r"[a-z]", w)]
        for full in longs:
            legal = {full.upper(), caps(full).upper()}
            for other in words:
                if other.upper() in legal:
                    continue
                if len(other) < len(full) and full.upper().startswith(other.upper()):
                    wrong.append((other, full, sorted(legal)))

    assert not wrong, "\n".join(
        f"{os.path.basename(path)} sends {bad!r}, but spells the same keyword "
        f"{full!r} elsewhere -- the only legal forms are {legal}"
        for bad, full, legal in wrong)


@pytest.mark.parametrize("path", DRIVERS, ids=[os.path.basename(p) for p in DRIVERS])
def test_a_buried_capital_is_never_dropped(path):
    """The DISChargingTime shape.

    A mnemonic whose uppercase run is broken by lowercase and then
    resumes -- DISChargingTime, ONOFFSync, TRACKMode -- abbreviates to
    all of its capitals, T included. Dropping the tail capital gives a
    spelling that looks obviously right and is not a command.
    """
    by_slot = {}
    for slot, word in slotted_keywords(read(path)):
        by_slot.setdefault(slot, set()).add(word)

    wrong = []
    for words in by_slot.values():
        buried = [w for w in words if re.search(r"[a-z]", w)
                  and re.search(r"[A-Z]", re.sub(r"^[A-Z]+", "", w))]
        for full in buried:
            for other in words:
                if other.upper() in {full.upper(), caps(full).upper()}:
                    continue
                if full.upper().startswith(other.upper()) and len(other) < len(full):
                    wrong.append((other, full, caps(full)))

    assert not wrong, "\n".join(
        f"{os.path.basename(path)} sends {bad!r} for {full!r}; the buried "
        f"capital makes the short form {short!r}"
        for bad, full, short in wrong)


class TestTheCheckCanFail:
    """A guard that cannot fail is not a guard -- so this drives the
    real check function over a driver that contradicts itself."""

    def test_it_flags_a_driver_that_contradicts_itself(self, tmp_path):
        driver = tmp_path / "pretend_driver.py"
        driver.write_text(
            'RESULTS = {"a": ":MEAS:DISC?", "b": ":MEASure:DISChargingTime?"}',
            encoding="utf-8")

        with pytest.raises(AssertionError) as caught:
            test_no_keyword_is_half_abbreviated(str(driver))
        assert "DISC" in str(caught.value)

    def test_the_buried_capital_check_also_fires(self, tmp_path):
        driver = tmp_path / "pretend_driver.py"
        driver.write_text(
            'CMDS = [":MEAS:DISC?", ":MEASure:DISChargingTime?"]',
            encoding="utf-8")

        with pytest.raises(AssertionError) as caught:
            test_a_buried_capital_is_never_dropped(str(driver))
        assert "DISCT" in str(caught.value)

    def test_it_does_not_fire_on_a_consistent_driver(self, tmp_path):
        driver = tmp_path / "pretend_driver.py"
        driver.write_text('CMDS = [":SYST:ERR?", ":SYSTem:ERRor?"]',
                          encoding="utf-8")
        test_no_keyword_is_half_abbreviated(str(driver))
        test_a_buried_capital_is_never_dropped(str(driver))

    def test_it_passes_a_correct_pair(self):
        source = '''CMDS = [":SYST:ERR?", ":SYSTem:ERRor?"]'''
        words = set(keywords_in(source))
        for full in (w for w in words if re.search(r"[a-z]", w)):
            for other in words:
                if len(other) < len(full) and full.upper().startswith(other.upper()):
                    assert other.upper() == caps(full).upper()
