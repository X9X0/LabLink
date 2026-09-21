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
        if holder is not None and _finished_or_stranded(holder):
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
                "%s.%s was still held after %.0fs by %s; assuming the task "
                "was destroyed and starting a new one",
                type(owner).__name__, attribute, now - started,
                _describe_holder(holder),
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


def _describe_holder(task) -> str:
    """What the task holding a slot was doing, for the log.

    "Assuming the task was destroyed" is a guess, and it has been the
    wrong guess more than once: the task has variously been finished,
    stranded on a closed loop, and simply still running. Saying which
    turns the next occurrence into evidence instead of another theory.
    """
    if task is None:
        return "no task (claimed outside a coroutine, or before this was recorded)"
    at = _await_chain(task)
    if task.cancelled():
        return f"a cancelled task ({at})"
    if task.done():
        return f"a task that finished without releasing it ({at})"
    try:
        closed = task.get_loop().is_closed()
    except Exception:
        closed = None
    if closed:
        return f"a task suspended on a closed loop ({at})"
    return f"a task still running ({at}){_which_loop(task)}"


def _which_loop(task) -> str:
    """Whether the task is on the loop that is asking about it.

    The remaining question about these stalls. The evidence so far says a
    fetch completes and the task waiting for it cannot be woken --
    "RuntimeError: Cannot enter into task ... wait_for=<Future finished>"
    -- which happens when the future and the task belong to different
    loops. Which of the two is the odd one out decides the fix: stopping
    a second loop being made at all, or binding the blocking call to the
    loop its caller is actually on. Guessing between those would be the
    fifth guess in this hunt.
    """
    try:
        theirs = task.get_loop()
    except Exception:
        return ""
    try:
        mine = asyncio.get_running_loop()
    except RuntimeError:
        return f" [task loop {id(theirs):#x}, nothing running here]"
    if theirs is mine:
        return f" [same loop {id(mine):#x}]"
    return (f" [DIFFERENT loops: task on {id(theirs):#x}, "
            f"asking from {id(mine):#x}]")


def _await_chain(task, limit: int = 12) -> str:
    """Every frame a suspended task is waiting through, outermost first.

    The outermost frame alone says almost nothing. "refresh line 528" only
    means refresh is awaiting the fan-out; it cannot tell a slow HTTP
    request from a timeout that never fires from a lock nobody releases,
    and those want different fixes. Following ``cr_await`` down gives the
    whole chain, so the next stall names the thing it is actually stuck
    on.

    Defensive throughout: this runs inside a warning about something that
    has already gone wrong, and must not raise on the way.
    """
    try:
        node = task.get_coro()
    except Exception:
        return "no coroutine"

    steps = []
    seen = 0
    while node is not None and seen < limit:
        seen += 1
        frame = getattr(node, "cr_frame", None) or getattr(node, "gi_frame", None)
        if frame is not None:
            try:
                steps.append(f"{frame.f_code.co_name}:{frame.f_lineno}")
            except Exception:
                steps.append("?")
        else:
            # Not a coroutine: a Future, a gather, a lock, a sleep. This
            # is usually the interesting end of the chain -- "waiting on a
            # Future" and "waiting on another coroutine" are different
            # problems -- so it is named rather than dropped.
            steps.append(type(node).__name__)
            break
        node = (getattr(node, "cr_await", None)
                or getattr(node, "ag_await", None)
                or getattr(node, "gi_yieldfrom", None))

    if node is not None:
        steps.append("...")
    return " > ".join(steps) if steps else "no frame"


def _finished_or_stranded(task) -> bool:
    """Whether the task holding a slot can no longer be working.

    Finished is the easy case. The other one is a task left on a loop that
    is not going to run it again: a coroutine awaiting on a loop that has
    been closed, or on a different loop from the one now running, will stay
    pending for the life of the process. Its finally never runs, so it
    never releases the slot, and waiting out the abandonment timeout is
    just a pause with nothing at the end of it.
    """
    if task.done():
        return True
    try:
        task_loop = task.get_loop()
    except Exception:
        return True                 # cannot tell whose it is: assume lost
    if task_loop.is_closed():
        return True
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        return False                # nothing running to compare against
    return task_loop is not running


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
