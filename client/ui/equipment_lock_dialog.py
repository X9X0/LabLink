"""Showing and managing the lock on a piece of equipment.

An exclusive lock decides who may send control commands to a real instrument.
Until now the client took one silently, and — worse — force-released whatever
it found first, so selecting equipment quietly stole control from whoever had
it. Nothing in the interface said a lock existed at all.

This makes it visible and deliberate: who holds it, from which address, since
when, and how long is left; then take it, release it, or override it with the
holder named in the warning.
"""

import logging
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                             QFrame, QGroupBox, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QVBoxLayout, QWidget)

logger = logging.getLogger(__name__)

# Offered timeouts. A lock that never expires is genuinely useful for a long
# unattended run, and genuinely dangerous when a client dies holding one, so it
# is offered but not the default.
TIMEOUT_CHOICES = [
    ("5 minutes", 300),
    ("15 minutes", 900),
    ("1 hour", 3600),
    ("8 hours", 28800),
    ("No timeout (until released)", 0),
]
DEFAULT_TIMEOUT_INDEX = 0


def describe_holder(status: dict) -> str:
    """One line naming who holds a lock, for a label or a warning."""
    if not status.get("locked"):
        return "not locked"

    who = status.get("username") or "an unidentified session"
    where = status.get("client_ip")
    return f"{who} ({where})" if where else who


