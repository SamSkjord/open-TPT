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

# Install Bluetooth audio support (PulseAudio with Bluetooth module)
echo -e "\n==== Installing Bluetooth audio support ===="
sudo apt install -y pulseaudio pulseaudio-module-bluetooth

# Install GPS and time sync packages
echo -e "\n==== Installing GPS and time sync packages ===="
sudo apt install -y gpsd gpsd-clients chrony pps-tools

# Add D-Bus policy for Bluetooth audio (allows pi user to access A2DP profiles)
echo -e "\n==== Configuring Bluetooth audio permissions ===="
sudo tee /etc/dbus-1/system.d/bluetooth-audio.conf > /dev/null << 'BTEOF'
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <policy user="pi">
    <allow send_destination="org.bluez"/>
    <allow send_interface="org.bluez.MediaEndpoint1"/>
    <allow send_interface="org.bluez.MediaTransport1"/>
    <allow send_interface="org.bluez.Agent1"/>
    <allow send_interface="org.freedesktop.DBus.ObjectManager"/>
    <allow send_interface="org.freedesktop.DBus.Properties"/>
  </policy>
  <policy group="bluetooth">
    <allow send_destination="org.bluez"/>
    <allow send_interface="org.bluez.MediaEndpoint1"/>
    <allow send_interface="org.bluez.MediaTransport1"/>
  </policy>
</busconfig>
BTEOF

# Add pi user to bluetooth group
sudo usermod -a -G bluetooth "$TARGET_USER" 2>/dev/null || true
echo "Bluetooth audio permissions configured"

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
  "pyserial>=3.5"
  "adafruit-blinka"
  "adafruit-circuitpython-neokey>=1.1.7"
  "adafruit-circuitpython-seesaw"
  "adafruit-circuitpython-neopixel"
  "adafruit-circuitpython-tca9548a"
  "adafruit-circuitpython-mlx90614"
  "adafruit-circuitpython-mlx90640"
  "adafruit-circuitpython-ssd1305"
  "adafruit-circuitpython-mcp230xx"
  "adafruit-circuitpython-icm20x"
  "tpms==2.0.1"
  "pytest>=7.0.0"
  "opencv-python"
  "matplotlib>=3.8.0"
  "pandas-stubs>=2.1.0"
  "python-can>=4.0.0"
  "cantools>=39.0.0"
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
dtparam=i2c_arm_baudrate=400000  # 400kHz - better noise immunity for motorsport EMI
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

  # Configure UART and PPS for GPS
  GPS_BLOCK_HEADER="# ==== openTPT GPS Configuration ===="
  if sudo grep -Fq "$GPS_BLOCK_HEADER" "$BOOT_CONFIG"; then
    echo "GPS configuration block already present."
  else
    sudo tee -a "$BOOT_CONFIG" >/dev/null <<'EOF'

# ==== openTPT GPS Configuration ====
# Enable UART for GPS module (GPIO 14/15 TX/RX)
enable_uart=1
# PPS signal from GPS on GPIO 18
dtoverlay=pps-gpio,gpiopin=18
# ==== end openTPT GPS Configuration ====
EOF
    echo "Appended GPS configuration to $BOOT_CONFIG (reboot required)."
  fi
fi

# Configure chrony for PPS time sync
# Note: gpsd is installed but disabled - openTPT reads serial directly for 10Hz
echo -e "\n==== Configuring chrony for PPS time sync ===="
CHRONY_PPS_HEADER="# PPS from GPS (precise timing)"
if sudo grep -Fq "$CHRONY_PPS_HEADER" /etc/chrony/chrony.conf; then
  echo "Chrony PPS configuration already present."
else
  sudo tee -a /etc/chrony/chrony.conf >/dev/null <<'EOF'

# PPS from GPS (precise timing)
# openTPT sets coarse time from NMEA, PPS refines to nanosecond precision
refclock PPS /dev/pps0 refid PPS precision 1e-7 prefer
# Allow NTP servers as fallback when GPS unavailable
EOF
  echo "Chrony configured for PPS time sync (Stratum 1)"
fi

# Keep NTP enabled as fallback for coarse time when GPS unavailable
# (PPS requires system time to be within ~0.5s to lock)
sudo timedatectl set-ntp true 2>/dev/null || true

