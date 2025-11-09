"""Data models for LabLink GUI client."""

from .equipment import (
    Equipment,
    EquipmentType,
    ConnectionStatus,
    EquipmentCommand,
)

from .acquisition import (
    # Enums
    AcquisitionMode,
    AcquisitionState,
    TriggerType,
    TriggerEdge,
    ExportFormat,
    TrendType,
    DataQuality,
    SyncState,
    # Data classes
    TriggerConfig,
    AcquisitionConfig,
    DataPoint,
    AcquisitionSession,
    RollingStatistics,
    FFTResult,
    TrendAnalysis,
    QualityMetrics,
    PeakInfo,
    CrossingInfo,
    SyncConfig,
    SyncGroup,
)

__all__ = [
    # Equipment models
    "Equipment",
    "EquipmentType",
    "ConnectionStatus",
    "EquipmentCommand",
    # Acquisition enums
    "AcquisitionMode",
    "AcquisitionState",
    "TriggerType",
    "TriggerEdge",
    "ExportFormat",
    "TrendType",
    "DataQuality",
    "SyncState",
    # Acquisition models
    "TriggerConfig",
    "AcquisitionConfig",
    "DataPoint",
    "AcquisitionSession",
    "RollingStatistics",
    "FFTResult",
    "TrendAnalysis",
    "QualityMetrics",
    "PeakInfo",
    "CrossingInfo",
    "SyncConfig",
    "SyncGroup",
]
