"""Log handlers with rotation and archival."""

import logging
import gzip
import shutil
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
from typing import Optional

from .formatters import JsonFormatter, ColoredFormatter, CompactFormatter


class CompressingRotatingFileHandler(RotatingFileHandler):
    """Rotating file handler that compresses old log files."""

    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0, encoding=None, delay=False):
        """Initialize handler."""
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)

    def doRollover(self):
        """Do a rollover and compress the old file."""
        super().doRollover()

        # Compress the previous log file
        if self.backupCount > 0:
            log_file = f"{self.baseFilename}.1"
            if Path(log_file).exists():
                compressed_file = f"{log_file}.gz"
                with open(log_file, 'rb') as f_in:
                    with gzip.open(compressed_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                Path(log_file).unlink()


def get_rotating_file_handler(
    log_dir: str,
    filename: str,
    max_bytes: int,
    backup_count: int,
    formatter_type: str = "json",
    compress: bool = True
) -> logging.Handler:
    """
    Get a rotating file handler with specified configuration.

    Args:
        log_dir: Directory for log files
        filename: Log file name
        max_bytes: Maximum file size before rotation
        backup_count: Number of backup files to keep
        formatter_type: "json", "text", or "compact"
        compress: Whether to compress rotated files

    Returns:
        Configured file handler
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    filepath = log_path / filename

    if compress:
        handler = CompressingRotatingFileHandler(
            filename=str(filepath),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
    else:
        handler = RotatingFileHandler(
            filename=str(filepath),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )

    # Set formatter
    if formatter_type == "json":
        handler.setFormatter(JsonFormatter())
    elif formatter_type == "compact":
        handler.setFormatter(CompactFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))

    return handler


def get_timed_rotating_handler(
    log_dir: str,
    filename: str,
    when: str = 'midnight',
    interval: int = 1,
    backup_count: int = 30,
    formatter_type: str = "json"
) -> TimedRotatingFileHandler:
    """
    Get a time-based rotating file handler.

    Args:
        log_dir: Directory for log files
        filename: Log file name
        when: When to rotate ('S', 'M', 'H', 'D', 'midnight')
        interval: Interval for rotation
        backup_count: Number of backup files to keep
        formatter_type: "json", "text", or "compact"

    Returns:
        Configured timed rotating handler
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    filepath = log_path / filename

    handler = TimedRotatingFileHandler(
        filename=str(filepath),
        when=when,
        interval=interval,
        backupCount=backup_count,
        encoding='utf-8'
    )

    # Set formatter
    if formatter_type == "json":
        handler.setFormatter(JsonFormatter())
    elif formatter_type == "compact":
        handler.setFormatter(CompactFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))

    return handler


def get_console_handler(colored: bool = True, level: int = logging.INFO) -> logging.StreamHandler:
    """
    Get a console handler for terminal output.

    Args:
        colored: Whether to use colored output
        level: Logging level

    Returns:
        Configured console handler
    """
    handler = logging.StreamHandler()
    handler.setLevel(level)

    if colored:
        handler.setFormatter(ColoredFormatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            datefmt='%H:%M:%S'
        ))
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        ))

    return handler


def get_equipment_handler(log_dir: str, equipment_id: str) -> logging.Handler:
    """
    Get a handler for equipment-specific logging.

    Args:
        log_dir: Directory for log files
        equipment_id: Equipment identifier

    Returns:
        Configured file handler for equipment logs
    """
    return get_rotating_file_handler(
        log_dir=log_dir,
        filename=f"equipment_{equipment_id}.log",
        max_bytes=10 * 1024 * 1024,  # 10 MB
        backup_count=5,
        formatter_type="json",
        compress=True
    )


def get_performance_handler(log_dir: str) -> logging.Handler:
    """
    Get a handler for performance metrics logging.

    Args:
        log_dir: Directory for log files

    Returns:
        Configured file handler for performance logs
    """
    return get_rotating_file_handler(
        log_dir=log_dir,
        filename="performance.log",
        max_bytes=50 * 1024 * 1024,  # 50 MB
        backup_count=10,
        formatter_type="json",
        compress=True
    )


def get_audit_handler(log_dir: str) -> logging.Handler:
    """
    Get a handler for audit trail logging.

    Args:
        log_dir: Directory for log files

    Returns:
        Configured file handler for audit logs
    """
    return get_rotating_file_handler(
        log_dir=log_dir,
        filename="audit.log",
        max_bytes=100 * 1024 * 1024,  # 100 MB
        backup_count=30,
        formatter_type="json",
        compress=True
    )