# Install GPS 10Hz configuration script and service
echo -e "\n==== Installing GPS 10Hz configuration ===="
GPS_CONFIG_SRC="$SCRIPT_DIR/services/gps/gps-config.sh"
GPS_SERVICE_SRC="$SCRIPT_DIR/services/gps/gps-config.service"

if [[ -f "$GPS_CONFIG_SRC" ]]; then
  sudo install -m 0755 "$GPS_CONFIG_SRC" /usr/local/bin/gps-config.sh
  sudo install -m 0644 "$GPS_SERVICE_SRC" /etc/systemd/system/gps-config.service
  sudo systemctl daemon-reload
  sudo systemctl enable gps-config.service
  echo "GPS 10Hz configuration installed (configures GPS and disables gpsd at boot)"
else
  echo "WARNING: Missing $GPS_CONFIG_SRC; skipping GPS 10Hz configuration."
fi

# Install USB patch deployment service
echo -e "\n==== Installing USB patch deployment service ===="
PATCH_SCRIPT_SRC="$SCRIPT_DIR/services/patch/usb-patch.sh"
PATCH_SERVICE_SRC="$SCRIPT_DIR/services/patch/usb-patch.service"

if [[ -f "$PATCH_SCRIPT_SRC" ]]; then
  sudo install -m 0755 "$PATCH_SCRIPT_SRC" /usr/local/bin/usb-patch.sh
  sudo install -m 0644 "$PATCH_SERVICE_SRC" /etc/systemd/system/usb-patch.service
  sudo systemctl daemon-reload
  sudo systemctl enable usb-patch.service
  echo "USB patch service installed (checks for patches at boot)"
else
  echo "WARNING: Missing $PATCH_SCRIPT_SRC; skipping USB patch service."
fi

# Install USB log sync service
echo -e "\n==== Installing USB log sync service ===="
LOG_SCRIPT_SRC="$SCRIPT_DIR/services/logging/usb-log-sync.sh"
LOG_SERVICE_SRC="$SCRIPT_DIR/services/logging/usb-log-sync.service"
LOG_TIMER_SRC="$SCRIPT_DIR/services/logging/usb-log-sync.timer"
LOG_PERIODIC_SRC="$SCRIPT_DIR/services/logging/usb-log-sync-periodic.service"

if [[ -f "$LOG_SCRIPT_SRC" ]]; then
  sudo install -m 0755 "$LOG_SCRIPT_SRC" /usr/local/bin/usb-log-sync.sh
  sudo install -m 0644 "$LOG_SERVICE_SRC" /etc/systemd/system/usb-log-sync.service
  sudo install -m 0644 "$LOG_TIMER_SRC" /etc/systemd/system/usb-log-sync.timer
  sudo install -m 0644 "$LOG_PERIODIC_SRC" /etc/systemd/system/usb-log-sync-periodic.service
  sudo systemctl daemon-reload
  # Enable shutdown sync (writes logs to USB on shutdown)
  sudo systemctl enable usb-log-sync.service
  echo "USB log sync service installed (syncs logs to USB on shutdown)"
  echo "  Optional: sudo systemctl enable usb-log-sync.timer  # For periodic sync every 30min"
else
  echo "WARNING: Missing $LOG_SCRIPT_SRC; skipping USB log sync service."
fi

# Install persistent CAN naming rule
echo -e "\n==== Installing persistent CAN interface naming rule ===="
UDEV_RULE_SRC="$SCRIPT_DIR/services/can/80-can-persistent-names.rules"
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

# Install camera persistent naming rule
echo -e "\n==== Installing camera persistent naming rule ===="
CAMERA_RULE_SRC="$SCRIPT_DIR/services/camera/99-camera-names.rules"
CAMERA_RULE_DST="/etc/udev/rules.d/99-camera-names.rules"

if [[ -f "$CAMERA_RULE_SRC" ]]; then
  if sudo test -f "$CAMERA_RULE_DST" && sudo cmp -s "$CAMERA_RULE_SRC" "$CAMERA_RULE_DST"; then
    echo "Camera naming rule already up to date."
  else
    sudo install -m 0644 "$CAMERA_RULE_SRC" "$CAMERA_RULE_DST"
    sudo udevadm control --reload-rules
    sudo udevadm trigger || true
    echo "Installed camera naming rule."
    echo "Connect cameras to USB ports:"
    echo "  - Rear camera  → USB port 1.1 (creates /dev/video-rear)"
    echo "  - Front camera → USB port 1.2 (creates /dev/video-front)"
    echo "Verify with: ls -l /dev/video-*"
  fi
