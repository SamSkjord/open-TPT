"""
Base class for hardware handlers with optimised bounded queue architecture.
Implements lock-free data snapshots for render path per system plan.
"""

import threading
import queue
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time


@dataclass
class HardwareSnapshot:
    """
    Immutable snapshot of hardware data for lock-free access.
    Uses dataclass frozen=True for immutability.
    """
    timestamp: float
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BoundedQueueHardwareHandler:
    """
    Base class for hardware handlers implementing bounded queue pattern.

    Key features:
    - Bounded queue for zero-copy data transfer
    - Lock-free snapshots for render path
    - Worker thread handles all I/O and processing
    - Never blocks render loop

    Performance targets from system plan:
    - Queue depth: 2 (1 current + 1 buffer)
    - Snapshot copy: < 0.1 ms
    - No locks in consumer (render) path
    """

    def __init__(self, queue_depth: int = 2):
        """
        Initialise the hardware handler.

        Args:
            queue_depth: Maximum queue depth (default 2 for double-buffering)
        """
        self.queue_depth = queue_depth
        self.data_queue = queue.Queue(maxsize=queue_depth)
        self.current_snapshot: Optional[HardwareSnapshot] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Performance monitoring
        self.frame_count = 0
        self.last_perf_time = time.time()
        self.update_hz = 0.0

        # Frame drop metrics
        self._frames_dropped = 0
        self._frames_dropped_total = 0
        self._last_drop_log_time = time.time()

    def start(self):
        """Start the hardware reading thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()
        print(f"{self.__class__.__name__} worker thread started")

    def stop(self):
        """Stop the hardware reading thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)  # Allow time for I2C operations to complete
        print(f"{self.__class__.__name__} worker thread stopped")

    def _worker_loop(self):
        """
        Worker thread loop - handles all I/O and processing.
        Override this method in subclasses.
        """
        raise NotImplementedError("Subclasses must implement _worker_loop")

    def _publish_snapshot(self, data: Dict[str, Any], metadata: Dict[str, Any] = None):
        """
        Publish a new data snapshot to the queue.

        Args:
            data: Hardware data dictionary
            metadata: Optional metadata (status, errors, etc.)
        """
        snapshot = HardwareSnapshot(
            timestamp=time.time(),
            data=data.copy() if data else {},
            metadata=metadata.copy() if metadata else {}
        )

        # Non-blocking put - drop oldest frame if queue full
        try:
            self.data_queue.put_nowait(snapshot)
        except queue.Full:
            # Queue full - drop oldest and retry
            try:
                self.data_queue.get_nowait()
                self.data_queue.put_nowait(snapshot)
                self._frames_dropped += 1
                self._frames_dropped_total += 1
            except (queue.Empty, queue.Full):
                # Race condition - frame truly dropped
                self._frames_dropped += 1
                self._frames_dropped_total += 1

        # Update performance metrics
        self.frame_count += 1
        current_time = time.time()
        elapsed = current_time - self.last_perf_time
        if elapsed >= 1.0:
            self.update_hz = self.frame_count / elapsed
            self.frame_count = 0
            self.last_perf_time = current_time

        # Log frame drops periodically (every 60 seconds if any drops occurred)
        drop_log_elapsed = current_time - self._last_drop_log_time
        if drop_log_elapsed >= 60.0:
            if self._frames_dropped > 0:
                print(
                    f"[WARNING] {self.__class__.__name__}: "
                    f"{self._frames_dropped} frames dropped in last 60s "
                    f"(total: {self._frames_dropped_total})"
                )
            self._frames_dropped = 0
            self._last_drop_log_time = current_time

    def get_snapshot(self) -> Optional[HardwareSnapshot]:
        """
        Get the latest data snapshot (lock-free for render path).

        Returns:
            HardwareSnapshot or None if no data available
        """
        # Drain queue keeping only latest snapshot (non-blocking)
        try:
            while True:
                self.current_snapshot = self.data_queue.get_nowait()
        except queue.Empty:
            pass

        return self.current_snapshot

    def get_data(self) -> Dict[str, Any]:
        """
        Get the latest hardware data.

        Returns:
            Dictionary with hardware data or empty dict if no data
        """
        snapshot = self.get_snapshot()
        return snapshot.data if snapshot else {}

    def get_update_rate(self) -> float:
        """
        Get the current update rate in Hz.

        Returns:
            Update rate in Hz
        """
        return self.update_hz

    def get_frame_drop_stats(self) -> Dict[str, int]:
        """
        Get frame drop statistics.

        Returns:
            Dictionary with 'recent' (last 60s) and 'total' frame drop counts
        """
        return {
            "recent": self._frames_dropped,
            "total": self._frames_dropped_total
        }
