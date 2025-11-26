# Claude Context - openTPT Project

**Purpose:** This document provides essential context for Claude AI working on the openTPT project, enabling quick onboarding and effective collaboration.

**Last Updated:** 2025-11-24 (v0.15.1)

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
- **SSH/Sync:** Always use `pi@` prefix (e.g., `./tools/quick_sync.sh pi@192.168.199.243`)

### Hardware Status (v0.15.1)
- ✅ **TPMS:** 4/4 sensors auto-paired (FL, FR, RL, RR)
- ✅ **Multi-Camera:** Dual USB cameras with seamless switching
  - Rear camera: `/dev/video-rear` (USB port 1.1)
  - Front camera: `/dev/video-front` (USB port 1.2)
- ✅ **NeoKey 1x4:** Physical control buttons working
- ✅ **Pico Thermal:** 1/4 MLX90640 connected (FL)
- ✅ **TOF Distance:** VL53L0X sensors for ride height (1/4 connected - FR)
  - Shows current distance (EMA smoothed) and 10-second minimum (raw)
  - Automatic retry/reinitialise with exponential backoff (fixes dropouts)
  - Recreates sensor object after 3 consecutive I2C failures
- ✅ **Brake Temps:** MCP9601 thermocouple support added
  - Dual-zone display (inner/outer pads) with gradient blending
  - I2C addresses: 0x65 (inner), 0x66 (outer)
- ✅ **Toyota Radar:** Enabled by default, receives 1-3 tracks
  - CAN channels: can_b1_0 (keep-alive), can_b1_1 (tracks)
- ✅ **OBD2:** MAP-based SOC simulation for desk testing
- ⚠️ **ADS1115:** Not connected (brake temps unavailable)
- ✅ **Power:** Waveshare CM4-POE-UPS carrier (12V DC or PoE+, PWM fan, temp ~51°C)

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

## I2C Hardware Map

Complete reference for all I2C devices and channels.

### I2C Addresses

| Address | Device | Purpose |
|---------|--------|---------|
| `0x08` | Pico (RP2040) | MLX90640 thermal camera slave (per corner) |
| `0x29` | VL53L0X | TOF distance sensor (ride height, per corner) |
| `0x48` | ADS1115 | 4-channel ADC for IR brake sensors |
| `0x5A` | MLX90614 | Single-point IR sensor (tyre or brake, per corner) |
| `0x65` | MCP9601 | Thermocouple amplifier (brake inner pad) |
| `0x66` | MCP9601 | Thermocouple amplifier (brake outer pad) |
| `0x68` | ICM20649 | IMU for G-meter |
| `0x70` | TCA9548A | I2C multiplexer (8 channels) |

### Mux Channel Assignments

All per-corner sensors share the same mux channel for their corner:

| Channel | Position | Devices on Channel |
|---------|----------|-------------------|
| 0 | FL | Pico (0x08), MLX90614 (0x5A), VL53L0X (0x29), MCP9601 (0x65/0x66) |
| 1 | FR | Pico (0x08), MLX90614 (0x5A), VL53L0X (0x29), MCP9601 (0x65/0x66) |
| 2 | RL | Pico (0x08), MLX90614 (0x5A), VL53L0X (0x29), MCP9601 (0x65/0x66) |
| 3 | RR | Pico (0x08), MLX90614 (0x5A), VL53L0X (0x29), MCP9601 (0x65/0x66) |

**Note:** Only one sensor type per corner is typically installed, but they all share the same I2C addresses and mux channels. The mux isolates them so address conflicts don't occur.

### GPIO Pins

| GPIO | Function | Notes |
|------|----------|-------|
| GPIO2 (SDA) | I2C1 Data | Main I2C bus for all sensors |
| GPIO3 (SCL) | I2C1 Clock | Main I2C bus for all sensors |
| GPIO17 | TCA9548A Reset | Active-low, has internal pull-up |

### Mux Selection Commands

