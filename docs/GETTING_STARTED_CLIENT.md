# LabLink GUI Client - Getting Started Guide

**For New Users** - A complete walkthrough of using the LabLink desktop client for the first time.

## 📋 What You'll Learn

By the end of this guide, you'll be able to:
- Install and launch the LabLink GUI client
- Connect to a LabLink server
- View and control laboratory equipment
- Monitor alarms and notifications
- Run data acquisition
- View equipment diagnostics

---

## 🎯 Step 1: Install Dependencies

### Option A: Automatic Installation (Recommended)

LabLink includes an automated installation script:

```bash
# From the LabLink root directory
cd LabLink
./install-client.sh
```

This script will:
- Install all Python dependencies
- Create a desktop shortcut (Linux/macOS)
- Set up the environment

### Option B: Manual Installation

If you prefer to install manually:

```bash
# Navigate to client directory
cd LabLink/client

# Install dependencies
pip install -r requirements.txt

# Or use a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Dependencies installed:**
- PyQt6 (GUI framework)
- pyqtgraph (real-time plotting)
- requests (HTTP communication)
- websockets (real-time data streaming)
- numpy, pandas (data handling)
- And more...

---

## 🚀 Step 2: Start the Server (If Not Running)

Before launching the client, you need a LabLink server running.

### Check if Server is Running

```bash
curl http://localhost:8000/health
```

If you get a response like `{"status":"healthy"}`, the server is running!

### Start the Server

If the server isn't running:

```bash
# From LabLink root directory
cd server
python main.py
```

You should see:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

**Keep this terminal open!** The server needs to stay running.

---

## 💻 Step 3: Launch the GUI Client

Open a **new terminal** and run:

```bash
cd LabLink/client
python main.py
```

### What Happens Next?

1. **Application Window Opens** - You'll see the LabLink main window
2. **Connection Dialog Appears** - A dialog box will pop up asking you to connect to a server

---

## 🔌 Step 4: Connect to the Server

You'll see the **"Connect to LabLink Server"** dialog with these options:

### Quick Connect (Recommended for First-Time Users)

1. **Server Hostname:** `localhost` (already filled in)
2. **HTTP Port:** `8000` (default)
3. **WebSocket Port:** `8000` (default)
4. Click **"Connect"**

![Connection Dialog]
```
┌─────────────────────────────────────┐
│  Connect to LabLink Server          │
├─────────────────────────────────────┤
│  Server: [localhost        ]        │
│  HTTP Port: [8000]                  │
│  WS Port:   [8000]                  │
│                                     │
│  [ Localhost ] [ Connect ] [Cancel] │
└─────────────────────────────────────┘
```

### Connection Successful!

You should see:
- ✅ Green connection indicator in the status bar
- "Connected to localhost:8000" message
- Tabs become active (Equipment, Acquisition, Alarms, etc.)

### Troubleshooting Connection Issues

**❌ "Connection Failed"**
- Is the server running? Check Step 2
- Firewall blocking the connection?
- Try: `curl http://localhost:8000/health`

**❌ "Connection Refused"**
- Server not started
- Wrong port number
- Run: `python server/main.py`

---

## 🛠️ Step 5: Explore the Interface

Once connected, you'll see **5 main tabs**:

### 1. Equipment Tab (Default View)

This is where you manage your laboratory equipment.

**What You'll See:**
```
┌───────────────────────────────────────────────────────┐
│  Equipment                                            │
├───────────────────────────────────────────────────────┤
│  [Refresh] [Connect] [Disconnect]                     │
│                                                       │
│  ┌──────────────────────────────────────────────┐   │
│  │ Equipment ID  │ Type        │ Status         │   │
│  ├──────────────────────────────────────────────┤   │
│  │ rigol_mso     │ Oscilloscope│ Disconnected   │   │
│  │ bk_9206b      │ Power Supply│ Disconnected   │   │
│  │ rigol_dl3021  │ E-Load      │ Disconnected   │   │
│  └──────────────────────────────────────────────┘   │
│                                                       │
│  SCPI Command: [*IDN?                           ]    │
│  [Send Command]                                       │
│                                                       │
│  Response:                                            │
│  ┌──────────────────────────────────────────────┐   │
│  │                                                │   │
│  └──────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

**Try This:**
1. Click **"Refresh"** to load equipment from the server
2. Select an equipment row
3. Click **"Connect"** to connect to the equipment
4. Type `*IDN?` in the SCPI Command box
5. Click **"Send Command"** to query the device

### 2. Data Acquisition Tab

Configure and run data acquisition sessions.

**Features:**
- Start/stop continuous data acquisition
- Configure sample rate and duration
- View real-time plots
- Export data to CSV/HDF5

**Try This:**
1. Select a connected equipment
2. Set sample rate (e.g., 1 Hz)
3. Click **"Start Acquisition"**
4. Watch the real-time plot update!

### 3. Alarms Tab

Monitor equipment alarms and notifications.

**What You'll See:**
```
┌───────────────────────────────────────────────────────┐
│  Alarms                                               │
├───────────────────────────────────────────────────────┤
│  [All] [Active] [Critical]                            │
│                                                       │
│  ┌──────────────────────────────────────────────┐   │
│  │ ⚠️ CRITICAL: Voltage exceeded limit          │   │
│  │ Equipment: bk_9206b                           │   │
│  │ Time: 2025-11-15 14:30:22                     │   │
│  │ [Acknowledge]                                 │   │
│  └──────────────────────────────────────────────┘   │
│                                                       │
│  ┌──────────────────────────────────────────────┐   │
│  │ ⚠️ WARNING: High temperature                  │   │
│  │ Equipment: rigol_dl3021                       │   │
│  │ Time: 2025-11-15 14:28:15                     │   │
│  │ [Acknowledge]                                 │   │
│  └──────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

