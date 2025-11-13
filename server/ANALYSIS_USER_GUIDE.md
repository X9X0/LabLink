# LabLink Data Analysis Pipeline - User Guide

## Overview

The LabLink Data Analysis Pipeline (v0.17.0) provides comprehensive tools for processing, analyzing, and reporting on laboratory equipment data. This system is designed for industrial and research applications requiring rigorous data analysis, quality control, and automated reporting.

### Key Features

1. **Signal Filtering** - Remove noise and extract relevant signals
   - IIR filters: Butterworth, Chebyshev, Bessel, Elliptic
   - FIR filters with customizable design
   - Specialized filters: Notch, Moving Average, Savitzky-Golay, Median
   - Zero-phase filtering support

2. **Data Resampling** - Adjust sampling rates and interpolate data
   - Multiple interpolation methods: Linear, Cubic, Spline, Fourier
   - Anti-aliasing for downsampling
   - Missing data interpolation
   - Signal alignment with cross-correlation

3. **Curve Fitting** - Fit mathematical models to experimental data
   - Linear and polynomial regression
   - Exponential, logarithmic, and power law models
   - Sinusoidal and Gaussian fits
   - Custom function support
   - Comprehensive statistics (R², RMSE, residuals)

4. **Statistical Process Control (SPC)** - Monitor process quality and capability
   - Control charts: X-bar/R, X-bar/S, Individuals, P, C, U
   - Western Electric rules detection
   - Process capability indices: Cp, Cpk, Pp, Ppk, Cpm
   - Expected yield and defect rate calculations

5. **Automated Report Generation** - Create professional analysis reports
   - Multiple formats: HTML, Markdown, JSON, PDF
   - Customizable sections with plots and tables
   - Styled HTML output with CSS
   - Template support

6. **Batch Processing** - Process multiple files in parallel
   - Parallel or sequential execution
   - Filter, fit, and resample operations
   - Progress tracking and error handling
   - JSON and CSV file support

## Quick Start

### 1. Signal Filtering

Remove 60 Hz power line noise from your signal:

```python
import requests

# Prepare data
data = [0.1, 0.2, 0.15, 0.25, ...]  # Your signal data
sample_rate = 1000  # Hz

# Apply notch filter
response = requests.post("http://localhost:8000/api/analysis/filter/notch", json={
    "data": data,
    "frequency": 60.0,
    "quality_factor": 30.0,
    "sample_rate": sample_rate
})

filtered_data = response.json()["filtered_data"]
```

Apply a low-pass filter to smooth noisy data:

```python
response = requests.post("http://localhost:8000/api/analysis/filter", json={
    "data": data,
    "time": time,
    "config": {
        "filter_type": "lowpass",
        "filter_method": "butterworth",
        "cutoff_freq": 10.0,
        "sample_rate": sample_rate,
        "order": 4,
        "zero_phase": True
    }
})

result = response.json()
filtered_data = result["filtered_data"]
cutoff_freq = result["actual_cutoff"]
```

### 2. Curve Fitting

Fit an exponential decay curve to your data:

```python
response = requests.post("http://localhost:8000/api/analysis/fit", json={
    "x_data": [0, 1, 2, 3, 4, 5],
    "y_data": [10.0, 6.7, 4.5, 3.0, 2.0, 1.3],
    "config": {
        "fit_type": "exponential",
        "initial_guess": [10.0, -0.5, 0.0]
    }
})

result = response.json()
coefficients = result["coefficients"]  # [a, b, c] for y = a*exp(b*x) + c
r_squared = result["r_squared"]
equation = result["equation"]
fitted_data = result["fitted_data"]
```

### 3. Process Capability Analysis

Analyze manufacturing process capability:

```python
# Your process measurements
measurements = [10.2, 10.1, 10.3, 9.9, 10.0, 10.2, ...]

response = requests.post("http://localhost:8000/api/analysis/spc/capability", json={
    "data": measurements,
    "lsl": 9.5,   # Lower specification limit
    "usl": 10.5,  # Upper specification limit
    "target": 10.0
})

result = response.json()
print(f"Cp: {result['cp']}")
print(f"Cpk: {result['cpk']}")
print(f"Expected yield: {result['expected_yield']*100:.2f}%")
print(f"Assessment: {result['assessment']}")
```

### 4. Generate Analysis Report

Create a comprehensive HTML report:

```python
sections = [
    {
        "title": "Experimental Results",
        "content": "Analysis of temperature vs. time data...",
        "plots": ["data:image/png;base64,..."],  # Base64 encoded plots
        "tables": [
            {"headers": ["Parameter", "Value"],
             "rows": [["Mean", "25.3"], ["Std Dev", "0.8"]]}
        ]
    }
]

response = requests.post("http://localhost:8000/api/analysis/report/generate", json={
    "sections": sections,
    "config": {
        "title": "Temperature Analysis Report",
        "author": "Lab Technician",
        "format": "html",
        "include_timestamp": True,
        "include_toc": True
    }
})

report = response.json()
html_content = report["content"]
```

## Detailed Usage Examples

### Signal Filtering

#### Example 1: Remove High-Frequency Noise

```python
# Low-pass filter to remove noise above 50 Hz
response = requests.post("http://localhost:8000/api/analysis/filter", json={
    "data": noisy_signal,
    "time": time_array,
    "config": {
        "filter_type": "lowpass",
        "filter_method": "butterworth",
        "cutoff_freq": 50.0,
        "sample_rate": 1000.0,
        "order": 5,
        "zero_phase": True
    }
})
```

**Filter Types:**
- `lowpass` - Pass frequencies below cutoff
- `highpass` - Pass frequencies above cutoff
- `bandpass` - Pass frequencies between f_low and f_high
- `bandstop` - Reject frequencies between f_low and f_high (notch)

**Filter Methods:**
- `butterworth` - Maximally flat passband, smooth rolloff
- `chebyshev1` - Steeper rolloff, ripple in passband
- `chebyshev2` - Steeper rolloff, ripple in stopband
- `bessel` - Linear phase response (preserves waveform shape)
- `elliptic` - Steepest rolloff, ripple in both bands
- `fir` - Finite impulse response (always stable)

#### Example 2: Extract Signal in Specific Band

```python
# Band-pass filter to extract 10-100 Hz component
response = requests.post("http://localhost:8000/api/analysis/filter", json={
    "data": signal,
    "time": time,
    "config": {
        "filter_type": "bandpass",
        "filter_method": "butterworth",
        "f_low": 10.0,
        "f_high": 100.0,
        "sample_rate": 1000.0,
        "order": 4
    }
})
```

#### Example 3: Savitzky-Golay Smoothing

Better than moving average for preserving features:

```python
response = requests.post("http://localhost:8000/api/analysis/filter/savitzky-golay", json={
    "data": noisy_data,
    "window_size": 11,  # Must be odd
    "poly_order": 3
})
```

### Data Resampling

#### Example 1: Downsample with Anti-Aliasing

```python
# Downsample from 1000 Hz to 100 Hz
response = requests.post("http://localhost:8000/api/analysis/resample", json={
    "x_data": time_array,
    "y_data": signal_data,
    "config": {
        "method": "fourier",
        "target_rate": 100.0,
        "anti_aliasing": True
    },
    "original_rate": 1000.0
})

resampled = response.json()
new_time = resampled["x_data"]
new_signal = resampled["y_data"]
```

#### Example 2: Upsample for Smoother Plots

```python
# Increase from 100 to 1000 points
response = requests.post("http://localhost:8000/api/analysis/resample", json={
    "x_data": x_data,
    "y_data": y_data,
    "config": {
        "method": "cubic",
        "target_points": 1000
    }
})
```

#### Example 3: Interpolate Missing Data

```python
# Fill NaN values with cubic interpolation
response = requests.post("http://localhost:8000/api/analysis/interpolate-missing", json={
    "x_data": [0, 1, 2, 3, 4, 5],
    "y_data": [1.0, float('nan'), 3.0, float('nan'), 5.0, 6.0],
    "method": "cubic"
})
```

### Curve Fitting

#### Example 1: Polynomial Regression

```python
# Fit 3rd order polynomial
response = requests.post("http://localhost:8000/api/analysis/fit", json={
    "x_data": x_values,
    "y_data": y_values,
    "config": {
        "fit_type": "polynomial",
        "degree": 3
    }
})

result = response.json()
# Coefficients for y = ax³ + bx² + cx + d
coeffs = result["coefficients"]
r_squared = result["r_squared"]
rmse = result["rmse"]
```

#### Example 2: Exponential Decay

Perfect for RC circuits, radioactive decay, chemical kinetics:

```python
response = requests.post("http://localhost:8000/api/analysis/fit", json={
    "x_data": time,
    "y_data": voltage,
    "config": {
        "fit_type": "exponential",
        "initial_guess": [5.0, -0.1, 0.0]  # [a, b, c] for y=a*exp(b*x)+c
    }
})

# Extract time constant: τ = -1/b
time_constant = -1.0 / result["coefficients"][1]
```

#### Example 3: Sinusoidal Fit

Fit oscillating data:

```python
response = requests.post("http://localhost:8000/api/analysis/fit", json={
    "x_data": time,
    "y_data": oscillating_signal,
    "config": {
        "fit_type": "sinusoidal"
        # Initial guess is auto-computed from FFT
    }
})

# Result: y = A*sin(ω*t + φ) + offset
coeffs = result["coefficients"]  # [A, ω, φ, offset]
amplitude = coeffs[0]
frequency_rad = coeffs[1]
frequency_hz = frequency_rad / (2 * np.pi)
phase = coeffs[2]
```

#### Example 4: Gaussian Peak Fitting

For spectral peaks, chromatography peaks, etc.:

```python
response = requests.post("http://localhost:8000/api/analysis/fit", json={
    "x_data": wavelength,
    "y_data": intensity,
    "config": {
        "fit_type": "gaussian"
    }
})

# Result: y = A*exp(-(x-μ)²/(2σ²)) + baseline
coeffs = result["coefficients"]  # [A, μ, σ, baseline]
peak_amplitude = coeffs[0]
peak_center = coeffs[1]
peak_width = coeffs[2]
```

#### Example 5: Predict from Fit

Use fitted coefficients to predict new values:

```python
# After fitting, predict at new x values
response = requests.post("http://localhost:8000/api/analysis/fit/predict", json={
    "coefficients": [1.5, -0.2, 0.5],  # From previous fit
    "x_new": [10, 20, 30, 40, 50],
    "fit_type": "exponential"
})

predictions = response.json()["y_predicted"]
```

### Statistical Process Control (SPC)

#### Example 1: Individuals (I-MR) Control Chart

For continuous processes with individual measurements:

```python
# Individual measurements over time
measurements = [10.1, 10.2, 9.9, 10.0, 10.3, 10.1, ...]

response = requests.post("http://localhost:8000/api/analysis/spc/chart", json={
    "data": measurements,
    "config": {
        "chart_type": "individuals",
        "subgroup_size": 1
    }
})

result = response.json()
# Control limits
ucl = result["upper_control_limit"]
cl = result["center_line"]
lcl = result["lower_control_limit"]

# Out of control points
if result["out_of_control_points"]:
    print(f"Warning: {len(result['out_of_control_points'])} out-of-control points detected")
    for point in result["out_of_control_points"]:
        print(f"  Point {point['index']}: {point['value']:.3f} - {point['reason']}")
```

#### Example 2: X-bar and R Chart

For subgrouped data (e.g., 5 samples per hour):

```python
# Measurements organized in subgroups
measurements = [
    10.1, 10.2, 9.9, 10.0, 10.1,  # Subgroup 1
    10.2, 10.3, 10.1, 10.2, 10.0,  # Subgroup 2
    ...
]

response = requests.post("http://localhost:8000/api/analysis/spc/chart", json={
    "data": measurements,
    "config": {
        "chart_type": "xbar_r",
        "subgroup_size": 5
    }
})

result = response.json()
# Two charts: X-bar (mean) and R (range)
xbar_ucl = result["xbar_ucl"]
xbar_cl = result["xbar_cl"]
xbar_lcl = result["xbar_lcl"]
r_ucl = result["r_ucl"]
r_cl = result["r_cl"]
```

#### Example 3: Process Capability

Calculate capability indices:

```python
response = requests.post("http://localhost:8000/api/analysis/spc/capability", json={
    "data": process_measurements,
    "lsl": 9.5,    # Lower spec limit
    "usl": 10.5,   # Upper spec limit
    "target": 10.0
})

result = response.json()

# Capability indices
cp = result["cp"]       # Potential capability (inherent)
cpk = result["cpk"]     # Actual capability (with centering)
pp = result["pp"]       # Performance (overall)
ppk = result["ppk"]     # Performance (with centering)
cpm = result["cpm"]     # Taguchi index

# Interpretation
print(f"Cp = {cp:.2f}")
if cp >= 1.33:
    print("Process is capable (Cp ≥ 1.33)")
elif cp >= 1.00:
    print("Process is marginally capable")
else:
    print("Process is not capable")

print(f"Cpk = {cpk:.2f}")
print(f"Expected yield: {result['expected_yield']*100:.4f}%")
print(f"Expected defects: {result['expected_defects_ppm']:.1f} PPM")
```

**Capability Index Guidelines:**
- **Cp, Cpk ≥ 1.67**: World class (6σ process)
- **Cp, Cpk ≥ 1.33**: Adequate for most processes
- **Cp, Cpk ≥ 1.00**: Minimum acceptable
- **Cp, Cpk < 1.00**: Process not capable

### Report Generation

#### Example 1: Create Multi-Section HTML Report

