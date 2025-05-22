#!/bin/bash
set -e

echo "==== openTPT Installation Script ===="
echo "This script will install all dependencies and set up openTPT to run on boot"
echo "This may take up to 30 minutes to complete"

# Update system
echo -e "\n==== Updating system packages ===="
sudo apt update
sudo apt upgrade -y

# Install dependencies for SDL2, SDL_ttf, SDL_image
echo -e "\n==== Installing build dependencies ===="
sudo apt install -y \
  libdrm-dev libgbm-dev libudev-dev libevdev-dev libasound2-dev libpulse-dev \
  libwayland-dev libxkbcommon-dev libfreetype6-dev libharfbuzz-dev \
  libpng-dev libjpeg-dev libtiff-dev libwebp-dev zlib1g-dev \
  cmake ninja-build build-essential python3-dev git

# Build SDL2 from release-2.28.5 with KMSDRM
echo -e "\n==== Building SDL2 from source ===="
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
echo -e "\n==== Building SDL_ttf ===="
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
echo -e "\n==== Building SDL_image ===="
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
#echo -e "\n==== Installing Python dependencies ===="
#sudo /usr/bin/python3 -m pip install numpy --break-system-packages

echo -e "\n==== Installing Python dependencies ===="
sudo /usr/bin/python3 -m pip install \
  numpy>=1.22.0 \
  pillow>=9.0.0 \
  adafruit-circuitpython-neokey>=1.2.0 \
  adafruit-circuitpython-tca9548a>=1.3.0 \
  adafruit-circuitpython-ads1x15>=2.2.0 \
  adafruit-circuitpython-mlx90640>=1.2.0 \
  tpms==2.0.1 \
  pytest>=7.0.0 \
  --break-system-packages


# Rebuild pygame to link with system SDL, SDL_image, SDL_ttf
echo -e "\n==== Rebuilding pygame from source ===="
sudo /usr/bin/python3 -m pip uninstall -y pygame || true
sudo /usr/bin/python3 -m pip install pygame --no-binary :all: --break-system-packages

# Verify SDL version from pygame
echo -e "\n==== Verifying pygame SDL linkage ===="
python3 -c "import pygame; print('Pygame SDL version:', pygame.get_sdl_version())"

# Copy systemd service file and enable
echo -e "\n==== Enabling openTPT systemd service ===="
CURRENT_DIR=$(pwd)
sudo cp $CURRENT_DIR/openTPT.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openTPT.service

echo -e "\n==== Installation complete! ===="
echo "To start openTPT now:         sudo systemctl start openTPT.service"
echo "To check service status:      sudo systemctl status openTPT.service"
echo "To view logs:                 sudo journalctl -u openTPT.service"
echo "This will now auto-start on boot"