def format_remaining(status: dict) -> str:
    """Human-readable time left on a lock."""
    if status.get("timeout_seconds") == 0:
        return "no timeout"
    remaining = status.get("time_remaining")
    if remaining is None:
        return "unknown"
    if remaining <= 0:
        # Worth saying plainly: an expired lock still blocks control until the
        # server reaps it, and on at least one deployment it never did.
        return "expired (still held)"
    minutes, seconds = divmod(int(remaining), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def format_acquired(status: dict) -> str:
    """When the lock was taken, and how long ago."""
    raw = status.get("acquired_at")
    if not raw:
        return "unknown"
    try:
        when = datetime.fromisoformat(raw)
    except ValueError:
        return str(raw)
    # The timestamp comes from the server's clock and is rendered against this
    # machine's. A Pi and a workstation routinely disagree by seconds, and a
    # naive subtraction then shows "-7s ago", which reads as a bug in the lock
    # rather than in the arithmetic. Small skew is reported as "just now";
    # anything larger is called what it is rather than shown as a negative age.
    seconds = int((datetime.now() - when).total_seconds())
    if seconds < -60:
        held = "clock skew between client and server"
    elif seconds < 30:
        held = "just now"
    elif seconds < 3600:
        held = f"{seconds // 60}m ago"
    else:
        held = f"{seconds // 3600}h {(seconds % 3600) // 60}m ago"
    return f"{when.strftime('%H:%M:%S')} ({held})"


class LockStatusWidget(QWidget):
    """A compact, always-visible indication of who holds the lock."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.icon_label = QLabel("🔓")
        layout.addWidget(self.icon_label)

        self.text_label = QLabel("No equipment selected")
        layout.addWidget(self.text_label)
        layout.addStretch()

        self._status: dict = {}

    def update_status(self, status: Optional[dict], is_mine: bool = False):
        """Render a lock status dict from the server."""
        self._status = status or {}

        if status is None:
            self.icon_label.setText("🔓")
            self.text_label.setText("No equipment selected")
            self.text_label.setStyleSheet("color: gray;")
            return

        if not status.get("locked"):
            self.icon_label.setText("🔓")
            self.text_label.setText("Unlocked — no one has control")
            self.text_label.setStyleSheet("color: gray;")
        elif is_mine:
            self.icon_label.setText("🔒")
            self.text_label.setText(
                f"You have control — {format_remaining(status)} remaining"
            )
            self.text_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        else:
            self.icon_label.setText("🔒")
            self.text_label.setText(
                f"Locked by {describe_holder(status)} — {format_remaining(status)}"
            )
            self.text_label.setStyleSheet("color: #e67e22; font-weight: bold;")


class EquipmentLockDialog(QDialog):
    """Take, release or override the lock on one instrument."""

    def __init__(self, client, equipment_id: str, equipment_name: str = "", parent=None):
        super().__init__(parent)
        self.client = client
        self.equipment_id = equipment_id
        self.equipment_name = equipment_name or equipment_id
        self.status: dict = {}

        self.setWindowTitle(f"Equipment control — {self.equipment_name}")
        self.setMinimumWidth(460)
        self._build()
        self.refresh()

        # A lock is a live thing: it counts down, and someone else may take or
        # release it while this is open.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(3000)

    def _build(self):
        layout = QVBoxLayout(self)

        header = QLabel(f"<b>{self.equipment_name}</b>")
        layout.addWidget(header)

        state_box = QGroupBox("Current lock")
        form = QFormLayout()
        self.holder_label = QLabel("—")
        self.ip_label = QLabel("—")
        self.since_label = QLabel("—")
        self.remaining_label = QLabel("—")
        self.mode_label = QLabel("—")
        self.session_label = QLabel("—")
        self.session_label.setStyleSheet("color: gray; font-family: monospace;")
        form.addRow("Held by:", self.holder_label)
        form.addRow("From:", self.ip_label)
        form.addRow("Since:", self.since_label)
        form.addRow("Time left:", self.remaining_label)
        form.addRow("Mode:", self.mode_label)
        form.addRow("Session:", self.session_label)
        state_box.setLayout(form)
        layout.addWidget(state_box)

        take_box = QGroupBox("Take control")
        take_layout = QFormLayout()
        self.timeout_combo = QComboBox()
        for label, seconds in TIMEOUT_CHOICES:
            self.timeout_combo.addItem(label, seconds)
        self.timeout_combo.setCurrentIndex(DEFAULT_TIMEOUT_INDEX)
        self.timeout_combo.setToolTip(
            "The lock releases itself after this long without activity, so a "
            "client that crashes does not hold the instrument forever."
        )
        take_layout.addRow("Release after:", self.timeout_combo)
        take_box.setLayout(take_layout)
        layout.addWidget(take_box)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #666;")
        layout.addWidget(self.hint_label)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        buttons = QHBoxLayout()
        self.acquire_btn = QPushButton("Take control")
        self.acquire_btn.clicked.connect(self._acquire)
        buttons.addWidget(self.acquire_btn)

        self.release_btn = QPushButton("Release")
        self.release_btn.clicked.connect(self._release)
        buttons.addWidget(self.release_btn)

        self.override_btn = QPushButton("Override…")
        self.override_btn.clicked.connect(self._override)
        self.override_btn.setStyleSheet("color: #c0392b;")
        buttons.addWidget(self.override_btn)

        buttons.addStretch()
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    # -- state ---------------------------------------------------------------
    def _is_mine(self) -> bool:
        return bool(self.client) and self.client.holds_lock(self.status)

    def refresh(self):
        """Re-read the lock from the server and update every control."""
        if not self.client:
            return
        try:
            self.status = self.client.get_lock_status(self.equipment_id)
        except Exception as exc:
            logger.error(f"Could not read lock status: {exc}")
            self.hint_label.setText(f"Could not read lock status: {exc}")
            return

        locked = bool(self.status.get("locked"))
        mine = self._is_mine()

        self.holder_label.setText(describe_holder(self.status) if locked else "no one")
        self.ip_label.setText(self.status.get("client_ip") or "—")
        self.since_label.setText(format_acquired(self.status) if locked else "—")
        self.remaining_label.setText(format_remaining(self.status) if locked else "—")
        self.mode_label.setText(str(self.status.get("lock_mode") or "—"))
        self.session_label.setText(str(self.status.get("session_id") or "—"))

        if mine:
            self.holder_label.setText("you")
            self.holder_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        elif locked:
            self.holder_label.setStyleSheet("color: #e67e22; font-weight: bold;")
        else:
            self.holder_label.setStyleSheet("color: gray;")

        self.acquire_btn.setEnabled(not locked)
        self.release_btn.setEnabled(mine)
        self.override_btn.setEnabled(locked and not mine)
        self.timeout_combo.setEnabled(not locked)

        if not locked:
            self.hint_label.setText(
                "No one holds this instrument. Taking control lets you send "
                "commands to it; others can still read from it."
            )
        elif mine:
            self.hint_label.setText(
                "You hold this instrument. Release it when you are finished so "
                "someone else can use it."
            )
        else:
            expired = self.status.get("time_remaining") == 0 and \
                self.status.get("timeout_seconds") != 0
            extra = (" This lock has passed its timeout but is still held, so "
                     "the holder may well be gone." if expired else "")
            self.hint_label.setText(
                f"Held by {describe_holder(self.status)}. You can read from this "
                f"instrument but not control it.{extra}"
            )

    # -- actions -------------------------------------------------------------
    def _acquire(self):
        seconds = self.timeout_combo.currentData()
        try:
            self.client.acquire_lock(self.equipment_id, "exclusive", seconds)
        except Exception as exc:
            QMessageBox.warning(self, "Could not take control", str(exc))
        self.refresh()

    def _release(self):
        try:
            self.client.release_lock(self.equipment_id)
        except Exception as exc:
            QMessageBox.warning(self, "Could not release", str(exc))
        self.refresh()

    def _override(self):
        """Take a lock somebody else holds, having said whose it is."""
        holder = describe_holder(self.status)
        since = format_acquired(self.status)
        remaining = format_remaining(self.status)

        reply = QMessageBox.warning(
            self,
            "Override another user's lock",
            f"<b>{holder}</b> holds {self.equipment_name}.\n\n"
            f"Taken: {since}\n"
            f"Time left: {remaining}\n\n"
            "Overriding takes control away from them. If they are running an "
            "experiment, that is what you will interrupt — and the instrument "
            "may change state as a result.\n\n"
            "Do this only if you know the holder has finished or gone away.\n\n"
            "Override anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.client.release_lock(self.equipment_id, force=True)
            self.client.acquire_lock(
                self.equipment_id, "exclusive", self.timeout_combo.currentData()
            )
            logger.warning(
                f"Overrode lock on {self.equipment_id} previously held by {holder}"
            )
        except Exception as exc:
            QMessageBox.warning(self, "Override failed", str(exc))
        self.refresh()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