```python
import base64

# Create report sections
sections = [
    {
        "title": "Executive Summary",
        "content": """
        This report presents the results of quality control analysis
        for Batch #12345. All measurements were within specification.
        """,
        "plots": [],
        "tables": []
    },
    {
        "title": "Statistical Analysis",
        "content": "Process capability analysis shows Cpk = 1.45",
        "plots": [],
        "tables": [
            {
                "headers": ["Metric", "Value", "Specification"],
                "rows": [
                    ["Mean", "10.02", "10.0 ± 0.5"],
                    ["Std Dev", "0.15", "< 0.2"],
                    ["Cp", "1.67", "≥ 1.33"],
                    ["Cpk", "1.45", "≥ 1.33"]
                ]
            }
        ]
    },
    {
        "title": "Control Chart",
        "content": "Process is in statistical control with no violations detected.",
        "plots": ["data:image/png;base64,iVBORw0KGgoAAAA..."],  # Your plot
        "tables": []
    }
]

response = requests.post("http://localhost:8000/api/analysis/report/generate", json={
    "sections": sections,
    "config": {
        "title": "Quality Control Report - Batch #12345",
        "author": "QC Lab",
        "format": "html",
        "include_timestamp": True,
        "include_toc": True,
        "custom_css": "body { font-family: Arial; }"
    }
})

report = response.json()
report_id = report["report_id"]
html_content = report["content"]

# Save to file
with open(f"report_{report_id}.html", "w") as f:
    f.write(html_content)
```

#### Example 2: Markdown Report

```python
response = requests.post("http://localhost:8000/api/analysis/report/generate", json={
    "sections": sections,
    "config": {
        "title": "Analysis Report",
        "format": "markdown"
    }
})

markdown_content = response.json()["content"]
```

### Batch Processing

#### Example 1: Process Multiple Files

```python
# Submit batch job
response = requests.post("http://localhost:8000/api/analysis/batch/submit", json={
    "job_name": "Filter all datasets",
    "input_files": [
        "/data/experiment1.json",
        "/data/experiment2.json",
        "/data/experiment3.json"
    ],
    "output_dir": "/data/filtered",
    "operation": "filter",
    "operation_config": {
        "filter_type": "lowpass",
        "cutoff_freq": 50.0,
        "sample_rate": 1000.0
    },
    "parallel": True,
    "max_workers": 4
})

job_id = response.json()["job_id"]

# Check status
status_response = requests.get(f"http://localhost:8000/api/analysis/batch/status/{job_id}")
status = status_response.json()

print(f"Status: {status['status']}")
print(f"Completed: {status['completed_files']}/{status['total_files']}")

# When complete
if status['status'] == 'completed':
    print(f"Output files: {status['output_files']}")
```

#### Example 2: Monitor Batch Job

```python
import time

job_id = "batch_a1b2c3d4"

while True:
    response = requests.get(f"http://localhost:8000/api/analysis/batch/status/{job_id}")
    status = response.json()

    print(f"Progress: {status['completed_files']}/{status['total_files']}")

    if status['status'] in ['completed', 'failed', 'cancelled']:
        break

    time.sleep(2)

if status['status'] == 'completed':
    print("Batch processing complete!")
    print(f"Output files: {status['output_files']}")
else:
    print(f"Job ended with status: {status['status']}")
    if status['errors']:
        print("Errors:")
        for error in status['errors']:
            print(f"  - {error}")
```

## API Reference

### Signal Filtering Endpoints

#### POST `/api/analysis/filter`

Apply digital filter to signal data.

**Request:**
```json
{
  "data": [0.1, 0.2, 0.15, ...],
  "time": [0.0, 0.001, 0.002, ...],
  "config": {
    "filter_type": "lowpass",
    "filter_method": "butterworth",
    "cutoff_freq": 50.0,
    "sample_rate": 1000.0,
    "order": 4,
    "zero_phase": true
  }
}
```

**Response:**
```json
{
  "filtered_data": [...],
  "time": [...],
  "actual_cutoff": 50.0,
  "config": {...}
}
```

#### POST `/api/analysis/filter/notch`

Remove specific frequency (e.g., 60 Hz power line noise).

**Request:**
```json
{
  "data": [...],
  "frequency": 60.0,
  "quality_factor": 30.0,
  "sample_rate": 1000.0
}
```

#### POST `/api/analysis/filter/moving-average`

Apply moving average smoothing.

**Request:**
```json
{
  "data": [...],
  "window_size": 10
}
```

#### POST `/api/analysis/filter/savitzky-golay`

Apply Savitzky-Golay smoothing (better feature preservation).

**Request:**
```json
{
  "data": [...],
  "window_size": 11,
  "poly_order": 3
}
```

