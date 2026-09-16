"""Rigol oscilloscope driver."""

import logging
import re
import uuid
from typing import Any, Dict, Optional

import numpy as np

from shared.models.data import WaveformData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import BaseEquipment

logger = logging.getLogger(__name__)



def _wanted(items, key: str) -> bool:
    """Whether a measurement item was asked for (None means all)."""
    if not items:
        return True
    wanted = {str(i).strip().lower() for i in items}
    return key in wanted


class LegacyScopeExtras:
    """Commands the per-instrument scope panel needs that the original
    DS1000Z / MSO2000A / DS1000D drivers did not expose.

    They speak the same command tree as ``rigol_modern_scope`` for these
    subsystems, so the panel can drive a DS1054Z and a DHO804 with one set of
    command names. Mixed into the three legacy classes; every method uses only
    ``_write`` / ``_query`` / ``_query_binary`` from BaseEquipment.
    """

    #: NORMal-mode waveform reads on these families return at most 1200
    #: points (the screen), which is what a live trace wants.
    WAVEFORM_POINTS = 1200

    async def get_waveform_data(self, channel: int = 1, mode: str = "NORMal",
                                points: Optional[int] = None, **_ignored) -> Dict[str, Any]:
        """JSON-friendly waveform: metadata plus time/voltage lists.

        Same shape as ``RigolModernScopeBase.get_waveform_data`` so the client
        panel does not care which driver answered. ``points`` decimates the
        trace server-side (every n-th sample) so a 1 Hz live trace does not
        move 1200 floats per channel when 400 pixels are available.
        """
        from .rigol_modern_scope import parse_preamble, raw_to_volts

        channel = int(channel)
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")
        await self._write(f":WAV:SOUR CHAN{channel}")
        await self._write(":WAV:MODE NORM")
        await self._write(":WAV:FORM BYTE")
        preamble = parse_preamble(await self._query(":WAV:PRE?"))
        raw = await self._query_binary(":WAV:DATA?")
        volts = raw_to_volts(bytes(raw), preamble, "BYTE")
        x_inc = float(preamble.get("x_increment") or 0.0) or 1e-9
        x_org = float(preamble.get("x_origin") or 0.0)
        times = x_org + np.arange(len(volts)) * x_inc

        if points and points > 0 and len(volts) > points:
            step = int(np.ceil(len(volts) / points))
            volts = volts[::step]
            times = times[::step]

        time_scale = float(await self._query(":TIM:MAIN:SCAL?"))
        volt_scale = float(await self._query(f":CHAN{channel}:SCAL?"))
        volt_offset = float(await self._query(f":CHAN{channel}:OFFS?"))
        return {
            "equipment_id": self.cached_info.id if self.cached_info else "unknown",
            "channel": channel,
            "source": f"CHAN{channel}",
            "mode": "NORMal",
            "sample_rate": 1.0 / x_inc,
            "time_scale": time_scale,
            "voltage_scale": volt_scale,
            "voltage_offset": volt_offset,
            "num_samples": int(len(volts)),
            "x_origin": x_org,
            "x_increment": float(times[1] - times[0]) if len(times) > 1 else x_inc,
            "y_increment": preamble.get("y_increment"),
            "data_id": f"waveform_{uuid.uuid4().hex[:8]}",
            "time": [float(t) for t in times],
            "voltage": [float(v) for v in volts],
        }

    # -- trigger -----------------------------------------------------------

    async def set_trigger(self, source: Optional[str] = None, level: Optional[float] = None,
                          slope: Optional[str] = None, mode: Optional[str] = None,
                          sweep: Optional[str] = None, **_ignored) -> Dict[str, Any]:
        """Edge trigger setup; only the given parameters are written."""
        if mode is not None:
            token = str(mode).strip().upper()
            token = {"EDGE": "EDGE", "PULSE": "PULS", "PULS": "PULS", "SLOPE": "SLOP",
                     "SLOP": "SLOP", "VIDEO": "VID", "VID": "VID", "PATTERN": "PATT",
                     "PATT": "PATT"}.get(token)
            if token is None:
                raise ValueError(f"Invalid trigger mode: {mode}")
            await self._write(f":TRIG:MODE {token}")
        if source is not None:
            src = str(source).strip().upper().replace("CHANNEL", "CHAN")
            if src.startswith("CH") and not src.startswith("CHAN"):
                src = "CHAN" + src[2:]
            if src in ("EXT", "EXTERNAL"):
                src = "EXT"
            elif src in ("AC", "ACLINE", "LINE"):
                src = "ACL"
            await self._write(f":TRIG:EDGE:SOUR {src}")
        if level is not None:
            await self._write(f":TRIG:EDGE:LEV {float(level)}")
        if slope is not None:
            sl = str(slope).strip().upper()
            sl = {"POS": "POS", "POSITIVE": "POS", "RISE": "POS", "RISING": "POS",
                  "NEG": "NEG", "NEGATIVE": "NEG", "FALL": "NEG", "FALLING": "NEG",
                  "RFAL": "RFAL", "EITHER": "RFAL", "BOTH": "RFAL"}.get(sl)
            if sl is None:
                raise ValueError(f"Invalid trigger slope: {slope}")
            await self._write(f":TRIG:EDGE:SLOP {sl}")
        if sweep is not None:
            sw = str(sweep).strip().upper()
            sw = {"AUTO": "AUTO", "NORMAL": "NORM", "NORM": "NORM", "SINGLE": "SING",
                  "SING": "SING"}.get(sw)
            if sw is None:
                raise ValueError(f"Invalid trigger sweep: {sweep}")
            await self._write(f":TRIG:SWE {sw}")
        return await self.get_trigger()

    async def get_trigger(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, cmd in (("mode", ":TRIG:MODE?"), ("source", ":TRIG:EDGE:SOUR?"),
                         ("slope", ":TRIG:EDGE:SLOP?"), ("sweep", ":TRIG:SWE?"),
                         ("status", ":TRIG:STAT?")):
            try:
                result[key] = (await self._query(cmd)).strip()
            except Exception as e:
                logger.debug(f"{cmd} failed: {e}")
                result[key] = None
        try:
            result["level"] = float(await self._query(":TRIG:EDGE:LEV?"))
        except Exception:
            result["level"] = None
        return result

    async def get_trigger_status(self) -> str:
        return (await self._query(":TRIG:STAT?")).strip()

    async def force_trigger(self):
        await self._write(":TFOR")

    # -- read-back for the panel --------------------------------------------

    async def get_channel(self, channel: int = 1) -> Dict[str, Any]:
        channel = int(channel)
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")
        pre = f":CHAN{channel}"
        result: Dict[str, Any] = {"channel": channel}
        for key, cmd, conv in (("enabled", f"{pre}:DISP?", lambda v: v.strip() in ("1", "ON")),
                               ("scale", f"{pre}:SCAL?", float),
                               ("offset", f"{pre}:OFFS?", float),
                               ("coupling", f"{pre}:COUP?", lambda v: v.strip()),
                               ("probe", f"{pre}:PROB?", float)):
            try:
                result[key] = conv(await self._query(cmd))
            except Exception as e:
                logger.debug(f"{cmd} failed: {e}")
                result[key] = None
        return result

    async def get_timebase(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        try:
            result["scale"] = float(await self._query(":TIM:MAIN:SCAL?"))
        except Exception:
            result["scale"] = None
        try:
            result["offset"] = float(await self._query(":TIM:MAIN:OFFS?"))
        except Exception:
            result["offset"] = None
        return result

    async def get_state(self) -> Dict[str, Any]:
        state: Dict[str, Any] = {"model": self.model, "channels": {}}
        for ch in range(1, self.num_channels + 1):
            try:
                state["channels"][str(ch)] = await self.get_channel(ch)
            except Exception as e:
                state["channels"][str(ch)] = {"error": str(e)}
        state["timebase"] = await self.get_timebase()
        state["trigger"] = await self.get_trigger()
        return state

    async def get_measurement(self, channel: str = "CH1") -> Dict[str, Any]:
        """Acquisition-engine hook: ``CH1`` (VAVG), ``CH2:VPP``, ``1.freq``."""
        text = (channel or "CH1").strip().upper()
        if ":" in text:
            src, item = text.split(":", 1)
        elif "." in text:
            src, item = text.split(".", 1)
        else:
            src, item = text, "VAVG"
        digits = "".join(c for c in src if c.isdigit()) or "1"
        ch = int(digits)
        item = {"FREQUENCY": "FREQ", "PER": "PERIOD"}.get(item, item).lower()
        measurements = await self.get_measurements(ch)
        value = measurements.get(item)
        if value is None:
            raise ValueError(f"Unknown measurement {item!r}; have {sorted(measurements)}")
        return {"value": value, "channel": ch, "item": item}

    async def get_readings(self, channel: int = 1) -> Dict[str, Any]:
        """A cheap status snapshot, not the measurements.

        ``/readings`` is polled by the Equipment tab's WebSocket stream twice a
        second and by monitors. Answering it with automatic measurements --
        seven ``:MEAS`` queries, each of which can wait a full acquisition on a
        DS1000Z -- held the instrument's I/O lock almost continuously, and a
        front-panel command from the Control tab queued behind it for tens of
        seconds. Measurements are fetched deliberately, with ``get_measurements``,
        on the scope panel's own cadence.
        """
        out: Dict[str, Any] = {"channel": int(channel)}
        try:
            out["trigger_status"] = (await self._query(":TRIG:STAT?")).strip()
        except Exception:
            out["trigger_status"] = None
        try:
            out["timebase_scale"] = float(await self._query(":TIM:MAIN:SCAL?"))
        except Exception:
            out["timebase_scale"] = None
        try:
            out["channel_scale"] = float(await self._query(f":CHAN{int(channel)}:SCAL?"))
        except Exception:
            out["channel_scale"] = None
        return out

    async def clear_display(self):
        """``:CLEar`` -- the front panel's CLEAR key."""
        await self._write(":CLE")

    async def _extra_command(self, command: str, parameters: dict) -> Any:
        """Dispatch for the methods this mixin adds; raises on anything else."""
        handlers = {
            "get_waveform_data": self.get_waveform_data,
            "set_trigger": self.set_trigger,
            "get_trigger": self.get_trigger,
            "get_trigger_status": self.get_trigger_status,
            "force_trigger": self.force_trigger,
            "get_channel": self.get_channel,
            "get_timebase": self.get_timebase,
            "get_state": self.get_state,
            "get_measurement": self.get_measurement,
            "get_readings": self.get_readings,
            "clear": self.clear_display,
            "run": self.trigger_run,
            "stop": self.trigger_stop,
            "single": self.trigger_single,
        }
        handler = handlers.get(command)
        if handler is None:
            raise ValueError(f"Unknown command: {command}")
        return await handler(**(parameters or {}))


class RigolMSO2072A(LegacyScopeExtras, BaseEquipment):
    """Driver for Rigol MSO2072A oscilloscope."""

    def __init__(self, resource_manager, resource_string: str):
        """Initialize Rigol scope."""
        super().__init__(resource_manager, resource_string)
        self.model = "MSO2072A"
        self.manufacturer = "Rigol"
        self.num_channels = 2
        self.num_digital = 16

    async def get_info(self) -> EquipmentInfo:
        """Get oscilloscope information."""
        idn = await self._query("*IDN?")
        parts = idn.split(",")

        manufacturer = parts[0] if len(parts) > 0 else self.manufacturer
        model = parts[1] if len(parts) > 1 else self.model
        serial = parts[2] if len(parts) > 2 else None

        # Generate deterministic ID from resource string
        from .base import generate_equipment_id
        equipment_id = generate_equipment_id(self.resource_string, "scope_")

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.OSCILLOSCOPE,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial,
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get oscilloscope status."""
        try:
            # Get basic status
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            firmware = parts[3] if len(parts) > 3 else None

            # Get capabilities
            capabilities = {
                "num_channels": self.num_channels,
                "num_digital": self.num_digital,
                "bandwidth": "70MHz",
                "sample_rate": "2GSa/s",
                "memory_depth": "56Mpts",
            }

            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=self.connected,
                firmware_version=firmware,
                capabilities=capabilities,
            )
        except Exception as e:
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=False,
                error=str(e),
            )

    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Execute a command on the oscilloscope."""
        if command == "get_waveform":
            return await self.get_waveform(**parameters)
        elif command == "set_timebase":
            return await self.set_timebase(**parameters)
        elif command == "set_channel":
            return await self.set_channel(**parameters)
        elif command == "trigger_single":
            return await self.trigger_single()
        elif command == "trigger_run":
            return await self.trigger_run()
        elif command == "trigger_stop":
            return await self.trigger_stop()
        elif command == "autoscale":
            return await self.autoscale()
        elif command == "get_measurements":
            return await self.get_measurements(**parameters)
        else:
            return await self._extra_command(command, parameters)

    async def get_waveform(self, channel: int = 1) -> WaveformData:
        """Get waveform data from a channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Set waveform source
        await self._write(f":WAV:SOUR CHAN{channel}")

        # Set waveform mode to normal
        await self._write(":WAV:MODE NORM")

        # Set format to BYTE
        await self._write(":WAV:FORM BYTE")

        # Get preamble (contains scaling info)
        preamble = await self._query(":WAV:PRE?")
        preamble_parts = preamble.split(",")

        # Parse preamble
        # Format: <format>,<type>,<points>,<count>,<xincrement>,<xorigin>,<xreference>,<yincrement>,<yorigin>,<yreference>
        if len(preamble_parts) >= 10:
            num_points = int(preamble_parts[2])
            x_increment = float(preamble_parts[4])
            x_origin = float(preamble_parts[5])
            y_increment = float(preamble_parts[7])
            y_origin = float(preamble_parts[8])
            y_reference = float(preamble_parts[9])
        else:
            raise ValueError("Invalid preamble format")

        # Get timebase and vertical settings
        time_scale = float(await self._query(":TIM:MAIN:SCAL?"))
        volt_scale = float(await self._query(f":CHAN{channel}:SCAL?"))
        volt_offset = float(await self._query(f":CHAN{channel}:OFFS?"))

        # Get sample rate
        sample_rate = 1.0 / x_increment if x_increment > 0 else 1e9

        # Create waveform data object
        data_id = f"waveform_{uuid.uuid4().hex[:8]}"

        waveform_data = WaveformData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel,
            sample_rate=sample_rate,
            time_scale=time_scale,
            voltage_scale=volt_scale,
            voltage_offset=volt_offset,
            num_samples=num_points,
            data_id=data_id,
        )

        # Note: Actual waveform data should be fetched separately via :WAV:DATA?
        # and transmitted via binary WebSocket to avoid overhead

        return waveform_data

    async def get_waveform_raw(self, channel: int = 1) -> bytes:
        """Get raw waveform data."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Set waveform source
        await self._write(f":WAV:SOUR CHAN{channel}")
        await self._write(":WAV:MODE NORM")
        await self._write(":WAV:FORM BYTE")

        # Get data
        raw_data = await self._query_binary(":WAV:DATA?")
        return raw_data

    async def set_timebase(self, scale: float, offset: float = 0.0):
        """Set timebase settings."""
        await self._write(f":TIM:MAIN:SCAL {scale}")
        await self._write(f":TIM:MAIN:OFFS {offset}")

    async def set_channel(
        self,
        channel: int,
        enabled: bool = True,
        scale: float = 1.0,
        offset: float = 0.0,
        coupling: str = "DC",
    ):
        """Set channel settings."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        await self._write(f":CHAN{channel}:DISP {'ON' if enabled else 'OFF'}")
        await self._write(f":CHAN{channel}:SCAL {scale}")
        await self._write(f":CHAN{channel}:OFFS {offset}")
        await self._write(f":CHAN{channel}:COUP {coupling}")

    async def trigger_single(self):
        """Set trigger to single mode."""
        await self._write(":SING")

    async def trigger_run(self):
        """Start continuous triggering."""
        await self._write(":RUN")

    async def trigger_stop(self):
        """Stop triggering."""
        await self._write(":STOP")

    async def autoscale(self):
        """Run autoscale."""
        await self._write(":AUT")

    async def get_measurements(self, channel: int = 1, items=None) -> Dict[str, float]:
        """Get automated measurements for a channel.

        ``items`` limits the set (e.g. ``["vpp", "freq"]``): every item is a
        query that can wait an acquisition on this family, so callers that
        show three numbers should not pay for seven.
        """
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        measurements = {}

        try:
            # Set measurement source
            await self._write(f":MEAS:SOUR CHAN{channel}")

            # Get common measurements
            if _wanted(items, "vpp"):
                measurements["vpp"] = float(await self._query(":MEAS:VPP?"))
            if _wanted(items, "vmax"):
                measurements["vmax"] = float(await self._query(":MEAS:VMAX?"))
            if _wanted(items, "vmin"):
                measurements["vmin"] = float(await self._query(":MEAS:VMIN?"))
            if _wanted(items, "vavg"):
                measurements["vavg"] = float(await self._query(":MEAS:VAV?"))
            if _wanted(items, "vrms"):
                measurements["vrms"] = float(await self._query(":MEAS:VRMS?"))
            if _wanted(items, "freq"):
                measurements["freq"] = float(await self._query(":MEAS:FREQ?"))
            if _wanted(items, "period"):
                measurements["period"] = float(await self._query(":MEAS:PER?"))

        except Exception as e:
            logger.error(f"Error getting measurements: {e}")

        return measurements


def ds1000z_specs(model: str):
    """Bandwidth and channel count read out of a DS1000Z model name.

    The family shares one command tree, so a DS1054Z is driven by this class
    too -- but it is a 50 MHz instrument, and reporting the DS1104Z's 100 MHz
    for it invites a measurement that is trusted well outside the analogue
    front end. Rigol encodes both numbers in the name: DS1 + bandwidth in tens
    of MHz + channel count + Z, so DS1054Z is 50 MHz and 4 channels, DS1074Z
    is 70, DS1104Z is 100. MSO1000Z models follow the same shape.

    Returns None for anything that does not match, leaving the caller's own
    defaults in place rather than guessing.
    """
    match = re.search(r"(?:DS|MSO)1(\d{2})(\d)Z", (model or "").upper())
    if not match:
        return None
    return {
        "bandwidth_mhz": int(match.group(1)) * 10,
        "num_channels": int(match.group(2)),
    }


class RigolDS1104(LegacyScopeExtras, BaseEquipment):
    """Driver for the Rigol DS1000Z oscilloscope family.

    Named for the DS1104Z, but the DS1054Z and DS1074Z share its command tree
    and are dispatched here as well; what differs between them is bandwidth,
    which is read from the model name rather than assumed.
    """

    def __init__(self, resource_manager, resource_string: str):
        """Initialize Rigol DS1104 scope."""
        super().__init__(resource_manager, resource_string)
        self.model = "DS1104"
        self.manufacturer = "Rigol"
        self.num_channels = 4
        self.num_digital = 0

    async def get_info(self) -> EquipmentInfo:
        """Get oscilloscope information."""
        idn = await self._query("*IDN?")
        parts = idn.split(",")

        manufacturer = parts[0] if len(parts) > 0 else self.manufacturer
        model = parts[1] if len(parts) > 1 else self.model
        serial = parts[2] if len(parts) > 2 else None

        # Generate deterministic ID from resource string
        from .base import generate_equipment_id
        equipment_id = generate_equipment_id(self.resource_string, "scope_")

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.OSCILLOSCOPE,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial,
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get oscilloscope status."""
        try:
            # Get basic status
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            firmware = parts[3] if len(parts) > 3 else None

            # Capabilities of the instrument that actually answered, not of
            # the model this class is named after.
            model = parts[1] if len(parts) > 1 else self.model
            specs = ds1000z_specs(model)
            capabilities = {
                "num_channels": specs["num_channels"] if specs else self.num_channels,
                "bandwidth": f"{specs['bandwidth_mhz']}MHz" if specs else "100MHz",
                "sample_rate": "1GSa/s",
                "memory_depth": "24Mpts",
            }

            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=self.connected,
                firmware_version=firmware,
                capabilities=capabilities,
            )
        except Exception as e:
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=False,
                error=str(e),
            )

    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Execute a command on the oscilloscope."""
        if command == "get_waveform":
            return await self.get_waveform(**parameters)
        elif command == "set_timebase":
            return await self.set_timebase(**parameters)
        elif command == "set_channel":
            return await self.set_channel(**parameters)
        elif command == "trigger_single":
            return await self.trigger_single()
        elif command == "trigger_run":
            return await self.trigger_run()
        elif command == "trigger_stop":
            return await self.trigger_stop()
        elif command == "autoscale":
            return await self.autoscale()
        elif command == "get_measurements":
            return await self.get_measurements(**parameters)
        else:
            return await self._extra_command(command, parameters)

    async def get_waveform(self, channel: int = 1) -> WaveformData:
        """Get waveform data from a channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Set waveform source
        await self._write(f":WAV:SOUR CHAN{channel}")

        # Set waveform mode to normal
        await self._write(":WAV:MODE NORM")

        # Set format to BYTE
        await self._write(":WAV:FORM BYTE")

        # Get preamble (contains scaling info)
        preamble = await self._query(":WAV:PRE?")
        preamble_parts = preamble.split(",")

        # Parse preamble
        if len(preamble_parts) >= 10:
            num_points = int(preamble_parts[2])
            x_increment = float(preamble_parts[4])
            x_origin = float(preamble_parts[5])
            y_increment = float(preamble_parts[7])
            y_origin = float(preamble_parts[8])
            y_reference = float(preamble_parts[9])
        else:
            raise ValueError("Invalid preamble format")

        # Get timebase and vertical settings
        time_scale = float(await self._query(":TIM:MAIN:SCAL?"))
        volt_scale = float(await self._query(f":CHAN{channel}:SCAL?"))
        volt_offset = float(await self._query(f":CHAN{channel}:OFFS?"))

        # Get sample rate
        sample_rate = 1.0 / x_increment if x_increment > 0 else 1e9

        # Create waveform data object
        data_id = f"waveform_{uuid.uuid4().hex[:8]}"

        waveform_data = WaveformData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel,
            sample_rate=sample_rate,
            time_scale=time_scale,
            voltage_scale=volt_scale,
            voltage_offset=volt_offset,
            num_samples=num_points,
            data_id=data_id,
        )

        return waveform_data

    async def get_waveform_raw(self, channel: int = 1) -> bytes:
        """Get raw waveform data."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Set waveform source
        await self._write(f":WAV:SOUR CHAN{channel}")
        await self._write(":WAV:MODE NORM")
        await self._write(":WAV:FORM BYTE")

        # Get data
        raw_data = await self._query_binary(":WAV:DATA?")
        return raw_data

    async def set_timebase(self, scale: float, offset: float = 0.0):
        """Set timebase settings."""
        await self._write(f":TIM:MAIN:SCAL {scale}")
        await self._write(f":TIM:MAIN:OFFS {offset}")

    async def set_channel(
        self,
        channel: int,
        enabled: bool = True,
        scale: float = 1.0,
        offset: float = 0.0,
        coupling: str = "DC",
    ):
        """Set channel settings."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        await self._write(f":CHAN{channel}:DISP {'ON' if enabled else 'OFF'}")
        await self._write(f":CHAN{channel}:SCAL {scale}")
        await self._write(f":CHAN{channel}:OFFS {offset}")
        await self._write(f":CHAN{channel}:COUP {coupling}")

    async def trigger_single(self):
        """Set trigger to single mode."""
        await self._write(":SING")

    async def trigger_run(self):
        """Start continuous triggering."""
        await self._write(":RUN")

    async def trigger_stop(self):
        """Stop triggering."""
        await self._write(":STOP")

    async def autoscale(self):
        """Run autoscale."""
        await self._write(":AUT")

    async def get_measurements(self, channel: int = 1, items=None) -> Dict[str, float]:
        """Get automated measurements for a channel.

        ``items`` limits the set (e.g. ``["vpp", "freq"]``): every item is a
        query that can wait an acquisition on this family, so callers that
        show three numbers should not pay for seven.
        """
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        measurements = {}

        try:
            # Set measurement source
            await self._write(f":MEAS:SOUR CHAN{channel}")

            # Get common measurements
            if _wanted(items, "vpp"):
                measurements["vpp"] = float(await self._query(":MEAS:VPP?"))
            if _wanted(items, "vmax"):
                measurements["vmax"] = float(await self._query(":MEAS:VMAX?"))
            if _wanted(items, "vmin"):
                measurements["vmin"] = float(await self._query(":MEAS:VMIN?"))
            if _wanted(items, "vavg"):
                measurements["vavg"] = float(await self._query(":MEAS:VAV?"))
            if _wanted(items, "vrms"):
                measurements["vrms"] = float(await self._query(":MEAS:VRMS?"))
            if _wanted(items, "freq"):
                measurements["freq"] = float(await self._query(":MEAS:FREQ?"))
            if _wanted(items, "period"):
                measurements["period"] = float(await self._query(":MEAS:PER?"))

        except Exception as e:
            logger.error(f"Error getting measurements: {e}")

        return measurements


