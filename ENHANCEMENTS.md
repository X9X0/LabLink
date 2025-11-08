# LabLink Server Enhancements v0.2.0

This document describes the three major enhancements implemented in LabLink Server v0.2.0.

## Summary

Three comprehensive server enhancements have been implemented:

1. **Configuration Management System** - 50+ configurable settings with validation
2. **Error Handling & Recovery** - Auto-reconnect, health monitoring, and retry logic
3. **Equipment Profile System** - Save/load equipment configurations

## Enhancement 1: Configuration Management System

### Overview
A comprehensive configuration system built on Pydantic with automatic validation, clear documentation, and helpful error messages.

### Features

- **50+ Configuration Options** organized into categories:
  - Server Configuration (host, ports, debug mode)
  - Data Storage (directories, formats, compression)
  - Equipment Configuration (timeouts, VISA backend)
  - Error Handling & Recovery (reconnect, retry, health monitoring)
  - Logging (levels, formats, rotation)
  - WebSocket (connections, compression, heartbeat)
  - API (CORS, rate limiting)
  - Security (authentication, TLS)
  - Equipment Profiles (enable/disable, auto-load)

- **Automatic Validation** on server startup
  - Port conflict detection
  - Path verification
  - Security warnings
  - Configuration consistency checks

- **Environment Variable Support**
  - All settings configurable via `.env` file
  - Prefix: `LABLINK_`
  - Example: `LABLINK_API_PORT=8000`

### Files Created/Modified

- `config/settings.py` - Enhanced Pydantic settings class (130 lines)
- `config/validator.py` - Configuration validator (220 lines)
- `.env.example` - Complete configuration template (95 lines)
- `main.py` - Integrated config validation on startup

### Usage

```python
from config.settings import settings

# Access any setting
print(settings.api_port)
print(settings.enable_auto_reconnect)
print(settings.health_check_interval_sec)
```

Validate configuration:
```bash
python3 -c "from config.validator import validate_config; validate_config()"
```

### Configuration Categories

#### Server Configuration
- `host` - Server bind address (default: 0.0.0.0)
- `api_port` - API server port (default: 8000)
- `ws_port` - WebSocket port (default: 8001)
- `debug` - Debug mode (default: false)
- `server_name` - Instance name (default: "LabLink Server")

#### Error Handling & Recovery
- `enable_auto_reconnect` - Auto-reconnect on disconnect (default: true)
- `reconnect_attempts` - Max reconnect attempts (default: 3)
- `reconnect_delay_ms` - Base reconnect delay (default: 1000)
- `reconnect_backoff_multiplier` - Exponential backoff (default: 2.0)
- `enable_health_monitoring` - Periodic health checks (default: true)
- `health_check_interval_sec` - Check interval (default: 30)
- `enable_command_retry` - Retry failed commands (default: true)
- `max_command_retries` - Max retry attempts (default: 2)
- `retry_delay_ms` - Retry delay (default: 500)

#### Equipment Profiles
- `enable_profiles` - Enable profile system (default: true)
- `auto_load_profiles` - Auto-load on connect (default: true)
- `profile_format` - Storage format (default: json)
- `profile_dir` - Profile storage directory (default: ./profiles)

See `.env.example` for complete list of all 50+ configuration options.

---

## Enhancement 2: Error Handling & Recovery System

### Overview
A robust error handling system with automatic reconnection, equipment health monitoring, and command retry logic with exponential backoff.

### Features

#### 1. Automatic Reconnection
- Detects equipment disconnections
- Attempts reconnection with exponential backoff
- Configurable retry attempts and delays
- Logs all reconnection attempts

**Example:**
```python
# Automatic reconnection triggered on disconnect
# Attempt 1: delay 1000ms
# Attempt 2: delay 2000ms
# Attempt 3: delay 4000ms
```

#### 2. Health Monitoring
- Periodic equipment health checks
- Automatic recovery on failure
- Background monitoring task
- Configurable check interval

**Features:**
- Runs in background (async task)
- Checks all connected equipment
- Triggers auto-reconnect on failure
- Logs health status

#### 3. Command Retry Logic
- Retries failed commands automatically
- Exponential backoff between retries
- Configurable max retry attempts
- Detailed error logging

#### 4. Enhanced Error Classes
- `EquipmentError` - Base error with severity and hints
- `ConnectionError` - Connection failures
- `CommandError` - Command execution failures
- `TimeoutError` - Operation timeouts

