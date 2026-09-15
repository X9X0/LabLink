"""The Control tab: an equipment list, a lock strip, and a panel per instrument.

This used to hold every power-supply control as well, and drove everything
as if it were a supply -- a scope was shown voltage and current dials it has
no concept of, and was polled for readings it could not give until the event
loop starved. The controls now live in ``client/ui/instruments``; this shell
only chooses which panel to show and hands it the instrument and the
connection it lives on.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Type

import qasync
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QPushButton, QSplitter, QStackedWidget,
                             QVBoxLayout, QWidget)

from client.api.client import LabLinkClient, call_blocking
from client.models.equipment import ConnectionStatus, Equipment
from client.ui.instruments.base import InstrumentPanel
from client.ui.instruments.registry import panel_class_for
# Re-exported: these lived here before the extraction and are imported from
# here by tests and by anything else that drew a reading.
from client.ui.instruments.widgets import (AnalogGauge,  # noqa: F401
                                           ChartWithReadouts, FittedReadout)
from client.utils.inflight import (REFRESH_ABANDONED_AFTER, claim_slot,
                                   release_slot)
from client.utils.server_manager import get_server_manager

logger = logging.getLogger(__name__)


class ControlPanel(QWidget):
    """Equipment list on the left, the selected instrument's panel on the right."""

    equipment_selected = pyqtSignal(str)
    # Something the user needs told about, shown in the main window's status
    # bar. Currently: control of an instrument passing to somebody else, and
    # a panel explaining why its readouts are blank.
    status_message = pyqtSignal(str)

    def __init__(self, client: Optional[LabLinkClient] = None, parent=None):
        super().__init__(parent)
        self.client = client
        self.selected_equipment: Optional[Equipment] = None
        self.equipment_list: List[Equipment] = []
        #: When the in-flight list fan-out started, or None. See
        #: client/utils/inflight.py for why this is a time, not a flag.
        self._list_refresh_started_at = None

        #: One panel instance per panel class, created when first needed and
        #: kept, so switching between two supplies keeps the graph history.
        self._panels: Dict[Type[InstrumentPanel], InstrumentPanel] = {}
        self.current_panel: Optional[InstrumentPanel] = None

        # Lock state changes without us doing anything: it counts down,
        # someone else can take or release it, and it can expire. Polled
        # slowly -- a server-side query, not a serial one.
        self.lock_timer = QTimer(self)
        self.lock_timer.timeout.connect(self._poll_lock_status)
        self._lock_poll_in_flight = False
        self._had_control = False

        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_equipment_list_panel())
        splitter.addWidget(self._create_instrument_area())
        splitter.setSizes([200, 800])
        main_layout.addWidget(splitter)

    def _create_equipment_list_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("<h3>Connected Equipment</h3>"))
        self.equipment_list_widget = QListWidget()
        self.equipment_list_widget.itemClicked.connect(self._on_equipment_selected)
        layout.addWidget(self.equipment_list_widget)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_equipment_list)
        layout.addWidget(refresh_btn)
        return panel

    def _create_instrument_area(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.equipment_info_label = QLabel("No equipment selected")
        self.equipment_info_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.equipment_info_label)

        # Who holds this instrument. Always on screen, because "why will it
        # not let me set anything" is otherwise unanswerable from the UI.
        from client.ui.equipment_lock_dialog import LockStatusWidget

        lock_row = QHBoxLayout()
        self.lock_status_widget = LockStatusWidget()
        lock_row.addWidget(self.lock_status_widget)
        lock_row.addStretch()
        self.manage_lock_button = QPushButton("Manage lock…")
        self.manage_lock_button.clicked.connect(self._show_lock_dialog)
        self.manage_lock_button.setEnabled(False)
        lock_row.addWidget(self.manage_lock_button)
        layout.addLayout(lock_row)

        # One page per instrument panel; page 0 is the empty state.
        self.panel_stack = QStackedWidget()
        self.empty_page = QLabel("Select an instrument to control it.")
        self.empty_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.panel_stack.addWidget(self.empty_page)
        layout.addWidget(self.panel_stack, 1)
        return panel

    # ------------------------------------------------------------------ #
    # Panels
    # ------------------------------------------------------------------ #

    def panel_for(self, equipment) -> InstrumentPanel:
        """The (cached) panel instance that drives this kind of instrument."""
        panel_class = panel_class_for(getattr(equipment, "equipment_type", None))
        panel = self._panels.get(panel_class)
        if panel is None:
            panel = panel_class()
            panel.status_message.connect(self.status_message)
            panel.equipment_gone.connect(self._on_equipment_gone)
            self._panels[panel_class] = panel
            self.panel_stack.addWidget(panel)
        return panel

    def _show_panel(self, panel: Optional[InstrumentPanel]):
        """Make one panel current: stop the old one, show the new one."""
        if self.current_panel is not None and self.current_panel is not panel:
            self.current_panel.stop()
        self.current_panel = panel
        self.panel_stack.setCurrentWidget(panel if panel is not None else self.empty_page)

    def _on_equipment_gone(self, equipment_id: str):
        """A panel found its instrument gone (404): the list is stale."""
        if self.selected_equipment is not None and self.selected_equipment.equipment_id == equipment_id:
            try:
                self.selected_equipment.connection_status = ConnectionStatus.DISCONNECTED
            except Exception:
                pass
        self.refresh_equipment_list()

    def _set_controls_enabled(self, enabled: bool):
        """Gate the current panel's command widgets; readings stay live."""
        if self.current_panel is not None:
            self.current_panel.set_controls_enabled(enabled)

    # ------------------------------------------------------------------ #
    # Selection
    # ------------------------------------------------------------------ #

    def _on_equipment_selected(self):
        selected_items = self.equipment_list_widget.selectedItems()
        if not selected_items:
            self._deselect()
            return

        key = selected_items[0].data(Qt.ItemDataRole.UserRole)

        # Release the lock on what was selected before -- on its own server,
        # which is not necessarily the one holding the new selection.
        previous = self.selected_equipment
        if previous is not None and previous.key != key:
            previous_client = self._client_for(previous)
            if previous_client:
                try:
                    previous_client.release_lock(previous.equipment_id)
                    logger.info(f"Released lock on {previous.equipment_id}")
                except Exception as e:
                    logger.error(f"Error releasing lock: {e}")

        # Matched on the composite key: two servers can each mint the same
        # equipment id.
        equipment = next((eq for eq in self.equipment_list if eq.key == key), None)
        if equipment is None:
            logger.warning(f"Selected row {key!r} matches no known instrument")
            return

        client = self._client_for(equipment)
        self.selected_equipment = equipment
        self.equipment_info_label.setText(
            f"{equipment.name} - {equipment.manufacturer} {equipment.model}"
        )

        panel = self.panel_for(equipment)
        self._show_panel(panel)
        # Binds the instrument and ranges the controls from its capabilities
        # -- what the shell itself used to do for supplies only.
        panel.set_instrument(equipment, client)

        # Take the lock for control, without taking it from anyone. Overriding
        # is a deliberate act in the lock dialog, with the holder named.
        if client:
            try:
                status = client.get_lock_status(equipment.equipment_id)
            except Exception as e:
                logger.error(f"Could not read lock status: {e}")
                status = {}

            if status.get("locked") and not client.holds_lock(status):
                from client.ui.equipment_lock_dialog import describe_holder

                logger.info(f"{equipment.equipment_id} is locked by {describe_holder(status)}; read-only")
                self._set_controls_enabled(False)
            else:
                try:
                    client.acquire_lock(equipment.equipment_id, lock_mode="exclusive")
                    logger.info(f"Acquired exclusive lock on {equipment.equipment_id}")
                    self._set_controls_enabled(True)
                except Exception as e:
                    logger.error(f"Error acquiring lock: {e}")
                    self._set_controls_enabled(False)
            self._refresh_lock_status()

        self.equipment_selected.emit(equipment.equipment_id)
        self._start_data_acquisition()

    def _deselect(self):
        if self.selected_equipment and self._selected_client():
            try:
                self._selected_client().release_lock(self.selected_equipment.equipment_id)
                logger.info(f"Released lock on {self.selected_equipment.equipment_id}")
            except Exception as e:
                logger.error(f"Error releasing lock: {e}")
        self.selected_equipment = None
        self._stop_data_acquisition()
        if self.current_panel is not None:
            self.current_panel.set_instrument(None, None)
        self._show_panel(None)
        self.equipment_info_label.setText("No equipment selected")
        # Clear the strip too, or it keeps naming a lock on equipment that is
        # no longer selected.
        self._apply_lock_status(None)

    def _start_data_acquisition(self):
        """Start the current panel polling, and the slow lock poll."""
        if self.selected_equipment is None:
            return
        if self.current_panel is not None:
            self.current_panel.start()
        # Slower than the readings on purpose: a server query, not a serial
        # one, and the countdown only has to look alive.
        self.lock_timer.start(5000)

    def _stop_data_acquisition(self):
        if self.current_panel is not None:
            self.current_panel.stop()
        self.lock_timer.stop()

    # ------------------------------------------------------------------ #
    # Locks
    # ------------------------------------------------------------------ #

    def _apply_lock_status(self, status: Optional[dict]):
        """Render a lock status and gate the controls to match."""
        if status is None:
            self.lock_status_widget.update_status(None)
            self.manage_lock_button.setEnabled(False)
            self._had_control = False
            return

        # Judged by the connection that holds the instrument, not the active
        # one: every server connection has a different session, so asking the
        # wrong client always answers "someone else has it".
        client = self._selected_client()
        mine = bool(client) and client.holds_lock(status)
        self.lock_status_widget.update_status(status, is_mine=mine)
        self.manage_lock_button.setEnabled(True)
        self._set_controls_enabled(mine)

        # Say so when control is taken away mid-session.
        if self._had_control and not mine:
            from client.ui.equipment_lock_dialog import describe_holder

            holder = describe_holder(status) if status.get("locked") else "no one - it expired"
            self.status_message.emit(f"Control of this instrument has passed to {holder}")
            logger.warning(f"Lost the lock on the selected equipment to {holder}")
        self._had_control = mine

    @qasync.asyncSlot()
    async def _poll_lock_status(self):
        """Re-read the lock off the GUI thread."""
        client = self._selected_client()
        if not (client and self.selected_equipment) or self._lock_poll_in_flight:
            return
        self._lock_poll_in_flight = True
        try:
            status = await call_blocking(client.get_lock_status, self.selected_equipment.equipment_id)
            self._apply_lock_status(status)
        except Exception as exc:
            logger.debug(f"Could not read lock status: {exc}")
        finally:
            self._lock_poll_in_flight = False

    def _refresh_lock_status(self):
        """Ask for a lock refresh now, without blocking the caller."""
        if not (self._selected_client() and self.selected_equipment):
            self._apply_lock_status(None)
            return
        self._poll_lock_status()

    def _show_lock_dialog(self):
        client = self._selected_client()
        if not (client and self.selected_equipment):
            return
        from client.ui.equipment_lock_dialog import EquipmentLockDialog

        dialog = EquipmentLockDialog(
            client, self.selected_equipment.equipment_id,
            getattr(self.selected_equipment, "name", ""), self,
        )
        dialog.exec()
        # The dialog may have taken or given up control.
        self._refresh_lock_status()
        try:
            status = client.get_lock_status(self.selected_equipment.equipment_id)
            self._set_controls_enabled(client.holds_lock(status))
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Equipment list
    # ------------------------------------------------------------------ #

    @qasync.asyncSlot()
    async def refresh_equipment_list(self):
        """Refresh the equipment list from every connected server."""
        connections = self._connections()
        if not connections:
            return
        # Skip this tick if the last fan-out has not come back yet -- unless
        # it has been out so long that it is not coming back.
        if not claim_slot(self, "_list_refresh_started_at", REFRESH_ABANDONED_AFTER):
            return
        try:
            await self._refresh_list_from(connections)
        finally:
            release_slot(self, "_list_refresh_started_at")

    async def _refresh_list_from(self, connections):
        """Merge the equipment lists of every given server."""
        results = await asyncio.gather(*(
            self._list_equipment_from(name, client) for name, client in connections.items()
        ))

        gathered = []
        unreachable = []
        for server_name, listed, error in results:
            if error is not None:
                # One server being unreachable must not empty the list for
                # the rest.
                logger.warning(f"Could not list equipment on {server_name}: {error}")
                unreachable.append(server_name or "server")
                continue
            gathered.extend(Equipment.from_api_dict(eq, server_name) for eq in listed)
        self.equipment_list = gathered

        selected_key = self.selected_equipment.key if self.selected_equipment else None
        servers = {eq.server_name for eq in self.equipment_list if eq.server_name}
        show_server = len(servers) > 1

        self.equipment_list_widget.clear()
        for equipment in self.equipment_list:
            if equipment.connection_status == ConnectionStatus.CONNECTED:
                text = f"{equipment.name} ({equipment.equipment_type.value})"
                if show_server and equipment.server_name:
                    text = f"{text} — {equipment.server_name}"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, equipment.key)
                self.equipment_list_widget.addItem(item)
                if equipment.key == selected_key:
                    self.equipment_list_widget.setCurrentItem(item)
        self.equipment_list_widget.setToolTip(
            f"Could not reach: {', '.join(unreachable)}" if unreachable else ""
        )

    async def _list_equipment_from(self, server_name, client):
        """List one server's instruments, reporting rather than raising."""
        try:
            return server_name, await call_blocking(client.list_equipment), None
        except Exception as e:
            return server_name, [], e

    def showEvent(self, event):
        """Bring the list up to date whenever this tab comes to the front."""
        super().showEvent(event)
        if self._connections():
            self.refresh_equipment_list()

    def set_client(self, client: LabLinkClient):
        """Set the active server's API client."""
        self.client = client
        self.refresh_equipment_list()

    # ------------------------------------------------------------------ #
    # Which connection an instrument lives on
    # ------------------------------------------------------------------ #

    def _connections(self):
        """Every server to list instruments from, keyed by name.

        Falls back to the single active client when the registry is empty,
        which is the case before a server is registered and in tests that
        construct the panel directly.
        """
        try:
            clients = get_server_manager().connected_clients()
        except Exception as e:
            logger.warning(f"Could not read the server registry: {e}")
            clients = {}
        if clients:
            return clients
        return {None: self.client} if self.client else {}

    def _client_for(self, equipment):
        """The connection that holds a given instrument.

        Every reading, setpoint and lock call has to go to the server the
        instrument is actually on, not whichever is selected in the dropdown.
        """
        if equipment is None or equipment.server_name is None:
            return self.client
        return get_server_manager().get_client(equipment.server_name) or self.client

    def _selected_client(self):
        return self._client_for(self.selected_equipment)
