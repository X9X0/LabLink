"""Database migration system for LabLink."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Migration:
    """Base class for database migrations."""

    def __init__(self, version: int, description: str):
        """Initialize migration.

        Args:
            version: Migration version number
            description: Migration description
        """
        self.version = version
        self.description = description

    def up(self, conn: sqlite3.Connection):
        """Apply migration.

        Args:
            conn: Database connection
        """
        raise NotImplementedError

    def down(self, conn: sqlite3.Connection):
        """Rollback migration.

        Args:
            conn: Database connection
        """
        raise NotImplementedError


class MigrationManager:
    """Manages database migrations."""

    def __init__(self, db_path: str):
        """Initialize migration manager.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.migrations: List[Migration] = []

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection.

        Returns:
            Database connection
        """
        return sqlite3.connect(self.db_path)

    def _create_migrations_table(self):
        """Create migrations tracking table."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
        """
        )

        conn.commit()
        conn.close()

    def register_migration(self, migration: Migration):
        """Register a migration.

        Args:
            migration: Migration to register
        """
        self.migrations.append(migration)
        # Sort by version
        self.migrations.sort(key=lambda m: m.version)

    def get_current_version(self) -> int:
        """Get current database version.

        Returns:
            Current version number (0 if no migrations applied)
        """
        self._create_migrations_table()

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(version) FROM schema_migrations")
        result = cursor.fetchone()
        version = result[0] if result[0] is not None else 0

        conn.close()

        return version

    def get_applied_migrations(self) -> List[Dict[str, Any]]:
        """Get list of applied migrations.

        Returns:
            List of applied migration records
        """
        self._create_migrations_table()

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT version, description, applied_at FROM schema_migrations ORDER BY version"
        )
        rows = cursor.fetchall()

        conn.close()

        return [
            {"version": row[0], "description": row[1], "applied_at": row[2]}
            for row in rows
        ]

    def get_pending_migrations(self) -> List[Migration]:
        """Get list of pending migrations.

        Returns:
            List of migrations that haven't been applied
        """
        current_version = self.get_current_version()
        return [m for m in self.migrations if m.version > current_version]

    def migrate(self, target_version: Optional[int] = None):
        """Apply pending migrations up to target version.

        Args:
            target_version: Target version (applies all if None)
        """
        self._create_migrations_table()

        pending = self.get_pending_migrations()

        if target_version:
            pending = [m for m in pending if m.version <= target_version]

        if not pending:
            logger.info("No pending migrations")
            return

        conn = self._get_connection()

        for migration in pending:
            try:
                logger.info(
                    f"Applying migration {migration.version}: {migration.description}"
                )

                # Apply migration
                migration.up(conn)

                # Record migration
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                    (
                        migration.version,
                        migration.description,
                        datetime.now().isoformat(),
                    ),
                )

                conn.commit()

                logger.info(f"Migration {migration.version} applied successfully")

            except Exception as e:
                logger.error(f"Migration {migration.version} failed: {e}")
                conn.rollback()
                raise

        conn.close()

    def rollback(self, target_version: int):
        """Rollback migrations to target version.

        Args:
            target_version: Target version to rollback to
        """
        current_version = self.get_current_version()

        if target_version >= current_version:
            logger.info("Nothing to rollback")
            return

        # Get migrations to rollback (in reverse order)
        to_rollback = [
            m
            for m in reversed(self.migrations)
            if target_version < m.version <= current_version
        ]

        if not to_rollback:
            logger.warning("No migrations found to rollback")
            return

        conn = self._get_connection()

        for migration in to_rollback:
            try:
                logger.info(
                    f"Rolling back migration {migration.version}: {migration.description}"
                )

                # Rollback migration
                migration.down(conn)

                # Remove migration record
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    (migration.version,),
                )

                conn.commit()

                logger.info(f"Migration {migration.version} rolled back successfully")

            except Exception as e:
                logger.error(f"Rollback of migration {migration.version} failed: {e}")
                conn.rollback()
                raise

        conn.close()


# Example migration for adding indices
class AddPerformanceIndicesMigration(Migration):
    """Add performance indices for common queries."""

    def __init__(self):
        super().__init__(version=1, description="Add performance indices")

    def up(self, conn: sqlite3.Connection):
        """Apply migration."""
        cursor = conn.cursor()

        # Additional indices for better query performance
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_command_session ON command_history(session_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_measurement_session ON measurements(session_id)"
        )

        conn.commit()

    def down(self, conn: sqlite3.Connection):
        """Rollback migration."""
        cursor = conn.cursor()

        cursor.execute("DROP INDEX IF EXISTS idx_command_session")
        cursor.execute("DROP INDEX IF EXISTS idx_measurement_session")

        conn.commit()
