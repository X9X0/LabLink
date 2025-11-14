"""Connection history tracking."""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .models import (ConnectionHistoryEntry, ConnectionStatistics,
                     DiscoveryConfig, LastKnownGood)

logger = logging.getLogger(__name__)


class ConnectionHistoryTracker:
    """Tracks connection history and statistics."""

    def __init__(self, config: DiscoveryConfig, db_path: str = "data/discovery.db"):
        """Initialize connection history tracker.

        Args:
            config: Discovery configuration
            db_path: Database file path
        """
        self.config = config
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Connection history table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS connection_history (
                    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    resource_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    connection_time_ms REAL,
                    manufacturer TEXT,
                    model TEXT,
                    firmware_version TEXT,
                    user_id TEXT,
                    session_id TEXT,
                    discovery_method TEXT,
                    ip_address TEXT
                )
            """
            )

            # Create index for efficient queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_device_timestamp
                ON connection_history(device_id, timestamp DESC)
            """
            )

            # Last known good configurations
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS last_known_good (
                    device_id TEXT PRIMARY KEY,
                    resource_name TEXT NOT NULL,
                    last_successful TIMESTAMP NOT NULL,
                    connection_count INTEGER DEFAULT 0,
                    manufacturer TEXT,
                    model TEXT,
                    serial_number TEXT,
                    ip_address TEXT,
                    hostname TEXT,
                    avg_response_time_ms REAL DEFAULT 0.0,
                    last_error TEXT
                )
            """
            )

            conn.commit()
            conn.close()

            logger.info(f"Initialized connection history database: {self.db_path}")

        except Exception as e:
            logger.error(f"Failed to initialize history database: {e}")
            raise

    def record_connection(
        self,
        device_id: str,
        resource_name: str,
        success: bool,
        connection_time_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        firmware_version: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        discovery_method: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> int:
        """Record a connection event.

        Args:
            device_id: Device identifier
            resource_name: VISA resource name
            success: Connection successful
            connection_time_ms: Connection time in milliseconds
            error_message: Error message if failed
            manufacturer: Manufacturer name
            model: Model number
            firmware_version: Firmware version
            user_id: User who initiated connection
            session_id: Session identifier
            discovery_method: How device was discovered
            ip_address: IP address (if applicable)

        Returns:
            Entry ID
        """
        if not self.config.enable_history:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO connection_history (
                    device_id, resource_name, event_type, timestamp, success,
                    error_message, connection_time_ms, manufacturer, model,
                    firmware_version, user_id, session_id, discovery_method, ip_address
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    device_id,
                    resource_name,
                    "connected" if success else "failed",
                    datetime.now(),
                    success,
                    error_message,
                    connection_time_ms,
                    manufacturer,
                    model,
                    firmware_version,
                    user_id,
                    session_id,
                    discovery_method,
                    ip_address,
                ),
            )

            entry_id = cursor.lastrowid

            # Update last known good if successful
            if success:
                self._update_last_known_good(
                    cursor,
                    device_id,
                    resource_name,
                    connection_time_ms,
                    manufacturer,
                    model,
                    ip_address,
                )

            conn.commit()
            return entry_id

        except Exception as e:
            logger.error(f"Failed to record connection: {e}")
            conn.rollback()
            return 0

        finally:
            conn.close()

    def record_disconnection(self, device_id: str, resource_name: str):
        """Record a disconnection event.

        Args:
            device_id: Device identifier
            resource_name: VISA resource name
        """
        if not self.config.enable_history:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO connection_history (
                    device_id, resource_name, event_type, timestamp, success
                ) VALUES (?, ?, ?, ?, ?)
            """,
                (device_id, resource_name, "disconnected", datetime.now(), True),
            )

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to record disconnection: {e}")
            conn.rollback()

        finally:
            conn.close()

    def _update_last_known_good(
        self,
        cursor: sqlite3.Cursor,
        device_id: str,
        resource_name: str,
        response_time_ms: Optional[float],
        manufacturer: Optional[str],
        model: Optional[str],
        ip_address: Optional[str],
    ):
        """Update last known good configuration.

        Args:
            cursor: Database cursor
            device_id: Device identifier
            resource_name: VISA resource name
            response_time_ms: Response time
            manufacturer: Manufacturer
            model: Model
            ip_address: IP address
        """
        # Get existing record
        cursor.execute(
            "SELECT connection_count, avg_response_time_ms FROM last_known_good WHERE device_id = ?",
            (device_id,),
        )
        row = cursor.fetchone()

        if row:
            # Update existing
            count, avg_time = row
            new_count = count + 1

            # Update average response time
            if response_time_ms is not None:
                if avg_time > 0:
                    new_avg = (avg_time * count + response_time_ms) / new_count
                else:
                    new_avg = response_time_ms
            else:
                new_avg = avg_time

            cursor.execute(
                """
                UPDATE last_known_good
                SET resource_name = ?,
                    last_successful = ?,
                    connection_count = ?,
                    manufacturer = COALESCE(?, manufacturer),
                    model = COALESCE(?, model),
                    ip_address = COALESCE(?, ip_address),
                    avg_response_time_ms = ?
                WHERE device_id = ?
            """,
                (
                    resource_name,
                    datetime.now(),
                    new_count,
                    manufacturer,
                    model,
                    ip_address,
                    new_avg,
                    device_id,
                ),
            )
        else:
            # Insert new
            cursor.execute(
                """
                INSERT INTO last_known_good (
                    device_id, resource_name, last_successful, connection_count,
                    manufacturer, model, ip_address, avg_response_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    device_id,
                    resource_name,
                    datetime.now(),
                    1,
                    manufacturer,
                    model,
                    ip_address,
                    response_time_ms or 0.0,
                ),
            )

    def get_last_known_good(self, device_id: str) -> Optional[LastKnownGood]:
        """Get last known good configuration for device.

        Args:
            device_id: Device identifier

        Returns:
            Last known good or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT * FROM last_known_good WHERE device_id = ?", (device_id,)
            )
            row = cursor.fetchone()

            if row:
                return LastKnownGood(
                    device_id=row[0],
                    resource_name=row[1],
                    last_successful=datetime.fromisoformat(row[2]),
                    connection_count=row[3],
                    manufacturer=row[4],
                    model=row[5],
                    serial_number=row[6],
                    ip_address=row[7],
                    hostname=row[8],
                    avg_response_time_ms=row[9],
                    last_error=row[10],
                )

            return None

        finally:
            conn.close()

    def get_history(
        self,
        device_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[ConnectionHistoryEntry]:
        """Get connection history.

        Args:
            device_id: Filter by device ID
            event_type: Filter by event type
            limit: Maximum entries to return

        Returns:
            List of history entries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            query = "SELECT * FROM connection_history WHERE 1=1"
            params = []

            if device_id:
                query += " AND device_id = ?"
                params.append(device_id)

            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            entries = []
            for row in rows:
                entry = ConnectionHistoryEntry(
                    entry_id=row[0],
                    device_id=row[1],
                    resource_name=row[2],
                    event_type=row[3],
                    timestamp=datetime.fromisoformat(row[4]),
                    success=bool(row[5]),
                    error_message=row[6],
                    connection_time_ms=row[7],
                    manufacturer=row[8],
                    model=row[9],
                    firmware_version=row[10],
                    user_id=row[11],
                    session_id=row[12],
                    discovery_method=row[13],
                    ip_address=row[14],
                )
                entries.append(entry)

            return entries

        finally:
            conn.close()

    def get_statistics(self, device_id: str) -> Optional[ConnectionStatistics]:
        """Get connection statistics for device.

        Args:
            device_id: Device identifier

        Returns:
            Connection statistics or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get total connections
            cursor.execute(
                """
                SELECT COUNT(*),
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END),
                       AVG(CASE WHEN connection_time_ms IS NOT NULL THEN connection_time_ms END),
                       MIN(CASE WHEN connection_time_ms IS NOT NULL THEN connection_time_ms END),
                       MAX(CASE WHEN connection_time_ms IS NOT NULL THEN connection_time_ms END),
                       MIN(timestamp),
                       MAX(timestamp)
                FROM connection_history
                WHERE device_id = ? AND event_type IN ('connected', 'failed')
            """,
                (device_id,),
            )

            row = cursor.fetchone()
            if not row or row[0] == 0:
                return None

            total = row[0]
            successful = row[1] or 0
            failed = row[2] or 0
            avg_time = row[3] or 0.0
            min_time = row[4]
            max_time = row[5]
            first_conn = datetime.fromisoformat(row[6]) if row[6] else None
            last_conn = datetime.fromisoformat(row[7]) if row[7] else None

            # Get last successful connection
            cursor.execute(
                """
                SELECT timestamp FROM connection_history
                WHERE device_id = ? AND success = 1
                ORDER BY timestamp DESC LIMIT 1
            """,
                (device_id,),
            )
            last_successful_row = cursor.fetchone()
            last_successful = (
                datetime.fromisoformat(last_successful_row[0])
                if last_successful_row
                else None
            )

            # Get last failed connection
            cursor.execute(
                """
                SELECT timestamp, error_message FROM connection_history
                WHERE device_id = ? AND success = 0
                ORDER BY timestamp DESC LIMIT 1
            """,
                (device_id,),
            )
            last_failed_row = cursor.fetchone()
            last_failed = (
                datetime.fromisoformat(last_failed_row[0]) if last_failed_row else None
            )
            last_error = last_failed_row[1] if last_failed_row else None

            # Count recent consecutive failures
            cursor.execute(
                """
                SELECT success FROM connection_history
                WHERE device_id = ?
                ORDER BY timestamp DESC
                LIMIT 10
            """,
                (device_id,),
            )
            recent = cursor.fetchall()
            recent_failures = 0
            for r in recent:
                if r[0] == 0:
                    recent_failures += 1
                else:
                    break

            return ConnectionStatistics(
                device_id=device_id,
                total_connections=total,
                successful_connections=successful,
                failed_connections=failed,
                success_rate=successful / total if total > 0 else 0.0,
                avg_connection_time_ms=avg_time,
                min_connection_time_ms=min_time,
                max_connection_time_ms=max_time,
                first_connection=first_conn,
                last_connection=last_conn,
                last_successful=last_successful,
                last_failed=last_failed,
                recent_failures=recent_failures,
                last_error=last_error,
            )

        finally:
            conn.close()

    def cleanup(self):
        """Clean up old history entries."""
        if not self.config.enable_history:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Delete entries older than retention period
            cutoff = datetime.now() - timedelta(days=self.config.history_retention_days)

            cursor.execute(
                "DELETE FROM connection_history WHERE timestamp < ?", (cutoff,)
            )

            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old history entries")

            # Limit total entries
            cursor.execute(
                """
                DELETE FROM connection_history
                WHERE entry_id NOT IN (
                    SELECT entry_id FROM connection_history
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
            """,
                (self.config.max_history_entries,),
            )

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to cleanup history: {e}")
            conn.rollback()

        finally:
            conn.close()
