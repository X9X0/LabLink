# Performance Monitoring System - User Guide

## Overview

The LabLink Performance Monitoring System provides comprehensive tracking, analysis, and alerting for equipment and system performance. Monitor latency, throughput, error rates, and detect performance degradation before it impacts operations.

## Key Features

- **Baseline Tracking**: Establish performance baselines for comparison
- **Trend Analysis**: Detect performance trends and predict future issues
- **Degradation Detection**: Automatic alerts when performance degrades
- **SQLite Persistence**: Historical data storage for long-term analysis
- **Performance Reports**: Comprehensive performance insights
- **Alert Integration**: Automatic performance alerts with recommendations

## Quick Start

### 1. Record Performance Metrics

```python
import aiohttp

async def record_latency():
    metric = {
        "equipment_id": "power_supply_1",
        "component": "equipment_commands",
        "metric_type": "latency",
        "value": 45.2,
        "unit": "ms",
        "operation": "set_voltage"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post('http://localhost:8000/api/performance/metrics', json=metric) as resp:
            data = await resp.json()
            print(f"Deviation from baseline: {data['deviation_percent']}%")
```

### 2. Create Performance Baseline

```python
async def create_baseline():
    baseline_request = {
        "equipment_id": "power_supply_1",
        "component": "equipment_commands",
        "measurement_period_hours": 24.0
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post('http://localhost:8000/api/performance/baselines', json=baseline_request) as resp:
            data = await resp.json()
            baseline = data['baseline']
            print(f"Baseline created: {baseline['avg_latency_ms']}ms avg latency")
```

### 3. Analyze Performance Trends

```python
async def analyze_trends():
    async with aiohttp.ClientSession() as session:
        async with session.get('http://localhost:8000/api/performance/trends/equipment_commands?hours=24') as resp:
            data = await resp.json()
            trend = data['trend']
            print(f"Trend: {trend['direction']}")
            print(f"Predicted latency in 24h: {trend['predicted_value_24h']}ms")
```

## API Reference

### Metrics Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/performance/metrics` | Record a performance metric |
| GET | `/api/performance/metrics` | Retrieve performance metrics |

### Baseline Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/performance/baselines` | Create performance baseline |
| GET | `/api/performance/baselines/{component}` | Get baseline for component |

### Analysis Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/performance/trends/{component}` | Analyze performance trend |
| GET | `/api/performance/status/{component}` | Get performance status |
| POST | `/api/performance/reports` | Generate performance report |
| GET | `/api/performance/summary` | Get quick performance summary |

### Alert Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/performance/alerts` | Get performance alerts |
| POST | `/api/performance/alerts/{alert_id}/acknowledge` | Acknowledge alert |
| POST | `/api/performance/alerts/{alert_id}/resolve` | Resolve alert |

## Performance Metrics

### Metric Types

- **latency**: Command response time (milliseconds)
- **throughput**: Commands per second
- **error_rate**: Percentage of failed commands
- **cpu_usage**: CPU utilization percentage
- **memory_usage**: Memory utilization percentage
- **bandwidth**: Data transfer rate
- **queue_depth**: Command queue depth

### Performance Status

- **excellent**: Performance above baseline
- **good**: Performance at baseline
- **degraded**: Performance below baseline but acceptable
- **poor**: Performance significantly degraded
- **critical**: Performance critically degraded

### Trend Direction

- **improving**: Performance getting better
- **stable**: Performance steady
- **degrading**: Performance declining
- **critical**: Performance critically declining

## Creating Baselines

Baselines are calculated from historical data over a specified period. They provide reference values for detecting performance changes.

### Automatic Calculation

When creating a baseline, the system automatically calculates:

- Average latency
- 95th percentile latency
- 99th percentile latency
- Average throughput
- Error rate
- Warning/critical thresholds (auto-generated)

### Example Baseline Creation

```http
POST /api/performance/baselines
```

**Request:**
```json
{
  "equipment_id": "oscilloscope_1",
  "component": "data_acquisition",
  "measurement_period_hours": 24.0
}
```

**Response:**
```json
{
  "success": true,
  "baseline": {
    "baseline_id": "baseline_abc123",
    "avg_latency_ms": 42.5,
    "p95_latency_ms": 65.0,
    "p99_latency_ms": 85.0,
    "avg_throughput": 25.3,
    "latency_warning_threshold_ms": 97.5,
    "latency_critical_threshold_ms": 130.0,
    "sample_count": 1250
  }
}
```

## Trend Analysis

Trend analysis uses linear regression to detect performance changes over time.

