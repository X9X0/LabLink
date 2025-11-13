"""Scheduler management with APScheduler, SQLite persistence, and integrations."""

import asyncio
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from .models import (
    ScheduleConfig,
    JobExecution,
    JobHistory,
    JobStatus,
    ScheduleType,
    TriggerType,
    ScheduleStatistics,
)
from .storage import SchedulerStorage

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages scheduled jobs with persistence, conflict detection, and integrations."""

    def __init__(self, db_path: str = "data/scheduler.db"):
        """
        Initialize scheduler manager.

        Args:
            db_path: Path to SQLite database for persistence
        """
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._jobs: Dict[str, ScheduleConfig] = {}
        self._executions: Dict[str, JobExecution] = {}
        self._running_jobs: Set[str] = set()  # Track running jobs for conflict detection
        self._storage = SchedulerStorage(db_path)
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the scheduler and load persisted jobs."""
        if self._scheduler is None:
            jobstores = {'default': MemoryJobStore()}
            executors = {'default': AsyncIOExecutor()}
            job_defaults = {
                'coalesce': True,
                'max_instances': 3,
                'misfire_grace_time': 300
            }

            self._scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults
            )

            self._scheduler.start()
            logger.info("Scheduler started")

            # Load persisted jobs from database
            await self._load_jobs_from_storage()

            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.info("Scheduler cleanup task started")

    async def shutdown(self):
        """Shutdown the scheduler."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._scheduler:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler shut down")

    async def create_job(self, config: ScheduleConfig) -> ScheduleConfig:
        """
        Create a new scheduled job with persistence.

        Args:
            config: Job configuration

        Returns:
            Created job configuration

        Raises:
            ValueError: If job ID already exists
        """
        if config.job_id in self._jobs:
            raise ValueError(f"Job {config.job_id} already exists")

        # Validate profile if specified
        if config.profile_id:
            await self._validate_profile(config.profile_id)

        # Save to database
        self._storage.save_job(config)

        self._jobs[config.job_id] = config

        if config.enabled:
            await self._add_to_scheduler(config)

        logger.info(f"Created job: {config.job_id} ({config.name})")
        return config

    async def update_job(self, job_id: str, config: ScheduleConfig) -> ScheduleConfig:
        """
        Update a scheduled job.

        Args:
            job_id: Job ID to update
            config: New job configuration

        Returns:
            Updated job configuration

        Raises:
            ValueError: If job not found
        """
        if job_id not in self._jobs:
            raise ValueError(f"Job {job_id} not found")

        # Validate profile if specified
        if config.profile_id:
            await self._validate_profile(config.profile_id)

        # Remove from scheduler
        if self._scheduler and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        # Update database
        self._storage.save_job(config)

        self._jobs[job_id] = config

        # Re-add if enabled
        if config.enabled:
            await self._add_to_scheduler(config)

        logger.info(f"Updated job: {job_id}")
        return config

    async def delete_job(self, job_id: str) -> bool:
        """
        Delete a scheduled job from scheduler and database.

        Args:
            job_id: Job ID to delete

        Returns:
            True if successful
        """
        if job_id not in self._jobs:
            return False

        # Remove from scheduler
        if self._scheduler and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        # Delete from database
        self._storage.delete_job(job_id)

        del self._jobs[job_id]
        logger.info(f"Deleted job: {job_id}")
        return True

    async def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        if job_id not in self._jobs:
            return False

        if self._scheduler and self._scheduler.get_job(job_id):
            self._scheduler.pause_job(job_id)

        self._jobs[job_id].enabled = False
        self._storage.save_job(self._jobs[job_id])

        logger.info(f"Paused job: {job_id}")
        return True

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        if job_id not in self._jobs:
            return False

        if self._scheduler and self._scheduler.get_job(job_id):
            self._scheduler.resume_job(job_id)
        else:
            await self._add_to_scheduler(self._jobs[job_id])

        self._jobs[job_id].enabled = True
        self._storage.save_job(self._jobs[job_id])

        logger.info(f"Resumed job: {job_id}")
        return True

    async def run_job_now(self, job_id: str) -> JobExecution:
        """
        Manually trigger a job to run immediately.

        Args:
            job_id: Job ID to run

        Returns:
            Job execution instance

        Raises:
            ValueError: If job not found
        """
        if job_id not in self._jobs:
            raise ValueError(f"Job {job_id} not found")

        config = self._jobs[job_id]
        execution = JobExecution(
            job_id=job_id,
            scheduled_time=datetime.now()
        )

        self._executions[execution.execution_id] = execution
        await self._execute_job(config, execution)

        return execution

    def get_job(self, job_id: str) -> Optional[ScheduleConfig]:
        """Get job configuration."""
        return self._jobs.get(job_id)

    def list_jobs(self, enabled: Optional[bool] = None) -> List[ScheduleConfig]:
        """List all jobs."""
        jobs = list(self._jobs.values())
        if enabled is not None:
            jobs = [j for j in jobs if j.enabled == enabled]
        return jobs

    def get_execution(self, execution_id: str) -> Optional[JobExecution]:
        """Get execution details."""
        # Check memory first
        if execution_id in self._executions:
            return self._executions[execution_id]

        # Check storage
        executions = self._storage.load_executions(limit=1000)
        for exec in executions:
            if exec.execution_id == execution_id:
                return exec

        return None

    def list_executions(self, job_id: Optional[str] = None, limit: int = 100) -> List[JobExecution]:
        """
        List job executions from storage.

        Args:
            job_id: Optional job ID to filter by
            limit: Maximum number of executions to return

        Returns:
            List of job executions
        """
        # Combine memory and storage
        memory_execs = list(self._executions.values())
        storage_execs = self._storage.load_executions(job_id=job_id, limit=limit)

        all_execs = memory_execs + storage_execs

        # Deduplicate by execution_id
        seen = set()
        unique_execs = []
        for exec in all_execs:
            if exec.execution_id not in seen:
                seen.add(exec.execution_id)
                unique_execs.append(exec)

        # Sort and limit
        unique_execs.sort(key=lambda e: e.scheduled_time, reverse=True)
        return unique_execs[:limit]

    def get_job_history(self, job_id: str) -> Optional[JobHistory]:
        """Get job execution history."""
        if job_id not in self._jobs:
            return None

        config = self._jobs[job_id]
        executions = self._storage.load_executions(job_id=job_id, limit=1000)

        history = JobHistory(
            job_id=job_id,
            job_name=config.name,
            total_executions=len(executions),
            successful=len([e for e in executions if e.status == JobStatus.COMPLETED]),
            failed=len([e for e in executions if e.status == JobStatus.FAILED]),
            cancelled=len([e for e in executions if e.status == JobStatus.CANCELLED])
        )

        if executions:
            history.last_execution = max(e.scheduled_time for e in executions)
            history.last_status = next(e.status for e in sorted(executions, key=lambda x: x.scheduled_time, reverse=True))

            completed = [e for e in executions if e.duration_seconds is not None]
            if completed:
                history.average_duration = sum(e.duration_seconds for e in completed) / len(completed)

        # Get next run time from scheduler
        if self._scheduler:
            job = self._scheduler.get_job(job_id)
            if job:
                history.next_run = job.next_run_time

        return history

    def get_statistics(self) -> ScheduleStatistics:
        """Get scheduler statistics."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_executions = self._storage.load_executions(limit=10000)
        today_executions = [e for e in today_executions if e.scheduled_time >= today]

        stats = ScheduleStatistics(
            total_jobs=len(self._jobs),
            active_jobs=len([j for j in self._jobs.values() if j.enabled]),
            disabled_jobs=len([j for j in self._jobs.values() if not j.enabled]),
            running_executions=len(self._running_jobs),
            total_executions_today=len(today_executions),
            successful_today=len([e for e in today_executions if e.status == JobStatus.COMPLETED]),
            failed_today=len([e for e in today_executions if e.status == JobStatus.FAILED])
        )

        # Count by type
        type_counts = defaultdict(int)
        for job in self._jobs.values():
            type_counts[job.schedule_type] += 1
        stats.by_type = dict(type_counts)

        # Upcoming jobs
        if self._scheduler:
            upcoming = []
            for job in self._scheduler.get_jobs():
                if job.next_run_time:
                    upcoming.append({
                        "job_id": job.id,
                        "job_name": self._jobs[job.id].name if job.id in self._jobs else "Unknown",
                        "next_run": job.next_run_time.isoformat()
                    })
            upcoming.sort(key=lambda x: x["next_run"])
            stats.upcoming_jobs = upcoming[:10]

        return stats

    def get_running_jobs(self) -> List[str]:
        """Get list of currently running job IDs."""
        return list(self._running_jobs)

    async def _load_jobs_from_storage(self):
        """Load all jobs from persistent storage."""
        jobs = self._storage.load_all_jobs()
        logger.info(f"Loading {len(jobs)} jobs from storage...")

        for config in jobs:
            self._jobs[config.job_id] = config

            if config.enabled:
                try:
                    await self._add_to_scheduler(config)
                    logger.info(f"Restored job: {config.job_id} ({config.name})")
                except Exception as e:
                    logger.error(f"Error restoring job {config.job_id}: {e}")

        logger.info(f"Restored {len(jobs)} scheduled jobs from database")

    async def _periodic_cleanup(self):
        """Periodic cleanup task for old execution records."""
        while True:
            try:
                await asyncio.sleep(86400)  # Run daily
                deleted = self._storage.cleanup_old_executions(days=30)
                logger.info(f"Periodic cleanup: removed {deleted} old execution records")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")

    async def _add_to_scheduler(self, config: ScheduleConfig):
        """Add job to APScheduler."""
        if not self._scheduler:
            return

        trigger = self._create_trigger(config)
        if not trigger:
            logger.warning(f"Could not create trigger for job {config.job_id}")
            return

        self._scheduler.add_job(
            func=lambda: self._schedule_wrapper(config),
            trigger=trigger,
            id=config.job_id,
            name=config.name,
            max_instances=config.max_instances,
            misfire_grace_time=config.misfire_grace_time,
            coalesce=config.coalesce,
            replace_existing=True
        )

    def _create_trigger(self, config: ScheduleConfig):
        """Create APScheduler trigger from config."""
        if config.trigger_type == TriggerType.CRON:
            if not config.cron_expression:
                return None
            return CronTrigger.from_crontab(config.cron_expression)

        elif config.trigger_type == TriggerType.INTERVAL:
            kwargs = {}
            if config.interval_seconds:
                kwargs['seconds'] = config.interval_seconds
            if config.interval_minutes:
                kwargs['minutes'] = config.interval_minutes
            if config.interval_hours:
                kwargs['hours'] = config.interval_hours
            if config.interval_days:
                kwargs['days'] = config.interval_days

            if not kwargs:
                return None

            return IntervalTrigger(**kwargs, start_date=config.start_date, end_date=config.end_date)

        elif config.trigger_type == TriggerType.DATE:
            if not config.run_date:
                return None
            return DateTrigger(run_date=config.run_date)

        elif config.trigger_type == TriggerType.DAILY:
            if not config.time_of_day:
                return None
            hour, minute, second = map(int, config.time_of_day.split(':'))
            return CronTrigger(hour=hour, minute=minute, second=second)

        elif config.trigger_type == TriggerType.WEEKLY:
            if config.day_of_week is None or not config.time_of_day:
                return None
            hour, minute, second = map(int, config.time_of_day.split(':'))
            return CronTrigger(day_of_week=config.day_of_week, hour=hour, minute=minute, second=second)

        elif config.trigger_type == TriggerType.MONTHLY:
            if config.day_of_month is None or not config.time_of_day:
                return None
            hour, minute, second = map(int, config.time_of_day.split(':'))
            return CronTrigger(day=config.day_of_month, hour=hour, minute=minute, second=second)

        return None

    async def _schedule_wrapper(self, config: ScheduleConfig):
        """Wrapper to execute scheduled job with conflict detection."""
        execution = JobExecution(
            job_id=config.job_id,
            scheduled_time=datetime.now()
        )

        self._executions[execution.execution_id] = execution

        # Check execution limit
        count = self._storage.get_execution_count(config.job_id)
        if config.max_executions and count >= config.max_executions:
            execution.status = JobStatus.SKIPPED
            execution.error = "Maximum executions reached"
            self._storage.save_execution(execution)
            del self._executions[execution.execution_id]
            return

        # Conflict detection
        if config.job_id in self._running_jobs:
            if config.conflict_policy == "skip":
                execution.status = JobStatus.SKIPPED
                execution.error = "Job already running (conflict_policy=skip)"
                self._storage.save_execution(execution)
                del self._executions[execution.execution_id]
                logger.info(f"Skipped job {config.job_id} due to conflict")
                return
            elif config.conflict_policy == "queue":
                # Wait for current execution to finish
                logger.info(f"Queuing job {config.job_id} due to conflict")
                while config.job_id in self._running_jobs:
                    await asyncio.sleep(1)
            # For "replace" policy, we continue and let max_instances handle it

        await self._execute_job(config, execution)

    async def _execute_job(self, config: ScheduleConfig, execution: JobExecution):
        """Execute a scheduled job with all integrations."""
        execution.status = JobStatus.RUNNING
        execution.started_at = datetime.now()
        execution.actual_time = execution.started_at
        self._running_jobs.add(config.job_id)

        try:
            # Apply profile if specified
            if config.profile_id:
                await self._apply_profile(config)

            # Execute based on type
            if config.schedule_type == ScheduleType.ACQUISITION:
                result = await self._run_acquisition(config)
            elif config.schedule_type == ScheduleType.STATE_CAPTURE:
                result = await self._capture_state(config)
            elif config.schedule_type == ScheduleType.MEASUREMENT:
                result = await self._take_measurement(config)
            elif config.schedule_type == ScheduleType.COMMAND:
                result = await self._execute_command(config)
            elif config.schedule_type == ScheduleType.EQUIPMENT_TEST:
                result = await self._run_equipment_test(config)
            else:
                result = {"status": "not_implemented"}

            execution.status = JobStatus.COMPLETED
            execution.result = result

            logger.info(f"Job {config.job_id} completed successfully")

        except Exception as e:
            execution.status = JobStatus.FAILED
            execution.error = str(e)
            logger.error(f"Job {config.job_id} failed: {e}")

            # Create alarm if enabled
            if config.on_failure_alarm:
                await self._create_failure_alarm(config, execution, e)

        finally:
            execution.completed_at = datetime.now()
            if execution.started_at:
                execution.duration_seconds = (execution.completed_at - execution.started_at).total_seconds()

            # Save to storage
            self._storage.save_execution(execution)
            self._storage.increment_execution_count(config.job_id)

            # Remove from memory and running set
            if execution.execution_id in self._executions:
                del self._executions[execution.execution_id]
            self._running_jobs.discard(config.job_id)

    async def _apply_profile(self, config: ScheduleConfig):
        """
        Apply equipment profile before job execution.

        Args:
            config: Job configuration with profile_id
        """
        try:
            from equipment.profiles import profile_manager
            from equipment.manager import equipment_manager

            if not config.equipment_id:
                logger.warning(f"Cannot apply profile {config.profile_id}: no equipment_id")
                return

            equipment = equipment_manager.get_equipment(config.equipment_id)
            if not equipment:
                logger.warning(f"Cannot apply profile: equipment {config.equipment_id} not found")
                return

            await profile_manager.apply_profile(equipment, config.profile_id)
            logger.info(f"Applied profile {config.profile_id} to {config.equipment_id}")

        except Exception as e:
            logger.error(f"Error applying profile {config.profile_id}: {e}")
            raise

    async def _validate_profile(self, profile_id: str):
        """
        Validate that a profile exists.

        Args:
            profile_id: Profile ID to validate

        Raises:
            ValueError: If profile not found
        """
        try:
            from equipment.profiles import profile_manager

            profile = profile_manager.get_profile(profile_id)
            if not profile:
                raise ValueError(f"Profile {profile_id} not found")

        except ImportError:
            logger.warning("Profile manager not available")

    async def _create_failure_alarm(self, config: ScheduleConfig, execution: JobExecution, error: Exception):
        """
        Create an alarm for job failure.

        Args:
            config: Job configuration
            execution: Failed job execution
            error: Exception that caused failure
        """
        try:
            from alarm import alarm_manager, AlarmSeverity

            alarm_manager.create_alarm(
                source=f"scheduler.{config.job_id}",
                severity=AlarmSeverity.ERROR,
                message=f"Scheduled job '{config.name}' failed",
                details={
                    "job_id": config.job_id,
                    "job_name": config.name,
                    "execution_id": execution.execution_id,
                    "error": str(error),
                    "equipment_id": config.equipment_id,
                    "schedule_type": config.schedule_type.value,
                    "scheduled_time": execution.scheduled_time.isoformat(),
                }
            )

            logger.info(f"Created failure alarm for job {config.job_id}")

        except ImportError:
            logger.warning("Alarm manager not available")
        except Exception as e:
            logger.error(f"Error creating failure alarm: {e}")

    async def _run_acquisition(self, config: ScheduleConfig) -> dict:
        """Run scheduled acquisition."""
        from acquisition import acquisition_manager, AcquisitionConfig
        from equipment.manager import equipment_manager

        acq_config = AcquisitionConfig(**config.parameters)
        equipment = equipment_manager.get_equipment(config.equipment_id)

        session = await acquisition_manager.create_session(equipment, acq_config)
        await acquisition_manager.start_acquisition(session.acquisition_id)

        return {"acquisition_id": session.acquisition_id, "status": "started"}

    async def _capture_state(self, config: ScheduleConfig) -> dict:
        """Capture equipment state."""
        from equipment.state import state_manager

        state = await state_manager.capture_state(config.equipment_id)
        return {"state_id": state.state_id, "timestamp": state.timestamp.isoformat()}

    async def _take_measurement(self, config: ScheduleConfig) -> dict:
        """Take single measurement."""
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(config.equipment_id)
        command = config.parameters.get("command", "get_readings")
        result = await equipment.execute_command(command, {})

        return {"measurement": result.dict() if hasattr(result, 'dict') else str(result)}

    async def _execute_command(self, config: ScheduleConfig) -> dict:
        """Execute equipment command."""
        from equipment.manager import equipment_manager

        equipment = equipment_manager.get_equipment(config.equipment_id)
        command = config.parameters.get("command")
        params = config.parameters.get("parameters", {})

        result = await equipment.execute_command(command, params)
        return {"result": result.dict() if hasattr(result, 'dict') else str(result)}

    async def _run_equipment_test(self, config: ScheduleConfig) -> dict:
        """Run equipment diagnostic test."""
        from diagnostics import diagnostics_manager

        equipment_id = config.equipment_id
        test_name = config.parameters.get("test_name", "connection")

        result = await diagnostics_manager.run_test(equipment_id, test_name)
        return {"test_result": result.dict() if hasattr(result, 'dict') else str(result)}


# Global scheduler manager
scheduler_manager = SchedulerManager()


def initialize_scheduler_manager(db_path: str = "data/scheduler.db") -> SchedulerManager:
    """
    Initialize global scheduler manager with custom database path.

    Args:
        db_path: Path to SQLite database

    Returns:
        Initialized scheduler manager
    """
    global scheduler_manager
    scheduler_manager = SchedulerManager(db_path)
    return scheduler_manager
