# Quick Start Guide - openTPT

## Current Configuration
- **Pi IP:** `192.168.199.246`
- **User:** `pi`
- **Path:** `/home/pi/open-TPT`
- **Status:** Production Ready (v0.17.9)

## Quick Deploy & Run

### Deploy from Mac
```bash
# Initial setup: SSH to Pi and clone repository
ssh pi@192.168.199.246
git clone https://github.com/SamSkjord/open-TPT.git
cd open-TPT
sudo ./install.sh

# Update: SSH to Pi and pull latest changes
ssh pi@192.168.199.246
cd /home/pi/open-TPT
git pull
sudo ./install.sh  # If dependencies changed

# Quick sync (code changes only - faster for development)
./tools/quick_sync.sh pi@192.168.199.246
```

### Run on Pi
```bash
# SSH to Pi
ssh pi@192.168.199.246

# Navigate to app
cd /home/pi/open-TPT

# Run application (requires sudo for GPIO/hardware access)
sudo ./main.py

# Or run in windowed mode for testing
sudo ./main.py --windowed
```

### View Service Logs
```bash
# Real-time system service logs
ssh pi@192.168.199.246 "sudo journalctl -u openTPT.service -f"

# Check service status
ssh pi@192.168.199.246 "sudo systemctl status openTPT.service"
```

## Hardware Controls

### NeoKey 1x4 Buttons
- **Button 0:** Cycle brightness (30% → 50% → 70% → 90% → 100%)
- **Button 1:** Page settings (hide overlay, reset peaks, etc.)
- **Button 2:** Switch within category (camera: rear↔front | UI: pages)
- **Button 3:** Switch view mode (camera ↔ UI)

### Keyboard (Development)
- **Up:** Cycle brightness
- **Down / T:** Page settings
- **Spacebar:** Switch within category
- **Right:** Switch view mode (camera ↔ UI)
- **ESC:** Exit application

## Key Configuration Files

| File | Purpose |
|------|---------|
| `utils/config.py` | All system constants, positions, thresholds |
| `utils/settings.py` | Persistent user settings (~/.opentpt_settings.json) |
| `/etc/udev/rules.d/99-camera-names.rules` | Camera device naming (auto-installed) |
| `/etc/udev/rules.d/80-can-persistent-names.rules` | CAN bus naming (auto-installed) |

## Hardware Status

### Current Setup (v0.17.9)
- **TPMS:** 4/4 sensors auto-paired (FL, FR, RL, RR)
- **Multi-Camera:** Dual USB cameras with seamless switching
- **NeoKey 1x4:** All buttons functional
- **Rotary Encoder:** I2C QT with NeoPixel (0x36)
- **G-Meter:** ICM-20649 IMU with real-time acceleration tracking
- **OBD2:** Vehicle speed, RPM, fuel level via CAN bus
- **CAN Auto-Start:** All 4 CAN interfaces automatically configured on boot
- **Pico Thermal:** 1/4 operational (FL connected)
- **Brake Temps:** FL (MCP9601 dual thermocouples), FR (ADC)
- **Toyota Radar:** Enabled (can_b1_0/can_b1_1)
- **GPS:** PA1616S at 10Hz for lap timing
- **NeoDriver:** LED strip for shift/delta/overtake

## Camera Setup

### USB Port Assignment
Connect cameras to specific USB ports for deterministic identification:
- **Rear camera** → USB port 1.1 (creates `/dev/video-rear`)
- **Front camera** → USB port 1.2 (creates `/dev/video-front`)

Verify symlinks:
```bash
ssh pi@192.168.199.246 "ls -l /dev/video-*"
```

## CAN Bus Setup

### OBD2 Speed Reading
The system automatically brings up all CAN interfaces on boot via the `can-setup.service`. OBD-II is connected to `can_b2_1` (Board 2, CAN_1 connector).

Enable/disable OBD2 speed in `utils/config.py`:
```python
OBD_ENABLED = True  # Set to False to disable
OBD_CHANNEL = "can_b2_1"  # OBD-II interface
```

Verify CAN interfaces:
```bash
ssh pi@192.168.199.246 "ip link show | grep can"
```

Manual CAN control (if needed):
```bash
# Bring down interface
sudo ip link set can_b2_1 down

# Bring up interface
sudo ip link set can_b2_1 up type can bitrate 500000

# Check CAN setup service status
sudo systemctl status can-setup.service
```

## Quick Troubleshooting

### Can't Connect to Pi
```bash
# Test network connectivity
ping 192.168.199.246

# Verify SSH access
ssh pi@192.168.199.246 "echo 'Connection OK'"
```

### Camera Issues
```bash
# Check camera devices
ssh pi@192.168.199.246 "ls -l /dev/video-*"

# Test camera with v4l2
ssh pi@192.168.199.246 "v4l2-ctl --list-devices"
```

### Service Not Starting
```bash
# Check service status
ssh pi@192.168.199.246 "sudo systemctl status openTPT.service"

# View recent logs
ssh pi@192.168.199.246 "sudo journalctl -u openTPT.service -n 50"

# Restart service
ssh pi@192.168.199.246 "sudo systemctl restart openTPT.service"
```

### Dependencies Missing
```bash
# SSH to Pi and re-run installation
ssh pi@192.168.199.246
cd /home/pi/open-TPT
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
./tools/quick_sync.sh pi@192.168.199.246
```

### 4. Test on Pi
```bash
# SSH and run with real hardware
ssh pi@192.168.199.246
cd /home/pi/open-TPT
sudo ./main.py
```

## Auto-Deploy on Save
```bash
# Install fswatch on Mac
brew install fswatch

# Auto-deploy when files change
fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@192.168.199.246
```

## Production Deployment

### Enable Systemd Service
```bash
# Service is auto-enabled by install.sh
# To manually control:
ssh pi@192.168.199.246

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
| `CHANGELOG.md` | Version history and features |

## Key Features (v0.17.9)

- Real-time TPMS monitoring with auto-pairing
- Dual USB camera support with seamless switching
- G-meter with IMU acceleration tracking and calibration wizard
- OBD2 vehicle data (speed, RPM, fuel level, HV battery SOC)
- Automatic CAN interface setup on boot
- Tyre thermal imaging (MLX90640 or MLX90614) with temperature overlays
- Brake temperature monitoring (MCP9601 thermocouples, IR sensors + ADC)
- Lock-free rendering (60 FPS target)
- Numba-optimised thermal processing
- Toyota radar overlay with collision warnings
- GPS lap timing with persistence (best laps saved)
- Fuel tracking (consumption, laps remaining, refuelling detection)
- NeoDriver LED strip (shift lights, delta, overtake)
- Telemetry recording to CSV (10Hz)
- On-screen menu system with rotary encoder
- Persistent user settings
- Deterministic hardware identification (udev rules)
- Performance monitoring and validation

## British English Reminders

Use British spelling throughout:
- **Tyre** (not Tire)
- **Optimised** (not Optimized)
- **Initialise** (not Initialize)
- **Colour** (not Color)
- **Centre** (not Center)

---

**Status:** System operational with full telemetry stack
**Last Updated:** 2026-01-16 (v0.17.9)
