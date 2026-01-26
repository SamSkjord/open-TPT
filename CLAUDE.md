# Claude Context - openTPT Project

**Version:** 0.19.11 | **Updated:** 2026-01-22

---

## Project Overview

**openTPT** (Open Tyre Pressure and Temperature Telemetry) - Raspberry Pi motorsport telemetry for real-time tyre, brake, camera, and radar monitoring.

| Attribute | Value |
|-----------|-------|
| Language | Python 3.11+ |
| Platform | Raspberry Pi 4/5 |
| Display | Waveshare 1024×600 HDMI |
| Graphics | SDL2/pygame with KMS/DRM |
| Architecture | Multi-threaded, bounded queues, lock-free rendering |
| Performance | 60 FPS, ≤12ms render time |
| **Spelling** | **British English throughout** |

---

## Critical Conventions

### British English - NON-NEGOTIABLE
| Use | Never |
|--------|---------|
| Tyre | Tire |
| Optimised | Optimized |
| Initialise | Initialize |
| Colour | Color |
| Centre | Center |

### Code Rules
1. **Always read files before editing** - Use Read tool, then Edit tool
2. **Never Write to existing files** - Only for new files
3. **Preserve indentation** - Match exact tabs/spaces from source
4. **Hardware requires sudo** - All I/O needs elevated privileges
5. **Lock-free rendering** - No blocking in render path
6. **Bounded queues** - All hardware handlers extend `BoundedQueueHardwareHandler`
7. **No emojis** - Never use emojis in code, comments, or documentation
8. **GPIO pin assignments** - Record all pin usage in README.md GPIO Pin Allocation table

---

## Production Environment

| Setting | Value |
|---------|-------|
| Pi IP | `192.168.199.246` |
| User | `pi` |
| Path | `/home/pi/open-TPT` |
| Service | `openTPT.service` |

### Hardware Status
- TPMS: 4/4 sensors (FL, FR, RL, RR)
- Multi-Camera: Dual USB (`/dev/video-rear`, `/dev/video-front`)
- NeoKey 1x4: Physical buttons
- Rotary Encoder: I2C QT with NeoPixel (0x36)
- Corner Sensors: CAN bus (can_b2_0) - Pico RP2040 CAN with MLX90640 thermal + brake temps
- Laser Ranger: CAN bus (can_b2_0) - Pico CAN Ranger with TOF laser, displayed on front camera
- Toyota Radar: can_b1_0 (keep-alive), can_b1_1 (tracks)
- OBD2: Speed, RPM, fuel level, Ford Mode 22 HV Battery SOC
- GPS: PA1616S at 10Hz (serial /dev/ttyS0) for lap timing and CoPilot
- NeoDriver: I2C LED strip at 0x60 (shift/delta/overtake modes)
- OLED Bonnet: 128x32 SSD1305 at 0x3C with MCP23017 buttons at 0x20 (10 VBOX-style pages)
- CoPilot: Rally callouts using OSM map data (USB/NVMe storage for 6.4GB roads.db)

### Pi 5 Compatibility
openTPT is compatible with both Pi 4 and Pi 5. The RP1 I/O chip on Pi 5 is abstracted by Adafruit Blinka and standard Linux interfaces.

| Component | Status | Notes |
|-----------|--------|-------|
| I2C devices | Compatible | Same addresses, same bus |
| CAN bus | Compatible | Standard socketcan interface |
| USB cameras | Compatible | Same udev rules |
| SPI CAN HATs | Compatible | Same GPIO pins |
| GPS UART | **Verify** | May need `/dev/ttyS0` vs `/dev/ttyAMA0` |
| TPMS UART | Compatible | `/dev/ttyAMA3` works on both |

See `DEPLOYMENT.md` section 6 for migration steps.

---

## Directory Structure

