# LabLink Advanced Logging System

## Overview

The LabLink Advanced Logging System provides comprehensive logging capabilities with structured JSON logging, automatic log rotation, performance metrics tracking, and audit trails.

**Version:** 0.7.0
**Status:** Production Ready

---

## Features

### Core Capabilities
- **Structured JSON Logging**: Machine-readable logs for easy parsing and analysis
- **Colored Console Output**: Easy-to-read colored logs for development
- **Automatic Log Rotation**: Size-based and time-based rotation with compression
- **Performance Metrics**: Track function execution time, memory usage, and system resources
- **Audit Trail**: Complete history of user actions and equipment operations
- **Equipment Event Logging**: Dedicated logs for each equipment device
- **HTTP Request Logging**: Complete access logs for all API calls
- **Multiple Log Formats**: JSON, text, and compact formats

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Code                          │
└────────────┬────────────────────────────────┬───────────────┘
             │                                │
    ┌────────▼────────┐              ┌────────▼────────┐
    │  get_logger()   │              │  Middleware      │
    │  decorators     │              │  @log_performance│
    └────────┬────────┘              └────────┬────────┘
             │                                │
    ┌────────▼────────────────────────────────▼────────┐
    │          Logging Configuration System             │
    │  - Formatters (JSON, Colored, Compact)           │
    │  - Handlers (File, Console, Rotating)            │
    │  - Specialized Loggers (Performance, Audit)      │
    └────────┬────────────────────────────────┬────────┘
             │                                │
    ┌────────▼────────┐              ┌────────▼────────┐
    │   Log Files     │              │    Console      │
    │  (Compressed)   │              │   (Colored)     │
    └─────────────────┘              └─────────────────┘
```

---

## Log Files

The logging system creates several specialized log files:

### Main Application Log
**File:** `logs/lablink.log`
**Purpose:** General application logging
**Rotation:** 10 MB per file, 30 days retention
**Format:** Configurable (JSON or text)

### Access Log
**File:** `logs/access.log`
**Purpose:** All HTTP requests and responses
**Rotation:** 50 MB per file, 30 days retention
**Format:** JSON

**Example Entry:**
```json
{
  "timestamp": "2025-01-08T10:30:00.123Z",
  "level": "INFO",
  "logger": "lablink.access",
  "message": "POST /api/acquisition/session/create",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_host": "192.168.1.100",
  "method": "POST",
  "path": "/api/acquisition/session/create",
  "status_code": 200,
  "duration_ms": 45.23
}
```

### Performance Log
**File:** `logs/performance.log`
**Purpose:** Performance metrics and timing information
**Rotation:** 50 MB per file, 10 days retention
**Format:** JSON

**Example Entry:**
```json
{
  "timestamp": "2025-01-08T10:30:00.456Z",
  "level": "INFO",
  "logger": "lablink.performance",
  "message": "Function execution: start_acquisition",
  "function": "start_acquisition",
  "module": "acquisition.manager",
  "duration_ms": 125.45,
  "memory_delta_mb": 2.3,
  "success": true
}
```

### Audit Log
**File:** `logs/audit.log`
**Purpose:** User actions and security-relevant events
**Rotation:** 100 MB per file, 30 days retention
**Format:** JSON

**Example Entry:**
```json
{
  "timestamp": "2025-01-08T10:30:00.789Z",
  "level": "INFO",
  "logger": "lablink.audit",
  "message": "User action: POST /api/safety/emergency_stop",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_host": "192.168.1.100",
  "method": "POST",
  "path": "/api/safety/emergency_stop",
  "status_code": 200,
  "action": "emergency_stop"
}
```

### Equipment Log
**File:** `logs/equipment.log`
**Purpose:** Equipment-specific events and operations
**Rotation:** 50 MB per file, 20 days retention
**Format:** JSON

**Example Entry:**
```json
{
  "timestamp": "2025-01-08T10:30:00.012Z",
  "level": "INFO",
  "logger": "lablink.equipment",
  "message": "Equipment command: PSU_001 - set_voltage",
  "equipment_id": "PSU_001",
  "event": "command",
  "command": "set_voltage",
  "success": true,
  "duration_ms": 12.34
}
```

### Equipment-Specific Logs
**File:** `logs/equipment_{equipment_id}.log`
**Purpose:** Dedicated log file for each equipment device
**Rotation:** 10 MB per file, 5 days retention
**Format:** JSON

---

## Usage Examples

### Basic Logging

```python
from logging_config import get_logger

