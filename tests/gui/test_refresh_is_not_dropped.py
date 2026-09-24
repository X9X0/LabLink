"""A refresh asked for while one is in flight must not vanish.

Reported from the bench: the connected dots beside the equipment names do
not appear when equipment is connected, and the Control tab's list takes a
while to catch up.

Both panels guard their fan-out with a single in-flight slot, which is
right for a timer tick -- the answer it would fetch is the one already on
its way. It is wrong for a request that follows an event: connecting an
instrument changes the thing the in-flight fetch already asked about, so
its answer is stale by the time it lands. The handler did call refresh,
the guard refused it, and nothing retried; the dot then waited for the
five-second tick or a tab switch.

Separately, the shell's periodic refresh and its tab-change handler look
for a method called ``refresh``. The Control tab's is called
``refresh_equipment_list``, so it was the one panel they both skipped --
sitting on that tab, nothing refreshed the list at all.
"""

import asyncio
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from PyQt6.QtWidgets import QApplication


    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not GUI_AVAILABLE, reason="PyQt6 is required")

if GUI_AVAILABLE:
    from client.ui.control_panel import ControlPanel
    from client.ui.equipment_panel import EquipmentPanel
    from client.utils.inflight import (REFRESH_ABANDONED_AFTER, claim_slot,
                                       note_missed, release_slot, take_missed)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Owner:
    pass


class TestTheRecordOfAMissedRequest:
    def test_nothing_is_missed_to_begin_with(self):
        assert take_missed(_Owner(), "_slot") is False

    def test_a_noted_miss_is_reported_once(self):
        owner = _Owner()
        note_missed(owner, "_slot")
        assert take_missed(owner, "_slot") is True
        assert take_missed(owner, "_slot") is False, "a miss was served twice"

    def test_several_misses_coalesce_into_one_pass(self):
        """Three collisions do not mean three extra fetches."""
        owner = _Owner()
        for _ in range(3):
            note_missed(owner, "_slot")
        assert take_missed(owner, "_slot") is True
        assert take_missed(owner, "_slot") is False

    def test_the_record_is_per_slot(self):
        owner = _Owner()
        note_missed(owner, "_readings")
        assert take_missed(owner, "_list") is False
        assert take_missed(owner, "_readings") is True

    def test_claiming_a_slot_is_unchanged(self):
        """The instrument panels guard readings with this; a missed reading
        really is better dropped than run late."""
        owner = _Owner()
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is False
        release_slot(owner, "_slot")
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True


class _SlowClient:
    """Answers list_equipment slowly, so a second request collides."""

    def __init__(self, gate):
        self.gate = gate
        self.calls = 0

    def list_equipment(self):
        self.calls += 1
        return []


def _drive(panel, method_name):
    slot = getattr(type(panel), method_name)
    return getattr(slot, "__wrapped__", slot)(panel)


class TestTheEquipmentPanelRunsAMissedRefresh:
    def test_a_collision_is_served_when_the_first_returns(self, qapp):
        """The reported bug: connecting refreshed nothing when it collided."""
        panel = EquipmentPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}

        async def scenario():
            first = asyncio.ensure_future(_drive(panel, "refresh"))
            await asyncio.sleep(0)          # let it take the slot
            # Connecting an instrument asks again while that is out.
            await _drive(panel, "refresh")  # refused, and recorded
            await first

        asyncio.run(scenario())
        panel.deleteLater()
        qapp.processEvents()

        assert client.calls >= 2, (
            "the second request was dropped -- this is why the connected dot "
            f"did not appear; the server was asked {client.calls} time(s)")

    def test_an_uncontended_refresh_asks_once(self, qapp):
        panel = EquipmentPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}

        asyncio.run(_drive(panel, "refresh"))
        panel.deleteLater()
        qapp.processEvents()

        assert client.calls == 1, f"asked {client.calls} times for one refresh"


class TestTheControlPanelIsRefreshedLikeTheOthers:
    def test_it_answers_to_refresh(self, qapp):
        """The name the periodic timer and the tab-change handler look for."""
        panel = ControlPanel()
        try:
            assert hasattr(panel, "refresh"), (
                "the shell skips this tab entirely: sitting on it, nothing "
                "refreshes the list")
        finally:
            panel.deleteLater()
            qapp.processEvents()

    def test_refresh_is_the_list_refresh(self, qapp):
        panel = ControlPanel()
        try:
            assert ControlPanel.refresh is ControlPanel.refresh_equipment_list
        finally:
            panel.deleteLater()
            qapp.processEvents()

    def test_a_collision_is_served_when_the_first_returns(self, qapp):
        panel = ControlPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}

        async def scenario():
            first = asyncio.ensure_future(_drive(panel, "refresh_equipment_list"))
            await asyncio.sleep(0)
            await _drive(panel, "refresh_equipment_list")
            await first

        asyncio.run(scenario())
        panel.deleteLater()
        qapp.processEvents()

        assert client.calls >= 2, (
            f"the second request was dropped; asked {client.calls} time(s)")


class TestASlotLeftByADeadTaskIsTakenAtOnce:
    """Reported after the connected-status fix: "they do update to
    connected now, but it's got quite a delay."

    The refresh task was being destroyed mid-await -- the client log shows
    "Cannot enter into task ... EquipmentPanel.refresh()" and "Task was
    destroyed but it is pending!" -- so its finally never ran and the slot
    stayed held. Every later refresh was then refused for the full
    abandoned_after, 45 seconds, before the panel could redraw.

    Nothing was in flight during those 45 seconds. The holder had already
    finished; only the clock said otherwise.
    """

    @staticmethod
    def _finished_task():
        async def done():
            return None

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(done())
            loop.run_until_complete(task)
            return task
        finally:
            loop.close()

    def test_a_slot_held_by_a_finished_task_is_free(self):
        owner = _Owner()
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True
        # The holder died without releasing: finally never ran.
        owner._slot_task = self._finished_task()

        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True, (
            "waited for the 45s backstop although nothing was running -- "
            "this is the delay before the panel redraws")

    def test_a_slot_held_by_a_live_task_is_still_refused(self):
        """The guard has to keep guarding."""
        owner = _Owner()

        async def scenario():
            assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True
            assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is False

        asyncio.run(scenario())

    def test_the_holder_is_remembered_when_a_task_claims_it(self):
        """Also keeps the task alive: asyncio holds only a weak reference,
        and a task nobody references can be collected mid-await."""
        owner = _Owner()

        async def scenario():
            claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER)
            assert owner._slot_task is asyncio.current_task()

        asyncio.run(scenario())

    def test_a_synchronous_caller_still_works(self):
        """claim_slot is called from plain methods too; no loop, no task."""
        owner = _Owner()
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True
        assert owner._slot_task is None
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is False

    def test_releasing_forgets_the_holder(self):
        owner = _Owner()

        async def scenario():
            claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER)
            release_slot(owner, "_slot")
            assert owner._slot_task is None
            assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True

        asyncio.run(scenario())

    def test_the_time_backstop_still_exists(self):
        """For a holder that is neither finished nor recorded -- a task
        garbage-collected before we could keep a reference, say."""
        owner = _Owner()
        assert claim_slot(owner, "_slot", 0.0) is True
        assert claim_slot(owner, "_slot", 0.0) is True, (
            "the abandonment timeout is gone, so a lost slot is lost for good")


