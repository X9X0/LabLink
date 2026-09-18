"""A raw-socket session for Rigol scopes, shaped like a PyVISA resource.

Why this exists, measured on the bench DS1054Z over LAN, 200 reads each:

    transport    median    p90       reads over 50 ms
    raw socket   1.36 ms   1.73 ms    9/200
    VXI-11       3.03 ms   139.7 ms  20/200

The medians differ by 2x and the p90 by about 80x. The tail is what decides
whether a live trace looks smooth, so VXI-11's RPC layer -- not the
instrument -- is what makes the trace stutter.

The socket is not simply better, which is why this is a class and not a
one-line resource string:

* **One session at a time.** The scope accepts a single socket connection;
  opening a second gets a connection that never answers. It also serves LAN
  only while USB is physically unplugged.
* **A query too soon after a write is dropped.** Measured: with no settle,
  0 of 12 queries after a write returned; at 10 ms, 4 of 12; at 20 ms, 9;
  at 50 ms and beyond, 12 of 12. ``*OPC?`` does not fix it -- the same
  sequence passed once and failed once.
* **The framing desyncs.** A 60 s soak ran 445 reads at 146 Hz and then every
  following read misparsed its header, because one reply had been left
  partly unread. Without recovery the stream simply dies after a few hundred
  frames, which is worse than being slow.

So this settles after writes, resynchronises when a header does not parse,
and reconnects when the socket drops. It exposes the handful of members
BaseEquipment uses of a PyVISA resource, so the drivers do not know the
difference.
"""

import logging
import socket
import time
from typing import Optional

logger = logging.getLogger(__name__)

#: Rigol's SCPI socket port on the DS1000Z family.
SCPI_PORT = 5555


def is_socket_resource(resource_string: str) -> bool:
    """Whether this resource asks for the raw socket transport."""
    return str(resource_string or "").strip().upper().endswith("::SOCKET")


def socket_address(resource_string: str):
    """``TCPIP0::host::5555::SOCKET`` -> ``(host, 5555)``."""
    parts = [p for p in str(resource_string).split("::") if p]
    if len(parts) < 2:
        raise ValueError(f"Cannot read a host out of {resource_string!r}")
    host = parts[1]
    port = SCPI_PORT
    for part in parts[2:]:
        if part.isdigit():
            port = int(part)
            break
    return host, port


