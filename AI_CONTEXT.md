# AI Assistant Context - openTPT Project

**Purpose:** This document provides essential context for AI assistants working on the openTPT project, enabling quick onboarding and effective collaboration.

**Last Updated:** 2025-11-19 (v0.8)

---

## Project Overview

**openTPT** (Open Tyre Pressure and Temperature Telemetry) is a Raspberry Pi-based motorsport telemetry system for real-time monitoring of tyres, brakes, cameras, and optional radar overlay.

### Key Characteristics
- **Language:** Python 3.11+
- **Platform:** Raspberry Pi 4/5
- **Display:** Waveshare 1024x600 HDMI (scales from 800x480 reference)
- **Graphics:** SDL2/pygame with KMS/DRM
- **Architecture:** Multi-threaded with bounded queues, lock-free rendering
- **Performance Target:** 60 FPS, ≤12ms render time
- **Spelling:** **British English** throughout (Tyre, Optimised, Initialise, Colour, Centre)

---

## Current Production Environment

### Hardware Configuration
- **Pi IP Address:** `192.168.199.243`
- **User:** `pi`
- **Project Path:** `/home/pi/open-TPT`
- **Service:** `openTPT.service` (systemd, auto-start on boot)

### Hardware Status (v0.8)
- ✅ **TPMS:** 4/4 sensors auto-paired (FL, FR, RL, RR)
- ✅ **Multi-Camera:** Dual USB cameras with seamless switching
  - Rear camera: `/dev/video-rear` (USB port 1.1)
  - Front camera: `/dev/video-front` (USB port 1.2)
- ✅ **NeoKey 1x4:** Physical control buttons working
- ✅ **Pico Thermal:** 1/4 MLX90640 connected (FL)
- ⚠️ **ADS1115:** Not connected (brake temps unavailable)
- ⚠️ **Radar:** Optional, disabled by default

---

## Critical Conventions

### 1. British English - ALWAYS
**This is non-negotiable throughout the codebase:**
- ✅ **Tyre** (not Tire)
- ✅ **Optimised** (not Optimized)
- ✅ **Initialise** (not Initialize)
- ✅ **Colour** (not Color)
- ✅ **Centre** (not Center)
- ✅ **Metres** (not Meters)

### 2. File Editing Protocol
**CRITICAL:** Always read files before editing them:
```python
# REQUIRED workflow:
1. Read file with Read tool
2. Make changes with Edit tool (preserving exact indentation)
3. NEVER use Write tool on existing files (only for new files)
```

### 3. Code Style
- **Indentation:** Preserve exact tabs/spaces from Read tool output (ignore line number prefix)
- **Comments:** Use British English
- **Docstrings:** Triple-quoted, British spelling
- **Line length:** Reasonable, no hard limit

### 4. Hardware I/O
- All hardware access requires `sudo`
- Use bounded queues for hardware handlers
- Lock-free snapshots in render path
- No blocking operations in render loop

---

## Project Architecture

### Directory Structure
```
openTPT/
├── main.py                   # Application entry point
├── gui/
│   ├── display.py           # Rendering (pressure, temps, heatmaps)
│   ├── camera.py            # Multi-camera with radar overlay
│   ├── radar_overlay.py     # Radar visualization
│   ├── input.py             # NeoKey 1x4 controls
│   └── scale_bars.py        # Temperature/pressure scales
├── hardware/
│   ├── tpms_input_optimized.py      # TPMS with bounded queues
│   ├── ir_brakes_optimized.py       # Brake temps (EMA smoothing)
│   ├── pico_tyre_handler_optimized.py  # Pico MLX90640 handlers
│   ├── mlx90614_handler.py          # MLX90614 single-point IR
│   ├── radar_handler.py             # Toyota radar (optional)
│   └── i2c_mux.py                   # TCA9548A control
├── perception/
│   └── tyre_zones.py        # Numba-optimised thermal processing
├── utils/
│   ├── config.py            # ALL configuration constants
│   ├── hardware_base.py     # Bounded queue base class
│   └── performance.py       # Performance monitoring
├── config/
│   ├── camera/
│   │   └── 99-camera-names.rules    # Camera udev rules
│   └── can/
│       └── 80-can-persistent-names.rules  # CAN udev rules
└── assets/
    ├── overlay.png          # UI overlay
    └── icons/               # Status icons
```

