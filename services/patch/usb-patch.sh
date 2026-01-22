#!/bin/bash
# USB Patch Deployment Script for openTPT
# Checks for patch archive on USB at boot and performs full replacement
# Handles read-only rootfs with overlayroot using overlayroot-chroot
#
# Full replacement ensures clean updates with no orphaned files from old versions.
# User data (settings, lap times, tracks) is safe on USB at /mnt/usb/.opentpt/
set -euo pipefail

USB_MOUNT="/mnt/usb"
APP_DIR="/home/pi/open-TPT"
PATCH_LOG="$USB_MOUNT/.opentpt/patch.log"  # Log to USB (rootfs may be read-only)
PATCH_NAMES=("opentpt-patch.tar.gz" "opentpt-patch.zip")

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

is_overlayroot_active() {
    # Check if overlayroot overlay is active (/ mounted as overlay)
    grep -q ' / overlay' /proc/mounts 2>/dev/null
}

# Find patch archive
PATCH_FILE=""
for name in "${PATCH_NAMES[@]}"; do
    [[ -f "$USB_MOUNT/$name" ]] && PATCH_FILE="$USB_MOUNT/$name" && break
done

[[ -z "$PATCH_FILE" ]] && log "No patch archive found on USB" && exit 0

log "Found patch: $PATCH_FILE"

# Verify archive before making changes
log "Verifying archive integrity..."
if [[ "$PATCH_FILE" == *.tar.gz ]]; then
    tar -tzf "$PATCH_FILE" > /dev/null 2>&1 || { log "ERROR: Corrupt archive"; exit 0; }
elif [[ "$PATCH_FILE" == *.zip ]]; then
    unzip -t "$PATCH_FILE" > /dev/null 2>&1 || { log "ERROR: Corrupt archive"; exit 0; }
fi
log "Archive verified OK"

# Determine extraction method based on overlay status
if is_overlayroot_active; then
    log "Overlayroot active - using overlayroot-chroot to patch underlying filesystem"

    # Copy patch file to a location accessible within chroot
    # USB mount may not be visible inside chroot, so copy to /tmp (which is overlay)
    cp "$PATCH_FILE" /tmp/opentpt-patch-temp

    # Create extraction script to run inside chroot
    cat > /tmp/apply-patch.sh << 'PATCHSCRIPT'
#!/bin/bash
set -e
APP_DIR="/home/pi/open-TPT"
PATCH_FILE="/tmp/opentpt-patch-temp"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [[ "$PATCH_FILE" == *.tar.gz ]] || file "$PATCH_FILE" | grep -q gzip; then
    tar -xzf "$PATCH_FILE"
elif [[ "$PATCH_FILE" == *.zip ]] || file "$PATCH_FILE" | grep -q Zip; then
    unzip -q "$PATCH_FILE"
fi

chown -R pi:pi "$APP_DIR"
rm -f "$PATCH_FILE"
PATCHSCRIPT
    chmod +x /tmp/apply-patch.sh

    # Apply patch to underlying filesystem via overlayroot-chroot
    # The chroot provides write access to the lower (read-only) filesystem
    if overlayroot-chroot /tmp/apply-patch.sh; then
        log "Patch applied to underlying filesystem"
        rm -f /tmp/apply-patch.sh /tmp/opentpt-patch-temp
    else
        log "ERROR: Failed to apply patch via overlayroot-chroot"
        rm -f /tmp/apply-patch.sh /tmp/opentpt-patch-temp
        exit 0
    fi
else
    log "Normal filesystem - applying patch directly"

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

    chown -R pi:pi "$APP_DIR"
fi

# Delete patch file after successful install
rm -f "$PATCH_FILE"
log "Removed patch archive"

log "Patch complete"
exit 0
