"""Equipment drivers for LabLink."""

from .base import BaseEquipment
from .bk_power_supply import (BK1685B, BK1687B, BK1688B, BK1696, BK1901B,
                              BK1902B, BK9103, BK9104, BK9130B, BK9205B,
                              BK9206B)
from .bk_registry import (MODELS, BKModel, catalog, is_bk_manufacturer,
                          is_drivable, resolve_idn, resolve_model, usb_mode)
from .bk_scpi import (BKSCPIElectronicLoad, BKSCPIMultimeter,
                      BKSCPIPowerSupply)
from .manager import equipment_manager
from .mock.mock_electronic_load import MockElectronicLoad
from .mock.mock_oscilloscope import MockOscilloscope
from .mock.mock_power_supply import MockPowerSupply
from .rigol_electronic_load import RigolDL3021A
from .rigol_scope import RigolDS1102D, RigolDS1104, RigolMSO2072A

__all__ = [
    "BaseEquipment",
    "equipment_manager",
    "RigolMSO2072A",
    "RigolDS1104",
    "RigolDS1102D",
    "RigolDL3021A",
    # B&K model-specific drivers
    "BK9206B",
    "BK9205B",
    "BK9130B",
    "BK1685B",
    "BK1687B",
    "BK1688B",
    "BK1696",
    "BK1901B",
    "BK1902B",
    "BK9103",
    "BK9104",
    # B&K generic SCPI drivers, selected from the registry
    "BKSCPIPowerSupply",
    "BKSCPIElectronicLoad",
    "BKSCPIMultimeter",
    # B&K model registry
    "MODELS",
    "BKModel",
    "catalog",
    "resolve_model",
    "resolve_idn",
    "is_bk_manufacturer",
    "is_drivable",
    "usb_mode",
    "MockOscilloscope",
    "MockPowerSupply",
    "MockElectronicLoad",
]
