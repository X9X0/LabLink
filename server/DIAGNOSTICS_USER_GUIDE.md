# Equipment Diagnostics System - User Guide

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Features](#core-features)
4. [Equipment Health Monitoring](#equipment-health-monitoring)
5. [Calibration Management](#calibration-management)
6. [Error Code Interpretation](#error-code-interpretation)
7. [Built-In Self-Tests (BIST)](#built-in-self-tests-bist)
8. [Temperature Monitoring](#temperature-monitoring)
9. [API Reference](#api-reference)
10. [Best Practices](#best-practices)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The LabLink Equipment Diagnostics System provides comprehensive health monitoring, calibration tracking, and diagnostic capabilities for laboratory equipment. It helps ensure equipment reliability, regulatory compliance, and optimal performance.

### Key Features

- **Comprehensive Health Monitoring**: Track connection, communication, performance, and functionality
- **Calibration Management**: Schedule calibrations, track history, and maintain compliance
- **Error Code Database**: Interpret equipment errors with troubleshooting guidance
- **Built-In Self-Tests**: Execute and track equipment diagnostic tests
- **Temperature Monitoring**: Monitor equipment temperature to prevent overheating
- **Operating Hours Tracking**: Track cumulative equipment usage
- **Diagnostic Reports**: Generate detailed health and calibration reports

---

## Quick Start

### 1. Check Equipment Health

```python
import aiohttp

async def check_health():
    async with aiohttp.ClientSession() as session:
        async with session.get('http://localhost:8000/api/diagnostics/health/power_supply_1') as resp:
            data = await resp.json()
            health = data['health']
            
            print(f"Health Status: {health['health_status']}")
            print(f"Health Score: {health['health_score']}/100")
            print(f"Connection: {health['connection_status']}")
            print(f"Communication: {health['communication_status']}")
```

### 2. Add Calibration Record

```python
from datetime import datetime, timedelta

async def add_calibration():
    record = {
        "equipment_id": "power_supply_1",
        "equipment_type": "power_supply",
        "equipment_model": "BK9130B",
        "calibration_type": "full",
        "due_date": (datetime.now() + timedelta(days=365)).isoformat(),
        "result": "pass",
        "performed_by": "John Doe",
        "organization": "Cal Lab Inc",
        "certificate_number": "CAL-2025-001"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post('http://localhost:8000/api/calibration/records', json=record) as resp:
            data = await resp.json()
            print(f"Calibration recorded: {data['calibration_id']}")
```

### 3. Check Equipment Errors

```python
async def check_errors():
    async with aiohttp.ClientSession() as session:
        async with session.get('http://localhost:8000/api/diagnostics/errors/power_supply_1') as resp:
            data = await resp.json()
            
            if data['has_error']:
                print(f"Error Code: {data['error_code']}")
                print(f"Error Message: {data['error_message']}")
                print(f"Severity: {data['error_info']['severity']}")
                print(f"Recommended Actions: {data['error_info']['recommended_actions']}")
```

---

## Core Features

### Health Scoring Algorithm

Equipment health is scored on a 0-100 scale based on four components:

- **Connection (30 points)**: Connected status and response time
- **Communication (30 points)**: Command success rate
- **Performance (20 points)**: Command latency and throughput
- **Functionality (20 points)**: Diagnostic test pass rate

#### Health Status Mapping

- **90-100**: Healthy (green) - Equipment operating optimally
- **70-89**: Degraded (yellow) - Minor issues, equipment operational
- **50-69**: Warning (orange) - Significant issues, may affect operation
- **1-49**: Critical (red) - Major issues, equipment unreliable
- **0**: Offline (gray) - Equipment not responding

### Diagnostic Categories

The system supports multiple diagnostic categories:

- **Connection**: Physical connection quality and stability
- **Communication**: Command/response performance
- **Performance**: Processing speed and throughput
- **Functionality**: Equipment-specific functional tests
- **Calibration**: Calibration status and compliance
- **Safety**: Safety system checks
- **System**: Overall system health

---

## Equipment Health Monitoring

### Real-Time Health Checks

Get current health status for equipment:

```http
GET /api/diagnostics/health/{equipment_id}
```

**Response:**
```json
{
  "success": true,
  "health": {
    "equipment_id": "power_supply_1",
    "timestamp": "2025-01-15T10:30:00",
    "health_status": "healthy",
    "health_score": 95.5,
    "connection_status": "pass",
    "communication_status": "pass",
    "performance_status": "pass",
    "functionality_status": "pass",
    "active_issues": [],
    "warnings": [],
    "recommendations": []
  }
}
```

### Cached Health Status

For faster responses, use cached health data:

```http
GET /api/diagnostics/health/{equipment_id}/cached
```

**Note**: Cached data may be outdated. Use real-time checks for critical decisions.

### Connection Diagnostics

Check connection quality in detail:

```http
GET /api/diagnostics/connection/{equipment_id}
```

**Response:**
```json
{
  "success": true,
  "connection": {
    "equipment_id": "power_supply_1",
    "is_connected": true,
    "response_time_ms": 45.2,
    "uptime_seconds": 3600,
    "disconnection_count": 0,
    "error_rate": 0.0
  }
}
```

### Communication Diagnostics

Monitor communication performance:

```http
GET /api/diagnostics/communication/{equipment_id}
```

**Response:**
```json
{
  "success": true,
  "communication": {
    "equipment_id": "power_supply_1",
    "total_commands": 1000,
    "successful_commands": 998,
    "failed_commands": 2,
    "average_response_time_ms": 42.5,
    "timeout_count": 0,
    "retry_count": 2
  }
}
```

### Performance Benchmarking

Run performance benchmarks:

```http
POST /api/diagnostics/benchmark/{equipment_id}
```

**Response:**
```json
{
  "success": true,
  "benchmark": {
    "equipment_id": "power_supply_1",
    "timestamp": "2025-01-15T10:30:00",
    "command_latency_ms": {
      "*IDN?": 38.2,
      "*OPC?": 42.1,
      "*STB?": 35.8
    },
    "throughput_commands_per_sec": 24.5,
    "performance_score": 92.3
  }
}
```

### System-Wide Diagnostics

Get overview of all equipment:

```http
GET /api/diagnostics/system
```

**Response:**
```json
{
  "success": true,
  "system": {
    "total_equipment": 5,
    "connected_equipment": 4,
    "healthy_equipment": 3,
    "degraded_equipment": 1,
    "critical_equipment": 0,
    "server_cpu_percent": 25.3,
    "server_memory_percent": 45.2
  }
}
```

---

## Calibration Management

### Calibration Record Structure

A calibration record contains:

- **Equipment Information**: ID, type, model
- **Calibration Details**: Type, date, due date, result
- **Personnel**: Performed by, organization, location
- **Measurements**: Pre/post calibration data
- **Standards**: Traceable calibration standards used
- **Environment**: Temperature, humidity during calibration
- **Results**: Adjustments made, out-of-tolerance items
- **Certificate**: Certificate number and file path

### Adding Calibration Records

Create a new calibration record:

```http
POST /api/calibration/records
```

**Request Body:**
```json
{
  "equipment_id": "oscilloscope_1",
  "equipment_type": "oscilloscope",
  "equipment_model": "Rigol MSO2072A",
  "calibration_type": "full",
  "due_date": "2026-01-15T00:00:00",
  "result": "pass",
  "performed_by": "Jane Smith",
  "organization": "AccuCal Laboratory",
  "location": "Lab Building A",
  "pre_calibration_measurements": {
    "dc_voltage_1v": 1.002,
    "dc_voltage_10v": 10.015
  },
  "post_calibration_measurements": {
    "dc_voltage_1v": 1.000,
    "dc_voltage_10v": 10.001
  },
  "standards_used": [
    {
      "type": "DC Voltage Standard",
      "model": "Fluke 5720A",
      "serial": "12345",
      "cert_number": "NIST-2024-123"
    }
  ],
  "temperature_celsius": 23.0,
  "humidity_percent": 45.0,
  "adjustments_made": ["DC voltage offset adjusted"],
  "certificate_number": "CAL-2025-OSC-001"
}
```

### Calibration Types

- **full**: Complete calibration of all parameters
- **partial**: Calibration of specific parameters only
- **verification**: Verification only (no adjustments)
- **adjustment**: Adjustment based on verification results
- **factory**: Factory calibration
- **in_house**: Internal calibration

### Calibration Results

- **pass**: Calibration passed within tolerance
- **pass_with_adjustment**: Passed after making adjustments
- **fail**: Calibration failed (out of tolerance)
- **incomplete**: Calibration not completed
- **aborted**: Calibration aborted

### Viewing Calibration History

Get full calibration history:

```http
GET /api/calibration/records/{equipment_id}?limit=10
```

Get latest calibration only:

```http
GET /api/calibration/records/{equipment_id}/latest
```

### Checking Calibration Status

Check if calibration is current:

```http
GET /api/calibration/status/{equipment_id}
```

**Response:**
```json
{
  "success": true,
  "equipment_id": "oscilloscope_1",
  "status": "current",
  "is_current": true,
  "days_until_due": 320,
  "last_calibration_date": "2025-01-15T00:00:00",
  "next_due_date": "2026-01-15T00:00:00"
}
```

### Calibration Status Values

- **current**: Calibration is valid
- **due_soon**: Calibration due within warning period (default 30 days)
- **due**: Calibration is due today
- **overdue**: Calibration is overdue
- **never_calibrated**: Equipment has never been calibrated
- **unknown**: Calibration status cannot be determined

### Calibration Scheduling

Set up automatic calibration scheduling:

```http
POST /api/calibration/schedules
```

**Request Body:**
```json
{
  "equipment_id": "oscilloscope_1",
  "interval_days": 365,
  "warning_days": 30,
  "auto_schedule": true,
  "notify_due_soon": true,
  "notify_overdue": true,
  "notification_emails": [
    "lab_manager@example.com",
    "qa_team@example.com"
  ]
}
```

### Finding Due Calibrations

Get list of equipment requiring calibration:

```http
GET /api/calibration/due?include_due_soon=true
```

**Response:**
```json
{
  "success": true,
  "count": 2,
  "equipment": [
    {
      "equipment_id": "multimeter_1",
      "status": "overdue",
      "days_until_due": -15,
      "due_date": "2024-12-30T00:00:00",
      "last_calibration": "2023-12-30T00:00:00"
    },
    {
      "equipment_id": "oscilloscope_2",
      "status": "due_soon",
      "days_until_due": 20,
      "due_date": "2025-02-05T00:00:00",
      "last_calibration": "2024-02-05T00:00:00"
    }
  ]
}
```

### Calibration Reports

Generate comprehensive calibration report:

```http
GET /api/calibration/report
```

**Response:**
```json
{
  "success": true,
  "report": {
    "generated_at": "2025-01-15T10:30:00",
    "total_equipment": 10,
    "status_summary": {
      "current": 6,
      "due_soon": 2,
      "due": 0,
      "overdue": 1,
      "never_calibrated": 1
    },
    "equipment_details": [ ... ]
  }
}
```

---

## Error Code Interpretation

The system includes a comprehensive error code database supporting:

- **Standard SCPI Errors** (IEEE 488.2)
- **Rigol-specific Errors**
- **BK Precision-specific Errors**

### Checking Equipment Errors

Get current error with interpretation:

```http
GET /api/diagnostics/errors/{equipment_id}
```

**Response with Error:**
```json
{
  "success": true,
  "equipment_id": "power_supply_1",
  "has_error": true,
  "error_code": -222,
  "error_message": "Data out of range",
  "error_info": {
    "found": true,
    "name": "Data Out of Range",
    "message": "Data value out of valid range",
    "severity": "error",
    "category": "operation",
    "possible_causes": [
      "Value too high or low",
      "Outside equipment limits"
    ],
    "recommended_actions": [
      "Check equipment specifications",
      "Use value within range"
    ],
    "requires_reset": false,
    "requires_service": false
  }
}
```

**Response without Error:**
```json
{
  "success": true,
  "equipment_id": "power_supply_1",
  "has_error": false,
  "error_code": null,
  "error_message": null
}
```

### Error Severity Levels

- **info**: Informational message
- **warning**: Warning but equipment operational
- **error**: Error affecting operation
- **critical**: Critical error, equipment non-functional
- **fatal**: Fatal error requiring service

### Error Categories

- **communication**: Communication/protocol errors
- **hardware**: Hardware failures
- **calibration**: Calibration-related errors
- **operation**: Operational errors
- **safety**: Safety-related errors
- **configuration**: Configuration errors
- **power**: Power-related issues
- **temperature**: Temperature issues
- **firmware**: Firmware errors

---

## Built-In Self-Tests (BIST)

Many equipment models support built-in self-tests for validating internal systems.

### Running Self-Tests

Execute equipment self-test:

```http
POST /api/diagnostics/self-test/{equipment_id}
```

**Response (Pass):**
```json
{
  "success": true,
  "test_result": {
    "test_id": "self_test",
    "equipment_id": "oscilloscope_1",
    "status": "pass",
    "duration_seconds": 15.3,
    "message": "Self-test passed",
    "details": {
      "passed": true,
      "tests": [
        {
          "name": "Memory Test",
          "passed": true,
          "details": "All memory banks OK"
        },
        {
          "name": "ADC Test",
          "passed": true,
          "details": "ADC calibration verified"
        },
        {
          "name": "Display Test",
          "passed": true,
          "details": "Display pixels OK"
        }
      ],
      "timestamp": "2025-01-15T10:30:00"
    }
  }
}
```

**Response (Not Supported):**
```json
{
  "success": true,
  "test_result": {
    "test_id": "self_test",
    "equipment_id": "power_supply_1",
    "status": "unknown",
    "message": "Self-test not supported by equipment"
  }
}
```

### Self-Test Status Values

- **pass**: Self-test passed
- **fail**: Self-test failed
- **warning**: Self-test passed with warnings
- **error**: Error occurred during self-test
- **unknown**: Self-test not supported

---

## Temperature Monitoring

Monitor equipment temperature to prevent overheating and ensure optimal performance.

### Checking Temperature

Get current equipment temperature:

```http
GET /api/diagnostics/temperature/{equipment_id}
```

**Response (Supported):**
```json
{
  "success": true,
  "equipment_id": "oscilloscope_1",
  "temperature_celsius": 42.5,
  "supported": true
}
```

**Response (Not Supported):**
```json
{
  "success": true,
  "equipment_id": "power_supply_1",
  "temperature_celsius": null,
  "supported": false
}
```

### Temperature Thresholds

Typical temperature ranges:

- **Normal**: 20-45°C
- **Warning**: 45-60°C
- **Critical**: >60°C

**Note**: Specific thresholds vary by equipment model. Check equipment specifications.

---

## API Reference

### Diagnostic Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/diagnostics/health/{equipment_id}` | Get equipment health status |
| GET | `/api/diagnostics/health` | Get all equipment health |
| GET | `/api/diagnostics/health/{equipment_id}/cached` | Get cached health status |
| GET | `/api/diagnostics/connection/{equipment_id}` | Check connection diagnostics |
| GET | `/api/diagnostics/communication/{equipment_id}` | Get communication statistics |
| POST | `/api/diagnostics/benchmark/{equipment_id}` | Run performance benchmark |
| GET | `/api/diagnostics/benchmark/{equipment_id}/history` | Get benchmark history |
| POST | `/api/diagnostics/report` | Generate diagnostic report |
| GET | `/api/diagnostics/system` | Get system-wide diagnostics |
| GET | `/api/diagnostics/temperature/{equipment_id}` | Check equipment temperature |
| GET | `/api/diagnostics/errors/{equipment_id}` | Check error codes |
| POST | `/api/diagnostics/self-test/{equipment_id}` | Run self-test |
| GET | `/api/diagnostics/comprehensive/{equipment_id}` | Get all diagnostics |

### Calibration Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/calibration/records` | Add calibration record |
| GET | `/api/calibration/records/{equipment_id}` | Get calibration history |
| GET | `/api/calibration/records/{equipment_id}/latest` | Get latest calibration |
| DELETE | `/api/calibration/records/{equipment_id}/{cal_id}` | Delete calibration record |
| GET | `/api/calibration/status/{equipment_id}` | Get calibration status |
| GET | `/api/calibration/due` | Get due calibrations |
| POST | `/api/calibration/schedules` | Set calibration schedule |
| GET | `/api/calibration/schedules/{equipment_id}` | Get calibration schedule |
| DELETE | `/api/calibration/schedules/{equipment_id}` | Delete calibration schedule |
| GET | `/api/calibration/report` | Generate calibration report |

---

## Best Practices

### Regular Health Monitoring

1. **Monitor Continuously**: Set up periodic health checks (every 5-10 minutes)
2. **Track Trends**: Store historical health scores to identify degradation
3. **Alert on Changes**: Set up alerts for health score drops >10 points
4. **Review Reports**: Weekly review of diagnostic reports

### Calibration Management

1. **Schedule Proactively**: Set calibration intervals based on usage and requirements
2. **Document Thoroughly**: Record all calibration details including environment
3. **Track Standards**: Maintain traceability to calibration standards
4. **Review Regularly**: Check for due calibrations weekly
5. **Pre/Post Verification**: Always record before and after measurements

### Error Handling

1. **Clear Errors Promptly**: Clear error queue after addressing issues
2. **Log All Errors**: Keep historical record of all errors
3. **Investigate Patterns**: Look for recurring errors indicating systemic issues
4. **Follow Recommendations**: Act on recommended troubleshooting steps

### Self-Test Procedures

1. **Regular Testing**: Run self-tests weekly or after significant events
2. **Record Results**: Log all self-test results for trend analysis
3. **Pre-Calibration**: Always run self-test before calibration
4. **After Maintenance**: Run self-test after any repairs or modifications

### Temperature Management

1. **Monitor High-Power Equipment**: Check temperature frequently during high-power operations
2. **Ensure Ventilation**: Verify adequate airflow and cooling
3. **Set Thresholds**: Configure temperature alarms based on equipment specs
4. **Thermal Cycling**: Allow proper warm-up and cool-down periods

---

## Troubleshooting

### Equipment Reports as Offline

**Symptoms:**
- Health status shows "offline"
- Health score is 0

**Possible Causes:**
- Equipment physically disconnected
- Communication cable issue
- Equipment powered off
- VISA resource conflict

**Solutions:**
1. Check physical connections and power
2. Verify VISA resource string is correct
3. Try manual reconnection via equipment API
4. Check for other software using the same resource

### High Error Rate

**Symptoms:**
- Communication status shows high failed command count
- Error rate >5%

**Possible Causes:**
- Poor quality cable
- Electrical interference
- Equipment firmware issue
- Timing/synchronization problems

**Solutions:**
1. Replace communication cable with high-quality shielded cable
2. Check for nearby electrical noise sources
3. Update equipment firmware
4. Add delays between commands
5. Reduce command rate

### Calibration Status Unknown

**Symptoms:**
- Calibration status shows "unknown"
- No due date available

**Possible Causes:**
- Never calibrated
- Calibration record missing due date
- Data corruption

**Solutions:**
1. Add initial calibration record with due date
2. Set up calibration schedule
3. Verify calibration data integrity

### Self-Test Failures

**Symptoms:**
- Self-test status shows "fail"
- Specific test components failing

**Possible Causes:**
- Hardware degradation
- Calibration drift
- Component failure
- Software/firmware issue

**Solutions:**
1. Review failed test details for specific component
2. Perform calibration if out of tolerance
3. Update firmware if available
4. Contact manufacturer support for persistent failures
5. Schedule equipment service/repair

### Temperature Too High

**Symptoms:**
- Temperature >60°C
- Equipment automatically shutting down

**Possible Causes:**
- Blocked ventilation
- Fan failure
- High ambient temperature
- Excessive load

**Solutions:**
1. Ensure adequate spacing around equipment (minimum 10cm)
2. Verify fan operation
3. Improve room cooling/ventilation
4. Reduce equipment load or duty cycle
5. Clean dust from vents and fans

---

## Regulatory Compliance

### ISO 17025 Calibration

For ISO 17025 compliance, ensure calibration records include:

- ✓ Traceable calibration standards
- ✓ Environmental conditions (temperature, humidity)
- ✓ Uncertainty calculations
- ✓ Pre and post calibration measurements
- ✓ Calibration certificate number
- ✓ Personnel qualifications
- ✓ Equipment identification (model, serial)

### FDA 21 CFR Part 11

For FDA-regulated environments:

- Maintain audit trail of all calibration records
- Implement electronic signatures for calibration approval
- Prevent backdating of calibration records
- Maintain data integrity and security
- Generate compliance reports on demand

### Good Laboratory Practice (GLP)

For GLP compliance:

- Perform and document regular equipment qualification (IQ/OQ/PQ)
- Maintain equipment usage logs
- Track calibration and maintenance history
- Document training on equipment operation
- Keep Standard Operating Procedures (SOPs) up to date

---

## Example Workflows

### Complete Equipment Setup

```python
async def setup_new_equipment(equipment_id, equipment_type, equipment_model):
    """Complete setup workflow for new equipment."""
    
    # 1. Connect equipment
    await connect_equipment(equipment_id)
    
    # 2. Run initial health check
    health = await check_health(equipment_id)
    print(f"Initial health score: {health['health_score']}")
    
    # 3. Run self-test
    self_test = await run_self_test(equipment_id)
    if self_test['status'] != 'pass':
        print("WARNING: Self-test failed!")
    
    # 4. Record calibration
    cal_record = {
        "equipment_id": equipment_id,
        "equipment_type": equipment_type,
        "equipment_model": equipment_model,
        "calibration_type": "full",
        "due_date": (datetime.now() + timedelta(days=365)).isoformat(),
        "result": "pass",
        "performed_by": "Setup Team"
    }
    await add_calibration(cal_record)
    
    # 5. Set up calibration schedule
    schedule = {
        "equipment_id": equipment_id,
        "interval_days": 365,
        "warning_days": 30,
        "notify_due_soon": true
    }
    await set_calibration_schedule(schedule)
    
    print(f"Equipment {equipment_id} setup complete!")
```

### Daily Health Check Routine

```python
async def daily_health_check():
    """Daily equipment health check routine."""
    
    # Get all equipment
    system_diag = await get_system_diagnostics()
    
    print(f"=== Daily Health Check ===")
    print(f"Total Equipment: {system_diag['total_equipment']}")
    print(f"Connected: {system_diag['connected_equipment']}")
    print(f"Healthy: {system_diag['healthy_equipment']}")
    print(f"Degraded: {system_diag['degraded_equipment']}")
    print(f"Critical: {system_diag['critical_equipment']}")
    
    # Check for errors on all equipment
    for eq_id, health_status in system_diag['equipment_health'].items():
        if health_status not in ['healthy', 'degraded']:
            error_info = await check_errors(eq_id)
            if error_info['has_error']:
                print(f"\nERROR on {eq_id}:")
                print(f"  Code: {error_info['error_code']}")
                print(f"  Message: {error_info['error_message']}")
                print(f"  Actions: {error_info['error_info']['recommended_actions']}")
    
    # Check due calibrations
    due_cals = await get_due_calibrations(include_due_soon=True)
    if due_cals['count'] > 0:
        print(f"\n{due_cals['count']} calibration(s) need attention:")
        for item in due_cals['equipment']:
            print(f"  {item['equipment_id']}: {item['status']} ({item['days_until_due']} days)")
```

---

## Support

For additional support:

- **Documentation**: See `/docs` endpoint for full API documentation
- **Issues**: Report issues on GitHub repository
- **Contact**: support@lablink.example.com

---

**Version**: 0.12.0  
**Last Updated**: January 2025