To select a mux channel (useful for debugging):
```bash
# FL (channel 0): write 0x01 (1 << 0)
sudo i2cset -y 1 0x70 0x01

# FR (channel 1): write 0x02 (1 << 1)
sudo i2cset -y 1 0x70 0x02

# RL (channel 2): write 0x04 (1 << 2)
sudo i2cset -y 1 0x70 0x04

# RR (channel 3): write 0x08 (1 << 3)
sudo i2cset -y 1 0x70 0x08

# Disable all channels: write 0x00
sudo i2cset -y 1 0x70 0x00
```

---

## Pico I2C Register Map

The Pico (RP2040) acts as an I2C slave at address `0x08`, providing thermal camera data.

### Register Layout

#### Configuration Registers (0x00-0x0F) - Read/Write

| Register | Name | Description |
|----------|------|-------------|
| 0x00 | Firmware Version | Read-only firmware version number |
| 0x01 | Output Mode | 0x00=USB serial, 0x01=I2C only, 0xFF=all |
| 0x02 | Frame Rate | Target frame rate (future use) |
| 0x03 | Fallback Mode | 0=zero temps when no tyre, 1=copy centre temp |
| 0x04 | Emissivity | Emissivity × 100 (e.g., 95 = 0.95) |
| 0x05 | Raw Mode | 0=tyre algorithm, 1=16-channel raw data |

#### Status Registers (0x10-0x1F) - Read Only

| Register | Name | Description |
|----------|------|-------------|
| 0x10 | Firmware Version | Same as 0x00 |
| 0x11 | Frame Counter Low | Frame number (low byte) |
| 0x12 | Frame Counter High | Frame number (high byte) |
| 0x13 | FPS | Current frame rate (integer) |
| 0x14 | **Detected** | **Tyre detected flag (0/1)** |
| 0x15 | **Confidence** | **Detection confidence (0-100%)** |
| 0x16 | Tyre Width | Tyre width in pixels |
| 0x17 | Span Start | Tyre span start pixel |
| 0x18 | Span End | Tyre span end pixel |
| 0x19 | Warnings | Warning flags bitfield |

#### Temperature Registers (0x20-0x2D) - Read Only

| Register | Name | Description |
|----------|------|-------------|
| 0x20-0x21 | **Left Median** | **Left/inner temperature (int16, tenths °C)** |
| 0x22-0x23 | **Centre Median** | **Centre temperature (int16, tenths °C)** |
| 0x24-0x25 | **Right Median** | **Right/outer temperature (int16, tenths °C)** |
| 0x26-0x27 | Left Average | Left average temperature |
| 0x28-0x29 | Centre Average | Centre average temperature |
| 0x2A-0x2B | Right Average | Right average temperature |
| 0x2C-0x2D | Lateral Gradient | Temperature gradient across tyre |

**Note:** All temperatures are signed int16 (little-endian) in tenths of degrees Celsius. To convert: `temp_celsius = int16_value / 10.0`

#### Raw Channel Data (0x30-0x4F) - Read Only

16 channels × 2 bytes when RAW_MODE=1 enabled. Each channel is int16 tenths of °C.

---

## Debug One-liners

Quick commands for hardware debugging.

### Pico Tyre Sensor (FL Example)

Read full sensor packet (temps, detected, confidence):

```bash
sudo python3 -c "
from smbus2 import SMBus
import time

bus = SMBus(1)
bus.write_byte(0x70, 1)  # FL: channel 0
time.sleep(0.01)

def read_int16(reg):
    low = bus.read_byte_data(0x08, reg)
    high = bus.read_byte_data(0x08, reg + 1)
    val = (high << 8) | low
    return (val - 65536 if val & 0x8000 else val) / 10.0

fw_ver = bus.read_byte_data(0x08, 0x10)
detected = bus.read_byte_data(0x08, 0x14)
confidence = bus.read_byte_data(0x08, 0x15)
left = read_int16(0x20)
centre = read_int16(0x22)
right = read_int16(0x24)

det_str = 'YES' if detected else 'NO'
print(f'FL Pico (FW v{fw_ver}):')
print(f'  Left:   {left:.1f}°C')
print(f'  Centre: {centre:.1f}°C')
print(f'  Right:  {right:.1f}°C')
print(f'  Detected: {det_str}')
print(f'  Confidence: {confidence}%')
"
```