logger = get_logger(__name__)

logger.debug("Debug message")
logger.info("Information message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")
```

### Logging with Extra Context

```python
logger.info(
    "Equipment connected",
    extra={
        "equipment_id": "PSU_001",
        "address": "USB0::0x1234::0x5678::INSTR",
        "success": True
    }
)
```

### Performance Logging Decorator

```python
from logging_config import log_performance

@log_performance
async def expensive_operation():
    # This function's execution time and memory usage will be logged
    await do_work()
    return result
```

### Equipment Event Logging

```python
from logging_config.middleware import equipment_event_logger

# Log connection
equipment_event_logger.log_connection(
    equipment_id="PSU_001",
    address="USB0::0x1234::0x5678::INSTR",
    success=True
)

# Log command execution
equipment_event_logger.log_command(
    equipment_id="PSU_001",
    command="set_voltage",
    success=True,
    duration_ms=12.34
)

# Log error
equipment_event_logger.log_error(
    equipment_id="PSU_001",
    error_type="timeout",
    error_message="Command timeout after 5000ms"
)

# Log state change
equipment_event_logger.log_state_change(
    equipment_id="PSU_001",
    old_state="idle",
    new_state="active"
)

# Log health check
equipment_event_logger.log_health_check(
    equipment_id="PSU_001",
    is_healthy=True,
    metrics={
        "response_time_ms": 45.2,
        "error_count": 0
    }
)
```

### Performance Monitoring

```python
from logging_config.performance import performance_monitor

# Log system metrics
performance_monitor.log_system_metrics()

# Log equipment metrics
performance_monitor.log_equipment_metrics(
    equipment_id="PSU_001",
    metrics={
        "voltage": 5.0,
        "current": 1.5,
        "temperature": 45.2
    }
)

# Log API metrics
performance_monitor.log_api_metrics(
    endpoint="/api/acquisition/session/create",
    method="POST",
    duration_ms=125.45,
    status_code=200
)

# Log acquisition metrics
performance_monitor.log_acquisition_metrics(
    acquisition_id="acq_abc123",
    samples_collected=5420,
    buffer_usage_percent=54.2,
    sample_rate=10.05
)
```

---

## Configuration

Configuration is done through environment variables or `.env` file:

```bash
# Log Level
LABLINK_LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Log Format
LABLINK_LOG_FORMAT=json  # json or text

# File Logging
LABLINK_LOG_TO_FILE=true
LABLINK_LOG_DIR=./logs

# Log Rotation
LABLINK_LOG_ROTATION_SIZE_MB=10
LABLINK_LOG_RETENTION_DAYS=30

# Performance Logging
LABLINK_ENABLE_PERFORMANCE_LOGGING=true
```

---

## Log Formatters

### JSON Formatter
Produces structured JSON logs for machine parsing:

```json
{
  "timestamp": "2025-01-08T10:30:00.123456",
  "level": "INFO",
  "logger": "lablink.equipment",
  "message": "Equipment connected",
  "module": "manager",
  "function": "connect_equipment",
  "line": 123,
  "equipment_id": "PSU_001",
  "address": "USB0::0x1234::0x5678::INSTR"
}
```

### Colored Formatter
Produces human-readable colored logs for console:

```
10:30:00 - INFO     - lablink.equipment - Equipment connected
10:30:01 - WARNING  - lablink.equipment - Connection timeout
10:30:02 - ERROR    - lablink.equipment - Failed to connect
```

### Compact Formatter
Produces concise single-line logs for production:

```
10:30:00.123 | I | equipment | Equipment connected (45.2ms)
10:30:01.456 | W | equipment | Connection timeout
10:30:02.789 | E | equipment | Failed to connect
```

---

## Log Handlers

### Rotating File Handler
Automatically rotates logs when they reach a specified size:

```python
from logging_config import get_rotating_file_handler

handler = get_rotating_file_handler(
    log_dir="./logs",
    filename="myapp.log",
    max_bytes=10 * 1024 * 1024,  # 10 MB
    backup_count=5,
    formatter_type="json",
    compress=True
)
```

### Timed Rotating Handler
Rotates logs at specific time intervals:

```python
from logging_config import get_timed_rotating_handler

