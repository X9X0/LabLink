# LabLink Alarm & Notification System Guide

**Version:** 0.11.0
**Last Updated:** 2025-11-13
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Equipment Monitoring Integration](#equipment-monitoring-integration)
4. [Creating Alarms](#creating-alarms)
5. [Notification Channels](#notification-channels)
6. [Alarm Management](#alarm-management)
7. [API Reference](#api-reference)
8. [Configuration Examples](#configuration-examples)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The LabLink alarm system provides comprehensive monitoring and alerting for lab equipment. Key features include:

- **Automatic Equipment Monitoring** - Alarms automatically trigger based on equipment readings
- **Multiple Notification Channels** - Email, SMS, Slack, Webhook, WebSocket
- **Flexible Alarm Conditions** - Greater than, less than, in range, out of range, and more
- **Alarm Lifecycle Management** - Create, acknowledge, clear, suppress alarms
- **Real-time WebSocket Updates** - Instant notifications in the GUI
- **Throttling & Rate Limiting** - Prevent notification flooding
- **Alarm History** - Track all alarm events

### Architecture

```
Equipment Readings → Equipment Manager → Alarm Integrator → Alarm Manager → Notifications
                                              ↓
                                        Check Conditions
                                              ↓
                                    Trigger/Clear Alarms
                                              ↓
                              Email | SMS | Slack | Webhook | WebSocket
```

---

## Quick Start

### 1. Create Your First Alarm

```python
import requests

# Create a voltage alarm for a power supply
alarm_config = {
    "name": "High Voltage Alert",
    "description": "Alert when PSU voltage exceeds 12V",
    "equipment_id": "PSU_001",
    "parameter": "voltage",
    "condition": "greater_than",
    "threshold": 12.0,
    "severity": "warning",
    "enabled": True,
    "notification_methods": ["email", "websocket", "slack"]
}

response = requests.post(
    "http://localhost:8000/api/alarms/create",
    json=alarm_config
)

alarm = response.json()
print(f"Created alarm: {alarm['alarm_id']}")
```

### 2. Configure Notifications

```python
# Configure email and Slack notifications
notification_config = {
    "email_enabled": True,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_username": "your-email@gmail.com",
    "smtp_password": "your-app-password",
    "smtp_use_tls": True,
    "email_from": "lablink@example.com",
    "email_recipients": ["admin@example.com", "lab-team@example.com"],

    "slack_enabled": True,
    "slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",

    "webhook_enabled": True,
    "webhook_url": "https://your-server.com/api/alarm-webhook",
    "webhook_auth_token": "your-secret-token"
}

requests.post(
    "http://localhost:8000/api/alarms/notifications/configure",
    json=notification_config
)
```

### 3. Monitor Equipment

The alarm system automatically monitors equipment once configured:

1. Equipment readings are collected every second
2. Alarm conditions are evaluated
3. Alarms trigger when conditions are met
4. Notifications are sent via configured channels
5. Alarms clear automatically when conditions normalize

---

## Equipment Monitoring Integration

### How It Works

The `EquipmentAlarmIntegrator` automatically connects equipment readings to the alarm system:

```python
# Automatically initialized in main.py
# No manual setup required!

from alarm import initialize_integrator, alarm_manager
from equipment.manager import equipment_manager

# Initialize integrator (done at startup)
integrator = initialize_integrator(equipment_manager, alarm_manager)
await integrator.start_monitoring()
```

### Monitored Parameters

The integrator automatically extracts these parameters from equipment status:

| Parameter | Aliases | Description |
|-----------|---------|-------------|
| `voltage` | `v`, `volt` | Voltage reading (V) |
| `current` | `i`, `amp` | Current reading (A) |
| `power` | `p`, `watt` | Power reading (W) |
| `temperature` | `temp`, `t` | Temperature reading (°C) |
| Custom | Any | Equipment-specific parameters |

### Manual Check

You can also manually trigger alarm checks:

```python
# Check alarms for specific equipment immediately
await integrator.check_equipment_now("PSU_001")

# Get monitoring status
status = await integrator.get_monitoring_status()
print(f"Monitoring {status['monitored_equipment']}")
```

---

## Creating Alarms

### Alarm Types

```python
class AlarmType(str, Enum):
    THRESHOLD = "threshold"        # Value exceeds threshold
    DEVIATION = "deviation"        # Value deviates from setpoint
    SAFETY = "safety"             # Safety limit violation
    COMMUNICATION = "communication" # Equipment communication failure
    SYSTEM = "system"             # System-level alarm
    EQUIPMENT = "equipment"       # Equipment-specific alarm
    USER_DEFINED = "user_defined" # Custom alarm type
    SCHEDULED = "scheduled"       # Time-based alarm
```

### Alarm Conditions

```python
class AlarmCondition(str, Enum):
    GREATER_THAN = "greater_than"     # value > threshold
    LESS_THAN = "less_than"           # value < threshold
    EQUAL_TO = "equal_to"             # value == threshold (within deadband)
    NOT_EQUAL_TO = "not_equal_to"     # value != threshold
    IN_RANGE = "in_range"             # threshold_low <= value <= threshold_high
    OUT_OF_RANGE = "out_of_range"     # value < threshold_low OR value > threshold_high
    RISING_EDGE = "rising_edge"       # value crosses threshold upward
    FALLING_EDGE = "falling_edge"     # value crosses threshold downward
```

### Alarm Severities

```python
class AlarmSeverity(str, Enum):
    INFO = "info"           # Informational (blue)
    WARNING = "warning"     # Warning condition (yellow)
    ERROR = "error"         # Error condition (red)
    CRITICAL = "critical"   # Critical condition (purple)
```

### Example: Temperature Monitoring

```python
# Alert if equipment temperature exceeds safe operating range
temp_alarm = {
    "name": "Equipment Overtemperature",
    "description": "Equipment temperature exceeds 50°C",
    "equipment_id": "OSCILLOSCOPE_001",
    "parameter": "temperature",
    "condition": "greater_than",
    "threshold": 50.0,
    "severity": "error",
    "enabled": True,
    "notification_methods": ["email", "slack", "websocket"]
}

response = requests.post("http://localhost:8000/api/alarms/create", json=temp_alarm)
```

### Example: Current Range Monitoring

```python
# Alert if current is outside acceptable range (0.5A - 2.0A)
current_alarm = {
    "name": "Current Out of Range",
    "description": "Load current outside acceptable range",
    "equipment_id": "LOAD_001",
    "parameter": "current",
    "condition": "out_of_range",
    "threshold_low": 0.5,
    "threshold_high": 2.0,
    "severity": "warning",
    "enabled": True,
    "notification_methods": ["websocket", "webhook"]
}

response = requests.post("http://localhost:8000/api/alarms/create", json=current_alarm)
```

### Example: Power Supply Voltage Deviation

```python
# Alert if voltage deviates more than 0.1V from setpoint
voltage_alarm = {
    "name": "Voltage Deviation",
    "description": "PSU voltage deviation from setpoint",
    "equipment_id": "PSU_001",
    "parameter": "voltage",
    "condition": "not_equal_to",
    "threshold": 5.0,  # Setpoint
    "deadband": 0.1,   # ±0.1V tolerance
    "severity": "warning",
    "enabled": True,
    "notification_methods": ["websocket"]
}

response = requests.post("http://localhost:8000/api/alarms/create", json=voltage_alarm)
```

---

## Notification Channels

### Email Notifications

**Configuration:**

```python
{
    "email_enabled": True,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_username": "your-email@gmail.com",
    "smtp_password": "your-app-password",  # Use app-specific password
    "smtp_use_tls": True,
    "email_from": "lablink-alarms@example.com",
    "email_recipients": [
        "admin@example.com",
        "engineer@example.com",
        "oncall@example.com"
    ]
}
```

**Email Format:**
- Severity-colored HTML emails
- Plain text fallback
- Equipment details, parameter values, thresholds
- Direct links to acknowledge alarms

### Slack Notifications

**Setup:**
1. Create a Slack incoming webhook:
   - Go to https://api.slack.com/messaging/webhooks
   - Create a new webhook for your channel
   - Copy the webhook URL

2. Configure LabLink:

```python
{
    "slack_enabled": True,
    "slack_webhook_url": "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX"
}
```

**Slack Message Format:**
- Severity-colored attachments
- Equipment and parameter details
- Emoji indicators for severity levels
- Timestamp and event IDs

### Webhook Notifications

**Generic webhook for integration with custom systems:**

```python
{
    "webhook_enabled": True,
    "webhook_url": "https://your-server.com/api/alarms",
    "webhook_auth_token": "your-bearer-token"  # Optional
}
```

**Webhook Payload:**

```json
{
    "event_type": "alarm",
    "event_id": "event_abc123",
    "alarm_id": "alarm_xyz789",
    "alarm_name": "High Voltage Alert",
    "severity": "warning",
    "state": "active",
    "message": "Alarm: High Voltage Alert - voltage = 12.5",
    "equipment_id": "PSU_001",
    "parameter": "voltage",
    "value": 12.5,
    "threshold": 12.0,
    "triggered_at": "2025-01-15T14:30:00.123456",
    "description": "Alert when PSU voltage exceeds 12V"
}
```

**Authentication:**
- Bearer token sent in `Authorization` header
- Supports standard OAuth2/JWT patterns

### SMS Notifications

**Via Twilio:**

```python
{
    "sms_enabled": True,
    "sms_provider": "twilio",
    "sms_api_key": "your-twilio-account-sid",
    "sms_api_secret": "your-twilio-auth-token",
    "sms_from_number": "+1234567890",
    "sms_recipients": ["+1987654321", "+1555555555"]
}
```

### WebSocket Notifications

**Real-time updates to connected clients:**

```python
{
    "websocket_enabled": True  # Enabled by default
}
```

**Client Integration:**

```python
# JavaScript/TypeScript client
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'alarm') {
        console.log(`Alarm: ${data.alarm_name}`);
        console.log(`Severity: ${data.severity}`);
        console.log(`Equipment: ${data.equipment_id}`);
        // Update UI, show notification, etc.
    }
};
```

---

## Alarm Management

### List All Alarms

```python
response = requests.get("http://localhost:8000/api/alarms")
alarms = response.json()

for alarm in alarms:
    print(f"{alarm['name']}: {alarm['enabled']} ({alarm['severity']})")
```

### Get Active Events

```python
response = requests.get("http://localhost:8000/api/alarms/events/active")
events = response.json()

for event in events:
    print(f"Event {event['event_id']}: {event['message']}")
    print(f"  State: {event['state']}, Severity: {event['severity']}")
```

### Acknowledge Alarm

```python
ack_data = {
    "event_id": "event_abc123",
    "acknowledged_by": "john.doe",
    "note": "Investigating root cause"
}

response = requests.post(
    "http://localhost:8000/api/alarms/events/acknowledge",
    json=ack_data
)
```

### Clear Alarm

```python
response = requests.post(
    f"http://localhost:8000/api/alarms/{alarm_id}/clear"
)
```

### Enable/Disable Alarm

```python
# Disable alarm
requests.post(f"http://localhost:8000/api/alarms/{alarm_id}/disable")

# Enable alarm
requests.post(f"http://localhost:8000/api/alarms/{alarm_id}/enable")
```

### Update Alarm Configuration

```python
updated_config = {
    "alarm_id": alarm_id,
    "name": "Updated Alarm Name",
    "threshold": 15.0,  # New threshold
    "severity": "error",  # Increased severity
    "enabled": True
}

response = requests.put(
    f"http://localhost:8000/api/alarms/{alarm_id}",
    json=updated_config
)
```

### Delete Alarm

```python
response = requests.delete(f"http://localhost:8000/api/alarms/{alarm_id}")
```

### Get Alarm Statistics

```python
response = requests.get("http://localhost:8000/api/alarms/statistics")
stats = response.json()

print(f"Active alarms: {stats['total_active']}")
print(f"Acknowledged: {stats['total_acknowledged']}")
print(f"By severity: {stats['by_severity']}")
```

---

## API Reference

### Alarm Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/alarms/create` | Create new alarm |
| GET | `/api/alarms` | List all alarms |
| GET | `/api/alarms/{alarm_id}` | Get specific alarm |
| PUT | `/api/alarms/{alarm_id}` | Update alarm |
| DELETE | `/api/alarms/{alarm_id}` | Delete alarm |
| POST | `/api/alarms/{alarm_id}/enable` | Enable alarm |
| POST | `/api/alarms/{alarm_id}/disable` | Disable alarm |
| POST | `/api/alarms/check` | Manually check alarm |

### Event Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/alarms/events/active` | Get active events |
| GET | `/api/alarms/events` | Get event history |
| GET | `/api/alarms/events/{event_id}` | Get specific event |
| POST | `/api/alarms/events/acknowledge` | Acknowledge event |
| POST | `/api/alarms/{alarm_id}/clear` | Clear alarm |

### Configuration Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/alarms/notifications/configure` | Configure notifications |
| GET | `/api/alarms/notifications/config` | Get notification config |
| GET | `/api/alarms/statistics` | Get alarm statistics |

---

## Configuration Examples

### Production Email Configuration

```python
# Using Gmail with app-specific password
{
    "email_enabled": True,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_username": "lab-notifications@company.com",
    "smtp_password": "abcd efgh ijkl mnop",  # App-specific password
    "smtp_use_tls": True,
    "email_from": "LabLink Alarms <lablink@company.com>",
    "email_recipients": [
        "engineer1@company.com",
        "engineer2@company.com",
        "oncall@company.com"
    ],
    "throttle_minutes": 5,
    "max_notifications_per_hour": 10
}
```

### Multi-Channel Configuration

```python
# Email + Slack + Webhook for comprehensive alerting
{
    # Email
    "email_enabled": True,
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "smtp_username": "alerts@company.com",
    "smtp_password": "your-password",
    "smtp_use_tls": True,
    "email_recipients": ["team@company.com"],

    # Slack
    "slack_enabled": True,
    "slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",

    # Webhook (for PagerDuty, custom systems, etc.)
    "webhook_enabled": True,
    "webhook_url": "https://events.pagerduty.com/v2/enqueue",
    "webhook_auth_token": "your-pagerduty-integration-key",

    # WebSocket (for GUI)
    "websocket_enabled": True,

    # Throttling
    "throttle_minutes": 5,
    "max_notifications_per_hour": 20
}
```

---

## Best Practices

### 1. Alarm Design

✅ **DO:**
- Use descriptive alarm names
- Set appropriate severity levels
- Include equipment IDs for equipment-specific alarms
- Use reasonable thresholds based on equipment specs
- Enable only necessary notification channels
- Document alarm purposes in descriptions

❌ **DON'T:**
- Create too many alarms (alarm fatigue)
- Set overly sensitive thresholds
- Use CRITICAL severity for non-critical issues
- Forget to test alarms before production

### 2. Notification Strategy

**By Severity:**
- **INFO** - WebSocket only (GUI notifications)
- **WARNING** - WebSocket + Email
- **ERROR** - WebSocket + Email + Slack
- **CRITICAL** - All channels + SMS

**Example:**

```python
# Info alarm - GUI only
info_alarm = {
    "severity": "info",
    "notification_methods": ["websocket"]
}

# Critical alarm - all channels
critical_alarm = {
    "severity": "critical",
    "notification_methods": ["email", "sms", "slack", "webhook", "websocket"]
}
```

### 3. Throttling Configuration

Prevent notification flooding:

```python
{
    "throttle_minutes": 5,          # Minimum 5 minutes between same alarm
    "max_notifications_per_hour": 12 # Maximum 12 notifications per hour per alarm
}
```

### 4. Equipment Monitoring

**Automatic vs Manual:**
- Use automatic monitoring for real-time equipment parameters
- Use manual checks for calculated values or external triggers

```python
# Automatic - equipment readings trigger automatically
voltage_alarm = {
    "equipment_id": "PSU_001",
    "parameter": "voltage",
    "enabled": True  # Automatically monitors
}

# Manual - you trigger the check
response = requests.post(
    "http://localhost:8000/api/alarms/check",
    json={
        "alarm_id": alarm_id,
        "value": calculated_value
    }
)
```

### 5. Acknowledgment Workflow

```python
# When alarm triggers:
# 1. Receive notification
# 2. Investigate issue
# 3. Acknowledge alarm with notes
ack_data = {
    "event_id": event_id,
    "acknowledged_by": "john.doe",
    "note": "Power supply replaced, voltage normalized"
}

# 4. Monitor for clearance
# 5. Alarm clears automatically when condition resolves
```

---

## Troubleshooting

### Alarms Not Triggering

**Check:**
1. Is alarm enabled? `"enabled": true`
2. Is equipment ID correct?
3. Is equipment connected and reporting status?
4. Is parameter name correct? (use aliases: `v`, `volt`, `voltage`)
5. Is threshold appropriate?

**Debug:**

```python
# Check equipment status
response = requests.get(f"http://localhost:8000/api/equipment/{equipment_id}/status")
status = response.json()
print(f"Current voltage: {status.get('voltage')}")

# Check alarm configuration
response = requests.get(f"http://localhost:8000/api/alarms/{alarm_id}")
alarm = response.json()
print(f"Threshold: {alarm['threshold']}, Condition: {alarm['condition']}")

# Check integrator status
response = requests.get("http://localhost:8000/api/alarms/integrator/status")
print(response.json())
```

### Notifications Not Sending

**Email:**
- Verify SMTP credentials
- Check firewall/network access to SMTP server
- Use app-specific passwords for Gmail
- Check spam folder

**Slack:**
- Verify webhook URL is correct
- Test webhook with curl:
  ```bash
  curl -X POST -H 'Content-Type: application/json' \
    -d '{"text":"Test message"}' \
    YOUR_WEBHOOK_URL
  ```

**Webhook:**
- Verify endpoint URL is accessible
- Check authentication token
- Monitor server logs for errors

### Too Many Notifications

**Adjust Throttling:**

```python
{
    "throttle_minutes": 10,         # Increase minimum time between
    "max_notifications_per_hour": 5  # Decrease maximum per hour
}
```

**Or disable alarm temporarily:**

```python
requests.post(f"http://localhost:8000/api/alarms/{alarm_id}/disable")
```

---

## Quick Reference Commands

### cURL Examples

```bash
# Create alarm
curl -X POST http://localhost:8000/api/alarms/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Alarm",
    "equipment_id": "PSU_001",
    "parameter": "voltage",
    "condition": "greater_than",
    "threshold": 12.0,
    "severity": "warning",
    "enabled": true
  }'

# Get active alarms
curl http://localhost:8000/api/alarms/events/active

# Acknowledge alarm
curl -X POST http://localhost:8000/api/alarms/events/acknowledge \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "event_123",
    "acknowledged_by": "user",
    "note": "Investigating"
  }'

# Configure Slack notifications
curl -X POST http://localhost:8000/api/alarms/notifications/configure \
  -H "Content-Type: application/json" \
  -d '{
    "slack_enabled": true,
    "slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK"
  }'
```

---

## Support

For issues or questions:
1. Check logs: `logs/lablink.log`, `logs/alarm.log`
2. Review equipment status
3. Verify alarm configuration
4. Test notification channels independently
5. Check network connectivity
6. Review API endpoint responses

---

**Version:** 0.11.0
**Repository:** https://github.com/X9X0/LabLink
**Documentation:** See `docs/` directory