### Resampling Endpoints

#### POST `/api/analysis/resample`

Resample data to new rate or number of points.

**Request:**
```json
{
  "x_data": [...],
  "y_data": [...],
  "config": {
    "method": "cubic",
    "target_rate": 100.0,
    "anti_aliasing": true
  },
  "original_rate": 1000.0
}
```

**Response:**
```json
{
  "x_data": [...],
  "y_data": [...]
}
```

#### POST `/api/analysis/interpolate-missing`

Interpolate missing (NaN) data points.

**Request:**
```json
{
  "x_data": [...],
  "y_data": [1.0, NaN, 3.0, ...],
  "method": "cubic"
}
```

### Curve Fitting Endpoints

#### POST `/api/analysis/fit`

Fit curve to data.

**Request:**
```json
{
  "x_data": [...],
  "y_data": [...],
  "config": {
    "fit_type": "exponential",
    "initial_guess": [1.0, -0.5, 0.0],
    "bounds": [[-10, -10, -10], [10, 10, 10]]
  }
}
```

**Response:**
```json
{
  "coefficients": [5.2, -0.234, 0.12],
  "fitted_data": [...],
  "x_data": [...],
  "y_data": [...],
  "r_squared": 0.995,
  "rmse": 0.012,
  "residuals": [...],
  "equation": "y = 5.2 * exp(-0.234x) + 0.12",
  "config": {...}
}
```

**Fit Types:**
- `linear` - y = mx + b
- `polynomial` - y = aₙxⁿ + ... + a₁x + a₀
- `exponential` - y = a·exp(b·x) + c
- `logarithmic` - y = a·ln(x) + b
- `power` - y = a·xᵇ
- `sinusoidal` - y = a·sin(b·x + c) + d
- `gaussian` - y = a·exp(-(x-μ)²/(2σ²)) + d
- `custom` - User-defined function

#### POST `/api/analysis/fit/predict`

Predict Y values for new X values using fit coefficients.

**Request:**
```json
{
  "coefficients": [1.5, -0.2, 0.5],
  "x_new": [10, 20, 30],
  "fit_type": "exponential"
}
```

### SPC Endpoints

#### POST `/api/analysis/spc/chart`

Generate statistical process control chart.

**Request:**
```json
{
  "data": [...],
  "config": {
    "chart_type": "individuals",
    "subgroup_size": 1
  }
}
```

**Response:**
```json
{
  "chart_type": "individuals",
  "center_line": 10.05,
  "upper_control_limit": 10.52,
  "lower_control_limit": 9.58,
  "out_of_control_points": [
    {"index": 42, "value": 10.65, "reason": "Point above UCL"}
  ],
  "rule_violations": [
    {"rule": "Western Electric Rule 1", "indices": [42]}
  ],
  "config": {...}
}
```

**Chart Types:**
- `xbar_r` - X-bar and R chart (subgrouped data)
- `xbar_s` - X-bar and S chart (larger subgroups)
- `individuals` - Individuals and Moving Range
- `p_chart` - Proportion defective
- `c_chart` - Count of defects
- `u_chart` - Defects per unit

#### POST `/api/analysis/spc/capability`

Analyze process capability.

**Request:**
```json
{
  "data": [...],
  "lsl": 9.5,
  "usl": 10.5,
  "target": 10.0
}
```

**Response:**
```json
{
  "cp": 1.45,
  "cpk": 1.38,
  "pp": 1.42,
  "ppk": 1.35,
  "cpm": 1.40,
  "expected_yield": 0.999997,
  "expected_defects_ppm": 3.2,
  "process_mean": 10.02,
  "process_std": 0.115,
  "assessment": "Process is capable (Cpk ≥ 1.33)"
}
```

### Report Generation Endpoints

#### POST `/api/analysis/report/generate`

Generate analysis report.

**Request:**
```json
{
  "sections": [
    {
      "title": "Results",
      "content": "Analysis shows...",
      "plots": ["data:image/png;base64,..."],
      "tables": [{"headers": [...], "rows": [...]}]
    }
  ],
  "config": {
    "title": "Analysis Report",
    "author": "Lab Tech",
    "format": "html",
    "include_timestamp": true,
    "include_toc": true
  }
}
```

**Response:**
```json
{
  "report_id": "report_a1b2c3d4",
  "title": "Analysis Report",
  "content": "<html>...</html>",
  "format": "html",
  "timestamp": "2025-11-13T10:30:00",
  "config": {...}
}
```

### Batch Processing Endpoints

#### POST `/api/analysis/batch/submit`

Submit batch processing job.

