# WebSocket Integration Plan - LabLink GUI

## Current Status

### ✅ Completed Infrastructure
- **WebSocket Manager** (`/home/x9x0/LabLink/client/utils/websocket_manager.py` - 496 lines)
  - Full async WebSocket client implementation
  - Auto-reconnect capability with configurable delay
  - Message type routing and callback system
  - Equipment and acquisition data streaming
  - Connection state management and statistics

- **Client API Integration** (`/home/x9x0/LabLink/client/api/client.py:74-222`)
  - WebSocket manager initialization in LabLinkClient
  - Async wrapper methods for all streaming operations
  - Handler registration convenience methods

### 🔧 Integration Required

The WebSocket manager exists but is not integrated into the GUI panels. All panels currently use polling (auto-refresh timers).

---

## Integration Architecture

### Approach: Hybrid Polling + WebSocket

**Rationale**: Start with optional WebSocket for real-time updates while keeping polling as fallback.

```
┌─────────────────┐
│   GUI Panel     │
│                 │
│ ┌─────────────┐ │
│ │ Auto-Refresh│ │ ← Polling (current, keeps working)
│ │   Timer     │ │
│ └─────────────┘ │
│                 │
│ ┌─────────────┐ │
│ │  WebSocket  │ │ ← Real-time (new, optional)
│ │   Handler   │ │
│ └─────────────┘ │
└─────────────────┘
         │
         ├─→ REST API (existing)
         └─→ WebSocket (new)
```

---

## Panel-by-Panel Integration Plan

### Phase 1: Equipment Panel (Highest Priority)

**Why**: Most time-sensitive data (live instrument readings)

**WebSocket Events to Handle**:
- `STREAM_DATA` - Real-time equipment readings
- `STREAM_STARTED` / `STREAM_STOPPED` - Stream status

**Changes Needed**:
1. Add WebSocket connection toggle button
2. Register stream data handler when equipment connected
3. Update readings display on stream data messages
4. Stop polling when WebSocket active, resume on disconnect

**Files to Modify**:
- `/home/x9x0/LabLink/client/ui/equipment_panel.py`

**Estimated Effort**: 2-3 hours

---

### Phase 2: Data Acquisition Panel (High Priority)

**Why**: Real-time plot updates are crucial for data acquisition

**WebSocket Events to Handle**:
- `ACQUISITION_STREAM` - Real-time acquisition data points
- `ACQUISITION_STREAM_STARTED` / `ACQUISITION_STREAM_STOPPED` - Stream status

**Changes Needed**:
1. Enable WebSocket streaming for active acquisitions
2. Update plots in real-time with incoming data
3. Maintain circular buffer for plot data
4. Add stream quality indicators (data rate, latency)

**Files to Modify**:
- `/home/x9x0/LabLink/client/ui/acquisition_panel.py`

**Estimated Effort**: 3-4 hours

---

### Phase 3: Alarm Panel (Medium Priority)

**Why**: Real-time alarm notifications

**WebSocket Events to Handle**:
- Custom alarm events (need server-side implementation)
- Alarm state changes
- New alarm events

**Changes Needed**:
1. Register for alarm event notifications
2. Update active alarms list in real-time
3. Show desktop notifications for critical alarms
4. Reduce polling frequency when WebSocket active

**Files to Modify**:
- `/home/x9x0/LabLink/client/ui/alarm_panel.py`

**Server-Side Needed**:
- Alarm event broadcasting via WebSocket (NEW)

**Estimated Effort**: 3-4 hours

---

### Phase 4: Diagnostics Panel (Lower Priority)

**Why**: Health data changes slowly, polling is acceptable

**WebSocket Events to Handle**:
- Equipment health change notifications
- Diagnostic test completion events

**Changes Needed**:
1. Real-time health score updates
2. Notify when health degrades
3. Stream benchmark progress

**Files to Modify**:
- `/home/x9x0/LabLink/client/ui/diagnostics_panel.py`

**Estimated Effort**: 2-3 hours

---

## Implementation Steps

### Step 1: Main Window WebSocket Setup

**Goal**: Central WebSocket management in main window

**Changes**:

```python
# In MainWindow class
def __init__(self):
    ...
    self.ws_connected = False

def connect_to_server(self, host, api_port, ws_port):
    ...
    # After REST API connection succeeds:
    asyncio.create_task(self._connect_websocket())

async def _connect_websocket(self):
    """Connect WebSocket in background."""
    success = await self.client.connect_websocket()
    if success:
        self.ws_connected = True
        self.status_bar.showMessage("WebSocket connected", 3000)
        # Enable WebSocket features in panels
        self._enable_websocket_features()
```

**Files**: `/home/x9x0/LabLink/client/ui/main_window.py`

---

### Step 2: Equipment Panel Real-Time Readings

**Goal**: Stream live equipment data instead of polling

**Pseudocode**:

```python
class EquipmentPanel(QWidget):
    def __init__(self):
        ...
        self.streaming_equipment = set()

    def _on_equipment_connected(self, equipment_id):
        """After equipment connects, start streaming."""
        if self.client.ws_manager and self.client.ws_manager.connected:
            asyncio.create_task(self._start_streaming(equipment_id))

    async def _start_streaming(self, equipment_id):
        """Start real-time data stream."""
        await self.client.start_equipment_stream(
            equipment_id=equipment_id,
            stream_type="readings",
            interval_ms=200  # 5 Hz update rate
        )
        self.streaming_equipment.add(equipment_id)

    def _register_ws_handlers(self):
        """Register WebSocket message handlers."""
        if self.client.ws_manager:
            self.client.ws_manager.on_stream_data(self._handle_stream_data)

    def _handle_stream_data(self, message):
        """Handle incoming stream data."""
        equipment_id = message['equipment_id']
        data = message['data']

        # Update UI (must use Qt signal/slot for thread safety)
        self.update_readings_signal.emit(equipment_id, data)
```

---

### Step 3: Acquisition Panel Real-Time Plotting

**Goal**: Update plots as data arrives instead of polling

**Key Features**:
- Append new data points to plot in real-time
- Maintain configurable plot buffer size
- Auto-scroll plot as new data arrives
- Show streaming status indicator

**Challenges**:
- Thread safety (WebSocket thread → GUI thread)
- Plot performance with high data rates
- Buffer management

**Solution**: Use Qt signals to safely update GUI from WebSocket callbacks

---

## Technical Considerations

### 1. Threading and Qt Event Loop

**Challenge**: WebSocket runs in asyncio event loop, Qt GUI runs in Qt event loop

**Solution**: Use QThread + asyncio bridge OR Qt signals

```python
# Option A: Use Qt signals (simpler)
class WebSocketSignals(QObject):
    stream_data_received = pyqtSignal(str, dict)  # equipment_id, data

# In handler:
def _handle_stream_data(self, message):
    # Emit signal to update GUI thread
    self.signals.stream_data_received.emit(
        message['equipment_id'],
        message['data']
    )
```

---

### 2. Connection Management

**States**:
- Not Connected → Only REST API (polling)
- Connecting → Show progress
- Connected → WebSocket + REST API hybrid
- Connection Lost → Fall back to polling, auto-reconnect

**User Control**:
- Enable/disable WebSocket in settings
- Manual reconnect button
- Connection status indicator in status bar

---

### 3. Error Handling

**Scenarios**:
- WebSocket connection fails → Continue with polling only
- Connection drops during streaming → Auto-reconnect, restart streams
- Message parsing errors → Log and continue
- Handler exceptions → Catch, log, don't crash GUI

---

### 4. Performance Optimization

**For High-Frequency Data**:
- Throttle GUI updates (max 30 FPS)
- Use circular buffers for plot data
- Aggregate multiple data points per frame
- Downsample old data automatically

**For Low-Frequency Data**:
- Keep polling as backup
- WebSocket for instant notifications only
- Hybrid approach reduces server load

---

## Server-Side Requirements

### Already Implemented
- ✅ WebSocket server endpoint (`/ws`)
- ✅ Equipment data streaming
- ✅ Acquisition data streaming
- ✅ Message type routing

### Needs Implementation
- ❌ Alarm event broadcasting
- ❌ Health status change notifications
- ❌ Job scheduler event notifications

---

## Testing Plan

### Unit Tests
1. WebSocket connection/disconnection
2. Message handler registration
3. Stream start/stop
4. Auto-reconnect logic
5. Error recovery

### Integration Tests
1. Connect to real server
2. Stream equipment data
3. Stream acquisition data
4. Handle server restart
5. Multiple simultaneous streams

### GUI Tests
1. Enable/disable WebSocket from UI
2. Verify real-time updates appear
3. Test fallback to polling when disconnected
4. Monitor performance with multiple streams

---

## Migration Path

### Phase 1: Optional WebSocket (RECOMMENDED START)
- WebSocket is opt-in feature
- Polling continues as default
- Users can enable in settings
- Easy rollback if issues

### Phase 2: Hybrid Default
- WebSocket enabled by default
- Polling as fallback
- Transparent to user

### Phase 3: WebSocket Primary
- Polling only for initial load
- WebSocket for all real-time data
- Deprecate heavy polling

---

## Estimated Timeline

| Phase | Task | Estimated Time |
|-------|------|----------------|
| 1 | Main window WebSocket setup | 2 hours |
| 2 | Equipment panel integration | 3 hours |
| 3 | Acquisition panel integration | 4 hours |
| 4 | Alarm panel integration | 3 hours |
| 5 | Diagnostics panel integration | 2 hours |
| 6 | Testing and bug fixes | 4 hours |
| **Total** | **Full integration** | **18-20 hours** |

---

## Success Criteria

### Minimal
- ✅ Equipment panel shows real-time readings via WebSocket
- ✅ Graceful fallback to polling when WebSocket unavailable
- ✅ No regression in existing functionality

### Complete
- ✅ All panels support WebSocket streaming
- ✅ < 100ms latency for equipment readings
- ✅ Automatic reconnection works reliably
- ✅ Performance with 10+ simultaneous streams

---

## Next Immediate Actions

1. **Start with Equipment Panel** - Highest value, lowest risk
2. **Add WebSocket toggle to main window** - User control
3. **Implement signal/slot bridge** - Thread safety
4. **Test with real equipment** - Validate approach

---

*Last Updated: 2025-11-10*
*Status: Ready for implementation*
