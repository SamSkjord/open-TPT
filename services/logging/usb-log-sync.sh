#!/bin/bash
#
# USB Log Sync Script for openTPT
#
# Exports openTPT service logs to a USB drive for easy offline review.
# Appends new log entries to a daily file to build complete history.
#
# Usage:
#   usb-log-sync.sh [--full]
#
# Options:
#   --full    Export all logs since boot (for shutdown sync)
#

set -euo pipefail

USB_MOUNT="/mnt/usb"
LOG_DIR="$USB_MOUNT/logs"
DATE=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/opentpt_${DATE}.log"
CURSOR_FILE="$LOG_DIR/.last_cursor"

# Check if USB is mounted
if ! mountpoint -q "$USB_MOUNT" 2>/dev/null; then
    exit 0  # Silent exit if USB not mounted
fi

# Create log directory if needed
mkdir -p "$LOG_DIR"

# Determine export mode
if [[ "${1:-}" == "--full" ]]; then
    # Full export on shutdown - get everything since boot
    {
        echo ""
        echo "======== Log sync: $(date) (full) ========"
        journalctl -u openTPT.service --boot --no-pager 2>/dev/null || true
    } >> "$LOG_FILE"
else
    # Incremental export - only new entries since last sync
    if [[ -f "$CURSOR_FILE" ]]; then
        CURSOR=$(cat "$CURSOR_FILE")
        {
            journalctl -u openTPT.service --after-cursor="$CURSOR" --no-pager 2>/dev/null || true
        } >> "$LOG_FILE"
    else
        # First run - get last 5 minutes
        {
            echo "======== Log sync started: $(date) ========"
            journalctl -u openTPT.service --since=-5min --no-pager 2>/dev/null || true
        } >> "$LOG_FILE"
    fi

    # Save cursor for next incremental sync
    journalctl -u openTPT.service --show-cursor -n 0 2>/dev/null | grep -oP '(?<=-- cursor: ).*' > "$CURSOR_FILE" || true
fi

# Sync to ensure writes complete
sync

# Clean up old daily logs (keep last 7 days)
find "$LOG_DIR" -name "opentpt_*.log" -mtime +7 -delete 2>/dev/null || true
