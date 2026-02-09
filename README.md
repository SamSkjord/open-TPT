# openTPT - Open Track Performance Telemetry

A modular GUI system for live motorsport telemetry using a Raspberry Pi 4/5 with HDMI display support. Features radar overlay on camera feeds for collision and overtake warnings.

[![Tests](https://github.com/SamSkjord/open-TPT/actions/workflows/tests.yml/badge.svg)](https://github.com/SamSkjord/open-TPT/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/SamSkjord/open-TPT/branch/main/graph/badge.svg)](https://codecov.io/gh/SamSkjord/open-TPT)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/SamSkjord/open-TPT)

## Overview

openTPT provides real-time monitoring of:
- Tyre pressure and temperature (via TPMS)
- Brake rotor temperatures (via IR sensors + ADC)
- Tyre surface thermal imaging (via Pico CAN corner sensors with MLX90640)
- Multi-camera support with seamless switching (dual USB UVC cameras)
- Dual radar support with independent front and rear units (Toyota Denso or Tesla Bosch, per-unit CAN bus configuration)
- Fuel tracking with consumption rate and laps remaining estimation
- GPS lap timing with delta display (circuit tracks and point-to-point stages)
- NeoDriver LED strip for shift lights, delta, and overtake warnings
- CoPilot rally callouts for corners, junctions, and hazards (OSM map data)

The system is designed for racing applications where real-time monitoring of tyre and brake conditions is critical for optimal performance and safety.

### Performance Architecture

openTPT features a high-performance architecture optimised for real-time telemetry:
- **Lock-free rendering** - No blocking operations in the render path (target: ≤12ms/frame)
- **Bounded queue system** - Double-buffered data snapshots for all hardware handlers
- **Numba JIT compilation** - Optimised thermal zone processing (< 1ms per sensor)
- **60 FPS target** - Smooth camera feed and telemetry updates
- **Multi-threaded I/O** - Hardware polling runs in dedicated background threads

## Hardware Requirements

### Core Components
- Raspberry Pi 4 or 5 (2GB+ RAM recommended)
- Waveshare 1024x600 HDMI display (or other HDMI displays - UI designed for 800x480, scales to fit)
- TPMS receivers and sensors
- Tyre/Brake temperature sensors via CAN bus:
  - Adafruit RP2040 CAN Bus Feather with MLX90640 thermal camera (pico-tyre-temp firmware)
  - Four sensors (FL, FR, RL, RR) on dedicated CAN bus (can_b2_0)
  - Provides tyre temps, brake temps, detection status, and full thermal frames
- Adafruit NeoKey 1x4 for input control

### Optional Components
- USB UVC cameras (up to 2 cameras for rear/front views with seamless switching)
- CAN radar (up to 2 units — independent front and rear, any combination):
  - **Toyota** (Denso): Prius/Corolla 2017+ unit, dual CAN bus (radar data + car keepalive)
  - **Tesla** (Bosch MRRevo14F): Any Model S/X/3 unit, single CAN bus, auto-VIN
  - CAN-to-USB adapters or SPI CAN controllers
  - DBC files included in `opendbc/`
- Dual Waveshare 2-CH CAN HAT+ stack for multi-bus CAN/OBD work

### GPIO Pin Allocation (Raspberry Pi 4/5)

| GPIO | Function | Interface | Notes |
|------|----------|-----------|-------|
| 2 | I2C1 SDA | I2C | NeoKey, encoder, OLED, NeoDriver, IMU |
| 3 | I2C1 SCL | I2C | NeoKey, encoder, OLED, NeoDriver, IMU |
| 4 | UART2 TX | UART | TPMS receiver (/dev/ttyAMA2 on Pi 5) |
| 5 | UART2 RX | UART | TPMS receiver |
| 7 | SPI0 CE1 | SPI | CAN HAT Board 2, CAN_1 (OBD-II) |
| 8 | SPI0 CE0 | SPI | CAN HAT Board 2, CAN_0 (Corner Sensors) |
| 9 | SPI0 MISO | SPI | CAN HAT Board 2 |
| 10 | SPI0 MOSI | SPI | CAN HAT Board 2 |
| 11 | SPI0 SCLK | SPI | CAN HAT Board 2 |
| 13 | CAN1_1 IRQ | IRQ | CAN HAT Board 1, CAN_1 interrupt |
| 14 | UART TX | UART | GPS PA1616S (/dev/serial0) |
| 15 | UART RX | UART | GPS PA1616S |
| 16 | SPI1 CE2 | SPI | CAN HAT Board 1, CAN_1 |
| 17 | SPI1 CE1 | SPI | CAN HAT Board 1, CAN_0 |
| 18 | PPS | GPIO | GPS pulse-per-second for chrony time sync |
| 19 | SPI1 MISO | SPI | CAN HAT Board 1 (I2S disabled) |
| 20 | SPI1 MOSI | SPI | CAN HAT Board 1 |
| 21 | SPI1 SCLK | SPI | CAN HAT Board 1 |
| 22 | CAN1_0 IRQ | IRQ | CAN HAT Board 1, CAN_0 interrupt |
| 23 | CAN2_0 IRQ | IRQ | CAN HAT Board 2, CAN_0 interrupt (Corner Sensors) |
| 25 | CAN2_1 IRQ | IRQ | CAN HAT Board 2, CAN_1 interrupt (OBD-II) |

**Available GPIOs:**

| GPIO | Potential Use | Notes |
|------|---------------|-------|
| 0, 1 | Reserved | I2C0 HAT EEPROM - avoid |
| 6 | Free | - |
| 12 | Free | UART5 TX only (RX on GPIO13 used by CAN IRQ) |
| 24 | Free | - |
| 26, 27 | Free | - |

## Software Requirements

- Python 3.11+
- Required Python packages:
  - pygame (GUI and rendering)
  - numpy (data processing)
  - numba (JIT compilation for thermal processing)
  - python-can (CAN bus interface, optional for radar)
  - cantools (DBC decoding, optional for radar)
  - tpms-python (TPMS sensor communication)
  - Adafruit libraries (NeoKey, Seesaw, NeoDriver, ICM-20649)

See `requirements.txt` for the complete list.

## Installation

### 1. Flash SD Card

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Select **Raspberry Pi OS Lite (64-bit)** - no desktop needed
3. Click the gear icon to configure:
   - Set hostname (e.g., `open-tpt`)
   - Enable SSH with password authentication
   - Set username `pi` and password
   - Configure WiFi (optional, for initial setup)
4. Flash to SD card and boot the Pi

### 2. Initial Setup

```bash
# SSH into the Pi
ssh pi@<pi-ip-address>

# Update system and install git
sudo apt update && sudo apt install -y git

# Clone the repository
git clone https://github.com/SamSkjord/open-TPT.git
cd open-TPT

# Run the install script
sudo bash ./install.sh

# Wait...
make a cup of tea, this will take a little while

# Reboot to apply config.txt changes (CAN, UART, I2C, etc.)
sudo reboot
```

**Note:** Some harmless warnings may appear during installation:
- `pip upgrade failed` - Normal on Debian-managed Python, script continues with system pip
- `dpkg-statoverride: warning` - Log directories created on first run
- `CMake Deprecation Warning` - SDL2 still builds correctly
- `detached HEAD state` - Normal when cloning specific release tags

The install script handles everything:
- System packages (SDL2, pygame dependencies, audio, GPS, CAN tools)
- Python packages (all Adafruit libraries, numba, python-can, etc.)
- Hardware configuration (I2C, SPI, UART, CAN bus overlays)
- Udev rules (cameras, CAN interfaces)
- Systemd service (auto-start on boot)
- Boot optimisation (quiet boot, splash screen)
- User groups (gpio, i2c, spi, dialout, bluetooth)

### Running the Application

```bash
# Run with hardware (requires sudo for GPIO/I2C access)
sudo ./main.py

# Run in windowed mode (for testing/development)
sudo ./main.py --windowed
```

### Updating

```bash
# Quick sync from development machine (code only)
./tools/quick_sync.sh pi@192.168.199.242

# Or on the Pi, pull and re-run install if dependencies changed
cd /home/pi/open-TPT
git pull
sudo bash ./install.sh
```

### 3. Configure and Enable Read-Only Mode

Once `config.py` is configured for your hardware, enable read-only mode to protect the SD card from corruption on power loss:

```bash
# Edit config.py for your setup (CAN channels, thresholds, etc.)
sudo nano /home/pi/open-TPT/config.py

# Enable read-only root filesystem
sudo ./services/boot/setup-readonly.sh
sudo reboot
```

With read-only mode enabled:
- SD card is protected from writes (no corruption on power loss)
- All persistent data (settings, lap times, telemetry) stored on USB at `/mnt/usb/.opentpt/`
- To make changes, disable read-only mode: `sudo ./services/boot/disable-readonly.sh && sudo reboot`


## Usage

### Running the Application

To run openTPT with hardware:

```bash
sudo python3 ./main.py
```

To run in windowed mode (instead of fullscreen):

```bash
sudo python3 ./main.py --windowed
```

### Controls

When using physical NeoKey 1x4 (board mounted upside down for LED orientation, so physical positions inverted):
- Button 0: Switch view mode (camera pages ↔ UI pages)
- Button 1: Switch within category (camera: rear↔front | UI: cycles through enabled pages)
- Button 2: Page settings (context-sensitive: hide overlay, reset peaks, toggle map view, etc.)
- Button 3: Toggle telemetry recording (hold 1 second to activate)

## Configuration

### Display Configuration

openTPT is designed for 800x480 resolution and scales to other display sizes. Set `DISPLAY_WIDTH` and `DISPLAY_HEIGHT` in `config.py`.

### System Configuration

Hardware and system constants are in `config.py`:
- I2C addresses and bus settings
- CAN channels and bitrates
- Display dimensions and font paths
- Colour thresholds for temperature and pressure
- Default values for user preferences

### User Settings (Persistent)

User preferences changed via the on-screen menu are saved to `~/.opentpt_settings.json` and persist across restarts:
- **Units**: Temperature (C/F), Pressure (PSI/BAR/kPa), Speed (km/h/mph)
- **Camera**: Mirror and rotation for front/rear cameras
- **Display**: Brightness level, bottom gauge selection (SOC/Coolant/Oil/Intake/Fuel/Off)
- **Thresholds**: Tyre, brake, engine temperature warning/critical levels
- **Radar**: Per-unit enabled/disabled state (rear and front independently)
- **Speed source**: OBD or GPS

Settings are saved immediately when changed. If the file doesn't exist, defaults from `config.py` are used.

### Corner Sensor Configuration (CAN Bus)

openTPT uses CAN-based corner sensors for tyre and brake temperature monitoring. Each corner has an Adafruit RP2040 CAN Bus Feather running pico-tyre-temp firmware.

**Features:**
- Tyre thermal imaging (24x32 MLX90640)
- Left/Centre/Right zone temperatures
- Brake temperature monitoring (inner/outer)
- Tyre detection with confidence percentage
- Full frame transfer for installation verification

**CAN Bus Configuration** in `config.py`:

```python
CORNER_SENSOR_CAN_ENABLED = True
CORNER_SENSOR_CAN_CHANNEL = "can_b2_0"
CORNER_SENSOR_CAN_BITRATE = 500000
CORNER_SENSOR_CAN_DBC = "opendbc/pico_tyre_temp.dbc"
```

**Message IDs per corner:**

| Corner | TyreTemps | Detection | BrakeTemps | Status |
|--------|-----------|-----------|------------|--------|
| FL | 0x100 | 0x101 | 0x102 | 0x110 |
| FR | 0x120 | 0x121 | 0x122 | 0x130 |
| RL | 0x140 | 0x141 | 0x142 | 0x150 |
| RR | 0x160 | 0x161 | 0x162 | 0x170 |

**Emissivity Note:** Emissivity is configured in the sensor firmware (default 0.95 for rubber tyres) and reported via the Status message. This is applied during temperature calculation on the sensor itself.

### Brake Temperature Sensors

Brake temperatures are provided by the CAN-based corner sensors alongside tyre temperatures. Each corner sensor reports:
- Inner brake temperature
- Outer brake temperature (dual-zone support)
- Sensor status (OK, Disconnected, Error, NotFound)

**Emissivity** is configured in the corner sensor firmware (default 0.95) and reported via the Status message.
```

**Typical rotor emissivity values:**
- Cast iron (rusty/oxidised): **0.95** (most common, recommended default)
- Cast iron (machined/clean): 0.60-0.70
- Steel (oxidised): 0.80
- Steel (polished): 0.15-0.25
- Ceramic composite: 0.90-0.95

**Note:** Adjust the values to match your specific rotor materials. Using incorrect emissivity values can result in temperature errors of 5-20°C. The correction is applied automatically by the unified corner handler to all brake temperature readings.

### Multi-Camera Configuration

openTPT supports dual USB cameras for rear and front views with seamless switching. The system uses udev rules to provide deterministic camera identification based on USB port location.

#### Hardware Setup

1. Connect cameras to specific USB ports:
   - **Rear camera** → USB port 1.1 (creates `/dev/video-rear`)
   - **Front camera** → USB port 1.2 (creates `/dev/video-front`)

2. Enable cameras in `config.py`:
   ```python
   # Multi-camera configuration
   CAMERA_REAR_ENABLED = True   # Rear camera (with radar overlay if radar enabled)
   CAMERA_FRONT_ENABLED = True  # Front camera (no radar overlay)

   # Camera device paths (if using udev rules for persistent naming)
   CAMERA_REAR_DEVICE = "/dev/video-rear"   # or None for auto-detect
   CAMERA_FRONT_DEVICE = "/dev/video-front"  # or None for auto-detect
   ```

#### Udev Rules Setup

To ensure cameras are correctly identified regardless of boot order, create udev rules:

1. Create `/etc/udev/rules.d/99-camera-names.rules` on your Raspberry Pi:
   ```bash
   # Camera on USB port 1.1 = Rear camera
   SUBSYSTEM=="video4linux", KERNELS=="1-1.1", ATTR{index}=="0", SYMLINK+="video-rear"

   # Camera on USB port 1.2 = Front camera
   SUBSYSTEM=="video4linux", KERNELS=="1-1.2", ATTR{index}=="0", SYMLINK+="video-front"
   ```

2. Reload udev rules:
   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

3. Verify symlinks exist:
   ```bash
   ls -l /dev/video-*
   ```

   You should see:
   ```
   /dev/video-rear -> video0
   /dev/video-front -> video3
   ```
   (Actual device numbers may vary, but symlinks will always be consistent)

#### Finding USB Port Paths

To identify which USB port corresponds to which kernel path:

1. List USB devices with their kernel paths:
   ```bash
   for dev in /dev/video*; do
     udevadm info --query=all --name=$dev | grep -E "DEVNAME|KERNELS"
   done
   ```

2. Or use the system tree:
   ```bash
   ls -la /sys/bus/usb/devices/
   ```

Common USB port mappings on Raspberry Pi 4:
- `1-1.1` = Top-left USB 2.0 port
- `1-1.2` = Bottom-left USB 2.0 port
- `1-1.3` = Top-right USB 2.0 port
- `1-1.4` = Bottom-right USB 2.0 port

**Note:** USB 3.0 ports use different kernel paths (e.g., `2-1`, `2-2`). Adjust the udev rules accordingly if using USB 3.0 ports.

#### Camera Switching Behaviour

- Press Button 0 to switch between camera pages and UI pages
- Press Button 1 (or Spacebar) to switch within the current category:
  - In camera mode: Toggle between rear and front cameras
  - In UI mode: Cycle through enabled pages (telemetry, G-meter, lap timing, fuel, CoPilot)
- Rear radar overlay (chevrons) appears on the rear camera; front radar overlay (distance) appears on the front camera
- Camera switching is seamless with smooth frame transitions (no checkerboard flash)
- Dual FPS counters show both camera feed FPS and overall system FPS

### Radar Configuration

openTPT supports **dual independent radar units** — one rear-facing and one front-facing. Each unit can be a Toyota Denso or Tesla Bosch radar, or disabled. Any combination is supported: 2x Denso, 2x Tesla, Denso+Tesla, or a single unit with the other set to `"none"`.

- **Rear radar** drives the chevron overlay on the rear camera (collision/overtake warnings)
- **Front radar** drives the distance overlay on the front camera

#### Supported Radars

| Aspect | Toyota (Denso) | Tesla (Bosch MRRevo14F) |
|--------|---------------|------------------------|
| Compatible units | Prius/Corolla 2017+ | Any Model S/X/3 unit |
| CAN buses | 2 (radar data + car keepalive) | 1 (single bus, TX+RX) |
| Track count | 16 | 32 |
| Track data | 5 fields (dist, lat, speed, new, valid) | 16+ fields (+ classification, probability, acceleration) |
| Keepalive | ACC_CONTROL + 9 static frames at 100 Hz | ~30 vehicle state messages at 100 Hz |
| VIN | Not needed | Auto-read via UDS at startup |
| DBC files | `toyota_prius_2017_adas.dbc` | `tesla_radar.dbc` + `tesla_can.dbc` |

#### Hardware Setup — Toyota (Denso)

The Toyota Denso radar requires **two CAN buses**: one for keep-alive messages (TX) and one for radar track data (RX).

1. **Waveshare Dual CAN HAT** (Board 1):
   - CAN_0 connector (can_b1_0): Car keep-alive messages (TX to radar)
   - CAN_1 connector (can_b1_1): Radar track output (RX from radar)

2. **Toyota Radar Module** (Prius/Corolla 2017+):
   - Connect to both CAN buses as per wiring diagram
   - Radar will output ~320 Hz track messages once keep-alive is active

**CAN bus sharing:** When running two Denso units, they can share the same car (keep-alive) channel. The system automatically detects this and suppresses duplicate keep-alive messages — only the rear unit sends the 100 Hz ACC_CONTROL frames, while the front unit listens passively on the shared bus.

#### Hardware Setup — Tesla (Bosch MRRevo14F)

The Tesla radar uses a **single CAN bus** for all traffic (TX keepalive + RX tracks).

1. **Waveshare Dual CAN HAT** (Board 1):
   - CAN_0 connector (can_b1_0): Single bus — all radar traffic

2. **Tesla Bosch MRRevo14F radar** (any Model S/X/3 unit):
   - Connect radar CAN1 to the CAN bus
   - VIN is auto-read from the radar via UDS at startup (or set manually)
   - Radar outputs 32 object tracks on 0x310-0x36E at ~1100 msg/s
   - Each track includes object classification (car, truck, bike, pedestrian, unknown) and existence probability

#### Software Configuration

Radar is configured in `config.py` with per-unit settings. Set the type to `"toyota"`, `"tesla"`, or `"none"` for each position:

```python
RADAR_ENABLED = True          # Global radar enable

# Common parameters (shared by both units)
RADAR_INTERFACE = "socketcan"
RADAR_BITRATE = 500000
RADAR_TRACK_TIMEOUT = 0.5

# --- Rear Radar (chevron overlay on rear camera) ---
RADAR_REAR_TYPE = "toyota"                # "none", "toyota", "tesla"
# Toyota rear
RADAR_REAR_CHANNEL = "can_b1_1"           # Track data RX
RADAR_REAR_CAR_CHANNEL = "can_b1_0"       # Keep-alive TX (shareable between Denso units)
RADAR_REAR_DBC = "opendbc/toyota_prius_2017_adas.dbc"
RADAR_REAR_CONTROL_DBC = "opendbc/toyota_prius_2017_pt_generated.dbc"
# Tesla rear
RADAR_REAR_TESLA_CHANNEL = "can_b1_0"
RADAR_REAR_TESLA_DBC = "opendbc/tesla_radar.dbc"
RADAR_REAR_TESLA_VIN = None               # None = auto-read via UDS
RADAR_REAR_TESLA_AUTO_VIN = True

# --- Front Radar (distance overlay on front camera) ---
RADAR_FRONT_TYPE = "none"                 # "none", "toyota", "tesla"
# Toyota front
RADAR_FRONT_CHANNEL = "can_b1_0"
RADAR_FRONT_CAR_CHANNEL = "can_b1_0"      # Can share with rear Denso unit
RADAR_FRONT_DBC = "opendbc/toyota_prius_2017_adas.dbc"
RADAR_FRONT_CONTROL_DBC = "opendbc/toyota_prius_2017_pt_generated.dbc"
# Tesla front
RADAR_FRONT_TESLA_CHANNEL = "can_b1_0"
RADAR_FRONT_TESLA_DBC = "opendbc/tesla_radar.dbc"
RADAR_FRONT_TESLA_VIN = None
RADAR_FRONT_TESLA_AUTO_VIN = True

# Display parameters (rear overlay)
RADAR_CAMERA_FOV = 106.0           # Camera field of view (degrees)
RADAR_TRACK_COUNT = 3              # Number of tracks to display
RADAR_MAX_DISTANCE = 120.0         # Maximum distance (metres)
RADAR_WARN_YELLOW_KPH = 10.0       # Yellow warning threshold
RADAR_WARN_RED_KPH = 20.0          # Red warning threshold
```

**Example configurations:**

| Setup | Rear Type | Front Type | Notes |
|-------|-----------|------------|-------|
| Single rear Denso | `"toyota"` | `"none"` | Default — original single-radar behaviour |
| Single rear Tesla | `"tesla"` | `"none"` | Single Tesla unit on rear camera |
| Dual Denso | `"toyota"` | `"toyota"` | Two Denso units, shared car channel supported |
| Dual Tesla | `"tesla"` | `"tesla"` | Two Tesla units on separate CAN buses |
| Mixed | `"toyota"` | `"tesla"` | Denso rear + Tesla front (or vice versa) |

#### Dependencies

Install cantools for DBC file parsing:
```bash
pip3 install --break-system-packages cantools
```

Or install all dependencies from requirements.txt:
```bash
pip3 install --break-system-packages -r requirements.txt
```

#### Visual Display

**Rear camera** — chevron overlay (from rear radar):
- **Green chevrons**: Vehicle detected, safe distance (<10 km/h closing)
- **Yellow chevrons**: Moderate closing speed (10-20 km/h)
- **Red chevrons**: Rapid approach (>20 km/h closing speed)
- **Blue side arrows**: Overtaking vehicle warning
- **Distance and speed text**: Range in metres and relative velocity

Chevrons are **3x larger (120x108px) and solid-filled** for high visibility.

**Front camera** — distance overlay (from front radar):
- Displays closest tracked object distance in metres
- Configurable via the Front Camera menu (position, text size)

### Read-Only Root Filesystem (SD Card Protection)

openTPT supports a read-only root filesystem to protect the SD card from corruption due to sudden power loss - critical for vehicle-mounted systems where the Pi may lose power when the ignition is turned off.

**How it works:**
- Uses the `overlayroot` package (standard on Debian)
- Root filesystem is mounted read-only (protected)
- All writes go to a RAM overlay (tmpfs)
- User data persists on USB drive at `/mnt/usb/.opentpt/`

**Enable read-only mode:**
```bash
sudo ./services/boot/setup-readonly.sh
sudo reboot
```

**Disable for maintenance:**
```bash
sudo ./services/boot/disable-readonly.sh
sudo reboot
```

**USB Patch Updates:**
With read-only mode enabled, updates are applied via USB patch files. Place `opentpt-patch.tar.gz` on the USB root and reboot - the patch service automatically uses `overlayroot-chroot` to update the underlying filesystem.

See `CLAUDE.md` for detailed documentation.

### CoPilot Configuration

CoPilot provides rally-style audio callouts for upcoming corners, junctions, bridges, and hazards using OpenStreetMap road data and GPS position.

**Map Data Setup:**

1. Download a pre-processed roads database or create one from OSM PBF data
2. Place the `.roads.db` file on the USB drive:
   ```bash
   mkdir -p /mnt/usb/.opentpt/copilot/maps
   cp britain-and-ireland.roads.db /mnt/usb/.opentpt/copilot/maps/
   ```

**Route Files:**

Place GPX or KMZ route files on the USB drive:
- Lap timing routes: `/mnt/usb/.opentpt/routes/`
- CoPilot routes: `/mnt/usb/.opentpt/copilot/routes/`

**Configuration in `config.py`:**

```python
COPILOT_ENABLED = True              # Enable/disable CoPilot
COPILOT_MAP_DIR = "/mnt/usb/.opentpt/copilot/maps"  # Path to roads.db files
COPILOT_LOOKAHEAD_M = 1000          # Corner detection distance (metres)
COPILOT_AUDIO_ENABLED = True        # Enable audio callouts
COPILOT_OVERLAY_ENABLED = True      # Show corner indicator on all pages
```

**Operating Modes:**

- **Just Drive**: Detects corners on whatever road you're currently on
- **Route Follow**: Follows a loaded track/route for junction guidance

**Corner Severity (ASC Scale):**

| Grade | Description | Typical Speed |
|-------|-------------|---------------|
| 1 | Flat out / slight bend | Full throttle |
| 2 | Easy | Lift slightly |
| 3 | Medium | Light braking |
| 4 | Tight | Moderate braking |
| 5 | Very tight | Heavy braking |
| 6 | Hairpin | Near stop |

**Route Integration:**

CoPilot integrates with lap timing - when a track is loaded (KMZ circuit or GPX stage), CoPilot automatically uses the track centerline for junction guidance in Route Follow mode.

**Bluetooth Audio Metadata:**

When connected to a Bluetooth car head unit or speaker, CoPilot provides "Now Playing" information via AVRCP:
- Track title shows the current callout text (e.g., "left 4 tightens into right 3")
- Album art displays the CoPilot logo (splash.png)
- Artist shows "Skjord Motorsport", album shows "CoPilot"

Requires `python3-dbus` and `python3-gi` packages:
```bash
sudo apt install python3-dbus python3-gi
```

## Project Structure

```
openTPT/
├── main.py                              # Entry point + OpenTPT class shell
├── config.py                            # Hardware constants, defaults
├── requirements.txt
├── install.sh                           # Installation script for Raspberry Pi
├── assets/
│   ├── overlay.png                      # Fullscreen static GUI overlay
│   ├── icons/                           # Status, brake, tyre symbols
│   └── themes/                          # Map view colour themes (JSON)
├── core/                                # Core application modules (mixins)
│   ├── __init__.py                      # Exports all mixins
│   ├── initialization.py                # Hardware subsystem init
│   ├── event_handlers.py                # Input/event processing
│   ├── rendering.py                     # Display pipeline
│   ├── telemetry.py                     # Telemetry recording
│   └── performance.py                   # Power/memory monitoring
├── copilot/                             # Rally callout system
│   ├── main.py                          # CoPilot core class
│   ├── map_loader.py                    # OSM roads.db loading
│   ├── path_projector.py                # Road path projection
│   ├── corners.py                       # Corner detection (ASC scale)
│   ├── pacenotes.py                     # Callout generation
│   ├── audio.py                         # espeak-ng/sample playback
│   └── simulator.py                     # GPX route simulation
├── gui/
│   ├── display.py                       # Rendering + temperature overlays
│   ├── camera.py                        # Multi-camera + radar overlay
│   ├── menu/                            # On-screen menu system (modular)
│   │   ├── __init__.py                  # Exports Menu, MenuItem, MenuSystem
│   │   ├── base.py                      # Core menu classes
│   │   ├── bluetooth.py                 # Bluetooth Audio + TPMS pairing
│   │   ├── camera.py                    # Camera settings
│   │   ├── copilot.py                   # CoPilot settings
│   │   ├── lap_timing.py                # Lap timing + track selection
│   │   ├── lights.py                    # NeoDriver LED strip
│   │   ├── map_theme.py                 # Map view theme selection
│   │   ├── settings.py                  # Display, Units, Thresholds, Pages
│   │   └── system.py                    # GPS, IMU, Radar, System Status
│   ├── radar_overlay.py                 # Radar visualisation
│   ├── copilot_display.py               # CoPilot UI page
│   ├── input_threaded.py                # NeoKey 1x4 input handler
│   ├── encoder_input.py                 # Rotary encoder with menu navigation
│   ├── gmeter.py                        # G-meter display with IMU
│   ├── fuel_display.py                  # Fuel tracking display
│   ├── lap_timing_display.py            # Lap timing display
│   ├── icon_handler.py                  # Icon rendering
│   └── scale_bars.py                    # Temperature/pressure scale bars
├── hardware/
│   ├── corner_sensor_handler.py         # Corner sensors via CAN (tyre/brake temps)
│   ├── tpms_input_optimized.py          # TPMS with bounded queues
│   ├── radar_handler.py                 # Radar CAN handler (Toyota + Tesla)
│   ├── obd2_handler.py                  # OBD2/CAN vehicle data
│   ├── gps_handler.py                   # GPS serial NMEA parsing
│   ├── imu_handler.py                   # ICM-20649 IMU for G-meter
│   ├── neodriver_handler.py             # NeoDriver LED strip
│   ├── lap_timing_handler.py            # Lap timing logic
│   └── copilot_handler.py               # CoPilot integration handler
├── lap_timing/                          # Lap timing subsystem
│   ├── data/
│   │   ├── track_loader.py              # KMZ/GPX track loading
│   │   └── track_selector.py            # GPS-based track selection
│   └── utils/
│       └── geometry.py                  # Geospatial utilities
├── services/                            # Pi service configs
│   ├── boot/                            # Boot optimisation, splash service
│   ├── camera/                          # Camera udev rules
│   ├── can/                             # CAN bus udev rules
│   ├── gps/                             # GPS config service
│   └── systemd/                         # CAN setup service
├── utils/
│   ├── settings.py                      # Persistent user settings
│   ├── hardware_base.py                 # Bounded queue base class
│   ├── fuel_tracker.py                  # Fuel consumption tracking
│   ├── lap_timing_store.py              # SQLite lap time persistence
│   ├── telemetry_recorder.py            # CSV telemetry recording
│   ├── theme_loader.py                  # Map view theme loading
│   └── performance.py                   # Performance monitoring
├── usb_data/                            # USB drive data template
│   └── .opentpt/                        # Copy to USB to set up new drive
│       ├── lap_timing/tracks/           # Track databases + KMZ files
│       ├── routes/                      # Lap timing GPX/KMZ routes
│       └── copilot/routes/              # CoPilot GPX routes
└── opendbc/                             # CAN message definitions (DBC files)
```

## Features

### Completed
- Real-time TPMS monitoring (auto-pairing support)
- Brake temperature monitoring via CAN corner sensors (inner/outer zones)
- Tyre thermal imaging via CAN corner sensors (MLX90640 24x32 thermal cameras)
- Dual USB camera support with seamless switching (up to 26fps depending on camera hardware)
- Deterministic camera identification via udev rules
- NeoKey 1x4 physical controls
- Rotary encoder input with menu system
- Performance-optimised architecture with bounded queues
- Lock-free rendering (≤12ms per frame target)
- Numba JIT thermal processing (< 1ms per sensor)
- Dynamic resolution scaling
- UI auto-hide with fade animation
- Dual radar support with collision warnings (Toyota Denso + Tesla Bosch, independent front/rear)
- NeoDriver LED strip (shift lights, delta, overtake modes)
- Performance monitoring and validation
- TPMS sensor pairing via on-screen menu
- Bluetooth audio pairing for CoPilot callouts
- Telemetry recording to CSV (10Hz)
- GPS handler with 10Hz serial NMEA parsing
- Lap timing with persistence (best laps saved to SQLite)
- Fuel tracking with OBD2 integration (level, consumption, laps remaining)
- Temperature overlays on tyre zones and brake displays
- Persistent user settings (~/.opentpt_settings.json)
- Config hot-reload via menu
- CoPilot rally callouts (corners, junctions, hazards from OSM data)
- Unified route system (GPX stages and KMZ circuit tracks)
- Read-only root filesystem with overlayroot (SD card corruption protection)
- USB-based persistent storage (settings, lap times, tracks survive rootfs changes)
- USB patch deployment (offline updates with automatic overlay handling)

### Future Enhancements
- CAN bus scheduler for multi-bus OBD-II data
- Web-based remote monitoring
- Additional radar compatibility (Continental, Delphi)
- Buildroot image - minimal Linux for sub-5s boot, tiny footprint

### Might Get Round To It One Day
- SDL2 hardware rendering - use opengles2 renderer instead of software blitting for GPU acceleration
- Data logging to cloud storage

### Hardware TODO
- [x] PA1616S Adafruit GPS - for lap timing and position logging
- [x] Adafruit NeoDriver - LED strip control (delta, overtake, shift, rainbow modes)
- [x] Brake temperature sensors - now via CAN corner sensors (inner/outer zones)
- [ ] LTR-559 Auto brightness - ambient light sensor for automatic display brightness (enable/disable + offset settings)
- [x] Mini OLED display - secondary display for delta time and fuel data (OLED Bonnet)
- [x] Migrate corner sensors to CAN bus - CAN more robust than I2C for automotive environments; all four corners on can_b2_0
- [x] Direct TPMS serial connection - TPMS receiver via UART3 (GPIO4/5) at 19200 baud; frees USB port
- [x] TOF laser sensor CAN device - front distance measurement displayed on front camera view (Pico CAN Ranger)
- [ ] ANT+ heart rate monitoring - driver heart rate logging via ANT+ USB dongle
- [ ] CHT sensor - 14mm under spark plug cylinder head temperature (thermomart.com/14mm-under-spark-plug)
- [ ] Suspension sensors - strain gauge load cells for force and linear potentiometers for travel (strainblog.micro-measurements.com/content/measuring-load-raspberry-pi)

### Software TODO
- [x] Bluetooth audio menu - scan, pair, connect, disconnect, forget (requires PulseAudio)
- [x] Display menu - encoder-based brightness control
- [x] Lap timing integration - GPS lap timing with persistence
- [x] CoPilot integration
- [ ] TPMS menu expansion - swap corners, view sensor data
- [x] TPMS serial port config - TPMS_SERIAL_PORT in config.py for direct UART connection (/dev/ttyAMA3)
- [x] Tyre temps menu - corner sensor details, full frame view for installation verification, flip inner/outer
- [x] Camera view options - mirror, rotate settings for front/rear cameras
- [x] Units menu - C/F, PSI/BAR/kPa, km/h/mph switching
- [x] Alerts/Warnings menu - temperature/pressure thresholds for visual warnings
- [ ] Recording settings - output directory, auto-start on motion detection
- [ ] G-meter settings - reset peaks, max G range, history duration
- [x] Radar settings - enable/disable, sensitivity, overlay options, invert for upside-down mounting
- [x] System info - IP address, storage space, uptime, sensor status
- [ ] Pi power status/throttling - show vcgencmd get_throttled status on system info page
- [ ] Network/WiFi menu - connect for remote access
- [x] IMU calibration wizard - zero offset calibration via menu
- [x] Power menu - screen timeout, safe shutdown
- [x] Track selection - for lap timing
- [x] Config persistence - persistent settings via ~/.opentpt_settings.json
- [x] Config hot-reload - reload settings from menu without restart
- [x] Read-only rootfs - overlayroot-based SD card corruption protection
- [x] USB persistent storage - settings, lap times, tracks on USB drive
- [x] USB patch deployment - offline updates with automatic overlay handling
- [ ] Configurable OBD2 PIDs - move to config.py with key, mode, pid, bytes, formula, priority, smoothing
- [x] Bottom gauge selection - choose data source for bottom status bar (SOC, coolant, oil, intake, fuel, off)
- [ ] Top bar configuration - choose which PIDs/data to display on top status bar

- [ ] Lap corner analysis logging - per lap, per corner: min speeds, yaw acceleration
- [x] Pitlane timer - countdown/countup timer for pitlane speed limits and pit stop duration
- [x] Fuel tracking page - average fuel per lap, laps remaining, fuel used this session
- [ ] Tyre temp graphs - show tyre temperature graphs on edges of track timer and camera views
- [ ] Gear-based shift points - optimal shift RPM per gear based on torque curve crossover (glennmessersmith.com/shiftpt.html)
- [ ] Tyre slip indicator - compare wheel speed (OBD2) vs ground speed (GPS) to show acceleration/braking slip percentage
- [ ] Steering angle - read steering angle sensor via OBD2/CAN for oversteer/understeer analysis
- [ ] Brake input - pedal force sensor (driver input) and hydraulic line pressure for brake analysis

### Bugs
- [ ] Camera settings menu always opens on rear camera even when front camera is selected
- [ ] Menu status bar text is horizontally aligned with the bottom of the menu square, appears to have a line through it - adjust spacing

## Troubleshooting

### Quick Checks

```bash
# Check service status
ssh pi@<ip> "sudo systemctl status openTPT.service"

# View live logs
ssh pi@<ip> "sudo journalctl -u openTPT.service -f"

# Check I2C devices (should see 0x30, 0x36, 0x60, 0x68)
ssh pi@<ip> "sudo i2cdetect -y 1"

# Check CAN interfaces
ssh pi@<ip> "ip link show | grep can"

# Check cameras
ssh pi@<ip> "ls -l /dev/video-*"

# Check throttling (0x0 = OK)
ssh pi@<ip> "vcgencmd get_throttled && vcgencmd measure_temp"
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Service won't start | Check logs: `journalctl -u openTPT.service -n 50` |
| I2C devices not found | Verify I2C enabled: `ls /dev/i2c-*` |
| CAN interfaces missing | Reboot after install, check `dmesg \| grep mcp` |
| Camera not detected | Check USB port assignment and udev rules |
| Read-only mode issues | Disable: `sudo ./services/boot/disable-readonly.sh && sudo reboot` |

## Development

### Quick Sync (Mac to Pi)

```bash
# Sync code changes (doesn't reinstall dependencies)
./tools/quick_sync.sh pi@<pi-ip>

# Auto-sync on file changes
brew install fswatch
fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@<pi-ip>
```

### Local Development (No Hardware)

```bash
pip3 install pygame numpy pillow
./main.py --windowed
```

## Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Complete project documentation (this file) |
| `CHANGELOG.md` | Version history and features |
| `CLAUDE.md` | AI assistant context guide |

## Acknowledgements

- Map view themes adapted from [maptoposter](https://github.com/originalankur/maptoposter) by Ankur Gupta

## License

This project is licensed under the MIT License - see the LICENSE file for details.
