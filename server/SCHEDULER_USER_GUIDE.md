# Scheduled Operations User Guide

## Overview

The LabLink Scheduled Operations system provides automated, cron-like scheduling of equipment operations with SQLite persistence, conflict detection, and integration with alarms and equipment profiles.

**Key Features:**
- **Persistent Scheduling**: Jobs survive server restarts
- **Cron-like Flexibility**: Support for cron expressions, intervals, daily, weekly, monthly schedules
- **Conflict Detection**: Handle overlapping job executions with configurable policies
- **Alarm Integration**: Automatic alerts on job failures
- **Profile Integration**: Apply equipment profiles before job execution
- **Comprehensive History**: Track all job executions with statistics

---

## Quick Start

### 1. Create a Simple Scheduled Job

Schedule a measurement every hour:

```python
POST /api/scheduler/jobs/create
{
  "name": "Hourly Voltage Check",
  "description": "Measure output voltage every hour",
  "schedule_type": "measurement",
  "equipment_id": "power_supply_1",
  "trigger_type": "interval",
  "interval_hours": 1,
  "parameters": {
    "command": "get_voltage"
  },
  "enabled": true
}
```

### 2. Create a Cron-based Job

Run diagnostics every day at 3 AM:

```python
POST /api/scheduler/jobs/create
{
  "name": "Nightly Equipment Test",
  "schedule_type": "equipment_test",
  "equipment_id": "oscilloscope_1",
  "trigger_type": "daily",
  "time_of_day": "03:00:00",
  "parameters": {
    "test_name": "connection"
  },
  "on_failure_alarm": true
}
```

---

## Job Types

### 1. ACQUISITION
Start a data acquisition session:
```json
{
  "schedule_type": "acquisition",
  "equipment_id": "oscilloscope_1",
  "parameters": {
    "duration": 60,
    "sample_rate": 1000,
    "channels": [1, 2]
  }
}
```

### 2. STATE_CAPTURE
Capture equipment state:
```json
{
  "schedule_type": "state_capture",
  "equipment_id": "power_supply_1"
}
```

### 3. MEASUREMENT
Take a single measurement:
```json
{
  "schedule_type": "measurement",
  "equipment_id": "multimeter_1",
  "parameters": {
    "command": "get_voltage"
  }
}
```

### 4. COMMAND
Execute equipment command:
```json
{
  "schedule_type": "command",
  "equipment_id": "load_1",
  "parameters": {
    "command": "set_current",
    "parameters": {"value": 2.5}
  }
}
```

### 5. EQUIPMENT_TEST
Run diagnostic tests:
```json
{
  "schedule_type": "equipment_test",
  "equipment_id": "power_supply_1",
  "parameters": {
    "test_name": "self_test"
  }
}
```

---

## Trigger Types

### CRON
Use cron expressions for complex schedules:
```json
{
  "trigger_type": "cron",
  "cron_expression": "0 */6 * * *"  // Every 6 hours
}
```

**Common cron patterns:**
- `0 * * * *` - Every hour
- `0 0 * * *` - Daily at midnight
- `*/15 * * * *` - Every 15 minutes
- `0 9-17 * * 1-5` - 9 AM to 5 PM on weekdays

### INTERVAL
Run at fixed intervals:
```json
{
  "trigger_type": "interval",
  "interval_minutes": 30  // or interval_seconds, interval_hours, interval_days
}
```

### DAILY
Run daily at specific time:
```json
{
  "trigger_type": "daily",
  "time_of_day": "14:30:00"
}
```

### WEEKLY
Run weekly on specific day:
```json
{
  "trigger_type": "weekly",
  "day_of_week": 1,  // 0=Monday, 6=Sunday
  "time_of_day": "09:00:00"
}
```

### MONTHLY
Run monthly on specific day:
```json
{
  "trigger_type": "monthly",
  "day_of_month": 15,
  "time_of_day": "12:00:00"
}
```

### DATE
One-time execution:
```json
{
  "trigger_type": "date",
  "run_date": "2025-12-25T10:00:00"
}
```

---

