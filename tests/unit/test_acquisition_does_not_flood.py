"""A channel that cannot be read must not fill the disk.

Starting an acquisition on a power supply with channel CH1 -- which
that driver does not implement -- was accepted. The loop then failed on
every sample at the configured rate and logged each failure:

    6,287 identical lines in about ten seconds, 1.1 MB of log

On a Pi with a modest card, an acquisition left running overnight that
way fills the disk. The session meanwhile reported itself as
"acquiring" while the buffer filled with NaN, so nothing but the log
said anything was wrong.

Two things were wrong and both are fixed here: the session should
never have been created, and a repeating error should be reported at a
rate a human can read.
"""

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.acquisition.manager import AcquisitionManager


class Complaints:
    """The per-channel state the loop keeps."""

    def __init__(self):
        self.store = {}


def count_errors(caplog):
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


class TestARepeatingFailureIsReportedOnce:
    def test_the_first_one_is_logged(self, caplog):
        """It is the one that says what went wrong."""
        state = {}
        with caplog.at_level(logging.ERROR):
            AcquisitionManager._complain_occasionally(
                state, "acq-1", "CH1", NotImplementedError("no acquisition"))
        assert len(count_errors(caplog)) == 1
        assert "no acquisition" in caplog.text

    def test_the_next_six_thousand_are_not(self, caplog):
        """The bench case, at the rate it actually happened."""
        state = {}
        with caplog.at_level(logging.ERROR):
            for _ in range(6287):
                AcquisitionManager._complain_occasionally(
                    state, "acq-1", "CH1",
                    NotImplementedError("no acquisition"))

        assert len(count_errors(caplog)) == 1, (
            f"{len(count_errors(caplog))} lines for one repeating failure")

    def test_the_count_is_not_lost(self, caplog):
        """Suppressed is not the same as forgotten: once the interval
        passes, the tally is reported."""
        state = {}
        AcquisitionManager._complain_occasionally(
            state, "acq-1", "CH1", NotImplementedError("no acquisition"))
        for _ in range(500):
            AcquisitionManager._complain_occasionally(
                state, "acq-1", "CH1", NotImplementedError("no acquisition"))

        # Pretend the interval has passed.
        state["CH1"][2] -= AcquisitionManager.COMPLAIN_EVERY_SEC + 1
        with caplog.at_level(logging.ERROR):
            AcquisitionManager._complain_occasionally(
                state, "acq-1", "CH1", NotImplementedError("no acquisition"))

        # Two lines for 502 failures: the first, and this summary.
        assert len(count_errors(caplog)) == 2, (
            f"{len(count_errors(caplog))} lines for 502 failures")
        assert "still failing" in caplog.text
        assert "502 times" in caplog.text, caplog.text

    def test_a_different_error_is_always_reported(self, caplog):
        """New information, so it is not a repeat."""
        state = {}
        AcquisitionManager._complain_occasionally(
            state, "acq-1", "CH1", NotImplementedError("no acquisition"))
        with caplog.at_level(logging.ERROR):
            AcquisitionManager._complain_occasionally(
                state, "acq-1", "CH1", OSError("the instrument went away"))
        assert "went away" in caplog.text

    def test_each_channel_is_counted_separately(self, caplog):
        state = {}
        with caplog.at_level(logging.ERROR):
            AcquisitionManager._complain_occasionally(
                state, "acq-1", "CH1", NotImplementedError("no acquisition"))
            AcquisitionManager._complain_occasionally(
                state, "acq-1", "CH2", NotImplementedError("no acquisition"))
        assert len(count_errors(caplog)) == 2, (
            "a second failing channel is a separate fact")


class TestTheSessionIsRefusedUpFront:
    """Better than reporting it politely six thousand times."""

    class Supply:
        """A supply: no get_measurement, and execute_command refuses."""

        async def execute_command(self, command, parameters):
            raise RuntimeError("not supported")

    class Meter:
        async def get_measurement(self, channel):
            return {"value": 1.23}

    @pytest.mark.asyncio
    async def test_a_channel_it_cannot_read_is_refused(self):
        from server.acquisition.models import AcquisitionConfig

        manager = AcquisitionManager()
        config = AcquisitionConfig(equipment_id="ps_1", channels=["CH1"])

        with pytest.raises(ValueError) as refused:
            await manager.create_session(self.Supply(), config)

        said = str(refused.value)
        assert "CH1" in said and "ps_1" in said, said
        assert manager._sessions == {}, "it kept a session it had refused"

    @pytest.mark.asyncio
    async def test_a_channel_it_can_read_is_accepted(self):
        from server.acquisition.models import AcquisitionConfig

        manager = AcquisitionManager()
        config = AcquisitionConfig(equipment_id="dmm_1", channels=["CH1"])

        session = await manager.create_session(self.Meter(), config)
        assert session.acquisition_id in manager._sessions

    @pytest.mark.asyncio
    async def test_a_busy_instrument_is_not_a_bad_configuration(self):
        """An instrument that is off or locked raises something other
        than NotImplementedError. That is the loop's to retry, not a
        reason to refuse the session outright."""
        from server.acquisition.models import AcquisitionConfig

        class Busy:
            async def get_measurement(self, channel):
                raise OSError("resource busy")

        manager = AcquisitionManager()
        config = AcquisitionConfig(equipment_id="dmm_1", channels=["CH1"])

        session = await manager.create_session(Busy(), config)
        assert session.acquisition_id in manager._sessions