### Key Design Patterns

**1. Bounded Queue Architecture**
```python
# Hardware handlers extend BoundedQueueHardwareHandler
# Producer thread: polls hardware, publishes snapshots
# Consumer (render): lock-free snapshot access via get_snapshot()
# Queue depth = 2 (double-buffering)
```

**2. Lock-Free Rendering**
```python
# Render path NEVER blocks on I/O
# All data access via immutable snapshots
# Target: ≤12ms per frame
```

**3. Graceful Degradation**
```python
# Try/except imports for optional features
# Mock data when hardware unavailable
# System works with partial sensors
```

---

## Common Development Tasks

### Deploying Changes
```bash
# From Mac to Pi
./deploy_to_pi.sh pi@192.168.199.243           # Full deployment
./tools/quick_sync.sh pi@192.168.199.243       # Quick sync (code only)

# Auto-deploy on save (requires fswatch)
fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@192.168.199.243
```

### Testing on Pi
```bash
ssh pi@192.168.199.243
cd /home/pi/open-TPT
sudo ./main.py                    # Fullscreen mode
sudo ./main.py --windowed         # Windowed mode
```

### Service Management
```bash
ssh pi@192.168.199.243
sudo systemctl status openTPT.service      # Check status
sudo systemctl restart openTPT.service     # Restart
sudo journalctl -u openTPT.service -f      # View logs
```

---

## Configuration System

### Primary Config File: `utils/config.py`

**Contains:**
- Display settings and scaling factors
- Hardware I2C addresses
- Sensor type selection (per tyre/brake)
- Temperature/pressure thresholds
- Camera configuration
- Radar settings (optional)
- All UI positions (auto-scaled)

**Example Configuration Blocks:**
```python
# Multi-camera
CAMERA_REAR_ENABLED = True
CAMERA_FRONT_ENABLED = True
CAMERA_REAR_DEVICE = "/dev/video-rear"
CAMERA_FRONT_DEVICE = "/dev/video-front"

# Per-tyre sensor types
TYRE_SENSOR_TYPES = {
    "FL": "pico",      # MLX90640 thermal camera
    "FR": "pico",
    "RL": "mlx90614",  # Single-point IR
    "RR": "mlx90614",
}

# Radar (optional)
RADAR_ENABLED = False  # Disabled by default
RADAR_CHANNEL = "can0"
RADAR_DBC = "opendbc/toyota_prius_2017_adas.dbc"
```

### Display Config: `display_config.json`
```json
{
  "width": 1024,
  "height": 600,
  "notes": "Waveshare display resolution"
}
```

### Udev Rules (Auto-installed by install.sh)
- `/etc/udev/rules.d/99-camera-names.rules` - Camera device naming
- `/etc/udev/rules.d/80-can-persistent-names.rules` - CAN interface naming

---

## Multi-Camera System (v0.8)

### Architecture
- **Two independent USB cameras** (rear and front)
- **Deterministic identification** via udev rules based on USB port
- **Seamless switching** with freeze-frame transitions (no checkerboard)
- **Resource management:** Only one camera initialized at a time
- **Radar overlay:** Only on rear camera

### Camera Switching Flow
1. Save last frame for smooth transition
2. Stop current camera capture thread
3. Release old camera device
4. Switch to new camera
5. Restore saved frame (prevents checkerboard)
6. Initialize new camera
7. Start capture thread

### Key Files
- `gui/camera.py` - Camera management and switching (lines 1-800+)
- `utils/config.py` - Camera configuration (lines 35-50)
- `config/camera/99-camera-names.rules` - Udev rules

### USB Port Mapping (Raspberry Pi 4)
- `1-1.1` = Top-left USB 2.0 port → `/dev/video-rear`
- `1-1.2` = Bottom-left USB 2.0 port → `/dev/video-front`

---

## Performance Optimization

### Targets (All Met in v0.6-v0.8)
- ✅ Render loop: ≤12ms/frame (achieved: ~8ms)
- ✅ Lock-free access: <100µs (achieved: ~6µs, 16x better)
- ✅ Thermal processing: <1ms/sensor (achieved: ~0.5-1.5ms)
- ✅ FPS: 60 FPS target (achieved: 60-62.5 FPS)

