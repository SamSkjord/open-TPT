# Quick Start Guide - openTPT

## Current Configuration
- **Pi IP:** `192.168.199.243`
- **User:** `pi`
- **Path:** `/home/pi/openTPT`
- **Status:** ✅ Production Ready

## Quick Deploy & Run

### Deploy from Mac
```bash
# Full deployment (first time or major changes)
./deploy_to_pi.sh pi@192.168.199.243

# Quick sync (code changes only - faster)
./tools/quick_sync.sh pi@192.168.199.243
```

### Run on Pi
```bash
# SSH to Pi
ssh pi@192.168.199.243

# Navigate to app
cd /home/pi/openTPT

# Run application (requires sudo for GPIO/hardware access)
sudo ./main.py

# Or run in windowed mode for testing
sudo ./main.py --windowed
```

### View Service Logs
```bash
# Real-time system service logs
ssh pi@192.168.199.243 "sudo journalctl -u openTPT.service -f"

# Check service status
ssh pi@192.168.199.243 "sudo systemctl status openTPT.service"
```

## Hardware Controls

### NeoKey 1x4 Buttons
- **Button 0:** Increase brightness
- **Button 1:** Decrease brightness
- **Button 2:** Cycle camera views (telemetry ↔ rear ↔ front)
- **Button 3:** Toggle UI overlay visibility

### Keyboard (Development)
- **Up/Down:** Brightness control
- **Spacebar:** Cycle camera views
- **T:** Toggle UI overlay
- **ESC:** Exit application

## Key Configuration Files

| File | Purpose |
|------|---------|
| `utils/config.py` | All system constants, positions, thresholds |
| `display_config.json` | Display resolution settings |
| `/etc/udev/rules.d/99-camera-names.rules` | Camera device naming (auto-installed) |
| `/etc/udev/rules.d/80-can-persistent-names.rules` | CAN bus naming (auto-installed) |

## Hardware Status

### Current Setup (v0.8)
- ✅ **TPMS:** 4/4 sensors auto-paired (FL, FR, RL, RR)
- ✅ **Multi-Camera:** Dual USB cameras with seamless switching
- ✅ **NeoKey 1x4:** All buttons functional
- ✅ **Pico Thermal:** 1/4 operational (FL connected)
- ⚠️ **ADS1115:** Not connected (brake temps unavailable)
- ⚠️ **Radar:** Optional (disabled by default)

## Camera Setup

### USB Port Assignment
Connect cameras to specific USB ports for deterministic identification:
- **Rear camera** → USB port 1.1 (creates `/dev/video-rear`)
- **Front camera** → USB port 1.2 (creates `/dev/video-front`)

Verify symlinks:
```bash
ssh pi@192.168.199.243 "ls -l /dev/video-*"
```

## Quick Troubleshooting

### Can't Connect to Pi
```bash
# Test network connectivity
ping 192.168.199.243

# Verify SSH access
ssh pi@192.168.199.243 "echo 'Connection OK'"
```

### Camera Issues
```bash
# Check camera devices
ssh pi@192.168.199.243 "ls -l /dev/video-*"

# Test camera with v4l2
ssh pi@192.168.199.243 "v4l2-ctl --list-devices"
```

### Service Not Starting
```bash
# Check service status
ssh pi@192.168.199.243 "sudo systemctl status openTPT.service"

# View recent logs
ssh pi@192.168.199.243 "sudo journalctl -u openTPT.service -n 50"

# Restart service
ssh pi@192.168.199.243 "sudo systemctl restart openTPT.service"
```

### Dependencies Missing
```bash
# SSH to Pi and re-run installation
ssh pi@192.168.199.243
cd /home/pi/openTPT
sudo ./install.sh
```

## Development Workflow

### 1. Edit Code on Mac
```bash
# Open project in your editor
code /Users/sam/git/open-TPT
```

### 2. Test Locally (Mock Mode)
```bash
cd /Users/sam/git/open-TPT
./main.py --windowed
```

### 3. Deploy to Pi
```bash
# Quick sync for rapid iteration
./tools/quick_sync.sh pi@192.168.199.243
```

### 4. Test on Pi
```bash
# SSH and run with real hardware
ssh pi@192.168.199.243
cd /home/pi/openTPT
sudo ./main.py
```

## Auto-Deploy on Save
```bash
# Install fswatch on Mac
brew install fswatch

# Auto-deploy when files change
fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@192.168.199.243
```

## Production Deployment

### Enable Systemd Service
```bash
# Service is auto-enabled by install.sh
# To manually control:
ssh pi@192.168.199.243

# Enable auto-start on boot
sudo systemctl enable openTPT.service

# Start service now
sudo systemctl start openTPT.service

# Check status
sudo systemctl status openTPT.service
```

## Documentation References

| Document | Purpose |
|----------|---------|
| `README.md` | Complete project documentation |
| `QUICKSTART.md` | This file - quick reference |
| `DEPLOYMENT.md` | Detailed deployment workflow |
| `PERFORMANCE_OPTIMIZATIONS.md` | Technical implementation details |
| `WAVESHARE_DUAL_CAN_HAT_SETUP.md` | CAN hardware configuration |
| `CHANGELOG.md` | Version history and features |
| `open-TPT_System_Plan.md` | Long-term architecture plan |

## Key Features (v0.8)

- ✅ Real-time TPMS monitoring with auto-pairing
- ✅ Dual USB camera support with seamless switching
- ✅ Tyre thermal imaging (MLX90640 or MLX90614)
- ✅ Brake temperature monitoring (IR sensors + ADC)
- ✅ Lock-free rendering (60 FPS target)
- ✅ Numba-optimised thermal processing
- ✅ Optional Toyota radar overlay
- ✅ Deterministic hardware identification (udev rules)
- ✅ Performance monitoring and validation

## British English Reminders

Use British spelling throughout:
- ✅ **Tyre** (not Tire)
- ✅ **Optimised** (not Optimized)
- ✅ **Initialise** (not Initialize)
- ✅ **Colour** (not Color)
- ✅ **Centre** (not Center)

---

**Status:** ✅ System operational with multi-camera support
**Last Updated:** 2025-11-19 (v0.8)
