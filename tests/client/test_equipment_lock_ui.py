"""Equipment locks, made visible and deliberate.

An exclusive lock decides who may command a real instrument. The client used
to take one silently and — before that — force-release whatever it found, so
selecting equipment quietly stole control from whoever had it. Nothing on
screen said a lock existed, which made "why will it not let me set anything"
unanswerable from the interface, and made a stolen lock untraceable.

These cover the parts a person relies on: that the holder is named, that the
countdown is honest about an expired-but-held lock, that overriding cannot
happen without a warning naming the holder, and that selecting equipment no
longer steals.
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

pytest.importorskip("PyQt6")

from client.ui.equipment_lock_dialog import (  # noqa: E402
    TIMEOUT_CHOICES,
    EquipmentLockDialog,
    LockStatusWidget,
    describe_holder,
    format_acquired,
    format_remaining,
)


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def status(**overrides):
    base = {
        "locked": True,
        "username": "alice",
        "client_ip": "10.10.0.77",
        "acquired_at": datetime.now().isoformat(),
        "time_remaining": 245.0,
        "timeout_seconds": 300,
        "session_id": "theirs",
        "lock_mode": "exclusive",
    }
    base.update(overrides)
    return base


class TestDescribeHolder:
    """A session id answers none of the questions a person actually has."""

    def test_names_the_user_and_address(self):
        assert describe_holder(status()) == "alice (10.10.0.77)"

    def test_user_alone_when_there_is_no_address(self):
        assert describe_holder(status(client_ip=None)) == "alice"

    def test_says_so_when_the_holder_is_anonymous(self):
        """Better than printing a uuid at somebody."""
        assert describe_holder(status(username=None)) == \
            "an unidentified session (10.10.0.77)"

    def test_unlocked(self):
        assert describe_holder({"locked": False}) == "not locked"


class TestFormatRemaining:
    def test_counts_down(self):
        assert format_remaining(status(time_remaining=245.0)) == "4m 5s"

    def test_hours(self):
        assert format_remaining(status(time_remaining=7300.0)) == "2h 1m"

    def test_seconds(self):
        assert format_remaining(status(time_remaining=9.0)) == "9s"

    def test_no_timeout_is_not_zero_time(self):
        assert format_remaining(status(timeout_seconds=0, time_remaining=None)) \
            == "no timeout"

    def test_expired_but_still_held_says_so(self):
        """The distinction that matters when a lock will not go away.

        A lock past its timeout still blocks control until the server reaps
        it, and on at least one deployment the reaper never ran. "0s" would
        suggest waiting; this says what is actually true.
        """
        assert format_remaining(status(time_remaining=0.0)) == "expired (still held)"


class TestFormatAcquired:
    def test_reports_age(self):
        when = (datetime.now() - timedelta(minutes=5)).isoformat()
        assert "5m ago" in format_acquired({"acquired_at": when})

    def test_clock_skew_is_not_shown_as_a_negative_age(self):
        """The server is a Pi and the client is a workstation.

        They routinely disagree by seconds. Subtracting naively printed
        "(-7s ago)", which reads as a broken lock rather than a clock.
        """
        ahead = (datetime.now() + timedelta(hours=2)).isoformat()
        rendered = format_acquired({"acquired_at": ahead})

        assert "-" not in rendered.split("(")[1]
        assert "skew" in rendered

    def test_small_skew_is_just_now(self):
        ahead = (datetime.now() + timedelta(seconds=5)).isoformat()
        assert "just now" in format_acquired({"acquired_at": ahead})

    def test_missing_and_malformed_do_not_raise(self):
        assert format_acquired({}) == "unknown"
        assert format_acquired({"acquired_at": "not-a-date"}) == "not-a-date"


class TestLockStatusWidget:
    def test_unlocked(self, app):
        w = LockStatusWidget()
        w.update_status({"locked": False})

        assert "Unlocked" in w.text_label.text()

    def test_mine_says_so_distinctly(self, app):
        w = LockStatusWidget()
        w.update_status(status(session_id="mine"), is_mine=True)

        assert "You have control" in w.text_label.text()
        assert "bold" in w.text_label.styleSheet()

    def test_someone_elses_names_them(self, app):
        w = LockStatusWidget()
        w.update_status(status(), is_mine=False)

        assert "alice" in w.text_label.text()
        assert "10.10.0.77" in w.text_label.text()


class TestLockDialog:
    def _dialog(self, st, mine=False):
        client = MagicMock()
        client.get_lock_status.return_value = st
        client.holds_lock.return_value = mine
        dialog = EquipmentLockDialog(client, "ps_1", "B&K 1902B")
        dialog._timer.stop()          # no background refresh during a test
        return dialog, client

    def test_shows_every_fact_about_a_foreign_lock(self, app):
        d, _ = self._dialog(status())

        assert d.holder_label.text() == "alice (10.10.0.77)"
        assert d.ip_label.text() == "10.10.0.77"
        assert "4m 5s" in d.remaining_label.text()
        assert d.session_label.text() == "theirs"

    def test_buttons_match_a_foreign_lock(self, app):
        d, _ = self._dialog(status())

        assert not d.acquire_btn.isEnabled(), "cannot take a held lock"
        assert not d.release_btn.isEnabled(), "cannot release someone else's"
        assert d.override_btn.isEnabled(), "override is the way through"

    def test_buttons_match_my_own_lock(self, app):
        d, _ = self._dialog(status(session_id="mine"), mine=True)

        assert not d.acquire_btn.isEnabled()
        assert d.release_btn.isEnabled()
        assert not d.override_btn.isEnabled(), "no need to override yourself"

    def test_buttons_match_an_unlocked_instrument(self, app):
        d, _ = self._dialog({"locked": False})

        assert d.acquire_btn.isEnabled()
        assert not d.release_btn.isEnabled()
        assert not d.override_btn.isEnabled()

    def test_acquire_passes_the_chosen_timeout(self, app):
        d, client = self._dialog({"locked": False})
        d.timeout_combo.setCurrentIndex(
            [i for i, (_, s) in enumerate(TIMEOUT_CHOICES) if s == 3600][0]
        )

        d._acquire()

        client.acquire_lock.assert_called_once_with("ps_1", "exclusive", 3600)

    def test_no_timeout_is_offered(self):
        """Useful for a long unattended run; deliberately not the default."""
        assert 0 in [seconds for _, seconds in TIMEOUT_CHOICES]
        assert TIMEOUT_CHOICES[0][1] != 0

    def test_override_needs_confirmation_and_names_the_holder(self, app):
        """Taking control from a person is not a thing to do silently."""
        d, client = self._dialog(status())

        with patch("client.ui.equipment_lock_dialog.QMessageBox") as box:
            box.StandardButton.No = 0
            box.StandardButton.Yes = 1
            box.warning.return_value = 0          # the user declines
            d._override()

        assert box.warning.called, "override must warn"
        message = box.warning.call_args[0][2]
        assert "alice" in message, "the warning must name the holder"
        assert "interrupt" in message.lower()
        client.release_lock.assert_not_called()
        client.acquire_lock.assert_not_called()

    def test_declining_the_override_changes_nothing(self, app):
        d, client = self._dialog(status())

        with patch("client.ui.equipment_lock_dialog.QMessageBox") as box:
            box.StandardButton.No = 0
            box.StandardButton.Yes = 1
            box.warning.return_value = 0
            d._override()

        client.release_lock.assert_not_called()

    def test_accepting_the_override_forces_and_retakes(self, app):
        d, client = self._dialog(status())

        with patch("client.ui.equipment_lock_dialog.QMessageBox") as box:
            box.StandardButton.No = 0
            box.StandardButton.Yes = 1
            box.warning.return_value = 1          # the user confirms
            d._override()

        client.release_lock.assert_called_once_with("ps_1", force=True)
        assert client.acquire_lock.called


class TestSelectingEquipmentDoesNotSteal:
    """The behaviour this feature exists to remove.

    control_panel used to call release_lock(force=True) before acquiring, on
    every selection. That silently took control from whoever held it, which is
    why locks appeared not to work in the GUI at all.
    """

    def test_no_unconditional_force_release_in_the_selection_path(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2]
                  / "client" / "ui" / "control_panel.py").read_text(encoding="utf-8")
        selection = source.split("def _on_equipment_selected", 1)[1]

        assert "force=True" not in selection, (
            "the equipment selection path force-releases a lock again; "
            "overriding belongs in the lock dialog, where the holder is named"
        )

    def test_selection_checks_who_holds_it_first(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2]
                  / "client" / "ui" / "control_panel.py").read_text(encoding="utf-8")
        selection = source.split("def _on_equipment_selected", 1)[1]

        assert "get_lock_status" in selection
        assert "holds_lock" in selection


class TestControlPanelWiring:
    """The strip and the controls must track the lock without being asked.

    A lock counts down, and somebody else can take it or let it expire while
    you are working. If the panel only refreshes on selection, the controls
    grey out with no explanation — which is the thing this feature exists to
    prevent.
    """

    @pytest.fixture
    def panel(self, app):
        from client.ui.control_panel import ControlPanel

        client = MagicMock()
        client.holds_lock.side_effect = lambda st: st.get("session_id") == "mine"
        panel = ControlPanel(client=client)
        equipment = MagicMock()
        equipment.equipment_id = "ps_1"
        equipment.name = "B&K 1902B"
        panel.selected_equipment = equipment
        yield panel, client
        panel.lock_timer.stop()
        panel.readings_timer.stop()

    def test_holding_the_lock_enables_the_controls(self, panel):
        p, _ = panel
        p._apply_lock_status(status(session_id="mine", username="me"))

        assert p.voltage_dial.isEnabled()
        assert p.output_button.isEnabled()
        assert "You have control" in p.lock_status_widget.text_label.text()

    def test_someone_else_holding_it_disables_them(self, panel):
        p, _ = panel
        p._apply_lock_status(status())

        assert not p.voltage_dial.isEnabled()
        assert not p.output_button.isEnabled()
        assert "alice" in p.lock_status_widget.text_label.text()

    def test_losing_control_is_announced(self, panel):
        """Controls greying out silently is the failure worth avoiding."""
        p, _ = panel
        messages = []
        p.status_message.connect(messages.append)

        p._apply_lock_status(status(session_id="mine", username="me"))
        p._apply_lock_status(status())          # alice takes it

        assert messages, "losing the lock must say so"
        assert "alice" in messages[-1]

    def test_no_announcement_when_you_never_had_it(self, panel):
        p, _ = panel
        messages = []
        p.status_message.connect(messages.append)

        p._apply_lock_status(status())
        p._apply_lock_status(status())

        assert not messages

    def test_deselection_clears_the_strip(self, panel):
        p, _ = panel
        p._apply_lock_status(status())

        p._apply_lock_status(None)

        assert "No equipment selected" in p.lock_status_widget.text_label.text()
        assert not p.manage_lock_button.isEnabled()

    def test_lock_polling_runs_with_acquisition(self, panel):
        p, _ = panel
        p._start_data_acquisition()

        assert p.lock_timer.isActive()
        assert p.lock_timer.interval() == 5000, (
            "polled slower than readings on purpose: a server query, not a "
            "serial one"
        )

        p._stop_data_acquisition()
        assert not p.lock_timer.isActive()

    def test_polling_happens_off_the_gui_thread(self):
        """A blocking HTTP call on a timer is how the SD dialog froze.

        The readings path already solved this with asyncSlot + call_blocking;
        the lock poll has to use it too, or it reintroduces the same fault at
        a slower interval.
        """
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2]
                  / "client" / "ui" / "control_panel.py").read_text(encoding="utf-8")
        poll = source.split("async def _poll_lock_status", 1)[1].split("def ", 1)[0]

        assert "call_blocking" in poll
        assert "_lock_poll_in_flight" in poll, "a slow server must not queue ticks"
        before = source.split("async def _poll_lock_status", 1)[0]
        assert before.rstrip().endswith("@qasync.asyncSlot()")
