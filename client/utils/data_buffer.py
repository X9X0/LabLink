"""Circular data buffer for real-time plotting."""

import numpy as np
from typing import Optional, Tuple
from collections import deque


class CircularBuffer:
    """Efficient circular buffer for time-series data."""

    def __init__(self, size: int, num_channels: int = 1):
        """Initialize circular buffer.

        Args:
            size: Buffer size (number of samples)
            num_channels: Number of data channels
        """
        self.size = size
        self.num_channels = num_channels

        # Data storage
        self._time = np.zeros(size, dtype=np.float64)
        self._data = np.zeros((num_channels, size), dtype=np.float64)

        # Buffer state
        self._index = 0
        self._full = False
        self._count = 0

    def append(self, timestamp: float, values: np.ndarray):
        """Append a data point.

        Args:
            timestamp: Time value
            values: Data values (length must match num_channels)
        """
        if len(values) != self.num_channels:
            raise ValueError(f"Expected {self.num_channels} values, got {len(values)}")

        self._time[self._index] = timestamp
        self._data[:, self._index] = values

        self._index += 1
        self._count += 1

        if self._index >= self.size:
            self._index = 0
            self._full = True

    def get_data(self, channel: int = 0) -> Tuple[np.ndarray, np.ndarray]:
        """Get data for a channel in chronological order.

        Args:
            channel: Channel index (0-indexed)

        Returns:
            Tuple of (time_array, data_array)
        """
        if channel < 0 or channel >= self.num_channels:
            raise ValueError(f"Invalid channel: {channel}")

        if not self._full:
            # Return only filled portion
            return self._time[:self._index].copy(), self._data[channel, :self._index].copy()
        else:
            # Reorder to chronological
            time_data = np.roll(self._time, -self._index)
            channel_data = np.roll(self._data[channel, :], -self._index)
            return time_data, channel_data

    def get_all_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get all channels in chronological order.

        Returns:
            Tuple of (time_array, data_array) where data_array is shape (num_channels, samples)
        """
        if not self._full:
            return self._time[:self._index].copy(), self._data[:, :self._index].copy()
        else:
            time_data = np.roll(self._time, -self._index)
            data_array = np.roll(self._data, -self._index, axis=1)
            return time_data, data_array

    def get_latest(self, n: int = 1) -> Tuple[np.ndarray, np.ndarray]:
        """Get the latest n samples.

        Args:
            n: Number of samples to retrieve

        Returns:
            Tuple of (time_array, data_array)
        """
        n = min(n, self.get_count())
        if n == 0:
            return np.array([]), np.array([[] for _ in range(self.num_channels)])

        if not self._full:
            start_idx = max(0, self._index - n)
            return self._time[start_idx:self._index].copy(), self._data[:, start_idx:self._index].copy()
        else:
            # Get last n samples wrapping around
            indices = [(self._index - n + i) % self.size for i in range(n)]
            return self._time[indices].copy(), self._data[:, indices].copy()

    def clear(self):
        """Clear the buffer."""
        self._time.fill(0)
        self._data.fill(0)
        self._index = 0
        self._full = False
        self._count = 0

    def get_count(self) -> int:
        """Get number of samples in buffer.

        Returns:
            Sample count
        """
        return self.size if self._full else self._index

    def get_total_count(self) -> int:
        """Get total number of samples ever added.

        Returns:
            Total count
        """
        return self._count

    def is_full(self) -> bool:
        """Check if buffer is full.

        Returns:
            True if buffer is full
        """
        return self._full


class SlidingWindowBuffer:
    """Sliding window buffer that maintains only recent data."""

    def __init__(self, window_size: float, sample_rate: float):
        """Initialize sliding window buffer.

        Args:
            window_size: Window size in seconds
            sample_rate: Expected sample rate in Hz
        """
        self.window_size = window_size
        self.sample_rate = sample_rate

        # Use deque for efficient append/pop
        self._times = deque()
        self._data = deque()

        self._count = 0

    def append(self, timestamp: float, value: float):
        """Append a data point.

        Args:
            timestamp: Time value
            value: Data value
        """
        self._times.append(timestamp)
        self._data.append(value)
        self._count += 1

        # Remove old data outside window
        while len(self._times) > 0:
            if self._times[-1] - self._times[0] > self.window_size:
                self._times.popleft()
                self._data.popleft()
            else:
                break

    def get_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get all data in window.

        Returns:
            Tuple of (time_array, data_array)
        """
        return np.array(self._times), np.array(self._data)

    def get_latest(self, n: int = 1) -> Tuple[np.ndarray, np.ndarray]:
        """Get latest n samples.

        Args:
            n: Number of samples

        Returns:
            Tuple of (time_array, data_array)
        """
        n = min(n, len(self._times))
        if n == 0:
            return np.array([]), np.array([])

        return (
            np.array(list(self._times)[-n:]),
            np.array(list(self._data)[-n:])
        )

    def clear(self):
        """Clear the buffer."""
        self._times.clear()
        self._data.clear()
        self._count = 0

    def get_count(self) -> int:
        """Get number of samples in window.

        Returns:
            Sample count
        """
        return len(self._times)

    def get_total_count(self) -> int:
        """Get total samples ever added.

        Returns:
            Total count
        """
        return self._count
