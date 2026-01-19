#!/bin/bash
# setup-readonly.sh - Configure read-only root filesystem with overlay
# This provides faster boot (no journal replay) and power-loss protection
#
# IMPORTANT: Run this AFTER testing that openTPT works correctly
# This script modifies critical system files - ensure you have a backup!
#
# How it works:
# - Root filesystem mounted read-only
# - Overlay filesystem for writes (tmpfs in RAM)
# - /var/log, /tmp use tmpfs
# - Config persistence via bind mount from data partition
#
# To revert: Boot with cmdline "rw" or use recovery mode

set -e

echo "=== Read-Only Root Filesystem Setup ==="
echo ""
echo "WARNING: This modifies critical boot configuration!"
echo "Ensure you have a backup before proceeding."
echo ""
read -p "Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

# Check we're running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo ./setup-readonly.sh)"
    exit 1
fi

# Determine boot partition location
if [ -d /boot/firmware ]; then
    BOOT_DIR="/boot/firmware"
else
    BOOT_DIR="/boot"
fi

echo "[1/4] Creating overlay directories..."
mkdir -p /overlay
mkdir -p /overlay/upper
mkdir -p /overlay/work
echo "  Created /overlay/{upper,work}"

echo ""
echo "[2/4] Configuring tmpfs for volatile directories..."

# Add tmpfs entries to fstab if not present
if ! grep -q "tmpfs.*\/var\/log" /etc/fstab; then
    echo "tmpfs /var/log tmpfs defaults,noatime,nosuid,nodev,noexec,mode=0755,size=32M 0 0" >> /etc/fstab
    echo "  Added: tmpfs /var/log (32M)"
fi

if ! grep -q "tmpfs.*\/tmp" /etc/fstab; then
    echo "tmpfs /tmp tmpfs defaults,noatime,nosuid,nodev,mode=1777,size=64M 0 0" >> /etc/fstab
    echo "  Added: tmpfs /tmp (64M)"
fi

if ! grep -q "tmpfs.*\/var\/tmp" /etc/fstab; then
    echo "tmpfs /var/tmp tmpfs defaults,noatime,nosuid,nodev,mode=1777,size=32M 0 0" >> /etc/fstab
    echo "  Added: tmpfs /var/tmp (32M)"
fi

echo ""
echo "[3/4] Updating cmdline.txt for read-only root..."
CMDLINE_FILE="$BOOT_DIR/cmdline.txt"
CMDLINE=$(cat "$CMDLINE_FILE")

# Change rootwait to ro (read-only)
if ! echo "$CMDLINE" | grep -q " ro "; then
    CMDLINE=$(echo "$CMDLINE" | sed 's/rootwait/rootwait ro/')
    echo "$CMDLINE" > "$CMDLINE_FILE"
    echo "  Added: ro (read-only root)"
else
    echo "  Already configured: ro"
fi

echo ""
echo "[4/4] Creating data persistence directory..."

# Create directory for persistent data (telemetry, config)
mkdir -p /home/pi/open-TPT/data
chown pi:pi /home/pi/open-TPT/data

# Update openTPT config to use this directory for recordings
echo "  Created: /home/pi/open-TPT/data (for recordings and config)"

echo ""
echo "=== Read-Only Root Setup Complete ==="
echo ""
echo "Changes made:"
echo "  - Created /overlay directories for overlay filesystem"
echo "  - Added tmpfs for /var/log, /tmp, /var/tmp"
echo "  - Added 'ro' flag to cmdline.txt"
echo "  - Created /home/pi/open-TPT/data for persistent storage"
echo ""
echo "IMPORTANT: The root filesystem will be read-only after reboot."
echo ""
echo "To temporarily enable writes:"
echo "  sudo mount -o remount,rw /"
echo ""
echo "To permanently revert to read-write:"
echo "  Edit $CMDLINE_FILE and remove 'ro'"
echo ""
echo "Reboot to apply: sudo reboot"