class TestASlotStrandedOnADeadLoopIsAlsoTaken:
    """The first attempt at this fix did not work, and the bench said so:
    "client updated, delay is still there."

    Checking ``task.done()`` was not enough. A task whose loop has gone is
    not done -- it is suspended on an await that will never resume, so it
    stays pending for the life of the process and the slot stays held for
    the full 45s every time.
    """

    @staticmethod
    def _task_on_a_closed_loop():
        async def waits_forever():
            await asyncio.Event().wait()

        loop = asyncio.new_event_loop()
        task = loop.create_task(waits_forever())
        loop.run_until_complete(asyncio.sleep(0))   # let it start and suspend
        loop.close()
        return task

    def test_a_pending_task_on_a_closed_loop_frees_the_slot(self):
        owner = _Owner()
        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True
        stranded = self._task_on_a_closed_loop()
        assert stranded.done() is False, "the premise: it never finishes"
        owner._slot_task = stranded

        assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True, (
            "still waiting out the 45s backstop for a task that cannot run")

    def test_a_task_on_a_different_live_loop_frees_the_slot(self):
        """What the orphan-loop bug produced: tasks on a loop nobody runs."""
        owner = _Owner()
        other = asyncio.new_event_loop()
        try:
            async def waits_forever():
                await asyncio.Event().wait()

            stranded = other.create_task(waits_forever())
            other.run_until_complete(asyncio.sleep(0))

            async def scenario():
                claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER)
                owner._slot_task = stranded
                assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True

            asyncio.run(scenario())
            stranded.cancel()
        finally:
            other.close()

    def test_a_task_on_the_running_loop_still_holds_it(self):
        """The guard must not be defeated by the new check."""
        owner = _Owner()

        async def scenario():
            assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is True
            assert claim_slot(owner, "_slot", REFRESH_ABANDONED_AFTER) is False

        asyncio.run(scenario())


class TestRunNowOrSoonLeavesTheLoopAsItFoundIt:
    """The source of the stranded tasks.

    The startup connection dialog is shown before loop.run_forever(), so a
    bind from it runs with no loop running and takes the asyncio.run()
    branch. asyncio.run() sets the thread's current loop to None on the way
    out -- and every @asyncSlot after that gets a fresh orphan loop that
    nobody runs, so its task sits pending until it is collected.
    """

    def test_the_current_loop_survives(self):
        from client.ui.instruments.base import run_now_or_soon

        made = asyncio.new_event_loop()
        asyncio.set_event_loop(made)
        try:
            async def work():
                return None

            run_now_or_soon(work())

            assert asyncio.get_event_loop_policy().get_event_loop() is made, (
                "the thread was left with no event loop, so every asyncSlot "
                "after this one schedules onto a loop nobody will ever run")
        finally:
            made.close()
            asyncio.set_event_loop(None)

    def test_the_coroutine_still_runs_to_completion(self):
        """Tests bind panels with no loop running and rely on this."""
        from client.ui.instruments.base import run_now_or_soon

        ran = []

        async def work():
            ran.append(True)

        made = asyncio.new_event_loop()
        asyncio.set_event_loop(made)
        try:
            run_now_or_soon(work())
            assert ran == [True]
        finally:
            made.close()
            asyncio.set_event_loop(None)


class TestCoalescingDoesNotRunForEver:
    """The 45-second stall, and it was this.

    The coalescing added earlier ran "again if someone asked while I was
    working" as a while loop. A periodic refresh fires every five seconds
    and records a miss each time, so there was always someone who had
    asked: the loop never exited and held the in-flight slot for as long
    as it ran. claim_slot then refused every other refresh until its 45s
    backstop gave up.

    The giveaway in the log was that the per-server timeout added to catch
    a hanging fetch never fired once, while the 45s warning fired seven
    times. Nothing was hanging. The fetches all finished; this loop kept
    starting another one before the slot could be released.
    """

    @pytest.mark.asyncio
    async def test_it_does_not_loop_while_requests_keep_arriving(self, qapp):
        panel = EquipmentPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}

        # A request arrives during every pass, as the 5s timer does.
        real = panel._refresh_from

        async def refresh_and_ask_again(connections):
            note_missed(panel, "_refresh_started_at")
            return await real(connections)

        panel._refresh_from = refresh_and_ask_again

        slot = type(panel).refresh
        await asyncio.wait_for(
            getattr(slot, "__wrapped__", slot)(panel), timeout=5)

        panel.deleteLater()
        qapp.processEvents()

        assert client.calls <= 2, (
            f"ran {client.calls} passes without releasing the slot; with a "
            f"tick every five seconds this never ends")

    @pytest.mark.asyncio
    async def test_the_slot_is_released_afterwards(self, qapp):
        panel = EquipmentPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}
        note_missed(panel, "_refresh_started_at")

        slot = type(panel).refresh
        await asyncio.wait_for(
            getattr(slot, "__wrapped__", slot)(panel), timeout=5)

        assert panel._refresh_started_at is None, (
            "the slot is still held, so the next refresh waits out the "
            "45s backstop")
        panel.deleteLater()
        qapp.processEvents()

    @pytest.mark.asyncio
    async def test_a_single_miss_is_still_served(self, qapp):
        """Bounding it must not undo the coalescing itself."""
        panel = EquipmentPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}
        note_missed(panel, "_refresh_started_at")

        slot = type(panel).refresh
        await asyncio.wait_for(
            getattr(slot, "__wrapped__", slot)(panel), timeout=5)

        assert client.calls == 2, (
            f"the missed request was not served: {client.calls} pass(es)")
        panel.deleteLater()
        qapp.processEvents()


