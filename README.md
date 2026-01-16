# openTPT - Open Tyre Pressure and Temperature Telemetry

A modular GUI system for live racecar telemetry using a Raspberry Pi 4 with HDMI display support.
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/SamSkjord/open-TPT)

## Overview

openTPT provides real-time monitoring of:
- Tyre pressure and temperature (via TPMS)
- Brake rotor temperatures (via IR sensors + ADC)
- Tyre surface thermal imaging (via Pico I2C slave modules with MLX90640, or MLX90614 sensors)
- Multi-camera support with seamless switching (dual USB UVC cameras)
- Toyota radar overlay on rear camera (CAN bus radar with collision warnings)
- Fuel tracking with consumption rate and laps remaining estimation
- GPS lap timing with delta display
- NeoDriver LED strip for shift lights, delta, and overtake warnings

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
- Raspberry Pi 4 (2GB+ RAM recommended)
- Waveshare 1024x600 HDMI display (or other HDMI displays - UI designed for 800x480, scales to fit)
- TPMS receivers and sensors
- ADS1115/ADS1015 ADC for IR brake temperature sensors
- Tyre temperature sensors (configurable per tyre):
  - Raspberry Pi Pico with MLX90640 thermal camera (pico-tyre-temp I2C slave modules), OR
  - MLX90614 single-point IR sensors
  - **Mix and match**: Use Pico modules on front tyres and MLX90614 on rear tyres (or any combination)
- TCA9548A I2C multiplexer for tyre temperature sensors (channels 0-3)
- Adafruit NeoKey 1x4 for input control

### Optional Components
- USB UVC cameras (up to 2 cameras for rear/front views with seamless switching)
- Toyota radar with CAN interface (for radar overlay on rear camera):
  - Dual CAN bus support (radar data + car keepalive)
  - Compatible Toyota radar unit (e.g., Prius 2017)
  - CAN-to-USB adapters or SPI CAN controllers
  - DBC files for radar decoding
- Dual Waveshare 2-CH CAN HAT+ stack on the Waveshare CM4-POE-UPS-BASE for multi-bus CAN/OBD work (see `DEPLOYMENT.md` for hardware setup)

## Software Requirements

- Python 3.7+
- Required Python packages:
  - pygame (GUI and rendering)
  - numpy (data processing)
  - numba (JIT compilation for thermal processing)
  - python-can (CAN bus interface, optional for radar)
  - cantools (DBC decoding, optional for radar)
  - tpms-python (TPMS sensor communication)
  - Adafruit libraries (NeoKey, ADS1x15, TCA9548A, MLX90614)

