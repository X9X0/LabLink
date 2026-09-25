"""Every setter that changes the instrument needs a lock."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.api.equipment import requires_control


class TestTheFunctionModeSettersNeedALock:
    """These shipped able to reconfigure a locked instrument.

    requires_control is a substring test, and "set_mode" does not occur
    in "set_function_mode" -- so every one of the list, battery, OCP and
    OPP setters slipped past it. Arming somebody else's battery
    discharge, or moving the step current of their OCP test, is control
    by any reading.
    """

    @pytest.mark.parametrize("action", [
        "set_function_mode",
        "set_function_parameter",
        "set_battery_cutoffs",
        "set_list_step",
        "set_list_mode",
        "set_list_end_state",
    ])
    def test_it_is_control(self, action):
        assert requires_control(action), f"{action} bypasses the lock"

    @pytest.mark.parametrize("action", [
        "get_function_mode",
        "get_function_parameter",
        "get_battery_cutoffs",
        "get_battery_results",
        "get_list_step",
        "get_protection_status",
        "get_readings",
    ])
    def test_reading_still_needs_no_lock(self, action):
        """Observing an instrument somebody else is driving is the
        point of the observer lock."""
        assert not requires_control(action), f"{action} now demands a lock"
