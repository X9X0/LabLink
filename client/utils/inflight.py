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

import asyncio
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

    if started is not None:
        holder = getattr(owner, _holder(attribute), None)
        if holder is not None and holder.done():
            # The task that took this slot has finished without releasing
            # it, so it died somewhere its finally could not run. There is
            # nothing in flight and no reason to wait: take the slot now.
            #
            # Waiting for the time backstop instead is what an operator
            # saw as "it does update to connected, but there is quite a
            # delay" -- the panel had refreshed, the refresh task was
            # destroyed mid-await, and every later refresh was refused for
            # the full abandoned_after (45s) before anything could redraw.
            logger.info(
                "%s.%s was left held by a task that has finished; taking it",
                type(owner).__name__, attribute,
            )
        elif (now - started) < abandoned_after:
            return False
        else:
            logger.warning(
                "%s.%s was still held after %.0fs; assuming the task was "
                "destroyed and starting a new one",
                type(owner).__name__, attribute, now - started,
            )

    setattr(owner, attribute, now)
    # Keep a reference to the running task, for two reasons. It is what
    # lets the check above tell "finished without releasing" from "still
    # working". And asyncio only holds a weak reference to a task, so a
    # caller that keeps none can have it garbage-collected mid-await --
    # which is the "Task was destroyed but it is pending!" in this log,
    # and the way slots came to be stranded in the first place.
    try:
        setattr(owner, _holder(attribute), asyncio.current_task())
    except RuntimeError:            # no running loop: a synchronous caller
        setattr(owner, _holder(attribute), None)
    return True


def release_slot(owner, attribute: str) -> None:
    """Release a slot taken by :func:`claim_slot`."""
    setattr(owner, attribute, None)
    setattr(owner, _holder(attribute), None)


def _holder(attribute: str) -> str:
    """Where the task owning ``attribute``'s slot is remembered."""
    return f"{attribute}_task"


# ---------------------------------------------------------------------- #
# Coalescing
# ---------------------------------------------------------------------- #
#
# Refusing an overlapping request is right for a timer tick: the answer it
# would have fetched is the one already on its way. It is wrong for a
# request that follows an event, because the state it is asking about
# changed *after* the in-flight fetch was sent.
#
# Connecting an instrument is exactly that. The handler refreshes the list
# so the connected dot appears, but if a periodic refresh happened to be in
# flight the request was dropped and never retried, so the dot did not
# appear until something else asked -- up to a five-second tick away, or a
# tab switch. Recording the miss and running once more when the current
# fetch returns costs one extra pass and makes the list current.
#
# Opt-in, and deliberately not folded into claim_slot: the instrument panels
# guard their readings with the same slot, and there a missed tick really is
# better dropped than run late.


def note_missed(owner, attribute: str) -> None:
    """Record that a request arrived while ``attribute``'s slot was held."""
    setattr(owner, f"{attribute}_missed", True)


def take_missed(owner, attribute: str) -> bool:
    """Whether a request was missed, clearing the record."""
    name = f"{attribute}_missed"
    missed = bool(getattr(owner, name, False))
    if missed:
        setattr(owner, name, False)
    return missed
