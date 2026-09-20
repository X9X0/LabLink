"""The contract every instrument panel follows.

The Control tab used to drive everything as if it were a power supply, and
both of the polling storms that shipped came from that: one panel polled
every instrument for volts and amps, so an instrument that could not answer
was asked anyway, several times a second, until the event loop starved and
*other* instruments stopped connecting. Here each panel declares what it
polls and how fast, owns its own timer, and stops itself on a permanent
refusal. The shell never assumes an instrument can answer anything.

Panels are self-contained -- own client, own timer -- so detaching one into
its own window (issue #248) is reparenting rather than a rewrite.
"""

import inspect
import logging
import time
from typing import Any, Dict, NamedTuple, Optional, Set

import qasync
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (QAbstractSpinBox, QApplication, QDoubleSpinBox,
                             QGroupBox, QHBoxLayout, QLabel, QWidget)

from client.api.client import call_blocking
from client.models.equipment import ConnectionStatus, Equipment
from client.utils.inflight import (READINGS_ABANDONED_AFTER, claim_slot,
                                   release_slot)

logger = logging.getLogger(__name__)


class Commanded(NamedTuple):
    """What a panel last asked one control to be, and when it asked."""

    value: Any
    at: float


def run_now_or_soon(coro):
    """Run a coroutine on the running event loop, or to completion if none is.

    The application always has qasync's loop running, so this schedules the
    work and returns at once -- the GUI thread never waits on a server
    request. Tests bind panels with no loop running; there the coroutine
    runs to completion before this returns, so a test can assert on what
    the binding did as it always could.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        return loop.create_task(coro)
    asyncio.run(coro)
    return None

#: What a panel may declare it polls. ``None`` means the panel never polls.
POLL_READINGS = "readings"
POLL_MEASUREMENTS = "measurements"
POLL_STATE = "state"
POLL_KINDS = (POLL_READINGS, POLL_MEASUREMENTS, POLL_STATE, None)

#: Give the instrument a moment after selection (and lock acquisition) before
#: the first poll. A B&K supply answers the first serial query after a lock
#: with an empty line if it is asked immediately.
SETTLE_MS = 500


class InstrumentPanel(QWidget):
    """Base class for one instrument type's control panel.

    Subclasses set :attr:`POLLS` and :attr:`DEFAULT_INTERVAL_MS`, build their
    controls in :meth:`_build_ui`, implement :meth:`poll` for whatever they
    declared, and gate their command widgets in :meth:`set_controls_enabled`.
    Everything about *when* to poll, and when to stop, lives here.
    """

    #: One of :data:`POLL_KINDS`. The shell reads it only to describe the
    #: panel; the base class uses it to decide whether to run a timer at all.
    POLLS: Optional[str] = None

    #: The panel's own cadence. The operator can override it, and the override
    #: is remembered per equipment type, never applied to another type.
    DEFAULT_INTERVAL_MS: int = 1000

    #: The settings key this panel's override is remembered under.
    SETTINGS_TYPE: str = "generic"

    #: Something the operator needs told about, shown by the shell in the
    #: main window's status bar.
    status_message = pyqtSignal(str)

    #: The server no longer holds this instrument (404). The shell refreshes
    #: its list; the panel has already stopped polling.
    equipment_gone = pyqtSignal(str)

    #: Emitted when the timer starts or stops, with the new state. Lets a
    #: test -- or a detached window -- see the polling contract being kept.
    polling_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = None
        self.equipment: Optional[Equipment] = None
        self.capabilities: Dict[str, Any] = {}

        #: When the in-flight poll started, or None. A time rather than a
        #: flag so a destroyed task cannot stop the readings for good.
        self._poll_started_at = None
        self._poll_failures = 0
        self._backoff_ms = 0
        self._interval_ms = self.DEFAULT_INTERVAL_MS
        #: Operator commands in flight, and when the last one finished. Polls
        #: yield to commands: the instrument answers one request at a time,
        #: and a knob turn must not queue behind a background fetch.
        self._commands_in_flight = 0
        self._last_command_finished_at = 0.0
        #: Controls this panel has commanded and the instrument has not yet
        #: been seen to agree with. See :meth:`commanded`.
        self._pending: Dict[str, Commanded] = {}
        #: The value each control should end up at, and which controls have
        #: a write in flight. See :meth:`write_latest`.
        self._write_targets: Dict[str, Any] = {}
        self._writing: Set[str] = set()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        # The settle delay before the first poll. A child timer rather than
        # QTimer.singleShot with a lambda: the lambda would keep a reference
        # to a panel that may since have been deselected or destroyed, and
        # firing into a dead widget is undefined. A child timer dies with
        # its parent and is stopped by stop().
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._start_now)

        self.refresh_spinbox: Optional[QDoubleSpinBox] = None
        self._build_ui()
        self._load_remembered_interval()

    # ------------------------------------------------------------------ #
    # What subclasses provide
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        """Create the panel's widgets. Called once from ``__init__``."""

    async def poll(self):
        """Fetch whatever :attr:`POLLS` says and update the widgets.

        Runs off the Qt thread's event loop; use ``call_blocking`` for client
        calls. Raise to report a fault: the base class decides whether it is
        transient (keep polling) or permanent (stop).
        """

    def configure(self, capabilities: Dict[str, Any]):
        """Adapt the controls to a newly selected instrument's capabilities."""

    def set_controls_enabled(self, enabled: bool):
        """Enable or disable the widgets that command the instrument.

        Readings stay live either way: not holding the lock means you cannot
        change the instrument, not that you cannot watch it.
        """

    def show_not_connected(self):
        """Blank the readouts; the server does not hold this instrument open."""

    def show_unsupported(self):
        """Blank the readouts; this instrument cannot answer what we poll."""

    def clear_instrument(self):
        """Forget the current instrument's values (called on deselect)."""

    async def refresh_settings(self):
        """Read the instrument's own settings onto the controls.

        Runs off the GUI thread after binding, never inside it: on a DS1000Z a
        full state read is some thirty SCPI queries, each queued behind the
        pollers, and doing that synchronously froze the window for as long as
        it took -- twenty seconds on the bench. Panels implement this with
        ``await self.send(...)`` and block widget signals while setting them.
        """

    # ------------------------------------------------------------------ #
    # Instrument binding
    # ------------------------------------------------------------------ #

    def set_instrument(self, equipment: Optional[Equipment], client) -> None:
        """Bind the panel to an instrument on a particular server connection.

        Stops any polling of the previous instrument first and binds at
        once. Reading the instrument -- its capabilities, then its settings --
        happens off the GUI thread (:meth:`_bind`): every one of those is a
        server request that queues behind whatever the instrument is already
        doing, and doing them synchronously froze the window for as long as
        the queue took. Twenty seconds, on a bench with a DS1000Z.
        """
        self.stop()
        self.commit_typed_values_on_enter_only()
        # What was commanded belonged to the instrument being left. Carried
        # over, it would suppress the new one's readings.
        self.forget_commanded()
        self.equipment = equipment
        self.client = client
        self.capabilities = {}
        if equipment is None or client is None:
            self.clear_instrument()
            return
        run_now_or_soon(self._bind(equipment, client))

    def commit_typed_values_on_enter_only(self) -> None:
        """Report a typed value when the operator has finished typing it.

        A QDoubleSpinBox emits ``valueChanged`` on every keystroke by
        default, so typing 12.5 into a supply's voltage field emitted 1,
        then 12, then 12.5 -- and the panel sends each one to the
        instrument. The supply really was commanded to 1 V and 12 V on the
        way to 12.5. On a live bench that is not a cosmetic bug.

        Turning keyboard tracking off makes Qt emit once, when the edit is
        finished: Enter, Tab, focus leaving the field, or a press of the
        arrows or step buttons. Applied here rather than in each panel so a
        panel written later cannot forget it, and at binding time because
        that is the moment a panel becomes able to command hardware.
        """
        for box in self.findChildren(QAbstractSpinBox):
            box.setKeyboardTracking(False)

    def editing_in_progress(self) -> bool:
        """Whether the operator is part-way through typing a value.

        Polled readings overwrite the setpoint widgets, which while someone
        is typing replaces what they have entered so far -- so a half-typed
        number could be left in the field and then committed.
        """
        focused = QApplication.focusWidget()
        if focused is None:
            return False
        return focused is self or self.isAncestorOf(focused)

    # ------------------------------------------------------------------ #
    # Commands against readings
    # ------------------------------------------------------------------ #
    #
    # A panel both commands an instrument and polls it, and the two are not
    # ordered against each other. Sending is asynchronous; the poll keeps
    # running; so a reading taken *before* a command routinely arrives
    # *after* it, carrying the value from before. Believing it walks the
    # control back to where it was -- and on the next operator nudge the
    # panel sends that stale value, moving the instrument to match the
    # display. The supply panel hit this three times, on three widgets, and
    # was patched three times with a two-second "ignore readings" window per
    # widget.
    #
    # A window is the wrong shape for it. It ignores the instrument for a
    # fixed time whether or not the command landed, so a knob turned on the
    # front panel cannot reach the display for two seconds, and a command
    # the instrument *refused* is hidden for two seconds and then snaps.
    #
    # What the panel actually knows is narrower: "I asked for this and have
    # not yet seen the instrument agree." That is what these record. A
    # reading that confirms the commanded value clears the entry at once --
    # no waiting -- and readings rule again. A reading that contradicts it
    # is ignored until the instrument has had long enough to have taken it,
    # after which the instrument wins and says so in the log, because a
    # command that never landed is something the operator needs to see.

    #: How long to keep believing the panel over the instrument while the
    #: two disagree. Long enough to cover a command in flight and the
    #: readings already in flight behind it; short enough that a command
    #: that never landed does not stay hidden.
    PENDING_TIMEOUT_SEC = 3.0

    #: How far a reading may sit from what was commanded and still count as
    #: agreement. Supplies round to their own resolution -- ask a 0.1 V
    #: supply for 22.19 and it reports 22.2 -- and an exact comparison would
    #: never confirm, leaving every command to time out instead.
    #:
    #: It has to sit in a window with a floor and a ceiling, and the first
    #: version of this got the ceiling wrong.
    #:
    #: The floor is half the instrument's resolution: 0.05 for the 0.1 V
    #: setpoints these supplies store. Below that, rounding never confirms.
    #:
    #: The ceiling is the smallest step the operator can command, which for
    #: a dial notch is 0.10. At 0.1 the tolerance *equalled* the notch, so
    #: a reading exactly one notch behind counted as agreement -- and by
    #: floating point it did so about half the time, which is why the
    #: mismatch was intermittent. Accepting it wrote the stale value back
    #: into the field, and since the next notch is computed from the field,
    #: the scroll rewound a notch each time it happened.
    CONFIRM_TOLERANCE = 0.06

    def commanded(self, control: str, value: Any) -> None:
        """Record that this panel has asked ``control`` to become ``value``.

        Call it synchronously, at the moment the operator acts, rather than
        inside the coroutine that sends: the readings that carry the stale
        value are already in flight by then.
        """
        self._pending[control] = Commanded(value, time.monotonic())

    def may_show(self, control: str, reported: Any) -> bool:
        """Whether a reading may be shown, or the commanded value still stands.

        Consumes one reading for that control, so call it once per reading:
        it is what clears the pending entry when the instrument agrees.
        """
        pending = self._pending.get(control)
        if pending is None:
            return True                 # nothing commanded; the instrument rules
        if reported is None:
            return False                # says nothing, so changes nothing
        if self._confirms(pending.value, reported):
            del self._pending[control]
            return True
        if time.monotonic() - pending.at >= self.PENDING_TIMEOUT_SEC:
            del self._pending[control]
            logger.warning(
                f"{self.describe()}: asked {control} for {pending.value!r} and it "
                f"still reads {reported!r} after {self.PENDING_TIMEOUT_SEC:g}s; "
                f"showing what the instrument says"
            )
            return True
        return False

    # ------------------------------------------------------------------ #
    # One write at a time, carrying the latest value
    # ------------------------------------------------------------------ #

    def write_latest(self, control: str, value: Any, send) -> None:
        """Send ``value`` for ``control``, coalescing while one is in flight.

        A continuous control sends on every change, and a dial sends on
        every notch. Fired straight at the server that is one HTTP request
        per notch, against an instrument that answers one at a time -- a
        B&K supply on a 9600-baud serial line. Scrolled across a wide
        range, the requests pile up, the server's bounded instrument queue
        refuses the overflow, and those notches are simply lost::

            19:25:36,860  Error sending voltage command: 503 Service Unavailable
            19:25:36,879  Error sending voltage command: 503 Service Unavailable
            19:25:36,895  Error sending voltage command: 503 Service Unavailable
            19:25:36,913  Error sending voltage command: 503 Service Unavailable
            19:25:44,201  asked voltage for 27.1 and it still reads 16.1 after 3s

        The operator had scrolled to 27.1 V and the supply sat at 16.1 V.

        Nothing wanted those intermediate values anyway: while a knob is
        moving, only where it stops matters. So each control keeps one
        target and one writer. A change made while a write is out replaces
        the target rather than starting a second write, and the writer
        picks it up when the current one returns. Twenty notches become
        two or three writes, in order, ending on the value the operator
        actually chose -- which unordered concurrent writes could not
        guarantee even when none of them was refused.
        """
        self._write_targets[control] = value
        if control in self._writing:
            return                  # the writer already running will take it
        self._writing.add(control)
        run_now_or_soon(self._drain_writes(control, send))

    async def _drain_writes(self, control: str, send) -> None:
        """Write the target for ``control`` until nothing new has arrived."""
        try:
            while control in self._write_targets:
                value = self._write_targets.pop(control)
                result = send(value)
                # The panels' senders are asyncSlots, which return a task.
                # Awaiting it is what serialises the writes; a plain
                # function (a test's recorder) has nothing to wait for.
                if inspect.isawaitable(result):
                    await result
        except Exception as e:
            logger.error(f"{self.describe()}: writing {control} failed: {e}")
        finally:
            self._writing.discard(control)
            self._write_targets.pop(control, None)

    def writes_in_flight(self) -> bool:
        """Whether any control still has a value on its way to the instrument."""
        return bool(self._writing)

    def forget_commanded(self, control: Optional[str] = None) -> None:
        """Drop pending state -- for one control, or all of them."""
        if control is None:
            self._pending.clear()
        else:
            self._pending.pop(control, None)

    def _confirms(self, wanted: Any, reported: Any) -> bool:
        """Whether a reading agrees with what was commanded."""
        if isinstance(wanted, bool) or isinstance(reported, bool):
            return bool(reported) is bool(wanted)
        try:
            return abs(float(reported) - float(wanted)) <= self.CONFIRM_TOLERANCE
        except (TypeError, ValueError):
            return reported == wanted

    async def _bind(self, equipment: Equipment, client) -> None:
        """Range the controls from the instrument's capabilities, then its settings."""
        try:
            status = await call_blocking(client.get_equipment_status, equipment.equipment_id)
            capabilities = dict((status or {}).get("capabilities") or {})
        except Exception as e:
            logger.error(f"Could not read capabilities of {equipment.equipment_id}: {e}")
            capabilities = {}
        if self.equipment is not equipment:
            return  # the selection moved on while we were reading
        self.capabilities = capabilities
        try:
            self.configure(self.capabilities)
        except Exception as e:
            logger.error(f"Error configuring controls from capabilities: {e}")
        await self._refresh_settings_guarded()

    def _schedule_refresh_settings(self):
        """Run :meth:`refresh_settings` off the GUI thread."""
        run_now_or_soon(self._refresh_settings_guarded())

    async def _refresh_settings_guarded(self):
        equipment = self.equipment
        if equipment is None or self.client is None:
            return
        try:
            await self.refresh_settings()
        except Exception as e:
            if equipment is self.equipment:
                logger.warning(f"Could not read settings from {self.equipment_id}: {e}")

    @property
    def equipment_id(self) -> Optional[str]:
        return getattr(self.equipment, "equipment_id", None)

    def is_connected(self) -> bool:
        """Whether the server currently holds the bound instrument open.

        An older server sends no status at all and only lists what is open,
        so the absence of a status is treated as connected.
        """
        if self.equipment is None:
            return False
        status = getattr(self.equipment, "connection_status", None)
        return status is None or status == ConnectionStatus.CONNECTED

    def mark_disconnected(self):
        """Stop trusting a cached "connected" that the server contradicts.

        :meth:`is_connected` reads the status the list was populated with, so
        without this the next start would poll straight back into the 404.
        """
        if self.equipment is not None:
            try:
                self.equipment.connection_status = ConnectionStatus.DISCONNECTED
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Cadence
    # ------------------------------------------------------------------ #

    def interval_ms(self) -> int:
        """The current poll interval, never zero."""
        return max(int(self._interval_ms), 10)

    def set_interval_ms(self, interval_ms: int, remember: bool = True):
        """Change the cadence; a running timer picks it up at once."""
        self._interval_ms = max(int(interval_ms), 10)
        # An explicit cadence from the operator outranks a back-off.
        self._poll_failures = 0
        self._backoff_ms = 0
        if self.poll_timer.isActive():
            self.poll_timer.setInterval(self.interval_ms())
        if remember:
            self._remember_interval()

    def set_rate_hz(self, rate_hz: float, remember: bool = True):
        rate = max(float(rate_hz), 0.1)
        self.set_interval_ms(int(round(1000 / rate)), remember=remember)

    def rate_hz(self) -> float:
        return 1000.0 / self.interval_ms()

    def _load_remembered_interval(self):
        try:
            from client.utils.settings import SettingsManager

            rate = SettingsManager().get_reading_rate_for(
                self.SETTINGS_TYPE, 1000.0 / self.DEFAULT_INTERVAL_MS
            )
            self.set_rate_hz(rate, remember=False)
        except Exception as e:
            logger.debug(f"Could not load the remembered rate: {e}")
        if self.refresh_spinbox is not None:
            self.refresh_spinbox.blockSignals(True)
            self.refresh_spinbox.setValue(round(self.rate_hz(), 1))
            self.refresh_spinbox.blockSignals(False)

    def _remember_interval(self):
        try:
            from client.utils.settings import SettingsManager

            SettingsManager().set_reading_rate_for(self.SETTINGS_TYPE, self.rate_hz())
        except Exception as e:
            logger.debug(f"Could not save the reading rate: {e}")

    def _create_rate_control(self, tooltip: str = "How often to query the instrument") -> QGroupBox:
        """A refresh-rate control wired to this panel's timer.

        Placed by the subclass wherever suits its layout. Remembered per
        equipment type, so the supply's 10 Hz is not imposed on the scope.
        """
        group = QGroupBox("Refresh Rate")
        layout = QHBoxLayout(group)
        layout.addWidget(QLabel("Update Rate (Hz):"))
        self.refresh_spinbox = QDoubleSpinBox()
        self.refresh_spinbox.setMinimum(0.1)
        self.refresh_spinbox.setMaximum(10.0)
        self.refresh_spinbox.setDecimals(1)
        self.refresh_spinbox.setSingleStep(0.1)
        self.refresh_spinbox.setValue(round(1000.0 / self.DEFAULT_INTERVAL_MS, 1))
        self.refresh_spinbox.setToolTip(tooltip)
        self.refresh_spinbox.valueChanged.connect(self._on_refresh_changed)
        layout.addWidget(self.refresh_spinbox)
        return group

    def _on_refresh_changed(self, value: float):
        """The operator chose a rate: use it now and remember it for this type."""
        self.set_rate_hz(value, remember=True)

    # ------------------------------------------------------------------ #
    # Polling lifecycle
    # ------------------------------------------------------------------ #

    def start(self):
        """Begin polling the bound instrument, if it can be polled at all.

        Never starts for an instrument the server has not opened: polling one
        404s at the reading rate, and that churn was enough to stop the
        connect task ever being entered.
        """
        self._settle_timer.stop()
        # A missing client is not a reason to refuse: the tick itself checks
        # for one, and a panel constructed without a connection (as the GUI
        # tests do) still has to honour its cadence.
        if self.POLLS is None or self.equipment is None:
            return
        if not self.is_connected():
            self.stop()
            self.show_not_connected()
            return
        self._settle_timer.start(SETTLE_MS)

    def _start_now(self):
        if self.equipment is None or not self.is_connected():
            return  # deselected during the settle delay
        self.poll_timer.start(self.interval_ms())
        self.polling_changed.emit(True)

    def stop(self):
        """Stop polling. Safe to call when nothing is running."""
        self._settle_timer.stop()
        if self.poll_timer.isActive():
            self.poll_timer.stop()
            self.polling_changed.emit(False)

    def is_polling(self) -> bool:
        return self.poll_timer.isActive() or self._settle_timer.isActive()

    @qasync.asyncSlot()
    async def _poll(self):
        """One timer tick: run :meth:`poll` and interpret any failure."""
        if self.equipment is None or self.client is None:
            return
        # Commands first. A background fetch that can take seconds on a slow
        # instrument must not be issued while the operator's command is
        # waiting, nor right after it -- the instrument is still settling.
        if self.commands_pending():
            return
        # A tick in flight when the selection changed would otherwise 404
        # and keep the loop too busy for the connect task to start.
        if not self.is_connected():
            self.stop()
            return
        # The timer can outpace a slow server; skip ticks while a request is
        # still out instead of queueing them. One held long past any plausible
        # round trip is treated as lost.
        if not claim_slot(self, "_poll_started_at", READINGS_ABANDONED_AFTER):
            return
        try:
            await self.poll()
        except Exception as e:
            self._handle_poll_error(e)
        else:
            self._poll_succeeded()
        finally:
            release_slot(self, "_poll_started_at")

    #: A poll that keeps failing is retried on a doubling interval, up to this.
    #: Ten failing polls at the panel's 2 s cadence used to be ten more entries
    #: in the instrument's queue; with a bad command costing a ten-second
    #: timeout each, the client was generating backlog faster than the server
    #: could drain it, and the bench DS1054Z reached a 205 s queue.
    POLL_BACKOFF_CAP_MS = 30_000

    def _poll_succeeded(self):
        """Give up any back-off: the instrument is answering again."""
        if self._backoff_ms:
            logger.info("%s is answering again; back to %d ms polling",
                        self.equipment_id or "?", self.interval_ms())
        self._poll_failures = 0
        self._backoff_ms = 0
        if self.poll_timer.isActive():
            self.poll_timer.setInterval(self.interval_ms())

    def _back_off(self):
        """Double the poll interval, to a cap, after a failed poll.

        The operator's chosen cadence in ``_interval_ms`` is left alone, so
        recovery goes straight back to it.
        """
        self._poll_failures += 1
        backoff = min(self.interval_ms() * (2 ** self._poll_failures),
                      self.POLL_BACKOFF_CAP_MS)
        if backoff <= self.interval_ms() or backoff == self._backoff_ms:
            return
        self._backoff_ms = backoff
        if self.poll_timer.isActive():
            self.poll_timer.setInterval(backoff)
        logger.info("%s: %d consecutive failed polls; slowing to %d ms",
                    self.equipment_id or "?", self._poll_failures, backoff)

    def _handle_poll_error(self, error: Exception):
        name = self.equipment_id or "?"
        if self._equipment_is_gone(error):
            # Disconnected, or the server restarted, which an update does.
            # Retrying cannot fix that, and asking again ten times a second
            # is the 404 storm that starves the connect task.
            logger.info("Equipment %s is no longer open on the server; stopping", name)
            self.stop()
            self.mark_disconnected()
            self.show_not_connected()
            self.equipment_gone.emit(name)
        elif self._readings_unsupported(error):
            # A permanent "not for this instrument", not a fault. Polling
            # anyway produced the same storm a stale id did.
            logger.info("%s cannot answer this panel's poll; stopping", name)
            self.stop()
            self.show_unsupported()
        else:
            # Transient: a timeout, a 503 from an instrument with a backlog, a
            # serial hiccup. Keep polling, but not at full speed -- asking
            # again every tick is what turns one slow command into a queue
            # minutes deep.
            logger.error(f"Error polling {name}: {error}")
            self._back_off()

    @staticmethod
    def _equipment_is_gone(error) -> bool:
        """Whether the server answered "I do not have that instrument".

        Narrow on purpose: a timeout, a dropped connection or a serial hiccup
        is transient and should keep polling. Only a 404 means the id itself
        is stale.
        """
        response = getattr(error, "response", None)
        return getattr(response, "status_code", None) == 404

    @staticmethod
    def _readings_unsupported(error) -> bool:
        """Whether the server answered "that instrument cannot do this".

        501 is what the server sends for an instrument whose driver lacks the
        capability; 405 is the same answer from a server that routes it
        differently. Neither can be fixed by asking again. Deliberately not
        every 5xx: a 500 or 503 means the server is unwell, and a supply
        should keep reading through one.
        """
        response = getattr(error, "response", None)
        return getattr(response, "status_code", None) in (405, 501)

    # ------------------------------------------------------------------ #
    # Helpers for subclasses
    # ------------------------------------------------------------------ #

    #: Polls stay quiet for this long after an operator command completes,
    #: so a run of knob clicks is not interleaved with fetches.
    COMMAND_COOLDOWN_S = 0.75

    def commands_pending(self) -> bool:
        """Whether a command is in flight or has just finished."""
        import time

        if self._commands_in_flight > 0:
            return True
        return (time.monotonic() - self._last_command_finished_at) < self.COMMAND_COOLDOWN_S

    async def send(self, command: str, parameters: Optional[Dict[str, Any]] = None,
                   priority: bool = True) -> Any:
        """Send a driver command to the bound instrument, off the GUI thread.

        ``priority`` marks an operator command: polls are held back while it
        is out and for a short cooldown afterwards. Polls call with
        ``priority=False`` so they do not hold each other back.

        Raises RuntimeError when the server reports the command failed, so a
        subclass can decide whether that is worth telling the operator.
        """
        if self.equipment is None or self.client is None:
            return None
        if priority:
            self._commands_in_flight += 1
        try:
            result = await call_blocking(
                self.client.send_command, self.equipment.equipment_id, command,
                parameters or {},
            )
        finally:
            if priority:
                import time

                self._commands_in_flight -= 1
                self._last_command_finished_at = time.monotonic()
        if isinstance(result, dict) and result.get("success") is False:
            raise RuntimeError(result.get("error") or f"{command} failed")
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return result

    def describe(self) -> str:
        """One line naming the instrument, for headers and messages."""
        e = self.equipment
        if e is None:
            return "No equipment selected"
        return f"{e.name} - {e.manufacturer} {e.model}"