class TestTheStallReportsItself:
    """Four explanations, three of them wrong. Enough.

    The slot has been reported held for 45s repeatedly, while the
    per-server timeout that would catch a hanging fetch has never fired
    once. The time is not going where I keep looking, so the code says
    where it went rather than leaving it to be guessed at again.
    """

    def test_a_slow_refresh_says_how_long_each_pass_took(self, qapp, caplog):
        import logging

        panel = EquipmentPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}
        panel.SLOW_REFRESH_SEC = 0.0        # everything counts as slow

        with caplog.at_level(logging.WARNING,
                             logger="client.ui.equipment_panel"):
            asyncio.run(_drive(panel, "refresh"))

        panel.deleteLater()
        qapp.processEvents()

        said = [r.getMessage() for r in caplog.records
                if "held the slot" in r.getMessage()]
        assert said, "a slow refresh passed without saying anything"
        assert "first pass" in said[0] and "second pass" in said[0], said[0]

    def test_a_quick_refresh_says_nothing(self, qapp, caplog):
        import logging

        panel = EquipmentPanel()
        client = _SlowClient(None)
        panel.client = client
        panel._connections = lambda: {"srv": client}

        with caplog.at_level(logging.WARNING,
                             logger="client.ui.equipment_panel"):
            asyncio.run(_drive(panel, "refresh"))

        panel.deleteLater()
        qapp.processEvents()

        assert not [r for r in caplog.records if "held the slot" in r.getMessage()]

    def test_the_backstop_says_what_the_holder_was_doing(self):
        """"Assuming the task was destroyed" has been wrong more than once."""
        import logging

        from client.utils.inflight import _describe_holder

        owner = _Owner()
        assert claim_slot(owner, "_slot", 0.0) is True
        owner._slot_task = None

        with caplog_at(logging.WARNING) as records:
            claim_slot(owner, "_slot", 0.0)

        assert any("no task" in r.getMessage() for r in records), (
            [r.getMessage() for r in records])

    def test_a_running_holder_is_described_as_running(self):
        from client.utils.inflight import _describe_holder

        async def scenario():
            return _describe_holder(asyncio.current_task())

        assert "still running" in asyncio.run(scenario())

    def test_a_finished_holder_is_described_as_finished(self):
        from client.utils.inflight import _describe_holder

        async def done():
            return None

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(done())
            loop.run_until_complete(task)
            assert "finished without releasing" in _describe_holder(task)
        finally:
            loop.close()

    def test_no_holder_is_not_an_error(self):
        from client.utils.inflight import _describe_holder

        assert "no task" in _describe_holder(None)


import contextlib
import logging as _logging


@contextlib.contextmanager
def caplog_at(level):
    """Collect records from the inflight logger."""
    records = []

    class Grab(_logging.Handler):
        def emit(self, record):
            records.append(record)

    log = _logging.getLogger("client.utils.inflight")
    handler = Grab(level)
    log.addHandler(handler)
    was = log.level
    log.setLevel(level)
    try:
        yield records
    finally:
        log.removeHandler(handler)
        log.setLevel(was)


