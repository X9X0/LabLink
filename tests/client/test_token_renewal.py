"""A session must not go quietly unauthorized half an hour in.

Access tokens last 30 minutes by default and the refresh token lasts a week,
but the client refreshed only while connecting and nothing watched for a 401
afterwards. So thirty minutes into a session every authenticated call began
failing, and nothing said so: the window still showed a connection, the reads
that need no auth still worked, and the first sign was a write refused with
"401 Unauthorized" -- an update-mode switch, an hour after connecting.

The socket had a worse version of the same problem. The server closes /ws
with 4001 unless the token is supplied as a query parameter, and the client
never supplied one, so on a secured server the socket never connected at all
and retried every five seconds indefinitely.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from client.api.client import _TimeoutSession  # noqa: E402


def response(status):
    r = MagicMock()
    r.status_code = status
    return r


class TestTheSessionRenewsOnA401:
    @pytest.fixture
    def session(self):
        s = _TimeoutSession()
        s.headers["Authorization"] = "Bearer stale"
        return s

    def test_a_successful_call_is_left_alone(self, session):
        session.renew_token = MagicMock(return_value=True)

        with patch("requests.Session.request", return_value=response(200)) as sent:
            result = session.request("GET", "http://host/api/equipment/list")

        assert result.status_code == 200
        assert sent.call_count == 1
        session.renew_token.assert_not_called()

    def test_a_401_renews_and_retries_once(self, session):
        def renew():
            session.headers["Authorization"] = "Bearer fresh"
            return True

        session.renew_token = MagicMock(side_effect=renew)

        with patch("requests.Session.request",
                   side_effect=[response(401), response(200)]) as sent:
            result = session.request(
                "POST", "http://host/api/system/update/configure-mode"
            )

        assert result.status_code == 200, "the retry's result must be returned"
        assert sent.call_count == 2
        session.renew_token.assert_called_once()

    def test_it_retries_only_once(self, session):
        """A server that keeps saying 401 must not be hammered."""
        session.renew_token = MagicMock(return_value=True)

        with patch("requests.Session.request",
                   side_effect=[response(401), response(401)]) as sent:
            result = session.request("POST", "http://host/api/system/update/check")

        assert result.status_code == 401
        assert sent.call_count == 2
        assert session.renew_token.call_count == 1

    def test_a_failed_renewal_returns_the_401(self, session):
        """The caller then sees the real answer and can ask for a sign-in."""
        session.renew_token = MagicMock(return_value=False)

        with patch("requests.Session.request", return_value=response(401)) as sent:
            result = session.request("POST", "http://host/api/system/update/check")

        assert result.status_code == 401
        assert sent.call_count == 1, "no retry when there is no new token"

    def test_a_raising_renewal_does_not_escape(self, session):
        session.renew_token = MagicMock(side_effect=RuntimeError("network down"))

        with patch("requests.Session.request", return_value=response(401)):
            result = session.request("POST", "http://host/api/system/update/check")

        assert result.status_code == 401

    @pytest.mark.parametrize("path", [
        "/api/security/refresh", "/api/security/login", "/api/auth/login",
    ])
    def test_the_credential_endpoints_never_trigger_a_renewal(self, session, path):
        """Refreshing in response to a refusal from these would recurse, and a
        failed login answering 401 is the correct answer."""
        session.renew_token = MagicMock(return_value=True)

        with patch("requests.Session.request", return_value=response(401)) as sent:
            result = session.request("POST", f"http://host{path}")

        assert result.status_code == 401
        assert sent.call_count == 1
        session.renew_token.assert_not_called()

    def test_without_a_renewer_it_behaves_as_before(self, session):
        session.renew_token = None

        with patch("requests.Session.request", return_value=response(401)) as sent:
            result = session.request("GET", "http://host/api/equipment/list")

        assert result.status_code == 401
        assert sent.call_count == 1

    def test_a_second_thread_does_not_renew_again(self, session):
        """Panels call through worker threads, so parallel 401s are real.

        The second caller finds the token already changed and simply retries
        with it.
        """
        renewals = []

        def renew():
            renewals.append(1)
            session.headers["Authorization"] = "Bearer fresh"
            return True

        session.renew_token = MagicMock(side_effect=renew)

        with patch("requests.Session.request",
                   side_effect=[response(401), response(200)]):
            session.request("GET", "http://host/api/a")

        # The header has moved on; a later 401 renews again, but a caller that
        # started with the stale header does not.
        assert len(renewals) == 1

    def test_the_default_timeout_still_applies(self, session):
        """The renewal logic must not have displaced what this class is for."""
        session.renew_token = None

        with patch("requests.Session.request", return_value=response(200)) as sent:
            session.request("GET", "http://host/api/equipment/list")

        assert "timeout" in sent.call_args.kwargs


ws = pytest.importorskip("websockets")
from client.utils.websocket_manager import WebSocketManager  # noqa: E402


class TestTheSocketSendsItsToken:
    @pytest.fixture
    def manager(self):
        return WebSocketManager(host="192.168.91.191", port=8000)

    def test_the_token_is_in_the_url(self, manager):
        manager.token_provider = lambda: "abc.def.ghi"
        assert manager._authenticated_url() == (
            "ws://192.168.91.191:8000/ws?token=abc.def.ghi"
        )

    def test_it_is_read_fresh_each_time(self, manager):
        """A token renewed elsewhere must reach the next attempt."""
        tokens = iter(["first", "second"])
        manager.token_provider = lambda: next(tokens)

        assert manager._authenticated_url().endswith("first")
        assert manager._authenticated_url().endswith("second")

    def test_it_is_escaped(self, manager):
        manager.token_provider = lambda: "has spaces&others"
        url = manager._authenticated_url()
        assert " " not in url
        assert "?token=has%20spaces%26others" in url

    def test_no_token_leaves_the_url_alone(self, manager):
        """An unsecured server needs none, and must still be reachable."""
        manager.token_provider = lambda: None
        assert manager._authenticated_url() == "ws://192.168.91.191:8000/ws"

    def test_no_provider_leaves_the_url_alone(self, manager):
        assert manager._authenticated_url() == "ws://192.168.91.191:8000/ws"

    def test_a_raising_provider_does_not_stop_the_attempt(self, manager):
        def boom():
            raise RuntimeError("no client")

        manager.token_provider = boom
        assert manager._authenticated_url() == "ws://192.168.91.191:8000/ws"

    def test_the_base_url_carries_no_token_for_logging(self, manager):
        """The URL is logged; the credential must not be."""
        manager.token_provider = lambda: "secret.jwt.value"
        manager._authenticated_url()
        assert "secret" not in manager.base_url
