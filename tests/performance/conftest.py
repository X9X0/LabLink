"""Guards for the benchmark suite.

These tests need the `benchmark` fixture from pytest-benchmark, which is not a
declared dependency of this project. Without it every test in the directory
errors at setup with "fixture 'benchmark' not found", so skip the whole
directory cleanly instead.

To run them:  pip install pytest-benchmark && pytest tests/performance
"""

import pytest

collect_ignore_glob = []

try:
    import pytest_benchmark  # noqa: F401

    HAS_BENCHMARK = True
except ImportError:
    HAS_BENCHMARK = False


def pytest_collection_modifyitems(config, items):
    """Skip benchmark tests when the plugin is unavailable."""
    if HAS_BENCHMARK:
        return

    skip = pytest.mark.skip(
        reason="pytest-benchmark not installed (pip install pytest-benchmark)"
    )
    for item in items:
        if "benchmark" in getattr(item, "fixturenames", ()):
            item.add_marker(skip)
