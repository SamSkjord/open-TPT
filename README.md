# openTPT - Open Tyre Pressure and Temperature Telemetry

A modular GUI system for live racecar telemetry using a Raspberry Pi 4 and HyperPixel display.

## Overview

openTPT provides real-time monitoring of:
- 🛞 Tyre pressure & temperature (via TPMS)
- 🔥 Brake rotor temperatures (via IR sensors + ADC)
- 🌡️ Tyre surface heatmaps (via MLX90640 thermal cameras)
- 🎥 Full-screen rear-view toggle (USB UVC camera)

The system is designed for racing applications where real-time monitoring of tyre and brake conditions is critical for optimal performance and safety.

## Hardware Requirements

- Raspberry Pi 4 (2GB+ RAM recommended)
- Display options:
  - HyperPixel display (800x480 resolution), or
  - Standard HDMI display of any resolution (system now supports dynamic scaling)
- TPMS receivers and sensors
- ADS1115/ADS1015 ADC for IR brake temperature sensors
- MLX90640 thermal cameras (one per tyre)
- TCA9548A I2C multiplexer for thermal cameras
- Adafruit NeoKey 1x4 for input control
- USB UVC camera (optional, for rear view)

## Software Requirements

- Python 3.7+
- Required Python packages (see requirements.txt)

## Installation

1. Clone this repository:
```
git clone https://github.com/yourusername/open-TPT.git
cd open-TPT
```

## Usage

### Running the Application

To run openTPT in normal mode (with hardware):

```
./main.py
```

For development or testing without hardware, use mock mode:

```
./main.py --mock
```

To run in windowed mode (instead of fullscreen):

```
./main.py --windowed
```

### Controls

When using physical NeoKey 1x4:
- Button 0: Increase brightness
- Button 1: Decrease brightness
- Button 2: Toggle rear-view camera
- Button 3: Reserved for future use

Keyboard controls (for development):
- Up/Down arrows: Increase/decrease brightness
- Spacebar: Toggle rear-view camera
- 'M' key: Toggle mock mode
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
- Color thresholds for temperature and pressure
- Mock mode parameters
- I2C addresses and bus settings

## Development Mode

The mock mode allows development and testing without physical hardware. In this mode:
- TPMS data is simulated with realistic variations
- Brake temperatures are simulated with realistic behavior
- Thermal cameras show simulated heat patterns
- All hardware interfaces gracefully handle missing devices

## Project Structure

```
openTPT/
├── main.py                      # App entrypoint
├── requirements.txt
├── assets/
│   ├── overlay.png              # Fullscreen static GUI overlay
│   └── icons/                   # Optional: status, brake, tyre symbols
├── gui/
│   ├── display.py               # Draw pressure, temps, heatmaps
│   ├── overlay.py               # Load + render static overlay
│   ├── camera.py                # Rear-view USB camera logic
│   └── input.py                 # NeoKey 1x4 (brightness + camera toggle)
├── hardware/
│   ├── tpms_input.py            # TPMS data wrapper
│   ├── ir_brakes.py             # ADS1115/ADS1015 for brake rotors
│   ├── mlx_handler.py           # MLX90640 thermal I2C polling
│   └── i2c_mux.py               # TCA9548A Mux control
└── utils/
    └── config.py                # Constants: positions, colours, thresholds
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