```
openTPT/
├── main.py                          # Entry point + OpenTPT class shell
├── config.py                        # ALL configuration constants
├── services/                        # Pi service configs (systemd, udev, etc.)
├── core/                            # Core application modules (mixins)
│   ├── __init__.py                  # Exports all mixins
│   ├── initialization.py            # Hardware subsystem init
│   ├── event_handlers.py            # Input/event processing
│   ├── rendering.py                 # Display pipeline
│   ├── telemetry.py                 # Telemetry recording
│   └── performance.py               # Power/memory monitoring
├── copilot/                         # Rally callout system
│   ├── main.py                      # CoPilot core class
│   ├── map_loader.py                # OSM roads.db loading
│   ├── path_projector.py            # Road path projection
│   ├── corners.py                   # Corner detection (ASC scale)
│   ├── pacenotes.py                 # Callout generation
│   ├── audio.py                     # espeak-ng/sample playback
│   └── simulator.py                 # GPX route following
├── gui/
│   ├── display.py                   # Rendering + temperature overlays
│   ├── camera.py                    # Multi-camera + radar overlay
│   ├── menu/                        # On-screen menu system (modular)
│   │   ├── __init__.py              # Exports Menu, MenuItem, MenuSystem
│   │   ├── base.py                  # Core menu classes
│   │   ├── bluetooth.py             # Bluetooth Audio + TPMS pairing
│   │   ├── camera.py                # Camera settings
│   │   ├── copilot.py               # CoPilot settings
│   │   ├── lap_timing.py            # Lap timing + track selection
│   │   ├── lights.py                # NeoDriver LED strip
│   │   ├── map_theme.py             # Map view theme selection
│   │   ├── oled.py                  # OLED Bonnet display settings
│   │   ├── pit_timer.py             # Pit timer settings
│   │   ├── settings.py              # Display, Units, Thresholds, Pages
│   │   ├── system.py                # GPS, IMU, Radar, System Status
│   │   └── tyre_temps.py            # Tyre temperature sensor settings
│   ├── copilot_display.py           # CoPilot UI page
│   ├── pit_timer_display.py         # Pit timer UI page
│   └── radar_overlay.py             # Radar visualisation
├── hardware/
│   ├── corner_sensor_handler.py     # Corner sensors + laser ranger via CAN (can_b2_0)
│   ├── tpms_input_optimized.py      # TPMS (tpms>=2.1.0)
│   ├── radar_handler.py             # Toyota radar
│   ├── obd2_handler.py              # OBD2/CAN
│   ├── gps_handler.py               # GPS serial NMEA parsing
│   ├── neodriver_handler.py         # NeoDriver LED strip
│   ├── oled_bonnet_handler.py       # OLED Bonnet secondary display
│   ├── lap_timing_handler.py        # Lap timing logic
│   ├── pit_timer_handler.py         # Pit lane timer logic
│   └── copilot_handler.py           # CoPilot integration handler
├── assets/
│   └── themes/                      # Map view colour themes (JSON)
├── usb_data/                        # USB drive data template
│   └── .opentpt/                    # Copy to USB root to set up new drive
│       ├── lap_timing/tracks/       # Track databases and KMZ files
│       ├── routes/                  # Lap timing GPX/KMZ routes
│       ├── copilot/routes/          # CoPilot GPX routes
│       └── pit_timer/               # Pit lane waypoints
├── utils/
│   ├── settings.py                  # Persistent user settings
│   ├── hardware_base.py             # Bounded queue base class
│   ├── fuel_tracker.py              # Fuel consumption tracking
│   ├── lap_timing_store.py          # SQLite lap time persistence
│   ├── pit_lane_store.py            # SQLite pit waypoint persistence
│   ├── telemetry_recorder.py        # CSV telemetry recording
│   └── theme_loader.py              # Map view theme loading
└── opendbc/*.dbc                    # CAN message definitions
```

---

## I2C Hardware Map

### Addresses
| Address | Device | Purpose |
|---------|--------|---------|
| `0x20` | MCP23017 | GPIO expander for OLED buttons |
| `0x30` | NeoKey | 1x4 button input with NeoPixels |
| `0x36` | Seesaw | Rotary encoder with NeoPixel |
| `0x3C` | SSD1305 | OLED Bonnet 128x32 |
| `0x60` | NeoDriver | I2C to NeoPixel LED strip |
| `0x68` | ICM20649 | IMU for G-meter |

### Bus Speed
**400kHz (Fast Mode)** - chosen over 1MHz for motorsport EMI resilience.

---

## Corner Sensors CAN (pico_tyre_temp.dbc)

Corner sensors (tyre temps, brake temps, detection) use CAN bus instead of I2C for improved reliability and simplified wiring.

### CAN Configuration
| Setting | Value |
|---------|-------|
| Channel | `can_b2_0` |
| Bitrate | 500 kbps |
| DBC File | `opendbc/pico_tyre_temp.dbc` |

