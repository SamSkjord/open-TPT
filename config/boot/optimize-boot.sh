#!/bin/bash
# optimize-boot.sh - Optimise Raspberry Pi boot time for openTPT
# Run once after initial installation: sudo ./optimize-boot.sh
# Target: Sub-7-second boot from power-on to application running

set -e

echo "=== openTPT Boot Optimisation Script ==="
echo ""

# Check we're running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo ./optimize-boot.sh)"
    exit 1
fi

# Backup original files
echo "[1/8] Backing up original boot files..."
cp /boot/firmware/config.txt /boot/firmware/config.txt.backup 2>/dev/null || \
cp /boot/config.txt /boot/config.txt.backup 2>/dev/null || true
cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.backup 2>/dev/null || \
cp /boot/cmdline.txt /boot/cmdline.txt.backup 2>/dev/null || true
echo "  Backups created with .backup extension"

# Determine boot partition location
if [ -d /boot/firmware ]; then
    BOOT_DIR="/boot/firmware"
else
    BOOT_DIR="/boot"
fi
echo "  Boot directory: $BOOT_DIR"

# Update config.txt with boot speed optimisations
echo ""
echo "[2/8] Updating config.txt..."
CONFIG_FILE="$BOOT_DIR/config.txt"

# Add boot speed settings if not present
if ! grep -q "boot_delay=0" "$CONFIG_FILE"; then
    # Insert after disable_splash or at start of file
    if grep -q "disable_splash" "$CONFIG_FILE"; then
        sed -i '/disable_splash/a boot_delay=0' "$CONFIG_FILE"
    else
        sed -i '1i boot_delay=0' "$CONFIG_FILE"
    fi
    echo "  Added: boot_delay=0"
fi

if ! grep -q "initial_turbo" "$CONFIG_FILE"; then
    sed -i '/boot_delay/a initial_turbo=60' "$CONFIG_FILE"
    echo "  Added: initial_turbo=60"
fi

if ! grep -q "force_eeprom_read" "$CONFIG_FILE"; then
    sed -i '/initial_turbo/a force_eeprom_read=0' "$CONFIG_FILE"
    echo "  Added: force_eeprom_read=0"
fi

# Disable initramfs for faster boot (boot directly to kernel)
if grep -q "auto_initramfs=1" "$CONFIG_FILE"; then
    sed -i 's/auto_initramfs=1/auto_initramfs=0/' "$CONFIG_FILE"
    echo "  Changed: auto_initramfs=0 (skip initramfs)"
elif ! grep -q "auto_initramfs" "$CONFIG_FILE"; then
    echo "auto_initramfs=0" >> "$CONFIG_FILE"
    echo "  Added: auto_initramfs=0 (skip initramfs)"
fi

# Update cmdline.txt for fast boot
echo ""
echo "[3/8] Updating cmdline.txt..."
CMDLINE_FILE="$BOOT_DIR/cmdline.txt"
CMDLINE=$(cat "$CMDLINE_FILE")

# Remove serial console if present (saves ~0.5s)
if echo "$CMDLINE" | grep -q "console=serial0"; then
    CMDLINE=$(echo "$CMDLINE" | sed 's/console=serial0,[0-9]* //g')
    echo "  Removed: serial console"
fi

# Add fast boot parameters if not present
if ! echo "$CMDLINE" | grep -q "systemd.show_status"; then
    CMDLINE="$CMDLINE systemd.show_status=0"
    echo "  Added: systemd.show_status=0"
fi

if ! echo "$CMDLINE" | grep -q "rd.udev.log_priority"; then
    CMDLINE="$CMDLINE rd.udev.log_priority=3"
    echo "  Added: rd.udev.log_priority=3"
fi

if ! echo "$CMDLINE" | grep -q "fsck.mode"; then
    # Replace fsck.repair=yes with fsck.mode=skip
    CMDLINE=$(echo "$CMDLINE" | sed 's/fsck.repair=yes/fsck.mode=skip/g')
    if ! echo "$CMDLINE" | grep -q "fsck.mode"; then
        CMDLINE="$CMDLINE fsck.mode=skip"
    fi
    echo "  Added: fsck.mode=skip"
fi

# Ensure quiet boot
if ! echo "$CMDLINE" | grep -q "quiet"; then
    CMDLINE="$CMDLINE quiet"
fi
CMDLINE=$(echo "$CMDLINE" | sed 's/loglevel=[0-9]/loglevel=0/g')

# Write updated cmdline
echo "$CMDLINE" > "$CMDLINE_FILE"

# Disable unnecessary services
echo ""
echo "[4/8] Disabling unnecessary services..."

SERVICES_TO_DISABLE=(
    "avahi-daemon"
    "triggerhappy"
    "ModemManager"
    "apt-daily.timer"
    "apt-daily-upgrade.timer"
    "man-db.timer"
    # Note: systemd-timesyncd kept enabled for NTP time sync
    # Note: wpa_supplicant kept enabled for WiFi connectivity
)

# Mask additional slow services
systemctl mask systemd-time-wait-sync 2>/dev/null || true

for service in "${SERVICES_TO_DISABLE[@]}"; do
    if systemctl is-enabled "$service" &>/dev/null; then
        systemctl disable --now "$service" 2>/dev/null || true
        echo "  Disabled: $service"
    fi
done

# Mask plymouth (we use quiet boot)
systemctl mask plymouth 2>/dev/null || true
echo "  Masked: plymouth"

# Keep bluetooth enabled for CoPilot audio
echo "  Kept enabled: bluetooth (for CoPilot audio)"
echo "  Kept enabled: wpa_supplicant (for WiFi connectivity)"

# Systemd journal optimisation - use RAM only
echo ""
echo "[5/8] Optimising systemd journal..."
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/volatile.conf << 'JOURNAL_EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=16M
JOURNAL_EOF
echo "  Configured: volatile journal (RAM only, 16M max)"

# Install optimised service files
echo ""
echo "[6/8] Installing optimised service files..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SRC="$SCRIPT_DIR/../../openTPT.service"
CAN_SERVICE_SRC="$SCRIPT_DIR/../systemd/can-setup.service"
CAN_SCRIPT_SRC="$SCRIPT_DIR/../systemd/can-setup.sh"

if [ -f "$SERVICE_SRC" ]; then
    cp "$SERVICE_SRC" /etc/systemd/system/openTPT.service
    echo "  Installed: openTPT.service"
else
    echo "  Warning: openTPT.service not found at $SERVICE_SRC"
fi

if [ -f "$CAN_SERVICE_SRC" ]; then
    cp "$CAN_SERVICE_SRC" /etc/systemd/system/can-setup.service
    echo "  Installed: can-setup.service (removed network dependency)"
else
    echo "  Warning: can-setup.service not found at $CAN_SERVICE_SRC"
fi

if [ -f "$CAN_SCRIPT_SRC" ]; then
    cp "$CAN_SCRIPT_SRC" /usr/local/bin/can-setup.sh
    chmod +x /usr/local/bin/can-setup.sh
    echo "  Installed: can-setup.sh (with interface wait loop)"
else
    echo "  Warning: can-setup.sh not found at $CAN_SCRIPT_SRC"
fi

systemctl daemon-reload
systemctl enable openTPT.service can-setup.service 2>/dev/null || true
echo "  Enabled services"

# Install boot splash
echo ""
echo "[7/8] Installing boot splash..."
SPLASH_SERVICE="$SCRIPT_DIR/splash.service"

# Install fbi if not present
if ! command -v fbi &>/dev/null; then
    echo "  Installing fbi package..."
    apt-get install -y fbi >/dev/null 2>&1
fi

# Install splash service
if [ -f "$SPLASH_SERVICE" ]; then
    cp "$SPLASH_SERVICE" /etc/systemd/system/splash.service
    systemctl daemon-reload
    systemctl enable splash.service
    echo "  Installed and enabled splash.service"
    echo "  Splash image: /home/pi/open-TPT/assets/splash.png"
else
    echo "  Warning: splash.service not found at $SPLASH_SERVICE"
fi

# Precompile Python bytecode
echo ""
echo "[8/8] Precompiling Python bytecode..."
if [ -d /home/pi/open-TPT ]; then
    python3 -m compileall -q /home/pi/open-TPT 2>/dev/null || true
    echo "  Compiled: /home/pi/open-TPT/*.pyc"
else
    echo "  Skipped: /home/pi/open-TPT not found (will compile on first run)"
fi

echo ""
echo "=== Boot Optimisation Complete ==="
echo ""
echo "Changes made:"
echo "  - config.txt: boot_delay=0, initial_turbo=60, auto_initramfs=0"
echo "  - cmdline.txt: removed serial console, added quiet boot params"
echo "  - Disabled: avahi, triggerhappy, wpa_supplicant, apt timers"
echo "  - Systemd journal: volatile (RAM only, 16M max)"
echo "  - can-setup.service: removed network dependency (saves ~3s)"
echo "  - openTPT.service: starts at sysinit.target (before network)"
echo "  - splash.service: displays splash-rotated.png at boot"
echo "  - Python bytecode: precompiled for faster imports"
echo ""
echo "Reboot to apply changes:"
echo "  sudo reboot"
echo ""
echo "After reboot, verify boot time with:"
echo "  systemd-analyze"
echo "  systemd-analyze blame"
echo "  systemd-analyze critical-chain openTPT.service"
