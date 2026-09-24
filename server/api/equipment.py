"""Equipment management API endpoints."""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.config.settings import settings
from server.discovery.models import DiscoveredDevice
from server.equipment import rigol_registry
from server.equipment.base import InstrumentBusy, SetpointRefused
from server.equipment.bk_registry import (CATEGORY_LABELS, MANUFACTURER,
                                          catalog, resolve_model)
from server.equipment.locks import lock_manager
from server.equipment.manager import equipment_manager
from shared.models.commands import Command, CommandResponse
from shared.models.equipment import (EquipmentCommand, EquipmentInfo,
                                     EquipmentStatus, EquipmentType)

logger = logging.getLogger(__name__)

router = APIRouter()


# Commands that require exclusive control (vs read-only)
CONTROL_COMMANDS = {
    "set_voltage",
    "set_current",
    "set_output",
    # Protection limits are control, not configuration: raising an OVP ceiling
    # under another operator's session removes the guard on their experiment,
    # and clearing a trip re-arms an output that latched off for a reason.
    "set_ovp",
    "set_ocp",
    "clear_protection",
    "set_input",
    "set_mode",
    "set_range",
    "set_channel",
    "set_trigger",
    "set_timebase",
    "set_scale",
    "set_position",
    "set_offset",
    "reset",
    "clear",
    "save",
    "recall",
    "calibrate",
}


def requires_control(action: str) -> bool:
    """Check if an action requires exclusive equipment control."""
    action_lower = action.lower()
    return any(cmd in action_lower for cmd in CONTROL_COMMANDS)


def _why_control_was_refused(equipment_id: str, session_id: str) -> str:
    """Say which of the three reasons it was, because they differ.

    ``can_control_equipment`` returns False for three unrelated
    situations, and the old message described all of them as "locked by
    session unknown":

      * nobody holds a lock at all -- you simply have not taken one;
      * somebody else holds it;
      * you hold it, but as an observer rather than exclusively.

    The first is the common one and the message was actively wrong
    about it. "Locked by session unknown" reads as another operator
    having taken your instrument, which is the opposite of the truth
    and sends you looking for a colleague to ask. It cost time on the
    bench once already, when a lock had merely timed out.
    """
    status = lock_manager.get_lock_status(equipment_id)

    if not status.get("locked"):
        return (
            f"No lock is held on {equipment_id}, and control commands "
            f"need one. Acquire an exclusive lock first. (Nobody else "
            f"holds it -- a lock of your own may simply have timed out.)"
        )

    owner = status.get("session_id")
    if owner != session_id:
        who = status.get("username") or "another session"
        expired = " Their lock has expired and will be released shortly." \
            if status.get("expired") else ""
        return (
            f"{equipment_id} is locked by {who} (session {owner})."
            f"{expired} Control commands need the exclusive lock."
        )

    return (
        f"You hold {equipment_id} as an observer, which permits reading "
        f"but not control. Acquire it exclusively to send commands."
    )


class ConnectDeviceRequest(BaseModel):
    """Request to connect to a device."""

    resource_string: str
    equipment_type: EquipmentType
    model: str


class DiscoverDevicesResponse(BaseModel):
    """Response for device discovery."""

    devices: List[DiscoveredDevice]


@router.post("/discover")
async def discover_devices():
    """Discover available VISA devices with full device information."""
    try:
        devices = await equipment_manager.discover_devices()
        # Convert DiscoveredDevice objects to dicts for JSON serialization
        devices_dict = [device.model_dump() for device in devices]
        return {"devices": devices_dict}
    except Exception as e:
        logger.error(f"Error discovering devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_supported_models(
    manufacturer: Optional[str] = None,
    equipment_type: Optional[str] = None,
    supported_only: bool = False,
):
    """List the instrument models LabLink knows about.

    Every B&K Precision family with a published programming manual is listed,
    each with the interfaces it actually carries, the protocol it speaks, and
    whether LabLink has a driver for it. A family with ``supported: false`` is
    still identified during discovery — it just cannot be connected yet.

    **Query parameters:**
    - `manufacturer`: filter by manufacturer (B&K Precision or Rigol)
    - `equipment_type`: filter by LabLink equipment type
    - `supported_only`: omit families with no driver

    **Returns:** a list of model entries.
    """
    entries = catalog() + rigol_registry.catalog()

    if manufacturer:
        wanted = manufacturer.lower()
        entries = [e for e in entries if wanted in e["manufacturer"].lower()]
    if equipment_type:
        entries = [e for e in entries if e["equipment_type"] == equipment_type]
    if supported_only:
        entries = [e for e in entries if e["supported"]]

    return {
        "count": len(entries),
        "models": entries,
        "categories": {**CATEGORY_LABELS, **rigol_registry.category_labels()},
    }


