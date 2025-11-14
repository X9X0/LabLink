"""Session management for tracking client connections.

Tracks active sessions, their equipment locks, and provides session lifecycle management.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SessionInfo(BaseModel):
    """Information about a client session."""

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    client_name: Optional[str] = None
    client_ip: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    timeout_seconds: int = Field(default=600, ge=0)  # 10 minutes default
    metadata: dict = Field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if session has expired due to inactivity."""
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

    def session_duration(self) -> float:
        """Get total session duration in seconds."""
        return (datetime.now() - self.created_at).total_seconds()


class SessionManager:
    """Manages client sessions."""

    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}
        self._session_events: Dict[str, List[dict]] = {}

    def _log_event(self, session_id: str, event_data: dict):
        """Log a session-related event."""
        if session_id not in self._session_events:
            self._session_events[session_id] = []

        event_data["timestamp"] = datetime.now().isoformat()
        self._session_events[session_id].append(event_data)

        # Keep only last 100 events per session
        if len(self._session_events[session_id]) > 100:
            self._session_events[session_id] = self._session_events[session_id][-100:]

    def create_session(
        self,
        client_name: Optional[str] = None,
        client_ip: Optional[str] = None,
        timeout_seconds: int = 600,
        metadata: Optional[dict] = None,
    ) -> SessionInfo:
        """
        Create a new session.

        Args:
            client_name: Optional client identifier
            client_ip: Client IP address
            timeout_seconds: Session timeout (0 = no timeout)
            metadata: Additional session metadata

        Returns:
            SessionInfo object
        """
        session = SessionInfo(
            client_name=client_name,
            client_ip=client_ip,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {},
        )

        self._sessions[session.session_id] = session

        self._log_event(
            session.session_id,
            {
                "event": "session_created",
                "client_name": client_name,
                "client_ip": client_ip,
            },
        )

        logger.info(
            f"Session created: {session.session_id} (client={client_name}, ip={client_ip})"
        )

        return session

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get session by ID."""
        return self._sessions.get(session_id)

    def update_session_activity(self, session_id: str) -> bool:
        """Update session activity timestamp."""
        if session_id in self._sessions:
            self._sessions[session_id].update_activity()
            return True
        return False

    def end_session(self, session_id: str) -> bool:
        """
        End a session.

        Args:
            session_id: Session to end

        Returns:
            True if session was ended, False if not found
        """
        if session_id not in self._sessions:
            return False

        session = self._sessions[session_id]
        duration = session.session_duration()

        self._log_event(
            session_id, {"event": "session_ended", "duration_seconds": duration}
        )

        del self._sessions[session_id]

        logger.info(f"Session ended: {session_id} (duration={duration:.1f}s)")

        return True

    def cleanup_expired_sessions(self) -> List[str]:
        """
        Remove expired sessions.

        Returns:
            List of expired session IDs
        """
        expired_sessions = []

        for session_id, session in list(self._sessions.items()):
            if session.is_expired():
                expired_sessions.append(session_id)

                self._log_event(
                    session_id,
                    {
                        "event": "session_expired",
                        "duration_seconds": session.session_duration(),
                    },
                )

                del self._sessions[session_id]

                logger.info(f"Session expired: {session_id}")

        return expired_sessions

    def get_all_sessions(self) -> List[SessionInfo]:
        """Get all active sessions."""
        return list(self._sessions.values())

    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)

    def get_session_events(self, session_id: str, limit: int = 50) -> List[dict]:
        """Get event history for a session."""
        events = self._session_events.get(session_id, [])
        return events[-limit:]

    def update_session_metadata(self, session_id: str, metadata: dict) -> bool:
        """Update session metadata."""
        if session_id in self._sessions:
            self._sessions[session_id].metadata.update(metadata)

            self._log_event(
                session_id,
                {"event": "metadata_updated", "metadata_keys": list(metadata.keys())},
            )

            return True
        return False

    def get_sessions_by_client(self, client_name: str) -> List[SessionInfo]:
        """Get all sessions for a specific client."""
        return [
            session
            for session in self._sessions.values()
            if session.client_name == client_name
        ]

    def get_sessions_by_ip(self, client_ip: str) -> List[SessionInfo]:
        """Get all sessions from a specific IP address."""
        return [
            session
            for session in self._sessions.values()
            if session.client_ip == client_ip
        ]


# Global session manager instance
session_manager = SessionManager()