### Message IDs per Corner
| Corner | TyreTemps | Detection | BrakeTemps | Status | FrameData |
|--------|-----------|-----------|------------|--------|-----------|
| FL | 0x100 | 0x101 | 0x102 | 0x110 | 0x11C |
| FR | 0x120 | 0x121 | 0x122 | 0x130 | 0x13C |
| RL | 0x140 | 0x141 | 0x142 | 0x150 | 0x15C |
| RR | 0x160 | 0x161 | 0x162 | 0x170 | 0x17C |

### Message Contents
- **TyreTemps** (10Hz): Left/Centre/Right median temps + lateral gradient (int16, 0.1 degC)
- **TyreDetection** (10Hz): Detected flag, Warnings, Confidence, TyreWidth
- **BrakeTemps** (10Hz): Inner/Outer temps + status (0=OK, 1=Disconnected, 2=Error, 3=NotFound)
- **Status** (1Hz): FPS, FirmwareVersion, WheelID, Emissivity
- **FrameData** (on request): 256 segments x 3 pixels for full 768-pixel thermal frame

### Command IDs
| ID | Name | Purpose |
|----|------|---------|
| 0x7F3 | FrameRequest | Request full thermal frame from specific wheel |
| 0x7F1 | ConfigRequest | Request configuration from all sensors |

---

## Laser Ranger CAN (pico_can_ranger.dbc)

TOF laser distance sensor for front camera overlay using Pico CAN Ranger on the same CAN bus as corner sensors.
Handled by `corner_sensor_handler.py` (shares CAN notifier with corner sensors).

### CAN Configuration
| Setting | Value |
|---------|-------|
| Channel | `can_b2_0` (shared with corner sensors) |
| Bitrate | 500 kbps |
| DBC File | `opendbc/pico_can_ranger.dbc` |

### Message IDs (Sensor ID 0)
| ID | Name | Rate | Purpose |
|----|------|------|---------|
| 0x200 | RangeData | ~4Hz | Distance, status, error code |
| 0x210 | Status | 1Hz | Measurement rate, firmware, sensor ID |

### Message Contents
- **RangeData**: Distance (uint16 mm), Status (0=OK, 1=Error), ErrorCode, MeasurementCount
- **Status**: MeasurementRate (Hz*10), FirmwareVersion, SensorID, TotalMeasurements

### Display Behaviour
- Shows distance on front camera view (user-configurable position)
- Colour coding: green (>15m), yellow (5-15m), red (<5m)
- Hidden when distance exceeds 50m or sensor offline/error

### User Settings (via Front Camera menu)
| Setting | Options | Default |
|---------|---------|---------|
| `laser_ranger.display_enabled` | true/false | true |
| `laser_ranger.display_position` | top, bottom | bottom |
| `laser_ranger.text_size` | small, medium, large | medium |

---

## Common Commands

### Deployment
```bash
./tools/quick_sync.sh pi@192.168.199.246    # Sync code
ssh pi@192.168.199.246 'sudo systemctl restart openTPT.service'
```

### Service Management
```bash
sudo systemctl status openTPT.service       # Status
sudo systemctl restart openTPT.service      # Restart
sudo journalctl -u openTPT.service -f       # Live logs
```

### Debug Commands
```bash
# I2C scan (NeoKey, encoder, OLED, NeoDriver, IMU)
sudo i2cdetect -y 1

# Corner sensor CAN traffic
candump can_b2_0

# Power status
vcgencmd get_throttled  # 0x0=OK, 0x50000=historical undervoltage
```

### Log Filtering
```bash
# By component
sudo journalctl -u openTPT.service -f | grep -iE "pico|radar|imu"

# By corner
sudo journalctl -u openTPT.service --since "30 min ago" | grep "FL"

# Failures
sudo journalctl -u openTPT.service -f | grep -E "failures|error|backoff"
```

---

## Known Issues & Solutions

| Issue | Solution |
|-------|----------|
| **IMU I/O errors** | Non-critical, auto-retries. Restart service if persistent |
| **Corner sensor offline** | Check CAN bus connection and `candump can_b2_0` for messages |
| **Heatmaps grey/offline** | Stale data cached 0.5s. Check `CORNER_SENSOR_CAN_TIMEOUT_S` |
| **6+ hour crashes** | Fixed v0.11+ (GC every 60s, surface clear every 10min) |
| **throttled=0x50000** | Historical undervoltage, normal on CM4-POE-UPS. Check bits 0-3 for current issues |

---

## Threading Architecture

### Thread Structure

