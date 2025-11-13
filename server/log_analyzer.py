#!/usr/bin/env python3
"""
LabLink Log Analyzer
====================

A comprehensive CLI tool for analyzing, querying, and generating reports from LabLink logs.

Features:
- Query logs by time range, level, logger, keywords
- Generate summary reports
- Analyze performance metrics
- Detect anomalies
- Export to various formats (JSON, CSV, text)
- Real-time log monitoring

Usage:
    python log_analyzer.py query --level ERROR --last 1h
    python log_analyzer.py report --type summary --output report.txt
    python log_analyzer.py performance --metric response_time --threshold 1000
    python log_analyzer.py anomaly --sensitivity medium
    python log_analyzer.py watch --follow
"""

import json
import gzip
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass
import argparse
import statistics


@dataclass
class LogEntry:
    """Represents a parsed log entry."""
    timestamp: datetime
    level: str
    logger: str
    message: str
    module: Optional[str] = None
    function: Optional[str] = None
    line: Optional[int] = None
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'LogEntry':
        """Create LogEntry from JSON log line."""
        timestamp_str = data.get('timestamp', '')
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            timestamp = datetime.now()

        # Extract known fields
        known_fields = {'timestamp', 'level', 'logger', 'message', 'module', 'function', 'line'}
        extra = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            timestamp=timestamp,
            level=data.get('level', 'UNKNOWN'),
            logger=data.get('logger', ''),
            message=data.get('message', ''),
            module=data.get('module'),
            function=data.get('function'),
            line=data.get('line'),
            extra=extra
        )


