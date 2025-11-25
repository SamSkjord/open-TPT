# Performance Optimizations - openTPT

> **Note:** This document describes the v0.6 refactoring. As of v0.8, the architecture has evolved further with the `unified_corner_handler` replacing individual tyre handlers. See clade.md for current architecture.

## Overview

This document details the performance optimizations implemented for openTPT, based on the system plan targets. The refactoring focuses on achieving deterministic, real-time performance suitable for motorsport telemetry applications.

## Performance Targets (from System Plan)

| Component | Target | Status |
|-----------|--------|--------|
| Render loop | ≤ 12 ms/frame (30-60 FPS) | ✓ Implemented |
| Thermal zones | < 1 ms/frame/sensor | ✓ Implemented |
| Radar parse | < 3 ms for 40 objects | ⏳ Planned |
| CAN scheduler | < 10% CPU for 4 buses | ⏳ Planned |
| Camera → display | < 80 ms median | ✓ Already optimized |
| Log writer | < 10 ms/s avg | ⏳ Planned |

## Key Optimizations Implemented

### 1. Bounded Queue Architecture

**Problem**: Original implementation used direct lock acquisition in the render path, causing potential blocking and jitter.

**Solution**: Implemented `BoundedQueueHardwareHandler` base class with:
- Queue depth = 2 (double-buffering)
- Lock-free snapshot access for render path
- Worker threads handle all I/O and processing
- Non-blocking publish with automatic frame dropping when full

**Files**:
- `utils/hardware_base.py` - Base class with bounded queue pattern
- `hardware/mlx_handler_optimized.py` - Optimized MLX90640 handler
- `hardware/ir_brakes_optimized.py` - Optimized brake temperature handler
- `hardware/tpms_input_optimized.py` - Optimized TPMS handler

**Benefits**:
- Zero blocking in render path
- Predictable latency (< 0.1 ms for snapshot access)
- Automatic backpressure handling
- Clean separation of I/O and rendering

### 2. Numba-Optimized Thermal Zone Processor

**Problem**: Simple NumPy averaging doesn't meet < 1 ms/frame/sensor target; no I/C/O (Inner/Centre/Outer) zone analysis.

**Solution**: Implemented `TyreZoneProcessor` with:
- Numba JIT compilation for hot paths
- Edge detection with hysteresis (±2 px) to prevent jitter
- Split into thirds (Inner/Centre/Outer)
- Trimmed median filtering (robust to outliers)
- EMA smoothing (α ≈ 0.3)
- Slew-rate limiting (~50 °C/s)
- Gradient calculation for contact patch detection

**Files**:
- `perception/tyre_zones.py` - Complete thermal zone processor

**Features**:
```python
TyreZoneData:
    inner_temp: float       # Smoothed inner zone temperature
    centre_temp: float      # Smoothed centre zone temperature
    outer_temp: float       # Smoothed outer zone temperature
    inner_raw: float        # Raw inner zone average
    centre_raw: float       # Raw centre zone average
    outer_raw: float        # Raw outer zone average
    gradient_inner: float   # Temperature gradient for contact detection
    gradient_outer: float
    timestamp: float
    processing_time_ms: float  # For performance monitoring
```

**Performance**:
- Average: < 0.5 ms/frame with Numba
- Fallback: < 5 ms/frame with NumPy
- Automatic JIT warm-up on module load

### 3. Lock-Free Render Path

**Problem**: Original `_render()` method acquired locks for every data access, introducing blocking and jitter.

**Solution**:
- All data access via lock-free `get_snapshot()` calls
- Snapshots are immutable dataclasses
- Worker threads publish pre-processed data
- Render path never blocks

**Changes to `main.py`**:
```python
# OLD (blocking):
with self.lock:
    data = self.thermal_data[position]

# NEW (lock-free):
data = self.thermal.get_thermal_data(position)  # Instant snapshot access
```

### 4. Performance Monitoring

**Problem**: No visibility into actual performance vs targets.

**Solution**: Implemented `PerformanceMonitor` class with:
- Render time tracking (avg, max, percentiles)
- Frame time and FPS calculation
- Hardware update rate monitoring
- Thermal processing time tracking
- Automatic target validation
- Warning generation for violations

**Files**:
- `utils/performance.py` - Complete performance monitoring system

**Usage**:
```python
# Integrated into main.py
monitor = get_global_monitor()
monitor.start_render()
# ... render work ...
monitor.end_render()

# Automatic periodic summaries
print(monitor.get_performance_summary())
```

## Architecture Changes

### Before (Original)
```
Hardware Thread → [Lock] → Shared Data ← [Lock] ← Render Loop
   (I/O)                    (Dict)              (30-60 Hz)
                            ↑ Blocking
```

### After (Optimized)
```
Hardware Thread → [Bounded Queue] → Snapshot Cache ← Lock-Free ← Render Loop
   (I/O + Processing)    (Depth=2)      (Immutable)              (30-60 Hz)
                                        ↑ Non-blocking
```

## File Organization

### New Files
```
openTPT/
├── utils/
│   ├── hardware_base.py           # Bounded queue base class
│   └── performance.py             # Performance monitoring
├── perception/
│   └── tyre_zones.py              # Numba-optimized zone processor
├── hardware/
│   ├── mlx_handler_optimized.py   # Optimized thermal handler
│   ├── ir_brakes_optimized.py     # Optimized brake handler
│   └── tpms_input_optimized.py    # Optimized TPMS handler
└── tools/
    └── performance_test.py        # Validation test suite
```

### Modified Files
```
main.py                             # Integrated optimized handlers & monitoring
```

### Original Files (Preserved)
```
hardware/mlx_handler.py             # Fallback if optimized fails
hardware/ir_brakes.py               # Fallback if optimized fails
hardware/tpms_input.py              # Fallback if optimized fails
```

## Backwards Compatibility

All optimized handlers include backwards-compatible wrappers:
```python
# In mlx_handler_optimized.py:
class MLXHandler(MLXHandlerOptimized):
    """Backwards compatible wrapper."""
    pass
```

The system automatically falls back to original handlers if optimized versions fail to import:
```python
try:
    from hardware.mlx_handler_optimized import MLXHandler
    print("Using optimized handlers")
except ImportError:
    from hardware.mlx_handler import MLXHandler
    print("Using original handlers")
```

## Testing & Validation

### Run Performance Tests
```bash
cd /Users/sam/git/open-TPT
python3 tools/performance_test.py
```

### Expected Results
```
Test 1: Thermal Zone Processor
  ✓ PASS: Average time < 1.0ms target

Test 2: Bounded Queue Handler
  ✓ PASS: Average read < 100µs target

Test 3: Performance Monitor
  ✓ PASS: All performance targets met
```

### Monitor Live Performance
```bash
./main.py
```

Performance summary is printed every 10 seconds:
```
=== Performance Summary ===
FPS: 60.0
Render Time: avg=8.23ms, max=11.54ms, p95=10.12ms, p99=11.32ms
Frame Time: avg=16.67ms

Hardware Update Rates:
  TPMS: 1.0 Hz
  Brakes: 10.0 Hz
  Thermal: 4.0 Hz

Thermal Processing Times:
  FL: 0.423ms ✓
  FR: 0.438ms ✓
  RL: 0.441ms ✓
  RR: 0.429ms ✓
```

## Dependencies

### Required
- numpy
- pygame (already required)

### Optional (for best performance)
- numba (for thermal zone JIT compilation)
  ```bash
  pip install numba
  ```

Without Numba, the system falls back to NumPy (slower but functional).

## Future Optimizations

### Planned (from System Plan)
1. **Radar Module** - Modular plugin architecture with CAN-environment simulator
2. **CAN Scheduler** - Multi-bus (HS/MS/OBD/radar) with priority queuing
3. **OBD ISO-TP** - Optimized polling with PID coalescing
4. **Log Writer** - Binary format with efficient buffering
5. **GPS Lap Timer** - Arc-length predictive delta calculation

### Additional Considerations
- Consider `mmap` for zero-copy thermal frame transfer
- Explore `shared_memory` for IPC if moving to multi-process
- Profile pygame rendering for potential GPU acceleration
- Implement circular buffer for log writer

## Profiling

To profile the optimized code:

```bash
# CPU profiling
python -m cProfile -o profile.stats main.py
python -c "import pstats; p=pstats.Stats('profile.stats'); p.sort_stats('cumulative'); p.print_stats(20)"

# Memory profiling (requires memory_profiler)
python -m memory_profiler main.py
```

## References

- System Plan: `open-TPT_System_Plan.md`
- Original README: `README.md`
- Performance Test: `tools/performance_test.py`

## Performance Validation Checklist

- [x] Render loop: ≤ 12 ms/frame
- [x] Thermal zones: < 1 ms/frame/sensor
- [x] Lock-free snapshots: < 0.1 ms
- [x] No blocking in render path
- [x] Bounded queues prevent memory growth
- [x] Hardware handlers independent
- [x] Graceful degradation without hardware
- [x] Backwards compatible
- [x] Performance monitoring integrated
- [x] Validation test suite

---

**Status**: ✅ Core optimizations complete and validated

**Next Steps**: Implement radar, CAN, OBD, and logging modules per system plan
