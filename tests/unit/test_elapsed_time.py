"""Durations must be measured with a monotonic, high-resolution clock.

Found on Windows, where `time.time()` resolves to the 15.625 ms timer tick.
999 of 1000 instant operations measured exactly 0.0 there, which broke two
things that had always passed on Linux, where the same call resolves to about
a nanosecond:

- a diagnostics check asserting `response_time_ms > 0` got 0.0
- a trend fit over five points captured inside one tick got five *identical*
  timestamps, making the regression's x-vector constant, and numpy raised
  "SVD did not converge in Linear Least Squares"

Resolution is only half of it. `time.time()` is a wall clock and can step
backwards under an NTP correction, so an elapsed time computed from it can be
negative on any platform. `time.perf_counter()` is monotonic and is the right
API for an interval.

These tests do not need a coarse clock to be meaningful: they assert the
property directly, so they hold on every platform.
"""

import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# The two places a wall clock is correct, and why. Anything else measuring an
# interval should be monotonic.
WALL_CLOCK_ALLOWED = {
    "server/logging_config/utils.py",   # compared against st_mtime
    "server/websocket/enhanced_features.py",  # a timestamp reported to clients
}


class TestMonotonicClockIsUsedForDurations:
    def test_no_duration_is_measured_with_the_wall_clock(self):
        """A subtraction of two time.time() values is the bug's signature."""
        offenders = []

        for path in sorted(REPO.glob("server/**/*.py")):
            rel = path.relative_to(REPO).as_posix()
            if rel in WALL_CLOCK_ALLOWED:
                continue
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                if re.search(r"time\.time\(\)\s*-|-\s*\w*(start|last)\w*\s*$", line) \
                        and "time.time()" in line:
                    offenders.append(f"{rel}:{number}: {line.strip()}")

        assert not offenders, (
            "durations measured with the wall clock:\n  " + "\n  ".join(offenders)
        )

    def test_wall_clock_survives_only_where_it_is_correct(self):
        """Guards the exceptions, so they stay deliberate rather than missed."""
        using_wall_clock = set()

        for path in sorted(REPO.glob("server/**/*.py")):
            if "time.time()" in path.read_text(encoding="utf-8"):
                using_wall_clock.add(path.relative_to(REPO).as_posix())

        assert using_wall_clock == WALL_CLOCK_ALLOWED, (
            f"unexpected: {using_wall_clock - WALL_CLOCK_ALLOWED}, "
            f"gone: {WALL_CLOCK_ALLOWED - using_wall_clock}"
        )

    def test_perf_counter_resolves_a_fast_operation(self):
        """The property the Windows clock lacked."""
        distinct = {time.perf_counter() for _ in range(1000)}

        assert len(distinct) > 1, "perf_counter is not resolving repeated calls"

    def test_perf_counter_never_goes_backwards(self):
        """What time.time() cannot promise on any platform."""
        readings = [time.perf_counter() for _ in range(1000)]

        assert readings == sorted(readings)


class TestDegenerateTrendFit:
    """Points sharing a timestamp must not raise."""

    @pytest.fixture
    def trending(self):
        pytest.importorskip("numpy")
        from server.waveform.advanced_analysis import AdvancedWaveformAnalyzer

        return AdvancedWaveformAnalyzer()

    def _add(self, analyzer, monkeypatch, timestamps):
        """Drive update_trend with a controlled clock.

        update_trend stamps points with datetime.now() internally, so a coarse
        clock is simulated by patching that rather than by hoping the machine
        has one.
        """
        import server.waveform.advanced_analysis as mod
        from server.waveform.advanced_analysis import TrendParameter

        supplied = iter(timestamps)
        real_datetime = mod.datetime

        class FrozenDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                try:
                    return next(supplied)
                except StopIteration:
                    return timestamps[-1]

        monkeypatch.setattr(mod, "datetime", FrozenDatetime)

        trend = None
        for i in range(len(timestamps) // 3):
            trend = analyzer.update_trend("eq", 1, TrendParameter.FREQUENCY, 1.0 + i)
        return trend

    def test_identical_timestamps_do_not_raise(self, trending, monkeypatch):
        """Points inside one clock tick: the exact Windows failure.

        Without the guard numpy raises LinAlgError, "SVD did not converge in
        Linear Least Squares", because the x-vector is constant.
        """
        now = datetime.now()
        trend = self._add(trending, monkeypatch, [now] * 15)

        assert trend is not None
        assert trend.drift_rate == 0.0, "no elapsed time means no measurable drift"
        assert trend.trend_direction == "stable"

    def test_distinct_timestamps_still_fit(self, trending, monkeypatch):
        """The guard must not swallow a real trend."""
        now = datetime.now()
        stamps = [now + timedelta(seconds=i) for i in range(15)]
        trend = self._add(trending, monkeypatch, stamps)

        assert trend is not None
        assert trend.drift_rate > 0, "a rising series should show positive drift"
        assert trend.trend_direction == "up"