class TestTheStallNamesWhatItIsWaitingOn:
    """The outermost frame alone was not enough.

    The first stall to be caught with instrumentation said "a task still
    running (refresh line 528)" -- which is the line awaiting the
    fan-out, and tells us only that it is awaiting the fan-out. It cannot
    tell a slow request from a timeout that never fires from a lock
    nobody releases, and those want different fixes. Following the await
    chain down names the thing at the end of it.
    """

    @pytest.mark.asyncio
    async def test_it_reports_every_frame_in_the_chain(self):
        from client.utils.inflight import _await_chain

        started = asyncio.Event()

        async def innermost():
            started.set()
            await asyncio.Event().wait()      # never returns

        async def middle():
            await innermost()

        async def outermost():
            await middle()

        task = asyncio.ensure_future(outermost())
        await started.wait()
        await asyncio.sleep(0)

        chain = _await_chain(task)
        task.cancel()

        for name in ("outermost", "middle", "innermost"):
            assert name in chain, f"{name!r} missing from {chain!r}"

    @pytest.mark.asyncio
    async def test_it_names_a_future_at_the_end(self):
        """"Waiting on a Future" and "waiting on a coroutine" are
        different problems and used to read the same."""
        from client.utils.inflight import _await_chain

        never = asyncio.get_event_loop().create_future()

        async def waits():
            await never

        task = asyncio.ensure_future(waits())
        await asyncio.sleep(0)

        chain = _await_chain(task)
        task.cancel()
        never.cancel()

        assert "waits" in chain
        assert "Future" in chain, chain

    def test_it_does_not_raise_on_a_task_that_has_finished(self):
        from client.utils.inflight import _await_chain

        async def done():
            return None

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(done())
            loop.run_until_complete(task)
            _await_chain(task)          # must not raise
        finally:
            loop.close()

    def test_it_is_bounded(self):
        """It runs inside a warning; it must not walk for ever."""
        import inspect

        from client.utils.inflight import _await_chain

        assert "limit" in inspect.signature(_await_chain).parameters


class TestTheStallSaysWhichLoopEachSideIsOn:
    """The last unknown about these stalls.

    A fetch completes and the task waiting for it cannot be woken:
    "RuntimeError: Cannot enter into task ... wait_for=<Future finished>".
    That happens when the future and the task belong to different loops.
    Which of the two is the odd one out decides the fix, and the log did
    not say.
    """

    @pytest.mark.asyncio
    async def test_it_says_so_when_the_loops_match(self):
        from client.utils.inflight import _describe_holder

        async def waits():
            await asyncio.Event().wait()

        task = asyncio.ensure_future(waits())
        await asyncio.sleep(0)
        said = _describe_holder(task)
        task.cancel()

        assert "same loop" in said, said

    def test_it_shouts_when_they_differ(self):
        """The case that matters; it used to read the same as a match.

        Two real loops, and the question asked from the second one --
        which is the situation being diagnosed. Not an async test: you
        cannot drive a second loop from inside a running one.
        """
        from client.utils.inflight import _describe_holder

        async def waits():
            await asyncio.Event().wait()

        theirs = asyncio.new_event_loop()
        mine = asyncio.new_event_loop()
        try:
            stranded = theirs.create_task(waits())
            theirs.run_until_complete(asyncio.sleep(0))

            async def ask():
                return _describe_holder(stranded)

            said = mine.run_until_complete(ask())
            stranded.cancel()

            assert "DIFFERENT loops" in said, said
            assert "task on" in said and "asking from" in said
        finally:
            theirs.close()
            mine.close()

    def test_it_copes_with_no_loop_running(self):
        from client.utils.inflight import _describe_holder

        async def waits():
            await asyncio.Event().wait()

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(waits())
            loop.run_until_complete(asyncio.sleep(0))
            said = _describe_holder(task)       # called with no loop running
            task.cancel()
            assert "nothing running here" in said, said
        finally:
            loop.close()