| Thread | Purpose | Blocking Allowed |
|--------|---------|------------------|
| **Main Thread** | Pygame event loop, rendering at 60 FPS | NO - must complete in ≤12ms |
| **Hardware Threads** | I2C/CAN/Serial I/O, one per handler | YES - isolated from render |
| **Background Threads** | Bluetooth ops, menu actions, audio | YES - daemon threads |

### Data Flow Guarantees

```
Hardware Thread          Queue (depth=2)         Main Thread
     |                        |                       |
  [I/O read]                  |                       |
     |                        |                       |
  _publish_snapshot() ------> [snapshot] -----> get_snapshot()
     |                     (non-blocking)        (lock-free)
     |                        |                       |
                           [oldest dropped         [render]
                            if queue full]
```

**Key Guarantees:**
1. **Lock-free consumer path** - `get_snapshot()` never blocks
2. **Bounded memory** - Queue maxsize=2 prevents unbounded growth
3. **No data races** - Immutable `HardwareSnapshot` (frozen dataclass)
4. **Graceful degradation** - Dropped frames logged, render continues

### Thread Safety Patterns

| Pattern | Used For | Example |
|---------|----------|---------|
| **Bounded Queue** | Hardware data transfer | `BoundedQueueHardwareHandler` |
| **Immutable Snapshots** | Lock-free render access | `HardwareSnapshot(frozen=True)` |
| **Daemon Threads** | Background operations | `threading.Thread(daemon=True)` |
| **Threading Lock** | Shared mutable state | `_bt_connect_lock` in bluetooth.py |
| **Exponential Backoff** | Hardware retry logic | `ExponentialBackoff` class |

### What Can Run Where

| Operation | Main Thread | Hardware Thread | Background Thread |
|-----------|-------------|-----------------|-------------------|
| Pygame rendering | YES | NO | NO |
| I2C/SPI reads | NO | YES | NO |
| Subprocess calls | NO | NO | YES |
| Queue publish | NO | YES | NO |
| Queue consume | YES | NO | NO |
| Settings read | YES | YES | YES |
| Settings write | YES | NO | YES |

### Critical Rules

1. **Never block main thread** - All I/O must happen in worker threads
2. **Never access pygame from threads** - Only main thread touches display
3. **Use queues for data transfer** - No shared mutable state between threads
4. **Daemon threads for optional work** - Allows clean shutdown
5. **Timeout all I/O** - Prevents thread hangs (see `_i2c_with_timeout`)

---

## Key Design Patterns

### Bounded Queue Handler
```python
from utils.hardware_base import BoundedQueueHardwareHandler

class MyHandler(BoundedQueueHardwareHandler):
    def __init__(self):
        super().__init__(queue_depth=2)

    def _poll_loop(self):
        while self._running:
            data = self.sensor.read()
            self._publish_snapshot(data)
            time.sleep(0.1)

    def get_snapshot(self):
        return self._get_snapshot()  # Lock-free
```

### Configuration
All settings in `config.py` (root level), organised into 12 sections:

1. **Display & UI** - Resolution, colours, assets, scaling, layout
2. **Units & Thresholds** - Temperature, pressure, speed
3. **Hardware - I2C Bus** - Addresses, mux, timing, backoff
4. **Hardware - Sensors** - Tyre, brake, TPMS, IMU
5. **Hardware - Cameras** - Resolution, devices, transforms
6. **Hardware - Input** - NeoKey, encoder, NeoDriver, OLED
7. **Hardware - CAN Bus** - OBD2, Corner Sensors CAN, Radar
8. **Hardware - GPS** - Serial, timeouts
9. **Features - Lap Timing** - Tracks, corners, sectors
10. **Features - Fuel** - Tank, thresholds
11. **Features - CoPilot** - Maps, callouts, audio
12. **Threading & Performance** - Queues, timeouts

---

## Subsystem Quick Reference

### Multi-Camera (v0.8)
- Two USB cameras via udev rules (USB port to device name)
- Freeze-frame transitions (no checkerboard)
- Radar overlay on rear camera only

### Toyota Radar (v0.10)
- can_b1_1: Track data (RX), can_b1_0: Keep-alive (TX)
- Chevrons: green safe, yellow moderate, red rapid approach, blue overtaking
- Requires `cantools` package

### GPS and Lap Timing (v0.17)
- PA1616S GPS at 10Hz via /dev/ttyS0
- PPS time sync via chrony
- Lap times persisted to SQLite (`~/.opentpt/lap_timing/lap_timing.db`)
- Best lap loaded automatically when track selected