else
  echo "WARNING: Missing $CAMERA_RULE_SRC; skipping camera naming rule."
fi

# Copy systemd service files and enable
echo -e "\n==== Setting up CAN interface auto-start ===="
sudo cp "$SCRIPT_DIR/services/systemd/can-setup.sh" /usr/local/bin/
sudo chmod +x /usr/local/bin/can-setup.sh
sudo cp "$SCRIPT_DIR/services/systemd/can-setup.service" /etc/systemd/system/
echo "CAN interface service installed"

echo -e "\n==== Enabling systemd services ===="
cd "$SCRIPT_DIR"
sudo cp "$SCRIPT_DIR/services/systemd/openTPT.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable can-setup.service
sudo systemctl enable openTPT.service
echo "Services enabled"

# Configure quiet boot (no kernel messages)
echo -e "\n==== Configuring quiet boot ===="
CMDLINE_FILE=""
if [[ -f /boot/firmware/cmdline.txt ]]; then
  CMDLINE_FILE="/boot/firmware/cmdline.txt"
elif [[ -f /boot/cmdline.txt ]]; then
  CMDLINE_FILE="/boot/cmdline.txt"
fi

if [[ -n "$CMDLINE_FILE" ]]; then
  if ! grep -q "quiet" "$CMDLINE_FILE"; then
    # Add quiet boot parameters
    sudo sed -i 's/$/ quiet splash loglevel=0 logo.nologo vt.global_cursor_default=0/' "$CMDLINE_FILE"
    echo "Quiet boot parameters added to $CMDLINE_FILE"
  else
    echo "Quiet boot already configured"
  fi
else
  echo "WARNING: Could not find cmdline.txt"
fi

# Install splash screen service
echo -e "\n==== Installing boot splash ===="
sudo apt install -y fbi
SPLASH_SERVICE_SRC="$SCRIPT_DIR/services/boot/splash.service"
if [[ -f "$SPLASH_SERVICE_SRC" ]]; then
  sudo install -m 0644 "$SPLASH_SERVICE_SRC" /etc/systemd/system/splash.service
  sudo systemctl daemon-reload
  sudo systemctl enable splash.service
  echo "Boot splash service installed"
else
  echo "WARNING: Missing $SPLASH_SERVICE_SRC"
fi

# Disable login prompt on tty1 (we want splash -> app, no login)
echo -e "\n==== Disabling tty1 login prompt ===="
sudo systemctl disable getty@tty1.service 2>/dev/null || true
echo "tty1 login disabled"

# Disable rainbow screen and boot diagnostics
echo -e "\n==== Disabling boot diagnostics ===="
if [[ -n "$BOOT_CONFIG" ]] && ! grep -q "disable_splash=1" "$BOOT_CONFIG"; then
  sudo tee -a "$BOOT_CONFIG" >/dev/null <<'EOF'

# ==== openTPT Boot Display ====
disable_splash=1
boot_delay=0
# ==== end openTPT Boot Display ====
EOF
  echo "Rainbow screen and boot delay disabled"
else
  echo "Boot diagnostics already configured"
fi

# Disable cloud-init to prevent boot delays and network configuration issues
echo -e "\n==== Disabling cloud-init ===="
if [ -d /etc/cloud ]; then
  sudo touch /etc/cloud/cloud-init.disabled
  echo "cloud-init disabled"
else
  echo "cloud-init not found (already removed or not installed)"
fi

# Precompile Python bytecode for faster startup
echo -e "\n==== Precompiling Python bytecode ===="
"$PYTHON_BIN" -m compileall -q "$SCRIPT_DIR" 2>/dev/null || true
echo "Python bytecode compiled"

echo -e "\n==== Installation complete! ===="
echo ""
echo "IMPORTANT: Reboot required for CAN and GPS hardware to initialise."
echo "           sudo reboot"
echo ""
echo "After reboot:"
echo "  Check CAN interfaces:   ip link show | grep can"
echo "  Check service status:   sudo systemctl status openTPT.service"
echo "  View logs:              sudo journalctl -u openTPT.service -f"
echo ""
echo "openTPT will auto-start on boot."
