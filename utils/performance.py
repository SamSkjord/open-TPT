"""
Performance monitoring utilities for openTPT.
Tracks render loop timing, hardware update rates, and validates performance targets.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import statistics


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot."""
    timestamp: float
    render_time_ms: float
    fps: float
    frame_time_ms: float
    hardware_update_rates: Dict[str, float] = field(default_factory=dict)
    thermal_processing_times: Dict[str, float] = field(default_factory=dict)


class PerformanceMonitor:
    """
    Monitor and validate performance against system plan targets.

    Performance targets from system plan:
    - Render loop: ≤ 12 ms/frame (30-60 FPS)
    - Thermal zones: < 1 ms/frame/sensor
    - Radar parse: < 3 ms for 40 objects
    - CAN scheduler: < 10% CPU for 4 buses
    - Camera → display: < 80 ms median
    - Log writer: < 10 ms/s avg
    """

    def __init__(self, history_size: int = 100):
        """
        Initialize performance monitor.

        Args:
            history_size: Number of samples to keep for statistics
        """
        self.history_size = history_size

        # Timing history (ring buffers)
        self.render_times = deque(maxlen=history_size)
        self.frame_times = deque(maxlen=history_size)

        # Current measurement
        self.last_frame_time = time.perf_counter()
        self.render_start_time = None

        # FPS calculation
        self.frame_count = 0
        self.fps_calc_start = time.time()
        self.current_fps = 0.0

        # Hardware update rates
        self.hardware_update_rates = {}

        # Thermal processing times
        self.thermal_processing_times = {}

        # Performance warnings
        self.warnings = deque(maxlen=10)

    def start_render(self):
        """Mark the start of a render cycle."""
        self.render_start_time = time.perf_counter()

    def end_render(self):
        """Mark the end of a render cycle and record metrics."""
        if self.render_start_time is None:
            return

        current_time = time.perf_counter()

        # Calculate render time
        render_time_ms = (current_time - self.render_start_time) * 1000.0
        self.render_times.append(render_time_ms)

        # Calculate frame time (time since last frame)
        frame_time_ms = (current_time - self.last_frame_time) * 1000.0
        self.frame_times.append(frame_time_ms)
        self.last_frame_time = current_time

        # Update FPS
        self.frame_count += 1
        elapsed = time.time() - self.fps_calc_start
        if elapsed >= 1.0:
            self.current_fps = self.frame_count / elapsed
            self.frame_count = 0
            self.fps_calc_start = time.time()

        # Check for performance warnings
        self._check_performance_targets(render_time_ms, frame_time_ms)

        self.render_start_time = None

    def _check_performance_targets(self, render_time_ms: float, frame_time_ms: float):
        """Check if performance targets are being met."""
        # Target: ≤ 12 ms/frame
        if render_time_ms > 12.0:
            self.warnings.append({
                "timestamp": time.time(),
                "type": "RENDER_SLOW",
                "value": render_time_ms,
                "target": 12.0,
                "message": f"Render time {render_time_ms:.2f}ms exceeds target 12ms"
            })

        # Target: 30-60 FPS (16.67-33.33 ms/frame)
        if frame_time_ms > 33.33:
            self.warnings.append({
                "timestamp": time.time(),
                "type": "FPS_LOW",
                "value": 1000.0 / frame_time_ms,
                "target": 30.0,
                "message": f"FPS {1000.0/frame_time_ms:.1f} below target 30"
            })

    def update_hardware_rate(self, handler_name: str, rate_hz: float):
        """
        Update hardware handler update rate.

        Args:
            handler_name: Name of hardware handler
            rate_hz: Update rate in Hz
        """
        self.hardware_update_rates[handler_name] = rate_hz

    def update_thermal_processing_time(self, position: str, time_ms: float):
        """
        Update thermal processing time.

        Args:
            position: Tyre position
            time_ms: Processing time in ms
        """
        self.thermal_processing_times[position] = time_ms

        # Target: < 1 ms/frame/sensor
        if time_ms > 1.0:
            self.warnings.append({
                "timestamp": time.time(),
                "type": "THERMAL_SLOW",
                "value": time_ms,
                "target": 1.0,
                "message": f"Thermal processing {position} {time_ms:.2f}ms exceeds target 1ms"
            })

    def get_current_metrics(self) -> PerformanceMetrics:
        """
        Get current performance metrics.

        Returns:
            PerformanceMetrics snapshot
        """
        return PerformanceMetrics(
            timestamp=time.time(),
            render_time_ms=self.get_avg_render_time(),
            fps=self.current_fps,
            frame_time_ms=self.get_avg_frame_time(),
            hardware_update_rates=self.hardware_update_rates.copy(),
            thermal_processing_times=self.thermal_processing_times.copy()
        )

    def get_avg_render_time(self) -> float:
        """Get average render time in ms."""
        if not self.render_times:
            return 0.0
        return statistics.mean(self.render_times)

    def get_max_render_time(self) -> float:
        """Get maximum render time in ms."""
        if not self.render_times:
            return 0.0
        return max(self.render_times)

    def get_avg_frame_time(self) -> float:
        """Get average frame time in ms."""
        if not self.frame_times:
            return 0.0
        return statistics.mean(self.frame_times)

    def get_percentile_render_time(self, percentile: float) -> float:
        """
        Get percentile render time.

        Args:
            percentile: Percentile (0-100)

        Returns:
            Render time at percentile
        """
        if not self.render_times:
            return 0.0
        sorted_times = sorted(self.render_times)
        index = int(len(sorted_times) * percentile / 100.0)
        return sorted_times[min(index, len(sorted_times) - 1)]

    def get_warnings(self) -> List[Dict]:
        """Get recent performance warnings."""
        return list(self.warnings)

    def clear_warnings(self):
        """Clear performance warnings."""
        self.warnings.clear()

    def get_performance_summary(self) -> str:
        """
        Get formatted performance summary.

        Returns:
            Multi-line string with performance statistics
        """
        lines = [
            "=== Performance Summary ===",
            f"FPS: {self.current_fps:.1f}",
            f"Render Time: avg={self.get_avg_render_time():.2f}ms, "
            f"max={self.get_max_render_time():.2f}ms, "
            f"p95={self.get_percentile_render_time(95):.2f}ms, "
            f"p99={self.get_percentile_render_time(99):.2f}ms",
            f"Frame Time: avg={self.get_avg_frame_time():.2f}ms",
            "",
            "Hardware Update Rates:",
        ]

        for name, rate in self.hardware_update_rates.items():
            lines.append(f"  {name}: {rate:.1f} Hz")

        if self.thermal_processing_times:
            lines.append("")
            lines.append("Thermal Processing Times:")
            for pos, time_ms in self.thermal_processing_times.items():
                status = "✓" if time_ms < 1.0 else "⚠"
                lines.append(f"  {pos}: {time_ms:.3f}ms {status}")

        warnings = self.get_warnings()
        if warnings:
            lines.append("")
            lines.append(f"Performance Warnings ({len(warnings)}):")
            for warning in list(warnings)[-5:]:  # Last 5 warnings
                lines.append(f"  {warning['type']}: {warning['message']}")

        lines.append("=" * 30)
        return "\n".join(lines)

    def is_meeting_targets(self) -> bool:
        """
        Check if all performance targets are being met.

        Returns:
            True if all targets met
        """
        # Check render time target
        if self.get_avg_render_time() > 12.0:
            return False

        # Check FPS target
        if self.current_fps < 30.0:
            return False

        # Check thermal processing targets
        for time_ms in self.thermal_processing_times.values():
            if time_ms > 1.0:
                return False

        return True


# Global performance monitor instance
_global_monitor: Optional[PerformanceMonitor] = None


def get_global_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor
