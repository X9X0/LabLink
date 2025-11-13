# Waveform Capture & Analysis User Guide

**Version:** 0.16.0
**Last Updated:** 2025-11-13
**Status:** Complete

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Features](#features)
4. [Configuration](#configuration)
5. [API Reference](#api-reference)
6. [Usage Examples](#usage-examples)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The Waveform Capture & Analysis system provides professional-grade oscilloscope functionality with advanced measurement, analysis, and visualization capabilities. It extends LabLink's oscilloscope support with:

- **High-speed waveform acquisition** with averaging and decimation
- **Enhanced automatic measurements** (30+ measurement types)
- **Cursor measurements** (horizontal and vertical)
- **Math channels** (15 operations including FFT)
- **Persistence mode** (infinite, envelope, variable)
- **Histogram analysis** (voltage and time distributions)
- **XY mode** (plot channel vs channel)
- **Continuous acquisition** for real-time monitoring

### Key Benefits

- Professional measurement accuracy
- Advanced signal analysis (FFT, THD, SNR)
- Real-time waveform processing
- Flexible math operations
- Statistical analysis
- Efficient data management

---

## Quick Start

### 1. Basic Waveform Capture

```python
import requests

# Capture waveform from channel 1
response = requests.post("http://localhost:8000/api/waveform/capture", json={
    "equipment_id": "scope_abc123",
    "config": {
        "channel": 1,
        "num_averages": 1,
        "single_shot": False
    }
})

waveform = response.json()
print(f"Captured {waveform['num_samples']} samples")
print(f"Sample rate: {waveform['sample_rate']/1e6:.1f} MSa/s")
```

### 2. Get Enhanced Measurements

```python
# Get comprehensive measurements
response = requests.post("http://localhost:8000/api/waveform/measurements", json={
    "equipment_id": "scope_abc123",
    "channel": 1,
    "use_cached": True
})

measurements = response.json()
print(f"Frequency: {measurements['frequency']/1000:.2f} kHz")
print(f"Vpp: {measurements['vpp']:.3f} V")
print(f"Rise time: {measurements['rise_time']*1e6:.2f} µs")
```

### 3. Calculate FFT

```python
# Calculate FFT of waveform
response = requests.post("http://localhost:8000/api/waveform/math", json={
    "equipment_id": "scope_abc123",
    "config": {
        "operation": "fft",
        "source_channel1": 1,
        "fft_window": "hann",
        "fft_mode": "magnitude"
    }
})

fft_result = response.json()
frequencies = fft_result['frequency_data']
magnitudes = fft_result['magnitude_data']
```

---

## Features

### 1. High-Speed Waveform Acquisition

Capture waveforms with advanced options:

- **Averaging**: Average multiple acquisitions to reduce noise
- **High-resolution mode**: Increase effective bit depth
- **Decimation**: Reduce data points while preserving signal integrity
- **Smoothing**: Apply low-pass filtering
- **Single-shot**: Capture single triggered waveform

**Example:**
```python
config = {
    "channel": 1,
    "num_averages": 10,        # Average 10 waveforms
    "high_resolution": True,   # Enable hi-res mode
    "reduce_points": 1000,     # Decimate to 1000 points
    "apply_smoothing": True,   # Apply smoothing filter
    "single_shot": False       # Continuous capture
}
```

### 2. Enhanced Automatic Measurements (30+ Types)

**Voltage Measurements:**
- Vpp (peak-to-peak)
- Vmax, Vmin
- Vamp (amplitude)
- Vtop, Vbase (histogram-based)
- Vmid (middle voltage)
- Vavg (average)
- Vrms (RMS voltage)
- Vac_rms (AC RMS)

**Time Measurements:**
- Period
- Frequency
- Rise time (10%-90%)
- Fall time (90%-10%)
- Positive pulse width
- Negative pulse width
- Duty cycle
- Phase
- Delay

**Overshoot/Preshoot:**
- Overshoot (%)
- Preshoot (%)

**Edge Measurements:**
- Positive edge count
- Negative edge count
- Pulse count
- Pulse rate

**Area Measurements:**
- Total waveform area
- Single cycle area

**Slew Rate:**
- Rising edge slew rate
- Falling edge slew rate

**Signal Quality:**
- SNR (signal-to-noise ratio)
- THD (total harmonic distortion)
- SINAD
- ENOB (effective number of bits)

**Statistical:**
- Standard deviation
- Variance
- Skewness
- Kurtosis

### 3. Cursor Measurements

**Horizontal Cursors (Time):**
- Measure time between two points
- Calculate frequency (1/ΔT)
- Read voltage values at cursor positions
- Calculate voltage delta

**Vertical Cursors (Voltage):**
- Measure voltage between two levels
- Find time when signal crosses each level
- Calculate time delta

**Example:**
```python
# Horizontal cursors
response = requests.post("http://localhost:8000/api/waveform/cursor", json={
    "equipment_id": "scope_abc123",
    "channel": 1,
    "cursor_type": "horizontal",
    "cursor1_position": 0.0001,  # 100 µs
    "cursor2_position": 0.0002   # 200 µs
})

cursor_data = response.json()
print(f"ΔT = {cursor_data['delta_time']*1e6:.2f} µs")
print(f"Frequency = {cursor_data['frequency']/1000:.2f} kHz")
print(f"ΔV = {cursor_data['delta_voltage']:.3f} V")
```

### 4. Math Channels

**Binary Operations (Channel1 op Channel2):**
- ADD: Ch1 + Ch2
- SUBTRACT: Ch1 - Ch2
- MULTIPLY: Ch1 × Ch2
- DIVIDE: Ch1 ÷ Ch2

**Unary Operations (Single Channel):**
- INVERT: -Ch1
- ABS: |Ch1|
- SQRT: √Ch1
- SQUARE: Ch1²
- LOG: ln(Ch1)
- EXP: e^Ch1

**Transform Operations:**
- FFT: Fast Fourier Transform
  - Magnitude, phase, real, imaginary modes
  - Multiple window functions (Hann, Hamming, Blackman, etc.)
- INTEGRATE: Cumulative integral
- DIFFERENTIATE: Time derivative

**Processing Operations:**
- AVERAGE: Running average (configurable window)
- ENVELOPE: Signal envelope (Hilbert transform)

**Example:**
```python
# Add two channels
response = requests.post("http://localhost:8000/api/waveform/math", json={
    "equipment_id": "scope_abc123",
    "config": {
        "operation": "add",
        "source_channel1": 1,
        "source_channel2": 2,
        "scale": 1.0,
        "offset": 0.0
    }
})

# Calculate FFT with Hann window
response = requests.post("http://localhost:8000/api/waveform/math", json={
    "equipment_id": "scope_abc123",
    "config": {
        "operation": "fft",
        "source_channel1": 1,
        "fft_window": "hann",
        "fft_mode": "magnitude"
    }
})
```

### 5. Persistence Mode

Accumulate multiple waveforms to visualize signal variations:

**Modes:**
- **INFINITE**: Accumulate all waveforms (shows all traces)
- **ENVELOPE**: Show min/max envelope
- **VARIABLE**: Variable persistence with exponential decay

**Example:**
```python
# Enable envelope persistence
requests.post("http://localhost:8000/api/waveform/persistence/enable", json={
    "equipment_id": "scope_abc123",
    "channel": 1,
    "config": {
        "mode": "envelope",
        "max_waveforms": 100
    }
})

# Get persistence overlay
response = requests.get(
    "http://localhost:8000/api/waveform/persistence/scope_abc123/1"
)
persistence_data = response.json()

# Disable persistence
requests.post("http://localhost:8000/api/waveform/persistence/disable", json={
    "equipment_id": "scope_abc123",
    "channel": 1
})
```

### 6. Histogram Analysis

Calculate voltage or time distributions:

**Features:**
- Configurable bin count (10-1000)
- Statistical measures (mean, std dev, median, mode)
- Distribution shape metrics (skewness, kurtosis)

**Example:**
```python
# Calculate voltage histogram
response = requests.post("http://localhost:8000/api/waveform/histogram", json={
    "equipment_id": "scope_abc123",
    "channel": 1,
    "histogram_type": "voltage",
    "num_bins": 100
})

histogram = response.json()
print(f"Mean: {histogram['mean']:.3f} V")
print(f"Std Dev: {histogram['std_dev']:.3f} V")
print(f"Skewness: {histogram['skewness']:.3f}")
```

### 7. XY Mode

Plot one channel against another:

**Example:**
```python
# Capture both channels first
requests.post("http://localhost:8000/api/waveform/capture", json={
    "equipment_id": "scope_abc123",
    "config": {"channel": 1}
})

requests.post("http://localhost:8000/api/waveform/capture", json={
    "equipment_id": "scope_abc123",
    "config": {"channel": 2}
})

# Create XY plot
response = requests.post("http://localhost:8000/api/waveform/xy-plot", json={
    "equipment_id": "scope_abc123",
    "x_channel": 1,
    "y_channel": 2
})

xy_data = response.json()
x_values = xy_data['x_data']
y_values = xy_data['y_data']
```

### 8. Continuous Acquisition

Start continuous high-speed waveform capture:

**Example:**
```python
# Start continuous acquisition at 10 Hz
response = requests.post("http://localhost:8000/api/waveform/continuous/start", json={
    "equipment_id": "scope_abc123",
    "channel": 1,
    "rate_hz": 10.0
})

task_id = response.json()['task_id']
print(f"Started acquisition: {task_id}")

# List active acquisitions
response = requests.get("http://localhost:8000/api/waveform/continuous/list")
print(response.json())

# Stop acquisition
requests.post("http://localhost:8000/api/waveform/continuous/stop", json={
    "task_id": task_id
})
```

---

## Configuration

### Server Settings (config/settings.py or .env)

```bash
# Enable/disable waveform analysis
LABLINK_ENABLE_WAVEFORM_ANALYSIS=true

# Cache settings
LABLINK_WAVEFORM_CACHE_SIZE=100
LABLINK_WAVEFORM_EXPORT_DIR=./data/waveforms

# Acquisition defaults
LABLINK_DEFAULT_NUM_AVERAGES=1
LABLINK_ENABLE_HIGH_RESOLUTION=false
LABLINK_DEFAULT_DECIMATION_POINTS=1000

# Persistence settings
LABLINK_ENABLE_PERSISTENCE=true
LABLINK_PERSISTENCE_MAX_WAVEFORMS=100
LABLINK_PERSISTENCE_DECAY_TIME=1.0

# Histogram settings
LABLINK_HISTOGRAM_DEFAULT_BINS=100

# Math channel settings
LABLINK_ENABLE_MATH_CHANNELS=true
LABLINK_FFT_DEFAULT_WINDOW=hann
LABLINK_MATH_AVERAGE_COUNT=10

# Continuous acquisition
LABLINK_MAX_CONTINUOUS_RATE_HZ=100.0
LABLINK_CONTINUOUS_BUFFER_SIZE=1000
```

---

## API Reference

### Waveform Capture Endpoints

#### POST /api/waveform/capture

Capture waveform with advanced options.

**Request Body:**
```json
{
  "equipment_id": "scope_abc123",
  "config": {
    "channel": 1,
    "num_averages": 1,
    "high_resolution": false,
    "interpolation": false,
    "single_shot": false,
    "reduce_points": null,
    "apply_smoothing": false
  }
}
```

**Response:** ExtendedWaveformData with full voltage and time arrays

#### GET /api/waveform/cached/{equipment_id}/{channel}

Get cached waveform.

**Response:** ExtendedWaveformData or 404 if not cached

#### DELETE /api/waveform/cache/{equipment_id}

Clear waveform cache for equipment (or all if equipment_id is null).

### Measurement Endpoints

#### POST /api/waveform/measurements

Get comprehensive automatic measurements.

**Request Body:**
```json
{
  "equipment_id": "scope_abc123",
  "channel": 1,
  "use_cached": true
}
```

**Response:** EnhancedMeasurements with 30+ measurements

#### GET /api/waveform/measurements/{equipment_id}/{channel}

Get measurements for cached waveform.

### Cursor Endpoints

#### POST /api/waveform/cursor

Calculate cursor measurements.

**Request Body:**
```json
{
  "equipment_id": "scope_abc123",
  "channel": 1,
  "cursor_type": "horizontal",
  "cursor1_position": 0.0001,
  "cursor2_position": 0.0002
}
```

**Response:** CursorData with delta values and readouts

### Math Channel Endpoints

#### POST /api/waveform/math

Apply math operation to waveform(s).

**Request Body:**
```json
{
  "equipment_id": "scope_abc123",
  "config": {
    "operation": "fft",
    "source_channel1": 1,
    "source_channel2": null,
    "scale": 1.0,
    "offset": 0.0,
    "fft_window": "hann",
    "fft_mode": "magnitude"
  }
}
```

**Response:** MathChannelResult with result waveform

### Persistence Endpoints

#### POST /api/waveform/persistence/enable

Enable persistence mode.

**Request Body:**
```json
{
  "equipment_id": "scope_abc123",
  "channel": 1,
  "config": {
    "mode": "envelope",
    "decay_time": 1.0,
    "max_waveforms": 100,
    "color_grading": true
  }
}
```

#### POST /api/waveform/persistence/disable

Disable persistence mode.

**Request Body:**
```json
{
  "equipment_id": "scope_abc123",
  "channel": 1
}
```

#### GET /api/waveform/persistence/{equipment_id}/{channel}

Get accumulated persistence data.

### Histogram Endpoints

#### POST /api/waveform/histogram

Calculate voltage or time histogram.

**Request Body:**
```json
{
  "equipment_id": "scope_abc123",
  "channel": 1,
  "histogram_type": "voltage",
  "num_bins": 100
}
```

**Response:** HistogramData with distribution statistics

### XY Plot Endpoints

#### POST /api/waveform/xy-plot

Create XY plot from two channels.

**Request Body:**
```json
{
  "equipment_id": "scope_abc123",
  "x_channel": 1,
  "y_channel": 2
}
```

**Response:** XYPlotData with x/y data arrays

### Continuous Acquisition Endpoints

#### POST /api/waveform/continuous/start

Start continuous acquisition.

**Request Body:**
```json
{
  "equipment_id": "scope_abc123",
  "channel": 1,
  "rate_hz": 10.0
}
```

**Response:** Task ID

#### POST /api/waveform/continuous/stop

Stop continuous acquisition.

**Request Body:**
```json
{
  "task_id": "acq_scope_abc123_ch1_12345678"
}
```

#### GET /api/waveform/continuous/list

List active continuous acquisitions.

### Info Endpoint

#### GET /api/waveform/info

Get waveform system information.

**Response:**
```json
{
  "cached_waveforms": 5,
  "persistence_channels": 2,
  "active_acquisitions": 1,
  "xy_plots_cached": 1
}
```

---

## Usage Examples

### Example 1: Signal Characterization

Complete signal characterization workflow:

```python
import requests

BASE_URL = "http://localhost:8000"
EQUIPMENT_ID = "scope_abc123"

# 1. Capture waveform with averaging
print("Capturing waveform...")
response = requests.post(f"{BASE_URL}/api/waveform/capture", json={
    "equipment_id": EQUIPMENT_ID,
    "config": {
        "channel": 1,
        "num_averages": 10,  # Reduce noise
        "apply_smoothing": True
    }
})
waveform = response.json()

# 2. Get all measurements
print("\nGetting measurements...")
response = requests.post(f"{BASE_URL}/api/waveform/measurements", json={
    "equipment_id": EQUIPMENT_ID,
    "channel": 1,
    "use_cached": True
})
measurements = response.json()

# Print key measurements
print(f"\n=== Signal Characteristics ===")
print(f"Frequency: {measurements['frequency']/1000:.2f} kHz")
print(f"Period: {measurements['period']*1e6:.2f} µs")
print(f"Amplitude: {measurements['vamp']:.3f} V")
print(f"Vpp: {measurements['vpp']:.3f} V")
print(f"Vrms: {measurements['vrms']:.3f} V")
print(f"Rise time: {measurements['rise_time']*1e9:.1f} ns")
print(f"Fall time: {measurements['fall_time']*1e9:.1f} ns")
print(f"Duty cycle: {measurements['duty_cycle']:.1f}%")
print(f"Overshoot: {measurements['overshoot']:.1f}%")
print(f"SNR: {measurements['snr']:.1f} dB")
print(f"THD: {measurements['thd']:.2f}%")
```

### Example 2: Frequency Domain Analysis

Analyze signal in frequency domain:

```python
# Capture waveform
requests.post(f"{BASE_URL}/api/waveform/capture", json={
    "equipment_id": EQUIPMENT_ID,
    "config": {"channel": 1, "num_averages": 5}
})

# Calculate FFT
response = requests.post(f"{BASE_URL}/api/waveform/math", json={
    "equipment_id": EQUIPMENT_ID,
    "config": {
        "operation": "fft",
        "source_channel1": 1,
        "fft_window": "hann",
        "fft_mode": "magnitude"
    }
})

fft_result = response.json()
frequencies = fft_result['frequency_data']
magnitudes = fft_result['magnitude_data']

# Find fundamental frequency
import numpy as np
magnitudes_arr = np.array(magnitudes)
fundamental_idx = np.argmax(magnitudes_arr[1:]) + 1  # Skip DC
fundamental_freq = frequencies[fundamental_idx]

print(f"Fundamental frequency: {fundamental_freq/1000:.2f} kHz")
print(f"Magnitude: {magnitudes[fundamental_idx]:.2f}")
```

### Example 3: Jitter Analysis with Persistence

Visualize signal jitter using persistence mode:

```python
# Enable envelope persistence
requests.post(f"{BASE_URL}/api/waveform/persistence/enable", json={
    "equipment_id": EQUIPMENT_ID,
    "channel": 1,
    "config": {
        "mode": "envelope",
        "max_waveforms": 100
    }
})

# Capture multiple waveforms
print("Capturing waveforms for jitter analysis...")
for i in range(100):
    requests.post(f"{BASE_URL}/api/waveform/capture", json={
        "equipment_id": EQUIPMENT_ID,
        "config": {"channel": 1}
    })

# Get envelope data
response = requests.get(
    f"{BASE_URL}/api/waveform/persistence/{EQUIPMENT_ID}/1"
)
envelope = response.json()

# Calculate jitter statistics
voltage_data = envelope['voltage_data']
min_envelope = voltage_data[0::2]  # Even indices
max_envelope = voltage_data[1::2]  # Odd indices

jitter = np.array(max_envelope) - np.array(min_envelope)
print(f"Peak jitter: {np.max(jitter)*1000:.1f} mV")
print(f"Average jitter: {np.mean(jitter)*1000:.1f} mV")
```

### Example 4: Multi-Channel Analysis

Analyze relationship between two channels:

```python
# Capture both channels
for channel in [1, 2]:
    requests.post(f"{BASE_URL}/api/waveform/capture", json={
        "equipment_id": EQUIPMENT_ID,
        "config": {"channel": channel}
    })

# Create XY plot
response = requests.post(f"{BASE_URL}/api/waveform/xy-plot", json={
    "equipment_id": EQUIPMENT_ID,
    "x_channel": 1,
    "y_channel": 2
})
xy_data = response.json()

# Calculate correlation
x_data = np.array(xy_data['x_data'])
y_data = np.array(xy_data['y_data'])
correlation = np.corrcoef(x_data, y_data)[0, 1]
print(f"Correlation: {correlation:.3f}")

# Calculate phase difference (for periodic signals)
# Get measurements for both channels
measurements1 = requests.post(f"{BASE_URL}/api/waveform/measurements", json={
    "equipment_id": EQUIPMENT_ID,
    "channel": 1
}).json()

measurements2 = requests.post(f"{BASE_URL}/api/waveform/measurements", json={
    "equipment_id": EQUIPMENT_ID,
    "channel": 2
}).json()

# Use delay or cross-correlation for phase
# (simplified example)
print(f"Ch1 Frequency: {measurements1['frequency']/1000:.2f} kHz")
print(f"Ch2 Frequency: {measurements2['frequency']/1000:.2f} kHz")
```

### Example 5: Automated Testing

Automated signal quality test:

```python
def test_signal_quality(equipment_id, channel, specs):
    """Test signal against specifications."""

    # Capture waveform
    requests.post(f"{BASE_URL}/api/waveform/capture", json={
        "equipment_id": equipment_id,
        "config": {
            "channel": channel,
            "num_averages": 10
        }
    })

    # Get measurements
    response = requests.post(f"{BASE_URL}/api/waveform/measurements", json={
        "equipment_id": equipment_id,
        "channel": channel
    })
    measurements = response.json()

    # Check against specs
    results = {}
    results['frequency_ok'] = (
        specs['freq_min'] <= measurements['frequency'] <= specs['freq_max']
    )
    results['amplitude_ok'] = (
        specs['amp_min'] <= measurements['vamp'] <= specs['amp_max']
    )
    results['rise_time_ok'] = (
        measurements['rise_time'] <= specs['rise_time_max']
    )
    results['overshoot_ok'] = (
        measurements['overshoot'] <= specs['overshoot_max']
    )
    results['thd_ok'] = (
        measurements['thd'] <= specs['thd_max']
    )

    results['all_pass'] = all(results.values())

    return results, measurements

# Test specifications
specs = {
    'freq_min': 995e3,      # 995 kHz
    'freq_max': 1005e3,     # 1005 kHz
    'amp_min': 1.9,         # 1.9 V
    'amp_max': 2.1,         # 2.1 V
    'rise_time_max': 50e-9, # 50 ns
    'overshoot_max': 10,    # 10%
    'thd_max': 2.0,         # 2%
}

# Run test
results, measurements = test_signal_quality("scope_abc123", 1, specs)

print("\n=== Test Results ===")
for test, passed in results.items():
    status = "PASS" if passed else "FAIL"
    print(f"{test}: {status}")
```

---

## Best Practices

### 1. Waveform Capture

- Use **averaging** to reduce noise when possible
- Enable **high-resolution mode** for DC or slow signals
- Use **decimation** to reduce data size for long captures
- Apply **smoothing** only when necessary (can distort sharp edges)
- Use **single-shot** mode for triggered events

### 2. Measurements

- Capture waveform with adequate sample rate (>10× signal bandwidth)
- Use averaging for better measurement accuracy
- Check signal conditioning (trigger stable, no clipping)
- Verify measurements make sense (frequency vs period, etc.)
- Use cached waveforms when making multiple measurements

### 3. Math Operations

- **FFT**: Use appropriate window function (Hann for general use)
- **Integration**: Watch for DC drift
- **Differentiation**: Amplifies noise - average first
- **Binary operations**: Ensure channels are time-aligned
- Apply scale/offset after operation for better results

### 4. Persistence Mode

- Use **envelope** mode for jitter analysis
- Use **variable** mode for signal stability visualization
- Limit **max_waveforms** to prevent memory issues
- Clear persistence buffer periodically

### 5. Performance

- Clear cache periodically to prevent memory buildup
- Use decimation for large waveforms
- Limit continuous acquisition rate to what you need
- Stop continuous acquisition when not in use
- Use appropriate histogram bin count (more bins = more computation)

### 6. Data Management

- Export important waveforms for offline analysis
- Use waveform IDs to track related data
- Cache waveforms when performing multiple operations
- Clean up old cached data

---

## Troubleshooting

### Problem: No waveform cached

**Symptom:** 404 error when accessing cached waveform

**Solutions:**
- Capture waveform first before requesting measurements/cursors
- Check equipment_id and channel number are correct
- Verify waveform capture succeeded

### Problem: Measurements return None/null

**Symptom:** Some measurements are null in response

**Solutions:**
- Ensure signal is periodic for time measurements
- Check signal amplitude is sufficient
- Verify trigger is stable
- Increase averaging to reduce noise

### Problem: FFT results unexpected

**Symptom:** FFT shows unexpected peaks or shape

**Solutions:**
- Check sample rate is adequate (>2× max frequency)
- Verify number of samples is sufficient
- Try different window functions
- Check for aliasing (reduce bandwidth or increase sample rate)

### Problem: Continuous acquisition stops

**Symptom:** Continuous acquisition terminates unexpectedly

**Solutions:**
- Check equipment connection is stable
- Verify acquisition rate is not too high
- Check server logs for errors
- Ensure equipment supports requested rate

### Problem: Math operation fails

**Symptom:** Error when applying math operation

**Solutions:**
- Verify both channels are captured for binary operations
- Check waveforms have same length
- Ensure operation is appropriate for signal
- Check for divide-by-zero in division operations

### Problem: High memory usage

**Symptom:** Server memory grows over time

**Solutions:**
- Clear waveform cache periodically
- Reduce persistence max_waveforms
- Stop unused continuous acquisitions
- Use decimation to reduce data size
- Limit cache size in configuration

### Problem: Slow performance

**Symptom:** Waveform operations take too long

**Solutions:**
- Enable decimation to reduce data points
- Use lower averaging count
- Reduce histogram bin count
- Stop continuous acquisitions
- Clear cache

---

## Related Documentation

- [API Reference](API_REFERENCE.md) - Complete API documentation
- [Data Acquisition System](ACQUISITION_SYSTEM.md) - Data acquisition features
- [Equipment Guide](EQUIPMENT_GUIDE.md) - Equipment setup and configuration

---

## Version History

### v0.16.0 (2025-11-13)
- Initial release
- High-speed waveform acquisition
- 30+ enhanced measurements
- Cursor measurements (horizontal & vertical)
- 15 math operations including FFT
- Persistence mode (3 modes)
- Histogram analysis
- XY plot mode
- Continuous acquisition
- 25+ API endpoints
- Comprehensive documentation

---

**For questions or issues, please refer to the project repository or contact the development team.**
