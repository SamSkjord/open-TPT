#!/bin/bash
# setup-readonly.sh - Enable read-only root filesystem using overlayroot
#
# Uses the standard overlayroot package (Debian Trixie) which provides:
# - Lower layer: Read-only root filesystem on SD card
# - Upper layer: tmpfs (RAM) captures all writes
# - Result: SD card never written to during normal operation
#
# All persistent data uses USB storage at /mnt/usb/.opentpt/
#
# To disable: Run disable-readonly.sh or edit /etc/overlayroot.conf
# To patch with overlay active: USB patches use overlayroot-chroot automatically

set -e

echo "=== Read-Only Root Filesystem Setup (overlayroot) ==="
echo ""
echo "This will install and configure overlayroot to protect the SD card."
echo "All writes during runtime will go to RAM (tmpfs overlay)."
echo ""
echo "Prerequisites:"
echo "  - USB drive mounted at /mnt/usb with persistent data"
echo "  - All user data already migrated to /mnt/usb/.opentpt/"
echo ""
echo "WARNING: After reboot, the root filesystem cannot be modified!"
echo "         Use disable-readonly.sh or USB patch to make changes."
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

# Check USB is mounted (persistent storage required)
if ! mountpoint -q /mnt/usb; then
    echo "WARNING: USB not mounted at /mnt/usb"
    echo "         Settings and data will not persist across reboots!"
    echo ""
    read -p "Continue anyway? (yes/no): " CONFIRM_USB
    if [ "$CONFIRM_USB" != "yes" ]; then
        echo "Aborted. Mount USB and try again."
        exit 1
    fi
fi

echo ""
echo "[1/3] Installing overlayroot package..."
apt-get update
apt-get install -y overlayroot
echo "  overlayroot installed"

echo ""
echo "[2/3] Configuring overlayroot..."
# Enable tmpfs overlay - all writes go to RAM
cat > /etc/overlayroot.conf << 'EOF'
# overlayroot configuration for openTPT
# Protects SD card from corruption due to power loss
#
# overlayroot="tmpfs" - Uses RAM for overlay (writes lost on reboot)
# overlayroot=""      - Disabled (normal read-write operation)
#
# To modify root filesystem:
#   1. Run disable-readonly.sh, reboot, make changes, run setup-readonly.sh
#   2. Or use USB patch which handles overlay automatically
#   3. Or use: sudo overlayroot-chroot (temporary access to lower fs)

overlayroot="tmpfs"
EOF
echo "  /etc/overlayroot.conf configured"

echo ""
echo "[3/3] Updating initramfs..."
update-initramfs -u
echo "  initramfs updated"

echo ""
echo "=== Read-Only Root Setup Complete ==="
echo ""
echo "After reboot:"
echo "  - Root filesystem will be read-only (protected)"
echo "  - All writes go to RAM overlay (lost on reboot)"
echo "  - USB at /mnt/usb remains read-write (persistent data)"
echo ""
echo "To verify overlay is active after reboot:"
echo "  mount | grep overlay"
echo ""
echo "To temporarily write to root filesystem:"
echo "  sudo overlayroot-chroot"
echo ""
echo "To permanently disable read-only mode:"
echo "  Run disable-readonly.sh and reboot"
echo ""
echo "Reboot to activate: sudo reboot"
