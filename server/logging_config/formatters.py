"""Custom log formatters for structured and colored logging."""

import json
import logging
from datetime import datetime
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "equipment_id"):
            log_data["equipment_id"] = record.equipment_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code
        if hasattr(record, "endpoint"):
            log_data["endpoint"] = record.endpoint
        if hasattr(record, "method"):
            log_data["method"] = record.method

        # Add any custom fields from extra dict
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "user_id",
                "equipment_id",
                "request_id",
                "duration_ms",
                "status_code",
                "endpoint",
                "method",
            ]:
                if not key.startswith("_"):
                    log_data[key] = value

        return json.dumps(log_data)


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        # Color the level name
        levelname = record.levelname
        if levelname in self.COLORS:
            colored_levelname = (
                f"{self.COLORS[levelname]}{self.BOLD}{levelname:8s}{self.RESET}"
            )
            record.levelname = colored_levelname

        # Format the message
        formatted = super().format(record)

        return formatted


class CompactFormatter(logging.Formatter):
    """Compact formatter for production logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record compactly."""
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]

        # Build compact message
        parts = [
            timestamp,
            record.levelname[0],  # First letter only (D/I/W/E/C)
            record.name.split(".")[-1],  # Just module name
            record.getMessage(),
        ]

        # Add performance info if present
        if hasattr(record, "duration_ms"):
            parts.append(f"({record.duration_ms:.1f}ms)")

        return " | ".join(parts)
