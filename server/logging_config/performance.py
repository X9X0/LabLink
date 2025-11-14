"""Performance monitoring and metrics logging."""

import functools
import logging
import time
from datetime import datetime
from typing import Any, Callable, Optional

import psutil

# Performance logger
performance_logger = logging.getLogger("lablink.performance")


def log_performance(func: Callable) -> Callable:
    """
    Decorator to log function execution time and performance metrics.

    Usage:
        @log_performance
        async def my_function():
            ...
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        try:
            result = await func(*args, **kwargs)
            success = True
            error = None
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

            duration_ms = (end_time - start_time) * 1000
            memory_delta = end_memory - start_memory

            performance_logger.info(
                f"Function execution: {func.__name__}",
                extra={
                    "function": func.__name__,
                    "module": func.__module__,
                    "duration_ms": round(duration_ms, 2),
                    "memory_delta_mb": round(memory_delta, 2),
                    "success": success,
                    "error": error,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        return result

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        try:
            result = func(*args, **kwargs)
            success = True
            error = None
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

            duration_ms = (end_time - start_time) * 1000
            memory_delta = end_memory - start_memory

            performance_logger.info(
                f"Function execution: {func.__name__}",
                extra={
                    "function": func.__name__,
                    "module": func.__module__,
                    "duration_ms": round(duration_ms, 2),
                    "memory_delta_mb": round(memory_delta, 2),
                    "success": success,
                    "error": error,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        return result

    # Return appropriate wrapper based on function type
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


# Need to import asyncio at module level for iscoroutinefunction check
import asyncio


class PerformanceMonitor:
    """Monitor and log system performance metrics."""

    def __init__(self):
        """Initialize performance monitor."""
        self.logger = performance_logger

    def log_system_metrics(self):
        """Log current system performance metrics."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        self.logger.info(
            "System performance metrics",
            extra={
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_mb": memory.available / 1024 / 1024,
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / 1024 / 1024 / 1024,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def log_equipment_metrics(self, equipment_id: str, metrics: dict):
        """
        Log equipment-specific performance metrics.

        Args:
            equipment_id: Equipment identifier
            metrics: Dictionary of metrics to log
        """
        self.logger.info(
            f"Equipment metrics: {equipment_id}",
            extra={
                "equipment_id": equipment_id,
                "timestamp": datetime.now().isoformat(),
                **metrics,
            },
        )

    def log_api_metrics(
        self, endpoint: str, method: str, duration_ms: float, status_code: int
    ):
        """
        Log API endpoint performance metrics.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            duration_ms: Request duration in milliseconds
            status_code: HTTP status code
        """
        self.logger.info(
            f"API request: {method} {endpoint}",
            extra={
                "endpoint": endpoint,
                "method": method,
                "duration_ms": round(duration_ms, 2),
                "status_code": status_code,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def log_acquisition_metrics(
        self,
        acquisition_id: str,
        samples_collected: int,
        buffer_usage_percent: float,
        sample_rate: float,
    ):
        """
        Log data acquisition performance metrics.

        Args:
            acquisition_id: Acquisition session ID
            samples_collected: Number of samples collected
            buffer_usage_percent: Buffer utilization percentage
            sample_rate: Actual sample rate achieved
        """
        self.logger.info(
            f"Acquisition metrics: {acquisition_id}",
            extra={
                "acquisition_id": acquisition_id,
                "samples_collected": samples_collected,
                "buffer_usage_percent": round(buffer_usage_percent, 2),
                "sample_rate": round(sample_rate, 2),
                "timestamp": datetime.now().isoformat(),
            },
        )


# Global performance monitor instance
performance_monitor = PerformanceMonitor()
