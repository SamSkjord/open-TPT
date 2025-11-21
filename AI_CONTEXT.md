# AI Assistant Context - openTPT Project

**Purpose:** This document provides essential context for AI assistants working on the openTPT project, enabling quick onboarding and effective collaboration.

**Last Updated:** 2025-11-20 (v0.10)

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

### Hardware Status (v0.10)
- ✅ **TPMS:** 4/4 sensors auto-paired (FL, FR, RL, RR)
- ✅ **Multi-Camera:** Dual USB cameras with seamless switching
  - Rear camera: `/dev/video-rear` (USB port 1.1)
  - Front camera: `/dev/video-front` (USB port 1.2)
- ✅ **NeoKey 1x4:** Physical control buttons working
- ✅ **Pico Thermal:** 1/4 MLX90640 connected (FL)
- ✅ **Toyota Radar:** Enabled by default, receives 1-3 tracks
  - CAN channels: can_b1_0 (keep-alive), can_b1_1 (tracks)
- ✅ **OBD2:** MAP-based SOC simulation for desk testing
- ⚠️ **ADS1115:** Not connected (brake temps unavailable)

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
│   ├── unified_corner_handler.py    # Unified handler for all tyre sensors
│   ├── tpms_input_optimized.py      # TPMS with bounded queues
│   ├── mlx90614_handler.py          # MLX90614 single-point IR
│   ├── radar_handler.py             # Toyota radar handler (bounded queues)
│   ├── toyota_radar_driver.py       # Toyota radar CAN driver
│   ├── obd2_handler.py              # OBD2 speed and MAP-based SOC
│   └── i2c_mux.py                   # TCA9548A control
├── utils/
│   ├── config.py            # ALL configuration constants
│   ├── hardware_base.py     # Bounded queue base class
│   └── performance.py       # Performance monitoring
├── config/
│   ├── camera/
│   │   └── 99-camera-names.rules    # Camera udev rules
│   └── can/
│       └── 80-can-persistent-names.rules  # CAN udev rules
├── opendbc/
│   ├── toyota_prius_2017_adas.dbc          # Toyota radar DBC
│   └── toyota_prius_2017_pt_generated.dbc  # Powertrain DBC
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
# SSH to Pi and update via git
ssh pi@192.168.199.243
cd /home/pi/open-TPT
git pull
sudo ./install.sh  # If dependencies changed

# Quick sync (code only, for development)
./tools/quick_sync.sh pi@192.168.199.243

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

# Radar (enabled by default)
RADAR_ENABLED = True
RADAR_CHANNEL = "can_b1_1"  # Radar track output
CAR_CHANNEL = "can_b1_0"    # Keep-alive messages
RADAR_DBC = "opendbc/toyota_prius_2017_adas.dbc"
CONTROL_DBC = "opendbc/toyota_prius_2017_pt_generated.dbc"

# OBD2 (for speed and MAP-based SOC)
OBD_ENABLED = True
OBD_CHANNEL = "can_b2_1"
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

## Toyota Radar Overlay System (v0.10)

### Architecture
- **Toyota radar CAN integration** for collision warnings on rear camera
- **Bounded queue architecture** for lock-free render access (depth=2)
- **Track detection** displays 1-3 nearest vehicles within 120m
- **Color-coded chevrons** (3x larger, solid-filled for visibility)
- **Overtake warnings** with blue side arrows

### CAN Bus Configuration
- **can_b1_0**: Car keep-alive messages (TX from Pi to radar)
- **can_b1_1**: Radar track output (RX from radar to Pi, ~320 Hz)
- **Waveshare Dual CAN HAT** (Board 1) for dual-bus communication
- **DBC files** for message decoding (opendbc/ directory)

### Chevron Color Coding
- 🟢 **Green**: Vehicle detected, safe distance (<10 km/h closing)
- 🟡 **Yellow**: Moderate closing speed (10-20 km/h)
- 🔴 **Red**: Rapid approach (>20 km/h closing speed)
- 🔵 **Blue side arrows**: Overtaking vehicle warning

### Track Processing
- **Track merging**: Combines nearby tracks within 1m radius
- **Timeout**: 0.5s for stale track removal
- **Display**: 3 nearest tracks within 120m range
- **FOV**: 106° horizontal field of view

