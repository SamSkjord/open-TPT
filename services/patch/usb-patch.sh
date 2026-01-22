#!/bin/bash
# USB Patch Deployment Script for openTPT
# Checks for patch archive on USB at boot and performs full replacement
# Handles read-only rootfs by temporarily remounting as read-write
#
# Full replacement ensures clean updates with no orphaned files from old versions.
# User data (settings, lap times, tracks) is safe on USB at /mnt/usb/.opentpt/
set -euo pipefail

USB_MOUNT="/mnt/usb"
APP_DIR="/home/pi/open-TPT"
PATCH_LOG="$USB_MOUNT/.opentpt/patch.log"  # Log to USB (rootfs may be read-only)
PATCH_NAMES=("opentpt-patch.tar.gz" "opentpt-patch.zip")
REMOUNTED_RW=false

# Check USB mounted first (needed for logging)
if ! mountpoint -q "$USB_MOUNT"; then
    echo "USB not mounted - no patch to apply"
    exit 0
fi

mkdir -p "$(dirname "$PATCH_LOG")"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$PATCH_LOG"
}

cleanup() {
    # Remount rootfs as read-only if we changed it
    if [[ "$REMOUNTED_RW" == true ]]; then
        log "Remounting rootfs as read-only"
        mount -o remount,ro / 2>/dev/null || log "WARNING: Failed to remount rootfs read-only"
    fi
}
trap cleanup EXIT

is_rootfs_readonly() {
    # Check if root filesystem is mounted read-only
    grep -q ' / .*\bro\b' /proc/mounts
}

remount_rw_if_needed() {
    if is_rootfs_readonly; then
        log "Rootfs is read-only, remounting as read-write"
        if mount -o remount,rw /; then
            REMOUNTED_RW=true
            log "Rootfs remounted read-write"
        else
            log "ERROR: Failed to remount rootfs read-write"
            return 1
        fi
    fi
    return 0
}

# Find patch archive
PATCH_FILE=""
for name in "${PATCH_NAMES[@]}"; do
    [[ -f "$USB_MOUNT/$name" ]] && PATCH_FILE="$USB_MOUNT/$name" && break
done

[[ -z "$PATCH_FILE" ]] && log "No patch archive found on USB" && exit 0

log "Found patch: $PATCH_FILE"

# Remount filesystem read-write if needed
remount_rw_if_needed || exit 0

# Verify archive before making changes
log "Verifying archive integrity..."
if [[ "$PATCH_FILE" == *.tar.gz ]]; then
    tar -tzf "$PATCH_FILE" > /dev/null 2>&1 || { log "ERROR: Corrupt archive"; exit 0; }
elif [[ "$PATCH_FILE" == *.zip ]]; then
    unzip -t "$PATCH_FILE" > /dev/null 2>&1 || { log "ERROR: Corrupt archive"; exit 0; }
fi
log "Archive verified OK"

# Full replacement: delete existing and extract fresh
# User data is safe on USB at /mnt/usb/.opentpt/
log "Removing existing installation..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
cd "$APP_DIR"

log "Extracting new version..."
if [[ "$PATCH_FILE" == *.tar.gz ]]; then
    tar -xzf "$PATCH_FILE"
    log "Extracted $(tar -tzf "$PATCH_FILE" | wc -l) files"
elif [[ "$PATCH_FILE" == *.zip ]]; then
    unzip -q "$PATCH_FILE"
    log "Extracted $(unzip -l "$PATCH_FILE" | tail -1 | awk '{print $2}') files"
fi

# Delete patch file after successful install
rm -f "$PATCH_FILE"
log "Removed patch archive"

chown -R pi:pi "$APP_DIR"
log "Patch complete"
exit 0
