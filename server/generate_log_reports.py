#!/usr/bin/env python3
"""
LabLink Automated Log Report Generator
========================================

Generates comprehensive daily/weekly log analysis reports.

Features:
- Summary statistics
- Error analysis
- Performance metrics
- Anomaly detection
- User activity audit
- Customizable report periods
- Email/file output

Usage:
    python generate_log_reports.py --period daily
    python generate_log_reports.py --period weekly --email admin@example.com
    python generate_log_reports.py --custom --days 7 --output report.html
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

# Import our log analysis modules
try:
    from log_analyzer import (LogAnalyzer, LogEntry, LogFormatter, LogQuery,
                              LogReader)
except ImportError:
    print("Error: log_analyzer.py must be in the same directory", file=sys.stderr)
    sys.exit(1)


class ReportGenerator:
    """Generates comprehensive log reports."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.reader = LogReader(log_dir)
        self.analyzer = LogAnalyzer()

    def generate_daily_report(self) -> Dict[str, Any]:
        """Generate daily report."""
        # Get logs from last 24 hours
        entries = self.reader.read_all_logs()
        yesterday = datetime.now() - timedelta(days=1)
        entries = LogQuery.filter_by_time_range(entries, start=yesterday)

        return self._generate_report(entries, "Daily Report", "Last 24 hours")

    def generate_weekly_report(self) -> Dict[str, Any]:
        """Generate weekly report."""
        # Get logs from last 7 days
        entries = self.reader.read_all_logs()
        last_week = datetime.now() - timedelta(days=7)
        entries = LogQuery.filter_by_time_range(entries, start=last_week)

        return self._generate_report(entries, "Weekly Report", "Last 7 days")

    def generate_custom_report(self, days: int) -> Dict[str, Any]:
        """Generate custom period report."""
        entries = self.reader.read_all_logs()
        start_date = datetime.now() - timedelta(days=days)
        entries = LogQuery.filter_by_time_range(entries, start=start_date)

        return self._generate_report(entries, f"{days}-Day Report", f"Last {days} days")

    def _generate_report(
        self, entries: List[LogEntry], title: str, period: str
    ) -> Dict[str, Any]:
        """Generate comprehensive report from entries."""
        report = {
            "metadata": {
                "title": title,
                "period": period,
                "generated_at": datetime.now().isoformat(),
                "entry_count": len(entries),
            },
            "summary": self.analyzer.generate_summary(entries),
            "errors": self.analyzer.analyze_errors(entries),
            "performance": self.analyzer.analyze_performance(entries),
            "anomalies": self.analyzer.detect_anomalies(entries, sensitivity=2.0),
            "user_activity": self._analyze_user_activity(entries),
            "equipment_activity": self._analyze_equipment_activity(entries),
            "api_activity": self._analyze_api_activity(entries),
        }

        return report

    def _analyze_user_activity(self, entries: List[LogEntry]) -> Dict[str, Any]:
        """Analyze user activity."""
        # Filter audit logs
        audit_entries = [e for e in entries if "audit" in e.logger]

        if not audit_entries:
            return {"total_actions": 0, "by_user": {}, "by_action": {}}

        # Count by user
        user_actions = defaultdict(int)
        action_counts = defaultdict(int)
        user_action_details = defaultdict(lambda: defaultdict(int))

        for entry in audit_entries:
            user_id = entry.extra.get("user_id", "unknown")
            action = entry.extra.get("action", "unknown")

            user_actions[user_id] += 1
            action_counts[action] += 1
            user_action_details[user_id][action] += 1

        return {
            "total_actions": len(audit_entries),
            "unique_users": len(user_actions),
            "by_user": dict(
                sorted(user_actions.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            "by_action": dict(
                sorted(action_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "top_user_details": {
                user: dict(actions)
                for user, actions in list(user_action_details.items())[:5]
            },
        }

    def _analyze_equipment_activity(self, entries: List[LogEntry]) -> Dict[str, Any]:
        """Analyze equipment activity."""
        # Filter equipment logs
        equipment_entries = [e for e in entries if "equipment" in e.logger]

        if not equipment_entries:
            return {"total_events": 0, "by_equipment": {}, "by_event_type": {}}

        # Count by equipment and event type
        equipment_events = defaultdict(int)
        event_types = defaultdict(int)
        equipment_errors = defaultdict(int)

        for entry in equipment_entries:
            equipment_id = entry.extra.get("equipment_id", "unknown")
            event_type = entry.extra.get("event", "unknown")

            equipment_events[equipment_id] += 1
            event_types[event_type] += 1

            if entry.level in ["ERROR", "CRITICAL"]:
                equipment_errors[equipment_id] += 1

        return {
            "total_events": len(equipment_entries),
            "unique_equipment": len(equipment_events),
            "by_equipment": dict(
                sorted(equipment_events.items(), key=lambda x: x[1], reverse=True)
            ),
            "by_event_type": dict(event_types),
            "equipment_with_errors": dict(
                sorted(equipment_errors.items(), key=lambda x: x[1], reverse=True)
            ),
        }

    def _analyze_api_activity(self, entries: List[LogEntry]) -> Dict[str, Any]:
        """Analyze API activity."""
        # Filter access logs
        access_entries = [e for e in entries if "access" in e.logger]

        if not access_entries:
            return {"total_requests": 0, "by_endpoint": {}, "by_status": {}}

        # Count by endpoint and status
        endpoint_counts = defaultdict(int)
        status_counts = defaultdict(int)
        method_counts = defaultdict(int)
        slow_requests = []

        for entry in access_entries:
            path = entry.extra.get("path", "unknown")
            status = entry.extra.get("status_code", 0)
            method = entry.extra.get("method", "unknown")
            duration = entry.extra.get("duration_ms", 0)

            endpoint_counts[f"{method} {path}"] += 1
            status_counts[str(status)] += 1
            method_counts[method] += 1

            # Track slow requests (>1s)
            if duration > 1000:
                slow_requests.append(
                    {
                        "endpoint": f"{method} {path}",
                        "duration_ms": duration,
                        "timestamp": entry.timestamp.isoformat(),
                    }
                )

        return {
            "total_requests": len(access_entries),
            "by_endpoint": dict(
                sorted(endpoint_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            "by_status": dict(sorted(status_counts.items())),
            "by_method": dict(method_counts),
            "slow_requests": sorted(
                slow_requests, key=lambda x: x["duration_ms"], reverse=True
            )[:10],
        }


class ReportFormatter:
    """Format reports in various output formats."""

    @staticmethod
    def format_text(report: Dict[str, Any]) -> str:
        """Format report as text."""
        lines = []

        # Header
        metadata = report["metadata"]
        lines.append("=" * 80)
        lines.append(f"  {metadata['title']}")
        lines.append(f"  Period: {metadata['period']}")
        lines.append(f"  Generated: {metadata['generated_at']}")
        lines.append(f"  Total Entries: {metadata['entry_count']:,}")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        lines.append("📊 SUMMARY")
        lines.append("-" * 80)
        summary = report["summary"]
        if summary["total_entries"] > 0:
            lines.append(
                f"Time Range: {summary['time_range']['start']} to {summary['time_range']['end']}"
            )
            lines.append(f"Duration: {summary['time_range']['duration']}")
            lines.append("")
            lines.append("Log Levels:")
            for level, count in summary["level_distribution"].items():
                pct = (count / summary["total_entries"]) * 100
                lines.append(f"  {level:10s}: {count:6,d} ({pct:5.1f}%)")
        else:
            lines.append("No entries in this period")
        lines.append("")

        # Errors
        lines.append("❌ ERROR ANALYSIS")
        lines.append("-" * 80)
        errors = report["errors"]
        if errors["total_errors"] > 0:
            lines.append(f"Total Errors: {errors['total_errors']:,}")
            lines.append("")
            lines.append("Top Error Types:")
            for error_msg, count in list(errors["error_types"].items())[:5]:
                lines.append(f"  [{count:3d}] {error_msg[:70]}")
            lines.append("")
            if errors["affected_modules"]:
                lines.append("Affected Modules:")
                for module, count in list(errors["affected_modules"].items())[:5]:
                    lines.append(f"  {module:30s}: {count:3d}")
        else:
            lines.append("No errors in this period ✓")
        lines.append("")

        # Performance
        lines.append("⚡ PERFORMANCE")
        lines.append("-" * 80)
        perf = report["performance"]
        if perf["total_measurements"] > 0:
            lines.append(f"Total Measurements: {perf['total_measurements']:,}")
            if perf["duration_stats"]:
                stats = perf["duration_stats"]
                lines.append("")
                lines.append("Duration Statistics (ms):")
                lines.append(f"  Mean:   {stats['mean']:8.2f}")
                lines.append(f"  Median: {stats['median']:8.2f}")
                lines.append(f"  Min:    {stats['min']:8.2f}")
                lines.append(f"  Max:    {stats['max']:8.2f}")
                lines.append(f"  StdDev: {stats['stdev']:8.2f}")
            if perf["slow_operations"]:
                lines.append("")
                lines.append("Slowest Operations:")
                for op in perf["slow_operations"][:5]:
                    lines.append(
                        f"  [{op['duration_ms']:7.1f}ms] {op['operation'][:60]}"
                    )
        else:
            lines.append("No performance measurements in this period")
        lines.append("")

        # Anomalies
        lines.append("🚨 ANOMALIES")
        lines.append("-" * 80)
        anomalies = report["anomalies"]
        if anomalies:
            lines.append(f"Detected {len(anomalies)} anomalies:")
            lines.append("")
            for i, anomaly in enumerate(anomalies[:10], 1):
                lines.append(
                    f"{i}. {anomaly['type'].upper()} - Severity: {anomaly['severity']}"
                )
                for key, value in anomaly.items():
                    if key not in ["type", "severity"]:
                        lines.append(f"   {key}: {value}")
                lines.append("")
        else:
            lines.append("No anomalies detected ✓")
        lines.append("")

        # User Activity
        lines.append("👥 USER ACTIVITY")
        lines.append("-" * 80)
        user_activity = report["user_activity"]
        if user_activity["total_actions"] > 0:
            lines.append(f"Total Actions: {user_activity['total_actions']:,}")
            lines.append(f"Unique Users: {user_activity['unique_users']}")
            lines.append("")
            lines.append("Top Users:")
            for user, count in list(user_activity["by_user"].items())[:10]:
                lines.append(f"  {user:30s}: {count:4d} actions")
            lines.append("")
            lines.append("Actions by Type:")
            for action, count in user_activity["by_action"].items():
                lines.append(f"  {action:30s}: {count:4d}")
        else:
            lines.append("No user activity logged")
        lines.append("")

        # Equipment Activity
        lines.append("🔧 EQUIPMENT ACTIVITY")
        lines.append("-" * 80)
        equipment = report["equipment_activity"]
        if equipment["total_events"] > 0:
            lines.append(f"Total Events: {equipment['total_events']:,}")
            lines.append(f"Unique Equipment: {equipment['unique_equipment']}")
            lines.append("")
            lines.append("By Equipment:")
            for equip_id, count in list(equipment["by_equipment"].items())[:10]:
                lines.append(f"  {equip_id:30s}: {count:4d} events")
            lines.append("")
            lines.append("By Event Type:")
            for event_type, count in equipment["by_event_type"].items():
                lines.append(f"  {event_type:30s}: {count:4d}")
            if equipment["equipment_with_errors"]:
                lines.append("")
                lines.append("Equipment with Errors:")
                for equip_id, count in equipment["equipment_with_errors"].items():
                    lines.append(f"  {equip_id:30s}: {count:4d} errors")
        else:
            lines.append("No equipment activity logged")
        lines.append("")

        # API Activity
        lines.append("🌐 API ACTIVITY")
        lines.append("-" * 80)
        api = report["api_activity"]
        if api["total_requests"] > 0:
            lines.append(f"Total Requests: {api['total_requests']:,}")
            lines.append("")
            lines.append("Top Endpoints:")
            for endpoint, count in api["by_endpoint"].items():
                lines.append(f"  [{count:5d}] {endpoint}")
            lines.append("")
            lines.append("By HTTP Method:")
            for method, count in api["by_method"].items():
                lines.append(f"  {method:10s}: {count:6,d}")
            lines.append("")
            lines.append("By Status Code:")
            for status, count in api["by_status"].items():
                lines.append(f"  {status:10s}: {count:6,d}")
            if api["slow_requests"]:
                lines.append("")
                lines.append("Slow Requests (>1s):")
                for req in api["slow_requests"][:5]:
                    lines.append(f"  [{req['duration_ms']:7.1f}ms] {req['endpoint']}")
        else:
            lines.append("No API activity logged")
        lines.append("")

        # Footer
        lines.append("=" * 80)
        lines.append(f"End of Report - Generated by LabLink Log Report Generator")
        lines.append("=" * 80)

        return "\n".join(lines)

    @staticmethod
    def format_json(report: Dict[str, Any]) -> str:
        """Format report as JSON."""
        return json.dumps(report, indent=2, default=str)

    @staticmethod
    def format_html(report: Dict[str, Any]) -> str:
        """Format report as HTML."""
        metadata = report["metadata"]
        summary = report["summary"]
        errors = report["errors"]

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{metadata['title']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px; }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .metric-label {{ font-weight: bold; color: #666; }}
        .metric-value {{ font-size: 1.5em; color: #007bff; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #007bff; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background: #f9f9f9; }}
        .error {{ color: #d32f2f; }}
        .warning {{ color: #f57c00; }}
        .success {{ color: #388e3c; }}
        .anomaly {{ background: #fff3cd; padding: 10px; margin: 10px 0; border-left: 4px solid #ffc107; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{metadata['title']}</h1>
        <p><strong>Period:</strong> {metadata['period']}<br>
        <strong>Generated:</strong> {metadata['generated_at']}<br>
        <strong>Total Entries:</strong> {metadata['entry_count']:,}</p>

        <h2>📊 Summary</h2>
        <div class="metric">
            <div class="metric-label">Total Entries</div>
            <div class="metric-value">{summary['total_entries']:,}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Errors</div>
            <div class="metric-value error">{errors['total_errors']:,}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Anomalies</div>
            <div class="metric-value warning">{len(report['anomalies'])}</div>
        </div>

        <h2>❌ Top Errors</h2>
        <table>
            <tr><th>Count</th><th>Error Message</th></tr>
"""

        for error_msg, count in list(errors["error_types"].items())[:10]:
            html += f"            <tr><td>{count}</td><td>{error_msg[:100]}</td></tr>\n"

        html += """        </table>

        <h2>🚨 Anomalies</h2>
"""

        if report["anomalies"]:
            for anomaly in report["anomalies"][:10]:
                html += f"""        <div class="anomaly">
            <strong>{anomaly['type'].upper()}</strong> - Severity: {anomaly['severity']}<br>
"""
                for key, value in anomaly.items():
                    if key not in ["type", "severity"]:
                        html += f"            {key}: {value}<br>\n"
                html += "        </div>\n"
        else:
            html += "        <p class='success'>No anomalies detected ✓</p>\n"

        html += """    </div>
</body>
</html>"""

        return html


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LabLink Automated Log Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--log-dir", default="./logs", help="Log directory path")
    parser.add_argument("--period", choices=["daily", "weekly"], help="Report period")
    parser.add_argument("--custom", action="store_true", help="Custom period")
    parser.add_argument("--days", type=int, default=7, help="Days for custom period")
    parser.add_argument(
        "--format",
        choices=["text", "json", "html"],
        default="text",
        help="Output format",
    )
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    args = parser.parse_args()

    # Generate report
    log_dir = Path(args.log_dir)
    generator = ReportGenerator(log_dir)

    print(f"Generating report from {log_dir}...", file=sys.stderr)

    try:
        if args.period == "daily":
            report = generator.generate_daily_report()
        elif args.period == "weekly":
            report = generator.generate_weekly_report()
        elif args.custom:
            report = generator.generate_custom_report(args.days)
        else:
            print("Error: Must specify --period or --custom", file=sys.stderr)
            return 1

        # Format report
        formatter = ReportFormatter()
        if args.format == "json":
            output = formatter.format_json(report)
        elif args.format == "html":
            output = formatter.format_html(report)
        else:  # text
            output = formatter.format_text(report)

        # Write output
        if args.output:
            Path(args.output).write_text(output)
            print(f"Report saved to {args.output}", file=sys.stderr)
        else:
            print(output)

        return 0

    except Exception as e:
        print(f"Error generating report: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
