"""Persistent storage for scheduler using SQLite."""

import sqlite3
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from .models import ScheduleConfig, JobExecution, JobStatus

logger = logging.getLogger(__name__)


class SchedulerStorage:
    """SQLite-backed storage for scheduler data."""

    def __init__(self, db_path: str = "data/scheduler.db"):
        """
        Initialize scheduler storage.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _init_database(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                job_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                schedule_type TEXT NOT NULL,
                equipment_id TEXT,
                trigger_type TEXT NOT NULL,
                cron_expression TEXT,
                interval_seconds INTEGER,
                interval_minutes INTEGER,
                interval_hours INTEGER,
                interval_days INTEGER,
                run_date TEXT,
                time_of_day TEXT,
                day_of_week INTEGER,
                day_of_month INTEGER,
                parameters TEXT,
                enabled INTEGER DEFAULT 1,
                max_instances INTEGER DEFAULT 1,
                misfire_grace_time INTEGER DEFAULT 300,
                coalesce INTEGER DEFAULT 1,
                start_date TEXT,
                end_date TEXT,
                max_executions INTEGER,
                created_at TEXT NOT NULL,
                created_by TEXT,
                tags TEXT,
                profile_id TEXT,
                on_failure_alarm INTEGER DEFAULT 0,
                conflict_policy TEXT DEFAULT 'skip'
            )
        """)

        # Execution history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_executions (
                execution_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                duration_seconds REAL,
                result TEXT,
                error TEXT,
                output TEXT,
                scheduled_time TEXT NOT NULL,
                actual_time TEXT,
                trigger_info TEXT,
                FOREIGN KEY (job_id) REFERENCES scheduled_jobs(job_id) ON DELETE CASCADE
            )
        """)

        # Execution counts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_execution_counts (
                job_id TEXT PRIMARY KEY,
                execution_count INTEGER DEFAULT 0,
                last_updated TEXT,
                FOREIGN KEY (job_id) REFERENCES scheduled_jobs(job_id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_enabled ON scheduled_jobs(enabled)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_job_id ON job_executions(job_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_status ON job_executions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_scheduled_time ON job_executions(scheduled_time)")

        conn.commit()
        conn.close()

        logger.info(f"Scheduler storage initialized at {self.db_path}")

    def save_job(self, config: ScheduleConfig) -> bool:
        """
        Save job configuration to database.

        Args:
            config: Job configuration to save

        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO scheduled_jobs (
                    job_id, name, description, schedule_type, equipment_id,
                    trigger_type, cron_expression, interval_seconds, interval_minutes,
                    interval_hours, interval_days, run_date, time_of_day,
                    day_of_week, day_of_month, parameters, enabled, max_instances,
                    misfire_grace_time, coalesce, start_date, end_date,
                    max_executions, created_at, created_by, tags, profile_id,
                    on_failure_alarm, conflict_policy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                config.job_id,
                config.name,
                config.description,
                config.schedule_type.value,
                config.equipment_id,
                config.trigger_type.value,
                config.cron_expression,
                config.interval_seconds,
                config.interval_minutes,
                config.interval_hours,
                config.interval_days,
                config.run_date.isoformat() if config.run_date else None,
                config.time_of_day,
                config.day_of_week,
                config.day_of_month,
                json.dumps(config.parameters),
                1 if config.enabled else 0,
                config.max_instances,
                config.misfire_grace_time,
                1 if config.coalesce else 0,
                config.start_date.isoformat() if config.start_date else None,
                config.end_date.isoformat() if config.end_date else None,
                config.max_executions,
                config.created_at.isoformat(),
                config.created_by,
                json.dumps(config.tags),
                getattr(config, 'profile_id', None),
                1 if getattr(config, 'on_failure_alarm', False) else 0,
                getattr(config, 'conflict_policy', 'skip')
            ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Error saving job {config.job_id}: {e}")
            return False

    def load_job(self, job_id: str) -> Optional[ScheduleConfig]:
        """
        Load job configuration from database.

        Args:
            job_id: Job ID to load

        Returns:
            Job configuration or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM scheduled_jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return self._row_to_config(row)

        except Exception as e:
            logger.error(f"Error loading job {job_id}: {e}")
            return None

    def load_all_jobs(self) -> List[ScheduleConfig]:
        """
        Load all jobs from database.

        Returns:
            List of job configurations
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM scheduled_jobs")
            rows = cursor.fetchall()
            conn.close()

            return [self._row_to_config(row) for row in rows]

        except Exception as e:
            logger.error(f"Error loading jobs: {e}")
            return []

    def delete_job(self, job_id: str) -> bool:
        """
        Delete job from database.

        Args:
            job_id: Job ID to delete

        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("DELETE FROM scheduled_jobs WHERE job_id = ?", (job_id,))
            conn.commit()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Error deleting job {job_id}: {e}")
            return False

    def save_execution(self, execution: JobExecution) -> bool:
        """
        Save job execution to database.

        Args:
            execution: Job execution to save

        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO job_executions (
                    execution_id, job_id, status, started_at, completed_at,
                    duration_seconds, result, error, output, scheduled_time,
                    actual_time, trigger_info
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                execution.execution_id,
                execution.job_id,
                execution.status.value,
                execution.started_at.isoformat() if execution.started_at else None,
                execution.completed_at.isoformat() if execution.completed_at else None,
                execution.duration_seconds,
                json.dumps(execution.result) if execution.result else None,
                execution.error,
                execution.output,
                execution.scheduled_time.isoformat(),
                execution.actual_time.isoformat() if execution.actual_time else None,
                json.dumps(execution.trigger_info)
            ))

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Error saving execution {execution.execution_id}: {e}")
            return False

    def load_executions(
        self,
        job_id: Optional[str] = None,
        limit: int = 100,
        status: Optional[JobStatus] = None
    ) -> List[JobExecution]:
        """
        Load job executions from database.

        Args:
            job_id: Optional job ID to filter by
            limit: Maximum number of executions to load
            status: Optional status to filter by

        Returns:
            List of job executions
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM job_executions WHERE 1=1"
            params = []

            if job_id:
                query += " AND job_id = ?"
                params.append(job_id)

            if status:
                query += " AND status = ?"
                params.append(status.value)

            query += " ORDER BY scheduled_time DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            return [self._row_to_execution(row) for row in rows]

        except Exception as e:
            logger.error(f"Error loading executions: {e}")
            return []

    def get_execution_count(self, job_id: str) -> int:
        """
        Get total execution count for a job.

        Args:
            job_id: Job ID

        Returns:
            Execution count
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT execution_count FROM job_execution_counts WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            conn.close()

            return row[0] if row else 0

        except Exception as e:
            logger.error(f"Error getting execution count for {job_id}: {e}")
            return 0

    def increment_execution_count(self, job_id: str) -> bool:
        """
        Increment execution count for a job.

        Args:
            job_id: Job ID

        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO job_execution_counts (job_id, execution_count, last_updated)
                VALUES (?, 1, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    execution_count = execution_count + 1,
                    last_updated = ?
            """, (job_id, datetime.now().isoformat(), datetime.now().isoformat()))

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Error incrementing execution count for {job_id}: {e}")
            return False

    def cleanup_old_executions(self, days: int = 30) -> int:
        """
        Clean up old execution records.

        Args:
            days: Delete executions older than this many days

        Returns:
            Number of records deleted
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM job_executions WHERE scheduled_time < ?",
                (cutoff.isoformat(),)
            )

            deleted = cursor.rowcount
            conn.commit()
            conn.close()

            logger.info(f"Cleaned up {deleted} old execution records")
            return deleted

        except Exception as e:
            logger.error(f"Error cleaning up old executions: {e}")
            return 0

    def _row_to_config(self, row: sqlite3.Row) -> ScheduleConfig:
        """Convert database row to ScheduleConfig."""
        from .models import ScheduleType, TriggerType

        config_dict = {
            "job_id": row["job_id"],
            "name": row["name"],
            "description": row["description"],
            "schedule_type": ScheduleType(row["schedule_type"]),
            "equipment_id": row["equipment_id"],
            "trigger_type": TriggerType(row["trigger_type"]),
            "cron_expression": row["cron_expression"],
            "interval_seconds": row["interval_seconds"],
            "interval_minutes": row["interval_minutes"],
            "interval_hours": row["interval_hours"],
            "interval_days": row["interval_days"],
            "time_of_day": row["time_of_day"],
            "day_of_week": row["day_of_week"],
            "day_of_month": row["day_of_month"],
            "parameters": json.loads(row["parameters"]) if row["parameters"] else {},
            "enabled": bool(row["enabled"]),
            "max_instances": row["max_instances"],
            "misfire_grace_time": row["misfire_grace_time"],
            "coalesce": bool(row["coalesce"]),
            "max_executions": row["max_executions"],
            "created_by": row["created_by"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
        }

        # Parse dates
        if row["run_date"]:
            config_dict["run_date"] = datetime.fromisoformat(row["run_date"])
        if row["start_date"]:
            config_dict["start_date"] = datetime.fromisoformat(row["start_date"])
        if row["end_date"]:
            config_dict["end_date"] = datetime.fromisoformat(row["end_date"])
        if row["created_at"]:
            config_dict["created_at"] = datetime.fromisoformat(row["created_at"])

        # Extended fields
        config_dict["profile_id"] = row["profile_id"]
        config_dict["on_failure_alarm"] = bool(row["on_failure_alarm"])
        config_dict["conflict_policy"] = row["conflict_policy"]

        return ScheduleConfig(**config_dict)

    def _row_to_execution(self, row: sqlite3.Row) -> JobExecution:
        """Convert database row to JobExecution."""
        execution_dict = {
            "execution_id": row["execution_id"],
            "job_id": row["job_id"],
            "status": JobStatus(row["status"]),
            "duration_seconds": row["duration_seconds"],
            "error": row["error"],
            "output": row["output"],
            "scheduled_time": datetime.fromisoformat(row["scheduled_time"]),
            "trigger_info": json.loads(row["trigger_info"]) if row["trigger_info"] else {},
        }

        if row["started_at"]:
            execution_dict["started_at"] = datetime.fromisoformat(row["started_at"])
        if row["completed_at"]:
            execution_dict["completed_at"] = datetime.fromisoformat(row["completed_at"])
        if row["actual_time"]:
            execution_dict["actual_time"] = datetime.fromisoformat(row["actual_time"])
        if row["result"]:
            execution_dict["result"] = json.loads(row["result"])

        return JobExecution(**execution_dict)
