#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PYTHON_BIN="/usr/bin/python3"
PIP_CMD=(sudo "$PYTHON_BIN" -m pip)
# Allow pip to bypass Debian-managed guards when we really want system installs
export PIP_BREAK_SYSTEM_PACKAGES=1
export PIP_ROOT_USER_ACTION=ignore

TARGET_USER=${SUDO_USER:-$(whoami)}
TARGET_HOME=$(eval echo "~$TARGET_USER")

echo "==== openTPT Installation Script ===="
echo "This script will install all dependencies and set up openTPT to run on boot"
echo "This may take up to 30 minutes to complete"

# Update system
echo -e "\n==== Updating system packages ===="
sudo apt update
sudo apt upgrade -y

# Install dependencies for SDL2, SDL_ttf, SDL_image, pygame
echo -e "\n==== Installing build dependencies ===="
sudo apt install -y \
  build-essential cmake ninja-build git pkg-config \
  python3-dev python3-pip python3-venv \
  libdrm-dev libgbm-dev libudev-dev libevdev-dev \
  libasound2-dev libpulse-dev \
  libwayland-dev libxkbcommon-dev \
  libfreetype6-dev libharfbuzz-dev \
  libpng-dev libjpeg-dev libtiff-dev libwebp-dev zlib1g-dev \
  libx11-dev libxext-dev libxi-dev libxrandr-dev libxcursor-dev libxinerama-dev \
  libxrender-dev libxfixes-dev libsm-dev libice-dev \
  libgl1-mesa-dev libglu1-mesa-dev libgles2-mesa-dev libegl1-mesa-dev libglvnd-dev

echo -e "\n==== Upgrading pip tooling ===="
if ! "${PIP_CMD[@]}" install --break-system-packages --upgrade pip setuptools wheel; then
  echo "pip upgrade failed (likely due to Debian-managed pip). Continuing with system pip..."
fi

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

echo -e "\n==== Installing Python dependencies ===="
# Ensure no user-local pygame copies shadow the system install
echo -e "\n==== Removing user-local pygame builds ===="
if [[ -d "$TARGET_HOME/.local/lib" ]]; then
  sudo -u "$TARGET_USER" "$PYTHON_BIN" -m pip uninstall -y pygame pygame-ce >/dev/null 2>&1 || true
  while IFS= read -r sp_dir; do
    sudo -u "$TARGET_USER" rm -rf "$sp_dir"/pygame "$sp_dir"/pygame-* "$sp_dir"/pygame_ce "$sp_dir"/pygame_ce-*
  done < <(find "$TARGET_HOME/.local/lib" -maxdepth 3 -type d -name 'site-packages' 2>/dev/null)
fi

PYTHON_DEPS=(
  "numpy>=1.22.0,<2.3.0"
  "pillow>=9.0.0"
  "adafruit-circuitpython-neokey>=1.1.7"
  "adafruit-circuitpython-tca9548a>=0.8.3"
  "adafruit-circuitpython-ads1x15>=2.2.0"
  # Thermal sensors: MLX90640 for Pico slaves, MLX90614 for direct Pi reading
  "adafruit-circuitpython-mlx90640>=1.2.0"
  "adafruit-circuitpython-mlx90614>=1.2.0"
  "tpms==2.0.1"
  "pytest>=7.0.0"
  "opencv-python"
  "matplotlib>=3.8.0"
  "pandas-stubs>=2.1.0"
)
"${PIP_CMD[@]}" install --break-system-packages "${PYTHON_DEPS[@]}"

# Rebuild pygame to link with system SDL, SDL_image, SDL_ttf
echo -e "\n==== Rebuilding pygame from source ===="
"${PIP_CMD[@]}" uninstall --break-system-packages -y pygame || true
if ! "${PIP_CMD[@]}" install --break-system-packages --no-binary :all: pygame; then
  echo "Warning: pygame rebuild from source failed. Using existing pygame installation."
  echo "If pygame is already installed and working, this is not a problem."
fi