### Key Files
- `hardware/toyota_radar_driver.py` - CAN driver with keep-alive (lines 1-500+)
- `hardware/radar_handler.py` - Bounded queue handler (lines 1-250+)
- `gui/radar_overlay.py` - Chevron rendering (lines 1-358)
- `utils/config.py` - Radar configuration (lines 300-337)
- `opendbc/*.dbc` - Message definitions

### Critical Configuration Notes
- **auto_setup=False**: CAN interfaces managed by systemd, not application
- **Radar enabled by default**: RADAR_ENABLED = True in config
- **Correct channel assignment**: can_b1_1 for tracks (RX), can_b1_0 for keep-alive (TX)
- **3x larger chevrons**: 120×108px (was 40×36px), solid-filled

### Dependencies
```bash
pip3 install --break-system-packages cantools  # DBC parsing
```

---

## OBD2 & Status Bar System (v0.9)

### Architecture
- **Application-level status bars** visible on all pages (top/bottom)
- **MAP-based SOC simulation** for desk testing without vehicle
- **Direct MAP-to-SOC conversion** for instant updates
- **Dynamic color coding** for charge/discharge state

### Status Bar Features
- **Top bar**: Battery SOC with color zones (green/yellow/red)
- **Bottom bar**: Lap delta time display (future feature)
- **Always visible**: Rendered on ALL pages, not just G-meter

### OBD2 Configuration
- **CAN channel**: can_b2_1 (Board 2, CAN_1 connector)
- **PIDs**: 0x0D (speed), 0x0B (manifold absolute pressure)
- **MAP history**: 3 samples for fast response
- **SOC calculation**: Increasing MAP = discharging, decreasing MAP = charging

### Key Files
- `main.py` - Application-level status bar management (lines 1-1000+)
- `hardware/obd2_handler.py` - OBD2 handler with MAP reading (lines 1-300+)
- `ui/widgets/horizontal_bar.py` - Status bar widget (lines 1-150+)

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

### Issue: Radar Not Receiving Tracks
**Solution:**
- Check CAN channels: can_b1_1 for tracks (RX), can_b1_0 for keep-alive (TX)
- Verify cantools installed: `pip3 install --break-system-packages cantools`
- Check DBC files exist in opendbc/ directory
- Ensure auto_setup=False (systemd manages CAN interfaces)
- Test CAN activity: `ssh pi@IP 'timeout 3 candump can_b1_1 | wc -l'`
- Look for "Radar: Receiving N tracks" in logs

### Issue: Radar Import Errors
**Solution:**
- Import path should be: `from hardware.toyota_radar_driver import ...`
- Not: `from toyota_radar_driver import ...`
- Check radar_handler.py:20 for correct import statement

### Issue: Brake Temperatures Seem Wrong
**Solution:**
- Check emissivity configuration in utils/config.py BRAKE_ROTOR_EMISSIVITY
- Verify rotor material type (oxidised cast iron = 0.95, machined = 0.60-0.70)
- Polished/clean rotors have much lower emissivity and will read significantly lower
- Using wrong emissivity can cause 5-20°C error in readings
- Emissivity correction applied in unified_corner_handler.py lines 460-465 and 493-498

### Issue: Status Bars Not Visible
**Solution:**
- Check STATUS_BAR_ENABLED = True in utils/config.py
- Status bars managed in main.py (not gmeter.py anymore)
- Verify OBD2 handler initialized if using MAP-based SOC
- Check logs for OBD2 connection status

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

## Brake Temperature Emissivity Correction

### Overview
All IR sensors (MLX90614 and ADC-based IR sensors) have factory default emissivity of 1.0, which assumes a perfect black body. Since brake rotors have lower emissivity (typically 0.95 for oxidised cast iron), the sensors read lower than actual temperature. openTPT applies software emissivity correction to compensate.

### Configuration Location
- **Config file:** `utils/config.py` lines 469-496
- **Correction function:** `apply_emissivity_correction()` at lines 148-187
- **Applied in:** `hardware/unified_corner_handler.py` lines 460-465 (ADC) and 493-498 (MLX90614)

