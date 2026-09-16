"""Which panel drives which kind of instrument.

One place to look, and one rule: an equipment type with no panel of its own
gets :class:`GenericInstrumentPanel`, never the power-supply panel. The
Control tab showing volts-and-amps dials for an oscilloscope is the bug this
package replaces.
"""

from typing import Dict, Optional, Type

from client.models.equipment import EquipmentType
from client.ui.instruments.base import InstrumentPanel
from client.ui.instruments.generic import GenericInstrumentPanel

_REGISTRY: Dict[EquipmentType, Type[InstrumentPanel]] = {}


def register_panel(equipment_type: EquipmentType, panel_class: Type[InstrumentPanel]):
    """Map an equipment type to the panel class that drives it."""
    if not issubclass(panel_class, InstrumentPanel):
        raise TypeError(f"{panel_class!r} is not an InstrumentPanel")
    _REGISTRY[EquipmentType(equipment_type)] = panel_class


def panel_class_for(equipment_type) -> Type[InstrumentPanel]:
    """The panel class for a type; the generic panel when none is registered.

    Accepts the enum, its string value, or anything else (an unknown type
    from a newer server, a mock in a test) and still answers with a panel.
    """
    try:
        key = EquipmentType(equipment_type)
    except (ValueError, TypeError):
        return GenericInstrumentPanel
    return _REGISTRY.get(key, GenericInstrumentPanel)


def registered_panels() -> Dict[EquipmentType, Type[InstrumentPanel]]:
    return dict(_REGISTRY)


def _register_defaults():
    # Imported here so the registry module stays importable on its own and
    # the panels can import the registry without a cycle.
    from client.ui.instruments.electronic_load import ElectronicLoadPanel
    from client.ui.instruments.function_generator import FunctionGeneratorPanel
    from client.ui.instruments.multimeter import MultimeterPanel
    from client.ui.instruments.rf_generator import RFGeneratorPanel
    from client.ui.instruments.oscilloscope import OscilloscopePanel
    from client.ui.instruments.power_supply import PowerSupplyPanel

    register_panel(EquipmentType.POWER_SUPPLY, PowerSupplyPanel)
    register_panel(EquipmentType.OSCILLOSCOPE, OscilloscopePanel)
    register_panel(EquipmentType.ELECTRONIC_LOAD, ElectronicLoadPanel)
    register_panel(EquipmentType.MULTIMETER, MultimeterPanel)
    register_panel(EquipmentType.FUNCTION_GENERATOR, FunctionGeneratorPanel)
    register_panel(EquipmentType.RF_SIGNAL_GENERATOR, RFGeneratorPanel)


_register_defaults()
