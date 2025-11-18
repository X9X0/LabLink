# LabLink Advanced Visualizations (v1.2.0)

**Version:** 1.2.0
**Date:** November 18, 2025
**Status:** Complete

## Overview

LabLink v1.2.0 introduces a comprehensive advanced visualization system for analyzing waveform and measurement data. The new visualization page provides four specialized visualization types with interactive controls and real-time updates.

## Features

### 1. 3D Waveform Visualization

Three.js-powered 3D visualization for waveform data analysis.

**Capabilities:**
- Interactive 3D waveform plots with orbit controls
- Multiple waveform history (up to 10 waveforms)
- 3D surface rendering from waveform history
- Animated rotation mode
- Configurable grid and axes display
- Camera controls (orbit, zoom, pan)
- Dark mode support with automatic theme updates

**Controls:**
- **Left-click + drag**: Rotate view
- **Right-click + drag**: Pan view
- **Scroll wheel**: Zoom in/out
- **Reset View**: Reset camera to default position
- **Start/Stop Animation**: Rotate waveform automatically
- **Show Grid**: Toggle grid helper
- **Show Axes**: Toggle axes helper

**Implementation:**
- File: `/server/web/static/js/viz-3d-waveform.js`
- Technology: Three.js v0.160.0
- Performance: Optimized for 2000+ points with automatic sampling

### 2. FFT Waterfall Display

Time-frequency waterfall display (spectrogram) for spectral analysis.

**Capabilities:**
- Real-time FFT calculation with configurable window functions
- Color-mapped intensity display (blue → cyan → green → yellow → red)
- Scrolling waterfall display (up to 200 time slices)
- Configurable FFT size (256, 512, 1024, 2048)
- Multiple window functions (Hann, Hamming, Blackman, Bartlett, None)
- Frequency range and resolution display
- Time span tracking

**Window Functions:**
- **Hann**: General purpose, good for most signals
- **Hamming**: Similar to Hann, better side-lobe suppression
- **Blackman**: Excellent side-lobe suppression, wider main lobe
- **Bartlett**: Triangle window, simple implementation
- **None**: Rectangular window, fastest processing

**Implementation:**
- File: `/server/web/static/js/viz-waterfall.js`
- Canvas-based rendering for high performance
- DFT algorithm with configurable FFT size

**Statistics Displayed:**
- Frequency Range: 0 Hz to Nyquist frequency
- Time Span: Total time covered by waterfall
- Resolution: Frequency resolution per bin

### 3. Statistical Process Control (SPC) Charts

Animated SPC charts with control limits and process capability analysis.

**Chart Types:**

**X-bar & R Chart:**
- Control chart for subgroup means and ranges
- Uses A2, D3, D4 constants for control limits
- Displays both X-bar and R charts simultaneously

**X-bar & S Chart:**
- Control chart using standard deviation instead of range
- Better for larger subgroup sizes
- Uses A3 constants for control limits

**Individuals Chart:**
- Control chart for individual measurements
- Moving range chart for variability
- Ideal for single measurements or slow processes

**P Chart:**
- Proportion chart for defective items
- Binomial distribution-based control limits
- Useful for attribute data

**C Chart:**
- Count chart for number of defects
- Poisson distribution-based control limits
- For constant sample sizes

**Capabilities:**
- Real-time control limit calculation
- Automated violation detection with visual highlighting
- Process capability indices (Cp, Cpk)
- Animated chart updates
- Configurable subgroup size (2-10)
- Dual chart display (main + range/stdev)

**Implementation:**
- Files: `/server/web/static/js/viz-spc.js`
- Technology: Chart.js v4.4.1
- Animation duration: 750ms with easeInOutQuart easing

**Statistics Calculated:**
- **UCL (Upper Control Limit)**: Mean + 3σ
- **CL (Center Line)**: Process mean
- **LCL (Lower Control Limit)**: Mean - 3σ
- **Cp**: Process capability (spec range / 6σ)
- **Cpk**: Process capability index (min of upper/lower capability)
- **Violations**: Number of points outside control limits

**Violation Detection:**
- Points outside control limits are highlighted in red
- Automatic count of violations
- Visual pulse animation for violations

### 4. Multi-Instrument Correlation

Correlation analysis between two instruments with multiple visualization modes.

**Visualization Modes:**