**Try This:**
1. View active alarms
2. Click **"Acknowledge"** to acknowledge an alarm
3. Filter by severity (All/Active/Critical)

### 4. Scheduler Tab

View and manage scheduled operations.

**Features:**
- View scheduled jobs
- Manually trigger jobs
- View job execution history
- Create new scheduled tasks

### 5. Diagnostics Tab

Monitor equipment health and performance.

**Features:**
- Equipment health scores (0-100)
- Performance benchmarks
- Communication statistics
- System resource monitoring

---

## 🎮 Step 6: Your First Equipment Control

Let's walk through a **complete example** of controlling a power supply:

### Example: Turn on BK Precision 9206B Power Supply

1. **Go to Equipment Tab**
2. **Click "Refresh"** to load equipment
3. **Select "bk_9206b"** from the list
4. **Click "Connect"**
   - Status changes to "Connected" ✅
5. **Set Voltage:** Type in SCPI command box:
   ```
   VOLT 5.0
   ```
   Click "Send Command"
6. **Turn on Output:**
   ```
   OUTP ON
   ```
   Click "Send Command"
7. **Read Current:**
   ```
   MEAS:CURR?
   ```
   Click "Send Command"
   - Response shows current reading (e.g., `0.125`)

### Common SCPI Commands

| Equipment | Command | Purpose |
|-----------|---------|---------|
| Power Supply | `VOLT 12.0` | Set voltage to 12V |
| Power Supply | `CURR 0.5` | Set current limit to 0.5A |
| Power Supply | `OUTP ON` | Turn output on |
| Power Supply | `OUTP OFF` | Turn output off |
| Power Supply | `MEAS:VOLT?` | Read voltage |
| Power Supply | `MEAS:CURR?` | Read current |
| Oscilloscope | `*IDN?` | Get device info |
| Oscilloscope | `:CHAN1:SCAL?` | Get channel 1 scale |
| E-Load | `CURR 1.0` | Set load current to 1A |
| E-Load | `INP ON` | Turn input on |

---

## 📊 Step 7: Run Data Acquisition

Let's collect some data from your equipment:

### Example: Monitor Power Supply Voltage

1. **Go to Acquisition Tab**
2. **Configuration:**
   - Equipment: Select "bk_9206b"
   - Channel: "voltage"
   - Sample Rate: 1 Hz (1 sample/second)
   - Duration: 60 seconds
3. **Click "Start Acquisition"**
4. **Watch the Plot:**
   - Real-time graph shows voltage over time
   - Statistics panel updates (min, max, avg)
5. **Export Data:**
   - Click "Export"
   - Choose format (CSV, HDF5, NumPy)
   - Save to your desired location

---

## 🔔 Step 8: Monitor Alarms

Set up alarm monitoring for safety:

### Example: Voltage Limit Alarm

1. **Go to Alarms Tab**
2. **Create New Alarm:**
   - Name: "Voltage Safety Limit"
   - Equipment: "bk_9206b"
   - Type: Threshold
   - Parameter: voltage
   - Limit: 15.0V
   - Severity: Critical
3. **Monitor:**
   - Alarm triggers if voltage > 15V
   - Red notification appears
   - (Optional) Email/SMS notification
4. **Acknowledge:**
   - Click "Acknowledge" to mark as seen

---

## ⚙️ Step 9: Advanced Features

### Multi-Server Support

Connect to multiple LabLink servers:

