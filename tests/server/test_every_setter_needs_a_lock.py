"""Every action that changes an instrument needs a lock.

requires_control is a substring test over a hand-written list of
names, which means it only knows what somebody remembered to add. That
has now been discovered three times on this branch:

  * the :FUNCtion:MODE family -- "set_mode" does not occur in
    "set_function_mode", so list, battery, OCP and OPP all slipped past
  * start_list and stop_list, which are not spelled "set_something"
  * set_tracking and set_timer_step, which are, but matched no entry

Rather than wait for a fourth, this walks the actions the drivers
actually expose and asserts the rule directly: a name that begins with
"set_" changes the instrument, so it needs control.
"""

import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.api.equipment import requires_control

#: Drivers whose action tables are read below. Each is a class with an
#: execute_command that dispatches from a dict literal.
DRIVER_MODULES = (
    "server.equipment.siglent_power_supply",
    "server.equipment.rigol_electronic_load",
    "server.equipment.rigol_power_supply",
)

#: Reads that happen to start with "set_". None so far; kept so that a
#: genuine exception can be named and argued for rather than silently
#: widening the rule.
KNOWN_READS = frozenset()


def _action_names():
    """Every quoted action name in the drivers' dispatch tables.

    Read from the source rather than by building a driver, which would
    need a resource manager and a live instrument.
    """
    import re

    found = set()
    for name in DRIVER_MODULES:
        module = __import__(name, fromlist=["x"])
        source = inspect.getsource(module)
        for match in re.finditer(r'"(set_[a-z0-9_]+)":\s*self\.', source):
            found.add(match.group(1))
        for match in re.finditer(r'"(get_[a-z0-9_]+)":\s*self\.', source):
            found.add(match.group(1))
    return found


class TestSettersAreControl:
    def test_the_drivers_expose_something(self):
        """If this finds nothing the rest of the file proves nothing."""
        names = _action_names()
        assert len(names) > 20, names

    def test_every_setter_needs_control(self):
        offenders = sorted(
            name for name in _action_names()
            if name.startswith("set_")
            and name not in KNOWN_READS
            and not requires_control(name)
        )
        assert not offenders, (
            "these change an instrument and bypass the lock: %s" % offenders)

    def test_no_getter_demands_control(self):
        """Observing an instrument somebody else is driving is the
        point of the observer lock."""
        offenders = sorted(
            name for name in _action_names()
            if name.startswith("get_") and requires_control(name)
        )
        assert not offenders, (
            "these only read and yet demand a lock: %s" % offenders)


class TestTheNamesFoundOnTheBench:
    """Spelled out so a rename cannot quietly drop one."""

    @pytest.mark.parametrize("action", [
        "set_function_mode", "set_list_step", "set_battery_cutoffs",
        "start_list", "stop_list", "set_tracking", "set_timer_step",
        "set_timer_enabled", "set_output", "set_voltage", "set_current",
    ])
    def test_it_is_control(self, action):
        assert requires_control(action), action

    @pytest.mark.parametrize("action", [
        "get_all_readings", "get_timer_step", "get_timer_running",
        "get_tracking", "get_readings", "get_system_status",
        "get_protection_status", "measure",
    ])
    def test_it_is_not(self, action):
        assert not requires_control(action), action
