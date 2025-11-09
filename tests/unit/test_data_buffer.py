"""Unit tests for data buffer classes."""

import pytest
import numpy as np
from client.utils.data_buffer import CircularBuffer, SlidingWindowBuffer


@pytest.mark.unit
class TestCircularBuffer:
    """Test CircularBuffer class."""

    def test_initialization(self):
        """Test buffer initialization."""
        buffer = CircularBuffer(size=100, num_channels=3)

        assert buffer.size == 100
        assert buffer.num_channels == 3
        assert buffer.count == 0
        assert buffer.is_full() is False

    def test_append_single(self):
        """Test appending single data point."""
        buffer = CircularBuffer(size=10, num_channels=2)

        timestamp = 1.0
        values = np.array([1.5, 2.5])

        buffer.append(timestamp, values)

        assert buffer.count == 1
        time_data, channel_data = buffer.get_all()
        assert len(time_data) == 1
        assert time_data[0] == timestamp
        np.testing.assert_array_equal(channel_data[0], values)

    def test_circular_overwrite(self):
        """Test circular buffer overwrites old data."""
        buffer = CircularBuffer(size=5, num_channels=1)

        # Add more data than buffer size
        for i in range(10):
            buffer.append(float(i), np.array([float(i)]))

        # Should only have last 5 entries
        assert buffer.count == 5
        time_data, channel_data = buffer.get_all()
        assert len(time_data) == 5

        # Check data is from indices 5-9
        expected_times = [5.0, 6.0, 7.0, 8.0, 9.0]
        np.testing.assert_array_equal(time_data, expected_times)

    def test_get_channel(self):
        """Test getting single channel data."""
        buffer = CircularBuffer(size=10, num_channels=3)

        for i in range(5):
            values = np.array([float(i), float(i * 2), float(i * 3)])
            buffer.append(float(i), values)

        time_data, ch0_data = buffer.get_channel(0)
        time_data, ch1_data = buffer.get_channel(1)

        assert len(time_data) == 5
        np.testing.assert_array_equal(ch0_data, [0.0, 1.0, 2.0, 3.0, 4.0])
        np.testing.assert_array_equal(ch1_data, [0.0, 2.0, 4.0, 6.0, 8.0])

    def test_clear(self):
        """Test clearing buffer."""
        buffer = CircularBuffer(size=10, num_channels=2)

        for i in range(5):
            buffer.append(float(i), np.array([float(i), float(i)]))

        assert buffer.count == 5

        buffer.clear()

        assert buffer.count == 0
        time_data, channel_data = buffer.get_all()
        assert len(time_data) == 0

    def test_is_full(self):
        """Test is_full method."""
        buffer = CircularBuffer(size=3, num_channels=1)

        assert buffer.is_full() is False

        buffer.append(1.0, np.array([1.0]))
        assert buffer.is_full() is False

        buffer.append(2.0, np.array([2.0]))
        assert buffer.is_full() is False

        buffer.append(3.0, np.array([3.0]))
        assert buffer.is_full() is True

        buffer.append(4.0, np.array([4.0]))
        assert buffer.is_full() is True

    def test_invalid_channel(self):
        """Test getting invalid channel raises error."""
        buffer = CircularBuffer(size=10, num_channels=2)

        with pytest.raises(IndexError):
            buffer.get_channel(5)


@pytest.mark.unit
class TestSlidingWindowBuffer:
    """Test SlidingWindowBuffer class."""

    def test_initialization(self):
        """Test buffer initialization."""
        buffer = SlidingWindowBuffer(window_size=5.0, num_channels=2)

        assert buffer.window_size == 5.0
        assert buffer.num_channels == 2
        assert buffer.count == 0

    def test_append_within_window(self):
        """Test appending data within window."""
        buffer = SlidingWindowBuffer(window_size=10.0, num_channels=1)

        base_time = 100.0
        for i in range(5):
            buffer.append(base_time + i, np.array([float(i)]))

        assert buffer.count == 5

    def test_sliding_window_removes_old_data(self):
        """Test old data is removed outside window."""
        buffer = SlidingWindowBuffer(window_size=5.0, num_channels=1)

        base_time = 0.0

        # Add data spanning 10 seconds
        for i in range(11):
            buffer.append(base_time + i, np.array([float(i)]))

        # Should only keep data within last 5 seconds
        time_data, _ = buffer.get_all()

        # Latest timestamp is 10.0, window is 5.0
        # Should keep data from 5.0 to 10.0 (6 points: 5, 6, 7, 8, 9, 10)
        assert len(time_data) >= 5
        assert all(t >= 5.0 for t in time_data)

    def test_get_channel(self):
        """Test getting channel data."""
        buffer = SlidingWindowBuffer(window_size=10.0, num_channels=2)

        for i in range(5):
            values = np.array([float(i), float(i * 10)])
            buffer.append(float(i), values)

        time_data, ch1_data = buffer.get_channel(1)

        assert len(time_data) == 5
        np.testing.assert_array_equal(ch1_data, [0.0, 10.0, 20.0, 30.0, 40.0])

    def test_clear(self):
        """Test clearing buffer."""
        buffer = SlidingWindowBuffer(window_size=10.0, num_channels=1)

        for i in range(5):
            buffer.append(float(i), np.array([float(i)]))

        assert buffer.count == 5

        buffer.clear()

        assert buffer.count == 0

    def test_empty_buffer(self):
        """Test empty buffer returns empty arrays."""
        buffer = SlidingWindowBuffer(window_size=10.0, num_channels=2)

        time_data, channel_data = buffer.get_all()

        assert len(time_data) == 0
        assert len(channel_data) == 0
