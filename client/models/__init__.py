"""Data models for LabLink GUI client."""

from .acquisition import (AcquisitionConfig,  # Enums; Data classes
                          AcquisitionMode, AcquisitionSession,
                          AcquisitionState, CrossingInfo, DataPoint,
                          DataQuality, ExportFormat, FFTResult, PeakInfo,
                          QualityMetrics, RollingStatistics, SyncConfig,
                          SyncGroup, SyncState, TrendAnalysis, TrendType,
                          TriggerConfig, TriggerEdge, TriggerType)
from .equipment import (ConnectionStatus, Equipment, EquipmentCommand,
                        EquipmentType)

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
