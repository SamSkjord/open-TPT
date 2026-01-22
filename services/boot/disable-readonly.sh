#!/bin/bash
# disable-readonly.sh - Disable read-only root filesystem
#
# This disables overlayroot so the root filesystem becomes read-write again.
# Use this for maintenance, updates, or if you need to modify system files.
#
# After making changes, run setup-readonly.sh to re-enable protection.

set -e

echo "=== Disable Read-Only Root Filesystem ==="
echo ""

# Check we're running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo ./disable-readonly.sh)"
    exit 1
fi

# Check if overlayroot is installed
if [ ! -f /etc/overlayroot.conf ]; then
    echo "overlayroot is not installed. Nothing to disable."
    exit 0
fi

# Check current status
if grep -q '^overlayroot=""' /etc/overlayroot.conf 2>/dev/null; then
    echo "Read-only mode is already disabled."
    exit 0
fi

echo "Current overlayroot status:"
grep -E '^overlayroot=' /etc/overlayroot.conf || echo "  (not configured)"
echo ""

# If overlay is currently active, we need to use overlayroot-chroot
if grep -q ' / overlay' /proc/mounts 2>/dev/null; then
    echo "Overlay is currently active."
    echo "Disabling overlayroot via chroot..."

    # Use overlayroot-chroot to modify the underlying filesystem
    overlayroot-chroot sh -c 'sed -i "s/^overlayroot=.*/overlayroot=\"\"/" /etc/overlayroot.conf && update-initramfs -u'

    echo "overlayroot disabled in underlying filesystem."
else
    # Overlay not active, can modify directly
    echo "Disabling overlayroot..."
    sed -i 's/^overlayroot=.*/overlayroot=""/' /etc/overlayroot.conf

    echo "Updating initramfs..."
    update-initramfs -u
fi

echo ""
echo "=== Read-Only Mode Disabled ==="
echo ""
echo "After reboot:"
echo "  - Root filesystem will be read-write (normal operation)"
echo "  - SD card writes enabled (no power-loss protection)"
echo ""
echo "To re-enable read-only mode after making changes:"
echo "  Run setup-readonly.sh and reboot"
echo ""
echo "Reboot to apply: sudo reboot"