### Key Optimizations
1. **Bounded Queues:** Lock-free data snapshots
2. **Numba JIT:** Thermal zone processing (10x speedup on x86, 2x on ARM)
3. **EMA Smoothing:** Noise reduction in all sensors
4. **Slew-Rate Limiting:** Prevents unrealistic jumps

### Performance Monitoring
```python
# Automatic performance summary every 10 seconds:
# - FPS and render times
# - Hardware update rates
# - Thermal processing times
# - Warnings if targets exceeded
```

---

## Common Patterns

### Adding New Hardware Handler
```python
from utils.hardware_base import BoundedQueueHardwareHandler
from dataclasses import dataclass
from typing import Optional

@dataclass
class MyDataSnapshot:
    """Immutable snapshot of sensor data."""
    value: float
    timestamp: float

class MyHardwareHandler(BoundedQueueHardwareHandler):
    """Handler for my hardware with bounded queue."""

    def __init__(self):
        super().__init__(queue_depth=2)
        self._initialise()

    def _initialise(self):
        """Initialise hardware connection."""
        try:
            # Setup hardware
            self.sensor = MySensor()
        except Exception as e:
            print(f"Hardware unavailable: {e}")
            self.sensor = None

    def _poll_loop(self):
        """Background thread polls hardware."""
        while self._running:
            if self.sensor:
                value = self.sensor.read()
                snapshot = MyDataSnapshot(
                    value=value,
                    timestamp=time.time()
                )
                self._publish_snapshot(snapshot)
            time.sleep(0.1)  # Poll rate

    def get_snapshot(self) -> Optional[MyDataSnapshot]:
        """Lock-free snapshot access for render path."""
        return self._get_snapshot()
```

### Adding Configuration
```python
# In utils/config.py, group related settings:

# ==============================================================================
# My New Feature Configuration
# ==============================================================================

MY_FEATURE_ENABLED = True
MY_FEATURE_THRESHOLD = 42.0
MY_FEATURE_POSITIONS = {
    "FL": scale_position((100, 200)),
    "FR": scale_position((200, 200)),
}
```

### Updating Documentation
When adding features:
1. Update `README.md` (overview and configuration)
2. Update `CHANGELOG.md` (new version entry with details)
3. Update `QUICKSTART.md` (if affects daily use)
4. Update `utils/config.py` (inline comments for new settings)

---

## Troubleshooting Guide

### Issue: Camera Shows Checkerboard
**Solution:** Check camera switching implementation in `gui/camera.py`:
- Ensure old camera released before new camera initialized
- Verify freeze-frame saved before switching
- Check test pattern only generated when `self.frame is None`

### Issue: Import Errors
**Solution:**
- Check British spelling in imports/class names
- Verify optional imports wrapped in try/except
- Ensure graceful fallback to mock mode

### Issue: Blocking in Render Path
**Solution:**
- Use `_get_snapshot()` not direct data access
- Never acquire locks in render path
- All I/O in background threads

### Issue: GPIO/Hardware Access Denied
**Solution:**
```bash
# Always use sudo for hardware access
sudo ./main.py
```

### Issue: Performance Degradation
**Solution:**
- Check performance summary in logs
- Verify Numba installed: `pip3 list | grep numba`
- Look for blocking operations in render path
- Check thermal processing times

---

## Git Workflow

### Branch Strategy
- `main` - Production-ready code
- Feature branches for development
- No force-push to main

### Commit Messages
```bash
# Use British English in commit messages
git commit -m "Optimise thermal zone processing"  # ✅
git commit -m "Optimize thermal zone processing"  # ❌

# Be descriptive
git commit -m "Add dual camera support with udev rules"  # ✅
git commit -m "Camera stuff"  # ❌
```

### Before Committing
- [ ] Test in mock mode on Mac: `./main.py --windowed`
- [ ] Deploy to Pi and test with hardware
- [ ] Check British English spelling
- [ ] Update CHANGELOG.md if adding features
- [ ] Update relevant documentation

---

## Version History Quick Reference

### v0.8 (2025-11-19) - Multi-Camera Support
- Dual USB camera support with seamless switching
- Deterministic camera identification (udev rules)
- Smooth freeze-frame transitions
- Dual FPS counters
- Automated camera udev rules installation

