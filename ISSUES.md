# Known Issues - LabLink

## Server-Side Issues

### 1. Alarm Events Endpoint Route Matching (Priority: High) - ✅ LIKELY RESOLVED

**Issue**: The `/api/alarms/events` endpoint was returning 404 due to incorrect route ordering.

**Location**: `/home/user/LabLink/server/api/alarms.py:295-339`

**Status**: ✅ **CODE FIXED** - Routes are now correctly ordered (as of commit 8449012)

**Details**:
- ✅ Fixed route ordering by moving `/alarms/events` before `/alarms/events/{event_id}` (commit 8449012)
- ✅ Code inspection confirms routes are in correct order
- ✅ All required methods exist in alarm manager
- ⚠️ May require clean server restart to clear Python bytecode cache

**Resolution Steps** (if issue persists):
1. **Stop the server** completely
2. **Clear Python cache**:
   ```bash
   find server -type d -name __pycache__ -exec rm -rf {} +
   find server -name '*.pyc' -delete
   ```
3. **Restart server** in clean environment:
   ```bash
   python -m server.main
   ```
4. **Verify with test script**:
   ```bash
   python verify_endpoints.py
   ```

**Verification**:
- Run `python verify_endpoints.py` to test all problematic endpoints
- Should now return 200 with proper JSON response
- `/api/alarms/statistics` should also work

**Impact** (if still broken):
- Alarm history feature in GUI cannot retrieve historical events
- Statistics display unavailable

**Root Cause**: FastAPI route ordering (generic routes must come before parameterized routes). This has been fixed in the code.

---

### 2. Job Creation Validation (Priority: Medium) - ✅ RESOLVED

**Issue**: Creating jobs via `/api/scheduler/jobs/create` was returning 422 Unprocessable Entity

**Location**: Test scripts and client API

**Status**: ✅ **RESOLVED** - Issue was incorrect test payload format

**Root Cause**:
- Test payload was using nested structure with `job_config` wrapper
- API expects flat structure with direct fields
- This was a **test issue**, not a server issue

**Correct Payload Format**:
```json
{
  "name": "test_job",
  "schedule_type": "measurement",  // One of: acquisition, state_capture, equipment_test, measurement, command, script
  "trigger_type": "interval",      // One of: cron, interval, date, daily, weekly, monthly
  "interval_seconds": 3600,        // Required for interval trigger
  "equipment_id": "equipment_123", // Optional
  "parameters": {},                // Optional job-specific params
  "enabled": false                 // Optional, defaults to true
}
```

**Incorrect Payload Format** (was causing 422):
```json
{
  "job_config": {  // ❌ Don't wrap in job_config!
    "name": "test_job",
    ...
  }
}
```

**Required Fields** (vary by trigger type):
- **Always required**: `name`, `schedule_type`, `trigger_type`
- **CRON trigger**: `cron_expression`
- **INTERVAL trigger**: One of `interval_seconds`, `interval_minutes`, `interval_hours`, `interval_days`
- **DATE trigger**: `run_date`
- **DAILY trigger**: `time_of_day`
- **WEEKLY trigger**: `time_of_day`, `day_of_week`
- **MONTHLY trigger**: `time_of_day`, `day_of_month`

**Verification**:
- Run `python verify_endpoints.py` - now uses correct payload format
- Server API is correctly implemented
- Client API should use flat structure, not nested

---

## Client-Side Issues

### None Currently

All client-side code has been implemented successfully:
- ✅ Alarm history loading UI
- ✅ Job pause/resume functionality
- ✅ Job deletion functionality
- ✅ Client API methods for all new features

---

## Testing Status

### Completed
- ✅ Server connectivity
- ✅ Scheduler statistics endpoint
- ✅ Active alarms endpoint
- ✅ Job listing endpoint

### Blocked
- ❌ Alarm history retrieval (endpoint 404)
- ❌ Alarm statistics (endpoint 404)
- ❌ Job creation (validation error)

### Not Tested
- ⏳ Job pause/resume
- ⏳ Job deletion
- ⏳ GUI integration with live data

---

## Resolution Priority

1. **High**: Fix alarm events endpoint routing issue
2. **Medium**: Fix job creation validation
3. **Low**: Complete end-to-end GUI testing

---

*Last Updated: 2025-11-10*
