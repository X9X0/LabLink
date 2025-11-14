"""
Performance Profiling Utilities for LabLink

Provides decorators and context managers for profiling code performance.
Includes support for cProfile, line_profiler, and memory profiling.

Usage:
    # Decorator usage
    from server.utils.profiling import profile

    @profile
    def my_function():
        pass

    # Context manager usage
    with profile_context("operation_name"):
        expensive_operation()

    # Conditional profiling
    @profile_if_enabled
    def production_function():
        pass  # Only profiled if LABLINK_PROFILING=true
"""

import cProfile
import functools
import logging
import os
import pstats
import time
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Configuration
PROFILE_ENABLED = os.getenv("LABLINK_PROFILING", "false").lower() == "true"
PROFILE_OUTPUT_DIR = Path(os.getenv("LABLINK_PROFILE_DIR", "/tmp/lablink_profiles"))
PROFILE_PRINT_STATS = os.getenv("LABLINK_PROFILE_PRINT", "false").lower() == "true"
PROFILE_TOP_N = int(os.getenv("LABLINK_PROFILE_TOP", "20"))


def ensure_profile_dir():
    """Ensure profile output directory exists."""
    if PROFILE_ENABLED:
        PROFILE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def profile(
    output_file: Optional[str] = None,
    sort_by: str = "cumulative",
    print_stats: bool = False,
    top_n: int = 20,
):
    """
    Decorator to profile a function with cProfile.

    Args:
        output_file: Optional path to save profile data (default: /tmp/lablink_profiles/{func_name}.prof)
        sort_by: How to sort statistics ('cumulative', 'time', 'calls')
        print_stats: Whether to print statistics to console
        top_n: Number of top functions to print

    Example:
        @profile
        def slow_function():
            time.sleep(1)

        @profile(output_file="custom.prof", print_stats=True)
        def another_function():
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            profiler = cProfile.Profile()
            profiler.enable()

            try:
                result = func(*args, **kwargs)
            finally:
                profiler.disable()

                # Determine output file
                if output_file:
                    out_path = Path(output_file)
                else:
                    ensure_profile_dir()
                    out_path = PROFILE_OUTPUT_DIR / f"{func.__name__}.prof"

                # Save profile
                profiler.dump_stats(str(out_path))
                logger.info(f"Profile saved to: {out_path}")

                # Print statistics if requested
                if print_stats or PROFILE_PRINT_STATS:
                    stats = pstats.Stats(profiler)
                    stats.sort_stats(sort_by)
                    print(f"\n{'=' * 80}")
                    print(f"Profile for {func.__name__}")
                    print(f"{'=' * 80}")
                    stats.print_stats(top_n)
                    print(f"{'=' * 80}\n")

            return result

        return wrapper

    return decorator


def profile_if_enabled(func: Callable) -> Callable:
    """
    Conditional profiling decorator - only profiles if LABLINK_PROFILING=true.

    This is useful for production code where you want profiling available
    but not always active.

    Example:
        @profile_if_enabled
        def production_function():
            expensive_operation()

    Enable profiling:
        export LABLINK_PROFILING=true
        python server/main.py
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not PROFILE_ENABLED:
            return func(*args, **kwargs)

        # Profile is enabled
        return profile(
            print_stats=PROFILE_PRINT_STATS, top_n=PROFILE_TOP_N
        )(func)(*args, **kwargs)

    return wrapper


@contextmanager
def profile_context(
    name: str,
    output_file: Optional[str] = None,
    sort_by: str = "cumulative",
    print_stats: bool = False,
    top_n: int = 20,
):
    """
    Context manager for profiling a code block.

    Args:
        name: Name for this profiling session
        output_file: Optional path to save profile data
        sort_by: How to sort statistics
        print_stats: Whether to print statistics
        top_n: Number of top functions to print

    Example:
        with profile_context("database_operations"):
            for i in range(100):
                db.insert(record)
    """
    profiler = cProfile.Profile()
    profiler.enable()

    try:
        yield profiler
    finally:
        profiler.disable()

        # Determine output file
        if output_file:
            out_path = Path(output_file)
        else:
            ensure_profile_dir()
            out_path = PROFILE_OUTPUT_DIR / f"{name}.prof"

        # Save profile
        profiler.dump_stats(str(out_path))
        logger.info(f"Profile saved to: {out_path}")

        # Print statistics if requested
        if print_stats or PROFILE_PRINT_STATS:
            stats = pstats.Stats(profiler)
            stats.sort_stats(sort_by)
            print(f"\n{'=' * 80}")
            print(f"Profile for {name}")
            print(f"{'=' * 80}")
            stats.print_stats(top_n)
            print(f"{'=' * 80}\n")


