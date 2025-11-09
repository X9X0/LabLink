# LabLink Documentation

Complete documentation for the LabLink laboratory equipment control system.

## Quick Links

### For Users

- **[User Guide](USER_GUIDE.md)** - Complete guide for using LabLink
- **[Getting Started](GETTING_STARTED.md)** - Quick start guide
- **[Equipment Panels](EQUIPMENT_PANELS.md)** - Equipment-specific control panels
- **[mDNS Discovery](MDNS_DISCOVERY.md)** - Automatic server discovery

### For Developers

- **[API Reference](API_REFERENCE.md)** - REST API documentation
- **[WebSocket Streaming](WEBSOCKET_STREAMING.md)** - Real-time data streaming
- **[Test Suite](TEST_SUITE.md)** - Testing guide
- **[Mock Equipment](MOCK_EQUIPMENT.md)** - Simulated equipment drivers

### Configuration & Setup

- **[Settings](SETTINGS.md)** - Configuration persistence
- **[Visualization](VISUALIZATION.md)** - Data visualization guide

## Documentation by Category

### User Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| [User Guide](USER_GUIDE.md) | Complete user manual with tutorials and troubleshooting | End Users |
| [Getting Started](GETTING_STARTED.md) | Quick start guide for first-time users | New Users |
| [Equipment Panels](EQUIPMENT_PANELS.md) | Guide to equipment-specific control panels | Users |

### Technical Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| [API Reference](API_REFERENCE.md) | REST API endpoints and usage | Developers |
| [WebSocket Streaming](WEBSOCKET_STREAMING.md) | Real-time streaming protocol | Developers |
| [mDNS Discovery](MDNS_DISCOVERY.md) | Automatic server discovery using mDNS | Developers |
| [Settings](SETTINGS.md) | Configuration persistence system | Developers |
| [Visualization](VISUALIZATION.md) | Real-time plotting and charting | Developers |
| [Mock Equipment](MOCK_EQUIPMENT.md) | Simulated equipment for testing | Developers |

### Development Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| [Test Suite](TEST_SUITE.md) | Comprehensive testing guide | Developers |
| Development Roadmap | Feature roadmap and plans | Contributors |
| Project Summary | High-level project overview | All |

## Documentation Sections

### Getting Started

Start here if you're new to LabLink:

1. **[Getting Started](GETTING_STARTED.md)** - Installation and first steps
2. **[User Guide - Connecting](USER_GUIDE.md#connecting-to-a-server)** - Connect to a server
3. **[User Guide - Equipment](USER_GUIDE.md#working-with-equipment)** - Work with equipment
4. **[Equipment Panels](EQUIPMENT_PANELS.md)** - Use equipment control panels

### Using LabLink

Learn how to use different features:

- **Connection**
  - [Server Discovery](MDNS_DISCOVERY.md) - Automatic server discovery
  - [Manual Connection](USER_GUIDE.md#connecting-to-a-server) - Manual server configuration

- **Equipment Control**
  - [Oscilloscope Panel](EQUIPMENT_PANELS.md#oscilloscope-panel) - Waveform capture
  - [Power Supply Panel](EQUIPMENT_PANELS.md#power-supply-panel) - Voltage/current control
  - [Electronic Load Panel](EQUIPMENT_PANELS.md#electronic-load-panel) - Load testing

- **Data & Visualization**
  - [Real-Time Monitoring](USER_GUIDE.md#real-time-monitoring) - Live data display
  - [Data Acquisition](USER_GUIDE.md#data-acquisition) - Capture and export data
  - [Visualization Guide](VISUALIZATION.md) - Charts and plotting

- **Configuration**
  - [Settings](SETTINGS.md) - Persistent configuration
  - [Preferences](USER_GUIDE.md#settings-and-configuration) - Customize LabLink

### Development & Integration

Resources for developers:

- **API Integration**
  - [REST API](API_REFERENCE.md) - HTTP endpoints
  - [WebSocket Streaming](WEBSOCKET_STREAMING.md) - Real-time data

- **Testing**
  - [Test Suite](TEST_SUITE.md) - Running tests
  - [Mock Equipment](MOCK_EQUIPMENT.md) - Testing without hardware

- **Customization**
  - [Equipment Panels](EQUIPMENT_PANELS.md#creating-custom-equipment-panels) - Custom panels
  - [Settings](SETTINGS.md) - Configuration API

### Troubleshooting

Having issues? Check these resources:

- **[User Guide - Troubleshooting](USER_GUIDE.md#troubleshooting)** - Common issues and solutions
- **[Test Suite](TEST_SUITE.md#troubleshooting)** - Testing problems
- **[mDNS Discovery - Troubleshooting](MDNS_DISCOVERY.md#troubleshooting)** - Discovery issues
- **[Equipment Panels - Troubleshooting](EQUIPMENT_PANELS.md#troubleshooting)** - Panel issues

## Feature Guides

### Server Discovery (mDNS/Zeroconf)

Automatic server detection on your network:

- **[mDNS Discovery Guide](MDNS_DISCOVERY.md)** - Complete guide
- **Quick Start:** [MDNS_DISCOVERY.md#quick-start](MDNS_DISCOVERY.md#quick-start)
- **GUI Dialog:** [MDNS_DISCOVERY.md#discovery-dialog-gui](MDNS_DISCOVERY.md#discovery-dialog-gui)

### Equipment-Specific Control Panels

Specialized interfaces for different equipment:

- **[Equipment Panels Guide](EQUIPMENT_PANELS.md)** - Complete guide
- **Oscilloscope:** [EQUIPMENT_PANELS.md#oscilloscope-panel](EQUIPMENT_PANELS.md#oscilloscope-panel)
- **Power Supply:** [EQUIPMENT_PANELS.md#power-supply-panel](EQUIPMENT_PANELS.md#power-supply-panel)
- **Electronic Load:** [EQUIPMENT_PANELS.md#electronic-load-panel](EQUIPMENT_PANELS.md#electronic-load-panel)

### Real-Time Data Streaming

WebSocket-based live data:

- **[WebSocket Streaming Guide](WEBSOCKET_STREAMING.md)** - Complete guide
- **Quick Start:** [WEBSOCKET_STREAMING.md#quick-start](WEBSOCKET_STREAMING.md#quick-start)
- **Client Integration:** [WEBSOCKET_STREAMING.md#client-side-streaming](WEBSOCKET_STREAMING.md#client-side-streaming)

### Data Visualization

Real-time plotting and charting:

- **[Visualization Guide](VISUALIZATION.md)** - Complete guide
- **Plot Widget:** [VISUALIZATION.md#plot-widget](VISUALIZATION.md#plot-widget)
- **Waveform Display:** [VISUALIZATION.md#waveform-display](VISUALIZATION.md#waveform-display)

### Configuration Persistence

Saving and loading settings:

- **[Settings Guide](SETTINGS.md)** - Complete guide
- **Quick Start:** [SETTINGS.md#quick-start](SETTINGS.md#quick-start)
- **API Reference:** [SETTINGS.md#api-reference](SETTINGS.md#api-reference)

### Testing

Comprehensive test suite:

- **[Test Suite Guide](TEST_SUITE.md)** - Complete guide
- **Running Tests:** [TEST_SUITE.md#running-tests](TEST_SUITE.md#running-tests)
- **Writing Tests:** [TEST_SUITE.md#writing-tests](TEST_SUITE.md#writing-tests)

### Mock Equipment

Simulated equipment for development:

- **[Mock Equipment Guide](MOCK_EQUIPMENT.md)** - Complete guide
- **Mock Oscilloscope:** [MOCK_EQUIPMENT.md#mock-oscilloscope](MOCK_EQUIPMENT.md#mock-oscilloscope)
- **Mock Power Supply:** [MOCK_EQUIPMENT.md#mock-power-supply](MOCK_EQUIPMENT.md#mock-power-supply)

## Documentation Standards

All LabLink documentation follows these standards:

### Structure

- **Table of Contents** - For documents >500 lines
- **Quick Start** - For technical guides
- **API Reference** - For code documentation
- **Examples** - Complete, runnable examples
- **Troubleshooting** - Common issues and solutions

### Formatting

- **Markdown** - All docs in Markdown format
- **Code Blocks** - Syntax highlighting for code
- **Tables** - For structured information
- **Screenshots** - ASCII art for simple diagrams
- **Links** - Relative links within documentation

### Code Examples

All code examples should:
- Be complete and runnable
- Include imports
- Show error handling
- Have comments explaining key parts
- Follow Python PEP 8 style

Example:

```python
"""Complete example showing feature usage."""

from client.api.client import LabLinkClient

# Create client
client = LabLinkClient(host="localhost", api_port=8000, ws_port=8001)

try:
    # Connect to server
    if client.connect():
        print("✓ Connected successfully")

        # Use client...
        info = client.get_server_info()
        print(f"Server: {info['name']} v{info['version']}")

    else:
        print("✗ Connection failed")

finally:
    # Always disconnect
    client.disconnect()
```

## Contributing to Documentation

### Adding New Documentation

1. **Create Markdown file** in `docs/` directory
2. **Follow naming convention:** UPPERCASE_WITH_UNDERSCORES.md
3. **Add to this index** in appropriate category
4. **Include standard sections:**
   - Title and description
   - Table of contents (if >500 lines)
   - Quick start section
   - Detailed guide
   - API reference (if applicable)
   - Troubleshooting
   - Last updated date

### Updating Existing Documentation

1. **Update content** in relevant .md file
2. **Update "Last updated" date** at bottom
3. **Check all links** still work
4. **Test code examples** still run
5. **Update version** if significant changes

### Documentation Review

Before submitting documentation:

- [ ] Spell check complete
- [ ] All links work
- [ ] Code examples tested
- [ ] Screenshots up to date
- [ ] TOC matches content
- [ ] Cross-references correct
- [ ] Last updated date set

## Documentation Statistics

- **Total Documents:** 13
- **User Guides:** 3
- **Technical Guides:** 7
- **Development Docs:** 3
- **Total Lines:** ~15,000
- **Code Examples:** 100+

## Version Information

- **Documentation Version:** 1.0.0
- **LabLink Version:** 1.0.0
- **Last Updated:** 2024-11-08
- **Python Version:** 3.11+

## License

Documentation is licensed under CC BY 4.0. Code examples are licensed under MIT License.

---

**Need help?** Check the [User Guide](USER_GUIDE.md) or [Getting Started](GETTING_STARTED.md) guide.

**For developers:** See [API Reference](API_REFERENCE.md) and [Test Suite](TEST_SUITE.md).