**Change mux channel for other corners:**
- FL: `bus.write_byte(0x70, 1)` (channel 0)
- FR: `bus.write_byte(0x70, 2)` (channel 1)
- RL: `bus.write_byte(0x70, 4)` (channel 2)
- RR: `bus.write_byte(0x70, 8)` (channel 3)

### TOF Distance Sensor

Quick check TOF sensor on FR (channel 1):

```bash
sudo python3 -c "
import board, busio, adafruit_tca9548a, adafruit_vl53l0x
i2c = busio.I2C(board.SCL, board.SDA)
mux = adafruit_tca9548a.TCA9548A(i2c)
tof = adafruit_vl53l0x.VL53L0X(mux[1])  # FR = channel 1
print(f'FR TOF: {tof.range}mm')
"
```

### I2C Device Scan

Scan all devices on the bus (no mux):

```bash
sudo i2cdetect -y 1
```

Scan devices on mux channel 0 (FL):

```bash
# Select channel first
sudo i2cset -y 1 0x70 0x01
# Then scan
sudo i2cdetect -y 1
```

### Check I2C Bus Health

```bash
# Check for errors
dmesg | grep -i i2c | tail -20

# Check bus speed
sudo cat /sys/class/i2c-adapter/i2c-1/of_node/clock-frequency
```

---

## Log Analysis Tips

Useful journalctl commands for debugging specific issues.

### TOF Sensor Logs

```bash
# Real-time TOF messages
sudo journalctl -u openTPT.service -f | grep -iE "tof|distance|reinit"

# TOF initialization and errors (last hour)
sudo journalctl -u openTPT.service --since "1 hour ago" --no-pager | grep -i "tof\|vl53l0x"

# TOF failures and recovery
sudo journalctl -u openTPT.service --since "30 minutes ago" --no-pager | grep -E "TOF.*failures|Reinitialised"
```

### Pico/Tyre Sensor Logs

```bash
# Pico sensor errors and recovery
sudo journalctl -u openTPT.service --since "30 minutes ago" --no-pager | grep -iE "pico|mlx90614|failures|recovered"

# Pico initialization
sudo journalctl -u openTPT.service -b --no-pager | grep -E "Pico sensor|Channel [0-3]:"

# I2C mux reset events
sudo journalctl -u openTPT.service --since "1 hour ago" --no-pager | grep "mux reset"
```

### Brake Sensor Logs

```bash
# Brake temperature sensors
sudo journalctl -u openTPT.service --since "30 minutes ago" --no-pager | grep -iE "brake|mcp9601"
```

### IMU/G-Meter Logs

```bash
# IMU errors
sudo journalctl -u openTPT.service --since "10 minutes ago" --no-pager | grep -i "imu"
```

### Performance Logs

```bash
# Render timing (shows which components are slow)
sudo journalctl -u openTPT.service --since "5 minutes ago" --no-pager | grep "Render profile"

# Loop timing
sudo journalctl -u openTPT.service --since "5 minutes ago" --no-pager | grep "Loop profile"

# Memory stats
sudo journalctl -u openTPT.service --since "10 minutes ago" --no-pager | grep -E "Memory|GPU"
```

### General Sensor Status

```bash
# All sensor-related messages (last 10 mins)
sudo journalctl -u openTPT.service --since "10 minutes ago" --no-pager | grep -E "FL|FR|RL|RR|sensor|failures"

# Startup initialization sequence
sudo journalctl -u openTPT.service -b --no-pager | grep -A 5 "Initializing Unified Corner Handler"

# Recent logs (last 100 lines)
sudo journalctl -u openTPT.service -n 100 --no-pager
```

### Filtering by Corner

```bash
# FL sensor messages only
sudo journalctl -u openTPT.service --since "30 minutes ago" --no-pager | grep "FL"

# All corners with failures
sudo journalctl -u openTPT.service --since "30 minutes ago" --no-pager | grep -E "(FL|FR|RL|RR).*failures"
```

---

## Known Issues & Workarounds

### IMU I/O Errors (Recurring)

**Symptom:** Logs show `IMU: Error reading sensor: [Errno 5] Input/output error`

**Impact:** G-meter may show stale/frozen data temporarily

**Cause:** ICM20649 IMU occasionally fails to respond on I2C bus

