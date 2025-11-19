# Deployment Guide - Mac to Raspberry Pi

## Development Workflow

Development is done on Mac, then deployed to Raspberry Pi for testing.

## Prerequisites

### On Mac
- SSH access to Raspberry Pi
- `rsync` installed (comes with macOS, or `brew install rsync`)

### On Raspberry Pi
- SSH enabled (`sudo raspi-config` → Interface Options → SSH)
- Python 3.7+ installed
- Network connectivity

## Initial Setup

### 1. Set up SSH Key (Recommended)

This avoids entering password every deployment:

```bash
# On Mac - generate key if you don't have one
ssh-keygen -t ed25519

# Copy key to Pi
ssh-copy-id pi@192.168.199.243
# or with IP: ssh-copy-id pi@192.168.199.243
```

### 2. First-Time Pi Setup

SSH to the Pi and install dependencies:

```bash
# SSH to Pi
ssh pi@192.168.199.243

# Update system
sudo apt update && sudo apt upgrade -y

# Run the install script (when you first deploy)
cd /home/pi/openTPT
chmod +x install.sh
./install.sh
```

## Deployment Methods

### Method 1: Full Deployment (Recommended)

Deploy everything including assets:

```bash
cd /Users/sam/git/open-TPT

# Deploy to default location (/home/pi/openTPT)
./deploy_to_pi.sh pi@192.168.199.243

# Or use hostname (if mDNS configured)
./deploy_to_pi.sh pi@192.168.199.243

# Or deploy to custom location
./deploy_to_pi.sh pi@192.168.199.243 /opt/openTPT
```

The script will:
- ✓ Test connection
- ✓ Create directories
- ✓ Sync all files (excluding .git, scratch/, etc.)
- ✓ Set permissions
- ✓ Check dependencies

### Method 2: Quick Sync (Fast Updates)

Only sync Python files and configs (much faster):

```bash
./tools/quick_sync.sh pi@192.168.199.243
```

Use this when you've only changed code, not assets.

### Method 3: Manual rsync

For custom sync needs:

```bash
# Sync specific directory
rsync -avz ./hardware/ pi@192.168.199.243:/home/pi/openTPT/hardware/

# Sync with delete (match source exactly)
rsync -avz --delete ./ pi@192.168.199.243:/home/pi/openTPT/
```

### Method 4: Watch and Auto-Deploy

Automatically deploy on file changes (requires `fswatch`):

```bash
# Install fswatch on Mac
brew install fswatch

# Watch for changes and auto-deploy
fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@192.168.199.243
```

## Testing on Pi

### 1. Performance Tests

```bash
# SSH to Pi
ssh pi@192.168.199.243

# Run performance tests
cd /home/pi/openTPT
python3 tools/performance_test.py
```

Expected output:
```
Test 1: Thermal Zone Processor
  ✓ PASS: Average time < 1.0ms target

Test 2: Bounded Queue Handler
  ✓ PASS: Average read < 100µs target
```

### 2. Run Main Application

```bash
# Windowed mode (for testing over VNC/X11)
./main.py --windowed

# Fullscreen mode (normal operation)
./main.py
```

### 3. Check Performance Monitoring

The app prints performance summary every 10 seconds:

```
=== Performance Summary ===
FPS: 60.0
Render Time: avg=8.23ms, max=11.54ms, p95=10.12ms, p99=11.32ms

Hardware Update Rates:
  TPMS: 1.0 Hz
  Brakes: 10.0 Hz
  Thermal: 4.0 Hz

Thermal Processing Times:
  FL: 0.423ms ✓
```

## Troubleshooting

### Connection Issues

```bash
# Test basic connectivity
ping 192.168.199.243

# Test SSH
ssh pi@192.168.199.243 "echo 'Connection OK'"

# Or use hostname if mDNS configured
ping raspberrypi.local
./deploy_to_pi.sh pi@raspberrypi.local
```

### Permission Denied

```bash
# Ensure deploy script is executable
chmod +x deploy_to_pi.sh
chmod +x tools/quick_sync.sh

# Check remote directory permissions
ssh pi@192.168.199.243 "ls -la /home/pi/openTPT"
```

### Dependencies Not Installed

```bash
# SSH to Pi and install manually
ssh pi@192.168.199.243
cd /home/pi/openTPT
pip3 install -r requirements.txt
```

### Slow Performance on Pi

Check which handlers are being used:

```bash
# Should see:
# "Using optimized hardware handlers with bounded queues"

# If you see warnings about Numba:
pip3 install numba
```

## Development Tips

### Quick Edit-Deploy-Test Cycle

1. **Terminal 1** - Watch and auto-deploy:
   ```bash
   cd /Users/sam/git/open-TPT
   fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@192.168.199.243
   ```

2. **Terminal 2** - SSH session on Pi:
   ```bash
   ssh pi@192.168.199.243
   cd /home/pi/openTPT
   ./main.py --windowed
   ```

3. Edit code on Mac, save, and it auto-deploys + restart app on Pi

### Remote Debugging

Use VS Code Remote SSH extension:
1. Install "Remote - SSH" extension
2. Connect to Pi
3. Open `/home/pi/openTPT`
4. Debug directly on Pi

### Performance Profiling on Pi

```bash
# CPU profile
ssh pi@192.168.199.243
cd /home/pi/openTPT
python3 -m cProfile -o profile.stats main.py
python3 -c "import pstats; p=pstats.Stats('profile.stats'); p.sort_stats('cumulative'); p.print_stats(20)"

# Copy profile back to Mac for analysis
scp pi@192.168.199.243:/home/pi/openTPT/profile.stats ./
```

## Files Excluded from Deployment

The deployment script automatically excludes:
- `.git/` - Git repository data
- `.DS_Store` - Mac filesystem metadata
- `__pycache__/` - Python bytecode cache
- `*.pyc` - Compiled Python files
- `scratch/` - Experimental/test code
- `*.psd` - Photoshop source files
- `venv/`, `.venv/` - Virtual environments

Edit `deploy_to_pi.sh` to customize exclusions.

## Deployment Checklist

Before deploying to production:

- [ ] Test on Mac with mock mode: `./main.py --windowed`
- [ ] Run performance tests locally: `python3 tools/performance_test.py`
- [ ] Deploy to Pi: `./deploy_to_pi.sh pi@192.168.199.243`
- [ ] Run performance tests on Pi
- [ ] Test with actual hardware connected
- [ ] Verify all sensors reporting correctly
- [ ] Check performance summary meets targets
- [ ] Test camera toggle and UI controls
- [ ] Run for 10+ minutes to check stability
- [ ] Enable systemd service for auto-start

## Systemd Service (Production)

For production deployment, enable the systemd service:

```bash
# SSH to Pi
ssh pi@192.168.199.243

# Copy service file
sudo cp /home/pi/openTPT/openTPT.service /etc/systemd/system/

# Enable and start service
sudo systemctl enable openTPT.service
sudo systemctl start openTPT.service

# Check status
sudo systemctl status openTPT.service

# View logs
sudo journalctl -u openTPT.service -f
```

## Update Workflow

1. Develop and test on Mac
2. Deploy to Pi: `./deploy_to_pi.sh pi@192.168.199.243`
3. Test on Pi
4. If production, restart service:
   ```bash
   ssh pi@192.168.199.243 "sudo systemctl restart openTPT.service"
   ```

---

**Note**: Always test thoroughly on Pi before deploying to vehicle!
