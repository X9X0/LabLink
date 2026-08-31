"""
Tests that failed-login lockout survives a server restart.

Attempt counters used to live only in memory, so restarting the server (or a
crash/redeploy) handed a brute-force attacker a fresh attempt budget.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../server"))

from security.auth import AuthConfig, LoginAttemptTracker
from security.manager import SecurityManager


@pytest.fixture
def config():
    return AuthConfig(
        secret_key="test-secret-key-for-lockout-tests",
        max_failed_login_attempts=5,
        account_lockout_duration_minutes=30,
    )


@pytest.fixture
def db_path(tmp_path, config):
    """A security DB with the schema created (incl. login_attempts)."""
    path = tmp_path / "security.db"
    SecurityManager(db_path=str(path), config=config)
    return path


class TestLockout:
    def test_locks_out_after_max_attempts(self, config, db_path):
        tracker = LoginAttemptTracker(config, db_path=db_path)

        for _ in range(5):
            tracker.record_failed_attempt("victim")

        assert tracker.is_locked_out("victim") is True

    def test_not_locked_out_below_threshold(self, config, db_path):
        tracker = LoginAttemptTracker(config, db_path=db_path)

        for _ in range(4):
            tracker.record_failed_attempt("victim")

        assert tracker.is_locked_out("victim") is False


class TestPersistenceAcrossRestart:
    def test_attempts_survive_restart(self, config, db_path):
        tracker = LoginAttemptTracker(config, db_path=db_path)
        for _ in range(3):
            tracker.record_failed_attempt("victim")

        restarted = LoginAttemptTracker(config, db_path=db_path)

        assert restarted.get_attempt_count("victim") == 3

    def test_lockout_survives_restart(self, config, db_path):
        """The regression this guards: restart must not reset the budget."""
        tracker = LoginAttemptTracker(config, db_path=db_path)
        for _ in range(5):
            tracker.record_failed_attempt("victim")

        restarted = LoginAttemptTracker(config, db_path=db_path)

        assert restarted.is_locked_out("victim") is True

    def test_successful_login_clears_persisted_attempts(self, config, db_path):
        tracker = LoginAttemptTracker(config, db_path=db_path)
        for _ in range(5):
            tracker.record_failed_attempt("victim")

        tracker.clear_attempts("victim")
        restarted = LoginAttemptTracker(config, db_path=db_path)

        assert restarted.get_attempt_count("victim") == 0
        assert restarted.is_locked_out("victim") is False

    def test_attempts_are_per_username(self, config, db_path):
        tracker = LoginAttemptTracker(config, db_path=db_path)
        for _ in range(5):
            tracker.record_failed_attempt("victim")
        tracker.record_failed_attempt("bystander")

        restarted = LoginAttemptTracker(config, db_path=db_path)

        assert restarted.is_locked_out("victim") is True
        assert restarted.is_locked_out("bystander") is False


class TestResilience:
    def test_tracker_works_without_db(self, config):
        """In-memory mode must still function (db_path is optional)."""
        tracker = LoginAttemptTracker(config)

        for _ in range(5):
            tracker.record_failed_attempt("victim")

        assert tracker.is_locked_out("victim") is True

    def test_db_failure_does_not_break_login(self, config, tmp_path):
        """Persistence problems must never block an auth response."""
        tracker = LoginAttemptTracker(
            config, db_path=tmp_path / "nonexistent-dir" / "security.db"
        )

        count = tracker.record_failed_attempt("victim")

        assert count == 1  # in-memory tracking still works
