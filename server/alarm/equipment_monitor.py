"""
Equipment-Alarm Integration Module
===================================

Connects equipment readings to alarm monitoring for automatic alarm triggering.

This module bridges the gap between the equipment manager and alarm manager,
enabling alarms to automatically trigger based on equipment status changes.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Set

from shared.models.equipment import EquipmentStatus

logger = logging.getLogger(__name__)


class EquipmentAlarmIntegrator:
    """
    Integrates equipment monitoring with alarm system.

    This class monitors equipment status changes and automatically checks
    relevant alarms, triggering notifications when conditions are met.
    """

    def __init__(self, equipment_manager, alarm_manager):
        """
        Initialize the integrator.

        Args:
            equipment_manager: Equipment manager instance
            alarm_manager: Alarm manager instance
        """
        self.equipment_manager = equipment_manager
        self.alarm_manager = alarm_manager
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._last_check: Dict[str, datetime] = {}
        self._check_interval = 1.0  # Check every 1 second
        self._running = False

        logger.info("Equipment-Alarm integrator initialized")

    async def start_monitoring(self):
        """Start monitoring all equipment for alarm conditions."""
        if self._running:
            logger.warning("Monitoring already running")
            return

        self._running = True
        logger.info("Starting equipment-alarm monitoring")

        # Start monitoring task for each connected equipment
        for equipment_id in self.equipment_manager.equipment.keys():
            await self._start_equipment_monitoring(equipment_id)

    async def stop_monitoring(self):
        """Stop all equipment monitoring."""
        self._running = False
        logger.info("Stopping equipment-alarm monitoring")

        # Cancel all monitoring tasks
        for equipment_id, task in list(self._monitoring_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._monitoring_tasks.clear()

    async def _start_equipment_monitoring(self, equipment_id: str):
        """Start monitoring a specific equipment."""
        if equipment_id in self._monitoring_tasks:
            return

        task = asyncio.create_task(self._monitor_equipment(equipment_id))
        self._monitoring_tasks[equipment_id] = task
        logger.debug(f"Started monitoring for equipment: {equipment_id}")

    async def _stop_equipment_monitoring(self, equipment_id: str):
        """Stop monitoring a specific equipment."""
        if equipment_id not in self._monitoring_tasks:
            return

        task = self._monitoring_tasks[equipment_id]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        del self._monitoring_tasks[equipment_id]
        logger.debug(f"Stopped monitoring for equipment: {equipment_id}")

    async def _monitor_equipment(self, equipment_id: str):
        """Monitor equipment and check alarms."""
        try:
            while self._running:
                try:
                    # Get equipment status
                    status = await self.equipment_manager.get_device_status(
                        equipment_id
                    )

                    if status:
                        # Check alarms for this equipment
                        await self._check_equipment_alarms(equipment_id, status)

                    # Wait before next check
                    await asyncio.sleep(self._check_interval)

                except Exception as e:
                    logger.error(f"Error monitoring equipment {equipment_id}: {e}")
                    await asyncio.sleep(self._check_interval)

        except asyncio.CancelledError:
            logger.debug(f"Monitoring cancelled for equipment {equipment_id}")

    async def _check_equipment_alarms(self, equipment_id: str, status: EquipmentStatus):
        """
        Check all alarms relevant to this equipment.

        Args:
            equipment_id: Equipment identifier
            status: Current equipment status
        """
        # Get all alarms for this equipment
        alarms = await self.alarm_manager.list_alarms()
        equipment_alarms = [
            alarm
            for alarm in alarms
            if alarm.equipment_id == equipment_id and alarm.enabled
        ]

        if not equipment_alarms:
            return

        # Extract readings from status
        readings = self._extract_readings(status)

        # Check each alarm
        for alarm in equipment_alarms:
            parameter = alarm.parameter.lower()

            if parameter in readings:
                value = readings[parameter]

                # Check the alarm condition
                try:
                    await self.alarm_manager.check_alarm(alarm.alarm_id, value)
                except Exception as e:
                    logger.error(f"Error checking alarm {alarm.alarm_id}: {e}")

    def _extract_readings(self, status: EquipmentStatus) -> Dict[str, float]:
        """
        Extract numeric readings from equipment status.

        Args:
            status: Equipment status

        Returns:
            Dictionary of parameter name to value
        """
        readings = {}

        # Extract common parameters
        if hasattr(status, "voltage") and status.voltage is not None:
            readings["voltage"] = float(status.voltage)
            readings["v"] = float(status.voltage)
            readings["volt"] = float(status.voltage)

        if hasattr(status, "current") and status.current is not None:
            readings["current"] = float(status.current)
            readings["i"] = float(status.current)
            readings["amp"] = float(status.current)

        if hasattr(status, "power") and status.power is not None:
            readings["power"] = float(status.power)
            readings["p"] = float(status.power)
            readings["watt"] = float(status.power)

        if hasattr(status, "temperature") and status.temperature is not None:
            readings["temperature"] = float(status.temperature)
            readings["temp"] = float(status.temperature)
            readings["t"] = float(status.temperature)

        # Extract custom parameters from status_info dict
        if hasattr(status, "status_info") and isinstance(status.status_info, dict):
            for key, value in status.status_info.items():
                if isinstance(value, (int, float)):
                    readings[key.lower()] = float(value)

        return readings

    async def on_equipment_connected(self, equipment_id: str):
        """
        Called when equipment is connected.

        Args:
            equipment_id: Equipment identifier
        """
        if self._running:
            await self._start_equipment_monitoring(equipment_id)
            logger.info(
                f"Started alarm monitoring for connected equipment: {equipment_id}"
            )

    async def on_equipment_disconnected(self, equipment_id: str):
        """
        Called when equipment is disconnected.

        Args:
            equipment_id: Equipment identifier
        """
        await self._stop_equipment_monitoring(equipment_id)

        # Clear any active alarms for this equipment
        alarms = await self.alarm_manager.list_alarms()
        for alarm in alarms:
            if alarm.equipment_id == equipment_id:
                await self.alarm_manager.clear_alarm(alarm.alarm_id)

        logger.info(
            f"Stopped alarm monitoring for disconnected equipment: {equipment_id}"
        )

    async def check_equipment_now(self, equipment_id: str):
        """
        Immediately check alarms for specific equipment.

        Args:
            equipment_id: Equipment identifier
        """
        try:
            status = await self.equipment_manager.get_device_status(equipment_id)
            if status:
                await self._check_equipment_alarms(equipment_id, status)
                logger.debug(f"Manual alarm check completed for {equipment_id}")
        except Exception as e:
            logger.error(f"Error in manual alarm check for {equipment_id}: {e}")

    def set_check_interval(self, interval: float):
        """
        Set the monitoring check interval.

        Args:
            interval: Interval in seconds (minimum 0.1)
        """
        self._check_interval = max(0.1, interval)
        logger.info(f"Check interval set to {self._check_interval}s")

    async def get_monitoring_status(self) -> Dict:
        """
        Get current monitoring status.

        Returns:
            Dictionary with monitoring status information
        """
        return {
            "running": self._running,
            "monitored_equipment": list(self._monitoring_tasks.keys()),
            "check_interval": self._check_interval,
            "active_tasks": len(self._monitoring_tasks),
        }


# Global integrator instance (initialized in main.py)
equipment_alarm_integrator: Optional[EquipmentAlarmIntegrator] = None


def get_integrator() -> Optional[EquipmentAlarmIntegrator]:
    """Get the global equipment-alarm integrator instance."""
    return equipment_alarm_integrator


def initialize_integrator(equipment_manager, alarm_manager) -> EquipmentAlarmIntegrator:
    """
    Initialize the global equipment-alarm integrator.

    Args:
        equipment_manager: Equipment manager instance
        alarm_manager: Alarm manager instance

    Returns:
        Initialized integrator instance
    """
    global equipment_alarm_integrator
    equipment_alarm_integrator = EquipmentAlarmIntegrator(
        equipment_manager, alarm_manager
    )
    return equipment_alarm_integrator