### v0.7 (2025-11-13) - Radar Overlay
- Optional Toyota radar CAN integration
- Collision warning visualization
- Overtake detection
- Bounded queue radar handler
- Graceful degradation when unavailable

### v0.6 (2025-11-12) - Performance Refactoring
- Bounded queue architecture
- Lock-free rendering
- Numba-optimised thermal processing
- Performance monitoring
- British English throughout

---

## Quick Decision Matrix

### When to Use Which Tool

**Reading Files:**
- Single known file: `Read` tool
- Pattern matching: `Glob` then `Read`
- Content search: `Grep` for initial search, then `Read` matches
- Large file: `Read` with offset/limit

**Editing Files:**
- Existing file: `Read` first, then `Edit` (NEVER `Write`)
- New file: `Write`
- Multiple replacements: Multiple `Edit` calls or `replace_all=True`

**Executing Commands:**
- Terminal operations: `Bash` tool
- File operations: Use Read/Write/Edit tools (NOT cat/sed/awk in Bash)
- Git operations: `Bash` tool following git safety protocol

**Multi-Camera Changes:**
- Read `gui/camera.py` first (large file, may need offset/limit)
- Understand camera switching flow before modifying
- Test both cameras after changes
- Verify freeze-frame transition works

---

## Documentation Map

Quick reference for finding information:

| Need | Document |
|------|----------|
| Quick commands | `QUICKSTART.md` |
| Project overview | `README.md` |
| Latest changes | `CHANGELOG.md` |
| Deploy to Pi | `DEPLOYMENT.md` |
| CAN setup | `WAVESHARE_DUAL_CAN_HAT_SETUP.md` |
| Performance details | `PERFORMANCE_OPTIMIZATIONS.md` |
| Future planning | `open-TPT_System_Plan.md` |
| AI context | `AI_CONTEXT.md` (this file) |

---

## Common User Requests

### "Fix the camera switching"
→ Read `gui/camera.py`, check `switch_camera()` method, verify resource management

### "Update documentation"
→ Update relevant docs (README, CHANGELOG, QUICKSTART), ensure British English

### "Add new sensor"
→ Create handler extending `BoundedQueueHardwareHandler`, add config to `utils/config.py`

### "Deploy to Pi"
→ `./deploy_to_pi.sh pi@192.168.199.243` or `./tools/quick_sync.sh`

### "Performance issue"
→ Check logs for performance summary, verify targets met, check for blocking

---

## Testing Checklist

Before marking work complete:
- [ ] Code uses British English spelling
- [ ] No blocking operations in render path
- [ ] Hardware handlers use bounded queues
- [ ] Graceful degradation without hardware
- [ ] Documentation updated (README, CHANGELOG)
- [ ] Tested in mock mode on Mac
- [ ] Deployed and tested on Pi
- [ ] Performance targets met (check logs)
- [ ] Git commit message uses British English

---

## Contact Points

### Hardware
- All sensor access requires sudo
- I2C bus 1 for main devices
- TCA9548A multiplexer at 0x70
- Camera udev rules auto-installed by install.sh

### Software
- Main entry: `main.py`
- Config: `utils/config.py`
- Service: `/etc/systemd/system/openTPT.service`
- Logs: `sudo journalctl -u openTPT.service`

### Network
- Pi IP: `192.168.199.243`
- User: `pi`
- Project path: `/home/pi/open-TPT`
- Service name: `openTPT.service`

---

## Final Notes

1. **British English is non-negotiable** - Check every string, comment, and identifier
2. **Read before editing** - ALWAYS use Read tool before Edit tool
3. **Lock-free rendering** - Never block in render path
4. **Test on Pi** - Mock mode doesn't catch hardware issues
5. **Update docs** - Keep CHANGELOG and README current
6. **Use bounded queues** - All hardware handlers must extend base class
7. **Graceful degradation** - System works with missing hardware

**When in doubt:**
- Check existing code patterns
- Read the relevant documentation
- Ask the user for clarification
- Maintain British English spelling

---

**This document should be read at the start of every new session to maintain context and coding standards.**

**Version:** 0.8 (Multi-Camera)
**Last Updated:** 2025-11-19
**Maintained by:** AI assistants working on openTPT