@router.get("/models/{model}")
async def describe_model(model: str):
    """Resolve a model or SKU string to its family and interface facts.

    Accepts what an instrument actually reports — a SKU (`9241`), a variant
    (`2569B-MSO`), a hyphenated part number (`HVL-1000-25`) or a full
    `B&K Precision 9130B` string — and returns the family it belongs to.
    """
    info = resolve_model(model)
    if info is None:
        rigol_entry = rigol_registry.resolve_model(model)
        if rigol_entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"No B&K Precision or Rigol family matches model {model!r}",
            )
        return {"query": model, **rigol_entry}

    entry = next(e for e in catalog() if e["key"] == info.key)
    return {"query": model, **entry}


class USBDiagnosticsRequest(BaseModel):
    """Request to run USB diagnostics."""

    resource_string: str


@router.post("/diagnostics/usb")
async def run_usb_diagnostics(request: USBDiagnosticsRequest):
    """
    Run USB diagnostics on a device to troubleshoot connection issues.

    Helps identify why USB serial numbers may be unreadable and provides
    recommendations for resolving the issue.
    """
    try:
        from server.utils.usb_diagnostics import diagnose_usb_device

        diagnostics = diagnose_usb_device(request.resource_string)
        logger.info(f"USB diagnostics run for {request.resource_string}")

        return diagnostics
    except Exception as e:
        logger.error(f"Error running USB diagnostics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect", response_model=dict)
async def connect_device(request: ConnectDeviceRequest):
    """Connect to a device."""
    try:
        equipment_id = await equipment_manager.connect_device(
            request.resource_string,
            request.equipment_type,
            request.model,
        )
        return {"equipment_id": equipment_id, "status": "connected"}
    except Exception as e:
        logger.error(f"Error connecting device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect/{equipment_id}")
async def disconnect_device(
    equipment_id: str,
    session_id: Optional[str] = None,
    on_disconnect: Optional[str] = None,
):
    """Disconnect a device, leaving it in the state the operator chooses.

    **This can switch off a live output, and by default it does.** LabLink
    sends the off command itself, in `EquipmentManager.disconnect_device`,
    when `safe_state_on_disconnect` is set -- which is the default.

    - `on_disconnect=off` disables the output before closing the transport
    - `on_disconnect=hold` leaves the instrument exactly as it is
    - omitted: the server's configured default

    "hold" means LabLink sends nothing; it is not a guarantee about the
    instrument, since a serial port with `hupcl` set may drop DTR on close
    regardless. See issue #198, whose original diagnosis blamed that close for
    behaviour LabLink was in fact commanding.
    """
    try:
        # Release locks for this equipment
        if settings.enable_equipment_locks and session_id:
            try:
                await lock_manager.release_lock(equipment_id, session_id, force=False)
            except Exception as e:
                logger.warning(f"Error releasing lock during disconnect: {e}")

        try:
            await equipment_manager.disconnect_device(equipment_id, on_disconnect)
        except ValueError as e:
            # An unknown policy is the caller's mistake, not a server fault --
            # and silently falling back to the default would turn an output
            # off for someone who asked for it to stay on.
            raise HTTPException(status_code=400, detail=str(e))

        applied = on_disconnect or equipment_manager.default_disconnect_policy()
        return {
            "equipment_id": equipment_id,
            "status": "disconnected",
            "on_disconnect": applied,
        }
    except HTTPException:
        # Re-raise rather than let the handler below wrap it: without this, a
        # rejected policy came back as `500 {"detail": "400: Unknown disconnect
        # policy ..."}` -- the right message inside the wrong status, which a
        # client cannot distinguish from the server having fallen over.
        raise
    except Exception as e:
        logger.error(f"Error disconnecting device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{equipment_id}")
async def forget_device(equipment_id: str):
    """Remove a remembered instrument from the register.

    Disconnecting closes the port; this drops the entry. Without it the list
    only grows -- a scope moved from USB to LAN appears twice, because the id
    is derived from the resource string, and the stale one can never be
    cleared. Refused while the instrument is open, so this cannot strand a
    live session.
    """
    try:
        removed = await equipment_manager.forget_device(equipment_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"{equipment_id} is not in the register"
        )
    return {"equipment_id": equipment_id, "status": "removed"}