# Verify SDL version from pygame
echo -e "\n==== Verifying pygame SDL linkage ===="
"$PYTHON_BIN" -c "import pygame; print('Pygame SDL version:', pygame.get_sdl_version())"

# Configure Dual CAN hardware overlays
echo -e "\n==== Configuring Waveshare Dual CAN HAT overlays ===="
BOOT_CONFIG=""
if [[ -f /boot/firmware/config.txt ]]; then
  BOOT_CONFIG="/boot/firmware/config.txt"
elif [[ -f /boot/config.txt ]]; then
  BOOT_CONFIG="/boot/config.txt"
fi

if [[ -z "$BOOT_CONFIG" ]]; then
  echo "WARNING: Could not locate config.txt; skipping CAN overlay configuration."
else
  echo "Boot config file: $BOOT_CONFIG"
  CAN_BLOCK_HEADER="# ==== openTPT Dual Waveshare 2-CH CAN HAT+ ===="
  if sudo grep -Fq "$CAN_BLOCK_HEADER" "$BOOT_CONFIG"; then
    echo "Dual Waveshare CAN block already present."
  else
    sudo tee -a "$BOOT_CONFIG" >/dev/null <<'EOF'

# ==== openTPT Dual Waveshare 2-CH CAN HAT+ ====
dtparam=i2c_arm=on
dtparam=i2s=off        # Disabled to free GPIO19 for SPI1_MISO
dtparam=spi=on
dtoverlay=spi1-3cs
dtoverlay=mcp2515,spi1-1,oscillator=16000000,interrupt=22  # Board 1, CAN_0 (GPIO22 IRQ)
dtoverlay=mcp2515,spi1-2,oscillator=16000000,interrupt=13  # Board 1, CAN_1 (GPIO13 IRQ)
dtoverlay=spi0-2cs
dtoverlay=mcp2515,spi0-0,oscillator=16000000,interrupt=23  # Board 2, CAN_0 (GPIO23 IRQ)
dtoverlay=mcp2515,spi0-1,oscillator=16000000,interrupt=25  # Board 2, CAN_1 (GPIO25 IRQ / OBD-II)
# ==== end openTPT Dual Waveshare 2-CH CAN HAT+ ====
EOF
    echo "Appended Dual CAN block to $BOOT_CONFIG (reboot required)."
  fi
fi

# Install persistent CAN naming rule
echo -e "\n==== Installing persistent CAN interface naming rule ===="
UDEV_RULE_SRC="$SCRIPT_DIR/config/can/80-can-persistent-names.rules"
UDEV_RULE_DST="/etc/udev/rules.d/80-can-persistent-names.rules"

if [[ -f "$UDEV_RULE_SRC" ]]; then
  if sudo test -f "$UDEV_RULE_DST" && sudo cmp -s "$UDEV_RULE_SRC" "$UDEV_RULE_DST"; then
    echo "Persistent CAN naming rule already up to date."
  else
    sudo install -m 0644 "$UDEV_RULE_SRC" "$UDEV_RULE_DST"
    sudo udevadm control --reload-rules
    sudo udevadm trigger -s net || true
    echo "Installed persistent CAN naming rule (reboot recommended)."
  fi
else
  echo "WARNING: Missing $UDEV_RULE_SRC; skipping persistent naming rule."
fi

# Copy systemd service file and enable
echo -e "\n==== Enabling openTPT systemd service ===="
cd "$SCRIPT_DIR"
sudo cp "$SCRIPT_DIR/openTPT.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openTPT.service

# Disable cloud-init to prevent boot delays and network configuration issues
echo -e "\n==== Disabling cloud-init ===="
if [ -d /etc/cloud ]; then
  sudo touch /etc/cloud/cloud-init.disabled
  echo "cloud-init disabled"
else
  echo "cloud-init not found (already removed or not installed)"
fi

echo -e "\n==== Installation complete! ===="
echo "To start openTPT now:         sudo systemctl start openTPT.service"
echo "To check service status:      sudo systemctl status openTPT.service"
echo "To view logs:                 sudo journalctl -u openTPT.service"
echo "This will now auto-start on boot"
