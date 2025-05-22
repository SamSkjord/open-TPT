# openTPT - Open Tyre Pressure and Temperature Telemetry

A modular GUI system for live racecar telemetry using a Raspberry Pi

## Overview

openTPT provides real-time monitoring of:
- 🛞 Tyre pressure & temperature (via TPMS)
- 🔥 Brake rotor temperatures (via IR sensors + ADC)
- 🌡️ Tyre surface heatmaps (via MLX90640 thermal cameras)
- 🎥 Full-screen rear-view toggle (USB UVC camera)

The system is designed for racing applications where real-time monitoring of tyre and brake conditions is critical for optimal performance and safety.

## Hardware Requirements

- Raspberry Pi 4 (2GB+ RAM recommended)
- HyperPixel or compatible display (800x480 resolution)
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

2. Install the required Python packages:
```
pip install -r requirements.txt
```

3. Make the main script executable:
```
chmod +x main.py
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

The system can be configured by editing the `utils/config.py` file, which contains settings for:
- Display dimensions and FPS target
- Positions for telemetry indicators
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

## ✅ KMSDRM Implementation on Raspberry Pi (Bookworm Lite)

This guide explains how to build and configure `pygame` with SDL2 and KMSDRM for fullscreen graphical output on Raspberry Pi without using X11 or Wayland.

---

### ⚙️ Goal

Run `openTPT` as a fullscreen `pygame` application using the KMSDRM backend (no desktop, no login required), with proper support for:

- Fonts (`SDL_ttf`)
- PNG/JPEG/WebP images (`SDL_image`)
- Systemd service launching on boot

---

### 🧱 Prerequisites

Ensure you're running Raspberry Pi OS Bookworm Lite on a Pi 4 (or compatible).

---

### 🛠️ Setup Script

Save this as `install_openTPT.sh` and run with `chmod +x install_openTPT.sh && ./install_openTPT.sh`.

```bash
#!/bin/bash
set -e

echo "==== openTPT Installation Script ===="
echo "This script will install all dependencies and set up openTPT to run on boot"
echo "This may take up to 30 minutes to complete"

# Update system
sudo apt update
sudo apt upgrade -y

# Install dependencies for SDL2, SDL_ttf, SDL_image
sudo apt install -y \
  libdrm-dev libgbm-dev libudev-dev libevdev-dev libasound2-dev libpulse-dev \
  libwayland-dev libxkbcommon-dev libfreetype6-dev libharfbuzz-dev \
  libpng-dev libjpeg-dev libtiff-dev libwebp-dev zlib1g-dev \
  cmake ninja-build build-essential python3-dev git

# Build SDL2 from release-2.28.5 with KMSDRM
cd /tmp
rm -rf SDL2
git clone --branch release-2.28.5 https://github.com/libsdl-org/SDL.git SDL2
cd SDL2
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DSDL_VIDEO_DRIVER_KMSDRM=ON
make -j$(nproc)
sudo make install
sudo ldconfig

# Build SDL_ttf
cd /tmp
rm -rf SDL2_ttf
git clone --branch release-2.20.2 https://github.com/libsdl-org/SDL_ttf.git SDL2_ttf
cd SDL2_ttf
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
sudo make install
sudo ldconfig

# Build SDL_image
cd /tmp
rm -rf SDL2_image
git clone --branch release-2.8.2 https://github.com/libsdl-org/SDL_image.git SDL2_image
cd SDL2_image
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
sudo make install
sudo ldconfig

# Install numpy
sudo /usr/bin/python3 -m pip install numpy --break-system-packages

# Rebuild pygame with all SDL features linked
sudo /usr/bin/python3 -m pip uninstall -y pygame || true
sudo /usr/bin/python3 -m pip install pygame --no-binary :all: --break-system-packages

# Verify pygame SDL linkage
python3 -c "import pygame; print('Pygame SDL version:', pygame.get_sdl_version())"

# Enable openTPT systemd service
CURRENT_DIR=$(pwd)
sudo cp $CURRENT_DIR/openTPT.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openTPT.service

echo "==== Installation complete ===="
echo "Start now with: sudo systemctl start openTPT.service"
```

---

### ✅ Result

- `pygame` uses `KMSDRM` backend — no X11
- Fonts (`pygame.font`) and PNG/JPG/WebP support (`pygame.image.load()`)
- Fullscreen rendering from systemd at boot