### Fuel Tracking (v0.17.9)
- OBD2 fuel level PID 0x2F
- Average consumption per lap calculation
- Refuelling detection with session reset
- Configurable warning/critical thresholds

### NeoDriver LED Strip (v0.17.2)
- I2C address 0x60, configurable pixel count
- Modes: shift (RPM), delta (lap time), overtake (radar), off
- Direction: centre-out, edges-in, left-to-right, right-to-left

### Brake Temperatures
- Provided by CAN corner sensors (inner/outer zones)
- Emissivity configured in sensor firmware (default 0.95)
- Status includes sensor health (OK, Disconnected, Error, NotFound)

### CoPilot Rally Callouts (v0.18.1)
- OSM-based corner detection with audio callouts
- Uses GPS heading for road path projection
- Map data: `/mnt/usb/.opentpt/copilot/maps/*.roads.db` (always on USB)
- Routes: `/mnt/usb/.opentpt/copilot/routes/*.gpx` (USB if available)
- Audio: espeak-ng TTS or Janne Laahanen rally samples
- Modes: Just Drive (follow current road), Route Follow (track/GPX)
- Corner severity: ASC 1-6 scale (1=flat, 6=hairpin)
- Route integration: Uses lap timing track centerline when available
- Supports both circuit tracks (KMZ) and point-to-point stages (GPX)
- Config: `COPILOT_*` in config.py, `copilot.*` in settings

### USB Patch Deployment (v0.19.10)
- Offline updates for vehicle-mounted Pi without network access
- Full replacement: deletes existing app and extracts fresh (no orphaned files)
- User data safe on USB at `/mnt/usb/.opentpt/`
- Checks `/mnt/usb` at boot for `opentpt-patch.tar.gz` or `opentpt-patch.zip`
- Log file: `/mnt/usb/.opentpt/patch.log`
- Boot sequence: `usb-patch.service` runs before `splash.service` and `openTPT.service`

**Creating patches:**
```bash
# From repo root - create full release archive
tar -czvf opentpt-patch.tar.gz --exclude='.git' --exclude='usb_data' --exclude='__pycache__' .

# Or using zip
zip -r opentpt-patch.zip . -x '.git/*' -x 'usb_data/*' -x '__pycache__/*'
```

**Deploying:** Copy archive to USB root, insert into Pi, reboot.

**Verifying:**
```bash
cat /mnt/usb/.opentpt/patch.log
sudo journalctl -u usb-patch.service
```

### USB Log Sync (v0.19.7)
- Exports openTPT service logs to USB drive for offline review
- Daily log files: `/mnt/usb/logs/opentpt_YYYYMMDD.log`
- Incremental sync every 30 seconds (only new entries appended)
- Full sync on shutdown/reboot
- Keeps last 7 days of logs

**Enabling:**
```bash
sudo systemctl enable usb-log-sync.service   # Shutdown sync
sudo systemctl enable usb-log-sync.timer     # 30s incremental sync
```

**Checking status:**
```bash
sudo systemctl status usb-log-sync.timer
ls -la /mnt/usb/logs/
```

### Pit Timer (v0.19)
- VBOX-style pit lane timer with GPS-based entry/exit detection
- Two timing modes: Entrance-to-Exit (total pit time) vs Stationary-only (box time)
- GPS waypoint marking via OLED buttons (hold Select on PIT page)
- Crossing detection using same cross-product algorithm as lap timing
- Countdown timer for minimum stop time
- Speed monitoring with warning when approaching limit
- Per-track storage of pit waypoints (`~/.opentpt/pit_timer/pit_waypoints.db`)
- OLED display: PIT mode shows entry/exit status, timers, countdown
- Main GUI page with large timer, speed bar, GO/WAIT indicators
- Config: `PIT_TIMER_*` in config.py, `pit_timer.*` in settings

**State Machine:**
- ON_TRACK: Normal driving (waiting for entry line)
- IN_PIT_LANE: Between entry line and pit box (speed monitored)
- STATIONARY: Stopped in pit box (countdown active if min time set)

**OLED Button Actions (on PIT page, selected):**
- Prev (<): Mark entry line at current GPS position
- Next (>): Mark exit line at current GPS position
- Select: Toggle timing mode

### USB Data Storage (v0.19.10)
All persistent data uses USB storage when available for read-only rootfs robustness.
On boot, if USB not mounted at `/mnt/usb`, a warning is shown on splash screen.

