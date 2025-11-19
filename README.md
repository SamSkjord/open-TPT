# openTPT - Open Tyre Pressure and Temperature Telemetry

A modular GUI system for live racecar telemetry using a Raspberry Pi 4 with HDMI display support.
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/SamSkjord/open-TPT)

## Overview

openTPT provides real-time monitoring of:
- 🛞 Tyre pressure & temperature (via TPMS)
- 🔥 Brake rotor temperatures (via IR sensors + ADC)
- 🌡️ Tyre surface thermal imaging (via Pico I2C slave modules with MLX90640, or MLX90614 sensors)
- 🎥 Multi-camera support with seamless switching (dual USB UVC cameras)
- 📡 Optional Toyota radar overlay on rear camera (CAN bus radar with collision warnings)

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
- Dual Waveshare 2-CH CAN HAT+ stack on the Waveshare CM4-POE-UPS-BASE for multi-bus CAN/OBD work (see `WAVESHARE_DUAL_CAN_HAT_SETUP.md` for wiring, device-tree overlays, and deterministic interface naming instructions applied by `install.sh`)

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

5. Run the application:
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
- Button 0: Increase brightness
- Button 1: Decrease brightness
- Button 2: Toggle camera view (telemetry ↔ rear camera ↔ front camera)
- Button 3: Toggle UI overlay visibility

Keyboard controls (for development):
- Up/Down arrows: Increase/decrease brightness
- Spacebar: Toggle camera view (telemetry ↔ rear camera ↔ front camera)
- 'T' key: Toggle UI overlay visibility
- ESC: Exit application

## Configuration

### Display Configuration

openTPT is designed for 800x480 resolution and scales to other display sizes. To configure your display:

1. Run the configuration utility:
   ```
   python3 configure_display.py
   ```

2. Options:
   - Show current settings: `python3 configure_display.py --show`
   - Auto-detect resolution: `python3 configure_display.py --detect`
   - Set resolution manually: `python3 configure_display.py --width 1280 --height 720`

The display settings are stored in `display_config.json` in the project root directory.

### System Configuration

Other system settings can be configured by editing the `utils/config.py` file, which contains settings for:
- FPS target and brightness
- Positions for telemetry indicators (automatically scaled based on resolution)
- Colour thresholds for temperature and pressure
- I2C addresses and bus settings
- Unit preferences (Celsius/Fahrenheit, PSI/BAR/kPa)

### Tyre Sensor Configuration

openTPT supports per-tyre sensor type configuration, allowing you to mix Pico I2C slave modules (with MLX90640 thermal cameras) and MLX90614 single-point IR sensors.

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

To enable the optional radar overlay feature:

1. Edit `utils/config.py` and set:
   ```python
   RADAR_ENABLED = True
   ```

2. Configure CAN channels and DBC files:
   ```python
   RADAR_CHANNEL = "can0"      # CAN channel for radar data
   CAR_CHANNEL = "can1"        # CAN channel for car keepalive
   RADAR_INTERFACE = "socketcan"
   RADAR_BITRATE = 500000
   RADAR_DBC = "opendbc/toyota_prius_2017_adas.dbc"
   CONTROL_DBC = "opendbc/toyota_prius_2017_pt_generated.dbc"
   ```

3. Configure radar display parameters:
   ```python
   RADAR_CAMERA_FOV = 106.0           # Camera field of view (degrees)
   RADAR_TRACK_COUNT = 3              # Number of tracks to display
   RADAR_MAX_DISTANCE = 120.0         # Maximum distance (metres)
   RADAR_WARN_YELLOW_KPH = 10.0       # Yellow warning threshold
   RADAR_WARN_RED_KPH = 20.0          # Red warning threshold
   ```

When enabled, the radar overlay will display:
- Green/yellow/red chevron arrows showing track positions
- Distance and relative speed for each track
- Overtake warning arrows when vehicles are rapidly approaching from the sides

## Project Structure

```
openTPT/
├── main.py                              # App entrypoint
├── requirements.txt
├── deploy_to_pi.sh                      # Deployment script for Raspberry Pi
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
├── perception/
│   └── tyre_zones.py                    # Numba-optimised I/C/O zone processor
├── utils/
│   ├── config.py                        # Constants: positions, colours, thresholds
│   ├── hardware_base.py                 # Bounded queue base class
│   └── performance.py                   # Performance monitoring
└── scratch/
    └── sources/                         # Source code for external libraries
        ├── TPMS/
        ├── toyota-radar/
        └── uvc-radar-overlay/
```

## Features

### Completed ✓
- ✅ Real-time TPMS monitoring (auto-pairing support)
- ✅ Brake temperature monitoring with IR sensors
- ✅ Tyre thermal imaging via Pico I2C slaves (MLX90640) or MLX90614 sensors
- ✅ Dual USB camera support with seamless switching (60 FPS target)
- ✅ Deterministic camera identification via udev rules
- ✅ NeoKey 1x4 physical controls
- ✅ Performance-optimised architecture with bounded queues
- ✅ Lock-free rendering (≤12ms per frame target)
- ✅ Numba JIT thermal processing (< 1ms per sensor)
- ✅ Dynamic resolution scaling
- ✅ UI auto-hide with fade animation
- ✅ Optional Toyota radar overlay with collision warnings
- ✅ Performance monitoring and validation

### Future Enhancements
- CAN bus scheduler for OBD-II data
- GPS lap timing integration
- Data logging and telemetry export
- Web-based remote monitoring
- Additional radar compatibility (other manufacturers)

## Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Complete project documentation (this file) |
| `QUICKSTART.md` | Quick reference for daily use |
| `DEPLOYMENT.md` | Deployment workflow and troubleshooting |
| `PERFORMANCE_OPTIMIZATIONS.md` | Technical implementation details |
| `WAVESHARE_DUAL_CAN_HAT_SETUP.md` | CAN hardware configuration |
| `CHANGELOG.md` | Version history and features |
| `open-TPT_System_Plan.md` | Long-term architecture plan |
| `AI_CONTEXT.md` | AI assistant onboarding guide |

## License

This project is licensed under the MIT License - see the LICENSE file for details.