**Time-Aligned Overlay:**
- Dual Y-axis overlay plot
- Synchronized time alignment via interpolation
- Independent voltage scales for each channel
- Interactive tooltip with both channel values

**Scatter Plot:**
- X-Y scatter plot of voltage correlations
- Linear regression line calculation and display
- R² (coefficient of determination) calculation
- Visual correlation pattern analysis

**Cross-Correlation:**
- Cross-correlation function plot
- Lag-based correlation analysis
- Peak correlation detection
- Time lag calculation (samples and microseconds)

**Capabilities:**
- Automatic time alignment via linear interpolation
- Linear regression with R² calculation
- Cross-correlation with configurable lag range
- Correlation coefficient calculation
- Time lag detection and display
- Up to 1000 interpolated points for performance

**Implementation:**
- File: `/server/web/static/js/viz-correlation.js`
- Technology: Chart.js v4.4.1 with scatter and line charts
- Algorithms: Linear interpolation, least-squares regression, cross-correlation

**Statistics Calculated:**
- **Correlation Coefficient (r)**: Measure of linear correlation (-1 to +1)
- **R² Value**: Coefficient of determination (0 to 1)
- **Time Lag**: Optimal time offset for maximum correlation
- **Peak Correlation**: Maximum cross-correlation value

## User Interface

### Page Structure

**Location:** `/visualizations.html`

**Sections:**
1. **Navigation Bar**: Links to Dashboard, Profiles, Settings
2. **Data Source Selector**: Equipment and channel selection
3. **Visualization Tabs**: Tab-based interface for each visualization type
4. **Visualization Panel**: Interactive canvas/chart display
5. **Control Panel**: Type-specific controls and settings
6. **Statistics Display**: Real-time statistics and metrics

### Navigation

Access advanced visualizations from:
- Main dashboard via "Advanced Viz" button
- Direct URL: `http://localhost:8000/visualizations.html`

### Dark Mode Support

All visualizations fully support dark mode with automatic theme detection:
- Background colors adapt to theme
- Text colors update for readability
- Chart colors remain visible in both modes
- Grid and axis colors adjust automatically

## Backend Integration

### API Endpoints Used

**Waveform Capture:**
```javascript
POST /api/waveform/capture
{
  "equipment_id": "string",
  "config": {
    "channel": 1,
    "num_averages": 1,
    "high_resolution": false,
    "interpolation": false,
    "single_shot": false,
    "apply_smoothing": false
  }
}
```

**Cached Waveform Retrieval:**
```javascript
GET /api/waveform/cached/{equipment_id}/{channel}
```

**Measurements:**
```javascript
GET /api/waveform/measurements/{equipment_id}/{channel}
```

### JavaScript API Client

New methods added to `api.js`:

```javascript
// Capture waveform from equipment
await api.captureWaveform(equipmentId, channel, config);

// Get cached waveform
await api.getCachedWaveform(equipmentId, channel);

// Get waveform measurements
await api.getWaveformMeasurements(equipmentId, channel);
```

## Technical Architecture

### File Structure

```
server/web/
├── templates/
│   └── visualizations.html          # Main visualization page
├── static/
│   ├── css/
│   │   └── visualizations.css       # Visualization-specific styles
│   └── js/
│       ├── visualizations.js        # Main controller
│       ├── viz-3d-waveform.js       # Three.js 3D visualization
│       ├── viz-waterfall.js         # FFT waterfall display
│       ├── viz-spc.js               # SPC charts
│       └── viz-correlation.js       # Correlation analysis
```

### Module Architecture

Each visualization is implemented as a self-contained module with a common interface:

```javascript
window.VizModuleName = {
    init: function() { },           // Initialize visualization
    updateData: function(data) { }, // Update with new data
    updateTheme: function() { },    // Update for theme change
    destroy: function() { }         // Cleanup resources (optional)
};
```

### Dependencies

**External Libraries:**
- Chart.js v4.4.1 - 2D charting
- Three.js v0.160.0 - 3D graphics
- OrbitControls (Three.js) - Camera controls

**Internal Dependencies:**
- `utils.js` - Utility functions
- `api.js` - API client
- `auth.js` - Authentication

## Performance Characteristics

