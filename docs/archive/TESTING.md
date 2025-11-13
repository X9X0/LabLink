# LabLink Testing Guide

This guide helps you test and verify the LabLink system.

## Quick Verification

Run the demo test to verify all files are in place:

```bash
python3 demo_test.py
```

This will check:
- ✓ All API files present (111 endpoints across 10 files)
- ✓ All client UI components
- ✓ Model definitions
- ✓ API client methods (19+ methods)
- ✓ Code statistics (20,670+ lines)

## Full System Test

### Prerequisites

1. **Install Server Dependencies:**
   ```bash
   cd server
   pip install -r requirements.txt
   ```

2. **Install Client Dependencies:**
   ```bash
   cd client
   pip install -r requirements.txt
   ```

### Testing the Server

1. **Start the server:**
   ```bash
   cd server
   python3 main.py
   ```

2. **Verify server is running:**
   - Open browser to `http://localhost:8000`
   - Should see: `{"name": "LabLink Server", "version": "0.10.0", "status": "running"}`

3. **Test API documentation:**
   - Open browser to `http://localhost:8000/docs`
   - Interactive API documentation should load

4. **Test health endpoint:**
   ```bash
   curl http://localhost:8000/health
   ```
   - Should return: `{"status": "healthy", "connected_devices": 0}`

### Testing the Client

**Note:** The GUI client requires a display. In WSL, you'll need:
- WSLg (Windows 11) or
- X Server (VcXsrv, Xming) for Windows 10

1. **Set up display (if needed):**
   ```bash
   export DISPLAY=:0
   ```

2. **Start the client:**
   ```bash
   cd client
   python3 main.py
   ```

3. **Test connection:**
   - Connection dialog should appear
   - Click "Localhost" button
   - Click "Connect"
   - Status bar should show "Connected: localhost:8000"

4. **Test Equipment Panel:**
   - Click "Equipment" tab
   - Click "Refresh" button
   - Equipment list should update (may be empty without hardware)
   - Click "Discover" to scan for equipment

5. **Test Acquisition Panel:**
   - Click "Data Acquisition" tab
   - Select equipment from dropdown (if available)
   - Configure acquisition settings
   - Click "Start Acquisition"

6. **Test Alarms Panel:**
   - Click "Alarms" tab
   - Should show active alarms table
   - Click "Refresh" to update

7. **Test Scheduler Panel:**
   - Click "Scheduler" tab
   - Should show scheduled jobs table
   - Click "Refresh" to update

8. **Test Diagnostics Panel:**
   - Click "Diagnostics" tab
   - Click "Refresh" to see equipment health
   - Click "Run Full Diagnostics" for comprehensive report

## API Testing with curl

### Equipment Endpoints

```bash
# List all equipment
curl http://localhost:8000/api/equipment

# Get specific equipment
curl http://localhost:8000/api/equipment/{equipment_id}

# Connect to equipment
curl -X POST http://localhost:8000/api/equipment/{equipment_id}/connect
```

### Data Acquisition Endpoints

```bash
# Create acquisition session
curl -X POST http://localhost:8000/api/acquisition/create \
  -H "Content-Type: application/json" \
  -d '{"equipment_id": "eq_123", "mode": "continuous", "sample_rate_hz": 1000}'

# Start acquisition
curl -X POST http://localhost:8000/api/acquisition/{acquisition_id}/start

# Stop acquisition
curl -X POST http://localhost:8000/api/acquisition/{acquisition_id}/stop
```

### Alarm Endpoints

```bash
# List alarms
curl http://localhost:8000/api/alarms

# Get active alarm events
curl http://localhost:8000/api/alarms/events/active

# Acknowledge alarm
curl -X POST http://localhost:8000/api/alarms/events/acknowledge \
  -H "Content-Type: application/json" \
  -d '{"event_id": "event_123"}'
```

### Scheduler Endpoints

```bash
# List scheduled jobs
curl http://localhost:8000/api/scheduler/jobs

# Create job
curl -X POST http://localhost:8000/api/scheduler/jobs/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Job",
    "schedule_type": "acquisition",
    "trigger_type": "interval",
    "interval_seconds": 60,
    "equipment_id": "eq_123"
  }'

# Run job now
curl -X POST http://localhost:8000/api/scheduler/jobs/{job_id}/run
```

