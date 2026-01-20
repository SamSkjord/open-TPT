#!/bin/bash
# USB Patch Deployment Script for openTPT
# Checks for patch archive on USB at boot and extracts to application directory
set -euo pipefail

USB_MOUNT="/mnt/usb"
APP_DIR="/home/pi/open-TPT"
PATCH_LOG="/home/pi/.opentpt/patch.log"
PATCH_NAMES=("opentpt-patch.tar.gz" "opentpt-patch.zip")

mkdir -p "$(dirname "$PATCH_LOG")"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$PATCH_LOG"
}

# Check USB mounted
if ! mountpoint -q "$USB_MOUNT"; then
    log "USB not mounted - no patch to apply"
    exit 0
fi

# Find patch archive
PATCH_FILE=""
for name in "${PATCH_NAMES[@]}"; do
    [[ -f "$USB_MOUNT/$name" ]] && PATCH_FILE="$USB_MOUNT/$name" && break
done

[[ -z "$PATCH_FILE" ]] && log "No patch archive found on USB" && exit 0

log "Found patch: $PATCH_FILE"

# Verify and extract
cd "$APP_DIR"
if [[ "$PATCH_FILE" == *.tar.gz ]]; then
    tar -tzf "$PATCH_FILE" > /dev/null 2>&1 || { log "ERROR: Corrupt archive"; exit 0; }
    tar -xzvf "$PATCH_FILE" 2>&1 | while read -r f; do log "  extracted: $f"; done
elif [[ "$PATCH_FILE" == *.zip ]]; then
    unzip -t "$PATCH_FILE" > /dev/null 2>&1 || { log "ERROR: Corrupt archive"; exit 0; }
    unzip -o "$PATCH_FILE" 2>&1 | grep -E "inflating:|extracting:" | while read -r f; do log "  $f"; done
fi

# Rename to prevent re-application
mv "$PATCH_FILE" "${PATCH_FILE%.tar.gz}-applied-$(date '+%Y%m%d_%H%M%S').archive" 2>/dev/null || \
mv "$PATCH_FILE" "${PATCH_FILE%.zip}-applied-$(date '+%Y%m%d_%H%M%S').archive" 2>/dev/null || \
log "WARNING: Could not rename archive"

chown -R pi:pi "$APP_DIR"
log "Patch complete"
exit 0
