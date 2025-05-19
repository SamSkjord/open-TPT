#!/bin/bash
set -e

echo "==== openTPT Installation Script ===="
echo "This script will install all dependencies and set up openTPT to run on boot"
echo "This may take up to 30 minutes to complete" 

# Update system
echo -e "\n==== Updating system packages ===="
sudo apt update
sudo apt upgrade -y

# Install dependencies for SDL
echo -e "\n==== Installing SDL2 dependencies ===="
sudo apt install -y libdrm-dev libgbm-dev libudev-dev libevdev-dev libasound2-dev libpulse-dev libwayland-dev libxkbcommon-dev cmake ninja-build build-essential python3-dev

# Build SDL2 from source with KMSDRM support
echo -e "\n==== Building SDL2 from source with KMSDRM support ===="
cd /tmp
rm -rf SDL2
git clone https://github.com/libsdl-org/SDL.git SDL2
cd SDL2
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DSDL_DRM=ON -DSDL_KMSDRM=ON -DSDL_X11=OFF -DSDL_WAYLAND=OFF
make -j$(nproc)
sudo make install
sudo ldconfig

# Build and install SDL_ttf for font support
echo -e "\n==== Building SDL_ttf for font support ===="
cd /tmp
rm -rf SDL2_ttf
git clone https://github.com/libsdl-org/SDL_ttf.git SDL2_ttf
cd SDL2_ttf
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
sudo make install
sudo ldconfig

# Install required Python packages
echo -e "\n==== Installing Python packages ===="
pip install numpy

# Uninstall and reinstall pygame to use the system SDL libraries
echo -e "\n==== Reinstalling pygame to use system SDL ===="
pip uninstall pygame -y || true
pip install pygame --no-binary :all:

# Verify SDL version
echo -e "\n==== Verifying SDL version ===="
python3 -c "import pygame; print('Pygame is using SDL version:', pygame.get_sdl_version())"

# Copy systemd service file and enable it
echo -e "\n==== Setting up systemd service ===="
CURRENT_DIR=$(pwd)
sudo cp $CURRENT_DIR/openTPT.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openTPT.service

echo -e "\n==== Installation complete! ===="
echo "To start openTPT now, run: sudo systemctl start openTPT.service"
echo "To check status, run: sudo systemctl status openTPT.service"
echo "To view logs, run: sudo journalctl -u openTPT.service"
echo "The system will automatically start openTPT on the next boot"