@router.get("/list", response_model=List[EquipmentInfo])
async def list_devices():
    """List all connected devices."""
    try:
        devices = await equipment_manager.get_connected_devices()
        return devices
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}/status", response_model=EquipmentStatus)
async def get_device_status(equipment_id: str):
    """Get status of a specific device."""
    try:
        status = await equipment_manager.get_device_status(equipment_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{equipment_id}/readings")
async def get_device_readings(equipment_id: str):
    """Get current readings from a device."""
    try:
        # Debug logging
        all_equipment_ids = list(equipment_manager.equipment.keys())
        logger.info(f"Getting readings for equipment_id: {equipment_id}")
        logger.info(f"Available equipment IDs: {all_equipment_ids}")

        equipment = equipment_manager.get_equipment(equipment_id)
        if equipment is None:
            logger.error(f"Equipment {equipment_id} not found in manager. Available: {all_equipment_ids}")
            raise HTTPException(
                status_code=404,
                detail=f"Device {equipment_id} not found. Available: {all_equipment_ids}"
            )

        # Get readings from the equipment
        if hasattr(equipment, 'get_readings'):
            readings = await equipment.get_readings()
            # Convert to dict for JSON response
            if hasattr(readings, 'dict'):
                return readings.dict()
            elif hasattr(readings, '__dict__'):
                return readings.__dict__
            else:
                return {"data": str(readings)}
        else:
            raise HTTPException(
                status_code=501,
                detail=f"Equipment type {equipment.__class__.__name__} does not support readings"
            )
    except HTTPException:
        raise
    except InstrumentBusy as e:
        # Not a failure of this request: the instrument has a backlog. Say so
        # with a status the client can back off on instead of a 500 it retries.
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting device readings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{equipment_id}/command", response_model=CommandResponse)
async def execute_command(equipment_id: str, command: Command):
    """Execute a command on a device."""
    try:
        equipment = equipment_manager.get_equipment(equipment_id)
        if equipment is None:
            raise HTTPException(status_code=404, detail="Device not found")

        # Check lock requirements if enabled
        if settings.enable_equipment_locks:
            is_control_command = requires_control(command.action)

            if is_control_command:
                # Control commands require exclusive lock
                if not command.session_id:
                    raise HTTPException(
                        status_code=401,
                        detail="session_id required for control commands when locks are enabled",
                    )

                if not lock_manager.can_control_equipment(
                    equipment_id, command.session_id
                ):
                    raise HTTPException(
                        status_code=403,
                        detail=_why_control_was_refused(
                            equipment_id, command.session_id
                        ),
                    )

                # Update lock activity
                lock_manager.update_lock_activity(equipment_id, command.session_id)

            else:
                # A read is never refused. A lock is a claim on changing an
                # instrument, not on looking at one -- the panels put it
                # that way themselves: "not holding the lock means you
                # cannot change the instrument, not that you cannot watch
                # it" -- and GET /readings has never consulted a lock at
                # all. Only reads that come through this endpoint did,
                # which made get_setpoints the odd one out.
                #
                # On the bench that meant a second session holding a lock
                # blanked the setpoints for everyone else, and a client
                # restart was enough to create one: every restart mints a
                # new session id and the old lock lives on until it times
                # out. The operator could see the instrument's readings
                # while being told nothing about what it was set to.
                #
                # Control still requires the lock; that is the branch
                # above, and it is unchanged.
                if command.session_id:
                    # Keeps a genuine holder's lock alive while they are
                    # using the instrument, which is what this call is for.
                    lock_manager.update_lock_activity(equipment_id, command.session_id)

        result = await equipment.execute_command(command.action, command.parameters)

        return CommandResponse(
            command_id=command.command_id,
            success=True,
            data=result,
        )
    except HTTPException:
        raise
    except InstrumentBusy as e:
        raise HTTPException(status_code=503, detail=str(e))
    except SetpointRefused as e:
        # Not a fault. The operator asked for a value the instrument
        # cannot take and was told so; nothing is broken and the next
        # request will work. Logged at INFO because scrolling a dial
        # past a floor produces one of these per notch, and a log where
        # routine operation writes ERROR is one where a real error is
        # easy to miss -- which cost real time on this bench once.
        logger.info(f"Setpoint refused: {e}")
        return CommandResponse(
            command_id=command.command_id,
            success=False,
            error=str(e),
        )
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return CommandResponse(
            command_id=command.command_id,
            success=False,
            error=str(e),
        )