1. **Menu → File → Server Manager**
2. **Add Server:**
   - Name: "Lab Bench 1"
   - Host: 192.168.1.100
   - Click "Add"
3. **Switch Servers:**
   - Use dropdown in toolbar to switch between servers

### Equipment Profiles

Save and load equipment configurations:

1. **Equipment Tab → Profile Menu**
2. **Save Current Profile:**
   - Name: "Power Supply Safe Mode"
   - Saves all current settings
3. **Load Profile:**
   - Select profile from dropdown
   - Click "Load"
   - Equipment configured automatically!

### SSH Deployment

Deploy LabLink server to Raspberry Pi:

1. **Tools → SSH Deployment Wizard**
2. **Enter Pi Details:**
   - Hostname: lablink-pi.local
   - Username: admin
   - Password: lablink (default)
3. **Click "Deploy"**
   - Automatically copies files
   - Installs dependencies
   - Starts server as systemd service

---

## 🔧 Troubleshooting

### "No equipment found"

**Cause:** Server has no equipment configured

**Solution:**
```bash
# On the server, connect equipment via VISA
# Check available resources:
python -c "import pyvisa; rm = pyvisa.ResourceManager(); print(rm.list_resources())"
```

### "Command failed"

**Cause:** Equipment not responding or incorrect SCPI syntax

**Solution:**
- Verify equipment is connected
- Check SCPI command syntax in equipment manual
- Try `*IDN?` to test basic communication

### Real-time plot not updating

**Cause:** WebSocket connection issue

**Solution:**
- Check server WebSocket is running (port 8000)
- Reconnect to server
- Check firewall settings

### Client freezes when sending command

**Cause:** Equipment not responding, timeout

**Solution:**
- Check equipment power and connection
- Disconnect and reconnect equipment
- Restart server if needed

---

## 📚 Next Steps

Now that you know the basics:

1. **Read Equipment Manuals** - Learn SCPI commands for your devices
2. **Explore API Docs** - `http://localhost:8000/docs` for full API
3. **Set Up Scheduled Jobs** - Automate repetitive tasks
4. **Configure Alarms** - Set up safety monitoring
5. **Try Advanced Visualizations** - 3D plots, FFT analysis
6. **Mobile App** - Try the new LabLink mobile app (v1.1.0)

---

## 🎯 Quick Reference

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New server connection |
| `Ctrl+R` | Refresh equipment list |
| `Ctrl+Q` | Quit application |
| `F5` | Refresh current tab |

### Status Indicators

| Icon/Color | Meaning |
|------------|---------|
| 🟢 Green | Connected, healthy |
| 🟡 Yellow | Warning, needs attention |
| 🔴 Red | Error, disconnected |
| ⚫ Gray | Idle, not connected |

### File Locations

| Item | Location |
|------|----------|
| Client logs | `LabLink/client/lablink_client.log` |
| Server logs | `LabLink/server/logs/` |
| Saved profiles | `LabLink/profiles/` |
| Acquired data | `LabLink/data/` (configurable) |

---

## 💡 Tips for Success

1. **Always Connect Equipment First** - Before sending commands
2. **Use *IDN? to Test** - Verify communication before complex commands
3. **Save Profiles Often** - Don't lose your configurations
4. **Monitor Alarms** - Set up critical safety limits
5. **Check Logs** - `lablink_client.log` for debugging
6. **Start Simple** - Begin with basic commands, add complexity
7. **Read Documentation** - Equipment manuals are your friend!

---

## 🆘 Getting Help

- **Documentation:** `/docs` folder in LabLink repository
- **API Docs:** http://localhost:8000/docs (when server running)
- **Issues:** https://github.com/X9X0/LabLink/issues
- **Logs:** Check `lablink_client.log` for errors

---

## ✅ Checklist for New Users

- [ ] Installed Python 3.11+
- [ ] Installed client dependencies
- [ ] Started LabLink server
- [ ] Launched GUI client
- [ ] Connected to localhost server
- [ ] Refreshed equipment list
- [ ] Connected to equipment
- [ ] Sent first SCPI command (`*IDN?`)
- [ ] Started data acquisition
- [ ] Viewed real-time plot
- [ ] Checked alarms tab
- [ ] Explored diagnostics
- [ ] Saved an equipment profile

---

**Congratulations!** 🎉 You're now ready to use LabLink for laboratory equipment control!

For advanced features, see:
- [Data Acquisition Guide](ACQUISITION_SYSTEM.md)
- [Alarm System Guide](../server/ALARM_SYSTEM.md)
- [API Reference](API_REFERENCE.md)
- [Mobile App Guide](../mobile/README.md)

**Version:** LabLink v1.0.0
**Last Updated:** November 15, 2025
