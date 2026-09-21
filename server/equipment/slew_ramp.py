"""Keep driving a slew-limited setpoint until it reaches what was asked for.

The slew limiter answers "how far may this parameter move right now", clamps
the write to that, and returns. What it does not do is remember where the
operator wanted to go, so a change larger than one step simply never
arrives. On the bench: the dial was scrolled down to 9.6 V and the supply
stopped at 15.6 V, because that is where the last clamped write left it.

    requested 28.6, limited to 31.64  (max change 0.309 over 0.015s)
    requested 21.6, limited to 26.64
    requested 15.6, limited to 16.92
    requested  9.6, limited to 15.58   <- and there it stayed

Whether it got close depended on how many writes happened to arrive, which
is not a property anyone designed. Driving the dial faster produced *fewer*
writes and so moved the supply *less*.

The rate limit is the point and is not in question -- 20 V/s for a supply,
set deliberately. What was missing is that a rate limit describes how fast
to approach a value, not an excuse never to reach it. So the target is
remembered here, and the setpoint is re-applied every :data:`STEP_SEC`
until the instrument is there.

Re-applying goes back through the driver's own ``set_voltage`` /
``set_current``, which is the whole reason this is shaped as a repeat
rather than as a write loop of its own: the range checks, the emergency
stop check, the equipment lock and the slew limiter all apply to every step
exactly as they do to the operator's first one. A step that raises -- an
emergency stop, a disconnect mid-ramp -- ends the ramp.

A new target replaces the old one rather than queueing behind it: when the
operator moves a dial again, where they were heading a moment ago no longer
matters.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)

#: How long to wait between steps.
#:
#: This costs nothing in arrival time. The limiter allows movement in
#: proportion to the time since the last write, so a longer gap simply
#: buys a bigger step: at 20 V/s, 50 ms is a 1 V step and 200 ms is a 4 V
#: step, and the ramp reaches the target at the same moment either way.
#: What it does change is how many commands the instrument is asked to
#: service.
#:
#: 50 ms was too many. A B&K on a 9600-baud line needs tens of
#: milliseconds per command, and 20 ramp writes a second on top of a 5 Hz
#: poll -- which is three commands of its own, GETD, GOUT and GETS -- came
#: to roughly 35 a second. The supply stopped keeping up, and the bench
#: log showed what that looks like from here::
#:
#:     no acknowledgement after 'VOLT000': VI_ERROR_TMO
#:     no acknowledgement after 'VOLT004': VI_ERROR_TMO
#:     Error getting device readings: Invalid GETD response:
#:
#: Nine unacknowledged writes in half a minute, each costing a full VISA
#: timeout of dead port time, and a late acknowledgement then arriving in
#: front of the next read and desynchronising it.
STEP_SEC = 0.2

#: Refuse to ramp for longer than this. A target the instrument will not
#: reach -- because it is clamped by something else, or the supply is
#: ignoring us -- must not leave a task writing to it forever.
GIVE_UP_AFTER_SEC = 30.0


class SlewRamps:
    """The targets a piece of equipment is still travelling towards."""

    def __init__(self, describe: str = "equipment"):
        self._describe = describe
        self._targets: Dict[str, float] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        #: For a parameter mid-step, the exact target that step is
        #: re-applying. Keyed on the value and not merely "a step is in
        #: flight": a request that arrives during a step is the operator's
        #: and must be honoured, and a flag cannot tell the two apart --
        #: it would discard the very thing it is meant to protect.
        self._continuing: Dict[str, float] = {}

    def note(
        self,
        parameter: str,
        target: float,
        written: float,
        again: Callable[[float], Awaitable[None]],
    ) -> None:
        """Record what was asked for, and keep going if the write fell short.

        Args:
            parameter: "voltage", "current", ... -- ramped independently.
            target: what the caller asked for, before any clamping.
            written: what actually went to the instrument.
            again: re-applies the target, normally the driver's own setter.
        """
        if self._continuing.get(parameter) == target:
            # This is the ramp re-applying a target it already had, not
            # somebody asking for a new one -- every step goes back
            # through the driver's setter, which lands here again.
            #
            # If the operator moved the control while this step was in
            # flight, the target is now theirs and this call must not put
            # the old one back. It did, and the supply ramped to where the
            # dial had been one notch ago:
            #
            #   requested 6.2, limited to 3.57
            #   requested 7.2, limited to 3.75   <- the operator's value
            #   requested 6.2, limited to 3.58   <- the step that was in
            #   requested 6.2 ...                   flight, overwriting it
            #
            # Always exactly one notch short, because it is always the
            # last notch that gets clobbered.
            if self._targets.get(parameter) != target:
                return                  # superseded; leave the new one alone
            if self._reached(target, written):
                self._targets.pop(parameter, None)
            return

        if self._reached(target, written):
            # Arrived. Clearing the target is what stops a running ramp;
            # cancelling would mean a step cancelling the task it is
            # running on, since this is called from inside that step.
            self._targets.pop(parameter, None)
            return

        self._targets[parameter] = target
        task = self._tasks.get(parameter)
        if task is not None and not task.done():
            return              # the ramp already running will pick it up
        self._tasks[parameter] = asyncio.ensure_future(
            self._travel(parameter, again)
        )

    async def _travel(self, parameter: str, again) -> None:
        """Re-apply the target until it is reached, superseded or refused."""
        loop = asyncio.get_event_loop()
        started = loop.time()
        try:
            while True:
                await asyncio.sleep(STEP_SEC)
                target = self._targets.get(parameter)
                if target is None:
                    return                      # arrived, or abandoned
                if loop.time() - started > GIVE_UP_AFTER_SEC:
                    logger.warning(
                        f"{self._describe}: gave up ramping {parameter} to "
                        f"{target} after {GIVE_UP_AFTER_SEC:g}s"
                    )
                    self._targets.pop(parameter, None)
                    return
                # Marked for the duration of the write, so the note() this
                # setter makes on its way out knows it is this ramp
                # continuing rather than a fresh request.
                self._continuing[parameter] = target
                try:
                    await again(target)
                finally:
                    self._continuing.pop(parameter, None)
        except asyncio.CancelledError:
            self._targets.pop(parameter, None)
            raise
        except Exception as e:
            # A refusal is a reason to stop, not to keep writing: an
            # emergency stop, a disconnect, a value the instrument will not
            # take. The operator's own next command starts a fresh ramp.
            logger.warning(
                f"{self._describe}: stopped ramping {parameter}: {e}"
            )
            self._targets.pop(parameter, None)
        finally:
            self._tasks.pop(parameter, None)

    @staticmethod
    def _reached(target: float, written: float) -> bool:
        """Whether the write got all the way there.

        ``written`` is the value after clamping, so it is either the target
        itself, untouched, or a value the limiter cut short. The comparison
        can be exact; the epsilon only guards against a driver that rebuilds
        the float on the way past.
        """
        return abs(float(written) - float(target)) < 1e-9

    def travelling(self, parameter: Optional[str] = None) -> bool:
        """Whether a ramp is still running, for one parameter or any."""
        if parameter is None:
            return bool(self._targets)
        return parameter in self._targets

    def target(self, parameter: str) -> Optional[float]:
        """Where ``parameter`` is heading, or None if it is not."""
        return self._targets.get(parameter)

    def stop(self, parameter: Optional[str] = None) -> None:
        """Abandon a ramp, or all of them.

        Called when the instrument goes away: nothing should keep writing
        setpoints to equipment that has been disconnected.
        """
        names = [parameter] if parameter is not None else list(self._tasks)
        for name in names:
            self._targets.pop(name, None)
            self._continuing.pop(name, None)
            task = self._tasks.pop(name, None)
            if task is not None and not task.done():
                task.cancel()
