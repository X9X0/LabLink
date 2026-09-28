"""Siglent SPD-series programmable DC power supplies.

Verified against an SPD3303X-E, firmware 1.01.01.03.12R1 V6.2, serial
SPD3XJGCA01014, on the bench at 192.168.91.191.

The command set comes from the SPD3000X Quick Start (E02A). There is no
separate SPD programming guide -- Siglent publishes the command list in
the quick start, which is why it is easy to miss.

Two things about this instrument are worth knowing before reading the
code, because both cost something to discover:

**The abbreviations are not the usual ones.** The SPD line is
conventional SCPI, where the uppercase run in the published spelling is
the legal short form. ``MEASure:POWEr?`` therefore abbreviates to
``MEAS:POWE?`` -- four letters, not three. ``MEAS:POW?``, which is what
every other supply in this tree uses and what anyone would write from
memory, is an undefined header here. On the bench:

    MEASure:POWEr? CH1  -> '0.00'
    MEASure:POWE?  CH1  -> '0.00'
    MEAS:POW?      CH1  -> no reply at all, then
    SYSTem:ERRor?       -> '-113,Undefined header,MEAS:POW?'

Note what the failure looks like. The instrument does not answer and
does not fault the link -- it simply never replies, so the caller waits
out a full timeout and the connection needs clearing before the next
query works. A wrong keyword costs a stall, not an error. Every command
in this module is therefore spelled out in full.

**The channel is part of the command, not a parameter.** Setting goes
``CH1:VOLTage 5``; measuring goes ``MEASure:VOLTage? CH1``; output
switching goes ``OUTPut CH1,ON``. Three different shapes for the same
idea, and the third takes a comma rather than a space.

Channel 3 is not programmable. It is a fixed 2.5 / 3.3 / 5 V rail
selected by a switch on the front panel, and the only thing remote
control can do with it is switch it on and off. ``MEASure`` and the
channel prefix accept CH1 and CH2 only.
"""

import logging
import math
from typing import Any, Dict, Optional, Union

from shared.models.data import PowerSupplyData
from shared.models.equipment import (EquipmentInfo, EquipmentStatus,
                                     EquipmentType)

from .base import (BaseEquipment, CommandRejected, SetpointRefused,
                   generate_equipment_id)
from .siglent_registry import MANUFACTURER, resolve_idn, resolve_model

logger = logging.getLogger(__name__)


#: Channels that accept a setpoint. CH3 is a fixed rail: it appears in
#: OUTPut and nowhere else.
PROGRAMMABLE_CHANNELS = (1, 2)

#: Every channel that can be switched on and off.
SWITCHABLE_CHANNELS = (1, 2, 3)

#: Output coupling. The instrument calls it tracking.
TRACK_MODES = {0: "independent", 1: "series", 2: "parallel"}

#: The five timing groups a channel can hold, run one after another.
TIMER_GROUPS = (1, 2, 3, 4, 5)

#: Longest a single timing group can hold, per the guide.
MAX_TIMER_SECONDS = 10000.0
TRACK_BY_NAME = {name: value for value, name in TRACK_MODES.items()}


#: Bits of ``SYSTem:STATus?``, which answers in hex. From the quick
#: start's table. Bits 2 and 3 are a two-bit field and are handled
#: separately.
_STATUS_BITS = {
    0: ("ch1_cc", "CH1 in constant current"),
    1: ("ch2_cc", "CH2 in constant current"),
    4: ("ch1_on", "CH1 output on"),
    5: ("ch2_on", "CH2 output on"),
    6: ("timer1_on", "CH1 timer running"),
    7: ("timer2_on", "CH2 timer running"),
    8: ("ch1_waveform_display", "CH1 showing the waveform screen"),
    9: ("ch2_waveform_display", "CH2 showing the waveform screen"),
}