**Request:**
```json
{
  "job_name": "Filter all data",
  "input_files": ["/data/file1.json", "/data/file2.json"],
  "output_dir": "/data/filtered",
  "operation": "filter",
  "operation_config": {...},
  "parallel": true,
  "max_workers": 4
}
```

**Response:**
```json
{
  "job_id": "batch_a1b2c3d4",
  "message": "Batch job submitted"
}
```

#### GET `/api/analysis/batch/status/{job_id}`

Get batch job status.

**Response:**
```json
{
  "job_id": "batch_a1b2c3d4",
  "status": "running",
  "config": {...},
  "started_at": "2025-11-13T10:00:00",
  "total_files": 10,
  "completed_files": 6,
  "failed_files": 0,
  "output_files": [...],
  "errors": []
}
```

#### POST `/api/analysis/batch/cancel/{job_id}`

Cancel running batch job.

#### GET `/api/analysis/batch/list`

List all batch jobs.

### Utility Endpoints

#### GET `/api/analysis/info`

Get analysis system information and capabilities.

**Response:**
```json
{
  "filters": {
    "types": ["lowpass", "highpass", "bandpass", "bandstop"],
    "methods": ["butterworth", "chebyshev1", "chebyshev2", "bessel", "elliptic", "fir"]
  },
  "resampling": {
    "methods": ["linear", "cubic", "nearest", "spline", "fourier"]
  },
  "fitting": {
    "types": ["linear", "polynomial", "exponential", "logarithmic", "power", "sinusoidal", "gaussian", "custom"]
  },
  "spc": {
    "chart_types": ["xbar_r", "xbar_s", "individuals", "p_chart", "c_chart", "u_chart"]
  },
  "reports": {
    "formats": ["pdf", "html", "markdown", "json"]
  },
  "batch": {
    "operations": ["filter", "fit", "resample"]
  }
}
```

## Best Practices

### Signal Filtering

1. **Choose Appropriate Filter Type**
   - Butterworth: General purpose, smooth response
   - Chebyshev: Sharper cutoff, some ripple acceptable
   - Bessel: Preserve waveform shape (linear phase)
   - FIR: Always stable, linear phase

2. **Filter Order Selection**
   - Higher order = sharper cutoff but more phase distortion
   - Start with order 4-6 for most applications
   - Use zero-phase filtering (`filtfilt`) when phase matters

3. **Cutoff Frequency**
   - Set cutoff below highest frequency of interest
   - For noise removal: cutoff = 2-3× signal bandwidth
   - Must satisfy Nyquist: cutoff < sample_rate / 2

4. **Avoid Over-Filtering**
   - Can remove important signal features
   - Check filtered signal visually
   - Compare frequency spectra before/after

### Curve Fitting

1. **Provide Good Initial Guesses**
   - Especially critical for nonlinear fits
   - Estimate from data visualization
   - Use domain knowledge

2. **Check Fit Quality**
   - R² > 0.95 is good for most applications
   - Examine residuals plot for patterns
   - Residuals should be randomly distributed

3. **Use Bounds When Needed**
   - Prevent unphysical parameters
   - Improve convergence
   - Example: amplitude must be positive

4. **Validate Outside Training Range**
   - Extrapolation can be unreliable
   - Test predictions on new data
   - Document valid range

### Statistical Process Control

1. **Collect Sufficient Data**
   - Minimum 20-25 subgroups for control charts
   - At least 50-100 samples for capability analysis
   - More data = better estimates

2. **Ensure Process Stability**
   - Remove special causes before calculating capability
   - Process must be in statistical control
   - No trends or patterns

3. **Set Realistic Specifications**
   - Based on customer requirements, not process capability
   - LSL and USL should be meaningful
   - Target should be centered when possible

4. **Take Action on Violations**
   - Investigate out-of-control points immediately
   - Document corrective actions
   - Update control limits after process changes

### Report Generation

1. **Structure Reports Logically**
   - Executive summary first
   - Detailed analysis in middle
   - Conclusions and recommendations last

2. **Use Clear Visualizations**
   - High-resolution plots (300 DPI minimum)
   - Proper axis labels and units
   - Legends and annotations

3. **Include Context**
   - Measurement conditions
   - Equipment used
   - Data collection dates

4. **Automate Recurring Reports**
   - Use templates for consistency
   - Batch process multiple datasets
   - Schedule report generation

### Batch Processing

1. **Test on Single File First**
   - Verify operations work correctly
   - Check output format
   - Estimate processing time

2. **Use Parallel Processing**
   - Set `max_workers` = number of CPU cores
   - Significant speedup for I/O-bound tasks
   - Monitor memory usage

3. **Handle Errors Gracefully**
   - Check job status regularly
   - Review error messages
   - Implement retry logic if needed

