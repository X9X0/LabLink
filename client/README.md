# LabLink GUI Client

PyQt6-based desktop client for LabLink laboratory equipment control system.

## Features

- **Equipment Control**: Connect, control, and monitor laboratory equipment
- **Data Acquisition**: Configure and run data acquisition sessions with real-time visualization
- **Alarm Monitoring**: View and acknowledge equipment alarms and notifications
- **Job Scheduling**: Manage and monitor scheduled operations
- **Diagnostics**: Equipment health monitoring and performance diagnostics
- **Multi-Server Support**: Connect to multiple LabLink servers

## Requirements

- Python 3.11+
- PyQt6 6.6.0+
- See `requirements.txt` for full list

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the client:
   ```bash
   python main.py
   ```

## Quick Start

1. Launch the client:
   ```bash
   python main.py
   ```

2. Connect to LabLink server:
   - Click "Connect to Server..." or press Ctrl+N
   - Enter server hostname (default: localhost)
   - Click "Connect"

3. Control equipment:
   - Navigate to the Equipment tab
   - Click "Refresh" to see available equipment
   - Select equipment and click "Connect"
   - Send commands and view readings

## Features by Tab

### Equipment Tab
- View all available equipment
- Connect/disconnect equipment
- View current readings
- Send custom SCPI commands
- Monitor connection status

### Data Acquisition Tab
- Configure acquisition parameters
- Start/stop data acquisition
- View real-time data plots
- Export acquired data
- View acquisition statistics

### Alarms Tab
- View active alarms
- Acknowledge alarms
- Filter by severity
- View alarm history

### Scheduler Tab
- View scheduled jobs
- Create new jobs
- Manually trigger jobs
- View job execution history

### Diagnostics Tab
- View equipment health scores
- Run diagnostic tests
- Generate diagnostic reports
- View performance benchmarks
- System resource monitoring

## Architecture

```
client/
├── main.py           # Application entry point
├── ui/               # User interface components
│   ├── main_window.py
│   ├── connection_dialog.py
│   ├── equipment_panel.py
│   ├── acquisition_panel.py
│   ├── alarm_panel.py
│   ├── scheduler_panel.py
│   └── diagnostics_panel.py
├── api/              # API client
│   └── client.py
├── models/           # Data models
│   └── equipment.py
├── utils/            # Utility functions
└── resources/        # Icons, styles, etc.
```

## Development

### Adding New Features

1. Create new panel in `ui/` directory
2. Add panel to main window tabs
3. Implement API calls in panel
4. Update `ui/__init__.py` exports

### Customizing Appearance

- Edit PyQt6 stylesheets in main window
- Add custom icons to `resources/icons/`
- Modify color schemes in panel classes

## Known Limitations

- Real-time plotting not yet fully implemented
- WebSocket streaming partially implemented
- Server discovery feature pending
- SSH deployment wizard pending

## Future Enhancements

- Real-time data visualization with pyqtgraph
- WebSocket integration for live data streaming
- Automatic server discovery (mDNS/Bonjour)
- Multi-server connection management
- Data export to multiple formats
- Custom plot configurations
- Equipment-specific control panels

## Troubleshooting

### Connection Issues

- Verify server is running: `http://localhost:8000/health`
- Check firewall settings
- Verify correct port numbers

### Import Errors

- Ensure all dependencies installed: `pip install -r requirements.txt`
- Check Python version: `python --version` (must be 3.11+)

### Display Issues

- Try different Qt styles: Edit `app.setStyle()` in main.py
- Adjust DPI settings for high-resolution displays

## License

TBD

## Contributing

Contributions welcome! Please submit pull requests or open issues on GitHub.
