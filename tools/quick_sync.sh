#!/bin/bash
#
# Quick sync - deploy only modified files to Pi (faster)
# Usage: ./tools/quick_sync.sh [user@hostname]
#

set -e

PI_HOST=${1:-pi@raspberrypi.local}
REMOTE_PATH=/home/pi/open-TPT

# Quick sync only Python files and configs
rsync -avz --progress \
    --include='*.py' \
    --include='*.md' \
    --include='*.yaml' \
    --include='*.json' \
    --include='*/' \
    --exclude='*' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='scratch/' \
    ./ "${PI_HOST}:${REMOTE_PATH}/"

echo ""
echo "✓ Quick sync complete"
echo ""
