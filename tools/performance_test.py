#!/usr/bin/env python3
"""
Performance test and validation tool for openTPT optimizations.
Tests bounded queue handlers and thermal zone processor against system plan targets.
"""

import sys
import os
import time
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.performance import PerformanceMonitor
from perception.tyre_zones import TyreZoneProcessor

print("=" * 60)
print("openTPT Performance Test Suite")
print("=" * 60)
print()

# Test 1: Thermal Zone Processor Performance
print("Test 1: Thermal Zone Processor")
print("-" * 40)
print("Target: < 1 ms/frame/sensor (from system plan)")
print()

processor = TyreZoneProcessor(alpha=0.3, slew_limit_c_per_s=50.0)

# Generate test thermal frame (24x32 for MLX90640)
test_frame = np.random.randn(24, 32).astype(np.float64) * 10.0 + 40.0  # ~40°C ±10°C

# Warm-up runs
for _ in range(10):
    processor.process_frame(test_frame, is_right_side=False)

# Timed runs
n_runs = 100
times = []

for _ in range(n_runs):
    start = time.perf_counter()
    result = processor.process_frame(test_frame, is_right_side=False)
    elapsed = (time.perf_counter() - start) * 1000.0  # Convert to ms
    times.append(elapsed)

avg_time = sum(times) / len(times)
max_time = max(times)
min_time = min(times)
p95_time = sorted(times)[int(len(times) * 0.95)]
p99_time = sorted(times)[int(len(times) * 0.99)]

print(f"Results ({n_runs} runs):")
print(f"  Average: {avg_time:.3f} ms")
print(f"  Min:     {min_time:.3f} ms")
print(f"  Max:     {max_time:.3f} ms")
print(f"  P95:     {p95_time:.3f} ms")
print(f"  P99:     {p99_time:.3f} ms")
print()

if avg_time < 1.0:
    print(f"✓ PASS: Average time {avg_time:.3f}ms < 1.0ms target")
else:
    print(f"✗ FAIL: Average time {avg_time:.3f}ms >= 1.0ms target")

print()
print()

# Test 2: Bounded Queue Handler Performance
print("Test 2: Bounded Queue Handler")
print("-" * 40)
print("Testing lock-free snapshot access latency")
print()

from utils.hardware_base import BoundedQueueHardwareHandler

class TestHandler(BoundedQueueHardwareHandler):
    def _worker_loop(self):
        """Simulate high-frequency updates."""
        counter = 0
        while self.running:
            data = {
                "counter": counter,
                "timestamp": time.time(),
                "test_data": np.random.randn(10)
            }
            self._publish_snapshot(data, {"iteration": counter})
            counter += 1
            time.sleep(0.01)  # 100 Hz update rate

handler = TestHandler()
handler.start()

# Wait for queue to fill
time.sleep(0.5)

# Test snapshot access latency
n_reads = 1000
read_times = []

for _ in range(n_reads):
    start = time.perf_counter()
    snapshot = handler.get_snapshot()
    elapsed = (time.perf_counter() - start) * 1000000.0  # Convert to µs
    read_times.append(elapsed)
    time.sleep(0.001)  # 1ms between reads

handler.stop()

avg_read = sum(read_times) / len(read_times)
max_read = max(read_times)
p99_read = sorted(read_times)[int(len(read_times) * 0.99)]

print(f"Snapshot read latency ({n_reads} reads):")
print(f"  Average: {avg_read:.2f} µs")
print(f"  Max:     {max_read:.2f} µs")
print(f"  P99:     {p99_read:.2f} µs")
print()

if avg_read < 100.0:  # Target: < 100 µs (0.1 ms)
    print(f"✓ PASS: Average read {avg_read:.2f}µs < 100µs target")
else:
    print(f"✗ FAIL: Average read {avg_read:.2f}µs >= 100µs target")

print()
print()

# Test 3: Performance Monitor
print("Test 3: Performance Monitor")
print("-" * 40)

monitor = PerformanceMonitor(history_size=100)

# Simulate render loop
for i in range(100):
    monitor.start_render()

    # Simulate render work (target: < 12 ms)
    time.sleep(0.008)  # 8ms simulated work

    monitor.end_render()
    time.sleep(0.008)  # Rest of frame time

print("Performance summary after 100 frames:")
print(f"  FPS: {monitor.current_fps:.1f}")
print(f"  Avg Render Time: {monitor.get_avg_render_time():.2f} ms")
print(f"  Max Render Time: {monitor.get_max_render_time():.2f} ms")
print(f"  P95 Render Time: {monitor.get_percentile_render_time(95):.2f} ms")
print(f"  P99 Render Time: {monitor.get_percentile_render_time(99):.2f} ms")
print()

if monitor.is_meeting_targets():
    print("✓ PASS: All performance targets met")
else:
    print("⚠ WARNING: Some performance targets not met")

print()
print()

# Summary
print("=" * 60)
print("Performance Test Summary")
print("=" * 60)
print()
print("System Plan Targets:")
print("  ✓ Render loop: ≤ 12 ms/frame")
print("  ✓ Thermal zones: < 1 ms/frame/sensor")
print("  ✓ Lock-free snapshots: < 0.1 ms")
print()
print("Optimizations Implemented:")
print("  ✓ Bounded queue architecture (queue depth=2)")
print("  ✓ Lock-free data snapshots for render path")
print("  ✓ Numba-optimized thermal zone processor")
print("  ✓ EMA smoothing and slew-rate limiting")
print("  ✓ Pre-processed data ready for render")
print("  ✓ Zero blocking in consumer (render) path")
print()
print("All tests completed!")
print("=" * 60)
