"""
Unit tests for hardware base classes and utilities.
Tests ExponentialBackoff and BoundedQueueHardwareHandler logic.
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from utils.hardware_base import (
    ExponentialBackoff,
    HardwareSnapshot,
    BoundedQueueHardwareHandler,
)


class TestExponentialBackoff:
    """Tests for ExponentialBackoff class."""

    @pytest.mark.unit
    def test_initial_state_no_backoff(self):
        """Test that initial state has no backoff."""
        backoff = ExponentialBackoff()
        assert backoff.should_skip() is False
        assert backoff.consecutive_failures == 0
        assert backoff.current_delay == 0.0

    @pytest.mark.unit
    def test_first_failure_applies_initial_delay(self):
        """Test that first failure applies initial delay."""
        backoff = ExponentialBackoff(initial_delay=1.0)
        backoff.record_failure()

        assert backoff.consecutive_failures == 1
        assert backoff.current_delay == 1.0
        assert backoff.should_skip() is True

    @pytest.mark.unit
    def test_consecutive_failures_multiply_delay(self):
        """Test that consecutive failures multiply the delay."""
        backoff = ExponentialBackoff(initial_delay=1.0, multiplier=2.0)

        backoff.record_failure()
        assert backoff.current_delay == 1.0

        backoff.record_failure()
        assert backoff.current_delay == 2.0

        backoff.record_failure()
        assert backoff.current_delay == 4.0

    @pytest.mark.unit
    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        backoff = ExponentialBackoff(initial_delay=1.0, multiplier=10.0, max_delay=5.0)

        backoff.record_failure()  # 1.0
        backoff.record_failure()  # Would be 10.0, capped to 5.0

        assert backoff.current_delay == 5.0

    @pytest.mark.unit
    def test_reset_clears_state(self):
        """Test that reset clears all state."""
        backoff = ExponentialBackoff(initial_delay=1.0)

        backoff.record_failure()
        backoff.record_failure()
        backoff.reset()

        assert backoff.consecutive_failures == 0
        assert backoff.current_delay == 0.0
        assert backoff.should_skip() is False

    @pytest.mark.unit
    def test_should_skip_after_delay_expires(self):
        """Test that should_skip returns False after delay expires."""
        backoff = ExponentialBackoff(initial_delay=0.05)  # 50ms

        backoff.record_failure()
        assert backoff.should_skip() is True

        time.sleep(0.1)  # Wait for delay to expire
        assert backoff.should_skip() is False

    @pytest.mark.unit
    def test_custom_multiplier(self):
        """Test custom multiplier value."""
        backoff = ExponentialBackoff(initial_delay=1.0, multiplier=3.0)

        backoff.record_failure()  # 1.0
        backoff.record_failure()  # 3.0
        backoff.record_failure()  # 9.0

        assert backoff.current_delay == 9.0

    @pytest.mark.unit
    def test_consecutive_failures_tracks_count(self):
        """Test that consecutive_failures property tracks correctly."""
        backoff = ExponentialBackoff()

        for i in range(5):
            backoff.record_failure()
            assert backoff.consecutive_failures == i + 1

        backoff.reset()
        assert backoff.consecutive_failures == 0

    @pytest.mark.unit
    def test_default_values(self):
        """Test default parameter values."""
        backoff = ExponentialBackoff()

        assert backoff.initial_delay == 1.0
        assert backoff.multiplier == 2.0
        assert backoff.max_delay == 64.0


class TestHardwareSnapshot:
    """Tests for HardwareSnapshot dataclass."""

    @pytest.mark.unit
    def test_snapshot_creation(self):
        """Test creating a HardwareSnapshot."""
        snapshot = HardwareSnapshot(
            timestamp=1234567890.0,
            data={'temp': 25.0},
            metadata={'status': 'ok'}
        )

        assert snapshot.timestamp == 1234567890.0
        assert snapshot.data == {'temp': 25.0}
        assert snapshot.metadata == {'status': 'ok'}

    @pytest.mark.unit
    def test_snapshot_immutable(self):
        """Test that HardwareSnapshot is immutable (frozen)."""
        snapshot = HardwareSnapshot(
            timestamp=1234567890.0,
            data={'temp': 25.0}
        )

        with pytest.raises(AttributeError):
            snapshot.timestamp = 9999999999.0

    @pytest.mark.unit
    def test_snapshot_default_values(self):
        """Test HardwareSnapshot default values."""
        snapshot = HardwareSnapshot(timestamp=1234567890.0)

        assert snapshot.data == {}
        assert snapshot.metadata == {}

    @pytest.mark.unit
    def test_snapshot_equality(self):
        """Test HardwareSnapshot equality comparison."""
        snap1 = HardwareSnapshot(timestamp=1.0, data={'a': 1})
        snap2 = HardwareSnapshot(timestamp=1.0, data={'a': 1})
        snap3 = HardwareSnapshot(timestamp=2.0, data={'a': 1})

        assert snap1 == snap2
        assert snap1 != snap3


class TestBoundedQueueHardwareHandler:
    """Tests for BoundedQueueHardwareHandler base class."""

    @pytest.fixture
    def handler(self):
        """Create a test handler instance."""
        # Create a concrete subclass for testing
        class TestHandler(BoundedQueueHardwareHandler):
            def __init__(self):
                super().__init__(queue_depth=2)
                self.poll_count = 0

            def _worker_loop(self):
                while self.running:
                    self.poll_count += 1
                    self._publish_snapshot({'count': self.poll_count})
                    time.sleep(0.01)

        return TestHandler()

    @pytest.mark.unit
    def test_initial_state(self, handler):
        """Test handler initial state."""
        assert handler.running is False
        assert handler.current_snapshot is None
        assert handler.queue_depth == 2

    @pytest.mark.unit
    def test_get_snapshot_returns_none_initially(self, handler):
        """Test get_snapshot returns None before any data."""
        result = handler.get_snapshot()
        assert result is None

    @pytest.mark.unit
    def test_publish_snapshot_creates_snapshot(self, handler):
        """Test that _publish_snapshot creates a retrievable snapshot."""
        test_data = {'temp': 25.0, 'pressure': 32.0}
        handler._publish_snapshot(test_data)

        snapshot = handler.get_snapshot()
        assert snapshot is not None
        assert snapshot.data == test_data

    @pytest.mark.unit
    def test_publish_snapshot_with_metadata(self, handler):
        """Test publishing snapshot with metadata."""
        handler._publish_snapshot(
            {'value': 1},
            metadata={'status': 'ok', 'errors': 0}
        )

        snapshot = handler.get_snapshot()
        assert snapshot.metadata == {'status': 'ok', 'errors': 0}

    @pytest.mark.unit
    def test_get_data_returns_dict(self, handler):
        """Test get_data returns data dictionary."""
        handler._publish_snapshot({'temp': 25.0})

        result = handler.get_data()
        assert result == {'temp': 25.0}

    @pytest.mark.unit
    def test_get_data_returns_empty_dict_when_no_data(self, handler):
        """Test get_data returns empty dict when no data."""
        result = handler.get_data()
        assert result == {}

    @pytest.mark.unit
    def test_queue_bounded_to_depth(self, handler):
        """Test that queue doesn't grow beyond depth."""
        # Publish more snapshots than queue depth
        for i in range(10):
            handler._publish_snapshot({'count': i})

        # Queue should only have up to queue_depth items
        assert handler.data_queue.qsize() <= handler.queue_depth

    @pytest.mark.unit
    def test_get_snapshot_drains_queue(self, handler):
        """Test that get_snapshot drains the queue."""
        handler._publish_snapshot({'value': 1})
        handler._publish_snapshot({'value': 2})

        snapshot = handler.get_snapshot()

        # Should get the latest value
        assert snapshot.data['value'] == 2
        # Queue should be empty after get
        assert handler.data_queue.empty()

    @pytest.mark.unit
    def test_snapshot_timestamp_set(self, handler):
        """Test that snapshots have correct timestamps."""
        before = time.time()
        handler._publish_snapshot({'test': True})
        after = time.time()

        snapshot = handler.get_snapshot()
        assert before <= snapshot.timestamp <= after

    @pytest.mark.unit
    def test_publish_with_none_data(self, handler):
        """Test publishing with None data."""
        handler._publish_snapshot(None)

        snapshot = handler.get_snapshot()
        assert snapshot.data == {}

    @pytest.mark.unit
    def test_publish_with_none_metadata(self, handler):
        """Test publishing with None metadata."""
        handler._publish_snapshot({'test': True}, metadata=None)

        snapshot = handler.get_snapshot()
        assert snapshot.metadata == {}

    @pytest.mark.unit
    def test_frame_drop_stats(self, handler):
        """Test frame drop statistics tracking."""
        stats = handler.get_frame_drop_stats()
        assert 'recent' in stats
        assert 'total' in stats
        assert stats['recent'] == 0
        assert stats['total'] == 0

    @pytest.mark.unit
    def test_start_sets_running(self, handler):
        """Test that start() sets running flag."""
        handler.start()
        try:
            assert handler.running is True
            assert handler.thread is not None
            assert handler.thread.is_alive()
        finally:
            handler.stop()

    @pytest.mark.unit
    def test_stop_clears_running(self, handler):
        """Test that stop() clears running flag."""
        handler.start()
        handler.stop()

        assert handler.running is False

    @pytest.mark.unit
    def test_double_start_ignored(self, handler):
        """Test that starting twice doesn't create multiple threads."""
        handler.start()
        thread1 = handler.thread
        handler.start()
        thread2 = handler.thread

        try:
            assert thread1 is thread2
        finally:
            handler.stop()

    @pytest.mark.unit
    def test_get_update_rate(self, handler):
        """Test get_update_rate returns float."""
        rate = handler.get_update_rate()
        assert isinstance(rate, float)
        assert rate >= 0


class TestBoundedQueuePerformance:
    """Performance-related tests for BoundedQueueHardwareHandler."""

    @pytest.mark.unit
    def test_snapshot_copy_is_independent(self):
        """Test that snapshot data is copied, not referenced."""
        class TestHandler(BoundedQueueHardwareHandler):
            def _worker_loop(self):
                pass

        handler = TestHandler()
        original_data = {'temp': 25.0}
        handler._publish_snapshot(original_data)

        # Modify original after publishing
        original_data['temp'] = 999.0

        snapshot = handler.get_snapshot()
        # Snapshot should have original value, not modified
        assert snapshot.data['temp'] == 25.0

    @pytest.mark.unit
    def test_queue_overflow_drops_old(self):
        """Test that queue overflow drops oldest frames."""
        class TestHandler(BoundedQueueHardwareHandler):
            def _worker_loop(self):
                pass

        handler = TestHandler(queue_depth=2)

        # Fill queue
        handler._publish_snapshot({'seq': 1})
        handler._publish_snapshot({'seq': 2})

        # This should cause overflow, dropping seq=1
        handler._publish_snapshot({'seq': 3})

        # Get all snapshots
        snapshots = []
        while True:
            snap = handler.get_snapshot()
            if snap is None or (snapshots and snap == snapshots[-1]):
                break
            snapshots.append(snap)

        # Latest snapshot should be seq=3
        assert handler.current_snapshot.data['seq'] == 3