4. **Organize Output Files**
   - Use descriptive output directory names
   - Include operation name in output filenames
   - Maintain input-output mapping

## Common Use Cases

### 1. Oscilloscope Data Analysis

```python
# Load oscilloscope data, filter noise, fit decay
waveform_response = requests.get(f"http://localhost:8000/api/waveform/capture/{equipment_id}")
waveform = waveform_response.json()

# Filter 60 Hz noise
filtered = requests.post("http://localhost:8000/api/analysis/filter/notch", json={
    "data": waveform["voltage"],
    "frequency": 60.0,
    "quality_factor": 30.0,
    "sample_rate": waveform["sample_rate"]
}).json()

# Fit exponential decay
fit_result = requests.post("http://localhost:8000/api/analysis/fit", json={
    "x_data": waveform["time"],
    "y_data": filtered["filtered_data"],
    "config": {"fit_type": "exponential"}
}).json()

time_constant = -1.0 / fit_result["coefficients"][1]
print(f"Time constant: {time_constant*1e6:.2f} µs")
```

### 2. Manufacturing Quality Control

```python
# Collect daily measurements
measurements = get_daily_measurements()

# Generate control chart
chart = requests.post("http://localhost:8000/api/analysis/spc/chart", json={
    "data": measurements,
    "config": {"chart_type": "xbar_r", "subgroup_size": 5}
}).json()

# Check capability
capability = requests.post("http://localhost:8000/api/analysis/spc/capability", json={
    "data": measurements,
    "lsl": 9.5,
    "usl": 10.5
}).json()

# Generate daily report
if chart["out_of_control_points"] or capability["cpk"] < 1.33:
    # Alert quality engineer
    send_alert(chart, capability)
```

### 3. Spectroscopy Peak Analysis

```python
# Load spectrum
spectrum = load_spectrum_data()

# Smooth with Savitzky-Golay
smoothed = requests.post("http://localhost:8000/api/analysis/filter/savitzky-golay", json={
    "data": spectrum["intensity"],
    "window_size": 11,
    "poly_order": 3
}).json()

# Fit Gaussian to each peak
peaks = find_peaks(smoothed["smoothed_data"])
for peak_region in peaks:
    fit = requests.post("http://localhost:8000/api/analysis/fit", json={
        "x_data": peak_region["wavelength"],
        "y_data": peak_region["intensity"],
        "config": {"fit_type": "gaussian"}
    }).json()

    peak_center = fit["coefficients"][1]
    peak_width = fit["coefficients"][2]
    print(f"Peak at {peak_center:.2f} nm, FWHM = {2.355*peak_width:.2f} nm")
```

### 4. Calibration Data Processing

```python
# Process calibration measurements
cal_points = [(0, 0.01), (1, 0.98), (2, 2.01), (3, 2.99), (4, 4.02)]
x_cal, y_cal = zip(*cal_points)

# Fit linear calibration curve
fit = requests.post("http://localhost:8000/api/analysis/fit", json={
    "x_data": list(x_cal),
    "y_data": list(y_cal),
    "config": {"fit_type": "linear"}
}).json()

slope = fit["coefficients"][0]
intercept = fit["coefficients"][1]
r_squared = fit["r_squared"]

if r_squared > 0.999:
    print("Calibration valid")
    # Apply to measurements
    corrected = apply_calibration(raw_data, slope, intercept)
```

## Troubleshooting

### Filter Not Working as Expected

**Problem:** Filtered signal still noisy

**Solutions:**
- Increase filter order
- Lower cutoff frequency
- Try different filter method (Chebyshev has sharper rolloff)
- Use Savitzky-Golay for preserving features
- Apply multiple passes (but check phase distortion)

### Curve Fit Fails to Converge

**Problem:** "Optimal parameters not found" error

**Solutions:**
- Provide better initial guess
- Add bounds to constrain parameters
- Check if data matches model (plot first)
- Try simpler model (polynomial instead of custom)
- Ensure sufficient data points (at least 3× parameters)

### Control Chart Shows Many Violations

**Problem:** Too many out-of-control points

**Solutions:**
- Check if process is actually stable
- Verify measurement system accuracy
- Ensure subgroup size is appropriate
- Look for special causes (tool wear, operator changes)
- May need to separate different process conditions

### Batch Processing Fails

**Problem:** Job status shows failed files

**Solutions:**
- Check error messages in job result
- Verify file format (JSON or CSV)
- Ensure all required fields present in data
- Test operation on single file first
- Check file permissions and paths

### Report Generation Issues

**Problem:** Plots not showing in HTML report

