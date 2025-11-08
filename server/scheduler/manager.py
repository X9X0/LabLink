"""Scheduler management with APScheduler."""

import asyncio
import logging
from typing import Dict, List, Optional
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

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages scheduled jobs and executions."""

    def __init__(self):
        """Initialize scheduler manager."""
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._jobs: Dict[str, ScheduleConfig] = {}
        self._executions: Dict[str, JobExecution] = {}
        self._history: List[JobExecution] = []
        self._execution_counts: Dict[str, int] = defaultdict(int)
        self._max_history = 1000

    async def start(self):
        """Start the scheduler."""
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

    async def shutdown(self):
        """Shutdown the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler shut down")

    async def create_job(self, config: ScheduleConfig) -> ScheduleConfig:
        """Create a new scheduled job."""
        if config.job_id in self._jobs:
            raise ValueError(f"Job {config.job_id} already exists")

        self._jobs[config.job_id] = config

        if config.enabled:
            await self._add_to_scheduler(config)

        logger.info(f"Created job: {config.job_id} ({config.name})")
        return config

    async def update_job(self, job_id: str, config: ScheduleConfig) -> ScheduleConfig:
        """Update a scheduled job."""
        if job_id not in self._jobs:
            raise ValueError(f"Job {job_id} not found")

        # Remove from scheduler
        if self._scheduler and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        self._jobs[job_id] = config

        # Re-add if enabled
        if config.enabled:
            await self._add_to_scheduler(config)

        logger.info(f"Updated job: {job_id}")
        return config

    async def delete_job(self, job_id: str) -> bool:
        """Delete a scheduled job."""
        if job_id not in self._jobs:
            return False

        # Remove from scheduler
        if self._scheduler and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

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
        logger.info(f"Resumed job: {job_id}")
        return True

    async def run_job_now(self, job_id: str) -> JobExecution:
        """Manually trigger a job to run immediately."""
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
        return self._executions.get(execution_id)

    def list_executions(self, job_id: Optional[str] = None, limit: int = 100) -> List[JobExecution]:
        """List job executions."""
        executions = list(self._executions.values()) + self._history

        if job_id:
            executions = [e for e in executions if e.job_id == job_id]

        executions.sort(key=lambda e: e.scheduled_time, reverse=True)
        return executions[:limit]

    def get_job_history(self, job_id: str) -> JobHistory:
        """Get job execution history."""
        if job_id not in self._jobs:
            return None

        config = self._jobs[job_id]
        executions = [e for e in self._history if e.job_id == job_id]

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
        today_executions = [e for e in self._history if e.scheduled_time >= today]

        stats = ScheduleStatistics(
            total_jobs=len(self._jobs),
            active_jobs=len([j for j in self._jobs.values() if j.enabled]),
            disabled_jobs=len([j for j in self._jobs.values() if not j.enabled]),
            running_executions=len([e for e in self._executions.values() if e.status == JobStatus.RUNNING]),
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
        """Wrapper to execute scheduled job."""
        execution = JobExecution(
            job_id=config.job_id,
            scheduled_time=datetime.now()
        )

        self._executions[execution.execution_id] = execution

        # Check execution limit
        if config.max_executions:
            count = self._execution_counts[config.job_id]
            if count >= config.max_executions:
                execution.status = JobStatus.SKIPPED
                execution.error = "Maximum executions reached"
                return

        await self._execute_job(config, execution)

    async def _execute_job(self, config: ScheduleConfig, execution: JobExecution):
        """Execute a scheduled job."""
        execution.status = JobStatus.RUNNING
        execution.started_at = datetime.now()
        execution.actual_time = execution.started_at

        try:
            if config.schedule_type == ScheduleType.ACQUISITION:
                result = await self._run_acquisition(config)
            elif config.schedule_type == ScheduleType.STATE_CAPTURE:
                result = await self._capture_state(config)
            elif config.schedule_type == ScheduleType.MEASUREMENT:
                result = await self._take_measurement(config)
            elif config.schedule_type == ScheduleType.COMMAND:
                result = await self._execute_command(config)
            else:
                result = {"status": "not_implemented"}

            execution.status = JobStatus.COMPLETED
            execution.result = result

        except Exception as e:
            execution.status = JobStatus.FAILED
            execution.error = str(e)
            logger.error(f"Job {config.job_id} failed: {e}")

        finally:
            execution.completed_at = datetime.now()
            if execution.started_at:
                execution.duration_seconds = (execution.completed_at - execution.started_at).total_seconds()

            # Move to history
            self._history.append(execution)
            if len(self._history) > self._max_history:
                self._history.pop(0)

            del self._executions[execution.execution_id]
            self._execution_counts[config.job_id] += 1

    async def _run_acquisition(self, config: ScheduleConfig) -> dict:
        """Run scheduled acquisition."""
        from acquisition import acquisition_manager, AcquisitionConfig

        acq_config = AcquisitionConfig(**config.parameters)
        session = await acquisition_manager.create_session(
            equipment_manager.get_equipment(config.equipment_id),
            acq_config
        )
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


# Global scheduler manager
scheduler_manager = SchedulerManager()
