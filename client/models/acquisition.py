"""Data acquisition models for GUI client."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import uuid4


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


class TrendType(str, Enum):
    """Trend types."""
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    NOISY = "noisy"


class DataQuality(str, Enum):
    """Data quality grades."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class SyncState(str, Enum):
    """Synchronization group states."""
    IDLE = "idle"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class TriggerConfig:
    """Trigger configuration."""
    trigger_type: TriggerType = TriggerType.IMMEDIATE
    level: Optional[float] = None  # For level/edge triggers
    edge: Optional[TriggerEdge] = None  # For edge triggers
    channel: Optional[str] = None  # Which channel to monitor
    pre_trigger_samples: int = 0  # Samples before trigger

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls."""
        return {
            "trigger_type": self.trigger_type.value if isinstance(self.trigger_type, Enum) else self.trigger_type,
            "level": self.level,
            "edge": self.edge.value if isinstance(self.edge, Enum) and self.edge else None,
            "channel": self.channel,
            "pre_trigger_samples": self.pre_trigger_samples
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TriggerConfig':
        """Create TriggerConfig from dictionary."""
        return cls(
            trigger_type=TriggerType(data.get("trigger_type", "immediate")),
            level=data.get("level"),
            edge=TriggerEdge(data["edge"]) if data.get("edge") else None,
            channel=data.get("channel"),
            pre_trigger_samples=data.get("pre_trigger_samples", 0)
        )


@dataclass
class AcquisitionConfig:
    """Configuration for data acquisition."""

    # Basic settings
    equipment_id: str
    name: Optional[str] = None
    description: Optional[str] = None

    # Acquisition mode
    mode: AcquisitionMode = AcquisitionMode.CONTINUOUS
    sample_rate: float = 1.0  # Samples per second
    num_samples: Optional[int] = None  # For single-shot mode
    duration_seconds: Optional[float] = None  # Max duration

    # Channels
    channels: List[str] = field(default_factory=lambda: ["CH1"])

    # Trigger settings
    trigger_config: TriggerConfig = field(default_factory=TriggerConfig)

    # Buffer settings
    buffer_size: int = 10000  # Circular buffer size

    # Export settings
    auto_export: bool = False  # Auto-export when done
    export_format: ExportFormat = ExportFormat.CSV
    export_path: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls."""
        result = {
            "equipment_id": self.equipment_id,
            "mode": self.mode.value if isinstance(self.mode, Enum) else self.mode,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "buffer_size": self.buffer_size,
            "auto_export": self.auto_export,
            "export_format": self.export_format.value if isinstance(self.export_format, Enum) else self.export_format,
        }

        if self.name:
            result["name"] = self.name
        if self.description:
            result["description"] = self.description
        if self.num_samples is not None:
            result["num_samples"] = self.num_samples
        if self.duration_seconds is not None:
            result["duration_seconds"] = self.duration_seconds
        if self.export_path:
            result["export_path"] = self.export_path
        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AcquisitionConfig':
        """Create AcquisitionConfig from dictionary."""
        trigger_data = data.get("trigger_config", {})
        trigger_config = TriggerConfig.from_dict(trigger_data) if trigger_data else TriggerConfig()

        return cls(
            equipment_id=data["equipment_id"],
            name=data.get("name"),
            description=data.get("description"),
            mode=AcquisitionMode(data.get("mode", "continuous")),
            sample_rate=data.get("sample_rate", 1.0),
            num_samples=data.get("num_samples"),
            duration_seconds=data.get("duration_seconds"),
            channels=data.get("channels", ["CH1"]),
            trigger_config=trigger_config,
            buffer_size=data.get("buffer_size", 10000),
            auto_export=data.get("auto_export", False),
            export_format=ExportFormat(data.get("export_format", "csv")),
            export_path=data.get("export_path"),
            metadata=data.get("metadata", {})
        )


