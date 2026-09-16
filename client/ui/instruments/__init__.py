"""Per-instrument control panels and the contract they share."""

from client.ui.instruments.base import (POLL_KINDS, POLL_MEASUREMENTS,
                                        POLL_READINGS, POLL_STATE,
                                        InstrumentPanel)
from client.ui.instruments.electronic_load import ElectronicLoadPanel
from client.ui.instruments.generic import GenericInstrumentPanel
from client.ui.instruments.multimeter import MultimeterPanel
from client.ui.instruments.oscilloscope import OscilloscopePanel
from client.ui.instruments.power_supply import PowerSupplyPanel
from client.ui.instruments.registry import (panel_class_for, register_panel,
                                            registered_panels)
from client.ui.instruments.widgets import (AnalogGauge, ChartWithReadouts,
                                           FittedReadout, nice_range)

__all__ = [
    "InstrumentPanel",
    "GenericInstrumentPanel",
    "PowerSupplyPanel",
    "OscilloscopePanel",
    "ElectronicLoadPanel",
    "MultimeterPanel",
    "POLL_KINDS",
    "POLL_READINGS",
    "POLL_MEASUREMENTS",
    "POLL_STATE",
    "panel_class_for",
    "register_panel",
    "registered_panels",
    "AnalogGauge",
    "ChartWithReadouts",
    "FittedReadout",
    "nice_range",
]