class SiglentSPD(BaseEquipment):
    """An SPD-series supply.

    Defaults describe the SPD3303X/X-E: two programmable channels at
    0-32 V / 0-3.2 A plus the fixed CH3 rail. Subclasses narrow it.
    """

    model = "SPD3303X"
    num_channels = 3
    programmable_channels = PROGRAMMABLE_CHANNELS
    max_voltage = 32.0
    max_current = 3.2
    #: Whether the family has the fixed third rail at all. The single
    #: channel SPD1000X does not.
    has_fixed_rail = True

    def __init__(self, resource_manager, resource_string: str,
                 model: Optional[str] = None):
        super().__init__(resource_manager, resource_string)
        self.manufacturer = MANUFACTURER
        if model:
            self.model = model
        self.serial_number: Optional[str] = None
        self.firmware_version: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Wire helpers
    # ------------------------------------------------------------------ #

    async def _command(self, command: str) -> None:
        """Send a setting and ask the supply what it made of it.

        Same reasoning as the DL3000 driver: a SCPI fault goes to the
        error queue, not to the reply, so a write the instrument threw
        away is indistinguishable from one it obeyed.

        There is no ``*CLS`` here, and that is deliberate rather than an
        omission -- the quick start's command list does not include it,
        and this is not an instrument to send undocumented headers to
        when the documented penalty for one is a stalled link. The queue
        is drained by reading instead, which is what ``SYSTem:ERRor?``
        does on every SCPI instrument.
        """
        await self._drain_errors()
        await self._write(command)
        try:
            fault = await self.get_error()
        except Exception as e:
            # Not being able to ask is not the same as the command
            # failing, and must not be reported as one.
            logger.debug("%s: could not read the error queue after %r: %s"
                         % (self.resource_string, command, e))
            return
        if fault.get("code"):
            raise CommandRejected(
                "%s rejected %r: %s"
                % (self.model, command,
                   fault.get("message") or fault.get("raw")))

    async def _drain_errors(self, limit: int = 8) -> None:
        """Empty the error queue so an old fault is not blamed on the
        next command."""
        for _ in range(limit):
            try:
                fault = await self.get_error()
            except Exception:
                return
            if not fault.get("code"):
                return

    async def get_error(self) -> Dict[str, Any]:
        """One entry from the error queue.

        The reply is ``0 No Error`` -- space separated -- when clean and
        ``-113,Undefined header,MEAS:POW?`` when not. Two different
        shapes from the same query, so both are parsed rather than one
        assumed.
        """
        raw = (await self._query("SYSTem:ERRor?")).strip()
        head = raw.split(",")[0].strip()
        code_text = head.split()[0] if head.split() else head
        try:
            code = int(code_text)
        except ValueError:
            return {"code": None, "message": raw, "raw": raw}
        message = raw[len(code_text):].lstrip(" ,").strip()
        return {"code": code, "message": message or "No error", "raw": raw}

    def _check_channel(self, channel: Union[int, str],
                       allowed=None) -> int:
        """Resolve a channel to 1, 2 or 3, refusing anything else.

        Accepts 1 and "CH1" alike, because callers arrive from both an
        API and a panel.
        """
        allowed = allowed or self.programmable_channels
        text = str(channel).strip().upper()
        if text.startswith("CH"):
            text = text[2:]
        try:
            number = int(text)
        except ValueError:
            raise SetpointRefused(
                "Channel %r is not a channel number on this supply" % channel)
        if number not in allowed:
            if number in SWITCHABLE_CHANNELS and self.has_fixed_rail:
                raise SetpointRefused(
                    "CH%d on the %s is a fixed %s rail selected by the front "
                    "panel switch. It can be switched on and off and nothing "
                    "else -- it takes no setpoint and cannot be measured."
                    % (number, self.model, "2.5/3.3/5 V"))
            raise SetpointRefused(
                "CH%d is not a channel on the %s. It has: %s"
                % (number, self.model,
                   ", ".join("CH%d" % c for c in allowed)))
        return number

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #

    async def connect(self):
        """Open the link, then ask the supply what it is.

        BaseEquipment.connect returns nothing and raises on failure, so
        there is no return value to test here -- reaching the next line
        is what success looks like. Identification is best effort on
        top of that: a supply that is open and talking should not be
        thrown away because its *IDN? was slow.
        """
        await super().connect()
        try:
            fields, family = resolve_idn(await self._query("*IDN?"))
        except Exception as e:
            logger.warning("%s: could not identify the supply: %s"
                           % (self.resource_string, e))
            return
        if fields.get("model"):
            self.model = fields["model"]
        self.serial_number = fields.get("serial_number")
        self.firmware_version = fields.get("firmware_version")
        if family is not None:
            self.num_channels = family.channels
            if family.max_voltage:
                self.max_voltage = family.max_voltage
            if family.max_current:
                self.max_current = family.max_current
            self.has_fixed_rail = family.channels >= 3
            self.programmable_channels = tuple(
                c for c in (1, 2) if c <= max(1, family.channels - 1)
            ) or (1,)

    async def get_info(self) -> EquipmentInfo:
        return EquipmentInfo(
            id=generate_equipment_id(self.resource_string, "ps_"),
            type=EquipmentType.POWER_SUPPLY,
            manufacturer=MANUFACTURER,
            model=self.model,
            serial_number=self.serial_number,
            connection_type=self._determine_connection_type(),
            resource_string=self.resource_string,
        )

    async def get_status(self) -> EquipmentStatus:
        return EquipmentStatus(
            id=self.cached_info.id if self.cached_info else "unknown",
            connected=self.connected,
            firmware_version=self.firmware_version,
            capabilities=self._capabilities(),
        )

    def _capabilities(self) -> Dict[str, Any]:
        return {
            "channels": self.num_channels,
            "programmable_channels": list(self.programmable_channels),
            "max_voltage": self.max_voltage,
            "max_current": self.max_current,
            "has_fixed_rail": self.has_fixed_rail,
            "tracking_modes": sorted(TRACK_BY_NAME),
        }

    # ------------------------------------------------------------------ #
    # Setpoints
    # ------------------------------------------------------------------ #

    async def set_voltage(self, voltage: float, channel: Union[int, str] = 1):
        n = self._check_channel(channel)
        value = float(voltage)
        if value < 0 or value > self.max_voltage:
            raise SetpointRefused(
                "%.3f V is outside the %s range of 0 to %g V"
                % (value, self.model, self.max_voltage))
        await self._command("CH%d:VOLTage %.3f" % (n, value))

    async def set_current(self, current: float, channel: Union[int, str] = 1):
        n = self._check_channel(channel)
        value = float(current)
        if value < 0 or value > self.max_current:
            raise SetpointRefused(
                "%.3f A is outside the %s range of 0 to %g A"
                % (value, self.model, self.max_current))
        await self._command("CH%d:CURRent %.3f" % (n, value))

    async def get_setpoints(self, channel: Union[int, str] = 1
                            ) -> Dict[str, Optional[float]]:
        n = self._check_channel(channel)
        return {
            "voltage": await self._float("CH%d:VOLTage?" % n),
            "current": await self._float("CH%d:CURRent?" % n),
        }

    async def set_output(self, enabled: bool,
                         channel: Union[int, str] = 1) -> None:
        """Switch a channel on or off.

        CH3 is allowed here and nowhere else: switching the fixed rail
        is the one thing remote control can do with it.
        """
        n = self._check_channel(channel, allowed=SWITCHABLE_CHANNELS
                                if self.has_fixed_rail
                                else self.programmable_channels)
        await self._command("OUTPut CH%d,%s" % (n, "ON" if enabled else "OFF"))

    async def get_output(self, channel: Union[int, str] = 1) -> bool:
        """Whether a channel is on.

        There is no OUTPut? query. The state lives in SYSTem:STATus?,
        which is the only place to read it from.
        """
        n = self._check_channel(channel, allowed=SWITCHABLE_CHANNELS
                                if self.has_fixed_rail
                                else self.programmable_channels)
        status = await self.get_system_status()
        if n == 3:
            # The status word has no CH3 bit. Saying "off" would be a
            # guess presented as a fact.
            raise CommandRejected(
                "The %s does not report whether CH3 is on. Its status word "
                "has bits for CH1 and CH2 only." % self.model)
        return bool(status.get("ch%d_on" % n))

    # ------------------------------------------------------------------ #
    # Measurement
    # ------------------------------------------------------------------ #

    async def _float(self, query: str) -> Optional[float]:
        raw = (await self._query(query)).strip()
        try:
            return float(raw)
        except ValueError:
            logger.debug("%s: %r answered %r, which is not a number"
                         % (self.resource_string, query, raw))
            return None

    async def measure(self, channel: Union[int, str] = 1
                      ) -> Dict[str, Optional[float]]:
        """Measured volts, amps and watts for one channel.

        POWEr, not POW. See the module docstring.
        """
        n = self._check_channel(channel)
        return {
            "voltage": await self._float("MEASure:VOLTage? CH%d" % n),
            "current": await self._float("MEASure:CURRent? CH%d" % n),
            "power": await self._float("MEASure:POWEr? CH%d" % n),
        }

    async def get_system_status(self) -> Dict[str, Any]:
        """Decode ``SYSTem:STATus?``.

        The reply is hex with an 0x prefix, and the quick start is
        explicit that it has to be read as bits.
        """
        raw = (await self._query("SYSTem:STATus?")).strip()
        try:
            value = int(raw, 16)
        except ValueError:
            raise ValueError("Unexpected SYSTem:STATus? reply: %r" % raw)
        out: Dict[str, Any] = {"raw": raw, "value": value}
        for bit, (name, _why) in _STATUS_BITS.items():
            out[name] = bool(value & (1 << bit))
        # Bits 2 and 3 are one field. The quick start documents two of
        # its four values -- "01: Independent mode; 10: Parallel mode"
        # -- and says nothing about series, which is the third mode the
        # same instrument offers.
        #
        # Asked on the bench (DL3B268M00049's neighbour, SPD3XJGCA01014):
        #
        #   OUTPut:TRACK 0 -> SYSTem:STATus? 0x4  bits 01  independent
        #   OUTPut:TRACK 1 -> SYSTem:STATus? 0xc  bits 11  series
        #   OUTPut:TRACK 2 -> SYSTem:STATus? 0x8  bits 10  parallel
        #
        # So 11 is series. Recorded here because a panel cannot show
        # which mode a supply is in without it, and the only other way
        # to find out is to do what this comment did.
        coupling = (value >> 2) & 0b11
        out["coupling"] = {0b01: "independent",
                           0b11: "series",
                           0b10: "parallel"}.get(coupling)
        out["coupling_bits"] = coupling
        return out

    async def get_tracking(self) -> Optional[str]:
        """Which of independent, series or parallel the supply is in."""
        return (await self.get_system_status()).get("coupling")

    async def get_readings(self, channel: Union[int, str] = 1
                           ) -> PowerSupplyData:
        """Measured V/I plus setpoints, output state and CV/CC."""
        n = self._check_channel(channel)
        async with self._io_lock:
            measured = await self.measure(n)
            setpoints = await self.get_setpoints(n)
            status = await self.get_system_status()

        v_set = setpoints["voltage"]
        i_set = setpoints["current"]
        in_cc = bool(status.get("ch%d_cc" % n))
        on = bool(status.get("ch%d_on" % n))
        return PowerSupplyData(
            equipment_id=self.cached_info.id if self.cached_info else "unknown",
            channel=n,
            voltage_set=float("nan") if v_set is None else v_set,
            current_set=float("nan") if i_set is None else i_set,
            voltage_actual=measured["voltage"],
            current_actual=measured["current"],
            output_enabled=on,
            # The status bit says CC or not; CV is the other case, but
            # only while the output is actually on.
            in_cv_mode=on and not in_cc,
            in_cc_mode=on and in_cc,
        )

    async def get_all_readings(self) -> Dict[str, Any]:
        """Every readable channel in one pass.

        A panel showing three channels cannot afford a round trip
        each. Measured on the bench against this supply: get_readings
        for one channel is ~83 ms and a bare status query is ~73 ms,
        so almost all of it is the hop rather than the instrument.
        Three sequential per-channel calls come to ~250 ms against a
        100 ms poll; one call that reads the status word once and
        shares it across the channels is a single hop.

        CH3 is reported in ``unreadable`` rather than ``channels``,
        and that is not tidiness either. It answers none of the
        measurement queries -- and it does not refuse them, it simply
        never replies, so each attempt costs a full read timeout.
        Probed on the bench:

            MEASure:VOLTage? CH3  -> no reply, error queue clean
            CH3:VOLTage?          -> no reply, then
            SYSTem:ERRor?         -> -113,Undefined header,CH3:VOLTage?

        A caller that tried CH3 anyway would stall the whole poll, not
        just that channel, so the only safe thing is to say plainly
        that it cannot be read.
        """
        async with self._io_lock:
            status = await self.get_system_status()
            channels = []
            for n in self.programmable_channels:
                measured = await self.measure(n)
                setpoints = await self.get_setpoints(n)
                on = bool(status.get("ch%d_on" % n))
                in_cc = bool(status.get("ch%d_cc" % n))
                channels.append({
                    "channel": n,
                    # Bits 6 and 7. There is no countdown query -- the
                    # timer subsystem is TIMEr:SET, TIMEr:SET? and
                    # TIMEr, and none of them reports time remaining --
                    # so this is the whole of what the instrument will
                    # say about a run in progress.
                    "timer_running": bool(status.get("timer%d_on" % n)),
                    "voltage_set": setpoints["voltage"],
                    "current_set": setpoints["current"],
                    "voltage_actual": measured["voltage"],
                    "current_actual": measured["current"],
                    "power_actual": measured["power"],
                    "output_enabled": on,
                    # Off is not regulating anything, so claim neither.
                    "in_cv_mode": on and not in_cc,
                    "in_cc_mode": on and in_cc,
                })

        unreadable = []
        if self.has_fixed_rail:
            unreadable.append({
                "channel": 3,
                "why": ("a fixed 2.5/3.3/5 V rail selected by the front "
                        "panel switch. The supply reports neither its "
                        "voltage nor its draw over the remote interface, "
                        "and it can only be switched on and off."),
                "switchable": True,
            })

        return {
            "channels": channels,
            "unreadable": unreadable,
            "coupling": status.get("coupling"),
            "raw_status": status.get("raw"),
        }

    async def get_measurement(self, channel: str = "V") -> Dict[str, Any]:
        """One quantity, taken directly.

        Overridden because this supply has a query per quantity, so
        there is no reason to read all three and throw two away.
        """
        key = str(channel).strip().upper()
        key = self.MEASUREMENT_ALIASES.get(key, key)
        direct = {"V": ("MEASure:VOLTage?", "V", "voltage"),
                  "I": ("MEASure:CURRent?", "A", "current"),
                  "P": ("MEASure:POWEr?", "W", "power")}
        if key not in direct:
            return await super().get_measurement(channel)
        query, unit, label = direct[key]
        value = await self._float("%s CH%d" % (query, self.programmable_channels[0]))
        return {"channel": key, "value": value, "unit": unit, "label": label}

    # ------------------------------------------------------------------ #
    # Coupling
    # ------------------------------------------------------------------ #

    async def set_tracking(self, mode: Union[int, str]) -> None:
        """Independent, series or parallel.

        These are not display options. The guide: in series "CH1 and
        CH2 are linked internally into one channel which is controlled
        by CH1", rated 0-60 V / 0-3.2 A, with the load across CH2's
        positive and CH1's negative terminal; in parallel they are
        linked the same way, rated 0-32 V / 0-6.4 A, with the load on
        CH1's terminals. So the wiring an operator wants depends on the
        mode, and changing it under a live load changes what their
        circuit is connected to.

        Which is why the outputs go off first. The guide's own
        procedure starts from a supply that is off -- "Make sure that
        parallel/series mode is off" before wiring -- and switching
        while sourcing is not something to do on the operator's behalf
        without being asked.
        """
        if isinstance(mode, str):
            value = TRACK_BY_NAME.get(mode.strip().lower())
            if value is None:
                raise SetpointRefused(
                    "Tracking mode must be one of %s"
                    % ", ".join(sorted(TRACK_BY_NAME)))
        else:
            value = int(mode)
            if value not in TRACK_MODES:
                raise SetpointRefused(
                    "Tracking mode must be 0, 1 or 2 (%s)"
                    % ", ".join("%d=%s" % kv for kv in TRACK_MODES.items()))
        # Off first: see the docstring. Both channels, because in
        # series and parallel it is CH1 that carries the pair.
        for channel in self.programmable_channels:
            try:
                await self.set_output(False, channel)
            except Exception as e:
                logger.debug("%s: could not switch CH%d off before changing "
                             "the coupling: %s"
                             % (self.resource_string, channel, e))
        await self._command("OUTPut:TRACK %d" % value)

    # ------------------------------------------------------------------ #
    # Timer
    # ------------------------------------------------------------------ #

    async def _refuse_unless_independent(self, what: str) -> None:
        """The timer only runs in independent mode.

        The guide is explicit: "The timer function is invalid when the
        series mode or parallel mode is turn on." The instrument does
        not say so -- it accepts the command and does nothing -- so
        the refusal has to come from here or not at all.
        """
        try:
            coupling = await self.get_tracking()
        except Exception as e:
            logger.debug("%s: could not read the coupling before %s: %s"
                         % (self.resource_string, what, e))
            return
        if coupling in (None, "independent"):
            return
        raise SetpointRefused(
            "The %s timer only runs in independent mode, and this supply is "
            "in %s mode. In %s, CH1 and CH2 are one channel controlled by "
            "CH1, and the timer is ignored -- the instrument accepts the "
            "command and does nothing. Set independent mode first."
            % (self.model, coupling, coupling))

    def _check_timer_group(self, group: Union[int, str]) -> int:
        try:
            number = int(group)
        except (TypeError, ValueError):
            raise SetpointRefused("Timer group %r is not a number" % group)
        if number not in TIMER_GROUPS:
            raise SetpointRefused(
                "The %s has timer groups %s, not %r"
                % (self.model, "-".join(str(g) for g in
                                        (TIMER_GROUPS[0], TIMER_GROUPS[-1])),
                   group))
        return number

    async def set_timer_step(self, channel: Union[int, str],
                             group: Union[int, str], voltage: float,
                             current: float, seconds: float) -> None:
        """One of the five timing groups for a channel.

        Each group is a voltage, a current and how long to hold them,
        and the five run one after another -- the guide calls it
        consecutive output. Longest per group is 10000 s.
        """
        n = self._check_channel(channel)
        number = self._check_timer_group(group)
        voltage, current = float(voltage), float(current)
        seconds = float(seconds)
        if voltage < 0 or voltage > self.max_voltage:
            raise SetpointRefused(
                "%.3f V is outside the %s range of 0 to %g V"
                % (voltage, self.model, self.max_voltage))
        if current < 0 or current > self.max_current:
            raise SetpointRefused(
                "%.3f A is outside the %s range of 0 to %g A"
                % (current, self.model, self.max_current))
        if seconds < 0 or seconds > MAX_TIMER_SECONDS:
            raise SetpointRefused(
                "A timer group holds for 0 to %g s; %g was asked for"
                % (MAX_TIMER_SECONDS, seconds))
        await self._refuse_unless_independent("timer")
        await self._command("TIMEr:SET CH%d,%d,%.3f,%.3f,%g"
                            % (n, number, voltage, current, seconds))

    async def get_timer_step(self, channel: Union[int, str],
                             group: Union[int, str]) -> Dict[str, Any]:
        """What one timing group holds.

        The reply is three comma-separated numbers, voltage then
        current then seconds.
        """
        n = self._check_channel(channel)
        number = self._check_timer_group(group)
        raw = (await self._query("TIMEr:SET? CH%d,%d" % (n, number))).strip()
        parts = [piece.strip() for piece in raw.split(",")]
        out: Dict[str, Any] = {"channel": n, "group": number, "raw": raw}
        for key, piece in zip(("voltage", "current", "seconds"), parts):
            try:
                out[key] = float(piece)
            except ValueError:
                out[key] = None
        for key in ("voltage", "current", "seconds"):
            out.setdefault(key, None)
        return out

    async def set_timer_enabled(self, enabled: bool,
                                channel: Union[int, str] = 1) -> None:
        """Start or stop a channel's timer.

        Worth knowing, from the guide: switching the output off while
        the timer runs stops the countdown rather than ending it, and
        it picks up again when the output comes back on. The timer
        switches itself off when the time reaches zero.
        """
        n = self._check_channel(channel)
        if enabled:
            await self._refuse_unless_independent("timer")
        await self._command("TIMEr CH%d,%s" % (n, "ON" if enabled else "OFF"))

    async def get_timer_running(self, channel: Union[int, str] = 1) -> bool:
        """Whether a channel's timer is counting.

        From the status word: bit 6 is CH1's timer, bit 7 is CH2's.
        """
        n = self._check_channel(channel)
        status = await self.get_system_status()
        return bool(status.get("timer%d_on" % n))

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #

    async def execute_command(self, command: str, parameters: dict) -> Any:
        actions = {
            "set_voltage": self.set_voltage,
            "set_current": self.set_current,
            "get_setpoints": self.get_setpoints,
            "set_output": self.set_output,
            "get_output": self.get_output,
            "measure": self.measure,
            "get_readings": self.get_readings,
            "get_all_readings": self.get_all_readings,
            "get_measurement": self.get_measurement,
            "get_system_status": self.get_system_status,
            "set_tracking": self.set_tracking,
            "get_tracking": self.get_tracking,
            "set_timer_step": self.set_timer_step,
            "get_timer_step": self.get_timer_step,
            "set_timer_enabled": self.set_timer_enabled,
            "get_timer_running": self.get_timer_running,
            "get_error": self.get_error,
            "get_info": self.get_info,
            "get_status": self.get_status,
        }
        handler = actions.get(command)
        if handler is None:
            raise ValueError(f"Unknown command: {command}")
        return await handler(**(parameters or {}))


class SiglentSPD3303X(SiglentSPD):
    """SPD3303X and SPD3303X-E. Two programmable channels plus the
    fixed rail."""

    model = "SPD3303X"


class SiglentSPD1000X(SiglentSPD):
    """SPD1168X and SPD1305X. One channel, no fixed rail.

    The channel prefix is optional on a single-channel supply, but
    sending CH1: is accepted and keeps one code path.
    """

    model = "SPD1168X"
    num_channels = 1
    programmable_channels = (1,)
    has_fixed_rail = False
    max_voltage = 16.0
    max_current = 8.0


def spd_driver_for(model: Optional[str]):
    """The SPD class for a model string, or None if it is not an SPD."""
    family = resolve_model(model)
    if family is None:
        return None
    return {"SPD3000X": SiglentSPD3303X,
            "SPD1000X": SiglentSPD1000X}.get(family.key)
