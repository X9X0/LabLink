"""
Tests for OAuth2 ``state`` (CSRF) verification.

The state issued by /oauth2/authorize must be verified and consumed by
/oauth2/login, so an attacker cannot have a victim's browser complete a flow
the attacker started (login CSRF / account linking).
"""

import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../server"))

from security.oauth2 import OAuth2Manager


@pytest.fixture
def oauth2_manager():
    return OAuth2Manager()


class TestStateVerification:
    def test_issued_state_is_accepted(self, oauth2_manager):
        oauth2_manager.register_state("issued-state")

        assert oauth2_manager.consume_state("issued-state") is True

    def test_unknown_state_is_rejected(self, oauth2_manager):
        """The core CSRF defence: a state we never issued must not pass."""
        assert oauth2_manager.consume_state("attacker-supplied") is False

    def test_state_is_single_use(self, oauth2_manager):
        """Replaying a captured state must not work a second time."""
        oauth2_manager.register_state("one-shot")

        assert oauth2_manager.consume_state("one-shot") is True
        assert oauth2_manager.consume_state("one-shot") is False

    def test_missing_state_is_rejected(self, oauth2_manager):
        assert oauth2_manager.consume_state(None) is False
        assert oauth2_manager.consume_state("") is False

    def test_expired_state_is_rejected(self, oauth2_manager):
        oauth2_manager.register_state("stale")
        oauth2_manager._pending_states["stale"] = datetime.now() - timedelta(minutes=1)

        assert oauth2_manager.consume_state("stale") is False

    def test_states_are_independent(self, oauth2_manager):
        oauth2_manager.register_state("a")
        oauth2_manager.register_state("b")

        assert oauth2_manager.consume_state("a") is True
        assert oauth2_manager.consume_state("b") is True


class TestStateStoreHygiene:
    def test_expired_states_are_pruned(self, oauth2_manager):
        for i in range(20):
            oauth2_manager.register_state(f"old-{i}")
            oauth2_manager._pending_states[f"old-{i}"] = datetime.now() - timedelta(
                minutes=1
            )

        oauth2_manager.register_state("fresh")

        assert "fresh" in oauth2_manager._pending_states
        assert not [k for k in oauth2_manager._pending_states if k.startswith("old-")]

    def test_store_does_not_grow_without_bound(self, oauth2_manager):
        """Repeated abandoned flows must not accumulate forever."""
        for i in range(200):
            oauth2_manager.register_state(f"abandoned-{i}")
            oauth2_manager._pending_states[f"abandoned-{i}"] = (
                datetime.now() - timedelta(minutes=1)
            )

        oauth2_manager.register_state("current")

        assert len(oauth2_manager._pending_states) == 1
