#!/bin/bash
#
# Quick sync - deploy only modified files to Pi (faster)
# Usage: ./tools/quick_sync.sh [user@hostname]
#

set -e

PI_HOST=${1:-pi@raspberrypi.local}
REMOTE_PATH=/home/pi/open-TPT

# Sync project files (excludes .git, scratch, caches)
# --delete removes files on remote that no longer exist locally
rsync -avz --progress --delete \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='scratch/' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='venv/' \
    --exclude='.venv/' \
    --exclude='.claude/' \
    --exclude='*.webp' \
    --exclude='assets/tracks/' \
    ./ "${PI_HOST}:${REMOTE_PATH}/"

echo ""
echo "✓ Quick sync complete"
echo ""
