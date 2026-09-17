"""The raw-socket session: framing, resynchronising, and the write settle.

Measured on the bench DS1054Z over LAN, 200 reads each: the socket's median
is 1.36 ms against VXI-11's 3.03, and its p90 1.73 ms against 139.7 -- about
eighty times better in the tail, which is what a live trace is made of.

It is not simply better, and each of these tests pins one of the ways it is
worse:

* a query too soon after a write is dropped (0 of 12 answered with no settle,
  9 of 12 at 20 ms, 12 of 12 at 50)
* the framing desynchronises: a 60 s soak ran 445 reads and then every read
  after misparsed its header, because one reply had been left partly unread
"""

import socket

import pytest

from server.equipment.rigol_socket import (RigolSocketSession, is_socket_resource,
                                           socket_address)


class _FakeSocket:
    """A socket that replies from a script, and records what it was sent."""

    def __init__(self, replies=(), chunk=None):
        self.sent = []
        self._pending = bytearray()
        self._replies = list(replies)
        self.closed = False
        self._timeout = None
        self.chunk = chunk

    # -- the parts the session uses
    def settimeout(self, value):
        self._timeout = value

    def gettimeout(self):
        return self._timeout

    def setsockopt(self, *_a):
        pass

    def connect(self, _address):
        pass

    def sendall(self, payload):
        self.sent.append(payload)
        if self._replies:
            self._pending.extend(self._replies.pop(0))

    def recv(self, count):
        if not self._pending:
            raise socket.timeout("nothing queued")
        take = min(count, self.chunk or count, len(self._pending))
        out = bytes(self._pending[:take])
        del self._pending[:take]
        return out

    def close(self):
        self.closed = True


def _block(payload: bytes) -> bytes:
    return b"#" + str(len(str(len(payload)))).encode() + str(len(payload)).encode() \
        + payload + b"\n"


@pytest.fixture
def session(monkeypatch):
    made = {}

    def build(*_a, **_k):
        made["socket"] = _FakeSocket()
        return made["socket"]

    monkeypatch.setattr(socket, "socket", build)
    s = RigolSocketSession("TCPIP0::192.168.91.37::5555::SOCKET")
    s.fake = made["socket"]
    return s


class TestResourceStrings:
    def test_a_socket_resource_is_recognised(self):
        assert is_socket_resource("TCPIP0::192.168.91.37::5555::SOCKET")
        assert is_socket_resource("tcpip0::host::5555::socket")

    def test_other_resources_are_not(self):
        assert not is_socket_resource("TCPIP0::192.168.91.37::inst0::INSTR")
        assert not is_socket_resource("USB0::6833::1230::DS1ZA1::0::INSTR")

    def test_the_address_is_read_out_of_it(self):
        assert socket_address("TCPIP0::192.168.91.37::5555::SOCKET") == \
            ("192.168.91.37", 5555)

    def test_the_port_defaults_to_the_rigol_one(self):
        assert socket_address("TCPIP0::192.168.91.37::SOCKET") == \
            ("192.168.91.37", 5555)


class TestFraming:
    def test_a_binary_block_is_read_whole(self, session):
        session.fake._replies.append(_block(bytes(range(200))))
        data = session.query_binary_values(":WAV:DATA?", container=bytes)
        assert data == bytes(range(200))

    def test_a_block_split_across_packets_is_reassembled(self, monkeypatch):
        """The scope's replies arrive in pieces; a short read is not the end."""
        made = {}

        def build(*_a, **_k):
            made["socket"] = _FakeSocket(chunk=7)     # dribble it out
            return made["socket"]

        monkeypatch.setattr(socket, "socket", build)
        session = RigolSocketSession("TCPIP0::host::5555::SOCKET")
        made["socket"]._replies.append(_block(bytes(range(250))))
        assert session.query_binary_values(":WAV:DATA?", container=bytes) == \
            bytes(range(250))

    def test_a_text_reply_is_read_to_its_newline(self, session):
        session.fake._replies.append(b"RIGOL,DS1054Z,1,00.04.03\n")
        assert session.query("*IDN?") == "RIGOL,DS1054Z,1,00.04.03"


class TestResynchronising:
    def test_a_lost_header_is_resynchronised_and_retried(self, session):
        """A reply left partly unread poisons every read after it.

        On the bench this killed the stream after 445 reads: once the reader
        was out of step, every header misparsed and nothing recovered.
        """
        session.fake._replies.append(b"\x53\x53\x53\x53rubbish")   # not a block
        session.fake._replies.append(_block(b"good samples"))
        data = session.query_binary_values(":WAV:DATA?", container=bytes)
        assert data == b"good samples"
        assert session.resyncs == 1

    def test_framing_lost_twice_raises_rather_than_returning_rubbish(self, session):
        session.fake._replies.append(b"junk one\n")
        session.fake._replies.append(b"junk two\n")
        with pytest.raises(IOError, match="framing"):
            session.query_binary_values(":WAV:DATA?", container=bytes)
        assert session.resyncs == 2


class TestTheWriteSettle:
    def test_a_query_after_a_write_waits(self, session, monkeypatch):
        """0 of 12 queries answered with no settle; 12 of 12 at 50 ms."""
        slept = []
        monkeypatch.setattr("server.equipment.rigol_socket.time.sleep",
                            lambda s: slept.append(s))
        session.write(":WAV:SOUR CHAN1")
        session.fake._replies.append(b"CHAN1\n")
        session.query(":WAV:SOUR?")
        assert slept and sum(slept) >= session.WRITE_SETTLE_SEC * 0.9, slept

    def test_a_run_of_writes_settles_once_not_once_each(self, session, monkeypatch):
        slept = []
        monkeypatch.setattr("server.equipment.rigol_socket.time.sleep",
                            lambda s: slept.append(s))
        session.write(":WAV:SOUR CHAN1")
        session.write(":WAV:MODE NORM")
        session.write(":WAV:FORM BYTE")
        session.fake._replies.append(b"ok\n")
        session.query(":WAV:PRE?")
        assert len(slept) == 1, f"settled once per write: {slept}"

    def test_reads_with_no_write_before_them_do_not_wait(self, session, monkeypatch):
        """The streaming loop writes nothing, so it must pay nothing."""
        slept = []
        monkeypatch.setattr("server.equipment.rigol_socket.time.sleep",
                            lambda s: slept.append(s))
        for _ in range(5):
            session.fake._replies.append(_block(b"abc"))
            session.query_binary_values(":WAV:DATA?", container=bytes)
        assert slept == [], f"the hot path paid a settle it did not owe: {slept}"


class TestTheSessionSurface:
    def test_it_looks_open_to_the_validity_check(self, session):
        assert session.session
        session.close()
        assert not session.session

    def test_the_timeout_is_settable_in_milliseconds(self, session):
        session.timeout = 2500
        assert session.timeout == 2500
        assert session.fake.gettimeout() == pytest.approx(2.5)