**Directory Structure (USB at `/mnt/usb/.opentpt/`):**
```
.opentpt/
├── settings.json           # User preferences
├── lap_timing/
│   ├── lap_timing.db       # Lap times database
│   └── tracks/
│       ├── tracks.db       # Track database (copied from bundled)
│       ├── racelogic.db    # Racelogic database (copied from bundled)
│       ├── maps/           # Custom track files
│       └── racelogic/      # Racelogic KMZ files
├── routes/                 # Lap timing GPX/KMZ files
├── pit_timer/
│   └── pit_waypoints.db    # Pit lane GPS waypoints
├── copilot/
│   ├── maps/               # OSM roads.db files (always USB, 6+ GB)
│   ├── routes/             # CoPilot GPX route files
│   └── cache/              # Road data cache
└── logs/                   # Service logs (daily files)
```

**Setting Up a New USB Drive:**
```bash
cp -r usb_data/.opentpt /mnt/usb/
```

**Track Data:**
- Template tracks in `usb_data/.opentpt/lap_timing/tracks/`
- Auto-copied to USB on first run if missing
- User tracks added to USB persist across app updates

**Fallback:**
If USB not available, falls back to `~/.opentpt/` on local filesystem.

### Read-Only Root Filesystem (v0.19.11)

Protects SD card from corruption due to sudden power loss using the `overlayroot` package.

**How It Works:**
- **Lower layer**: Read-only root filesystem on SD card (protected)
- **Upper layer**: tmpfs (RAM) captures all writes transparently
- **Result**: SD card never written to during normal operation

**Enabling:**
```bash
sudo ./services/boot/setup-readonly.sh
sudo reboot
```

**Verifying:**
```bash
mount | grep overlay   # Should show / as overlay
```

**Disabling (for maintenance):**
```bash
sudo ./services/boot/disable-readonly.sh
sudo reboot
```

**Temporary Write Access:**
```bash
sudo overlayroot-chroot    # Opens shell with write access to lower fs
```

**Patching with Overlay Active:**
USB patches automatically use `overlayroot-chroot` to apply changes to the underlying filesystem - no manual intervention needed.

**What's Protected:**
- All system files and application code on SD card
- Runtime writes go to RAM (lost on reboot, which is fine)

**What Persists (on USB):**
- Settings, lap times, pit waypoints, tracks
- Telemetry recordings, logs
- CoPilot maps and routes

---

## Git Workflow

```bash
# British English in commits
git commit -m "Optimise thermal processing"  # correct
git commit -m "Optimize thermal processing"  # wrong
```

### Before Committing
- [ ] British English spelling
- [ ] No blocking in render path
- [ ] Test in mock mode (`./main.py --windowed`)
- [ ] Deploy and test on Pi
- [ ] Update CHANGELOG.md

---

## Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Project overview, features, configuration, **TODO lists** |
| `CHANGELOG.md` | Version history with detailed changes |
| `QUICKSTART.md` | Quick commands for daily use |
| `DEPLOYMENT.md` | Pi deployment and boot splash setup |
| `CLAUDE.md` | AI assistant context (this file) |

**Note:** Hardware and Software TODO lists are maintained in `README.md` (see "Hardware TODO" and "Software TODO" sections).

### Keeping Documentation Updated

Documentation must be kept in sync with code changes:

1. **CHANGELOG.md** - Update for every feature, fix, or significant change
   - Group changes under version headers (e.g., `## [v0.17.9]`)
   - Include: New Features, Improvements, Bug Fixes, Modified Files
   - Be specific about what changed and why

2. **README.md** - Update when adding/removing:
   - Features or capabilities
   - Hardware support
   - Configuration options
   - Project structure changes

3. **QUICKSTART.md** - Update when changing:
   - Common commands or workflows
   - Hardware status
   - Key configuration files

4. **DEPLOYMENT.md** - Update when changing:
   - Installation steps
   - Boot/service configuration
   - Deployment scripts or methods

5. **CLAUDE.md** - Update when changing:
   - Hardware configuration or status
   - Directory structure
   - I2C addresses or registers
   - Key design patterns

---

## Final Notes

1. **British English is non-negotiable**
2. **Read before editing** - Always use Read tool first
3. **Lock-free rendering** - Never block in render path
4. **Test on Pi** - Mock mode doesn't catch hardware issues
5. **Bounded queues** - All hardware handlers must use them
6. **Graceful degradation** - System works with missing hardware
7. **Keep docs updated** - All changes should be reflected in documentation
