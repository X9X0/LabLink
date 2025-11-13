"""Database models for LabLink centralized storage."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class CommandStatus(str, Enum):
    """Command execution status."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"


class SessionStatus(str, Enum):
    """Data acquisition session status."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class DatabaseConfig:
    """Database configuration."""

    db_path: str = "data/lablink.db"
    enable_command_logging: bool = True
    enable_measurement_archival: bool = True
    enable_usage_tracking: bool = True
    retention_days: int = 90  # Keep data for 90 days
    auto_cleanup: bool = True  # Automatic cleanup of old records
    max_db_size_mb: int = 1000  # Maximum database size in MB


@dataclass
class CommandRecord:
    """Record of a command sent to equipment.

    Tracks all SCPI commands sent to equipment for audit trail and debugging.
    """

    record_id: Optional[int] = None  # Auto-generated primary key
    timestamp: datetime = field(default_factory=datetime.now)
    equipment_id: str = ""
    equipment_type: str = ""
    command: str = ""
    response: Optional[str] = None
    status: CommandStatus = CommandStatus.SUCCESS
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    user_id: Optional[str] = None
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "command": self.command,
            "response": self.response,
            "status": self.status.value,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
            "user_id": self.user_id,
            "session_id": self.session_id,
        }


@dataclass
class MeasurementRecord:
    """Record of a measurement taken from equipment.

    Archives all measurements for historical analysis and trending.
    """

    record_id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
    equipment_id: str = ""
    equipment_type: str = ""
    measurement_type: str = ""  # voltage, current, power, temperature, etc.
    channel: Optional[int] = None
    value: float = 0.0
    unit: str = ""
    quality: Optional[str] = None  # good, questionable, bad
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "measurement_type": self.measurement_type,
            "channel": self.channel,
            "value": self.value,
            "unit": self.unit,
            "quality": self.quality,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "user_id": self.user_id,
        }


@dataclass
class EquipmentUsageRecord:
    """Record of equipment usage statistics.

    Tracks connection time, command counts, and usage patterns.
    """

    record_id: Optional[int] = None
    equipment_id: str = ""
    equipment_type: str = ""
    session_start: datetime = field(default_factory=datetime.now)
    session_end: Optional[datetime] = None
    duration_seconds: float = 0.0
    command_count: int = 0
    measurement_count: int = 0
    error_count: int = 0
    user_id: Optional[str] = None
    disconnect_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "session_start": self.session_start.isoformat(),
            "session_end": self.session_end.isoformat() if self.session_end else None,
            "duration_seconds": self.duration_seconds,
            "command_count": self.command_count,
            "measurement_count": self.measurement_count,
            "error_count": self.error_count,
            "user_id": self.user_id,
            "disconnect_reason": self.disconnect_reason,
        }


@dataclass
class DataSessionRecord:
    """Record of a data acquisition session.

    Tracks data acquisition sessions with metadata and statistics.
    """

    session_id: str = ""
    equipment_ids: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    status: SessionStatus = SessionStatus.ACTIVE
    mode: str = ""  # continuous, single_shot, triggered
    sample_count: int = 0
    export_format: Optional[str] = None
    export_path: Optional[str] = None
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    statistics: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "equipment_ids": self.equipment_ids,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "status": self.status.value,
            "mode": self.mode,
            "sample_count": self.sample_count,
            "export_format": self.export_format,
            "export_path": self.export_path,
            "trigger_config": self.trigger_config,
            "statistics": self.statistics,
            "user_id": self.user_id,
            "error_message": self.error_message,
        }


@dataclass
class QueryResult:
    """Result of a database query."""

    records: List[Dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 100
    has_more: bool = False
    query_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "records": self.records,
            "total_count": self.total_count,
            "page": self.page,
            "page_size": self.page_size,
            "has_more": self.has_more,
            "query_time_ms": self.query_time_ms,
        }