See `requirements.txt` for the complete list.

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/open-TPT.git
cd open-TPT
```

2. Install dependencies:
```bash
pip3 install -r requirements.txt
```

3. (Optional) For Numba acceleration:
```bash
pip3 install numba
```

4. (Optional) For radar overlay support:
```bash
pip3 install python-can cantools
# Copy toyota_radar_driver.py to your project or install as package
```

5. (Optional) For Bluetooth audio support:
```bash
sudo apt install pulseaudio pulseaudio-module-bluetooth
```

6. Run the application:
```bash
sudo python3 ./main.py
```
Note: `sudo` is required for GPIO and I2C hardware access.

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

When using physical NeoKey 1x4:
- Button 0: Cycle brightness (30% → 50% → 70% → 90% → 100%)
- Button 1: Page settings (context-sensitive: hide overlay, reset peaks, etc.)
- Button 2: Switch within category (camera: rear↔front | UI: telemetry↔G-meter)
- Button 3: Switch view mode (camera pages ↔ UI pages)

Keyboard controls (for development):
- Up arrow: Cycle brightness
- Down arrow or 'T' key: Page settings
- Spacebar: Switch within category
- Right arrow: Switch view mode (camera ↔ UI)
- ESC: Exit application

## Configuration

### Display Configuration

openTPT is designed for 800x480 resolution and scales to other display sizes. Set `DISPLAY_WIDTH` and `DISPLAY_HEIGHT` in `utils/config.py`.

### System Configuration

Hardware and system constants are in `utils/config.py`:
- I2C addresses and bus settings
- CAN channels and bitrates
- Display dimensions and font paths
- Colour thresholds for temperature and pressure
- Default values for user preferences

### User Settings (Persistent)

User preferences changed via the on-screen menu are saved to `~/.opentpt_settings.json` and persist across restarts:
- **Units**: Temperature (C/F), Pressure (PSI/BAR/kPa), Speed (km/h/mph)
- **Camera**: Mirror and rotation for front/rear cameras
- **Display**: Brightness level
- **Radar**: Enabled/disabled state
- **Speed source**: OBD or GPS

Settings are saved immediately when changed. If the file doesn't exist, defaults from `config.py` are used.

### Tyre Sensor Configuration

openTPT supports per-tyre sensor type configuration, allowing you to mix Pico I2C slave modules (with MLX90640 thermal cameras) and MLX90614 single-point IR sensors.

**Emissivity Note:** Pico modules with MLX90640 sensors have emissivity pre-configured in the Pico firmware (default 0.95 for rubber tyres, configurable via I2C register). This is applied during temperature calculation on the Pico itself, not in openTPT.

Edit `utils/config.py` and configure the `TYRE_SENSOR_TYPES` dictionary:

```python
TYRE_SENSOR_TYPES = {
    "FL": "pico",      # Front Left - Pico module with MLX90640
    "FR": "pico",      # Front Right - Pico module with MLX90640
    "RL": "mlx90614",  # Rear Left - MLX90614 single-point IR
    "RR": "mlx90614",  # Rear Right - MLX90614 single-point IR
}
```

**Sensor type options:**
- `"pico"` - Raspberry Pi Pico I2C slave module with MLX90640 thermal camera
  - Provides detailed thermal imaging with left/centre/right zone data
  - Requires pico-tyre-temp firmware on the Pico
  - Connected via I2C multiplexer (TCA9548A)

- `"mlx90614"` - MLX90614 single-point IR temperature sensor
  - Simpler, lower-cost alternative
  - Single temperature reading per tyre
  - Connected via I2C multiplexer (TCA9548A)

**I2C multiplexer channel assignments:**

Configure channels for each sensor type in `utils/config.py`:

```python
# Pico I2C slave modules (MLX90640 thermal cameras)
PICO_MUX_CHANNELS = {
    "FL": 0,  # Front Left on channel 0
    "FR": 1,  # Front Right on channel 1
    "RL": 2,  # Rear Left on channel 2
    "RR": 3,  # Rear Right on channel 3
}

# MLX90614 single-point IR sensors
MLX90614_MUX_CHANNELS = {
    "FL": 0,  # Front Left on channel 0
    "FR": 1,  # Front Right on channel 1
    "RL": 2,  # Rear Left on channel 2
    "RR": 3,  # Rear Right on channel 3
}
```

**Note:** Both sensor types can share the same channel numbers if they're not used on the same positions. For example, if FL/FR use Pico modules on channels 0/1, and RL/RR use MLX90614 sensors, they can also use channels 0/1 (or 2/3).

### Brake Temperature Sensor Configuration

openTPT supports per-corner brake sensor type configuration with automatic emissivity correction for accurate temperature readings.

#### Sensor Types

Edit `utils/config.py` to configure the `BRAKE_SENSOR_TYPES` dictionary:

```python
BRAKE_SENSOR_TYPES = {
    "FL": "mlx90614",  # Front Left - MLX90614 IR sensor
    "FR": "adc",       # Front Right - ADC IR sensor
    "RL": "adc",       # Rear Left - ADC IR sensor
    "RR": "adc",       # Rear Right - ADC IR sensor
}
```

**Sensor type options:**
- `"mlx90614"` - MLX90614 single-point IR sensor via I2C multiplexer
- `"adc"` - IR sensor via ADS1115 ADC (4 channels available)
- `"obd"` - CAN/OBD-II (rarely available, most vehicles don't broadcast brake temps)

#### Emissivity Correction

**All IR sensors assume perfect black body emissivity (ε = 1.0) by default.** Since brake rotors have lower emissivity (typically 0.95 for oxidised cast iron), the sensors will read lower than actual temperature. openTPT automatically applies software emissivity correction to compensate.

**Note on Tyre vs Brake Emissivity Handling:**
- **Tyre sensors (MLX90640 via Pico):** Emissivity is configured in the Pico firmware (default 0.95 for rubber) and applied during temperature calculation by the MLX90640 API. No additional correction needed in openTPT.
- **Brake sensors (MLX90614/ADC):** Sensors use factory default ε = 1.0, so openTPT applies software correction to compensate for actual rotor emissivity (typically 0.95 for cast iron).

Both approaches achieve the same result - accurate temperature readings - using different implementation methods appropriate to each sensor type.

**How it works:**
1. MLX90614/IR sensor has factory default ε = 1.0 (not changed in hardware)
2. Actual brake rotor has lower emissivity (e.g., ε = 0.95)
3. Sensor reads lower than actual due to less radiation from non-black-body surface
4. Software correction adjusts reading upward: `T_actual = T_measured / ε^0.25`

Configure per-corner emissivity values in `utils/config.py`:

```python
BRAKE_ROTOR_EMISSIVITY = {
    "FL": 0.95,  # Front Left - typical oxidised cast iron
    "FR": 0.95,  # Front Right
    "RL": 0.95,  # Rear Left
    "RR": 0.95,  # Rear Right
}
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