### How It Works
1. MLX90614/IR sensor operates at factory default ε = 1.0 (not changed in hardware)
2. Actual brake rotor has ε = 0.95 (configurable per corner in BRAKE_ROTOR_EMISSIVITY)
3. Sensor reads lower than actual (less radiation from non-black-body surface)
4. Software correction adjusts upward: `T_actual = T_measured / ε^0.25` (Stefan-Boltzmann law)

### Typical Emissivity Values
- Cast iron (rusty/oxidised): 0.95 (default, most common)
- Cast iron (machined/clean): 0.60-0.70
- Steel (oxidised): 0.80
- Steel (polished): 0.15-0.25
- Ceramic composite: 0.90-0.95

### Configuration
```python
# In utils/config.py
BRAKE_ROTOR_EMISSIVITY = {
    "FL": 0.95,  # Adjust per corner to match rotor material
    "FR": 0.95,
    "RL": 0.95,
    "RR": 0.95,
}
```

### Important Notes
- The correction is applied automatically to ALL brake temperature readings (ADC and MLX90614)
- Using incorrect emissivity can result in temperature errors of 5-20°C
- **Tyre sensors handle emissivity differently:** MLX90640 sensors (via Pico firmware) have emissivity configured in the pico-tyre-temp firmware (default 0.95 for rubber) and apply it during MLX90640_CalculateTo() API call, NOT in openTPT Python code
- If user reports incorrect brake temperatures, check emissivity configuration first

### Tyre vs Brake Emissivity Handling
**Why the difference?**
- **Tyre sensors (MLX90640):** Emissivity configured in Pico firmware at `/Users/sam/git/pico-tyre-temp/main.c:36` (DEFAULT_EMISSIVITY = 0.95f for rubber). Applied via MLX90640 API parameter during temperature calculation. Configurable via I2C register 0x04.
- **Brake sensors (MLX90614/ADC):** Sensors operate at factory default ε = 1.0. Software correction applied in openTPT's unified_corner_handler.py after reading sensor. Configured via BRAKE_ROTOR_EMISSIVITY in utils/config.py.

Both achieve accurate temperatures - just different implementation points appropriate to each sensor architecture.

---

## Version History Quick Reference

### v0.10 (2025-11-20) - Toyota Radar Integration
- Toyota radar overlay enabled by default
- Real-time collision warnings on rear camera
- 3x larger solid-filled chevrons (120×108px)
- Track detection (1-3 vehicles within 120m)
- CAN channel configuration (can_b1_0/can_b1_1)
- DBC files for Toyota Prius 2017
- Overtake warnings with blue arrows
- Added cantools dependency

### v0.9 (2025-11-20) - Status Bars & OBD2
- Application-level status bars (visible on all pages)
- MAP-based SOC simulation for desk testing
- Direct MAP-to-SOC conversion (instant updates)
- Dynamic color coding for charge/discharge state
- Clean camera transitions (no stale frames)
- Correct front camera orientation (not mirrored)

### v0.8 (2025-11-19) - Multi-Camera Support
- Dual USB camera support with seamless switching
- Deterministic camera identification (udev rules)
- Smooth freeze-frame transitions
- Dual FPS counters
- Automated camera udev rules installation

### v0.7 (2025-11-13) - Radar Overlay (Initial)
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
→ SSH to Pi, `git pull`, optionally `sudo ./install.sh`, or use `./tools/quick_sync.sh`

### "Performance issue"
→ Check logs for performance summary, verify targets met, check for blocking

### "Radar not working"
→ Check CAN channels (can_b1_1 for tracks), verify cantools installed, check DBC files

### "Chevrons too small/hard to see"
→ Already fixed in v0.10: 3x larger (120×108px) and solid-filled

### "Status bars not showing"
→ Check STATUS_BAR_ENABLED in config, status bars now in main.py (v0.9+)

### "Brake temperatures reading low/high"
→ Check BRAKE_ROTOR_EMISSIVITY in utils/config.py, adjust per corner to match rotor material

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

**Version:** 0.10 (Toyota Radar Integration)
**Last Updated:** 2025-11-20
**Maintained by:** AI assistants working on openTPT
