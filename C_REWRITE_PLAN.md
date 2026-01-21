# Plan: Rewrite openTPT in C

## Overview

Rewrite the openTPT Python motorsport telemetry system (~15,000 lines across 80+ files) in pure C11 for improved performance. The new implementation will replicate the existing multi-threaded producer-consumer architecture with lock-free rendering at 60 FPS.

**Goals:** Reduce frame latency, faster startup, eliminate Python runtime overhead.

---

## Project Structure

```
opentpt-c/
├── CMakeLists.txt
├── include/
│   ├── opentpt/           # Core APIs (config, queue, handler, snapshot)
│   ├── hardware/          # Hardware handler APIs (12 modules)
│   └── gui/               # Display and menu APIs
├── src/
│   ├── core/              # main.c, app.c, init.c, render.c, events.c
│   ├── util/              # queue.c, settings.c, backoff.c, conversions.c
│   ├── hardware/          # All hardware handlers
│   └── gui/               # SDL2 rendering, pages, menu system
├── config/
│   └── config_defaults.h  # Generated from Python config.py
├── assets/                # Fonts, icons, themes (unchanged)
├── tests/                 # Unit and integration tests
└── tools/                 # config_gen.py, quick_sync.sh
```

---

## Core Architecture (C11 Equivalents)

| Python Pattern | C11 Implementation |
|----------------|-------------------|
| `BoundedQueueHardwareHandler` | `bounded_queue_handler_t` with function pointer vtable |
| `HardwareSnapshot(frozen=True)` | Immutable struct with reference counting |
| `queue.Queue(maxsize=2)` | Lock-free SPSC ring buffer (atomic head/tail) |
| `threading.Thread(daemon=True)` | pthreads with stop flag |
| `config.py` constants | `config_defaults.h` (generated) |
| `utils/settings.py` (JSON) | cJSON-based settings manager |
| pygame/SDL2 | SDL2 + SDL_ttf + SDL_image directly |

---

## Dependencies

| Library | Purpose |
|---------|---------|
| SDL2, SDL2_ttf, SDL2_image | Display rendering |
| pthreads | Threading |
| libi2c-dev | I2C bus access |
| SocketCAN (kernel) | CAN bus (OBD2, radar) |
| cJSON | JSON settings parsing |
| libjpeg-turbo | MJPEG camera decoding |

---

## Implementation Phases

### Phase 1: Core Framework
- CMake build system
- Lock-free SPSC queue (`src/util/queue.c`)
- Bounded queue handler base class pattern
- Hardware snapshot with reference counting
- Settings manager with cJSON
- Config generator script (`tools/config_gen.py`)
- Unit tests for queue and settings

**Key files to port:** `utils/hardware_base.py`, `config.py`, `utils/settings.py`

### Phase 2: Simple Hardware Handler (GPS)
- Serial port abstraction (termios)
- GPS handler with NMEA parsing
- Validate against Python version (compare lat/lon/speed)

**Key file to port:** `hardware/gps_handler.py`

### Phase 3: Basic Display
- SDL2 initialisation (KMS/DRM on Pi)
- Font rendering with SDL_ttf
- Basic telemetry page layout
- 60 FPS render loop with VSync

**Key files to port:** `gui/display.py`, `core/rendering.py`

### Phase 4: I2C Sensors
- I2C bus abstraction (`/dev/i2c-1`)
- TCA9548A multiplexer driver
- Pico I2C slave protocol (thermal frames)
- MLX90614, MCP9601, ADS1115 drivers
- Unified corner handler
- Thermal heatmap rendering (colour gradients)

**Key file to port:** `hardware/unified_corner_handler.py`

### Phase 5: CAN Bus
- SocketCAN abstraction
- OBD2 handler (PIDs, smoothing)
- Toyota radar handler (tracks, keep-alive)
- Radar overlay rendering

**Key files to port:** `hardware/obd2_handler.py`, `hardware/radar_handler.py`

### Phase 6: Camera & Input
- V4L2 camera capture (MJPEG)
- TPMS handler (wrap tpms_lib or rewrite)
- NeoDriver, OLED bonnet handlers
- Rotary encoder, NeoKey input

**Key files to port:** `gui/camera.py`, `hardware/tpms_input_optimized.py`

### Phase 7: Full UI
- Menu system (state machine with function pointers)
- All UI pages: G-meter, lap timing, fuel, CoPilot, pit timer
- Status bars, brightness control

**Key files to port:** `gui/menu/base.py`, all `gui/menu/*.py` mixins

### Phase 8: Integration & Polish
- Full integration testing
- Memory leak analysis (Valgrind)
- Performance profiling and optimisation
- Documentation

---

## Key Design Decisions

### Lock-Free SPSC Queue
```c
typedef struct spsc_queue {
    void** buffer;
    size_t capacity;
    _Alignas(64) atomic_size_t head;  // Producer
    _Alignas(64) atomic_size_t tail;  // Consumer
} spsc_queue_t;
```
Cache-line aligned to prevent false sharing. Queue depth = 2 (double-buffering).

### Handler Base Pattern
```c
typedef struct handler_vtable {
    void (*worker_loop)(void* self);
    void (*cleanup)(void* self);
} handler_vtable_t;

typedef struct bounded_queue_handler {
    const handler_vtable_t* vtable;
    pthread_t thread;
    volatile bool running;
    spsc_queue_t* queue;
    _Atomic(hardware_snapshot_t*) current_snapshot;
} bounded_queue_handler_t;
```
Function pointers provide polymorphism. Atomic snapshot swap for lock-free consumer access.

### Error Handling
Return error codes from all functions. Thread-local error context for diagnostics.

### Memory Management
Reference counting for snapshots. Pool allocation for hot paths. Valgrind validation.

---

## Critical Files to Reference

| Python File | Purpose |
|-------------|---------|
| `utils/hardware_base.py` | Threading pattern (BoundedQueueHardwareHandler, ExponentialBackoff) |
| `config.py` | All 1017 lines of constants |
| `hardware/unified_corner_handler.py` | Most complex handler (I2C mux, sensors, timeouts) |
| `gui/display.py` | Thermal heatmaps, colour gradients |
| `core/rendering.py` | Render loop, performance profiling |

---

## Verification

1. **Unit tests:** Queue operations, settings load/save, unit conversions
2. **Handler validation:** Run C and Python versions simultaneously, compare data output
3. **Visual comparison:** Screenshot comparison of telemetry pages
4. **Performance:** Frame time profiling (target <12ms), startup time comparison
5. **Stress testing:** 6+ hour runs, memory monitoring

---

## Build Commands

```bash
# Development (macOS)
mkdir build && cd build
cmake -DOPENTPT_MOCK_HARDWARE=ON ..
make -j$(nproc)
ctest

# Raspberry Pi
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j4
sudo ./opentpt --fullscreen
```

---

## Notes

- British English throughout (tyre, colour, initialise)
- No blocking operations in render path
- Graceful degradation when hardware missing (handler = NULL)
- Target: Pi 4/5 with 1024x600 Waveshare display