Each error includes:
- Severity level (LOW, MEDIUM, HIGH, CRITICAL)
- Troubleshooting hints
- Timestamp
- Recoverability flag

### Files Created

- `equipment/error_handler.py` - Complete error handling system (380 lines)
  - `RetryHandler` class
  - `ReconnectionHandler` class
  - `HealthMonitor` class
  - Error exception classes with troubleshooting hints

### Usage Examples

#### Retry Handler
```python
from equipment.error_handler import retry_handler

async def risky_operation():
    # May fail occasionally
    await equipment.execute_command("complex_operation")

# Automatically retries on failure
result = await retry_handler.execute_with_retry(
    risky_operation,
    operation_name="Complex Operation"
)
```

#### Reconnection Handler
```python
from equipment.error_handler import reconnection_handler

# Attempt to reconnect equipment
success = await reconnection_handler.attempt_reconnect(
    equipment.connect,
    equipment_id="scope_abc123"
)
```

#### Health Monitoring
```python
from equipment.error_handler import health_monitor

# Start monitoring (automatically started in main.py)
await health_monitor.start(equipment_manager)

# Stop monitoring (automatically stopped on shutdown)
await health_monitor.stop()
```

#### Enhanced Errors
```python
from equipment.error_handler import ConnectionError, ErrorSeverity

try:
    await equipment.connect()
except Exception as e:
    raise ConnectionError(
        resource_string="USB0::0x1AB1::0x04CE::...",
        original_error=e
    )
# Output includes troubleshooting hints:
# [HIGH] Failed to connect to USB0::...
#   💡 Hint: Check: 1) Equipment is powered on, 2) USB cable connected...
```

### Configuration
All error handling features are configurable via `.env`:
```bash
LABLINK_ENABLE_AUTO_RECONNECT=true
LABLINK_RECONNECT_ATTEMPTS=3
LABLINK_RECONNECT_DELAY_MS=1000
LABLINK_RECONNECT_BACKOFF_MULTIPLIER=2.0

LABLINK_ENABLE_HEALTH_MONITORING=true
LABLINK_HEALTH_CHECK_INTERVAL_SEC=30

LABLINK_ENABLE_COMMAND_RETRY=true
LABLINK_MAX_COMMAND_RETRIES=2
LABLINK_RETRY_DELAY_MS=500
```

---

## Enhancement 3: Equipment Profile System

### Overview
A comprehensive profile management system for saving, loading, and applying equipment configurations. Includes default profiles and a full REST API.

### Features

#### 1. Profile Management
- Save equipment configurations as profiles
- Load profiles to quickly restore settings
- List all available profiles
- Filter profiles by equipment type
- Delete profiles
- Apply profiles to connected equipment

#### 2. Default Profiles
Automatically created on server startup:

**Oscilloscopes:**
- "Oscilloscope - Debug Quick" - Fast debug settings
- "Oscilloscope - Power Analysis" - Power supply analysis

**Power Supplies:**
- "Power Supply - 5V Logic" - 5V @ 1A for digital circuits
- "Power Supply - 3.3V MCU" - 3.3V @ 500mA for MCUs
- "Power Supply - 12V Standard" - 12V @ 2A general use

**Electronic Loads:**
- "Electronic Load - Battery Test" - CC mode for battery discharge
- "Electronic Load - Power Supply Test" - CR mode for PS testing

#### 3. Profile Structure
```json
{
  "name": "Power Supply - 5V Logic",
  "description": "5V @ 1A for digital logic circuits",
  "equipment_type": "power_supply",
  "model": "generic",
  "settings": {
    "voltage": 5.0,
    "current_limit": 1.0,
    "output_enabled": false
  },
  "tags": ["5v", "logic", "default"],
  "created_at": "2025-11-07T21:30:00",
  "modified_at": "2025-11-07T21:30:00"
}
```

### Files Created

- `equipment/profiles.py` - Profile management system (340 lines)
  - `EquipmentProfile` Pydantic model
  - `ProfileManager` class
  - `create_default_profiles()` function

- `api/profiles.py` - REST API endpoints (240 lines)
  - GET `/api/profiles/list` - List all profiles
  - GET `/api/profiles/{name}` - Get specific profile
  - POST `/api/profiles/create` - Create new profile
  - PUT `/api/profiles/{name}` - Update profile
  - DELETE `/api/profiles/{name}` - Delete profile
  - POST `/api/profiles/{name}/apply/{equipment_id}` - Apply profile

