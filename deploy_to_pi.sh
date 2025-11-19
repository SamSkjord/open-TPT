#!/bin/bash
#
# Deploy openTPT to Raspberry Pi
# Usage: ./deploy_to_pi.sh [user@hostname] [optional-path]
#
# Examples:
#   ./deploy_to_pi.sh pi@raspberrypi.local
#   ./deploy_to_pi.sh pi@192.168.1.100
#   ./deploy_to_pi.sh pi@raspberrypi.local /home/pi/openTPT
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
PI_HOST=${1:-pi@raspberrypi.local}
REMOTE_PATH=${2:-/home/pi/open-TPT}

echo -e "${GREEN}=== openTPT Deployment to Raspberry Pi ===${NC}"
echo ""
echo "Source:      $(pwd)"
echo "Destination: ${PI_HOST}:${REMOTE_PATH}"
echo ""

# Check if rsync is available
if ! command -v rsync &> /dev/null; then
    echo -e "${RED}Error: rsync not found. Please install rsync.${NC}"
    echo "  brew install rsync"
    exit 1
fi

# Test connection
echo -e "${YELLOW}Testing connection to Pi...${NC}"
if ! ssh -o ConnectTimeout=5 "${PI_HOST}" "echo 'Connection OK'" &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to ${PI_HOST}${NC}"
    echo "Please check:"
    echo "  1. Pi is powered on and connected to network"
    echo "  2. SSH is enabled on Pi (sudo raspi-config)"
    echo "  3. Hostname/IP is correct"
    echo "  4. SSH keys are set up (or password is correct)"
    exit 1
fi
echo -e "${GREEN}✓ Connection successful${NC}"
echo ""

# Create remote directory if it doesn't exist
echo -e "${YELLOW}Creating remote directory...${NC}"
ssh "${PI_HOST}" "mkdir -p ${REMOTE_PATH}"
echo -e "${GREEN}✓ Remote directory ready${NC}"
echo ""

# Rsync files to Pi
echo -e "${YELLOW}Syncing files...${NC}"
rsync -avz --progress \
    --exclude '.git' \
    --exclude '.DS_Store' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'scratch/' \
    --exclude '*.psd' \
    --exclude 'venv/' \
    --exclude '.venv/' \
    ./ "${PI_HOST}:${REMOTE_PATH}/"

echo ""
echo -e "${GREEN}✓ Files synced successfully${NC}"
echo ""

# Make scripts executable
echo -e "${YELLOW}Setting permissions...${NC}"
ssh "${PI_HOST}" "cd ${REMOTE_PATH} && chmod +x main.py tools/*.py deploy_to_pi.sh"
echo -e "${GREEN}✓ Permissions set${NC}"
echo ""

# Install dependencies if needed
echo -e "${YELLOW}Checking dependencies...${NC}"
ssh "${PI_HOST}" "cd ${REMOTE_PATH} && python3 -m pip list | grep -q pygame || echo 'pygame not found - run install.sh on Pi'"
echo ""

# Show summary
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Next steps:"
echo "  1. SSH to Pi:        ssh ${PI_HOST}"
echo "  2. Navigate to app:  cd ${REMOTE_PATH}"
echo "  3. Test performance: python3 tools/performance_test.py"
echo "  4. Run application:  ./main.py"
echo ""
echo "To auto-deploy on save, use:"
echo "  fswatch -o . | xargs -n1 -I{} ./deploy_to_pi.sh ${PI_HOST}"
echo ""
