"""Logging utilities and setup functions."""

import logging
from pathlib import Path
from typing import Optional

from config.settings import settings
from .handlers import (
    get_rotating_file_handler,
    get_console_handler,
    get_performance_handler,
    get_audit_handler,
    get_equipment_handler
)


def get_logger(name: str, equipment_id: Optional[str] = None) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name
        equipment_id: Optional equipment ID for equipment-specific logging

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)

    # Add equipment-specific handler if provided
    if equipment_id and settings.log_to_file:
        handler = get_equipment_handler(settings.log_dir, equipment_id)
        logger.addHandler(handler)

    return logger


def setup_logging():
    """
    Setup logging configuration for the entire application.

    This should be called once at application startup.
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.get_numeric_log_level())

    # Clear existing handlers
    root_logger.handlers.clear()

    # Add console handler
    console_handler = get_console_handler(
        colored=True,
        level=settings.get_numeric_log_level()
    )
    root_logger.addHandler(console_handler)

    # Add file handlers if enabled
    if settings.log_to_file:
        # Main application log
        main_handler = get_rotating_file_handler(
            log_dir=settings.log_dir,
            filename="lablink.log",
            max_bytes=settings.log_rotation_size_mb * 1024 * 1024,
            backup_count=settings.log_retention_days,
            formatter_type=settings.log_format,
            compress=True
        )
        root_logger.addHandler(main_handler)

    # Setup specialized loggers
    setup_specialized_loggers()

    # Log startup message
    logger = logging.getLogger("lablink.logging")
    logger.info("Logging system initialized")
    logger.info(f"Log level: {settings.log_level}")
    logger.info(f"Log format: {settings.log_format}")
    logger.info(f"Log to file: {settings.log_to_file}")
    if settings.log_to_file:
        logger.info(f"Log directory: {settings.log_dir}")
        logger.info(f"Log rotation size: {settings.log_rotation_size_mb} MB")
        logger.info(f"Log retention: {settings.log_retention_days} days")


def setup_specialized_loggers():
    """Setup specialized loggers for different subsystems."""
    # Performance logger
    if settings.enable_performance_logging:
        perf_logger = logging.getLogger("lablink.performance")
        perf_logger.setLevel(logging.INFO)
        perf_logger.propagate = False  # Don't propagate to root

        if settings.log_to_file:
            perf_handler = get_performance_handler(settings.log_dir)
            perf_logger.addHandler(perf_handler)

    # Audit logger
    audit_logger = logging.getLogger("lablink.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False

    if settings.log_to_file:
        audit_handler = get_audit_handler(settings.log_dir)
        audit_logger.addHandler(audit_handler)

    # Access logger (HTTP requests)
    access_logger = logging.getLogger("lablink.access")
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False

    if settings.log_to_file:
        access_handler = get_rotating_file_handler(
            log_dir=settings.log_dir,
            filename="access.log",
            max_bytes=50 * 1024 * 1024,  # 50 MB
            backup_count=30,
            formatter_type="json",
            compress=True
        )
        access_logger.addHandler(access_handler)

    # Equipment logger
    equipment_logger = logging.getLogger("lablink.equipment")
    equipment_logger.setLevel(logging.INFO)
    equipment_logger.propagate = False

    if settings.log_to_file:
        equipment_handler = get_rotating_file_handler(
            log_dir=settings.log_dir,
            filename="equipment.log",
            max_bytes=50 * 1024 * 1024,  # 50 MB
            backup_count=20,
            formatter_type="json",
            compress=True
        )
        equipment_logger.addHandler(equipment_handler)


def cleanup_old_logs(log_dir: str, retention_days: int):
    """
    Clean up old log files based on retention policy.

    Args:
        log_dir: Directory containing log files
        retention_days: Number of days to retain logs
    """
    import time
    from datetime import datetime, timedelta

    log_path = Path(log_dir)
    if not log_path.exists():
        return

    cutoff_time = time.time() - (retention_days * 86400)  # 86400 seconds per day

    for log_file in log_path.glob("*.log*"):
        # Check file age
        if log_file.stat().st_mtime < cutoff_time:
            try:
                log_file.unlink()
                logging.getLogger("lablink.logging").info(f"Deleted old log file: {log_file.name}")
            except Exception as e:
                logging.getLogger("lablink.logging").error(f"Failed to delete old log file {log_file.name}: {e}")
