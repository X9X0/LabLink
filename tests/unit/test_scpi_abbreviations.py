"""Every keyword the load driver sends must be a legal abbreviation.

The DL3000 Programming Guide states the rule at 1-5, "Command
Abbreviation" -- a section its "Symbol Description" list does not
mention, which describes only braces, the vertical bar, square
brackets and angle brackets:

    The letters in the commands are case-insensitive. The commands can
    be input in uppercase letters or in lowercase letters. If
    abbreviation is used, you must enter all the uppercase letters that
    exist in the command syntax. For example, :SYSTem:ERRor? can be
    abbreviated as :SYST:ERR?

So :FUNC and :FUNCtion are the same command, and the lowercase letters
are all-or-nothing: :FUNCtio is not a command and neither is :FUNCti.

The trap is a mnemonic with a capital letter buried in its tail.
:MEASure:DISChargingTime? has one -- the uppercase letters are D, I,
S, C and T, so the legal abbreviation is DISCT. Sent as DISC it is not
a command at all, and this load answers by not answering: on the bench
capacity and watt-hours read back fine while the discharge time came
back None, through two full probe runs, because the driver's own
error handling turned a bad keyword into a shrug.

DOCUMENTED below is the spelling the guide prints for each keyword the
driver sends. The test applies the rule to it.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.equipment.rigol_electronic_load import (_BATTERY_RESULTS,
                                                    _FUNCTION_PARAMETERS)

#: Keyword as the guide prints it, upper-cased for lookup. Sourced from
#: the DL3000 Programming Guide (Apr 2019, PGJ01105-1110), chapter 2.
DOCUMENTED = {
    "SOURCE": "SOURce",
    "SOUR": "SOURce",
    "FUNCTION": "FUNCtion",
    "FUNC": "FUNCtion",
    "MODE": "MODE",
    "BATTARY": "BATTary",
    "BATT": "BATTary",
    "RANGE": "RANGe",
    "RANG": "RANGe",
    "VON": "VON",
    "VSTOP": "VSTop",
    "VST": "VSTop",
    "CSTOP": "CSTop",
    "CST": "CSTop",
    "TIMESTOP": "TIMestop",
    "TIM": "TIMestop",
    "OCP": "OCP",
    "OPP": "OPP",
    "VONDELAY": "VONDelay",
    "VOND": "VONDelay",
    "ISET": "ISET",
    "ISTEP": "ISTep",
    "IST": "ISTep",
    "IDELAYSTEP": "IDELaystep",
    "IDEL": "IDELaystep",
    "IMAX": "IMAX",
    "IMIN": "IMIN",
    "VOCP": "VOCP",
    "TOCP": "TOCP",
    "PSET": "PSET",
    "PSTEP": "PSTep",
    "PST": "PSTep",
    "PDELAYSTEP": "PDELaystep",
    "PDEL": "PDELaystep",
    "PMAX": "PMAX",
    "PMIN": "PMIN",
    "VOPP": "VOPP",
    "TOPP": "TOPP",
    "LIST": "LIST",
    "COUNT": "COUNt",
    "COUN": "COUNt",
    "STEP": "STEP",
    "LEVEL": "LEVel",
    "LEV": "LEVel",
    "WIDTH": "WIDth",
    "WID": "WIDth",
    "SLEW": "SLEW",
    "END": "END",
    "MEASURE": "MEASure",
    "MEAS": "MEASure",
    "CAPABILITY": "CAPability",
    "CAP": "CAPability",
    "WATTHOURS": "WATThours",
    "WATT": "WATThours",
    "DISCHARGINGTIME": "DISChargingTime",
    "DISCT": "DISChargingTime",
}


def legal_abbreviation(sent: str, documented: str) -> bool:
    """Apply the guide's rule to one keyword.

    Legal if it is the whole mnemonic, or if it is exactly the
    uppercase letters of it. Anything between the two -- some of the
    lowercase tail but not all of it -- is not a command.
    """
    sent = sent.upper()
    if sent == documented.upper():
        return True
    return sent == "".join(c for c in documented if c.isupper())


def keywords(scpi: str):
    return [p for p in scpi.lstrip(":").rstrip("?").split(":") if p]


def every_command():
    for name, (scpi, _unit, _limit) in _FUNCTION_PARAMETERS.items():
        yield name, scpi
    for name, scpi in _BATTERY_RESULTS.items():
        yield f"battery result {name}", scpi


class TestTheRuleItself:
    """The rule, checked on the guide's own worked example and on the
    mnemonic that caught us out."""

    def test_the_guides_example(self):
        assert legal_abbreviation("SYST", "SYSTem")
        assert legal_abbreviation("SYSTem", "SYSTem")

    def test_a_partial_tail_is_not_a_command(self):
        assert not legal_abbreviation("SYSTe", "SYSTem")
        assert not legal_abbreviation("SYS", "SYSTem")

    def test_a_buried_capital_belongs_in_the_abbreviation(self):
        """The one that cost two probe runs."""
        assert legal_abbreviation("DISCT", "DISChargingTime")
        assert legal_abbreviation("DISChargingTime", "DISChargingTime")
        assert not legal_abbreviation("DISC", "DISChargingTime"), (
            "DISC drops the T and is not a command")

    def test_an_all_caps_mnemonic_cannot_be_shortened(self):
        assert legal_abbreviation("ISET", "ISET")
        assert not legal_abbreviation("IS", "ISET")


class TestEveryKeywordTheDriverSends:
    @pytest.mark.parametrize("name,scpi", list(every_command()))
    def test_it_is_a_documented_keyword(self, name, scpi):
        for word in keywords(scpi):
            assert word.upper() in DOCUMENTED, (
                f"{name} sends {scpi!r}, and {word!r} is not a keyword the "
                f"guide prints")

    @pytest.mark.parametrize("name,scpi", list(every_command()))
    def test_it_is_a_legal_abbreviation(self, name, scpi):
        for word in keywords(scpi):
            documented = DOCUMENTED[word.upper()]
            assert legal_abbreviation(word, documented), (
                f"{name} sends {word!r}; the guide prints {documented!r}, so "
                f"the only legal forms are {documented!r} and "
                f"{''.join(c for c in documented if c.isupper())!r}")

    def test_the_discharge_time_is_not_sent_as_disc(self):
        """Named on its own because it shipped wrong twice and the
        failure mode is silence, not an error."""
        assert "DISC?" not in _BATTERY_RESULTS["discharge_seconds"].upper() \
            .replace("DISCHARGINGTIME?", ""), (
                "discharge time is abbreviated to DISC again")


class TestTheTableCoversWhatWeSend:
    def test_no_keyword_is_unchecked(self):
        """A new command with a keyword missing from DOCUMENTED should
        fail loudly rather than skip the check."""
        unknown = set()
        for _name, scpi in every_command():
            for word in keywords(scpi):
                if word.upper() not in DOCUMENTED:
                    unknown.add(word)
        assert not unknown, f"add these to DOCUMENTED from the guide: {unknown}"