## Advanced Features

### 1. Conflict Detection & Resolution

Handle overlapping job executions:

**Skip Policy** (default):
```json
{
  "conflict_policy": "skip"  // Skip if job already running
}
```

**Queue Policy**:
```json
{
  "conflict_policy": "queue"  // Wait for current execution to finish
}
```

**Replace Policy**:
```json
{
  "conflict_policy": "replace"  // Allow concurrent executions (uses max_instances)
}
```

### 2. Equipment Profile Integration

Apply equipment profiles before execution:

```json
{
  "schedule_type": "acquisition",
  "equipment_id": "oscilloscope_1",
  "profile_id": "high_resolution_profile",
  "parameters": {
    "duration": 300
  }
}
```

The profile will be automatically applied before the job runs.

### 3. Alarm Integration

Create alarms on job failures:

```json
{
  "name": "Critical Measurement",
  "schedule_type": "measurement",
  "equipment_id": "sensor_1",
  "on_failure_alarm": true  // Create alarm if job fails
}
```

Failure alarms include:
- Job name and ID
- Error details
- Equipment information
- Execution timestamp

### 4. Execution Limits

Limit total job executions:

```json
{
  "name": "One-time Daily Test",
  "trigger_type": "daily",
  "time_of_day": "09:00:00",
  "max_executions": 30,  // Stop after 30 runs
  "start_date": "2025-11-01T00:00:00",
  "end_date": "2025-12-01T00:00:00"
}
```

---

## API Reference

### Job Management

#### Create Job
`POST /api/scheduler/jobs/create`

#### Get Job
`GET /api/scheduler/jobs/{job_id}`

#### List Jobs
`GET /api/scheduler/jobs?enabled=true`

#### Delete Job
`DELETE /api/scheduler/jobs/{job_id}`

#### Pause Job
`POST /api/scheduler/jobs/{job_id}/pause`

#### Resume Job
`POST /api/scheduler/jobs/{job_id}/resume`

#### Run Job Now
`POST /api/scheduler/jobs/{job_id}/run`

### Execution Tracking

#### Get Execution
`GET /api/scheduler/executions/{execution_id}`

#### List Executions
`GET /api/scheduler/executions?job_id={job_id}&limit=100`

#### Get Job History
`GET /api/scheduler/jobs/{job_id}/history`

Returns:
- Total executions
- Success/failure counts
- Average duration
- Last execution time
- Next scheduled run

### Statistics

#### Get Scheduler Statistics
`GET /api/scheduler/statistics`

Returns:
- Total/active/disabled jobs
- Running executions
- Today's execution counts
- Jobs by type
- Upcoming jobs (next 10)

#### Get Running Jobs
`GET /api/scheduler/running`

Returns list of currently executing job IDs.

---

## Best Practices

### 1. Job Naming
Use descriptive, searchable names:
```
✅ "Hourly PSU Voltage Check"
✅ "Nightly Equipment Diagnostics"
❌ "Job 1"
❌ "Test"
```

### 2. Execution Time Selection
- **Avoid peak hours** for resource-intensive jobs
- **Stagger schedules** to prevent conflicts
- **Use cron for complex patterns** instead of multiple jobs

### 3. Error Handling
- Enable `on_failure_alarm` for critical jobs
- Monitor job history regularly
- Use `conflict_policy: "queue"` for must-not-skip jobs

### 4. Resource Management
```json
{
  "max_instances": 1,  // Prevent concurrent runs
  "misfire_grace_time": 300,  // 5 minutes grace for missed runs
  "coalesce": true  // Combine missed runs into one
}
```

### 5. Testing
Before deploying:
1. Create job with `enabled: false`
2. Test with "Run Job Now"
3. Verify execution results
4. Enable job

---

## Troubleshooting

### Job Not Running

**Check job status:**
```bash
GET /api/scheduler/jobs/{job_id}
```

**Common issues:**
- `enabled: false` - Job is paused
- Invalid trigger configuration
- Equipment not connected
- Max executions reached

**View job history:**
```bash
GET /api/scheduler/jobs/{job_id}/history
```

