# LabLink Log Analysis Guide

Complete guide for analyzing, querying, and monitoring LabLink application logs.

## Table of Contents

1. [Overview](#overview)
2. [Log Analyzer CLI](#log-analyzer-cli)
3. [Log Monitor](#log-monitor)
4. [User Identification](#user-identification)
5. [Common Use Cases](#common-use-cases)
6. [Advanced Topics](#advanced-topics)
7. [Best Practices](#best-practices)

---

## Overview

LabLink provides a comprehensive suite of log analysis tools to help you:

- **Query and filter logs** - Find specific events across all log files
- **Generate reports** - Analyze patterns and trends
- **Monitor in real-time** - Watch logs as they happen
- **Detect anomalies** - Identify unusual patterns automatically
- **Track user actions** - Audit user activity across the system

### Available Tools

| Tool | Purpose | Location |
|------|---------|----------|
| `log_analyzer.py` | Query, analyze, and report on historical logs | `server/log_analyzer.py` |
| `log_monitor.py` | Real-time log monitoring with filtering | `server/log_monitor.py` |

### Log Files

LabLink generates the following log files in the `./logs` directory:

| File | Content | Size Limit | Backups |
|------|---------|------------|---------|
| `lablink.log` | Main application logs | 10 MB | 5 |
| `access.log` | HTTP requests/responses | 50 MB | 30 |
| `performance.log` | Performance metrics | 50 MB | 10 |
| `audit.log` | Security and user actions | 100 MB | 30 |
| `equipment.log` | Equipment events | 50 MB | 20 |
| `equipment_{id}.log` | Per-equipment logs | 10 MB | 5 |

All logs use **structured JSON format** for easy parsing and analysis.

---

## Log Analyzer CLI

The log analyzer is a powerful command-line tool for querying and analyzing historical logs.

### Installation

No installation required! The tool uses Python's standard library.

```bash
# Make executable (optional)
chmod +x server/log_analyzer.py
```

### Basic Usage

```bash
# Query all logs
python server/log_analyzer.py query

# Query with filters
python server/log_analyzer.py query --level ERROR --last 1h

# Generate reports
python server/log_analyzer.py report --type summary

# Detect anomalies
python server/log_analyzer.py anomaly --sensitivity high
```

### Query Command

Search and filter logs with powerful query capabilities.

#### Basic Filtering

```bash
# Filter by log level
python server/log_analyzer.py query --level ERROR CRITICAL

# Filter by logger name
python server/log_analyzer.py query --logger equipment audit

# Filter by time range
python server/log_analyzer.py query --last 1h    # Last hour
python server/log_analyzer.py query --last 30m   # Last 30 minutes
python server/log_analyzer.py query --last 2d    # Last 2 days

# Limit results
python server/log_analyzer.py query --limit 50
```

#### Keyword and Pattern Matching

```bash
# Search for keywords (case-insensitive by default)
python server/log_analyzer.py query --keyword "connection" "failed"

# Case-sensitive search
python server/log_analyzer.py query --keyword "ConnectionError" --case-sensitive

# Regex pattern matching
python server/log_analyzer.py query --regex "timeout.*equipment"
```

#### Combined Filters

```bash
# Find all errors in equipment logger from last hour
python server/log_analyzer.py query \
    --level ERROR \
    --logger equipment \
    --last 1h

# Search for connection failures with details
python server/log_analyzer.py query \
    --keyword "connection" "failed" \
    --show-extra \
    --limit 10
```

#### Output Formats

```bash
# Text output (default, human-readable)
python server/log_analyzer.py query --level ERROR

# JSON output (machine-readable)
python server/log_analyzer.py query --level ERROR --output-format json

# CSV output (for spreadsheets)
python server/log_analyzer.py query --level ERROR --output-format csv

# Save to file
python server/log_analyzer.py query --level ERROR -o errors.json --output-format json
```

#### Examples

**Example 1: Find all equipment connection failures**

```bash
python server/log_analyzer.py query \
    --logger equipment \
    --keyword "connection" \
    --level ERROR WARNING \
    --last 24h \
    -o equipment_issues.txt
```

**Example 2: Audit user actions from specific time period**

```bash
python server/log_analyzer.py query \
    --logger audit \
    --last 1d \
    --output-format json \
    -o audit_report.json
```

**Example 3: Find slow API requests**

```bash
python server/log_analyzer.py query \
    --logger access \
    --regex "duration_ms.*[5-9][0-9]{3}" \
    --limit 20
```

### Report Command

Generate comprehensive analysis reports.

#### Report Types

**1. Summary Report**

High-level overview of log activity:

```bash
python server/log_analyzer.py report --type summary
```

Output includes:
- Total entry count
- Time range covered
- Distribution by log level
- Distribution by logger
- Most common messages

**2. Error Analysis Report**

Detailed error analysis:

```bash
python server/log_analyzer.py report --type errors
```

Output includes:
- Total error count
- Error types and frequencies
- Error timeline (errors per hour)
- Affected modules
- Top error messages

**3. Performance Analysis Report**

Performance metrics and slow operations:

```bash
python server/log_analyzer.py report --type performance
```

Output includes:
- Duration statistics (mean, median, min, max, stdev)
- Memory usage statistics
- Top 10 slowest operations
- Performance trends

#### Report Formats

```bash
# Text format (human-readable)
python server/log_analyzer.py report --type summary --format text

# JSON format (machine-readable)
python server/log_analyzer.py report --type summary --format json

# Save to file
python server/log_analyzer.py report --type errors -o error_analysis.txt
```

#### Examples

**Example 1: Daily summary report**

```bash
python server/log_analyzer.py report \
    --type summary \
    --format text \
    -o daily_summary_$(date +%Y%m%d).txt
```

**Example 2: Performance analysis for optimization**

```bash
python server/log_analyzer.py report \
    --type performance \
    --format json \
    -o performance_baseline.json
```

**Example 3: Weekly error report for review**

```bash
python server/log_analyzer.py report \
    --type errors \
    -o weekly_errors.txt
```

### Anomaly Detection Command

Automatically detect unusual patterns in logs.

#### Sensitivity Levels

```bash
# Low sensitivity (fewer alerts, only major anomalies)
python server/log_analyzer.py anomaly --sensitivity low

# Medium sensitivity (balanced, default)
python server/log_analyzer.py anomaly --sensitivity medium

# High sensitivity (more alerts, catch subtle issues)
python server/log_analyzer.py anomaly --sensitivity high
```

#### Detected Anomaly Types

1. **Error Spikes** - Sudden increase in error rate
2. **Repeated Errors** - Same error occurring rapidly
3. **Slow Operations** - Operations taking significantly longer than usual

#### Example Output

```
Found 3 anomalies:

1. ERROR_SPIKE - Severity: high
   timestamp: 2025-01-15T14:30:00
   count: 45
   expected: 5.2

2. REPEATED_ERROR - Severity: high
   message: Equipment connection timeout
   count: 12
   first_occurrence: 2025-01-15T14:32:15

3. SLOW_OPERATION - Severity: medium
   timestamp: 2025-01-15T15:10:22
   operation: Database query
   duration_ms: 5234
   expected_ms: 120.5
```

---

## Log Monitor

Real-time log monitoring with filtering and alerting.

### Basic Usage

```bash
# Monitor all logs in real-time
python server/log_monitor.py --follow

# Monitor with filters
python server/log_monitor.py --follow --level ERROR WARNING

# Monitor with alerts
python server/log_monitor.py --follow --alert-on "failed" "timeout"
```

### Features

- **Real-time streaming** - See logs as they're written
- **Color-coded output** - Easy visual identification by level
- **Filtering** - Focus on relevant logs only
- **Alerting** - Highlight critical events
- **Statistics** - Track activity during session

### Filtering

```bash
# Filter by log level
python server/log_monitor.py --follow --level ERROR CRITICAL

# Filter by logger
python server/log_monitor.py --follow --logger equipment audit

# Filter by keywords
python server/log_monitor.py --follow --keyword "connection" "equipment"

# Combined filters
python server/log_monitor.py --follow \
    --level WARNING ERROR \
    --logger equipment \
    --keyword "timeout"
```

### Alerting

Highlight specific patterns for immediate attention:

```bash
# Alert on specific keywords
python server/log_monitor.py --follow \
    --alert-on "failed" "error" "timeout" "critical"

# Alerts always trigger on CRITICAL level
python server/log_monitor.py --follow
```

When an alert triggers, you'll see:

```
================================================================================
🚨 ALERT - Pattern matched
================================================================================
[14:30:15.123] ERROR    lablink.equipment              Equipment connection failed
  └─ equipment_id=PSU_001 error=Connection timeout after 30s
================================================================================
```

### Statistics Display

Show periodic statistics during monitoring:

```bash
# Show stats every 60 seconds
python server/log_monitor.py --follow --stats-interval 60
```

Statistics include:
- Total entries processed
- Count by log level
- Top loggers
- Alerts triggered
- Session duration

### Color Output

Colors are enabled by default in interactive terminals:

- **DEBUG** - Cyan
- **INFO** - Green
- **WARNING** - Yellow
- **ERROR** - Red
- **CRITICAL** - Magenta (bold)

To disable colors:

```bash
python server/log_monitor.py --follow --no-color
```

### Examples

**Example 1: Monitor production errors**

```bash
python server/log_monitor.py --follow \
    --level ERROR CRITICAL \
    --alert-on "database" "connection"
```

**Example 2: Monitor equipment activity**

```bash
python server/log_monitor.py --follow \
    --logger equipment \
    --stats-interval 30
```

**Example 3: Monitor API performance**

```bash
python server/log_monitor.py --follow \
    --logger access \
    --keyword "duration_ms"
```

---

## User Identification

LabLink logs now include user identification for audit and analysis purposes.

### Supported Authentication Methods

The logging middleware automatically extracts user information from:

1. **Session-based auth** - `request.state.user`
2. **Custom headers** - `X-User-ID`, `X-User-Name`, `X-User-Email`, `X-User-Role`
3. **API keys** - `X-API-Key` header
4. **JWT tokens** - `Authorization: Bearer <token>`

### Log Fields

User-related fields in logs:

| Field | Description | Example |
|-------|-------------|---------|
| `user_id` | Unique user identifier | `"user_12345"` |
| `user_name` | Display name | `"John Doe"` |
| `user_email` | Email address | `"john@example.com"` |
| `user_role` | User role/permission level | `"admin"` |
| `auth_method` | Authentication method used | `"jwt"` |

### Example Log Entry

```json
{
  "timestamp": "2025-01-15T14:30:00.123456",
  "level": "INFO",
  "logger": "lablink.audit",
  "message": "User action: POST /api/equipment/connect",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "method": "POST",
  "path": "/api/equipment/connect",
  "status_code": 200,
  "user_id": "user_12345",
  "user_name": "John Doe",
  "user_email": "john@example.com",
  "user_role": "admin",
  "auth_method": "jwt"
}
```

### Querying by User

```bash
# Find all actions by specific user
python server/log_analyzer.py query \
    --keyword "user_12345" \
    --logger audit

# Find all admin actions
python server/log_analyzer.py query \
    --keyword "admin" \
    --logger audit \
    --last 7d

# Monitor specific user in real-time
python server/log_monitor.py --follow \
    --keyword "user_12345"
```

### Equipment Event Logging with User

When logging equipment events programmatically, include user information:

```python
from logging_config.middleware import equipment_event_logger

# Log equipment connection with user
equipment_event_logger.log_connection(
    equipment_id="PSU_001",
    address="USB0::0x1234::0x5678::INSTR",
    success=True,
    user_id="user_12345",
    user_name="John Doe"
)

# Log equipment command with user
equipment_event_logger.log_command(
    equipment_id="PSU_001",
    command="SET_VOLTAGE 5.0",
    success=True,
    duration_ms=45.2,
    user_id="user_12345",
    user_name="John Doe"
)
```

---

## Common Use Cases

### Use Case 1: Debugging Production Issues

**Scenario**: Users report intermittent equipment connection failures.

**Solution**:

```bash
# 1. Find all connection-related errors
python server/log_analyzer.py query \
    --logger equipment \
    --keyword "connection" \
    --level ERROR WARNING \
    --last 7d \
    -o connection_issues.json \
    --output-format json

# 2. Analyze patterns
python server/log_analyzer.py report --type errors

# 3. Monitor for new occurrences
python server/log_monitor.py --follow \
    --logger equipment \
    --keyword "connection" \
    --alert-on "failed" "timeout"
```

### Use Case 2: Performance Optimization

**Scenario**: Need to identify and optimize slow API endpoints.

**Solution**:

```bash
# 1. Generate performance baseline
python server/log_analyzer.py report \
    --type performance \
    -o performance_baseline.txt

# 2. Find slowest operations
python server/log_analyzer.py query \
    --logger access \
    --keyword "duration_ms" \
    --output-format json | \
    jq 'sort_by(.duration_ms) | reverse | .[0:10]'

# 3. Monitor specific endpoint
python server/log_monitor.py --follow \
    --logger access \
    --keyword "/api/equipment"
```

### Use Case 3: Security Audit

**Scenario**: Need to audit all user actions for compliance.

**Solution**:

```bash
# 1. Export all audit logs for date range
python server/log_analyzer.py query \
    --logger audit \
    --last 30d \
    --output-format csv \
    -o security_audit_$(date +%Y%m).csv

# 2. Find all admin actions
python server/log_analyzer.py query \
    --logger audit \
    --keyword "admin" \
    --last 30d

# 3. Monitor privileged operations
python server/log_monitor.py --follow \
    --logger audit \
    --alert-on "delete" "emergency" "disconnect"
```

### Use Case 4: Anomaly Detection

**Scenario**: Automatically detect unusual system behavior.

**Solution**:

```bash
# 1. Run daily anomaly detection
python server/log_analyzer.py anomaly --sensitivity medium

# 2. Set up scheduled check (cron)
# Add to crontab: 0 */6 * * * python /path/to/log_analyzer.py anomaly > /tmp/anomalies.txt

# 3. Monitor and alert in real-time
python server/log_monitor.py --follow \
    --level ERROR CRITICAL \
    --alert-on "spike" "anomaly"
```

### Use Case 5: Daily Reporting

**Scenario**: Generate daily summary reports for team review.

**Solution**:

Create a script `daily_report.sh`:

```bash
#!/bin/bash
DATE=$(date +%Y%m%d)
REPORT_DIR="./reports/$DATE"
mkdir -p "$REPORT_DIR"

# Summary report
python server/log_analyzer.py report \
    --type summary \
    -o "$REPORT_DIR/summary.txt"

# Error analysis
python server/log_analyzer.py report \
    --type errors \
    -o "$REPORT_DIR/errors.txt"

# Performance analysis
python server/log_analyzer.py report \
    --type performance \
    -o "$REPORT_DIR/performance.txt"

# Anomaly detection
python server/log_analyzer.py anomaly \
    --sensitivity medium \
    > "$REPORT_DIR/anomalies.txt"

echo "Daily report generated in $REPORT_DIR"
```

Run via cron:

```bash
# Run at 1 AM daily
0 1 * * * /path/to/daily_report.sh
```

---

## Advanced Topics

### Integration with External Tools

#### Elasticsearch/ELK Stack

Export logs to Elasticsearch for advanced analytics:

```bash
# Export to JSON for bulk import
python server/log_analyzer.py query \
    --output-format json \
    --last 1d \
    -o logs_for_elk.json

# Use Logstash to import
# (Configure logstash.conf with JSON input)
```

#### Splunk

```bash
# Splunk can directly ingest JSON log files
# Point Splunk to ./logs directory
# Configure source type as JSON
```

#### Grafana + Loki

```bash
# Use Promtail to ship logs to Loki
# Configure promtail.yml to watch ./logs/*.log
# Query in Grafana with LogQL
```

### Programmatic Access

Use the log analyzer classes in your own Python scripts:

```python
from pathlib import Path
from log_analyzer import LogReader, LogQuery, LogAnalyzer

# Read logs
log_dir = Path('./logs')
reader = LogReader(log_dir)
entries = reader.read_all_logs()

# Filter entries
filtered = LogQuery.filter_by_level(entries, ['ERROR', 'CRITICAL'])
filtered = LogQuery.filter_by_time_range(filtered, last_hours=24)

# Analyze
analyzer = LogAnalyzer()
summary = analyzer.generate_summary(filtered)
errors = analyzer.analyze_errors(filtered)
anomalies = analyzer.detect_anomalies(filtered)

# Process results
print(f"Found {len(filtered)} errors")
print(f"Detected {len(anomalies)} anomalies")
```

### Custom Alerting

Integrate with alerting systems:

```python
#!/usr/bin/env python3
"""Custom alerting script."""

import sys
from pathlib import Path
from log_analyzer import LogReader, LogQuery
from datetime import datetime, timedelta

def check_errors():
    """Check for recent errors and alert if threshold exceeded."""
    reader = LogReader(Path('./logs'))
    entries = reader.read_all_logs()

    # Get errors from last 5 minutes
    start_time = datetime.now() - timedelta(minutes=5)
    recent = LogQuery.filter_by_time_range(entries, start=start_time)
    errors = LogQuery.filter_by_level(recent, ['ERROR', 'CRITICAL'])

    # Alert if more than 10 errors
    if len(errors) > 10:
        send_alert(f"High error rate: {len(errors)} errors in 5 minutes")
        return 1

    return 0

def send_alert(message):
    """Send alert via your preferred method."""
    # Email, Slack, PagerDuty, etc.
    print(f"ALERT: {message}")

if __name__ == '__main__':
    sys.exit(check_errors())
```

Run via cron every 5 minutes:

```bash
*/5 * * * * /path/to/custom_alert.py
```

---

## Best Practices

### 1. Regular Log Analysis

- Run anomaly detection at least daily
- Generate weekly summary reports
- Review error trends regularly
- Monitor performance metrics

### 2. Efficient Querying

- Use specific log file patterns when possible:
  ```bash
  python server/log_analyzer.py query --file-pattern "equipment*.log"
  ```
- Limit time ranges to reduce processing:
  ```bash
  python server/log_analyzer.py query --last 1h  # Faster than querying all logs
  ```
- Use appropriate output formats:
  - Text for human review
  - JSON for processing
  - CSV for spreadsheets

### 3. Log Retention

- Archive old log files to separate storage
- Compress archived logs (already done automatically via `.gz`)
- Keep at least 30 days of logs for audit purposes
- Longer retention for audit logs (90+ days)

### 4. Monitoring Strategy

**Development**:
```bash
# Monitor everything with details
python server/log_monitor.py --follow --show-extra
```

**Production**:
```bash
# Focus on errors and warnings
python server/log_monitor.py --follow \
    --level WARNING ERROR CRITICAL \
    --alert-on "failed" "timeout" "error"
```

**Debugging**:
```bash
# Monitor specific component
python server/log_monitor.py --follow \
    --logger equipment \
    --keyword "PSU_001"
```

### 5. Performance Considerations

- Log files are compressed automatically to save space
- Querying compressed logs is slower but saves disk space
- For frequent analysis, keep recent logs uncompressed
- Use `--limit` to reduce memory usage for large result sets

### 6. Security and Privacy

- Audit logs contain sensitive information - restrict access
- Regularly review user actions in audit logs
- Export audit logs to secure, immutable storage
- Implement log retention policies compliant with regulations

### 7. Alerting Best Practices

- Use appropriate sensitivity levels:
  - **High** - Development/testing
  - **Medium** - Production
  - **Low** - Stable systems
- Don't over-alert (alert fatigue)
- Focus on actionable alerts
- Escalate CRITICAL level immediately

### 8. Documentation

- Document your log analysis procedures
- Keep runbooks for common issues found in logs
- Share findings with team regularly
- Update alert thresholds based on experience

---

## Quick Reference

### Log Analyzer Commands

```bash
# Query
log_analyzer.py query [--level LEVEL] [--logger LOGGER] [--keyword KW] [--last TIME] [--limit N] [-o FILE]

# Report
log_analyzer.py report [--type TYPE] [--format FORMAT] [-o FILE]

# Anomaly
log_analyzer.py anomaly [--sensitivity LEVEL]
```

### Log Monitor Commands

```bash
# Monitor
log_monitor.py --follow [--level LEVEL] [--logger LOGGER] [--keyword KW] [--alert-on PATTERN] [--stats-interval N]
```

### Time Expressions

- `30s` - 30 seconds
- `5m` - 5 minutes
- `2h` - 2 hours
- `7d` - 7 days

### Output Formats

- `text` - Human-readable
- `json` - Machine-readable
- `csv` - Spreadsheet-compatible

---

## Troubleshooting

### No logs found

**Problem**: Tool reports no log files found.

**Solution**:
```bash
# Check log directory
ls -la ./logs

# Verify log directory setting
python server/log_analyzer.py query --log-dir ./logs

# Check if logs are being generated
python server/main.py  # Start server to generate logs
```

### Out of memory

**Problem**: Tool crashes with memory error on large log files.

**Solution**:
```bash
# Use time filters to reduce dataset
python server/log_analyzer.py query --last 1d

# Use limit to reduce results
python server/log_analyzer.py query --limit 1000

# Query specific log files only
python server/log_analyzer.py query --file-pattern "access.log"
```

### Slow queries

**Problem**: Queries take too long to execute.

**Solution**:
- Reduce time range with `--last`
- Use specific file patterns
- Query uncompressed logs when possible
- Upgrade to SSD storage for log directory

### Invalid JSON errors

**Problem**: Tool reports JSON parsing errors.

**Solution**:
```bash
# Check log file format
head -n 1 logs/lablink.log

# Verify JSON structure
cat logs/lablink.log | head -n 1 | jq .

# Skip invalid lines (tool handles this automatically)
```

---

## Support

For issues or questions:

1. Check this guide and examples
2. Review log file permissions
3. Verify Python version (3.8+ required)
4. Check for disk space issues
5. Review application logs for errors

---

**Document Version**: 1.0
**Last Updated**: 2025-01-15
**LabLink Version**: 0.9.0+
