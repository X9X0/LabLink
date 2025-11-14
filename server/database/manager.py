"""Database manager for centralized data storage."""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (CommandRecord, CommandStatus, DatabaseConfig,
                     DataSessionRecord, EquipmentUsageRecord,
                     MeasurementRecord, QueryResult, SessionStatus)

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages centralized SQLite database for LabLink.

    Provides storage for:
    - Command history
    - Measurement archival
    - Equipment usage statistics
    - Data acquisition sessions
    """

    def __init__(
        self, db_path: str = "data/lablink.db", config: Optional[DatabaseConfig] = None
    ):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file
            config: Database configuration
        """
        self.db_path = db_path
        self.config = config or DatabaseConfig()
        self._lock = threading.RLock()
        self._connection = None

    def initialize(self):
        """Initialize database with schema."""
        # Create database directory
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Create tables
        self._create_schema()

        logger.info(f"Database initialized at {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection (thread-local).

        Returns:
            Database connection
        """
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_schema(self):
        """Create database schema."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Command history table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS command_history (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    equipment_id TEXT NOT NULL,
                    equipment_type TEXT NOT NULL,
                    command TEXT NOT NULL,
                    response TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    execution_time_ms REAL DEFAULT 0.0,
                    user_id TEXT,
                    session_id TEXT
                )
            """
            )

            # Create indices for command history
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_command_timestamp ON command_history(timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_command_equipment ON command_history(equipment_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_command_user ON command_history(user_id)"
            )

            # Measurements table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS measurements (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    equipment_id TEXT NOT NULL,
                    equipment_type TEXT NOT NULL,
                    measurement_type TEXT NOT NULL,
                    channel INTEGER,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    quality TEXT,
                    metadata TEXT,
                    session_id TEXT,
                    user_id TEXT
                )
            """
            )

            # Create indices for measurements
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_measurement_timestamp ON measurements(timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_measurement_equipment ON measurements(equipment_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_measurement_type ON measurements(measurement_type)"
            )

            # Equipment usage table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS equipment_usage (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    equipment_id TEXT NOT NULL,
                    equipment_type TEXT NOT NULL,
                    session_start TEXT NOT NULL,
                    session_end TEXT,
                    duration_seconds REAL DEFAULT 0.0,
                    command_count INTEGER DEFAULT 0,
                    measurement_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    user_id TEXT,
                    disconnect_reason TEXT
                )
            """
            )

            # Create indices for equipment usage
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_equipment ON equipment_usage(equipment_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_start ON equipment_usage(session_start)"
            )

            # Data sessions table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS data_sessions (
                    session_id TEXT PRIMARY KEY,
                    equipment_ids TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_seconds REAL DEFAULT 0.0,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    sample_count INTEGER DEFAULT 0,
                    export_format TEXT,
                    export_path TEXT,
                    trigger_config TEXT,
                    statistics TEXT,
                    user_id TEXT,
                    error_message TEXT
                )
            """
            )

            # Create indices for data sessions
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_start ON data_sessions(start_time)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_status ON data_sessions(status)"
            )

            conn.commit()
            conn.close()

            logger.info("Database schema created successfully")

    # === Command History Operations ===

    def log_command(self, record: CommandRecord) -> int:
        """Log a command execution.

        Args:
            record: Command record to log

        Returns:
            Record ID of inserted command
        """
        if not self.config.enable_command_logging:
            return -1

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO command_history (
                    timestamp, equipment_id, equipment_type, command, response,
                    status, error_message, execution_time_ms, user_id, session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    record.timestamp.isoformat(),
                    record.equipment_id,
                    record.equipment_type,
                    record.command,
                    record.response,
                    record.status.value,
                    record.error_message,
                    record.execution_time_ms,
                    record.user_id,
                    record.session_id,
                ),
            )

            record_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return record_id

    def get_command_history(
        self,
        equipment_id: Optional[str] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        status: Optional[CommandStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult:
        """Query command history.

        Args:
            equipment_id: Filter by equipment ID
            user_id: Filter by user ID
            start_time: Filter by start time
            end_time: Filter by end time
            status: Filter by status
            limit: Maximum records to return
            offset: Number of records to skip

        Returns:
            QueryResult with command records
        """
        query_start = datetime.now()

        conditions = []
        params = []

        if equipment_id:
            conditions.append("equipment_id = ?")
            params.append(equipment_id)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())
        if status:
            conditions.append("status = ?")
            params.append(status.value)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get total count
            cursor.execute(
                f"SELECT COUNT(*) FROM command_history WHERE {where_clause}", params
            )
            total_count = cursor.fetchone()[0]

            # Get records
            cursor.execute(
                f"""
                SELECT * FROM command_history
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """,
                params + [limit, offset],
            )

            records = [dict(row) for row in cursor.fetchall()]
            conn.close()

        query_time = (datetime.now() - query_start).total_seconds() * 1000

        return QueryResult(
            records=records,
            total_count=total_count,
            page=(offset // limit) + 1 if limit > 0 else 1,
            page_size=limit,
            has_more=(offset + limit) < total_count,
            query_time_ms=query_time,
        )

    # === Measurement Operations ===

    def archive_measurement(self, record: MeasurementRecord) -> int:
        """Archive a measurement.

        Args:
            record: Measurement record to archive

        Returns:
            Record ID of inserted measurement
        """
        if not self.config.enable_measurement_archival:
            return -1

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO measurements (
                    timestamp, equipment_id, equipment_type, measurement_type,
                    channel, value, unit, quality, metadata, session_id, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    record.timestamp.isoformat(),
                    record.equipment_id,
                    record.equipment_type,
                    record.measurement_type,
                    record.channel,
                    record.value,
                    record.unit,
                    record.quality,
                    json.dumps(record.metadata) if record.metadata else None,
                    record.session_id,
                    record.user_id,
                ),
            )

            record_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return record_id

    def get_measurements(
        self,
        equipment_id: Optional[str] = None,
        measurement_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult:
        """Query measurements.

        Args:
            equipment_id: Filter by equipment ID
            measurement_type: Filter by measurement type
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum records to return
            offset: Number of records to skip

        Returns:
            QueryResult with measurement records
        """
        query_start = datetime.now()

        conditions = []
        params = []

        if equipment_id:
            conditions.append("equipment_id = ?")
            params.append(equipment_id)
        if measurement_type:
            conditions.append("measurement_type = ?")
            params.append(measurement_type)
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get total count
            cursor.execute(
                f"SELECT COUNT(*) FROM measurements WHERE {where_clause}", params
            )
            total_count = cursor.fetchone()[0]

            # Get records
            cursor.execute(
                f"""
                SELECT * FROM measurements
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """,
                params + [limit, offset],
            )

            records = []
            for row in cursor.fetchall():
                record = dict(row)
                # Parse JSON metadata
                if record.get("metadata"):
                    record["metadata"] = json.loads(record["metadata"])
                records.append(record)

            conn.close()

        query_time = (datetime.now() - query_start).total_seconds() * 1000

        return QueryResult(
            records=records,
            total_count=total_count,
            page=(offset // limit) + 1 if limit > 0 else 1,
            page_size=limit,
            has_more=(offset + limit) < total_count,
            query_time_ms=query_time,
        )

    # === Equipment Usage Operations ===

    def start_usage_session(self, record: EquipmentUsageRecord) -> int:
        """Start tracking equipment usage session.

        Args:
            record: Equipment usage record

        Returns:
            Record ID of inserted session
        """
        if not self.config.enable_usage_tracking:
            return -1

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO equipment_usage (
                    equipment_id, equipment_type, session_start, user_id
                ) VALUES (?, ?, ?, ?)
            """,
                (
                    record.equipment_id,
                    record.equipment_type,
                    record.session_start.isoformat(),
                    record.user_id,
                ),
            )

            record_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return record_id

    def end_usage_session(
        self,
        record_id: int,
        command_count: int = 0,
        measurement_count: int = 0,
        error_count: int = 0,
        disconnect_reason: Optional[str] = None,
    ):
        """End equipment usage session.

        Args:
            record_id: Record ID of the session
            command_count: Number of commands executed
            measurement_count: Number of measurements taken
            error_count: Number of errors encountered
            disconnect_reason: Reason for disconnection
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get session start time
            cursor.execute(
                "SELECT session_start FROM equipment_usage WHERE record_id = ?",
                (record_id,),
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return

            session_start = datetime.fromisoformat(row[0])
            session_end = datetime.now()
            duration = (session_end - session_start).total_seconds()

            cursor.execute(
                """
                UPDATE equipment_usage
                SET session_end = ?, duration_seconds = ?,
                    command_count = ?, measurement_count = ?, error_count = ?,
                    disconnect_reason = ?
                WHERE record_id = ?
            """,
                (
                    session_end.isoformat(),
                    duration,
                    command_count,
                    measurement_count,
                    error_count,
                    disconnect_reason,
                    record_id,
                ),
            )

            conn.commit()
            conn.close()

    def get_equipment_usage_statistics(
        self,
        equipment_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get equipment usage statistics.

        Args:
            equipment_id: Filter by equipment ID
            start_time: Filter by start time
            end_time: Filter by end time

        Returns:
            Dictionary with usage statistics
        """
        conditions = []
        params = []

        if equipment_id:
            conditions.append("equipment_id = ?")
            params.append(equipment_id)
        if start_time:
            conditions.append("session_start >= ?")
            params.append(start_time.isoformat())
        if end_time:
            conditions.append("session_start <= ?")
            params.append(end_time.isoformat())

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) as session_count,
                    SUM(duration_seconds) as total_duration,
                    AVG(duration_seconds) as avg_duration,
                    SUM(command_count) as total_commands,
                    SUM(measurement_count) as total_measurements,
                    SUM(error_count) as total_errors
                FROM equipment_usage
                WHERE {where_clause}
            """,
                params,
            )

            row = cursor.fetchone()
            conn.close()

            return {
                "session_count": row[0] or 0,
                "total_duration_seconds": row[1] or 0.0,
                "average_duration_seconds": row[2] or 0.0,
                "total_commands": row[3] or 0,
                "total_measurements": row[4] or 0,
                "total_errors": row[5] or 0,
            }

    # === Data Session Operations ===

    def create_data_session(self, record: DataSessionRecord):
        """Create data acquisition session record.

        Args:
            record: Data session record
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO data_sessions (
                    session_id, equipment_ids, start_time, status, mode,
                    trigger_config, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    record.session_id,
                    json.dumps(record.equipment_ids),
                    record.start_time.isoformat(),
                    record.status.value,
                    record.mode,
                    (
                        json.dumps(record.trigger_config)
                        if record.trigger_config
                        else None
                    ),
                    record.user_id,
                ),
            )

            conn.commit()
            conn.close()

    def update_data_session(
        self,
        session_id: str,
        status: Optional[SessionStatus] = None,
        sample_count: Optional[int] = None,
        export_format: Optional[str] = None,
        export_path: Optional[str] = None,
        statistics: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ):
        """Update data acquisition session.

        Args:
            session_id: Session ID
            status: New status
            sample_count: Number of samples collected
            export_format: Export format used
            export_path: Export file path
            statistics: Session statistics
            error_message: Error message if failed
        """
        updates = []
        params = []

        if status:
            updates.append("status = ?")
            params.append(status.value)
            if status in (
                SessionStatus.COMPLETED,
                SessionStatus.CANCELLED,
                SessionStatus.FAILED,
            ):
                updates.append("end_time = ?")
                params.append(datetime.now().isoformat())

        if sample_count is not None:
            updates.append("sample_count = ?")
            params.append(sample_count)

        if export_format:
            updates.append("export_format = ?")
            params.append(export_format)

        if export_path:
            updates.append("export_path = ?")
            params.append(export_path)

        if statistics:
            updates.append("statistics = ?")
            params.append(json.dumps(statistics))

        if error_message:
            updates.append("error_message = ?")
            params.append(error_message)

        if not updates:
            return

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Calculate duration if ending session
            if status and status in (
                SessionStatus.COMPLETED,
                SessionStatus.CANCELLED,
                SessionStatus.FAILED,
            ):
                cursor.execute(
                    "SELECT start_time FROM data_sessions WHERE session_id = ?",
                    (session_id,),
                )
                row = cursor.fetchone()
                if row:
                    start_time = datetime.fromisoformat(row[0])
                    duration = (datetime.now() - start_time).total_seconds()
                    updates.append("duration_seconds = ?")
                    params.append(duration)

            cursor.execute(
                f"""
                UPDATE data_sessions
                SET {', '.join(updates)}
                WHERE session_id = ?
            """,
                params + [session_id],
            )

            conn.commit()
            conn.close()

    # === Cleanup Operations ===

    def cleanup_old_records(self, days: Optional[int] = None):
        """Clean up old records based on retention policy.

        Args:
            days: Number of days to keep (uses config if not specified)
        """
        if not self.config.auto_cleanup:
            return

        retention_days = days or self.config.retention_days
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Delete old command history
            cursor.execute(
                "DELETE FROM command_history WHERE timestamp < ?",
                (cutoff_date.isoformat(),),
            )
            command_deleted = cursor.rowcount

            # Delete old measurements
            cursor.execute(
                "DELETE FROM measurements WHERE timestamp < ?",
                (cutoff_date.isoformat(),),
            )
            measurement_deleted = cursor.rowcount

            # Delete old equipment usage records
            cursor.execute(
                "DELETE FROM equipment_usage WHERE session_start < ?",
                (cutoff_date.isoformat(),),
            )
            usage_deleted = cursor.rowcount

            # Delete old completed data sessions
            cursor.execute(
                "DELETE FROM data_sessions WHERE start_time < ? AND status IN ('completed', 'failed', 'cancelled')",
                (cutoff_date.isoformat(),),
            )
            session_deleted = cursor.rowcount

            conn.commit()
            conn.close()

            logger.info(
                f"Cleaned up old records: {command_deleted} commands, {measurement_deleted} measurements, "
                f"{usage_deleted} usage records, {session_deleted} sessions"
            )

            # Vacuum database to reclaim space
            conn = self._get_connection()
            conn.execute("VACUUM")
            conn.close()

    def get_database_statistics(self) -> Dict[str, Any]:
        """Get database statistics.

        Returns:
            Dictionary with database statistics
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get record counts
            cursor.execute("SELECT COUNT(*) FROM command_history")
            command_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM measurements")
            measurement_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM equipment_usage")
            usage_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM data_sessions")
            session_count = cursor.fetchone()[0]

            # Get database file size
            cursor.execute(
                "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"
            )
            db_size_bytes = cursor.fetchone()[0]

            conn.close()

        return {
            "command_count": command_count,
            "measurement_count": measurement_count,
            "usage_session_count": usage_count,
            "data_session_count": session_count,
            "database_size_bytes": db_size_bytes,
            "database_size_mb": db_size_bytes / (1024 * 1024),
            "database_path": self.db_path,
            "retention_days": self.config.retention_days,
        }