2. Enable cameras in `utils/config.py`:
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

#### Camera Switching Behavior

- Press Button 2 (or Spacebar) to cycle through views: Telemetry → Rear Camera → Front Camera → Telemetry
- When radar is enabled, the overlay only appears on the rear camera view
- Camera switching is seamless with smooth frame transitions (no checkerboard flash)
- Dual FPS counters show both camera feed FPS and overall system FPS

### Radar Configuration

The Toyota radar overlay is now **enabled by default** and displays collision warnings on the rear camera.

#### Hardware Setup

1. **Waveshare Dual CAN HAT** (Board 1):
   - CAN_0 connector (can_b1_0): Car keep-alive messages (TX to radar)
   - CAN_1 connector (can_b1_1): Radar track output (RX from radar)

2. **Toyota Radar Module** (Prius/Corolla 2017+):
   - Connect to both CAN buses as per wiring diagram
   - Radar will output ~320 Hz track messages

#### Software Configuration

The radar is configured in `utils/config.py`:

```python
# Enable/disable radar overlay
RADAR_ENABLED = True  # Now enabled by default

# CAN channel configuration (for Waveshare Dual CAN HAT)
RADAR_CHANNEL = "can_b1_1"  # Radar outputs tracks here
CAR_CHANNEL = "can_b1_0"    # Keep-alive sent here
RADAR_INTERFACE = "socketcan"
RADAR_BITRATE = 500000

# DBC files (included in opendbc/ directory)
RADAR_DBC = "opendbc/toyota_prius_2017_adas.dbc"
CONTROL_DBC = "opendbc/toyota_prius_2017_pt_generated.dbc"

# Display parameters
RADAR_CAMERA_FOV = 106.0           # Camera field of view (degrees)
RADAR_TRACK_COUNT = 3              # Number of tracks to display
RADAR_MAX_DISTANCE = 120.0         # Maximum distance (metres)
RADAR_WARN_YELLOW_KPH = 10.0       # Yellow warning threshold
RADAR_WARN_RED_KPH = 20.0          # Red warning threshold
```

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

When enabled, the radar overlay shows on the **rear camera only**:
- **Green chevrons**: Vehicle detected, safe distance (<10 km/h closing)
- **Yellow chevrons**: Moderate closing speed (10-20 km/h)
- **Red chevrons**: Rapid approach (>20 km/h closing speed)
- **Blue side arrows**: Overtaking vehicle warning
- **Distance and speed text**: Range in metres and relative velocity

Chevrons are **3x larger (120×108px) and solid-filled** for high visibility.

## Project Structure

```
openTPT/
├── main.py                              # App entrypoint
├── requirements.txt
├── install.sh                           # Installation script for Raspberry Pi
├── assets/
│   ├── overlay.png                      # Fullscreen static GUI overlay
│   └── icons/                           # Status, brake, tyre symbols
├── gui/
│   ├── display.py                       # Draw pressure, temps, heatmaps
│   ├── camera.py                        # Rear-view USB camera with radar overlay
│   ├── radar_overlay.py                 # Radar track rendering
│   ├── input.py                         # NeoKey 1x4 (brightness + camera toggle)
│   ├── icon_handler.py                  # Icon rendering
│   └── scale_bars.py                    # Temperature/pressure scale bars
├── hardware/
│   ├── unified_corner_handler.py        # Unified handler for all tyre sensors
│   ├── tpms_input_optimized.py          # TPMS with bounded queues
│   ├── mlx90614_handler.py              # MLX90614 single-point IR sensors
│   ├── radar_handler.py                 # Toyota radar CAN handler (optional)
│   └── i2c_mux.py                       # TCA9548A Mux control
├── utils/
│   ├── config.py                        # Hardware constants, defaults
│   ├── settings.py                      # Persistent user settings (~/.opentpt_settings.json)
│   ├── hardware_base.py                 # Bounded queue base class
│   └── performance.py                   # Performance monitoring
└── scratch/
    └── sources/                         # Source code for external libraries
        ├── TPMS/
        ├── toyota-radar/
        └── uvc-radar-overlay/
```

