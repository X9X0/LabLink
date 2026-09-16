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

import logging
from typing import Any, Dict, Optional

import qasync
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel, QWidget

from client.api.client import call_blocking
from client.models.equipment import ConnectionStatus, Equipment
from client.utils.inflight import (READINGS_ABANDONED_AFTER, claim_slot,
                                   release_slot)

logger = logging.getLogger(__name__)

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
        self._interval_ms = self.DEFAULT_INTERVAL_MS
        #: Operator commands in flight, and when the last one finished. Polls
        #: yield to commands: the instrument answers one request at a time,
        #: and a knob turn must not queue behind a background fetch.
        self._commands_in_flight = 0
        self._last_command_finished_at = 0.0

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

    # ------------------------------------------------------------------ #
    # Instrument binding
    # ------------------------------------------------------------------ #

    def set_instrument(self, equipment: Optional[Equipment], client) -> None:
        """Bind the panel to an instrument on a particular server connection.

        Stops any polling of the previous instrument first. Reads the new
        one's capabilities synchronously, as selection always has, so the
        controls are ranged before the first reading arrives.
        """
        self.stop()
        self.equipment = equipment
        self.client = client
        self.capabilities = {}
        if equipment is None or client is None:
            self.clear_instrument()
            return

        try:
            status = client.get_equipment_status(equipment.equipment_id) or {}
            self.capabilities = dict(status.get("capabilities") or {})
        except Exception as e:
            logger.error(f"Could not read capabilities of {equipment.equipment_id}: {e}")
        try:
            self.configure(self.capabilities)
        except Exception as e:
            logger.error(f"Error configuring controls from capabilities: {e}")

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
        finally:
            release_slot(self, "_poll_started_at")

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
            logger.error(f"Error polling {name}: {error}")

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
