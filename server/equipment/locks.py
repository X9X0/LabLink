"""Equipment lock management system for multi-user access control.

Provides exclusive locks, observer mode, lock queuing, and automatic timeout.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LockMode(str, Enum):
    """Equipment lock modes."""

    EXCLUSIVE = "exclusive"  # Full control, blocks all other access
    OBSERVER = "observer"  # Read-only, doesn't block other observers


class LockStatus(str, Enum):
    """Lock status states."""

    LOCKED = "locked"
    UNLOCKED = "unlocked"
    QUEUED = "queued"


class EquipmentLock(BaseModel):
    """Represents a lock on a piece of equipment."""

    lock_id: str = Field(default_factory=lambda: str(uuid4()))
    equipment_id: str
    session_id: str
    lock_mode: LockMode
    acquired_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    timeout_seconds: int = Field(default=300, ge=0)  # 5 minutes default

    class Config:
        use_enum_values = True

    def is_expired(self) -> bool:
        """Check if lock has expired due to inactivity."""
        if self.timeout_seconds == 0:
            return False  # 0 = no timeout

        expiry_time = self.last_activity + timedelta(seconds=self.timeout_seconds)
        return datetime.now() > expiry_time

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()

    def time_remaining(self) -> Optional[float]:
        """Get remaining time before timeout in seconds."""
        if self.timeout_seconds == 0:
            return None  # No timeout

        expiry_time = self.last_activity + timedelta(seconds=self.timeout_seconds)
        remaining = (expiry_time - datetime.now()).total_seconds()
        return max(0.0, remaining)


class LockQueueEntry(BaseModel):
    """Entry in the equipment lock queue."""

    queue_id: str = Field(default_factory=lambda: str(uuid4()))
    equipment_id: str
    session_id: str
    lock_mode: LockMode
    queued_at: datetime = Field(default_factory=datetime.now)
    position: int = 0

    class Config:
        use_enum_values = True


class LockViolation(Exception):
    """Raised when attempting an operation that violates lock rules."""

    def __init__(
        self,
        message: str,
        equipment_id: str,
        current_lock: Optional[EquipmentLock] = None,
    ):
        self.equipment_id = equipment_id
        self.current_lock = current_lock
        super().__init__(message)


class LockManager:
    """Manages equipment locks across all sessions."""

    def __init__(self):
        self._locks: Dict[str, EquipmentLock] = {}  # equipment_id -> lock
        self._observer_locks: Dict[str, Set[str]] = (
            {}
        )  # equipment_id -> set of session_ids
        self._lock_queue: Dict[str, List[LockQueueEntry]] = {}  # equipment_id -> queue
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock_events: Dict[str, List[dict]] = {}  # equipment_id -> event history

    async def start_cleanup_task(self):
        """Start background task to clean up expired locks."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Lock cleanup task started")

    async def stop_cleanup_task(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Lock cleanup task stopped")

    async def _cleanup_loop(self):
        """Background task to periodically clean up expired locks."""
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                await self._cleanup_expired_locks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in lock cleanup loop: {e}")

    async def _cleanup_expired_locks(self):
        """Remove expired locks and process queue."""
        expired_equipment = []

        for equipment_id, lock in list(self._locks.items()):
            if lock.is_expired():
                logger.info(
                    f"Lock expired for equipment {equipment_id}, session {lock.session_id}"
                )
                expired_equipment.append(equipment_id)

                # Log event
                self._log_event(
                    equipment_id,
                    {
                        "event": "lock_expired",
                        "session_id": lock.session_id,
                        "lock_id": lock.lock_id,
                        "duration_seconds": (
                            datetime.now() - lock.acquired_at
                        ).total_seconds(),
                    },
                )

        # Release expired locks and process queue
        for equipment_id in expired_equipment:
            await self._release_lock_internal(equipment_id)
            await self._process_queue(equipment_id)

    def _log_event(self, equipment_id: str, event_data: dict):
        """Log a lock-related event."""
        if equipment_id not in self._lock_events:
            self._lock_events[equipment_id] = []

        event_data["timestamp"] = datetime.now().isoformat()
        self._lock_events[equipment_id].append(event_data)

        # Keep only last 100 events per equipment
        if len(self._lock_events[equipment_id]) > 100:
            self._lock_events[equipment_id] = self._lock_events[equipment_id][-100:]

    def get_lock_events(self, equipment_id: str, limit: int = 50) -> List[dict]:
        """Get lock event history for equipment."""
        events = self._lock_events.get(equipment_id, [])
        return events[-limit:]

    async def acquire_lock(
        self,
        equipment_id: str,
        session_id: str,
        lock_mode: LockMode = LockMode.EXCLUSIVE,
        timeout_seconds: int = 300,
        queue_if_busy: bool = False,
    ) -> dict:
        """
        Acquire a lock on equipment.

        Args:
            equipment_id: ID of equipment to lock
            session_id: ID of session requesting lock
            lock_mode: EXCLUSIVE or OBSERVER
            timeout_seconds: Auto-release timeout (0 = no timeout)
            queue_if_busy: If True, add to queue when equipment is locked

        Returns:
            Dict with lock status and details

        Raises:
            LockViolation: If equipment is locked and queue_if_busy=False
        """
        # Check if session already has this lock
        if equipment_id in self._locks:
            existing_lock = self._locks[equipment_id]
            if existing_lock.session_id == session_id:
                # Refresh the lock
                existing_lock.update_activity()
                existing_lock.timeout_seconds = timeout_seconds

                self._log_event(
                    equipment_id,
                    {
                        "event": "lock_refreshed",
                        "session_id": session_id,
                        "lock_id": existing_lock.lock_id,
                        "new_timeout": timeout_seconds,
                    },
                )

                return {
                    "success": True,
                    "status": "refreshed",
                    "lock": existing_lock.dict(),
                }

        # Handle observer mode
        if lock_mode == LockMode.OBSERVER:
            return await self._acquire_observer_lock(
                equipment_id, session_id, timeout_seconds
            )

        # Handle exclusive mode
        if equipment_id in self._locks:
            # Equipment is locked by someone else
            current_lock = self._locks[equipment_id]

            if queue_if_busy:
                # Add to queue
                queue_entry = await self._add_to_queue(
                    equipment_id, session_id, lock_mode
                )
                return {
                    "success": False,
                    "status": "queued",
                    "message": f"Equipment locked by session {current_lock.session_id}",
                    "current_lock": current_lock.dict(),
                    "queue_entry": queue_entry.dict(),
                }
            else:
                raise LockViolation(
                    f"Equipment {equipment_id} is locked by session {current_lock.session_id}",
                    equipment_id=equipment_id,
                    current_lock=current_lock,
                )

        # Check if there are observer locks
        if equipment_id in self._observer_locks and self._observer_locks[equipment_id]:
            # Clear observer locks when acquiring exclusive lock
            observer_count = len(self._observer_locks[equipment_id])
            self._observer_locks[equipment_id].clear()
            logger.info(
                f"Cleared {observer_count} observer locks for equipment {equipment_id}"
            )

        # Acquire lock
        lock = EquipmentLock(
            equipment_id=equipment_id,
            session_id=session_id,
            lock_mode=lock_mode,
            timeout_seconds=timeout_seconds,
        )

        self._locks[equipment_id] = lock

        self._log_event(
            equipment_id,
            {
                "event": "lock_acquired",
                "session_id": session_id,
                "lock_id": lock.lock_id,
                "lock_mode": lock_mode,
                "timeout_seconds": timeout_seconds,
            },
        )

        logger.info(
            f"Lock acquired: equipment={equipment_id}, session={session_id}, mode={lock_mode}"
        )

        return {"success": True, "status": "locked", "lock": lock.dict()}

    async def _acquire_observer_lock(
        self, equipment_id: str, session_id: str, timeout_seconds: int
    ) -> dict:
        """Acquire an observer (read-only) lock."""
        # Check if equipment has exclusive lock
        if equipment_id in self._locks:
            current_lock = self._locks[equipment_id]
            if current_lock.lock_mode == LockMode.EXCLUSIVE:
                raise LockViolation(
                    f"Equipment {equipment_id} has exclusive lock by session {current_lock.session_id}",
                    equipment_id=equipment_id,
                    current_lock=current_lock,
                )

        # Add to observer set
        if equipment_id not in self._observer_locks:
            self._observer_locks[equipment_id] = set()

        self._observer_locks[equipment_id].add(session_id)

        self._log_event(
            equipment_id,
            {
                "event": "observer_lock_acquired",
                "session_id": session_id,
                "timeout_seconds": timeout_seconds,
            },
        )

        logger.info(
            f"Observer lock acquired: equipment={equipment_id}, session={session_id}"
        )

        return {
            "success": True,
            "status": "observer",
            "observer_count": len(self._observer_locks[equipment_id]),
        }

    async def release_lock(
        self, equipment_id: str, session_id: str, force: bool = False
    ) -> dict:
        """
        Release a lock on equipment.

        Args:
            equipment_id: ID of equipment
            session_id: ID of session releasing lock
            force: If True, release regardless of session (admin only)

        Returns:
            Dict with release status
        """
        # Check exclusive lock
        if equipment_id in self._locks:
            lock = self._locks[equipment_id]

            if lock.session_id != session_id and not force:
                raise LockViolation(
                    f"Cannot release lock: owned by session {lock.session_id}",
                    equipment_id=equipment_id,
                    current_lock=lock,
                )

            await self._release_lock_internal(equipment_id)

            self._log_event(
                equipment_id,
                {
                    "event": "lock_released" if not force else "lock_force_released",
                    "session_id": session_id,
                    "lock_id": lock.lock_id,
                    "duration_seconds": (
                        datetime.now() - lock.acquired_at
                    ).total_seconds(),
                },
            )

            # Process queue
            await self._process_queue(equipment_id)

            return {"success": True, "status": "released", "was_forced": force}

        # Check observer lock
        if (
            equipment_id in self._observer_locks
            and session_id in self._observer_locks[equipment_id]
        ):
            self._observer_locks[equipment_id].remove(session_id)

            self._log_event(
                equipment_id,
                {"event": "observer_lock_released", "session_id": session_id},
            )

            return {"success": True, "status": "observer_released"}

        return {
            "success": False,
            "status": "not_locked",
            "message": f"No lock found for session {session_id}",
        }

    async def _release_lock_internal(self, equipment_id: str):
        """Internal lock release (no permission check)."""
        if equipment_id in self._locks:
            del self._locks[equipment_id]
            logger.info(f"Lock released for equipment {equipment_id}")

    async def _add_to_queue(
        self, equipment_id: str, session_id: str, lock_mode: LockMode
    ) -> LockQueueEntry:
        """Add session to lock queue."""
        if equipment_id not in self._lock_queue:
            self._lock_queue[equipment_id] = []

        # Check if already in queue
        for entry in self._lock_queue[equipment_id]:
            if entry.session_id == session_id:
                return entry  # Already queued

        position = len(self._lock_queue[equipment_id])
        entry = LockQueueEntry(
            equipment_id=equipment_id,
            session_id=session_id,
            lock_mode=lock_mode,
            position=position,
        )

        self._lock_queue[equipment_id].append(entry)

        self._log_event(
            equipment_id,
            {
                "event": "queued",
                "session_id": session_id,
                "queue_id": entry.queue_id,
                "position": position,
            },
        )

        logger.info(
            f"Session {session_id} added to queue for equipment {equipment_id} at position {position}"
        )

        return entry

    async def _process_queue(self, equipment_id: str):
        """Process lock queue after a lock is released."""
        if equipment_id not in self._lock_queue or not self._lock_queue[equipment_id]:
            return

        # Get next in queue
        next_entry = self._lock_queue[equipment_id][0]

        # Try to acquire lock for next session
        try:
            result = await self.acquire_lock(
                equipment_id=next_entry.equipment_id,
                session_id=next_entry.session_id,
                lock_mode=next_entry.lock_mode,
                timeout_seconds=300,  # Default timeout
            )

            # Remove from queue
            self._lock_queue[equipment_id].pop(0)

            # Update positions
            for i, entry in enumerate(self._lock_queue[equipment_id]):
                entry.position = i

            self._log_event(
                equipment_id,
                {
                    "event": "queue_processed",
                    "session_id": next_entry.session_id,
                    "queue_id": next_entry.queue_id,
                    "result": "lock_acquired",
                },
            )

            logger.info(
                f"Queue processed: lock granted to session {next_entry.session_id}"
            )

        except Exception as e:
            logger.error(f"Error processing queue for equipment {equipment_id}: {e}")

    def get_lock_status(self, equipment_id: str) -> dict:
        """Get current lock status for equipment."""
        # Check exclusive lock
        if equipment_id in self._locks:
            lock = self._locks[equipment_id]
            return {
                "locked": True,
                "lock_mode": lock.lock_mode,
                "session_id": lock.session_id,
                "lock_id": lock.lock_id,
                "acquired_at": lock.acquired_at.isoformat(),
                "time_remaining": lock.time_remaining(),
                "queue_length": len(self._lock_queue.get(equipment_id, [])),
            }

        # Check observer locks
        if equipment_id in self._observer_locks and self._observer_locks[equipment_id]:
            return {
                "locked": False,
                "observer_count": len(self._observer_locks[equipment_id]),
                "observer_sessions": list(self._observer_locks[equipment_id]),
                "queue_length": len(self._lock_queue.get(equipment_id, [])),
            }

        return {
            "locked": False,
            "queue_length": len(self._lock_queue.get(equipment_id, [])),
        }

    def get_queue_status(self, equipment_id: str) -> List[LockQueueEntry]:
        """Get lock queue for equipment."""
        return self._lock_queue.get(equipment_id, [])

    def get_session_locks(self, session_id: str) -> List[str]:
        """Get all equipment IDs locked by a session."""
        locked_equipment = []

        # Check exclusive locks
        for equipment_id, lock in self._locks.items():
            if lock.session_id == session_id:
                locked_equipment.append(equipment_id)

        # Check observer locks
        for equipment_id, observers in self._observer_locks.items():
            if session_id in observers:
                locked_equipment.append(equipment_id)

        return locked_equipment

    async def release_all_session_locks(self, session_id: str) -> int:
        """Release all locks held by a session."""
        released_count = 0

        # Release exclusive locks
        equipment_to_release = []
        for equipment_id, lock in list(self._locks.items()):
            if lock.session_id == session_id:
                equipment_to_release.append(equipment_id)

        for equipment_id in equipment_to_release:
            await self.release_lock(equipment_id, session_id, force=False)
            released_count += 1

        # Release observer locks
        for equipment_id, observers in list(self._observer_locks.items()):
            if session_id in observers:
                observers.remove(session_id)
                released_count += 1

        logger.info(f"Released {released_count} locks for session {session_id}")

        return released_count

    def update_lock_activity(self, equipment_id: str, session_id: str) -> bool:
        """Update lock activity timestamp to prevent timeout."""
        if equipment_id in self._locks:
            lock = self._locks[equipment_id]
            if lock.session_id == session_id:
                lock.update_activity()
                return True

        return False

    def can_control_equipment(self, equipment_id: str, session_id: str) -> bool:
        """Check if a session can control equipment (has exclusive lock)."""
        if equipment_id not in self._locks:
            return False  # No lock = no control

        lock = self._locks[equipment_id]
        return lock.session_id == session_id and lock.lock_mode == LockMode.EXCLUSIVE

    def can_observe_equipment(self, equipment_id: str, session_id: str) -> bool:
        """Check if a session can observe equipment data."""
        # Can observe if session has exclusive lock
        if equipment_id in self._locks:
            lock = self._locks[equipment_id]
            if lock.session_id == session_id:
                return True

        # Can observe if session has observer lock
        if equipment_id in self._observer_locks:
            if session_id in self._observer_locks[equipment_id]:
                return True

        return False

    def get_all_locks(self) -> dict:
        """Get all current locks."""
        return {
            "exclusive_locks": {
                eq_id: lock.dict() for eq_id, lock in self._locks.items()
            },
            "observer_locks": {
                eq_id: list(sessions)
                for eq_id, sessions in self._observer_locks.items()
            },
            "queues": {
                eq_id: [entry.dict() for entry in queue]
                for eq_id, queue in self._lock_queue.items()
            },
        }


# Global lock manager instance
lock_manager = LockManager()