handler = get_timed_rotating_handler(
    log_dir="./logs",
    filename="daily.log",
    when='midnight',  # S, M, H, D, midnight
    interval=1,
    backup_count=30,
    formatter_type="json"
)
```

### Console Handler
Outputs colored logs to console:

```python
from logging_config import get_console_handler

handler = get_console_handler(
    colored=True,
    level=logging.INFO
)
```

---

## Middleware

### Logging Middleware
Automatically logs all HTTP requests and responses:

```python
from fastapi import FastAPI
from logging_config import LoggingMiddleware

app = FastAPI()
app.add_middleware(LoggingMiddleware)
```

**Logged Information:**
- Request ID (UUID)
- Client IP address
- HTTP method and URL
- Response status code
- Request duration
- Errors (if any)

**Audit-Worthy Actions:**
All write operations (POST, PUT, DELETE, PATCH) and sensitive read operations are logged to the audit trail.

---

## Log Rotation and Compression

### Automatic Rotation
Logs are automatically rotated when they reach the configured size or time interval.

### Compression
Old log files are automatically compressed with gzip to save disk space:

```
logs/
├── lablink.log              # Current log
├── lablink.log.1.gz         # Previous log (compressed)
├── lablink.log.2.gz         # Older log (compressed)
└── lablink.log.3.gz         # Even older log (compressed)
```

### Cleanup
Old logs beyond the retention period are automatically deleted.

---

## Best Practices

1. **Use Appropriate Log Levels**
   - `DEBUG`: Detailed information for diagnosing problems
   - `INFO`: Confirmation that things are working as expected
   - `WARNING`: Indication that something unexpected happened
   - `ERROR`: A serious problem that prevented a function from completing
   - `CRITICAL`: A very serious error that may prevent the program from continuing

2. **Add Context with Extra Fields**
   ```python
   logger.info("Operation completed", extra={
       "operation_id": op_id,
       "duration_ms": duration,
       "success": True
   })
   ```

3. **Use Structured Logging**
   - Use JSON format for production environments
   - Makes logs easy to parse and analyze
   - Enables log aggregation and analysis tools

4. **Monitor Log Sizes**
   - Configure appropriate rotation sizes
   - Set retention periods based on storage capacity
   - Enable compression to save disk space

5. **Secure Sensitive Information**
   - Never log passwords or API keys
   - Sanitize user input before logging
   - Be careful with personal information

6. **Use Performance Logging Sparingly**
   - Only enable for performance-critical functions
   - Can impact performance if overused
   - Disable in production if not needed

---

## Troubleshooting

**Q: Logs are not being created**
- Check that `LABLINK_LOG_TO_FILE=true`
- Verify log directory exists and is writable
- Check file permissions

**Q: Log files are too large**
- Reduce `LABLINK_LOG_ROTATION_SIZE_MB`
- Lower log level (INFO instead of DEBUG)
- Reduce retention period

**Q: Not seeing colored output in console**
- Some terminals don't support ANSI colors
- Check that output is a TTY (not redirected)
- Set `colored=False` in console handler

**Q: Performance logging is missing**
- Set `LABLINK_ENABLE_PERFORMANCE_LOGGING=true`
- Verify decorator is applied to functions
- Check that performance.log exists

**Q: Audit logs are missing events**
- Check middleware is added to FastAPI app
- Verify path matches audit-worthy patterns
- Check audit log file permissions

---

## Log Analysis

### Using jq for JSON Logs

Get all errors from the last hour:
```bash
tail -n 1000 logs/lablink.log | jq 'select(.level == "ERROR")'
```

Find slow API requests:
```bash
cat logs/access.log | jq 'select(.duration_ms > 1000)'
```

Equipment events by device:
```bash
cat logs/equipment.log | jq 'select(.equipment_id == "PSU_001")'
```

### Log Aggregation Tools

The JSON format is compatible with popular log aggregation tools:
- **ELK Stack** (Elasticsearch, Logstash, Kibana)
- **Splunk**
- **Graylog**
- **Loki** (Grafana)

---

## Version History

**v0.7.0** (2025-01-08)
- Initial release of Advanced Logging System
- Structured JSON logging with multiple formatters
- Automatic log rotation and compression
- Performance metrics logging
- Audit trail and access logs
- Equipment event logging
- HTTP request/response logging middleware
- Specialized loggers for different subsystems

---

**End of Documentation**
