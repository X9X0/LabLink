"""A keep-alive socket the server closed must not surface as a failure.

Seen on the bench about once a minute, and self-correcting::

    ConnectionError: ('Connection aborted.',
                      RemoteDisconnected('Remote end closed connection
                      without response'))

uvicorn closes an idle keep-alive connection after a few seconds. When
the client draws that socket out of its pool at the moment the server
is closing it, the request dies before it is sent -- so the server
never saw it, and the next call, on a fresh socket, works. That is the
whole reason it looked like it corrected itself.

requests defaults to no retries, so each of these reached a panel as a
failed read: a blank table, or "Could not read setpoints", for a
request that was never actually refused by anything.

The tests below drive a real socket rather than checking configuration,
because the interesting part is the interaction between the connection
pool and a peer that hangs up -- which a config assertion cannot see.

The second class is the one that matters more. Retrying a *command* to
a power supply because a socket looked odd would be a genuinely bad
idea, so it must not be possible.
"""

import http.server
import os
import socket
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class HangUpOnce(http.server.BaseHTTPRequestHandler):
    """Closes the first connection without answering, then behaves.

    Stands in for uvicorn reaping an idle keep-alive socket. With
    ``always`` set it never recovers, which is how the retry budget is
    measured.
    """

    protocol_version = "HTTP/1.1"
    dropped = False
    always = False
    seen = []

    def _answer(self):
        type(self).seen.append(self.command)
        if type(self).always or not type(self).dropped:
            type(self).dropped = True
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _answer
    do_POST = _answer

    def log_message(self, *a):
        pass


@pytest.fixture
def flaky_server():
    HangUpOnce.dropped = False
    HangUpOnce.always = False
    HangUpOnce.seen = []
    # Threading, and daemon threads: these are keep-alive connections, so
    # a single-threaded server sits in the handler waiting for the next
    # request on a socket the test has finished with, and shutdown() then
    # blocks for ever waiting for it to come back.
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HangUpOnce)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.fixture
def session():
    from client.api.client import _TimeoutSession

    made = _TimeoutSession()
    yield made
    made.close()


class TestAReadSurvivesTheHangUp:
    def test_a_get_still_returns(self, session, flaky_server):
        """The bench symptom, gone: the caller never sees the drop."""
        answer = session.get(f"{flaky_server}/api/equipment/list", timeout=5)

        assert answer.status_code == 200
        assert HangUpOnce.seen.count("GET") == 2, (
            "the dropped request was not retried, so a panel sees a "
            f"failure for a request the server never received: "
            f"{HangUpOnce.seen}")

    def test_it_gives_up_rather_than_retrying_for_ever(self, session,
                                                       flaky_server):
        """A server that is really broken must surface, not spin.

        Counted against a server that never recovers, so the budget is
        observed rather than asserted from configuration: one attempt
        plus the two retries, and then the caller is told.
        """
        import requests

        HangUpOnce.always = True

        with pytest.raises(requests.exceptions.ConnectionError):
            session.get(f"{flaky_server}/api/equipment/list", timeout=5)

        assert HangUpOnce.seen.count("GET") == 3, (
            f"expected one attempt and two retries, got "
            f"{HangUpOnce.seen.count('GET')}")


class TestACommandIsNeverRetried:
    """This client drives lab instruments. No automatic retry may reach
    one -- a setpoint sent twice is not a harmless duplicate."""

    def test_a_post_is_not_retried(self, session, flaky_server):
        import requests

        with pytest.raises(requests.exceptions.ConnectionError):
            session.post(f"{flaky_server}/api/equipment/ps_1/command",
                         json={"action": "set_voltage"}, timeout=5)

        assert HangUpOnce.seen.count("POST") == 1, (
            "a command was sent twice; on a power supply that is a "
            f"setpoint applied twice: {HangUpOnce.seen}")

    def test_the_policy_says_so_explicitly(self):
        """Guarding the default: urllib3 would also retry PUT and DELETE."""
        from client.api.client import _TimeoutSession

        allowed = _TimeoutSession._RETRY_READS.allowed_methods
        assert "POST" not in allowed
        assert "PUT" not in allowed, (
            "PUT is idempotent in HTTP terms, which is not the same as "
            "safe to repeat against an instrument")
        assert "DELETE" not in allowed
        assert "GET" in allowed


class TestTheAdapterIsActuallyMounted:
    def test_both_schemes_carry_the_policy(self, session):
        for prefix in ("http://", "https://"):
            adapter = session.get_adapter(prefix + "x")
            assert adapter.max_retries.total == 2, (
                f"{prefix} has default retries, so the pool races through")