### Diagnostics Endpoints

```bash
# Get equipment health
curl http://localhost:8000/api/diagnostics/health/{equipment_id}

# Get all equipment health
curl http://localhost:8000/api/diagnostics/health

# Run benchmark
curl -X POST http://localhost:8000/api/diagnostics/benchmark/{equipment_id}

# Generate diagnostic report
curl -X POST http://localhost:8000/api/diagnostics/report
```

## Verification Scripts

### Test Server Startup

```python
import requests

try:
    response = requests.get("http://localhost:8000/health", timeout=5)
    if response.status_code == 200:
        print("✓ Server is running")
        print(f"  Response: {response.json()}")
    else:
        print(f"✗ Server returned status {response.status_code}")
except requests.exceptions.ConnectionError:
    print("✗ Cannot connect to server")
except Exception as e:
    print(f"✗ Error: {e}")
```

### Test Client API

```python
import sys
sys.path.insert(0, "client")

from api.client import LabLinkClient

client = LabLinkClient("localhost", 8000, 8001)

if client.connect():
    print("✓ Connected to server")

    # Get server info
    info = client.get_server_info()
    print(f"  Server: {info['name']} v{info['version']}")

    # Test health check
    health = client.health_check()
    print(f"  Health: {health['status']}")

    # List equipment
    equipment = client.list_equipment()
    print(f"  Equipment count: {len(equipment)}")
else:
    print("✗ Failed to connect")
```

## Known Issues

### WSL Display Issues

If GUI doesn't display in WSL:

1. **Windows 11 with WSLg:**
   - Should work out of the box
   - Run: `python3 client/main.py`

2. **Windows 10:**
   - Install X Server (VcXsrv or Xming)
   - Set DISPLAY: `export DISPLAY=:0`
   - May have font/rendering issues

### Missing Dependencies

If you see import errors:

```bash
# Server dependencies
cd server && pip install -r requirements.txt

# Client dependencies
cd client && pip install -r requirements.txt
```

### Hardware Not Found

Without actual laboratory equipment:
- Server will run but show no devices
- Use API simulation mode (if implemented)
- Test with mock equipment drivers

## Performance Testing

### API Response Times

```bash
# Test multiple requests
for i in {1..10}; do
  time curl -s http://localhost:8000/health > /dev/null
done
```

### Load Testing

Use tools like `ab` (Apache Bench) or `wrk`:

```bash
# Install ab
sudo apt install apache2-utils

# Test health endpoint
ab -n 1000 -c 10 http://localhost:8000/health
```

## Continuous Testing

### Automated Test Suite

Create a test suite that:
1. Starts server
2. Waits for startup
3. Runs API tests
4. Checks responses
5. Shuts down server

Example script:

```bash
#!/bin/bash

# Start server in background
cd server
python3 main.py &
SERVER_PID=$!

# Wait for server to start
sleep 5

# Run tests
python3 ../test_api.py

# Stop server
kill $SERVER_PID
```

## Troubleshooting

### Server won't start

- Check if port 8000 is already in use:
  ```bash
  lsof -i :8000
  ```
- Kill existing process:
  ```bash
  kill $(lsof -t -i:8000)
  ```

### Client won't connect

- Verify server is running: `curl http://localhost:8000/health`
- Check firewall settings
- Try 127.0.0.1 instead of localhost

### Import errors

- Verify Python version: `python3 --version` (need 3.11+)
- Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`

## Success Criteria

A successful test should show:

- ✓ Server starts without errors
- ✓ Server responds to health checks
- ✓ API documentation accessible
- ✓ Client GUI launches (if display available)
- ✓ Client connects to server
- ✓ All panels load without errors
- ✓ API endpoints return expected responses
- ✓ No Python exceptions in logs

## Next Steps

After successful testing:

1. Connect real laboratory equipment
2. Configure equipment drivers
3. Test data acquisition with real devices
4. Set up alarms for your specific needs
5. Create scheduled jobs
6. Monitor equipment health

## Support

For issues:
- Check logs: `server/lablink_server.log` and `client/lablink_client.log`
- Review documentation in `docs/` directory
- Check GitHub issues