class RigolSocketSession:
    """A PyVISA-shaped session over a raw SCPI socket."""

    #: Settle after a write before the next query.
    #:
    #: On firmware 00.04.03 a query sent straight after a write was silently
    #: dropped -- 0 of 12 answered with no settle, 9 of 12 at 20 ms, 12 of 12
    #: at 50. On 00.06.04 the same test answers 12 of 12 with no settle at
    #: all, so the fault was the scope's and Rigol fixed it. A small settle is
    #: kept because a bench may still be on old firmware, and `query` retries
    #: after a full 50 ms if one is dropped anyway -- so old firmware costs a
    #: retry rather than a wrong answer, and new firmware costs 10 ms.
    WRITE_SETTLE_SEC = 0.01

    #: The settle to fall back to when a query after a write goes unanswered.
    RETRY_SETTLE_SEC = 0.05

    #: How long to keep draining when resynchronising before giving up.
    RESYNC_SEC = 0.5

    def __init__(self, resource_string: str, timeout_ms: int = 10000):
        self.resource_string = resource_string
        self._host, self._port = socket_address(resource_string)
        self._timeout_ms = int(timeout_ms)
        self._socket: Optional[socket.socket] = None
        self._settle_due = 0.0
        self.chunk_size = 20480
        self.resyncs = 0
        self.reconnects = 0
        self._connect()

    # -- PyVISA surface ------------------------------------------------ #

    @property
    def session(self):
        """Truthy while open: BaseEquipment reads this to test validity."""
        return self._socket

    @property
    def timeout(self):
        return self._timeout_ms

    @timeout.setter
    def timeout(self, milliseconds):
        self._timeout_ms = int(milliseconds)
        if self._socket is not None:
            self._socket.settimeout(max(self._timeout_ms, 1) / 1000.0)

    def write(self, command: str):
        self._send(f"{command}\n".encode())
        # The scope drops a query that arrives too soon after a write, so the
        # cost is paid before the next read rather than by sleeping here: a
        # run of writes then settles once, not once each.
        self._settle_due = time.monotonic() + self.WRITE_SETTLE_SEC

    def query(self, command: str) -> str:
        self._await_settle()
        self._send(f"{command}\n".encode())
        try:
            return self._read_line().decode(errors="replace").strip()
        except (socket.timeout, TimeoutError):
            # Old firmware drops a query that arrives too soon after a write.
            # Settle properly and ask once more rather than failing the call.
            logger.debug(f"{self.resource_string}: no answer to {command!r}; "
                         f"settling and asking again")
            self._drain()
            time.sleep(self.RETRY_SETTLE_SEC)
            self._send(f"{command}\n".encode())
            return self._read_line().decode(errors="replace").strip()

    def query_binary_values(self, command: str, datatype: str = "B",
                            container=list, **_ignored):
        """One IEEE-488.2 definite-length block, resynchronising if needed."""
        self._await_settle()
        for attempt in (1, 2):
            self._send(f"{command}\n".encode())
            try:
                payload = self._read_block()
            except _Desync as e:
                # A reply left partly unread poisons every read after it. One
                # resync and retry, rather than returning wrong samples.
                self.resyncs += 1
                logger.warning(
                    f"{self.resource_string}: {e}; resynchronising "
                    f"(resync #{self.resyncs})"
                )
                self._drain()
                if attempt == 2:
                    raise IOError(f"{command}: framing lost and not recovered")
                continue
            return bytes(payload) if container is bytes else list(payload)

    def read_raw(self) -> bytes:
        return self._read_line()

    def close(self):
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None

    def clear(self):
        """Device clear is not available on this transport; drain instead."""
        self._drain()

    # -- plumbing ------------------------------------------------------ #

    def _connect(self):
        self.close()
        made = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        made.settimeout(max(self._timeout_ms, 1) / 1000.0)
        made.connect((self._host, self._port))
        # Without this the kernel coalesces the short SCPI writes and adds a
        # round trip's worth of delay to the very thing being optimised.
        made.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._socket = made
        self._settle_due = 0.0

    def _reconnect(self):
        self.reconnects += 1
        logger.warning(f"{self.resource_string}: socket lost, reconnecting "
                       f"(reconnect #{self.reconnects})")
        time.sleep(0.2)          # the scope needs a moment to free the session
        self._connect()

    def _await_settle(self):
        remaining = self._settle_due - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        self._settle_due = 0.0

    def _send(self, payload: bytes):
        if self._socket is None:
            self._connect()
        try:
            self._socket.sendall(payload)
        except (OSError, AttributeError):
            self._reconnect()
            self._socket.sendall(payload)

    def _recv_exact(self, count: int) -> bytes:
        buf = bytearray()
        while len(buf) < count:
            part = self._socket.recv(count - len(buf))
            if not part:
                raise ConnectionError("the scope closed the socket")
            buf.extend(part)
        return bytes(buf)

    def _read_line(self) -> bytes:
        buf = bytearray()
        while not buf.endswith(b"\n"):
            part = self._socket.recv(4096)
            if not part:
                raise ConnectionError("the scope closed the socket")
            buf.extend(part)
        return bytes(buf)

    def _read_block(self) -> bytes:
        head = self._recv_exact(2)
        if head[:1] != b"#" or not head[1:2].isdigit():
            raise _Desync(f"expected an IEEE block, got {head!r}")
        digits = int(head[1:2])
        if digits == 0:
            raise _Desync("indefinite-length blocks are not supported")
        length_text = self._recv_exact(digits)
        if not length_text.isdigit():
            raise _Desync(f"bad block length {length_text!r}")
        payload = self._recv_exact(int(length_text))
        self._recv_exact(1)                     # the trailing newline
        return payload

    def _drain(self):
        """Discard whatever is queued, so the next reply starts a reply."""
        if self._socket is None:
            return
        original = self._socket.gettimeout()
        self._socket.settimeout(0.05)
        deadline = time.monotonic() + self.RESYNC_SEC
        try:
            while time.monotonic() < deadline:
                try:
                    if not self._socket.recv(65536):
                        break
                except socket.timeout:
                    break                        # nothing left to discard
                except OSError:
                    break
        finally:
            try:
                self._socket.settimeout(original)
            except OSError:
                pass


class _Desync(Exception):
    """The reply stream is no longer where the reader thinks it is."""
