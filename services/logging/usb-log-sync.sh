#!/bin/bash
#
# USB Log Sync Script for openTPT
#
# Exports recent openTPT service logs to a USB drive for easy offline review.
# Logs are written to /mnt/usb/logs/ with timestamped filenames.
#
# Usage:
#   usb-log-sync.sh [--full]
#
# Options:
#   --full    Export all logs since boot (not just last 2 hours)
#

set -euo pipefail

USB_MOUNT="/mnt/usb"
LOG_DIR="$USB_MOUNT/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/opentpt_${TIMESTAMP}.log"

# Check if USB is mounted
if ! mountpoint -q "$USB_MOUNT" 2>/dev/null; then
    echo "USB not mounted at $USB_MOUNT - skipping log sync"
    exit 0
fi

# Create log directory if needed
mkdir -p "$LOG_DIR"

# Determine time range
if [[ "${1:-}" == "--full" ]]; then
    TIME_ARGS="--boot"
    echo "Exporting all logs since boot..."
else
    TIME_ARGS="--since=-2h"
    echo "Exporting last 2 hours of logs..."
fi

# Export openTPT service logs
echo "Writing logs to $LOG_FILE"
journalctl -u openTPT.service $TIME_ARGS --no-pager > "$LOG_FILE" 2>/dev/null || true

# Also export related services for context
{
    echo ""
    echo "======== CAN Setup Service ========"
    journalctl -u can-setup.service $TIME_ARGS --no-pager 2>/dev/null || true

    echo ""
    echo "======== GPS Config Service ========"
    journalctl -u gps-config.service $TIME_ARGS --no-pager 2>/dev/null || true

    echo ""
    echo "======== USB Patch Service ========"
    journalctl -u usb-patch.service $TIME_ARGS --no-pager 2>/dev/null || true
} >> "$LOG_FILE"

# Sync to ensure writes complete
sync

# Clean up old logs (keep last 10)
cd "$LOG_DIR"
ls -t opentpt_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f

LOG_SIZE=$(du -h "$LOG_FILE" | cut -f1)
echo "Log sync complete: $LOG_FILE ($LOG_SIZE)"