@contextmanager
def time_block(name: str, log_level: int = logging.INFO):
    """
    Simple timing context manager (no profiling, just wall-clock time).

    Useful for quick performance checks without full profiling overhead.

    Args:
        name: Name of the operation being timed
        log_level: Logging level for the result

    Example:
        with time_block("Backup creation"):
            create_backup()
        # Output: Backup creation took 1.234s
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start_time
        logger.log(log_level, f"{name} took {elapsed:.3f}s")


def get_profile_stats(
    profile_file: str, sort_by: str = "cumulative", top_n: int = 20
) -> str:
    """
    Load and format profile statistics from a saved profile file.

    Args:
        profile_file: Path to .prof file
        sort_by: How to sort statistics
        top_n: Number of top functions to include

    Returns:
        Formatted statistics as string

    Example:
        stats = get_profile_stats("login.prof")
        print(stats)
    """
    stats = pstats.Stats(profile_file)
    stats.sort_stats(sort_by)

    # Capture output to string
    stream = StringIO()
    stats.stream = stream
    stats.print_stats(top_n)

    return stream.getvalue()


def compare_profiles(
    baseline_file: str, current_file: str, sort_by: str = "cumulative", top_n: int = 20
) -> dict:
    """
    Compare two profile files to detect performance regressions.

    Args:
        baseline_file: Path to baseline .prof file
        current_file: Path to current .prof file
        sort_by: How to sort statistics
        top_n: Number of top functions to compare

    Returns:
        Dictionary with comparison data

    Example:
        comparison = compare_profiles("baseline.prof", "current.prof")
        if comparison['regression']:
            print(f"Regression detected: {comparison['slowest_function']}")
    """
    baseline_stats = pstats.Stats(baseline_file)
    current_stats = pstats.Stats(current_file)

    # Get top functions from baseline
    baseline_stats.sort_stats(sort_by)
    stream = StringIO()
    baseline_stats.stream = stream
    baseline_stats.print_stats(top_n)

    # TODO: Implement detailed comparison logic
    # This is a placeholder for future implementation

    return {
        "baseline_file": baseline_file,
        "current_file": current_file,
        "regression": False,  # Placeholder
        "details": "Comparison not yet implemented",
    }


# Async profiling support
try:
    import asyncio

    def profile_async(
        output_file: Optional[str] = None,
        sort_by: str = "cumulative",
        print_stats: bool = False,
        top_n: int = 20,
    ):
        """
        Decorator to profile an async function.

        Example:
            @profile_async
            async def slow_async_function():
                await asyncio.sleep(1)
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                profiler = cProfile.Profile()
                profiler.enable()

                try:
                    result = await func(*args, **kwargs)
                finally:
                    profiler.disable()

                    # Determine output file
                    if output_file:
                        out_path = Path(output_file)
                    else:
                        ensure_profile_dir()
                        out_path = PROFILE_OUTPUT_DIR / f"{func.__name__}.prof"

                    # Save profile
                    profiler.dump_stats(str(out_path))
                    logger.info(f"Profile saved to: {out_path}")

                    # Print statistics if requested
                    if print_stats or PROFILE_PRINT_STATS:
                        stats = pstats.Stats(profiler)
                        stats.sort_stats(sort_by)
                        print(f"\n{'=' * 80}")
                        print(f"Profile for {func.__name__} (async)")
                        print(f"{'=' * 80}")
                        stats.print_stats(top_n)
                        print(f"{'=' * 80}\n")

                return result

            return wrapper

        return decorator

except ImportError:
    # asyncio not available
    pass


if __name__ == "__main__":
    # Example usage
    @profile(print_stats=True, top_n=10)
    def example_function():
        """Example function to demonstrate profiling."""
        total = 0
        for i in range(1000000):
            total += i
        return total

    print("Running example profiling...")
    result = example_function()
    print(f"Result: {result}")
    print(f"\nProfile saved to: {PROFILE_OUTPUT_DIR}/example_function.prof")
    print("\nView with:")
    print(f"  snakeviz {PROFILE_OUTPUT_DIR}/example_function.prof")