### Jobs Skipped

**Cause**: Conflict policy set to "skip" and job already running

**Solution**:
- Change to `conflict_policy: "queue"`
- Increase job duration
- Adjust schedule frequency

### High Failure Rate

**Check execution history:**
```bash
GET /api/scheduler/executions?job_id={job_id}
```

**Common causes:**
- Equipment offline
- Invalid parameters
- Profile application failure
- Insufficient permissions

---

## Persistence & Reliability

### Database Storage
Jobs are stored in SQLite database (`data/scheduler.db`):
- **Jobs table**: All job configurations
- **Executions table**: Execution history (30-day retention)
- **Execution counts**: Total execution tracking

### Server Restart Behavior
- All jobs automatically restored on startup
- Enabled jobs resume scheduling
- Execution history preserved
- No data loss

### Cleanup
Execution records older than 30 days are automatically cleaned up daily.

**Manual cleanup:**
```python
from scheduler.storage import SchedulerStorage
storage = SchedulerStorage()
deleted = storage.cleanup_old_executions(days=30)
```

---

## Examples

### Example 1: Automated Nightly Backup

```json
{
  "name": "Nightly Equipment State Backup",
  "schedule_type": "state_capture",
  "equipment_id": "power_supply_1",
  "trigger_type": "daily",
  "time_of_day": "02:00:00",
  "on_failure_alarm": true,
  "tags": ["backup", "critical"]
}
```

### Example 2: Periodic Equipment Health Check

```json
{
  "name": "4-Hour Equipment Health Check",
  "schedule_type": "equipment_test",
  "equipment_id": "oscilloscope_1",
  "trigger_type": "interval",
  "interval_hours": 4,
  "parameters": {
    "test_name": "connection"
  },
  "conflict_policy": "skip",
  "on_failure_alarm": true
}
```

### Example 3: Scheduled Acquisition with Profile

```json
{
  "name": "Weekly High-Resolution Waveform Capture",
  "schedule_type": "acquisition",
  "equipment_id": "scope_1",
  "profile_id": "high_res_1GS",
  "trigger_type": "weekly",
  "day_of_week": 1,
  "time_of_day": "08:00:00",
  "parameters": {
    "duration": 600,
    "sample_rate": 1000000,
    "channels": [1, 2, 3, 4]
  },
  "on_failure_alarm": true,
  "tags": ["weekly-report", "high-priority"]
}
```

### Example 4: Business Hours Monitoring

```json
{
  "name": "Business Hours Load Testing",
  "schedule_type": "command",
  "equipment_id": "load_1",
  "trigger_type": "cron",
  "cron_expression": "0 9-17 * * 1-5",  // 9 AM - 5 PM, Mon-Fri
  "parameters": {
    "command": "run_load_test",
    "parameters": {"duration": 60, "current": 5.0}
  },
  "conflict_policy": "queue"
}
```

---

## Integration with Other Systems

### With Alarms
Jobs can automatically create alarms on failure:
```json
{
  "on_failure_alarm": true
}
```

Alarms include full execution context and can trigger notifications.

### With Profiles
Apply pre-configured equipment settings:
```json
{
  "profile_id": "profile_name"
}
```

Profile is applied before job execution starts.

### With Acquisition System
Schedule automated data collection:
```json
{
  "schedule_type": "acquisition",
  "parameters": {
    "duration": 300,
    "format": "csv"
  }
}
```

Acquisitions are created and started automatically.

---

## Monitoring Dashboard

Track scheduler health:

1. **Active Jobs**: `GET /api/scheduler/jobs?enabled=true`
2. **Running Jobs**: `GET /api/scheduler/running`
3. **Today's Stats**: `GET /api/scheduler/statistics`
4. **Recent Failures**: `GET /api/scheduler/executions` (filter by status)

---

## Support

For issues or questions:
- Check execution history for error details
- Review job configuration
- Verify equipment connectivity
- Check alarm system for failure notifications
- Examine server logs for detailed error traces

**Database Location**: `data/scheduler.db`
**Log Tag**: `scheduler`