## Features

### Completed
- Real-time TPMS monitoring (auto-pairing support)
- Brake temperature monitoring with IR sensors (MCP9601 thermocouples and MLX90614)
- Tyre thermal imaging via Pico I2C slaves (MLX90640) or MLX90614 sensors
- Dual USB camera support with seamless switching (60 FPS target)
- Deterministic camera identification via udev rules
- NeoKey 1x4 physical controls
- Rotary encoder input with menu system
- Performance-optimised architecture with bounded queues
- Lock-free rendering (≤12ms per frame target)
- Numba JIT thermal processing (< 1ms per sensor)
- Dynamic resolution scaling
- UI auto-hide with fade animation
- Toyota radar overlay with collision warnings
- NeoDriver LED strip (shift lights, delta, overtake modes)
- Performance monitoring and validation
- TPMS sensor pairing via on-screen menu
- Bluetooth audio pairing for CopePilot
- Telemetry recording to CSV (10Hz)
- GPS handler with 10Hz serial NMEA parsing
- Lap timing with persistence (best laps saved to SQLite)
- Fuel tracking with OBD2 integration (level, consumption, laps remaining)
- Temperature overlays on tyre zones and brake displays
- Persistent user settings (~/.opentpt_settings.json)
- Config hot-reload via menu

### Future Enhancements
- CAN bus scheduler for multi-bus OBD-II data
- Web-based remote monitoring
- Additional radar compatibility (other manufacturers)
- Buildroot image - minimal Linux for sub-5s boot, read-only root, tiny footprint

### Might Get Round To It One Day
- SDL2 hardware rendering - use opengles2 renderer instead of software blitting for GPU acceleration
- Data logging to cloud storage

### Hardware TODO
- [x] PA1616S Adafruit GPS - for lap timing and position logging
- [x] Adafruit NeoDriver - LED strip control (delta, overtake, shift, rainbow modes)
- [x] MCP9601 Thermocouples - brake temperature sensors (per corner)
- [ ] LTR-559 Auto brightness - ambient light sensor for automatic display brightness (enable/disable + offset settings)
- [ ] Mini OLED display - secondary display for delta time and fuel data
- [ ] I2C bus reorganisation - main bus for IO, mux ch0 for external display/IO, ch1-4 for corners, ch5 for engine sensors, ch6 reserved (pedal sensors etc)

### Software TODO
- [x] Bluetooth audio menu - scan, pair, connect, disconnect, forget (requires PulseAudio)
- [x] Display menu - encoder-based brightness control
- [x] Lap timing integration - GPS lap timing with persistence
- [ ] CopePilot integration
- [ ] TPMS menu expansion - swap corners, view sensor data
- [ ] Tyre temps menu - corner sensor details, full frame view for installation verification, flip inner/outer
- [x] Camera view options - mirror, rotate settings for front/rear cameras
- [x] Units menu - C/F, PSI/BAR/kPa, km/h/mph switching
- [ ] Alerts/Warnings menu - temperature/pressure thresholds for visual warnings
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
- [ ] Configurable OBD2 PIDs - move to config.py with key, mode, pid, bytes, formula, priority, smoothing

- [ ] Lap corner analysis logging - per lap, per corner: min speeds, yaw acceleration
- [ ] Pitlane timer - countdown/countup timer for pitlane speed limits and pit stop duration
- [x] Fuel tracking page - average fuel per lap, laps remaining, fuel used this session
- [ ] Tyre temp graphs - show tyre temperature graphs on edges of track timer and camera views

### Bugs
- [ ] Camera settings menu always opens on rear camera even when front camera is selected

## Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Complete project documentation (this file) |
| `QUICKSTART.md` | Quick reference for daily use |
| `DEPLOYMENT.md` | Deployment workflow and troubleshooting |
| `CHANGELOG.md` | Version history and features |
| `CLAUDE.md` | AI assistant context guide |

## License

This project is licensed under the MIT License - see the LICENSE file for details.