**Workaround:**
- Non-critical - system continues operating
- IMU will retry on next read cycle
- If persistent, restart service: `sudo systemctl restart openTPT.service`

**Status:** Known issue, does not affect critical telemetry (tyres/brakes)

### TOF Sensor Dropouts (Mitigated in v0.15.1)

**Symptom:** Distance reading freezes or shows "--"

**Cause:** VL53L0X sensors occasionally lose I2C communication

**Solution:** Automatic retry/reinitialise implemented in v0.15.1
- Exponential backoff: 1s → 2s → 4s → 8s → 16s → 32s → 64s max
- Recreates sensor object after 3 consecutive failures
- Logs: `✓ TOF FR: Reinitialised after N attempts`

**Manual Check:**
```bash
# Check if TOF sensor responds
sudo python3 -c "import board, busio, adafruit_tca9548a, adafruit_vl53l0x; i2c = busio.I2C(board.SCL, board.SDA); mux = adafruit_tca9548a.TCA9548A(i2c); tof = adafruit_vl53l0x.VL53L0X(mux[1]); print(f'TOF: {tof.range}mm')"
```

### I2C Bus Lockup (Rare, Mitigated in v0.12)

**Symptom:** All I2C sensors stop responding, system logs I2C errors

**Cause:** Pico or sensor holding SDA line low due to interrupted transaction

**Solution (Automatic):**
- Hardware mux reset on GPIO17 (added in v0.12)
- Triggers after 3 consecutive failures per corner
- Logs: `⚠ I2C mux reset triggered (total resets: N)`

**Solution (Manual):**
```bash
# Restart service (soft recovery)
sudo systemctl restart openTPT.service

# If that doesn't work, power cycle the Pi
sudo reboot
```

### Thermal Heatmap Flashing Grey/Offline

**Symptom:** Tyre or brake heatmap briefly shows grey or "OFFLINE"

**Cause:** Sensor read took >1 second (exceeded `THERMAL_STALE_TIMEOUT`)

**Normal Behavior:** System caches last valid data for 1 second, then shows offline
- Usually self-recovers when sensor responds again
- Check logs for sensor-specific failures

**If Persistent:**
```bash
# Check which sensor is failing
sudo journalctl -u openTPT.service -f | grep -E "failures|backoff"
```

### Brake Temperatures Reading Low/High

**Symptom:** Brake temps don't match expected values

**Check Emissivity Settings:**
- MLX90614/ADC brake sensors use software emissivity correction
- Default: 0.95 (oxidised cast iron)
- Adjust in `utils/config.py`: `BRAKE_ROTOR_EMISSIVITY`

**Typical Values:**
- Cast iron (rusty/oxidised): 0.95
- Cast iron (machined/clean): 0.60-0.70
- Ceramic composite: 0.90-0.95

See "Brake Temperature Emissivity Correction" section for details.

### System Shows Power Issues (throttled=0x50000)

**Symptom:** Status bar shows throttling warning

**Cause:** Insufficient power supply or voltage drop

**Check Power:**
```bash
vcgencmd get_throttled
# 0x0 = OK
# 0x50000 = under-voltage occurred since boot
```

**Solution:**
- Use official Raspberry Pi power supply (5V 3A minimum)
- Check USB-C cable quality
- For PoE: Ensure PoE+ HAT and switch support 802.3at (25.5W)

### Long Runtime Crashes (Fixed in v0.11)

**Symptom:** System crashes or becomes unresponsive after 6+ hours

**Status:** Fixed in v0.11 with periodic garbage collection and surface cache clearing

