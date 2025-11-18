<!-- The file is longer than 100 lines, truncated to first 100 lines -->
# Advanced Waveform Analysis Tools

**Version:** 1.0.0
**Last Updated:** 2025-11-18
**Status:** Production Ready

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Quick Start](#quick-start)
4. [Spectral Analysis](#spectral-analysis)
5. [Jitter Analysis](#jitter-analysis)
6. [Eye Diagram Analysis](#eye-diagram-analysis)
7. [Mask Testing](#mask-testing)
8. [Waveform Search](#waveform-search)
9. [Reference Waveform Comparison](#reference-waveform-comparison)
10. [Parameter Trending](#parameter-trending)
11. [API Reference](#api-reference)
12. [Usage Examples](#usage-examples)
13. [Best Practices](#best-practices)

---

## Overview

The Advanced Waveform Analysis Tools extend LabLink's oscilloscope capabilities with professional-grade signal analysis features typically found in high-end test equipment. These tools enable deep signal characterization, compliance testing, and long-term monitoring.

### Key Features

- **Spectral Analysis**: Spectrograms, cross-correlation, transfer functions
- **Jitter Analysis**: TIE, period, cycle-to-cycle, and N-period jitter
- **Eye Diagram Analysis**: Serial data quality assessment with comprehensive measurements
- **Mask Testing**: Pass/fail testing against user-defined or standard masks
- **Waveform Search**: Find edges, pulses, runts, glitches, and other events
- **Reference Comparison**: Compare against golden waveforms
- **Parameter Trending**: Track measurements over time with drift analysis

### Use Cases

- **Serial Data Validation**: Eye diagrams, jitter analysis, mask testing
- **System Characterization**: Transfer functions, spectrograms
- **Quality Control**: Reference comparison, mask testing, trending
- **Signal Integrity**: Jitter analysis, eye diagrams, event search
- **Debugging**: Glitch detection, anomaly search, correlation analysis

---

## Features

### 1. Spectral Analysis

#### Spectrogram (Time-Frequency Analysis)

Visualizes how frequency content changes over time using Short-Time Fourier Transform (STFT).

**Applications:**
- Frequency-modulated signal analysis
- Chirp signal characterization
- Transient detection
- Time-varying spectrum visualization

**Parameters:**
- Window size: FFT window length (default: 256)
- Overlap: Sample overlap between windows (default: 128)
- Window function: Hann, Hamming, Blackman, etc.
- Display mode: Magnitude, power, or dB scale
- Frequency limits: Min/max frequency range

#### Cross-Correlation

Measures similarity and time delay between two signals.

**Applications:**
- Propagation delay measurement
- Signal similarity assessment
- Phase relationship detection
- Time-of-flight measurements

**Output:**
- Correlation function vs time lag
- Maximum correlation value
- Time lag at maximum correlation
- Pearson correlation coefficient

#### Transfer Function H(f) = Y(f)/X(f)

Analyzes system frequency response from input and output signals.

**Applications:**
- Filter characterization
- Amplifier frequency response
- System identification
- Bode plot generation

**Output:**
- Magnitude response (linear and dB)
- Phase response (degrees)
- Coherence function (0-1, quality metric)

---

### 2. Jitter Analysis

Comprehensive timing jitter measurements for digital signals.

#### Jitter Types

1. **TIE (Time Interval Error)**
   - Deviation of edge times from ideal positions
   - Shows cumulative timing error
   - Best for clock quality assessment

2. **Period Jitter**
   - Variation of period from mean value
   - Important for clock stability
   - Shows short-term period variations

3. **Cycle-to-Cycle Jitter**
   - Difference between consecutive periods
   - Critical for high-speed serial links
   - Indicates immediate period changes

4. **Half-Period Jitter**
   - Analyzes both rising and falling edges
   - Useful for dual-edge clocks
   - DDR memory analysis

5. **N-Period Jitter**
   - Jitter over N periods
   - Configurable N value
   - Long-term stability assessment

#### Jitter Measurements

- Mean jitter
- RMS jitter
- Peak-to-peak jitter
- Standard deviation
- Jitter histogram
- Number of edges analyzed
- Ideal period reference

---

### 3. Eye Diagram Analysis

Professional eye diagram generation and analysis for serial data links.

#### Eye Diagram Generation

**Process:**
1. Detect bit edges using threshold crossing
2. Extract symbol-period segments
3. Overlay segments to create eye pattern
4. Optional persistence map (2D histogram)

**Configuration:**
- Bit rate: Data rate in bps
- Samples per symbol: Reconstruction resolution
- Edge threshold: Auto or manual
- Number of traces: Overlay limit
- Persistence mode: Enable/disable

#### Eye Diagram Measurements

**Geometric Parameters:**
- Eye height: Voltage opening (V)
- Eye width: Time opening (s)
- Eye amplitude: Total voltage range
- Crossing percentage: Zero-crossing location

**Jitter and Noise:**
- RMS jitter (seconds)
- Peak-to-peak jitter (seconds)
- RMS noise (volts)

**Quality Metrics:**
- Q-factor: Signal quality metric
- SNR: Signal-to-noise ratio (dB)
- Eye opening: Usable area percentage (0-100%)

**Level Measurements:**
- Logic 1 level (V)
- Logic 0 level (V)
- Rise time (10%-90%)
- Fall time (90%-10%)

---

### 4. Mask Testing

Pass/fail testing of waveforms against user-defined masks.

#### Mask Types

1. **Polygon Masks**
   - User-defined polygonal regions
   - Multiple regions per mask
   - Inside or outside violation modes

2. **Standard Masks**
   - Eye diagram masks (e.g., IEEE standards)
   - Pre-defined templates
   - Industry-standard patterns

3. **Auto Masks**
   - Generated from reference waveforms
   - Configurable margins
   - Automatic tolerance regions

#### Mask Testing Process

1. Define mask regions as polygons
2. Specify fail conditions (inside/outside)
3. Test waveform points against mask
4. Report violations and margins

#### Test Results

- Overall pass/fail status
- Total samples tested
- Number of violations
- Failure rate (0-1)
- Failure locations (time, voltage)
- Per-region violation counts
- Minimum and mean margin to mask

---

### 5. Waveform Search

Automated detection of specific events in waveforms.

#### Supported Event Types

1. **EDGE_RISING**: Rising edge crossings
2. **EDGE_FALLING**: Falling edge crossings
3. **PULSE_POSITIVE**: Positive pulses with width filtering
4. **PULSE_NEGATIVE**: Negative pulses with width filtering
5. **RUNT**: Runt pulses (don't reach full threshold)
6. **TIMEOUT**: Timeout violations
7. **GLITCH**: Narrow glitches
8. **SETUP_HOLD**: Setup/hold violations (future)
9. **PATTERN**: Digital pattern matching (future)

#### Search Configuration

- Event type to find
- Threshold levels (upper/lower)
- Pulse width limits (min/max)
- Timeout duration
- Maximum events to find (limit)

#### Search Results

For each event:
- Event type
- Time of occurrence
- Sample index
- Amplitude
- Pulse width (if applicable)
- Additional details (event-specific)

Statistics:
- Total events found
- Mean time between events
- Event rate (Hz)
- Search duration

---

### 6. Reference Waveform Comparison

Compare test waveforms against "golden" reference standards.

#### Reference Waveform Setup

**Required Data:**
- Name and description
- Equipment ID and channel
- Time and voltage arrays
- Sample rate
- Capture timestamp

**Tolerance Settings:**
- Voltage tolerance percentage
- Time tolerance percentage

#### Comparison Process

1. Resample test waveform to match reference
2. Calculate voltage errors (RMS, max, mean)
3. Compute correlation coefficient
4. Find phase shift
5. Identify failure points
6. Calculate similarity percentage

#### Comparison Results

**Voltage Analysis:**
- RMS voltage error
- Maximum voltage error
- Mean voltage error

**Shape Analysis:**
- Cross-correlation coefficient
- Phase shift (seconds)

**Pass/Fail:**
- Overall pass/fail
- Similarity percentage (0-100%)
- Number of failed samples
- Failure times and error values

---

### 7. Parameter Trending

Track measurement parameters over time to detect drift and aging.

#### Trendable Parameters

**Voltage/Amplitude:**
- Frequency
- Amplitude (Vpp, Vrms)

**Timing:**
- Rise time
- Fall time
- Duty cycle

**Signal Quality:**
- Overshoot
- SNR
- THD

**Advanced:**
- RMS jitter
- Eye height
- Eye width

#### Trend Analysis

**Statistics:**
- Mean value
- Standard deviation
- Minimum and maximum
- Value range

**Drift Analysis:**
- Drift rate (linear regression slope)
- Trend direction (up/down/stable)

**Data Management:**
- Configurable maximum samples
- Sequence numbering
- Timestamp for each point

---

## Quick Start

### Example 1: Jitter Analysis

```python
import requests

BASE_URL = "http://localhost:8000"

# Capture waveform first
requests.post(f"{BASE_URL}/api/waveform/capture", json={
    "equipment_id": "scope_123",
    "config": {"channel": 1, "num_averages": 10}
})

# Analyze TIE jitter
response = requests.post(f"{BASE_URL}/api/waveform/advanced/jitter", json={
    "equipment_id": "scope_123",
    "channel": 1,
    "use_cached": True,
    "config": {
        "jitter_type": "tie",
        "edge_type": "rising",
        "threshold": None  # Auto threshold
    }
})

jitter_data = response.json()
print(f"RMS Jitter: {jitter_data['rms_jitter']*1e12:.2f} ps")
print(f"Peak-to-Peak Jitter: {jitter_data['pk_pk_jitter']*1e12:.2f} ps")
print(f"Edges analyzed: {jitter_data['n_edges']}")
```

### Example 2: Eye Diagram

```python
# Generate eye diagram for 1 Gbps serial data
response = requests.post(f"{BASE_URL}/api/waveform/advanced/eye-diagram", json={
    "equipment_id": "scope_123",
    "channel": 1,
    "use_cached": True,
    "config": {
        "bit_rate": 1e9,  # 1 Gbps
        "samples_per_symbol": 100,
        "edge_threshold": None,  # Auto
        "num_traces": 500,
        "persistence_mode": True
    }
})

eye_data = response.json()
params = eye_data['parameters']

print(f"Eye Height: {params['eye_height']*1000:.1f} mV")
print(f"Eye Opening: {params['eye_opening']:.1f}%")
print(f"Q-factor: {params['q_factor']:.2f}")
print(f"RMS Jitter: {params['rms_jitter']*1e12:.2f} ps")
```

### Example 3: Mask Testing

```python
# Define a simple voltage mask
mask_definition = {
    "name": "voltage_limits",
    "description": "Min/max voltage limits",
    "mode": "polygon",
    "polygons": [
        {
            "name": "upper_limit",
            "points": [
                {"time": 0.0, "voltage": 3.5},
                {"time": 1.0, "voltage": 3.5},
                {"time": 1.0, "voltage": 5.0},
                {"time": 0.0, "voltage": 5.0}
            ],
            "fail_inside": True  # Fail if waveform goes above 3.5V
        },
        {
            "name": "lower_limit",
            "points": [
                {"time": 0.0, "voltage": -1.0},
                {"time": 1.0, "voltage": -1.0},
                {"time": 1.0, "voltage": 0.5},
                {"time": 0.0, "voltage": 0.5}
            ],
            "fail_inside": True  # Fail if waveform goes below 0.5V
        }
    ],
    "normalized": True  # Time and voltage are 0-1 normalized
}

# Add mask definition
requests.post(f"{BASE_URL}/api/waveform/advanced/mask/define", json=mask_definition)

# Test waveform
response = requests.post(f"{BASE_URL}/api/waveform/advanced/mask/test", json={
    "equipment_id": "scope_123",
    "channel": 1,
    "use_cached": True,
    "mask_name": "voltage_limits"
})

result = response.json()
print(f"Test Result: {'PASS' if result['passed'] else 'FAIL'}")
print(f"Violations: {result['failed_samples']} / {result['total_samples']}")
print(f"Failure Rate: {result['failure_rate']*100:.2f}%")
```

### Example 4: Waveform Search

```python
# Search for glitches
response = requests.post(f"{BASE_URL}/api/waveform/advanced/search", json={
    "equipment_id": "scope_123",
    "channel": 1,
    "use_cached": True,
    "config": {
        "event_type": "glitch",
        "max_width": 10e-9,  # 10 ns max width
        "max_events": 100
    }
})

result = response.json()
print(f"Found {result['total_events']} glitches")

for i, event in enumerate(result['events'][:5], 1):
    print(f"Glitch {i}: Time={event['time']*1e6:.2f} µs, Width={event['width']*1e9:.2f} ns")
```

---

## API Reference

### Endpoint Summary

**Spectral Analysis:**
- `POST /api/waveform/advanced/spectrogram` - Calculate spectrogram
- `POST /api/waveform/advanced/cross-correlation` - Cross-correlation analysis
- `POST /api/waveform/advanced/transfer-function` - Transfer function H(f)

**Jitter Analysis:**
- `POST /api/waveform/advanced/jitter` - Calculate jitter measurements

**Eye Diagram:**
- `POST /api/waveform/advanced/eye-diagram` - Generate eye diagram

**Mask Testing:**
- `POST /api/waveform/advanced/mask/define` - Define new mask
- `GET /api/waveform/advanced/mask/list` - List all masks
- `POST /api/waveform/advanced/mask/test` - Test waveform against mask

**Waveform Search:**
- `POST /api/waveform/advanced/search` - Search for events

**Reference Comparison:**
- `POST /api/waveform/advanced/reference/add` - Add reference waveform
- `GET /api/waveform/advanced/reference/list` - List references
- `POST /api/waveform/advanced/reference/compare` - Compare to reference

**Parameter Trending:**
- `POST /api/waveform/advanced/trend/update` - Update trend data
- `GET /api/waveform/advanced/trend/get/{equipment_id}/{channel}/{parameter}` - Get trend

**System:**
- `GET /api/waveform/advanced/info` - System information

---

## Usage Examples

### Complete Jitter Analysis Workflow

```python
import requests
import numpy as np
import matplotlib.pyplot as plt

BASE_URL = "http://localhost:8000"
EQUIPMENT_ID = "scope_123"

# 1. Capture waveform
print("Capturing waveform...")
requests.post(f"{BASE_URL}/api/waveform/capture", json={
    "equipment_id": EQUIPMENT_ID,
    "config": {
        "channel": 1,
        "num_averages": 16,  # Average to reduce noise
        "apply_smoothing": False
    }
})

# 2. Analyze different jitter types
jitter_types = ["tie", "period", "cycle_to_cycle"]

for jitter_type in jitter_types:
    print(f"\nAnalyzing {jitter_type} jitter...")

    response = requests.post(f"{BASE_URL}/api/waveform/advanced/jitter", json={
        "equipment_id": EQUIPMENT_ID,
        "channel": 1,
        "use_cached": True,
        "config": {
            "jitter_type": jitter_type,
            "edge_type": "rising"
        }
    })

    jitter_data = response.json()

    print(f"  RMS: {jitter_data['rms_jitter']*1e12:.2f} ps")
    print(f"  Pk-Pk: {jitter_data['pk_pk_jitter']*1e12:.2f} ps")
    print(f"  Mean: {jitter_data['mean_jitter']*1e12:.2f} ps")
    print(f"  Std Dev: {jitter_data['std_dev']*1e12:.2f} ps")
    print(f"  Edges: {jitter_data['n_edges']}")

    # Plot histogram
    plt.figure(figsize=(8, 5))
    bins = np.array(jitter_data['histogram_bins']) * 1e12  # Convert to ps
    counts = jitter_data['histogram_counts']

    plt.bar(bins[:-1], counts, width=np.diff(bins), align='edge')
    plt.xlabel('Jitter (ps)')
    plt.ylabel('Count')
    plt.title(f'{jitter_type.upper()} Jitter Distribution')
    plt.grid(True, alpha=0.3)
    plt.savefig(f'jitter_{jitter_type}.png', dpi=150)
    plt.close()

print("\nJitter analysis complete!")
```

### Transfer Function Analysis

```python
# Measure amplifier frequency response

# 1. Capture input and output channels
for channel in [1, 2]:
    requests.post(f"{BASE_URL}/api/waveform/capture", json={
        "equipment_id": EQUIPMENT_ID,
        "config": {
            "channel": channel,
            "num_averages": 8
        }
    })

# 2. Calculate transfer function
response = requests.post(f"{BASE_URL}/api/waveform/advanced/transfer-function", json={
    "equipment_id": EQUIPMENT_ID,
    "input_channel": 1,
    "output_channel": 2,
    "use_cached": True,
    "nperseg": 512  # Longer segment for better frequency resolution
})

tf_data = response.json()

# 3. Plot Bode plot
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10))

frequencies = np.array(tf_data['frequencies'])
magnitude_db = np.array(tf_data['magnitude_db'])
phase = np.array(tf_data['phase'])
coherence = np.array(tf_data['coherence'])

# Magnitude
ax1.semilogx(frequencies, magnitude_db)
ax1.set_ylabel('Magnitude (dB)')
ax1.set_title('Transfer Function H(f) = Vout(f) / Vin(f)')
ax1.grid(True, which='both', alpha=0.3)

# Phase
ax2.semilogx(frequencies, phase)
ax2.set_ylabel('Phase (degrees)')
ax2.grid(True, which='both', alpha=0.3)

# Coherence
ax3.semilogx(frequencies, coherence)
ax3.set_xlabel('Frequency (Hz)')
ax3.set_ylabel('Coherence')
ax3.set_ylim([0, 1.1])
ax3.grid(True, which='both', alpha=0.3)

plt.tight_layout()
plt.savefig('transfer_function.png', dpi=150)

print(f"Transfer function calculated ({len(frequencies)} points)")
```

---

## Best Practices

### Jitter Analysis

1. **Averaging**: Use waveform averaging (8-16x) to reduce measurement noise
2. **Sample Rate**: Ensure sample rate is at least 20× signal frequency
3. **Trigger Stability**: Use stable triggering to get consistent edge positions
4. **Edge Selection**: Choose appropriate edge type (rising/falling) for clock
5. **Jitter Type**: Use TIE for absolute jitter, cycle-to-cycle for serial links

### Eye Diagram Analysis

1. **Bit Rate Accuracy**: Ensure accurate bit rate setting
2. **Signal Conditioning**: Use proper probe impedance and bandwidth
3. **Trace Count**: Use 200-1000 traces for good statistical representation
4. **Threshold**: Let auto-threshold find optimal decision point
5. **Bandwidth**: Oscilloscope bandwidth should be ≥ 3× bit rate

### Mask Testing

1. **Normalized Masks**: Use normalized coordinates for reusable masks
2. **Margin Testing**: Check min_margin and mean_margin for design margins
3. **Reference Generation**: Create masks from known-good waveforms
4. **Region Naming**: Use clear names for troubleshooting failures

### Waveform Search

1. **Threshold Selection**: Use appropriate thresholds for noise immunity
2. **Width Filtering**: Set realistic min/max widths to avoid false positives
3. **Event Limits**: Limit max_events to prevent memory issues on noisy signals
4. **Post-Processing**: Analyze event_rate and timing statistics

### Reference Comparison

1. **Golden Unit**: Capture reference from verified good unit
2. **Averaging**: Average both reference and test waveforms
3. **Tolerances**: Set realistic tolerances based on process capability
4. **Alignment**: Ensure reference and test use same settings/scales

### Parameter Trending

1. **Sampling Rate**: Update trends at appropriate intervals (not too fast)
2. **Data Retention**: Monitor trend storage and implement cleanup if needed
3. **Alert Thresholds**: Set meaningful alert limits based on specifications
4. **Drift Analysis**: Look for monotonic trends indicating aging/drift

---

## Troubleshooting

### Issue: "Not enough edge crossings found"

**Cause:** Signal level too low, wrong threshold, or not enough samples
**Solution:**
- Check signal amplitude is adequate (> 100 mV typical)
- Try auto-threshold (set to None)
- Increase capture time window
- Verify signal is actually toggling

### Issue: Eye diagram looks closed

**Cause:** Signal quality issues, wrong bit rate, or insufficient bandwidth
**Solution:**
- Verify correct bit rate setting
- Check probe bandwidth (should be ≥ 3× bit rate)
- Use averaging to reduce noise
- Check for signal integrity issues (ringing, reflections)

### Issue: Mask test always fails

**Cause:** Incorrect mask definition or coordinates
**Solution:**
- Verify mask coordinates are correct
- Check if normalized flag matches coordinate system
- Plot mask and waveform together to visualize
- Check fail_inside logic is correct

### Issue: Search finds too many events

**Cause:** Threshold too sensitive or noisy signal
**Solution:**
- Increase threshold levels
- Add width filtering (min_width, max_width)
- Reduce max_events limit
- Apply smoothing to waveform before search

### Issue: Transfer function shows low coherence

**Cause:** Input/output not correlated, noise, or nonlinear system
**Solution:**
- Verify input is actually driving output
- Increase averaging (nperseg parameter)
- Check for nonlinearities in system
- Ensure proper loading and termination

---

## Related Documentation

- [Waveform Capture & Analysis](WAVEFORM_USER_GUIDE.md) - Basic waveform features
- [Data Analysis Pipeline](ANALYSIS_USER_GUIDE.md) - Signal processing, filtering, SPC
- [API Reference](API_REFERENCE.md) - Complete API documentation

---

**For questions or issues, please refer to the project repository or contact the development team.**