### 3D Waveform
- **Max Points**: 2000 (auto-sampled from larger datasets)
- **History Buffer**: 10 waveforms
- **Frame Rate**: 60 FPS (requestAnimationFrame)
- **Memory**: ~50MB for full history

### FFT Waterfall
- **Max Lines**: 200 time slices
- **FFT Sizes**: 256, 512, 1024, 2048
- **Processing Time**: <50ms for 1024-point FFT
- **Canvas Updates**: Real-time with minimal lag

### SPC Charts
- **Max Data Points**: 1000+ (auto-sampled for display)
- **Animation Duration**: 750ms
- **Update Frequency**: On-demand
- **Memory**: <10MB per chart

### Correlation
- **Interpolated Points**: 1000
- **Cross-Correlation Lag**: ±100 samples
- **Processing Time**: <100ms for full analysis
- **Update Frequency**: On-demand

## Usage Examples

### Example 1: Analyzing Waveform Spectrum

1. Navigate to Advanced Visualizations page
2. Select an oscilloscope from equipment dropdown
3. Select channel (1-4)
4. Click "Load Data" to capture waveform
5. Switch to "FFT Waterfall" tab
6. Configure FFT size (512 recommended) and window (Hann)
7. Click "Update" to process and display waterfall
8. Observe frequency content over time

### Example 2: Process Control Monitoring

1. Load waveform data (voltage measurements)
2. Switch to "SPC Charts" tab
3. Select chart type (X-bar & R for continuous monitoring)
4. Set subgroup size (5 recommended)
5. Click "Generate Chart"
6. Review control limits and violations
7. Check Cp/Cpk values for process capability

### Example 3: Correlation Analysis

1. Load primary waveform (Channel 1)
2. Switch to "Correlation" tab
3. Select second equipment and channel
4. Click "Calculate"
5. Review time-aligned overlay for visual correlation
6. Check scatter plot and regression line
7. Analyze cross-correlation for time lag
8. Review statistics (r, R², time lag)

## Troubleshooting

### Common Issues

**Problem:** "No connected equipment found"
- **Solution**: Connect equipment first from main dashboard

**Problem:** "Invalid waveform data"
- **Solution**: Ensure equipment is an oscilloscope and channel has valid signal

**Problem:** 3D visualization not rendering
- **Solution**: Check browser WebGL support, update graphics drivers

**Problem:** Waterfall display is blank
- **Solution**: Load waveform data first, then switch to waterfall tab

**Problem:** Charts not updating after theme change
- **Solution**: Refresh page or reload data

### Browser Compatibility

**Supported Browsers:**
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

**Requirements:**
- WebGL support (for 3D visualizations)
- Canvas API support
- ES6 JavaScript support
- LocalStorage enabled

## Future Enhancements

Potential features for v1.2.1+:

1. **Export Capabilities**
   - PNG/SVG export for all visualizations
   - CSV export for processed data
   - PDF reports with all charts

2. **Advanced Analysis**
   - Harmonic analysis overlay on FFT
   - Advanced SPC rules (Western Electric, Nelson)
   - Multi-channel 3D correlation

3. **Performance Optimizations**
   - WebGL acceleration for waterfall
   - Web Workers for FFT calculation
   - Streaming mode for continuous updates

4. **UI Enhancements**
   - Fullscreen mode for each visualization
   - Side-by-side comparison mode
   - Customizable color schemes

## Version History

### v1.2.0 (November 18, 2025)
- Initial release of advanced visualizations
- Four visualization types implemented
- Full dark mode support
- Mobile-responsive design
- Integration with existing LabLink backend

## Support

For issues or feature requests:
- **GitHub Issues**: https://github.com/X9X0/LabLink/issues
- **Documentation**: See `/docs` directory
- **API Docs**: http://localhost:8000/docs (when server running)

## Related Documentation

- [ROADMAP.md](../ROADMAP.md) - Project roadmap and version planning
- [CHANGELOG.md](../CHANGELOG.md) - Detailed version history
- [WAVEFORM_USER_GUIDE.md](WAVEFORM_USER_GUIDE.md) - Waveform capture system
- [ADVANCED_WAVEFORM_ANALYSIS.md](../server/ADVANCED_WAVEFORM_ANALYSIS.md) - Backend analysis features

---

**Document Version:** 1.0
**Last Updated:** November 18, 2025
**Author:** LabLink Development Team
