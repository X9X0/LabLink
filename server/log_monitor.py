#!/usr/bin/env python3
"""
LabLink Log Monitor
===================

Real-time log monitoring tool with filtering and alerting capabilities.

Features:
- Watch multiple log files simultaneously
- Color-coded output by log level
- Filter by level, logger, keywords
- Alert on error patterns
- Display statistics
- Export monitoring sessions

Usage:
    python log_monitor.py --follow
    python log_monitor.py --follow --level ERROR WARNING
    python log_monitor.py --alert-on "connection failed" --notify
"""

import argparse
import json
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"


@dataclass
class MonitorStats:
    """Statistics for monitoring session."""

    start_time: datetime
    total_entries: int = 0
    by_level: dict = None
    by_logger: dict = None
    alerts_triggered: int = 0

    def __post_init__(self):
        if self.by_level is None:
            self.by_level = defaultdict(int)
        if self.by_logger is None:
            self.by_logger = defaultdict(int)


class LogMonitor:
    """Real-time log file monitor."""

    def __init__(self, log_dir: Path, file_pattern: str = "*.log"):
        self.log_dir = log_dir
        self.file_pattern = file_pattern
        self.file_positions = {}  # Track read positions
        self.stats = MonitorStats(start_time=datetime.now())
        self.recent_entries = deque(maxlen=100)  # Keep last 100 entries

    def get_log_files(self) -> List[Path]:
        """Get all log files to monitor."""
        if not self.log_dir.exists():
            return []

        files = []
        for filepath in self.log_dir.glob(self.file_pattern):
            if filepath.is_file() and filepath.suffix == ".log":
                files.append(filepath)

        return sorted(files)

    def read_new_lines(self, filepath: Path) -> List[str]:
        """Read new lines from a log file since last read."""
        lines = []

        try:
            # Get current file size
            current_size = filepath.stat().st_size

            # Get last read position
            last_position = self.file_positions.get(filepath, 0)

            # If file was truncated, reset position
            if current_size < last_position:
                last_position = 0

            # Read new content
            if current_size > last_position:
                with open(filepath, "r", encoding="utf-8") as f:
                    f.seek(last_position)
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                    self.file_positions[filepath] = f.tell()

        except Exception as e:
            print(
                f"{Colors.RED}Error reading {filepath}: {e}{Colors.RESET}",
                file=sys.stderr,
            )

        return lines

    def parse_log_line(self, line: str) -> Optional[dict]:
        """Parse a JSON log line."""
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def format_log_entry(self, entry: dict, colorize: bool = True) -> str:
        """Format a log entry for display."""
        timestamp = entry.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp = dt.strftime("%H:%M:%S.%f")[:-3]
            except:
                pass

        level = entry.get("level", "UNKNOWN")
        logger = entry.get("logger", "")
        message = entry.get("message", "")

        # Color by level
        if colorize:
            level_colors = {
                "DEBUG": Colors.CYAN,
                "INFO": Colors.GREEN,
                "WARNING": Colors.YELLOW,
                "ERROR": Colors.RED,
                "CRITICAL": Colors.MAGENTA + Colors.BOLD,
            }
            color = level_colors.get(level, Colors.WHITE)
            level_str = f"{color}{level:8s}{Colors.RESET}"
        else:
            level_str = f"{level:8s}"

        # Format main line
        output = f"{Colors.GRAY}{timestamp}{Colors.RESET} {level_str} {Colors.BLUE}{logger:30s}{Colors.RESET} {message}"

        # Add extra fields if present
        extra_fields = {
            k: v
            for k, v in entry.items()
            if k
            not in [
                "timestamp",
                "level",
                "logger",
                "message",
                "module",
                "function",
                "line",
            ]
        }

        if extra_fields:
            extra_str = " ".join(f"{k}={v}" for k, v in extra_fields.items())
            output += f"\n  {Colors.GRAY}└─ {extra_str}{Colors.RESET}"

        return output

    def check_filters(self, entry: dict, filters: dict) -> bool:
        """Check if entry passes all filters."""
        # Level filter
        if filters.get("levels"):
            if entry.get("level") not in filters["levels"]:
                return False

        # Logger filter
        if filters.get("loggers"):
            logger = entry.get("logger", "")
            if not any(log in logger for log in filters["loggers"]):
                return False

        # Keyword filter
        if filters.get("keywords"):
            message = entry.get("message", "").lower()
            if not any(kw.lower() in message for kw in filters["keywords"]):
                return False

        return True

    def check_alerts(self, entry: dict, alert_patterns: List[str]) -> bool:
        """Check if entry matches any alert patterns."""
        if not alert_patterns:
            return False

        message = entry.get("message", "").lower()
        level = entry.get("level", "")

        # Always alert on CRITICAL
        if level == "CRITICAL":
            return True

        # Check patterns
        for pattern in alert_patterns:
            if pattern.lower() in message:
                return True

        return False

    def display_alert(self, entry: dict, reason: str = ""):
        """Display an alert."""
        print(f"\n{Colors.RED}{Colors.BOLD}{'=' * 80}")
        print(f"🚨 ALERT{' - ' + reason if reason else ''}")
        print(f"{'=' * 80}{Colors.RESET}")
        print(self.format_log_entry(entry, colorize=True))
        print(f"{Colors.RED}{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")
        self.stats.alerts_triggered += 1

    def display_stats(self):
        """Display monitoring statistics."""
        elapsed = datetime.now() - self.stats.start_time
        elapsed_str = str(elapsed).split(".")[0]  # Remove microseconds

        print(f"\n{Colors.BOLD}{'=' * 80}")
        print(f"📊 Monitoring Statistics")
        print(f"{'=' * 80}{Colors.RESET}")
        print(f"Duration:        {elapsed_str}")
        print(f"Total Entries:   {self.stats.total_entries}")
        print(f"Alerts:          {self.stats.alerts_triggered}")

        if self.stats.by_level:
            print(f"\n{Colors.BOLD}By Level:{Colors.RESET}")
            for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                if level in self.stats.by_level:
                    count = self.stats.by_level[level]
                    print(f"  {level:10s}: {count:6d}")

        if self.stats.by_logger:
            print(f"\n{Colors.BOLD}Top Loggers:{Colors.RESET}")
            sorted_loggers = sorted(
                self.stats.by_logger.items(), key=lambda x: x[1], reverse=True
            )[:10]
            for logger, count in sorted_loggers:
                print(f"  {logger:40s}: {count:6d}")

        print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")

    def monitor(
        self, filters: dict, alert_patterns: List[str], show_stats_interval: int = 0
    ):
        """Main monitoring loop."""
        print(f"{Colors.BOLD}🔍 LabLink Log Monitor{Colors.RESET}")
        print(f"Monitoring: {self.log_dir}/{self.file_pattern}")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if filters.get("levels"):
            print(f"Levels: {', '.join(filters['levels'])}")
        if filters.get("loggers"):
            print(f"Loggers: {', '.join(filters['loggers'])}")
        if filters.get("keywords"):
            print(f"Keywords: {', '.join(filters['keywords'])}")
        if alert_patterns:
            print(f"Alerts: {', '.join(alert_patterns)}")

        print(f"\nPress Ctrl+C to stop\n{Colors.GRAY}{'─' * 80}{Colors.RESET}\n")

        last_stats_time = time.time()

        try:
            while True:
                files = self.get_log_files()
                entries_processed = 0

                for filepath in files:
                    lines = self.read_new_lines(filepath)

                    for line in lines:
                        entry = self.parse_log_line(line)
                        if not entry:
                            continue

                        # Update stats
                        self.stats.total_entries += 1
                        self.stats.by_level[entry.get("level", "UNKNOWN")] += 1
                        self.stats.by_logger[entry.get("logger", "")] += 1
                        self.recent_entries.append(entry)

                        # Check filters
                        if not self.check_filters(entry, filters):
                            continue

                        entries_processed += 1

                        # Check alerts
                        if self.check_alerts(entry, alert_patterns):
                            self.display_alert(entry, "Pattern matched")
                        else:
                            # Display entry
                            print(self.format_log_entry(entry, colorize=True))

                # Show periodic stats
                if show_stats_interval > 0:
                    current_time = time.time()
                    if current_time - last_stats_time >= show_stats_interval:
                        self.display_stats()
                        last_stats_time = current_time

                # Sleep briefly
                time.sleep(0.1)

        except KeyboardInterrupt:
            print(f"\n\n{Colors.YELLOW}Monitoring stopped by user{Colors.RESET}")
            self.display_stats()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="LabLink Log Monitor - Real-time log monitoring with filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor all logs
  python log_monitor.py --follow

  # Monitor only errors
  python log_monitor.py --follow --level ERROR CRITICAL

  # Monitor with keyword filter
  python log_monitor.py --follow --keyword "equipment" "connection"

  # Monitor with alerts
  python log_monitor.py --follow --alert-on "failed" "error" "timeout"

  # Show stats every 60 seconds
  python log_monitor.py --follow --stats-interval 60
        """,
    )

    parser.add_argument(
        "--log-dir", default="./logs", help="Log directory path (default: ./logs)"
    )
    parser.add_argument(
        "--file-pattern", default="*.log", help="Log file pattern (default: *.log)"
    )
    parser.add_argument(
        "--follow", "-f", action="store_true", help="Follow log files in real-time"
    )
    parser.add_argument(
        "--level",
        nargs="+",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Filter by log level",
    )
    parser.add_argument("--logger", nargs="+", help="Filter by logger name")
    parser.add_argument("--keyword", nargs="+", help="Filter by keywords in message")
    parser.add_argument("--alert-on", nargs="+", help="Alert on these patterns")
    parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    parser.add_argument(
        "--stats-interval",
        type=int,
        default=0,
        help="Show stats every N seconds (0 = disabled)",
    )

    args = parser.parse_args()

    if not args.follow:
        print("Error: --follow flag is required for monitoring", file=sys.stderr)
        print("Use --help for usage information", file=sys.stderr)
        return 1

    # Disable colors if requested or not a TTY
    if args.no_color or not sys.stdout.isatty():
        for attr in dir(Colors):
            if not attr.startswith("_"):
                setattr(Colors, attr, "")

    # Build filters
    filters = {"levels": args.level, "loggers": args.logger, "keywords": args.keyword}

    # Start monitoring
    log_dir = Path(args.log_dir)
    monitor = LogMonitor(log_dir, args.file_pattern)

    try:
        monitor.monitor(filters, args.alert_on or [], args.stats_interval)
        return 0
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