### API Usage Examples

#### List All Profiles
```bash
curl http://localhost:8000/api/profiles/list
```

#### Get Specific Profile
```bash
curl http://localhost:8000/api/profiles/Power%20Supply%20-%205V%20Logic
```

#### Create Profile
```bash
curl -X POST http://localhost:8000/api/profiles/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Custom Profile",
    "description": "Custom settings for my setup",
    "equipment_type": "power_supply",
    "model": "BK9205B",
    "settings": {
      "voltage": 12.0,
      "current_limit": 3.0
    },
    "tags": ["custom", "test"]
  }'
```

#### Apply Profile to Equipment
```bash
curl -X POST http://localhost:8000/api/profiles/Power%20Supply%20-%205V%20Logic/apply/ps_abc123
```

#### Delete Profile
```bash
curl -X DELETE http://localhost:8000/api/profiles/My%20Custom%20Profile
```

### Python Usage

```python
from equipment.profiles import profile_manager, EquipmentProfile

# Create a profile
profile = EquipmentProfile(
    name="My Profile",
    description="Custom settings",
    equipment_type="oscilloscope",
    model="DS1104",
    settings={
        "timebase_scale": 0.001,
        "channel_1_scale": 1.0
    },
    tags=["custom"]
)

# Save profile
profile_manager.save_profile(profile)

# Load profile
loaded = profile_manager.load_profile("My Profile")

# List profiles
all_profiles = profile_manager.list_profiles()
scope_profiles = profile_manager.list_profiles(equipment_type="oscilloscope")

# Delete profile
profile_manager.delete_profile("My Profile")

# Apply to equipment
profile_manager.apply_profile(equipment, "My Profile")
```

### Profile Storage
- Profiles stored as JSON files in `./profiles/` directory
- File naming: `{profile_name}.json`
- Automatic directory creation
- Cache for fast access

---

## Integration

All three enhancements are fully integrated into the main server application:

### Server Startup Sequence

1. **Load Configuration**
   - Read environment variables
   - Create necessary directories
   - Initialize settings

2. **Validate Configuration**
   - Check for errors and conflicts
   - Display warnings
   - Exit if validation fails

3. **Initialize Equipment Manager**
   - Set up VISA resource manager
   - Discover available equipment

4. **Start Health Monitoring**
   - Begin background health checks
   - Enable auto-reconnection

5. **Create Default Profiles**
   - Generate default equipment profiles
   - Save to profile directory

6. **Start API Server**
   - Mount all routers (equipment, data, profiles)
   - Enable CORS
   - Start listening

### Server Shutdown Sequence

1. **Stop Health Monitoring**
   - Cancel monitoring task
   - Clean up resources

2. **Disconnect Equipment**
   - Gracefully disconnect all equipment
   - Save any pending data

3. **Shutdown Complete**

---

## API Documentation

With the server running, visit:
- **Interactive API Docs**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc

New profile endpoints will appear under the "profiles" tag.

---

## Testing

### Verification Script
```bash
cd /home/x9x0/LabLink/server
python3 verify_enhancements.py
```

This validates:
- All files are present
- Required classes exist
- Required methods exist
- Integration is complete

### Manual Testing

1. **Test Configuration Validation**
```bash
cd server
python3 -c "from config.validator import validate_config; validate_config()"
```

2. **Test Profile Creation**
```bash
# Start server
python3 main.py

# In another terminal
curl http://localhost:8000/api/profiles/list
```

3. **Test Error Handling** (requires equipment)
- Connect equipment
- Unplug USB cable
- Watch logs for auto-reconnect attempts

---

## Statistics

- **Total New Code**: ~1,400 lines
- **New Files**: 4 major modules
- **Configuration Options**: 50+
- **API Endpoints**: 6 new endpoints
- **Default Profiles**: 7 profiles
- **Error Classes**: 5 specialized classes

---

## Next Steps

Recommended improvements:
- Add authentication middleware
- Implement rate limiting
- Add profile import/export (YAML support)
- Create profile templates for specific equipment models
- Add profile versioning
- Implement equipment-specific profile validation

---

## Version History

- **v0.2.0** (2025-11-07) - Added configuration management, error handling, and profile system
- **v0.1.0** (2025-11-06) - Initial release with basic equipment drivers

---

## Support

For issues or questions:
- Review configuration validation output
- Check server logs in `./logs/`
- Consult API documentation at `/docs`
- Review this document for usage examples