class RigolDS1102D(LegacyScopeExtras, BaseEquipment):
    """Driver for Rigol DS1102D digital oscilloscope.

    Specifications:
    - 2 analog channels
    - 100 MHz bandwidth
    - 1 GSa/s sample rate
    - 16 kpts memory depth
    """

    def __init__(self, resource_manager, resource_string: str):
        """Initialize Rigol DS1102D scope."""
        super().__init__(resource_manager, resource_string)
        self.model = "DS1102D"
        self.manufacturer = "Rigol"
        self.num_channels = 2
        self.num_digital = 0

    async def get_info(self) -> EquipmentInfo:
        """Get oscilloscope information."""
        idn = await self._query("*IDN?")
        parts = idn.split(",")

        manufacturer = parts[0] if len(parts) > 0 else self.manufacturer
        model = parts[1] if len(parts) > 1 else self.model
        serial = parts[2] if len(parts) > 2 else None

        # Generate deterministic ID from resource string
        from .base import generate_equipment_id
        equipment_id = generate_equipment_id(self.resource_string, "scope_")

        return EquipmentInfo(
            id=equipment_id,
            type=EquipmentType.OSCILLOSCOPE,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial,
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        """Get oscilloscope status."""
        try:
            # Get basic status
            idn = await self._query("*IDN?")
            parts = idn.split(",")
            firmware = parts[3] if len(parts) > 3 else None

            # Get capabilities
            capabilities = {
                "num_channels": self.num_channels,
                "bandwidth": "100MHz",
                "sample_rate": "1GSa/s",
                "memory_depth": "16kpts",
                "vertical_sensitivity": "2mV/div to 5V/div",
                "timebase_range": "2ns/div to 50s/div",
            }

            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=self.connected,
                firmware_version=firmware,
                capabilities=capabilities,
            )
        except Exception as e:
            return EquipmentStatus(
                id=self.cached_info.id if self.cached_info else "unknown",
                connected=False,
                error=str(e),
            )

    async def execute_command(self, command: str, parameters: dict) -> Any:
        """Execute a command on the oscilloscope."""
        if command == "get_waveform":
            return await self.get_waveform(**parameters)
        elif command == "set_timebase":
            return await self.set_timebase(**parameters)
        elif command == "set_channel":
            return await self.set_channel(**parameters)
        elif command == "trigger_single":
            return await self.trigger_single()
        elif command == "trigger_run":
            return await self.trigger_run()
        elif command == "trigger_stop":
            return await self.trigger_stop()
        elif command == "autoscale":
            return await self.autoscale()
        elif command == "get_measurements":
            return await self.get_measurements(**parameters)
        elif command == "set_trigger":
            return await self.set_trigger(**parameters)
        elif command == "force_trigger":
            return await self.force_trigger()
        elif command == "get_trigger_status":
            return await self.get_trigger_status()
        else:
            return await self._extra_command(command, parameters)

    async def get_waveform(self, channel: int = 1) -> WaveformData:
        """Get waveform data from a channel."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        # Set waveform source
        await self._write(f":WAV:SOUR CHAN{channel}")
        await self._write(":WAV:MODE NORM")
        await self._write(":WAV:FORM BYTE")

        # Get preamble (contains scaling info)
        preamble = await self._query(":WAV:PRE?")
        preamble_parts = preamble.split(",")

        # Parse preamble - DS1102D uses similar format to other Rigol scopes
        if len(preamble_parts) >= 10:
            num_points = int(preamble_parts[2])
            x_increment = float(preamble_parts[4])
            y_increment = float(preamble_parts[7])
            y_origin = float(preamble_parts[8])
            y_reference = float(preamble_parts[9])
        else:
            raise ValueError("Invalid preamble format")

        # Get timebase and vertical settings
        time_scale = float(await self._query(":TIM:SCAL?"))
        volt_scale = float(await self._query(f":CHAN{channel}:SCAL?"))
        volt_offset = float(await self._query(f":CHAN{channel}:OFFS?"))

        # Get sample rate
        sample_rate = 1.0 / x_increment if x_increment > 0 else 1e9

        # Create waveform data object
        data_id = f"waveform_{uuid.uuid4().hex[:8]}"

        return WaveformData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=channel,
            sample_rate=sample_rate,
            time_scale=time_scale,
            voltage_scale=volt_scale,
            voltage_offset=volt_offset,
            num_samples=num_points,
            data_id=data_id,
        )

    async def get_waveform_raw(self, channel: int = 1) -> bytes:
        """Get raw waveform data."""
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        await self._write(f":WAV:SOUR CHAN{channel}")
        await self._write(":WAV:MODE NORM")
        await self._write(":WAV:FORM BYTE")

        return await self._query_binary(":WAV:DATA?")

    async def set_timebase(self, scale: float, offset: float = 0.0):
        """Set timebase settings.

        Args:
            scale: Time per division (2ns to 50s)
            offset: Time offset (horizontal position)
        """
        if scale < 2e-9 or scale > 50:
            raise ValueError(f"Invalid timebase scale: {scale} (must be 2ns to 50s)")

        await self._write(f":TIM:SCAL {scale}")
        await self._write(f":TIM:OFFS {offset}")

    async def set_channel(
        self,
        channel: int,
        enabled: bool = True,
        scale: float = 1.0,
        offset: float = 0.0,
        coupling: str = "DC",
        probe: float = 1.0,
    ):
        """Set channel settings.

        Args:
            channel: Channel number (1-2)
            enabled: Enable/disable channel display
            scale: Volts per division (2mV to 5V)
            offset: Voltage offset
            coupling: Input coupling (DC, AC, GND)
            probe: Probe attenuation (1X, 10X, 100X, 1000X)
        """
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        if scale < 0.002 or scale > 5.0:
            raise ValueError(f"Invalid voltage scale: {scale} (must be 2mV to 5V)")

        await self._write(f":CHAN{channel}:DISP {'ON' if enabled else 'OFF'}")
        await self._write(f":CHAN{channel}:SCAL {scale}")
        await self._write(f":CHAN{channel}:OFFS {offset}")

        coupling_upper = coupling.upper()
        if coupling_upper not in ["DC", "AC", "GND"]:
            raise ValueError(f"Invalid coupling: {coupling} (must be DC, AC, or GND)")
        await self._write(f":CHAN{channel}:COUP {coupling_upper}")

        await self._write(f":CHAN{channel}:PROB {probe}")

    async def set_trigger(
        self,
        source: str = "CHAN1",
        mode: str = "EDGE",
        level: float = 0.0,
        slope: str = "POS",
        coupling: str = "DC",
    ):
        """Set trigger settings.

        Args:
            source: Trigger source (CHAN1, CHAN2, EXT, ACLINE)
            mode: Trigger mode (EDGE, PULSE, VIDEO, SLOPE, PATTERN)
            level: Trigger level in volts
            slope: Trigger slope (POS, NEG, RFAL)
            coupling: Trigger coupling (DC, AC, HF, LF)
        """
        valid_sources = ["CHAN1", "CHAN2", "EXT", "ACLINE"]
        source_upper = source.upper().replace(" ", "")
        if source_upper not in valid_sources:
            raise ValueError(f"Invalid trigger source: {source}")

        mode_upper = mode.upper()
        if mode_upper not in ["EDGE", "PULSE", "VIDEO", "SLOPE", "PATTERN"]:
            raise ValueError(f"Invalid trigger mode: {mode}")
        await self._write(f":TRIG:MODE {mode_upper}")

        await self._write(f":TRIG:{mode_upper}:SOUR {source_upper}")
        await self._write(f":TRIG:{mode_upper}:LEV {level}")

        if mode_upper == "EDGE":
            slope_upper = slope.upper()
            if slope_upper not in ["POS", "NEG", "RFAL"]:
                raise ValueError(f"Invalid trigger slope: {slope}")
            await self._write(f":TRIG:EDGE:SLOP {slope_upper}")

        coupling_upper = coupling.upper()
        if coupling_upper not in ["DC", "AC", "HF", "LF"]:
            raise ValueError(f"Invalid trigger coupling: {coupling}")
        await self._write(f":TRIG:{mode_upper}:COUP {coupling_upper}")

    async def trigger_single(self):
        """Set trigger to single mode and acquire one trigger event."""
        await self._write(":SING")

    async def trigger_run(self):
        """Start continuous triggering."""
        await self._write(":RUN")

    async def trigger_stop(self):
        """Stop triggering."""
        await self._write(":STOP")

    async def autoscale(self):
        """Run autoscale to automatically set vertical and horizontal scales."""
        await self._write(":AUT")

    async def get_measurements(self, channel: int = 1, items=None) -> Dict[str, float]:
        """Get automated measurements for a channel.

        Returns measurements including:
        - vpp: Peak-to-peak voltage
        - vmax/vmin: Maximum/minimum voltage
        - vavg: Average voltage
        - vrms: RMS voltage
        - freq: Frequency
        - period: Period
        - rise_time/fall_time: Rise/fall time (10%-90%)
        - positive_width/negative_width: Pulse widths
        - duty_cycle: Duty cycle percentage
        """
        if channel < 1 or channel > self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        measurements = {}

        try:
            await self._write(f":MEAS:SOUR CHAN{channel}")

            # Voltage measurements
            if _wanted(items, "vpp"):
                measurements["vpp"] = float(await self._query(":MEAS:VPP?"))
            if _wanted(items, "vmax"):
                measurements["vmax"] = float(await self._query(":MEAS:VMAX?"))
            if _wanted(items, "vmin"):
                measurements["vmin"] = float(await self._query(":MEAS:VMIN?"))
            if _wanted(items, "vavg"):
                measurements["vavg"] = float(await self._query(":MEAS:VAV?"))
            if _wanted(items, "vrms"):
                measurements["vrms"] = float(await self._query(":MEAS:VRMS?"))

            # Time measurements
            if _wanted(items, "freq"):
                measurements["freq"] = float(await self._query(":MEAS:FREQ?"))
            if _wanted(items, "period"):
                measurements["period"] = float(await self._query(":MEAS:PER?"))

            # Timing measurements (may not be available on all signals)
            try:
                measurements["rise_time"] = float(await self._query(":MEAS:RIS?"))
                measurements["fall_time"] = float(await self._query(":MEAS:FALL?"))
                measurements["positive_width"] = float(await self._query(":MEAS:PWID?"))
                measurements["negative_width"] = float(await self._query(":MEAS:NWID?"))
                measurements["duty_cycle"] = float(await self._query(":MEAS:DUTY?"))
            except Exception as e:
                logger.debug(f"Some timing measurements not available: {e}")

        except Exception as e:
            logger.error(f"Error getting measurements: {e}")

        return measurements

    async def force_trigger(self):
        """Force a trigger event immediately."""
        await self._write(":TFOR")

    async def get_trigger_status(self) -> str:
        """Get current trigger status.

        Returns:
            Trigger status: TD (triggered), WAIT (waiting), RUN (running), AUTO, STOP
        """
        return await self._query(":TRIG:STAT?")