@dataclass
class DataPoint:
    """Single data point with timestamp."""
    timestamp: datetime
    channel: str
    value: float
    unit: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DataPoint':
        """Create DataPoint from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        elif not isinstance(timestamp, datetime):
            timestamp = datetime.now()

        return cls(
            timestamp=timestamp,
            channel=data["channel"],
            value=float(data["value"]),
            unit=data.get("unit")
        )


@dataclass
class AcquisitionSession:
    """Acquisition session status and info."""
    acquisition_id: str
    equipment_id: str
    state: AcquisitionState
    config: AcquisitionConfig
    created_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    sample_count: int = 0
    error_message: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AcquisitionSession':
        """Create AcquisitionSession from API response."""
        config_data = data.get("config", {})
        config = AcquisitionConfig.from_dict(config_data) if config_data else None

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        elif not isinstance(created_at, datetime):
            created_at = datetime.now()

        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))

        stopped_at = data.get("stopped_at")
        if isinstance(stopped_at, str):
            stopped_at = datetime.fromisoformat(stopped_at.replace('Z', '+00:00'))

        return cls(
            acquisition_id=data["acquisition_id"],
            equipment_id=data.get("equipment_id", ""),
            state=AcquisitionState(data.get("state", "idle")),
            config=config,
            created_at=created_at,
            started_at=started_at,
            stopped_at=stopped_at,
            sample_count=data.get("sample_count", 0),
            error_message=data.get("error_message")
        )


@dataclass
class RollingStatistics:
    """Rolling statistics for acquisition data."""
    channel: str
    window_size: int
    mean: float
    std_dev: float
    min_val: float
    max_val: float
    rms: float
    peak_to_peak: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RollingStatistics':
        """Create RollingStatistics from API response."""
        return cls(
            channel=data["channel"],
            window_size=data["window_size"],
            mean=data["mean"],
            std_dev=data["std_dev"],
            min_val=data["min"],
            max_val=data["max"],
            rms=data["rms"],
            peak_to_peak=data["peak_to_peak"]
        )


@dataclass
class FFTResult:
    """FFT analysis result."""
    channel: str
    frequencies: List[float]
    magnitudes: List[float]
    fundamental_freq: float
    thd: float  # Total Harmonic Distortion
    snr: float  # Signal-to-Noise Ratio

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FFTResult':
        """Create FFTResult from API response."""
        return cls(
            channel=data["channel"],
            frequencies=data["frequencies"],
            magnitudes=data["magnitudes"],
            fundamental_freq=data["fundamental_frequency"],
            thd=data["thd"],
            snr=data["snr"]
        )


@dataclass
class TrendAnalysis:
    """Trend analysis result."""
    channel: str
    trend: TrendType
    slope: float
    confidence: float  # 0-1

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrendAnalysis':
        """Create TrendAnalysis from API response."""
        return cls(
            channel=data["channel"],
            trend=TrendType(data["trend"]),
            slope=data["slope"],
            confidence=data["confidence"]
        )


@dataclass
class QualityMetrics:
    """Data quality assessment."""
    channel: str
    noise_level: float
    stability_score: float  # 0-1
    outlier_ratio: float  # 0-1
    quality_grade: DataQuality

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QualityMetrics':
        """Create QualityMetrics from API response."""
        return cls(
            channel=data["channel"],
            noise_level=data["noise_level"],
            stability_score=data["stability_score"],
            outlier_ratio=data["outlier_ratio"],
            quality_grade=DataQuality(data["quality_grade"])
        )


@dataclass
class PeakInfo:
    """Peak detection result."""
    channel: str
    peak_count: int
    peak_indices: List[int]
    peak_values: List[float]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PeakInfo':
        """Create PeakInfo from API response."""
        return cls(
            channel=data["channel"],
            peak_count=data["peak_count"],
            peak_indices=data["peak_indices"],
            peak_values=data["peak_values"]
        )


@dataclass
class CrossingInfo:
    """Threshold crossing detection result."""
    channel: str
    threshold: float
    crossing_count: int
    crossing_indices: List[int]
    crossing_values: List[float]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CrossingInfo':
        """Create CrossingInfo from API response."""
        return cls(
            channel=data["channel"],
            threshold=data["threshold"],
            crossing_count=data["crossing_count"],
            crossing_indices=data["crossing_indices"],
            crossing_values=data["crossing_values"]
        )


@dataclass
class SyncConfig:
    """Synchronization group configuration."""
    group_id: str
    equipment_ids: List[str]
    master_equipment_id: Optional[str] = None
    sync_tolerance_ms: float = 10.0
    wait_for_all: bool = True
    auto_align_timestamps: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls."""
        return {
            "group_id": self.group_id,
            "equipment_ids": self.equipment_ids,
            "master_equipment_id": self.master_equipment_id,
            "sync_tolerance_ms": self.sync_tolerance_ms,
            "wait_for_all": self.wait_for_all,
            "auto_align_timestamps": self.auto_align_timestamps
        }


@dataclass
class SyncGroup:
    """Synchronization group status."""
    group_id: str
    state: SyncState
    equipment_ids: List[str]
    acquisition_ids: Dict[str, str]  # equipment_id -> acquisition_id
    master_equipment_id: Optional[str] = None
    ready_count: int = 0
    start_time: Optional[datetime] = None
    errors: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncGroup':
        """Create SyncGroup from API response."""
        start_time = data.get("start_time")
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))

        return cls(
            group_id=data["group_id"],
            state=SyncState(data.get("state", "idle")),
            equipment_ids=data.get("equipment_ids", []),
            acquisition_ids=data.get("acquisition_ids", {}),
            master_equipment_id=data.get("master_equipment_id"),
            ready_count=data.get("ready_count", 0),
            start_time=start_time,
            errors=data.get("errors", {})
        )
