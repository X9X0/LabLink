"""Every keyword the Rigol drivers send, checked against Rigol's manuals.

The rule is stated in the DL3000 Programming Guide at 1-5 and holds
across the line:

    The letters in the commands are case-insensitive. ... If
    abbreviation is used, you must enter all the uppercase letters that
    exist in the command syntax.

A keyword therefore has exactly two legal spellings -- the whole
mnemonic, or its capitals -- and nothing in between. ``:SYST`` and
``:SYSTem`` are the same command; ``:SYSTe`` is not a command at all,
and an instrument's usual response to one is no response.

That silence is the reason this file exists. Two commands shipped
wrong and neither raised anything:

  * ``:MEASure:DISChargingTime?`` was sent ``:MEAS:DISC?``. The buried
    capital T belongs in the abbreviation -- it is DISCT -- and the
    load answered by not answering. Two full bench probes read battery
    capacity and watt-hours back correctly and returned None for the
    discharge time before the rule explained why.

  * ``:MEAS:DUTY?`` on the scopes is not a command on any model this
    driver claims. The guides have PDUTy/NDUTy and PDUTycycle: duty
    cycle is signed, so there is no unqualified form. It sat inside a
    try block that logs at debug, so callers simply never saw a
    duty_cycle key.

The table in data/rigol_documented_keywords.json is generated from the
programming guides -- 51 of them, covering every family the drivers
claim -- and records, for each keyword we send, the spellings its
guides print. It is checked in because the manuals live outside the
repo and a test that quietly skips when they are absent would be worth
nothing.
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

TABLE = os.path.join(os.path.dirname(__file__), "data",
                     "rigol_documented_keywords.json")

with open(TABLE, encoding="utf-8") as _f:
    DOCUMENTED = json.load(_f)

LITERAL = re.compile(r'["\']([:*][A-Za-z0-9:*?\[\]]{2,}[^"\']*)["\']')
KEYWORD = re.compile(r"^[A-Za-z]+$")


def caps(word):
    return "".join(c for c in word if c.isupper())


def keywords_sent(driver):
    """What the driver sends today, read from its source."""
    path = os.path.join(os.path.dirname(__file__), "../../server/equipment",
                        driver)
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    for m in LITERAL.finditer(src):
        command = m.group(1).split()[0]
        common = command.startswith("*")
        for part in command.lstrip(":*").rstrip("?").split(":"):
            part = part.strip("[]")
            if KEYWORD.match(part) and len(part) >= 2:
                yield part, common


def cases():
    for driver, entry in sorted(DOCUMENTED.items()):
        for word, facts in sorted(entry["keywords"].items()):
            yield pytest.param(driver, word, facts, id=f"{driver}:{word}")


class TestTheTableIsReal:
    def test_it_covers_every_driver_with_a_guide(self):
        assert len(DOCUMENTED) >= 11, "drivers went missing from the table"

    def test_every_entry_names_its_guides(self):
        for driver, entry in DOCUMENTED.items():
            assert entry["guides"], f"{driver} has no guide behind it"

    def test_the_load_is_backed_by_the_dl3000_guide(self):
        guides = DOCUMENTED["rigol_electronic_load.py"]["guides"]
        assert any("DL3000" in g for g in guides), guides


class TestEveryKeywordIsLegal:
    @pytest.mark.parametrize("driver,word,facts", list(cases()))
    def test_it_is_a_spelling_the_guide_prints(self, driver, word, facts):
        """Legal = the whole mnemonic, or exactly its capitals."""
        if facts.get("common"):
            return                      # *IDN?, *RST and friends
        spellings = facts.get("documented") or []
        if not spellings:
            # Not in these guides. Only a problem if it looks like a
            # truncation of something that is -- otherwise it is a
            # parameter or a command the guide words differently.
            assert not facts.get("truncates"), (
                f"{driver} sends {word!r}, which is not in its guides but is "
                f"a truncation of {facts['truncates'][:3]}")
            return
        up = word.upper()
        assert any(up == s.upper() or up == caps(s).upper() for s in spellings), (
            f"{driver} sends {word!r}; its guides print {spellings}, so the "
            f"only legal forms are those and "
            f"{sorted({caps(s) for s in spellings})}")


class TestTheDriversStillSendWhatWeChecked:
    """The table is a snapshot. If a driver gains a keyword that is not
    in it, the check silently stops covering that keyword -- so the
    snapshot has to be regenerated, not quietly outgrown."""

    @pytest.mark.parametrize("driver", sorted(DOCUMENTED))
    def test_no_keyword_escaped_the_table(self, driver):
        known = set(DOCUMENTED[driver]["keywords"])
        now = {w for w, _c in keywords_sent(driver)}
        missing = now - known
        assert not missing, (
            f"{driver} now sends {sorted(missing)}, which is not in "
            f"tests/unit/data/rigol_documented_keywords.json -- regenerate it "
            f"from the manuals so these are checked too")


class TestTheTwoBugsThisFound:
    """Named, because both failed silently and both would look fine in
    a review."""

    def test_the_discharge_time_keeps_its_buried_capital(self):
        from server.equipment.rigol_electronic_load import _BATTERY_RESULTS

        sent = _BATTERY_RESULTS["discharge_seconds"].upper()
        assert "DISCHARGINGTIME" in sent or "DISCT" in sent, sent
        assert not re.search(r":DISC\?", sent), (
            "back to DISC, which is not a command")

    def test_the_scope_asks_for_a_signed_duty_cycle(self):
        path = os.path.join(os.path.dirname(__file__),
                            "../../server/equipment/rigol_scope.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        # Quoted, so the comment explaining the bug does not count as
        # the bug.
        assert '":MEAS:DUTY?"' not in src, (
            "no Rigol scope has an unqualified duty-cycle command")
        assert '":MEAS:PDUT?"' in src, "positive duty cycle went missing"
