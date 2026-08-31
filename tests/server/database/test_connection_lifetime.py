"""
Tests that DatabaseManager never leaks a connection on the error path.

Every query method used to close its connection only after a successful
execute(), so any raising statement (constraint violation, locked database,
malformed data) leaked the connection and its file descriptor.
"""

import os
import sqlite3
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../server"))

from database.manager import DatabaseManager
from database.models import CommandRecord, CommandStatus


def open_fd_count():
    """Open file descriptors for this process (Linux only)."""
    return len(os.listdir(f"/proc/{os.getpid()}/fd"))


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_path=str(tmp_path / "lablink.db"))
    manager.initialize()
    return manager


@pytest.fixture
def record():
    return CommandRecord(
        timestamp=datetime.now(),
        equipment_id="eq-1",
        equipment_type="power_supply",
        command="*IDN?",
        response="ok",
        status=CommandStatus.SUCCESS,
        execution_time_ms=1.0,
        user_id="user-1",
        session_id="session-1",
    )


def _break_schema(db):
    """Drop a table so queries raise *after* the connection is opened."""
    conn = sqlite3.connect(db.db_path)
    try:
        conn.execute("DROP TABLE command_history")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.skipif(
    not os.path.isdir("/proc/self/fd"), reason="requires /proc (Linux)"
)
class TestNoConnectionLeak:
    def test_failing_writes_do_not_leak_descriptors(self, db, record):
        _break_schema(db)
        baseline = open_fd_count()
        held = []

        for _ in range(100):
            try:
                db.log_command(record)
            except Exception as e:
                # Hold the exception, as a logger or error handler would; its
                # traceback keeps the frame (and any leaked conn) referenced.
                held.append(e)

        assert len(held) == 100, "expected every call to raise"
        assert open_fd_count() - baseline < 10, (
            f"connections leaked: {baseline} -> {open_fd_count()} open fds"
        )

    def test_failing_reads_do_not_leak_descriptors(self, db):
        _break_schema(db)
        baseline = open_fd_count()
        held = []

        for _ in range(100):
            try:
                db.get_command_history(limit=10)
            except Exception as e:
                held.append(e)

        assert len(held) == 100, "expected every call to raise"
        assert open_fd_count() - baseline < 10, (
            f"connections leaked: {baseline} -> {open_fd_count()} open fds"
        )


class TestNormalOperationUnaffected:
    """The leak fix must not change working behaviour."""

    def test_write_then_read(self, db, record):
        record_id = db.log_command(record)
        assert record_id > 0

        result = db.get_command_history(limit=10)
        assert len(result.records) == 1
        assert result.records[0]["command"] == "*IDN?"

    def test_statistics(self, db, record):
        db.log_command(record)

        stats = db.get_database_statistics()

        assert stats["command_count"] == 1

    def test_cleanup_and_vacuum(self, db, record):
        """VACUUM needs its own connection with no other one held open."""
        db.log_command(record)

        db.cleanup_old_records(days=1)

        assert db.get_database_statistics()["command_count"] == 1