class LogReader:
    """Reads and parses log files (including compressed files)."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir

    def read_log_file(self, filepath: Path) -> List[LogEntry]:
        """Read a single log file and return parsed entries."""
        entries = []

        try:
            if filepath.suffix == '.gz':
                with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                    entries = self._parse_lines(f)
            else:
                with open(filepath, 'r', encoding='utf-8') as f:
                    entries = self._parse_lines(f)
        except Exception as e:
            print(f"Warning: Failed to read {filepath}: {e}", file=sys.stderr)

        return entries

    def _parse_lines(self, file_obj) -> List[LogEntry]:
        """Parse lines from a file object."""
        entries = []
        for line in file_obj:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                entry = LogEntry.from_json(data)
                entries.append(entry)
            except json.JSONDecodeError:
                # Skip non-JSON lines
                continue

        return entries

    def get_log_files(self, pattern: str = "*") -> List[Path]:
        """Get all log files matching pattern."""
        if not self.log_dir.exists():
            return []

        files = []
        for filepath in self.log_dir.glob(pattern):
            if filepath.is_file() and (filepath.suffix in ['.log', '.gz']):
                files.append(filepath)

        return sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)

    def read_all_logs(self, pattern: str = "*.log") -> List[LogEntry]:
        """Read all log files matching pattern."""
        all_entries = []
        files = self.get_log_files(pattern)

        for filepath in files:
            entries = self.read_log_file(filepath)
            all_entries.extend(entries)

        # Sort by timestamp
        all_entries.sort(key=lambda x: x.timestamp)
        return all_entries


class LogQuery:
    """Query and filter log entries."""

    @staticmethod
    def filter_by_time_range(entries: List[LogEntry],
                            start: Optional[datetime] = None,
                            end: Optional[datetime] = None) -> List[LogEntry]:
        """Filter entries by time range."""
        if start is None and end is None:
            return entries

        filtered = []
        for entry in entries:
            if start and entry.timestamp < start:
                continue
            if end and entry.timestamp > end:
                continue
            filtered.append(entry)

        return filtered

    @staticmethod
    def filter_by_level(entries: List[LogEntry], levels: List[str]) -> List[LogEntry]:
        """Filter entries by log level."""
        if not levels:
            return entries

        levels_upper = [level.upper() for level in levels]
        return [e for e in entries if e.level.upper() in levels_upper]

    @staticmethod
    def filter_by_logger(entries: List[LogEntry], loggers: List[str]) -> List[LogEntry]:
        """Filter entries by logger name."""
        if not loggers:
            return entries

        return [e for e in entries if any(logger in e.logger for logger in loggers)]

    @staticmethod
    def filter_by_keyword(entries: List[LogEntry], keywords: List[str],
                         case_sensitive: bool = False) -> List[LogEntry]:
        """Filter entries by keywords in message."""
        if not keywords:
            return entries

        filtered = []
        for entry in entries:
            message = entry.message if case_sensitive else entry.message.lower()
            keywords_to_check = keywords if case_sensitive else [k.lower() for k in keywords]

            if any(keyword in message for keyword in keywords_to_check):
                filtered.append(entry)

        return filtered

    @staticmethod
    def filter_by_regex(entries: List[LogEntry], pattern: str) -> List[LogEntry]:
        """Filter entries by regex pattern in message."""
        if not pattern:
            return entries

        try:
            regex = re.compile(pattern)
            return [e for e in entries if regex.search(e.message)]
        except re.error as e:
            print(f"Invalid regex pattern: {e}", file=sys.stderr)
            return entries


class LogAnalyzer:
    """Analyze log entries and generate insights."""

    @staticmethod
    def generate_summary(entries: List[LogEntry]) -> Dict[str, Any]:
        """Generate summary statistics."""
        if not entries:
            return {
                'total_entries': 0,
                'time_range': None,
                'level_distribution': {},
                'logger_distribution': {},
                'top_messages': []
            }

        # Basic stats
        total = len(entries)
        time_range = (entries[0].timestamp, entries[-1].timestamp)

        # Level distribution
        level_counts = Counter(e.level for e in entries)

        # Logger distribution
        logger_counts = Counter(e.logger for e in entries)

        # Top messages
        message_counts = Counter(e.message for e in entries)
        top_messages = message_counts.most_common(10)

        return {
            'total_entries': total,
            'time_range': {
                'start': time_range[0].isoformat(),
                'end': time_range[1].isoformat(),
                'duration': str(time_range[1] - time_range[0])
            },
            'level_distribution': dict(level_counts),
            'logger_distribution': dict(logger_counts.most_common(10)),
            'top_messages': [{'message': msg, 'count': count} for msg, count in top_messages]
        }

    @staticmethod
    def analyze_errors(entries: List[LogEntry]) -> Dict[str, Any]:
        """Analyze error patterns."""
        error_entries = [e for e in entries if e.level in ['ERROR', 'CRITICAL']]

        if not error_entries:
            return {
                'total_errors': 0,
                'error_types': {},
                'error_timeline': [],
                'affected_modules': {}
            }

        # Error types (by message pattern)
        error_types = Counter(e.message for e in error_entries)

        # Timeline (errors per hour)
        timeline = defaultdict(int)
        for entry in error_entries:
            hour_key = entry.timestamp.strftime('%Y-%m-%d %H:00')
            timeline[hour_key] += 1

        # Affected modules
        module_errors = Counter(e.module for e in error_entries if e.module)

        return {
            'total_errors': len(error_entries),
            'error_types': dict(error_types.most_common(10)),
            'error_timeline': dict(sorted(timeline.items())),
            'affected_modules': dict(module_errors)
        }

    @staticmethod
    def analyze_performance(entries: List[LogEntry]) -> Dict[str, Any]:
        """Analyze performance metrics from logs."""
        perf_entries = [e for e in entries if 'duration_ms' in e.extra or 'memory_mb' in e.extra]

        if not perf_entries:
            return {
                'total_measurements': 0,
                'duration_stats': None,
                'memory_stats': None,
                'slow_operations': []
            }

        # Duration statistics
        durations = [e.extra['duration_ms'] for e in perf_entries if 'duration_ms' in e.extra]
        duration_stats = None
        if durations:
            duration_stats = {
                'mean': statistics.mean(durations),
                'median': statistics.median(durations),
                'min': min(durations),
                'max': max(durations),
                'stdev': statistics.stdev(durations) if len(durations) > 1 else 0
            }

        # Memory statistics
        memory_values = [e.extra['memory_mb'] for e in perf_entries if 'memory_mb' in e.extra]
        memory_stats = None
        if memory_values:
            memory_stats = {
                'mean': statistics.mean(memory_values),
                'median': statistics.median(memory_values),
                'min': min(memory_values),
                'max': max(memory_values)
            }

        # Slow operations (top 10 by duration)
        slow_ops = sorted(
            [e for e in perf_entries if 'duration_ms' in e.extra],
            key=lambda x: x.extra['duration_ms'],
            reverse=True
        )[:10]

        slow_operations = [{
            'timestamp': op.timestamp.isoformat(),
            'operation': op.message,
            'duration_ms': op.extra['duration_ms'],
            'function': op.function
        } for op in slow_ops]

        return {
            'total_measurements': len(perf_entries),
            'duration_stats': duration_stats,
            'memory_stats': memory_stats,
            'slow_operations': slow_operations
        }

    @staticmethod
    def detect_anomalies(entries: List[LogEntry], sensitivity: float = 2.0) -> List[Dict[str, Any]]:
        """Detect anomalies in log patterns."""
        anomalies = []

        if len(entries) < 10:
            return anomalies

        # 1. Detect error spikes
        error_entries = [e for e in entries if e.level in ['ERROR', 'CRITICAL']]
        if error_entries:
            # Group by 5-minute intervals
            intervals = defaultdict(int)
            for entry in error_entries:
                interval_key = entry.timestamp.replace(minute=(entry.timestamp.minute // 5) * 5, second=0, microsecond=0)
                intervals[interval_key] += 1

            if len(intervals) > 1:
                counts = list(intervals.values())
                mean_errors = statistics.mean(counts)
                stdev_errors = statistics.stdev(counts) if len(counts) > 1 else 0

                for interval, count in intervals.items():
                    if stdev_errors > 0 and count > mean_errors + (sensitivity * stdev_errors):
                        anomalies.append({
                            'type': 'error_spike',
                            'timestamp': interval.isoformat(),
                            'count': count,
                            'expected': round(mean_errors, 2),
                            'severity': 'high' if count > mean_errors + (3 * stdev_errors) else 'medium'
                        })

        # 2. Detect repeated errors (same error within short time)
        error_sequences = defaultdict(list)
        for entry in error_entries:
            error_sequences[entry.message].append(entry.timestamp)

        for message, timestamps in error_sequences.items():
            if len(timestamps) >= 5:
                # Check if 5+ errors occurred within 1 minute
                for i in range(len(timestamps) - 4):
                    time_span = timestamps[i + 4] - timestamps[i]
                    if time_span <= timedelta(minutes=1):
                        anomalies.append({
                            'type': 'repeated_error',
                            'message': message[:100],
                            'count': len(timestamps),
                            'first_occurrence': timestamps[0].isoformat(),
                            'severity': 'high'
                        })
                        break

        # 3. Detect performance degradation
        perf_entries = [e for e in entries if 'duration_ms' in e.extra]
        if len(perf_entries) > 10:
            durations = [e.extra['duration_ms'] for e in perf_entries]
            mean_duration = statistics.mean(durations)
            stdev_duration = statistics.stdev(durations) if len(durations) > 1 else 0

            for entry in perf_entries:
                duration = entry.extra['duration_ms']
                if stdev_duration > 0 and duration > mean_duration + (sensitivity * stdev_duration):
                    anomalies.append({
                        'type': 'slow_operation',
                        'timestamp': entry.timestamp.isoformat(),
                        'operation': entry.message,
                        'duration_ms': duration,
                        'expected_ms': round(mean_duration, 2),
                        'severity': 'medium'
                    })

        return anomalies


class LogFormatter:
    """Format log entries for output."""

    @staticmethod
    def format_entry_text(entry: LogEntry, show_extra: bool = True) -> str:
        """Format entry as text."""
        timestamp = entry.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        location = f"{entry.module}:{entry.function}:{entry.line}" if entry.module else ""

        text = f"[{timestamp}] {entry.level:8s} {entry.logger:30s} {entry.message}"

        if location:
            text += f"\n  └─ {location}"

        if show_extra and entry.extra:
            for key, value in entry.extra.items():
                text += f"\n     {key}: {value}"

        return text

    @staticmethod
    def format_entries_json(entries: List[LogEntry]) -> str:
        """Format entries as JSON."""
        data = []
        for entry in entries:
            item = {
                'timestamp': entry.timestamp.isoformat(),
                'level': entry.level,
                'logger': entry.logger,
                'message': entry.message,
                **entry.extra
            }
            if entry.module:
                item['module'] = entry.module
            if entry.function:
                item['function'] = entry.function
            if entry.line:
                item['line'] = entry.line
            data.append(item)

        return json.dumps(data, indent=2)

    @staticmethod
    def format_entries_csv(entries: List[LogEntry]) -> str:
        """Format entries as CSV."""
        if not entries:
            return ""

        # Get all unique extra field names
        extra_fields = set()
        for entry in entries:
            extra_fields.update(entry.extra.keys())

        # Header
        headers = ['timestamp', 'level', 'logger', 'message', 'module', 'function', 'line']
        headers.extend(sorted(extra_fields))
        csv_lines = [','.join(headers)]

        # Data rows
        for entry in entries:
            row = [
                entry.timestamp.isoformat(),
                entry.level,
                entry.logger,
                f'"{entry.message}"',
                entry.module or '',
                entry.function or '',
                str(entry.line) if entry.line else ''
            ]
            for field in sorted(extra_fields):
                value = entry.extra.get(field, '')
                row.append(str(value))
            csv_lines.append(','.join(row))

        return '\n'.join(csv_lines)


def parse_time_expression(expr: str) -> datetime:
    """Parse time expressions like '1h', '30m', '2d' into datetime."""
    match = re.match(r'^(\d+)([smhd])$', expr)
    if not match:
        raise ValueError(f"Invalid time expression: {expr}")

    value, unit = match.groups()
    value = int(value)

    now = datetime.now()
    if unit == 's':
        return now - timedelta(seconds=value)
    elif unit == 'm':
        return now - timedelta(minutes=value)
    elif unit == 'h':
        return now - timedelta(hours=value)
    elif unit == 'd':
        return now - timedelta(days=value)

    raise ValueError(f"Invalid time unit: {unit}")


def cmd_query(args):
    """Query logs command."""
    log_dir = Path(args.log_dir)
    reader = LogReader(log_dir)

    # Read logs
    print(f"Reading logs from {log_dir}...", file=sys.stderr)
    entries = reader.read_all_logs(args.file_pattern)
    print(f"Found {len(entries)} log entries", file=sys.stderr)

    # Apply filters
    if args.last:
        start_time = parse_time_expression(args.last)
        entries = LogQuery.filter_by_time_range(entries, start=start_time)
        print(f"Filtered to last {args.last}: {len(entries)} entries", file=sys.stderr)

    if args.level:
        entries = LogQuery.filter_by_level(entries, args.level)
        print(f"Filtered by level {args.level}: {len(entries)} entries", file=sys.stderr)

    if args.logger:
        entries = LogQuery.filter_by_logger(entries, args.logger)
        print(f"Filtered by logger: {len(entries)} entries", file=sys.stderr)

    if args.keyword:
        entries = LogQuery.filter_by_keyword(entries, args.keyword, args.case_sensitive)
        print(f"Filtered by keywords: {len(entries)} entries", file=sys.stderr)

    if args.regex:
        entries = LogQuery.filter_by_regex(entries, args.regex)
        print(f"Filtered by regex: {len(entries)} entries", file=sys.stderr)

    # Limit results
    if args.limit:
        entries = entries[:args.limit]

    # Format output
    formatter = LogFormatter()
    if args.output_format == 'json':
        output = formatter.format_entries_json(entries)
    elif args.output_format == 'csv':
        output = formatter.format_entries_csv(entries)
    else:  # text
        output = '\n\n'.join(formatter.format_entry_text(e, show_extra=args.show_extra) for e in entries)

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Wrote {len(entries)} entries to {args.output}", file=sys.stderr)
    else:
        print(output)


def cmd_report(args):
    """Generate report command."""
    log_dir = Path(args.log_dir)
    reader = LogReader(log_dir)
    analyzer = LogAnalyzer()

    # Read logs
    print(f"Reading logs from {log_dir}...", file=sys.stderr)
    entries = reader.read_all_logs(args.file_pattern)
    print(f"Analyzing {len(entries)} log entries...", file=sys.stderr)

    # Generate report
    if args.type == 'summary':
        report_data = analyzer.generate_summary(entries)
        title = "Log Summary Report"
    elif args.type == 'errors':
        report_data = analyzer.analyze_errors(entries)
        title = "Error Analysis Report"
    elif args.type == 'performance':
        report_data = analyzer.analyze_performance(entries)
        title = "Performance Analysis Report"
    else:
        print(f"Unknown report type: {args.type}", file=sys.stderr)
        return

    # Format report
    if args.format == 'json':
        output = json.dumps(report_data, indent=2)
    else:  # text
        output = f"{title}\n{'=' * len(title)}\n\n"
        output += format_report_text(report_data)

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Report saved to {args.output}", file=sys.stderr)
    else:
        print(output)


def format_report_text(data: Dict[str, Any]) -> str:
    """Format report data as readable text."""
    lines = []

    for key, value in data.items():
        # Format key
        key_formatted = key.replace('_', ' ').title()
        lines.append(f"{key_formatted}:")

        # Format value
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                lines.append(f"  {sub_key}: {sub_value}")
        elif isinstance(value, list):
            for item in value[:10]:  # Limit to 10 items
                if isinstance(item, dict):
                    item_str = ', '.join(f"{k}={v}" for k, v in item.items())
                    lines.append(f"  - {item_str}")
                else:
                    lines.append(f"  - {item}")
        else:
            lines.append(f"  {value}")

        lines.append("")  # Blank line

    return '\n'.join(lines)


def cmd_anomaly(args):
    """Detect anomalies command."""
    log_dir = Path(args.log_dir)
    reader = LogReader(log_dir)
    analyzer = LogAnalyzer()

    # Parse sensitivity
    sensitivity_map = {'low': 3.0, 'medium': 2.0, 'high': 1.5}
    sensitivity = sensitivity_map.get(args.sensitivity, 2.0)

    # Read logs
    print(f"Reading logs from {log_dir}...", file=sys.stderr)
    entries = reader.read_all_logs(args.file_pattern)
    print(f"Analyzing {len(entries)} entries for anomalies...", file=sys.stderr)

    # Detect anomalies
    anomalies = analyzer.detect_anomalies(entries, sensitivity=sensitivity)

    # Output
    print(f"\nFound {len(anomalies)} anomalies:\n")

    for i, anomaly in enumerate(anomalies, 1):
        print(f"{i}. {anomaly['type'].upper()} - Severity: {anomaly['severity']}")
        for key, value in anomaly.items():
            if key not in ['type', 'severity']:
                print(f"   {key}: {value}")
        print()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='LabLink Log Analyzer - Query and analyze application logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Query error logs from last hour
  python log_analyzer.py query --level ERROR --last 1h

  # Search for specific keywords
  python log_analyzer.py query --keyword "equipment" "connection" --output results.json

  # Generate summary report
  python log_analyzer.py report --type summary

  # Analyze performance
  python log_analyzer.py report --type performance --output perf_report.txt

  # Detect anomalies
  python log_analyzer.py anomaly --sensitivity high
        """
    )

    parser.add_argument('--log-dir', default='./logs', help='Log directory path (default: ./logs)')

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Query command
    query_parser = subparsers.add_parser('query', help='Query and filter logs')
    query_parser.add_argument('--level', nargs='+', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                             help='Filter by log level')
    query_parser.add_argument('--logger', nargs='+', help='Filter by logger name')
    query_parser.add_argument('--keyword', nargs='+', help='Filter by keywords in message')
    query_parser.add_argument('--regex', help='Filter by regex pattern')
    query_parser.add_argument('--last', help='Time range (e.g., 1h, 30m, 2d)')
    query_parser.add_argument('--limit', type=int, help='Limit number of results')
    query_parser.add_argument('--case-sensitive', action='store_true', help='Case-sensitive keyword search')
    query_parser.add_argument('--show-extra', action='store_true', default=True, help='Show extra fields')
    query_parser.add_argument('--output-format', choices=['text', 'json', 'csv'], default='text',
                             help='Output format')
    query_parser.add_argument('--file-pattern', default='*.log', help='Log file pattern (default: *.log)')
    query_parser.add_argument('--output', '-o', help='Output file (default: stdout)')

    # Report command
    report_parser = subparsers.add_parser('report', help='Generate analysis reports')
    report_parser.add_argument('--type', choices=['summary', 'errors', 'performance'], default='summary',
                              help='Report type')
    report_parser.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    report_parser.add_argument('--file-pattern', default='*.log', help='Log file pattern')
    report_parser.add_argument('--output', '-o', help='Output file (default: stdout)')

    # Anomaly detection command
    anomaly_parser = subparsers.add_parser('anomaly', help='Detect anomalies in logs')
    anomaly_parser.add_argument('--sensitivity', choices=['low', 'medium', 'high'], default='medium',
                               help='Detection sensitivity')
    anomaly_parser.add_argument('--file-pattern', default='*.log', help='Log file pattern')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == 'query':
            cmd_query(args)
        elif args.command == 'report':
            cmd_report(args)
        elif args.command == 'anomaly':
            cmd_anomaly(args)
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
