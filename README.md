# openTPT - Open Tyre Pressure and Temperature Telemetry

A modular GUI system for live racecar telemetry using a Raspberry Pi 4 and HyperPixel display.
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/SamSkjord/open-TPT)

## Overview

openTPT provides real-time monitoring of:
- 🛞 Tyre pressure & temperature (via TPMS)
- 🔥 Brake rotor temperatures (via IR sensors + ADC)
- 🌡️ Tyre surface heatmaps (via MLX90640 thermal cameras)
- 🎥 Full-screen rear-view toggle (USB UVC camera)
- 📡 Optional Toyota radar overlay (CAN bus radar with collision warnings)

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
- Display options:
  - HyperPixel display (800x480 resolution), or
  - Standard HDMI display of any resolution (system now supports dynamic scaling)
- TPMS receivers and sensors
- ADS1115/ADS1015 ADC for IR brake temperature sensors
- MLX90640 thermal cameras (one per tyre)
- TCA9548A I2C multiplexer for thermal cameras
- Adafruit NeoKey 1x4 for input control

### Optional Components
- USB UVC camera (for rear view)
- Toyota radar with CAN interface (for radar overlay):
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
  - thermal-tyre-driver (MLX90640 thermal cameras)
  - Adafruit libraries (NeoKey, ADS1x15, TCA9548A)

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
- Button 2: Toggle rear-view camera
- Button 3: Toggle UI overlay visibility

Keyboard controls (for development):
- Up/Down arrows: Increase/decrease brightness
- Spacebar: Toggle rear-view camera
- 'T' key: Toggle UI overlay visibility
- ESC: Exit application

## Configuration

### Display Configuration

openTPT now supports any display resolution. To configure your display:

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
│   ├── tpms_input_optimized.py          # TPMS with bounded queues
│   ├── ir_brakes_optimized.py           # Brake temps with EMA smoothing
│   ├── mlx_handler_optimized.py         # MLX90640 with zone processing
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
        ├── thermal-tyre-driver/
        ├── toyota-radar/
        └── uvc-radar-overlay/
```

## Features

### Completed ✓
- ✅ Real-time TPMS monitoring (auto-pairing support)
- ✅ Brake temperature monitoring with IR sensors
- ✅ MLX90640 thermal camera heatmaps (I/C/O zone analysis)
- ✅ USB camera rear-view with 60 FPS target
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

## License

This project is licensed under the MIT License - see the LICENSE file for details.