**Solutions:**
- Ensure plots are base64 encoded
- Include "data:image/png;base64," prefix
- Check image data is valid
- Verify plot size is reasonable
- Try different image format (JPEG instead of PNG)

## Performance Tips

1. **Filtering Large Datasets**
   - Use FIR filters for very long signals (more efficient)
   - Consider downsampling first if possible
   - Process in chunks for huge files

2. **Batch Processing**
   - Enable parallel processing (`parallel: true`)
   - Set `max_workers` to number of CPU cores
   - Process similar file sizes together

3. **Curve Fitting**
   - Downsample data if > 10,000 points
   - Provide good initial guesses
   - Use simpler models when possible

4. **Report Generation**
   - Limit plot resolution (1920×1080 is sufficient)
   - Use JPEG for photos, PNG for graphs
   - Generate HTML instead of PDF for speed

## Integration Examples

### Python Client

```python
import requests
import numpy as np

class LabLinkAnalysisClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def filter_signal(self, data, time, filter_type="lowpass",
                     cutoff=50.0, sample_rate=1000.0):
        response = requests.post(f"{self.base_url}/api/analysis/filter", json={
            "data": data.tolist() if isinstance(data, np.ndarray) else data,
            "time": time.tolist() if isinstance(time, np.ndarray) else time,
            "config": {
                "filter_type": filter_type,
                "filter_method": "butterworth",
                "cutoff_freq": cutoff,
                "sample_rate": sample_rate,
                "order": 4,
                "zero_phase": True
            }
        })
        result = response.json()
        return np.array(result["filtered_data"])

    def fit_curve(self, x_data, y_data, fit_type="linear", **kwargs):
        response = requests.post(f"{self.base_url}/api/analysis/fit", json={
            "x_data": x_data.tolist() if isinstance(x_data, np.ndarray) else x_data,
            "y_data": y_data.tolist() if isinstance(y_data, np.ndarray) else y_data,
            "config": {"fit_type": fit_type, **kwargs}
        })
        return response.json()

    def spc_capability(self, data, lsl, usl, target=None):
        response = requests.post(f"{self.base_url}/api/analysis/spc/capability", json={
            "data": data.tolist() if isinstance(data, np.ndarray) else data,
            "lsl": lsl,
            "usl": usl,
            "target": target
        })
        return response.json()

# Usage
client = LabLinkAnalysisClient()

# Filter noisy signal
filtered = client.filter_signal(noisy_data, time_array, cutoff=100.0)

# Fit exponential
fit_result = client.fit_curve(x, y, "exponential")

# Check capability
capability = client.spc_capability(measurements, 9.5, 10.5)
```

### JavaScript/TypeScript Client

```typescript
class LabLinkAnalysisClient {
  constructor(private baseUrl: string = "http://localhost:8000") {}

  async filterSignal(
    data: number[],
    time: number[],
    options: {
      filterType?: string;
      cutoff?: number;
      sampleRate?: number;
    } = {}
  ): Promise<number[]> {
    const response = await fetch(`${this.baseUrl}/api/analysis/filter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data,
        time,
        config: {
          filter_type: options.filterType || "lowpass",
          filter_method: "butterworth",
          cutoff_freq: options.cutoff || 50.0,
          sample_rate: options.sampleRate || 1000.0,
          order: 4,
          zero_phase: true,
        },
      }),
    });

    const result = await response.json();
    return result.filtered_data;
  }

  async fitCurve(
    xData: number[],
    yData: number[],
    fitType: string = "linear"
  ): Promise<FitResult> {
    const response = await fetch(`${this.baseUrl}/api/analysis/fit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        x_data: xData,
        y_data: yData,
        config: { fit_type: fitType },
      }),
    });

    return await response.json();
  }
}

// Usage
const client = new LabLinkAnalysisClient();

const filtered = await client.filterSignal(noisyData, timeArray, {
  cutoff: 100.0,
});

const fitResult = await client.fitCurve(x, y, "exponential");
console.log(`R² = ${fitResult.r_squared}`);
```

## Support and Resources

- **Documentation**: See ROADMAP.md for development history
- **API Reference**: http://localhost:8000/docs (FastAPI interactive docs)
- **Examples**: See this user guide
- **Issues**: Report bugs and feature requests via project repository

## Version History

**v0.17.0** (Current)
- Initial release of Data Analysis Pipeline
- Signal filtering with 6 filter methods
- Data resampling and interpolation
- Curve fitting with 8 fit types
- Statistical Process Control (SPC)
- Automated report generation
- Batch processing engine
- 30+ REST API endpoints

---

**LabLink Data Analysis Pipeline** - Professional data analysis for laboratory equipment
