# Known Issues - LabLink

## Server-Side Issues

### 1. Alarm Events Endpoint Route Matching (Priority: High)

**Issue**: The `/api/alarms/events` endpoint returns 404 "Alarm events not found" despite the route being defined.

**Location**: `/home/x9x0/LabLink/server/api/alarms.py:295-339`

**Details**:
- Fixed route ordering by moving `/alarms/events` before `/alarms/events/{event_id}`
- However, still getting 404 errors with message "Alarm events not found"
- Error message doesn't exist in current codebase, suggesting bytecode caching issue
- `/api/alarms/statistics` has same issue

**Attempted Fixes**:
- Cleared `__pycache__` directories
- Restarted server multiple times
- Route order corrected (generic before parameterized)

**Workaround**: None currently. The endpoint exists but FastAPI is not routing to it correctly.

**Impact**:
- Alarm history feature in GUI cannot retrieve historical events
- Statistics display unavailable

**Next Steps**:
1. Check if there's an older version of alarms.py being imported
2. Verify Python module import paths
3. Consider renaming the function to force reimport
4. Check if there are duplicate route definitions

---

### 2. Job Creation Validation (Priority: Medium)

**Issue**: Creating jobs via `/api/scheduler/jobs/create` returns 422 Unprocessable Entity

**Location**: Test script shows validation errors

**Details**:
- Scheduler job creation requires specific schema validation
- Test payload may be missing required fields or using incorrect format

**Impact**: Cannot test job creation from client GUI

**Next Steps**:
- Check scheduler API schema requirements
- Verify job_config payload matches expected format

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
