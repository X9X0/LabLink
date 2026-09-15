"""Equipment drivers for LabLink."""

from .base import BaseEquipment
from .bk_power_supply import BK1685B, BK1902B, BK9130B, BK9205B, BK9206B
from .manager import equipment_manager
from .mock.mock_electronic_load import MockElectronicLoad
from .mock.mock_daq import MockDAQ
from .mock.mock_function_generator import MockFunctionGenerator
from .mock.mock_multimeter import MockMultimeter
from .mock.mock_rf_generator import MockRFGenerator
from .mock.mock_spectrum_analyzer import MockSpectrumAnalyzer
from .mock.mock_vna import MockVNA
from .rigol_daq import RigolM300
from .mock.mock_oscilloscope import MockOscilloscope
from .mock.mock_power_supply import MockPowerSupply
from .rigol_electronic_load import RigolDL3000Base, RigolDL3021A, RigolDL3031A
from .rigol_modern_scope import (RigolDHO800, RigolDHO1000, RigolDHO5000,
                                 RigolDS1000ZE, RigolDS4000, RigolDS6000,
                                 RigolDS8000R, RigolDS70000, RigolDS80000,
                                 RigolMHO900, RigolModernScopeBase, RigolMSO5000,
                                 RigolMSO7000, RigolMSO8000)
from .rigol_multimeter import (RigolDM3058, RigolDM3058E, RigolDM3068,
                               RigolDMMBase)
from .rigol_function_generator import (RigolDG800, RigolDG800Pro, RigolDG900,
                                       RigolDG1000Z, RigolDG2000, RigolDG4000,
                                       RigolDG5000, RigolDG5000Pro, RigolDG6000,
                                       RigolDGBase, RigolDGProBase)
from .rigol_multimeter_dm858 import RigolDM858, RigolDM858E
from .rigol_rf_generator import (RigolDSG800, RigolDSG3000, RigolDSG5000,
                                 RigolDSGBase)
from .rigol_power_supply import (RigolDP700, RigolDP800, RigolDP900, RigolDP1116A,
                                 RigolDP1308A, RigolDP2000, RigolDPBase)
from .rigol_scope import RigolDS1102D, RigolDS1104, RigolMSO2072A
from .rigol_vna import RigolDNA6000, RigolRSAN, RigolVNABase
from .rigol_spectrum_analyzer import (RigolDSA800, RigolDSA1000, RigolRSA800,
                                      RigolRSA3000, RigolRSA5000, RigolRSA6000,
                                      RigolSABase)

__all__ = [
    "BaseEquipment",
    "equipment_manager",
    "RigolMSO2072A",
    "RigolDS1104",
    "RigolDS1102D",
    "RigolDL3021A",
    "RigolDL3000Base",
    "RigolDL3031A",
    "RigolDM858",
    "RigolDM858E",
    "RigolDSGBase",
    "RigolDSG800",
    "RigolDSG3000",
    "RigolDSG5000",
    "RigolModernScopeBase",
    "RigolDHO800",
    "RigolDHO1000",
    "RigolDHO5000",
    "RigolMHO900",
    "RigolMSO5000",
    "RigolMSO7000",
    "RigolMSO8000",
    "RigolDS8000R",
    "RigolDS4000",
    "RigolDS6000",
    "RigolDS70000",
    "RigolDS80000",
    "RigolDS1000ZE",
    "RigolSABase",
    "RigolDSA800",
    "RigolDSA1000",
    "RigolRSA3000",
    "RigolRSA5000",
    "RigolRSA800",
    "RigolRSA6000",
    "RigolVNABase",
    "RigolRSAN",
    "RigolDNA6000",
    "RigolM300",
    "RigolDMMBase",
    "RigolDM3058",
    "RigolDM3058E",
    "RigolDM3068",
    "RigolDPBase",
    "RigolDP800",
    "RigolDP700",
    "RigolDP900",
    "RigolDP2000",
    "RigolDP1308A",
    "RigolDP1116A",
    "RigolDGBase",
    "RigolDGProBase",
    "RigolDG800",
    "RigolDG900",
    "RigolDG1000Z",
    "RigolDG2000",
    "RigolDG4000",
    "RigolDG5000",
    "RigolDG800Pro",
    "RigolDG5000Pro",
    "RigolDG6000",
    "BK9206B",
    "BK9205B",
    "BK9130B",
    "BK1685B",
    "BK1902B",
    "MockOscilloscope",
    "MockPowerSupply",
    "MockElectronicLoad",
    "MockMultimeter",
    "MockFunctionGenerator",
    "MockSpectrumAnalyzer",
    "MockRFGenerator",
    "MockVNA",
    "MockDAQ",
]