### Trend Metrics

- **Slope**: Rate of change per hour
- **Correlation**: Confidence in trend (-1 to 1)
- **Predictions**: Estimated values in 1h and 24h
- **Time to Threshold**: Hours until threshold breach

### Example Trend Analysis

```http
GET /api/performance/trends/equipment_commands?equipment_id=power_supply_1&metric_type=latency&hours=24
```

**Response:**
```json
{
  "success": true,
  "trend": {
    "direction": "degrading",
    "slope": 0.5,
    "correlation": 0.85,
    "confidence": 0.85,
    "mean_value": 45.2,
    "predicted_value_1h": 45.7,
    "predicted_value_24h": 57.2,
    "time_to_threshold": 48.5,
    "deviation_from_baseline": 12.5
  }
}
```

## Performance Alerts

Alerts are automatically created when performance degrades beyond thresholds.

### Alert Severity

- **warning**: Degradation ≥20% from baseline
- **critical**: Degradation ≥50% from baseline

### Alert Recommendations

Each alert includes specific recommendations:

**For Latency Degradation:**
- Check equipment connection quality
- Verify network latency and bandwidth
- Review equipment load and queue depth
- Consider equipment restart

**For Throughput Degradation:**
- Check resource bottlenecks (CPU, memory, network)
- Review command batching
- Verify equipment not overloaded

**For Error Rate Increase:**
- Review error logs for patterns
- Check equipment health
- Verify command syntax
- Consider recalibration

## Performance Reports

Generate comprehensive performance reports for analysis.

### Example Report Request

```http
POST /api/performance/reports
```

**Request:**
```json
{
  "equipment_ids": ["power_supply_1", "oscilloscope_1"],
  "components": ["equipment_commands", "data_acquisition"],
  "hours": 24.0
}
```

**Response:**
```json
{
  "success": true,
  "report": {
    "overall_status": "good",
    "health_score": 85.2,
    "total_measurements": 5000,
    "avg_latency_ms": 43.5,
    "latency_vs_baseline_percent": 8.5,
    "active_alerts": 2,
    "degraded_components": ["data_acquisition"],
    "recommendations": [
      "1 component(s) showing performance degradation",
      "Monitor trends closely for further degradation"
    ]
  }
}
```

## Best Practices

### 1. Establish Baselines Early

Create baselines after initial equipment setup and system stabilization:

```python
# After 24 hours of operation
await create_baseline(equipment_id, component, hours=24)
```

### 2. Regular Monitoring

Monitor performance continuously:

```python
# Record metrics after each operation
await record_metric(component, "latency", response_time_ms)
```

### 3. Review Trends Weekly

Check performance trends regularly:

```python
# Weekly trend analysis
trend = await analyze_trend(component, hours=168)  # 1 week
```

### 4. Respond to Alerts Promptly

Acknowledge and resolve alerts quickly:

```python
# Acknowledge alert
await acknowledge_alert(alert_id)

# After fixing issue
await resolve_alert(alert_id)
```

### 5. Update Baselines After Changes

Recalibrate baselines after system changes:

```python
# After firmware update or configuration change
await create_baseline(equipment_id, component, hours=24)
```

## Troubleshooting

### High Latency

**Symptoms:**
- Latency trend showing "degrading"
- Latency >2x baseline

**Solutions:**
1. Check network connectivity
2. Verify equipment not overloaded
3. Review system resources (CPU, memory)
4. Check for competing processes

### Low Throughput

**Symptoms:**
- Throughput <70% of baseline
- Increasing command queue depth

**Solutions:**
1. Reduce command rate
2. Implement command batching
3. Check for resource bottlenecks
4. Review equipment specifications

### Increasing Error Rate

**Symptoms:**
- Error rate trending up
- High number of retries

**Solutions:**
1. Review error logs
2. Check equipment health
3. Verify command syntax
4. Test with simple commands
5. Consider equipment recalibration

## Database Maintenance

Performance data is stored in SQLite database at `data/performance.db`.

### Database Size Management

The database grows with metrics. Monitor size:

```bash
ls -lh data/performance.db
```

### Cleanup Old Data

Implement retention policy (example):

```sql
DELETE FROM performance_metrics 
WHERE timestamp < datetime('now', '-90 days');
```

## Integration with Diagnostics

Performance monitoring integrates with the diagnostics system:

- Performance alerts can trigger diagnostic checks
- Diagnostic health scores include performance metrics
- Baseline deviations affect equipment health scores

## Version

**Version**: 0.13.0  
**Last Updated**: January 2025
