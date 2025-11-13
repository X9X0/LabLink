"""Alarm system data models."""

from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class AlarmSeverity(str, Enum):
    """Alarm severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlarmState(str, Enum):
    """Alarm states."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    CLEARED = "cleared"
    SUPPRESSED = "suppressed"


class AlarmType(str, Enum):
    """Types of alarms."""
    THRESHOLD = "threshold"           # Value crosses threshold
    DEVIATION = "deviation"           # Value deviates from setpoint
    RATE_OF_CHANGE = "rate_of_change" # Value changes too quickly
    EQUIPMENT_ERROR = "equipment_error" # Equipment malfunction
    COMMUNICATION = "communication"   # Communication failure
    SAFETY = "safety"                 # Safety limit violation
    SYSTEM = "system"                 # System-level issue
    CUSTOM = "custom"                 # User-defined alarm


class AlarmCondition(str, Enum):
    """Alarm trigger conditions."""
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    EQUAL_TO = "equal_to"
    NOT_EQUAL_TO = "not_equal_to"
    IN_RANGE = "in_range"
    OUT_OF_RANGE = "out_of_range"
    RISING_EDGE = "rising_edge"
    FALLING_EDGE = "falling_edge"


class AlarmConfig(BaseModel):
    """Configuration for an alarm."""
    alarm_id: str = Field(default_factory=lambda: f"alarm_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Alarm name")
    description: Optional[str] = Field(None, description="Alarm description")

    # Source
    equipment_id: Optional[str] = Field(None, description="Equipment ID to monitor")
    parameter: str = Field(..., description="Parameter to monitor (e.g., 'voltage', 'temperature')")

    # Alarm type and condition
    alarm_type: AlarmType = Field(default=AlarmType.THRESHOLD)
    condition: AlarmCondition = Field(default=AlarmCondition.GREATER_THAN)
    severity: AlarmSeverity = Field(default=AlarmSeverity.WARNING)

    # Threshold values
    threshold: Optional[float] = Field(None, description="Threshold value")
    threshold_high: Optional[float] = Field(None, description="High threshold (for range)")
    threshold_low: Optional[float] = Field(None, description="Low threshold (for range)")
    deadband: Optional[float] = Field(None, description="Deadband to prevent flapping")

    # Timing
    delay_seconds: float = Field(default=0.0, description="Delay before triggering alarm")
    auto_clear: bool = Field(default=True, description="Automatically clear when condition resolves")

    # Actions
    enabled: bool = Field(default=True, description="Whether alarm is enabled")
    notifications: List[str] = Field(default_factory=list, description="Notification methods (email, sms, websocket)")
    escalation_enabled: bool = Field(default=False, description="Enable escalation")
    escalation_delay_minutes: Optional[int] = Field(None, description="Minutes before escalation")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: Optional[str] = Field(None, description="User who created alarm")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")


class AlarmEvent(BaseModel):
    """An alarm event occurrence."""
    event_id: str = Field(default_factory=lambda: f"event_{uuid.uuid4().hex[:8]}")
    alarm_id: str = Field(..., description="Associated alarm configuration ID")

    # Event details
    state: AlarmState = Field(default=AlarmState.ACTIVE)
    severity: AlarmSeverity = Field(..., description="Alarm severity")
    message: str = Field(..., description="Alarm message")

    # Source information
    equipment_id: Optional[str] = Field(None, description="Equipment that triggered alarm")
    parameter: str = Field(..., description="Parameter that triggered alarm")
    value: Optional[float] = Field(None, description="Current value")
    threshold: Optional[float] = Field(None, description="Threshold value")

    # Timing
    triggered_at: datetime = Field(default_factory=datetime.now)
    acknowledged_at: Optional[datetime] = Field(None)
    cleared_at: Optional[datetime] = Field(None)

    # User actions
    acknowledged_by: Optional[str] = Field(None, description="User who acknowledged")
    acknowledgment_note: Optional[str] = Field(None, description="Acknowledgment notes")

    # Escalation
    escalated: bool = Field(default=False)
    escalated_at: Optional[datetime] = Field(None)

    # Notification tracking
    notifications_sent: List[str] = Field(default_factory=list)
    notification_count: int = Field(default=0)

    # Metadata
    additional_data: Dict[str, Any] = Field(default_factory=dict)


class AlarmAcknowledgment(BaseModel):
    """Alarm acknowledgment data."""
    event_id: str = Field(..., description="Event ID to acknowledge")
    acknowledged_by: str = Field(..., description="User acknowledging alarm")
    note: Optional[str] = Field(None, description="Acknowledgment notes")
    timestamp: datetime = Field(default_factory=datetime.now)


class AlarmStatistics(BaseModel):
    """Alarm system statistics."""
    total_active: int = Field(default=0)
    total_acknowledged: int = Field(default=0)
    total_cleared: int = Field(default=0)
    by_severity: Dict[str, int] = Field(default_factory=dict)
    by_equipment: Dict[str, int] = Field(default_factory=dict)
    most_frequent: List[Dict[str, Any]] = Field(default_factory=list)


class NotificationConfig(BaseModel):
    """Configuration for alarm notifications."""
    # Email settings
    email_enabled: bool = Field(default=False)
    smtp_server: Optional[str] = Field(None)
    smtp_port: int = Field(default=587)
    smtp_username: Optional[str] = Field(None)
    smtp_password: Optional[str] = Field(None)
    smtp_use_tls: bool = Field(default=True)
    email_from: Optional[str] = Field(None)
    email_recipients: List[str] = Field(default_factory=list)

    # SMS settings (via Twilio, etc.)
    sms_enabled: bool = Field(default=False)
    sms_provider: Optional[str] = Field(None, description="Provider (twilio, etc.)")
    sms_api_key: Optional[str] = Field(None)
    sms_api_secret: Optional[str] = Field(None)
    sms_from_number: Optional[str] = Field(None)
    sms_recipients: List[str] = Field(default_factory=list)

    # WebSocket settings
    websocket_enabled: bool = Field(default=True)

    # Slack settings
    slack_enabled: bool = Field(default=False)
    slack_webhook_url: Optional[str] = Field(None, description="Slack incoming webhook URL")

    # Generic webhook settings
    webhook_enabled: bool = Field(default=False)
    webhook_url: Optional[str] = Field(None, description="Webhook endpoint URL")
    webhook_auth_token: Optional[str] = Field(None, description="Optional Bearer token for webhook authentication")

    # Notification throttling
    throttle_minutes: int = Field(default=5, description="Minimum minutes between notifications for same alarm")
    max_notifications_per_hour: int = Field(default=10)