**If Still Occurring:**
```bash
# Check memory stats
sudo journalctl -u openTPT.service --since "1 hour ago" | grep -E "Memory|GPU"

# Restart service as temporary workaround
sudo systemctl restart openTPT.service
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

### Issue: Power Issues Detected (throttled=0x50000)
**Solution:**
- On CM4-POE-UPS carrier, 0x50000 (historical undervoltage + throttling) is common even with adequate power
- Focus on bits 0-3 for **current** issues, bits 16-19 are historical
- If bit 0 (current undervoltage) is set, check power supply
- If bit 1 (frequency capped) is set, system is actively limiting performance
- Temperature at 51°C with PWM fan is normal operating range
- Check logs for voltage monitoring messages every 60 seconds

### Issue: I2C Bus Locked Up (i2cdetect hangs)
**Solution (v0.12+):**
- Fixed via threading lock in unified_corner_handler.py
- Root cause: smbus2 and busio both accessing I2C bus 1 without synchronisation
- Partial transactions could leave Pico holding SDA low
- **Hardware reset (recommended):** Connect TCA9548A RESET pin to GPIO17
  - Auto-triggers after 3 consecutive I2C failures
  - Uses Pi's internal pull-up (no external resistor needed)
  - Check logs for "I2C mux reset triggered" messages
- If still occurs, power cycle the Pi (soft reboot may not recover the bus)
- Check Pico serial output for "WARNING: Rebooted by watchdog" (indicates Pico hang recovered)
- GPIO bus recovery commands (if power cycle not possible):
  ```bash
  sudo raspi-gpio set 2 ip && sudo raspi-gpio set 3 ip
  sleep 0.1
  sudo raspi-gpio set 2 a0 && sudo raspi-gpio set 3 a0
  ```

### Issue: System Crashes After 6+ Hours
**Solution (v0.11+):**
- Fixed via periodic garbage collection (every 60s) and surface cache clearing (every 10 min)
- Check logs for "GC: Collected N objects" messages every 60 seconds
- Check logs for "Memory: Cleared cached pygame surfaces" every 10 minutes
- If still crashing, check for I2C bus errors in logs (separate issue)
- Verify pygame.display.flip() times in logs (should be <20ms, not seconds)
- Root cause was GPU memory fragmentation after ~648,000 frames

### Issue: pygame.display.flip() Blocking/Slow Render
**Solution:**
- Check garbage collection is running (logs every 60s)
- Check surface cache clearing is enabled (logs every 10 min)
- Verify not running on battery (UPS mode) - use mains power
- Check frame count in logs - issue appeared after ~6 hours at 30-60 FPS
- If GC not helping, may need to restart application

### Issue: Thermal/Brake Heatmaps Flashing Grey
**Solution (v0.12+):**
- Fixed via stale data caching in main.py
- Display runs at 35 FPS but sensor data updates at 7-10 Hz
- Stale data now cached for up to 1 second before showing offline
- Configure timeout via `THERMAL_STALE_TIMEOUT` in utils/config.py (default 1.0s)
- Applies to both thermal heatmaps and brake temperature displays

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

## Long Runtime Stability

### Overview
The system is designed for extended motorsport sessions (6+ hours). Several mechanisms ensure stable operation under long runtime conditions.

### Voltage Monitoring
- **Purpose:** Monitor Raspberry Pi power supply health
- **Implementation:** `main.py` lines 158-234 (`check_power_status()`)
- **Monitoring frequency:** At startup and every 60 seconds
- **What's checked:**
  - Undervoltage detection (current and historical)
  - Frequency capping due to power issues
  - Throttling due to power or thermal issues
  - Soft temperature limit reached
- **Configuration:** CM4-POE-UPS carrier board common status code 0x50000 (historical undervoltage) is expected, focus on bits 0-3 for current issues

### Memory Management
- **Purpose:** Prevent pygame/SDL memory fragmentation crashes after extended runtime
- **Implementation:** `main.py` lines 268-278 (initialization), 640-676 (periodic execution)
- **Garbage collection:** Every 60 seconds, frees 500-700 objects typically
- **Surface cache clearing:** Every 10 minutes, clears cached pygame surfaces
- **Impact:** No visible screen flicker, non-invasive background operation
- **Testing:** System runs stably at 30-60 FPS on G-meter page, needs 6+ hour runtime verification

### Key Files
- `main.py` lines 158-234: `check_power_status()` - Voltage monitoring
- `main.py` lines 268-278: Memory management initialization
- `main.py` lines 640-676: Periodic garbage collection and surface clearing

### Historical Context (v0.11)
Prior to v0.11, the system would crash after ~6 hours of continuous operation on the G-meter page:
- **Symptom:** pygame.display.flip() blocking for 3-17 seconds
- **Root cause:** GPU memory fragmentation after ~648,000 frames at 30-60 FPS
- **Solution:** Periodic garbage collection + surface cache clearing
- **Status:** Deployed and monitoring, awaiting long runtime verification

---

## Version History Quick Reference

### v0.15.1 (2025-11-24) - TOF Sensor Reliability
- TOF sensors: Automatic retry/reinitialise with exponential backoff
- Recreates sensor object after 3 consecutive I2C failures (fixes dropouts)
- Returns last known value during backoff for smoother display
- Logs recovery attempts: `✓ TOF FR: Reinitialised after N attempts`
- One-liner debug tool for Pico sensors: reads temps, detected flag, confidence

### v0.15 (2025-11-23) - Configuration Reorganisation
- Config file reorganised into 10 logical sections with table of contents
- All I2C addresses consolidated into single section
- Sensor thresholds co-located with sensor configuration
- Pi IP updated to 192.168.199.243
- SSH note: Always use `pi@` prefix for connections

### v0.14 (2025-11-22) - MCP9601 Thermocouple Brake Sensors
- MCP9601 thermocouple support for brake temperature
- Dual-zone brake display (inner/outer pads) with gradient blending
- I2C addresses: 0x65 (inner), 0x66 (outer)
- Separate backoff tracking extended to brake sensors

### v0.13 (2025-11-22) - VL53L0X TOF Distance Sensors
- VL53L0X Time-of-Flight sensors for ride height monitoring
- Displays current distance (EMA smoothed) and 10-second minimum (raw)
- Separate backoff tracking per sensor type (tyre/brake/TOF)
- Graceful handling when sensors out of range

### v0.12 (2025-11-22) - I2C Bus Reliability Fix
- Added threading lock to serialise I2C access between smbus2 and busio
- Prevents bus lockups that required power cycling to recover
- Protected methods: `_read_pico_sensor`, `_read_tyre_mlx90614`, `_read_brake_adc`, `_read_brake_mlx90614`
- Pico firmware v1.1: Minimal critical section + 5-second watchdog timer
- Hardware mux reset: Connect TCA9548A RESET to GPIO17 for auto-recovery
- Stale data caching: Thermal/brake heatmaps cache last valid data for up to 1 second (`THERMAL_STALE_TIMEOUT`)
- Exponential backoff: Failed sensors back off 1s→2s→4s→...→64s max, prevents bus hammering

### v0.11 (2025-11-21) - Long Runtime Stability & Security Fixes
- Voltage monitoring at startup and every 60 seconds
- Periodic garbage collection (every 60s) for memory stability
- Pygame surface cache clearing (every 10 minutes)
- Security fixes: CAN bus array access bounds checking
- Security fixes: Replaced bare except clauses with specific exceptions
- Security fixes: Input validation for emissivity correction
- Security fixes: Defensive thermal array shape validation
- Brake rotor emissivity correction documentation
- Fix for 6-hour runtime crash (pygame/SDL memory fragmentation)
- Pi IP address updated to 192.168.199.243
- Testing: GC frees 500-700 objects per cycle, system stable

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
| AI context | `clade.md` (this file) |

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

### "System shows power issues (throttled=0x50000)"
→ On CM4-POE-UPS, 0x50000 is common (historical undervoltage), check bits 0-3 for current issues

### "System crashed after 6+ hours"
→ v0.11+ has GC and surface clearing, check logs for "GC: Collected" and "Memory: Cleared" messages

### "pygame slow/blocking after long runtime"
→ Check GC running (every 60s), verify not on battery, may need application restart if severe

### "Heatmaps flashing grey/offline"
→ Fixed in v0.12 via stale data caching, adjust `THERMAL_STALE_TIMEOUT` in config if needed (default 1.0s)

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
8. **Long runtime stability** - GC every 60s, surface clearing every 10 min (v0.11+)

**When in doubt:**
- Check existing code patterns
- Read the relevant documentation
- Ask the user for clarification
- Maintain British English spelling

---

**This document should be read at the start of every new session to maintain context and coding standards.**

**Version:** 0.12 (I2C Bus Contention Fix)
**Last Updated:** 2025-11-22
**Maintained by:** AI assistants working on openTPT
