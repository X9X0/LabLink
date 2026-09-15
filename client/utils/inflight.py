"""A single-flight guard that cannot get stuck.

Several panels refresh on a timer and must not start a new request while the
previous one is still out -- a fan-out over several servers can easily outlast
a five-second tick, since an unreachable Pi spends a full connect timeout.

The obvious guard is a boolean set before the await and cleared in a finally.
It is wrong here. qasync destroys pending tasks when the event loop is
disturbed, which the log reports as "Task was destroyed but it is pending",
and a task destroyed mid-await never runs its finally. The flag then stays set
for the life of the process and the panel never refreshes again -- recoverable
only by restarting the client, which is what was happening after every server
update.

Recording *when* the work started fixes that without weakening the guard: a
slot still held long after anything could reasonably still be running is taken
anyway, so the failure mode is one overlapping refresh rather than a panel
that is permanently frozen.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

#: How long an unfinished operation is believed before it is assumed dead.
#: Comfortably longer than a fan-out over several servers, each of which can
#: spend a ten-second connect timeout on a Pi that is switched off.
REFRESH_ABANDONED_AFTER = 45.0

#: The equivalent for instrument readings, which run many times a second. A
#: reading that has not come back in this long is not coming back, and waiting
#: the full refresh timeout would leave the panel blank for most of a minute.
READINGS_ABANDONED_AFTER = 10.0


def claim_slot(owner, attribute: str, abandoned_after: float) -> bool:
    """Take the single in-flight slot named by ``attribute``, if it is free.

    Args:
        owner: the object holding the slot.
        attribute: name of the attribute storing the start time, or None.
        abandoned_after: seconds after which a held slot is assumed dead.

    Returns:
        True when the caller may proceed, with its start time recorded.
        False when another call genuinely is still in flight.
    """
    started: Optional[float] = getattr(owner, attribute, None)
    now = time.monotonic()

    if started is not None and (now - started) < abandoned_after:
        return False

    if started is not None:
        logger.warning(
            "%s.%s was still held after %.0fs; assuming the task was destroyed "
            "and starting a new one",
            type(owner).__name__, attribute, now - started,
        )

    setattr(owner, attribute, now)
    return True


def release_slot(owner, attribute: str) -> None:
    """Release a slot taken by :func:`claim_slot`."""
    setattr(owner, attribute, None)
