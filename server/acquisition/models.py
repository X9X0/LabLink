"""Data acquisition models and data structures."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
import numpy as np


class AcquisitionMode(str, Enum):
    """Data acquisition modes."""
    CONTINUOUS = "continuous"  # Acquire continuously until stopped
    SINGLE_SHOT = "single_shot"  # Acquire N samples then stop
    TRIGGERED = "triggered"  # Wait for trigger, then acquire


class AcquisitionState(str, Enum):
    """Acquisition session states."""
    IDLE = "idle"
    WAITING_TRIGGER = "waiting_trigger"
    ACQUIRING = "acquiring"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class TriggerType(str, Enum):
    """Trigger types for acquisition."""
    IMMEDIATE = "immediate"  # Start immediately
    LEVEL = "level"  # Trigger when value crosses threshold
    EDGE = "edge"  # Trigger on rising/falling edge
    TIME = "time"  # Trigger at specific time
    EXTERNAL = "external"  # External trigger signal


class TriggerEdge(str, Enum):
    """Trigger edge types."""
    RISING = "rising"
    FALLING = "falling"
    EITHER = "either"


class ExportFormat(str, Enum):
    """Data export formats."""
    CSV = "csv"
    HDF5 = "hdf5"
    NUMPY = "npy"
    JSON = "json"


class TriggerConfig(BaseModel):
    """Trigger configuration."""
    trigger_type: TriggerType = TriggerType.IMMEDIATE
    level: Optional[float] = None  # For level/edge triggers
    edge: Optional[TriggerEdge] = None  # For edge triggers
    channel: Optional[str] = None  # Which channel to monitor
    pre_trigger_samples: int = Field(default=0, ge=0)  # Samples before trigger


class AcquisitionConfig(BaseModel):
    """Configuration for data acquisition."""

    # Basic settings
    acquisition_id: str = Field(default_factory=lambda: str(uuid4()))
    equipment_id: str
    name: Optional[str] = None
    description: Optional[str] = None

    # Acquisition mode
    mode: AcquisitionMode = AcquisitionMode.CONTINUOUS
    sample_rate: float = Field(default=1.0, gt=0, description="Samples per second")
    num_samples: Optional[int] = Field(None, ge=1, description="For single-shot mode")
    duration_seconds: Optional[float] = Field(None, gt=0, description="Max duration")

    # Channels
    channels: List[str] = Field(default_factory=lambda: ["CH1"], description="Channels to acquire")

    # Trigger settings
    trigger_config: TriggerConfig = Field(default_factory=TriggerConfig)

    # Buffer settings
    buffer_size: int = Field(default=10000, ge=100, description="Circular buffer size")

    # Export settings
    auto_export: bool = Field(default=False, description="Auto-export when done")
    export_format: ExportFormat = Field(default=ExportFormat.CSV)
    export_path: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DataPoint(BaseModel):
    """Single data point with timestamp."""
    timestamp: datetime = Field(default_factory=datetime.now)
    channel: str
    value: float
    unit: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AcquisitionStats(BaseModel):
    """Statistics for acquisition session."""
    total_samples: int = 0
    samples_per_channel: Dict[str, int] = Field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    actual_sample_rate: Optional[float] = None
    buffer_overruns: int = 0
    min_values: Dict[str, float] = Field(default_factory=dict)
    max_values: Dict[str, float] = Field(default_factory=dict)
    mean_values: Dict[str, float] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AcquisitionSession(BaseModel):
    """Active acquisition session information."""
    acquisition_id: str
    equipment_id: str
    state: AcquisitionState = AcquisitionState.IDLE
    config: AcquisitionConfig
    stats: AcquisitionStats = Field(default_factory=AcquisitionStats)
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CircularBuffer:
    """Circular buffer for efficient data storage."""

    def __init__(self, size: int, num_channels: int = 1):
        """
        Initialize circular buffer.

        Args:
            size: Maximum number of samples per channel
            num_channels: Number of data channels
        """
        self.size = size
        self.num_channels = num_channels
        self.data = np.zeros((num_channels, size), dtype=np.float64)
        self.timestamps = np.zeros(size, dtype=np.float64)  # Unix timestamps
        self.write_index = 0
        self.count = 0
        self.overruns = 0
        self.start_time = datetime.now()

    def add(self, values: List[float], timestamp: Optional[float] = None):
        """
        Add a sample to the buffer.

        Args:
            values: List of values (one per channel)
            timestamp: Unix timestamp (or use current time)
        """
        if len(values) != self.num_channels:
            raise ValueError(f"Expected {self.num_channels} values, got {len(values)}")

        idx = self.write_index % self.size

        # Check for buffer overrun
        if self.count >= self.size:
            self.overruns += 1

        # Store data
        self.data[:, idx] = values
        self.timestamps[idx] = timestamp if timestamp else datetime.now().timestamp()

        self.write_index += 1
        self.count = min(self.count + 1, self.size)

    def get_latest(self, n: Optional[int] = None) -> tuple:
        """
        Get latest N samples.

        Args:
            n: Number of samples (None = all available)

        Returns:
            (data, timestamps) tuple
        """
        if n is None:
            n = self.count
        else:
            n = min(n, self.count)

        if n == 0:
            return np.array([]), np.array([])

        # Get indices of latest n samples
        if self.count < self.size:
            # Buffer not full yet
            indices = np.arange(max(0, self.write_index - n), self.write_index)
        else:
            # Buffer has wrapped around
            end_idx = self.write_index % self.size
            start_idx = (end_idx - n) % self.size

            if start_idx < end_idx:
                indices = np.arange(start_idx, end_idx)
            else:
                # Wrapped around
                indices = np.concatenate([
                    np.arange(start_idx, self.size),
                    np.arange(0, end_idx)
                ])

        return self.data[:, indices], self.timestamps[indices]

    def get_all(self) -> tuple:
        """Get all available data."""
        return self.get_latest(self.count)

    def clear(self):
        """Clear the buffer."""
        self.data.fill(0)
        self.timestamps.fill(0)
        self.write_index = 0
        self.count = 0
        self.overruns = 0
        self.start_time = datetime.now()

    def get_stats(self) -> Dict[str, Any]:
        """Get buffer statistics."""
        if self.count == 0:
            return {
                "size": self.size,
                "count": 0,
                "overruns": self.overruns,
                "utilization": 0.0
            }

        data, _ = self.get_all()

        return {
            "size": self.size,
            "count": self.count,
            "overruns": self.overruns,
            "utilization": self.count / self.size,
            "min": data.min(axis=1).tolist(),
            "max": data.max(axis=1).tolist(),
            "mean": data.mean(axis=1).tolist(),
            "std": data.std(axis=1).tolist()
        }
