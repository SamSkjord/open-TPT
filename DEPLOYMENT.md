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
ssh-copy-id pi@192.168.199.246
# or with IP: ssh-copy-id pi@192.168.199.246
```

### 2. First-Time Pi Setup

SSH to the Pi and clone the repository:

```bash
# SSH to Pi
ssh pi@192.168.199.246

# Update system
sudo apt update && sudo apt upgrade -y

# Clone repository
cd /home/pi
git clone https://github.com/SamSkjord/open-TPT.git
cd open-TPT

# Run the install script
sudo ./install.sh
```

The install script will:
- ✓ Install Python dependencies
- ✓ Set up udev rules for cameras and CAN
- ✓ Configure systemd service
- ✓ Set up CAN interfaces
- ✓ Enable auto-start on boot

### 3. GPS and Time Sync Setup

The install script handles GPS configuration automatically. It:
- Enables UART (GPIO 14/15) and PPS (GPIO 18) in config.txt
- Configures GPS for 10Hz RMC-only output
- Sets up chrony for PPS time sync
- Disables gpsd (openTPT reads serial directly for 10Hz)

**Manual setup** (if not using install.sh):

```bash
# Add to /boot/firmware/config.txt
sudo tee -a /boot/firmware/config.txt << EOF

# ==== openTPT GPS Configuration ====
enable_uart=1
dtoverlay=pps-gpio,gpiopin=18
# ==== end openTPT GPS Configuration ====
EOF

# Reboot to enable UART and PPS
sudo reboot
```

After reboot, configure GPS for 10Hz:

```bash
# Install packages
sudo apt-get install -y chrony pps-tools

# Configure chrony for PPS time sync
sudo tee -a /etc/chrony/chrony.conf << EOF

# PPS from GPS (precise timing)
# openTPT sets coarse time from NMEA, PPS refines to nanosecond precision
refclock PPS /dev/pps0 refid PPS precision 1e-7 prefer
EOF

# Keep NTP enabled as fallback
sudo timedatectl set-ntp true

# Restart chrony
sudo systemctl restart chrony
```

The `gps-config.service` runs at boot to configure the GPS module for 10Hz RMC-only output before openTPT starts.

**Verify GPS:**

```bash
# Check PPS signal (should show pulses every second)
sudo ppstest /dev/pps0

# Check chrony PPS sync
chronyc sources

# Test GPS handler directly
cd /home/pi/open-TPT
sudo python3 -c "
from hardware.gps_handler import GPSHandler
import time
h = GPSHandler()
time.sleep(3)
s = h.get_snapshot()
print(f'Update rate: {s.data.get(\"update_rate\", 0):.1f} Hz')
print(f'Position: {s.data.get(\"latitude\")}, {s.data.get(\"longitude\")}')
h.stop()
"
```

Expected output: ~10Hz update rate.

### 4. Dual CAN HAT Hardware Setup

The install script configures the software (device tree overlays, udev rules), but stacking two Waveshare 2-CH CAN HAT+ boards requires physical jumper changes on Board 2.

**Board 1 (Bottom)** - No changes needed, uses SPI1 with default jumpers.

**Board 2 (Top)** - Must be reconfigured for SPI0:

| Jumper Block | Setting |
|--------------|---------|
| INT_0 | D23 (GPIO23) |
| INT_1 | D25 (GPIO25) |
| CE_0 | CE0 (middle position) |
| CE_1 | CE1 (middle position) - NOT D18 |
| SPI MISO/MOSI/SCK | All 5 jumpers to SPI0 positions |

**Important:** GPIO18 (D18) is SPI1 CE0, not SPI0 CE1. The CE_1 jumper must be on the middle "CE1" position.

After running `install.sh` and rebooting, verify interfaces:
```bash
ip link show | grep can_b
# Should show: can_b1_0, can_b1_1, can_b2_0, can_b2_1
```

Interface mapping:
- `can_b1_0` - Board 1, CAN_0 connector
- `can_b1_1` - Board 1, CAN_1 connector
- `can_b2_0` - Board 2, CAN_0 connector
- `can_b2_1` - Board 2, CAN_1 connector (typically OBD-II)

### 5. RTC Setup (CM4-POE-UPS-BASE)

The CM4-POE-UPS-BASE carrier has a PCF85063A RTC on I2C-10. To enable it:

```bash
# Add to /boot/firmware/config.txt (install.sh may already include this)
CFG=/boot/firmware/config.txt
[ -f /boot/config.txt ] && CFG=/boot/config.txt

sudo sed -i -e '/^dtparam=i2c_vc=/d' -e '/^dtoverlay=i2c-rtc/d' "$CFG"
echo 'dtparam=i2c_vc=on' | sudo tee -a "$CFG"
echo 'dtoverlay=i2c-rtc,pcf85063a,i2c_csi_dsi' | sudo tee -a "$CFG"
sudo reboot
```

After reboot, verify RTC:
```bash
sudo i2cdetect -y 10          # Should show 0x51
cat /sys/class/rtc/rtc0/name  # Should show: rtc-pcf85063 10-0051
```

Set RTC time from system:
```bash
sudo hwclock --systohc --utc
```

Optional: restore time from RTC on boot (useful when no network):
```bash
sudo tee /etc/systemd/system/rtc-hctosys.service >/dev/null <<'EOF'
[Unit]
Description=Set system time from RTC
After=dev-rtc.device
[Service]
Type=oneshot
ExecStart=/usr/sbin/hwclock --hctosys --utc
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable rtc-hctosys.service
```

## Deployment Methods

### Method 1: Git Pull (Recommended for Updates)

Update to latest version:

```bash
# SSH to Pi
ssh pi@192.168.199.246
cd /home/pi/open-TPT

# Pull latest changes
git pull

# Re-run installer if dependencies changed
sudo ./install.sh
```

### Method 2: Quick Sync (Fast Updates for Development)

Only sync Python files and configs (much faster):

```bash
./tools/quick_sync.sh pi@192.168.199.246
```

Use this when you've only changed code, not assets.

### Method 3: Manual rsync

For custom sync needs:

```bash
# Sync specific directory
rsync -avz ./hardware/ pi@192.168.199.246:/home/pi/open-TPT/hardware/

# Sync with delete (match source exactly)
rsync -avz --delete ./ pi@192.168.199.246:/home/pi/open-TPT/
```

### Method 4: Watch and Auto-Deploy

Automatically deploy on file changes (requires `fswatch`):

```bash
# Install fswatch on Mac
brew install fswatch

# Watch for changes and auto-deploy
fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@192.168.199.246
```

## Testing on Pi

### 1. Performance Tests

```bash
# SSH to Pi
ssh pi@192.168.199.246

# Test the application
cd /home/pi/open-TPT
sudo ./main.py --windowed
```

The application will display performance metrics in real-time every 10 seconds.

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
ping 192.168.199.246

# Test SSH
ssh pi@192.168.199.246 "echo 'Connection OK'"

# Or use hostname if mDNS configured
ping raspberrypi.local
```

### Permission Denied

```bash
# Ensure quick sync script is executable
chmod +x tools/quick_sync.sh

# Check remote directory permissions
ssh pi@192.168.199.246 "ls -la /home/pi/open-TPT"
```

### Dependencies Not Installed

```bash
# SSH to Pi and install manually
ssh pi@192.168.199.246
cd /home/pi/open-TPT
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
   fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@192.168.199.246
   ```

2. **Terminal 2** - SSH session on Pi:
   ```bash
   ssh pi@192.168.199.246
   cd /home/pi/open-TPT
   ./main.py --windowed
   ```

3. Edit code on Mac, save, and it auto-deploys + restart app on Pi

### Remote Debugging

Use VS Code Remote SSH extension:
1. Install "Remote - SSH" extension
2. Connect to Pi
3. Open `/home/pi/open-TPT`
4. Debug directly on Pi

### Performance Profiling on Pi

```bash
# CPU profile
ssh pi@192.168.199.246
cd /home/pi/open-TPT
python3 -m cProfile -o profile.stats main.py
python3 -c "import pstats; p=pstats.Stats('profile.stats'); p.sort_stats('cumulative'); p.print_stats(20)"

# Copy profile back to Mac for analysis
scp pi@192.168.199.246:/home/pi/open-TPT/profile.stats ./
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
- [ ] Deploy to Pi: `./deploy_to_pi.sh pi@192.168.199.246`
- [ ] Test with actual hardware connected
- [ ] Verify all sensors reporting correctly
- [ ] Check performance summary meets targets
- [ ] Test camera toggle and UI controls
- [ ] Run for 10+ minutes to check stability
- [ ] Enable systemd service for auto-start

## Boot Time Optimisation

For production use, optimise boot time to under 7 seconds:

```bash
# SSH to Pi
ssh pi@192.168.199.246
cd /home/pi/open-TPT

# Run the boot optimisation script
sudo ./config/boot/optimize-boot.sh

# Reboot to apply
sudo reboot
```

The script automatically:
- Removes boot delays (`boot_delay=0`, `initial_turbo=60`)
- Skips filesystem check (`fsck.mode=skip`)
- Disables serial console (saves ~0.5s)
- Disables unnecessary services (avahi, wpa_supplicant, etc.)
- Configures openTPT to start at `sysinit.target` (before network)
- Installs boot splash service (displays `assets/splash.png` immediately)

### Boot Splash Services

Two services work together to provide seamless splash screen display:

**1. fbi-splash.service** (`config/boot/fbi-splash.service`)

Displays `assets/splash.png` using framebuffer image viewer (fbi) as early as possible during boot. This runs before the main application starts.

```bash
# Install/update the service
sudo cp /home/pi/open-TPT/config/boot/fbi-splash.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable fbi-splash.service
```

Key features:
- Waits up to 5 seconds for `/dev/fb0` to become available
- Uses `--rotate 3` for correct display orientation (270 degrees)
- Runs at `sysinit.target` for earliest possible display

**2. openTPT.service** (`openTPT.service`)

The main application service starts after fbi-splash and kills the fbi process once pygame has initialised the display, providing a seamless transition.

Service chain: `sysinit.target` -> `fbi-splash.service` -> `openTPT.service`

**Customising the splash image:**

Replace `assets/splash.png` with your own image. The image should be:
- PNG format
- Portrait orientation (will be rotated 270 degrees for landscape display)
- Recommended size: 600x1024 pixels

After reboot, verify boot time:
```bash
systemd-analyze                              # Total boot time
systemd-analyze blame                        # Service times
systemd-analyze critical-chain openTPT.service  # Critical path
```

**Note**: WiFi is disabled at boot for speed. To enable manually:
```bash
sudo systemctl start wpa_supplicant
```

## Systemd Service (Production)

For production deployment, enable the systemd service:

```bash
# SSH to Pi
ssh pi@192.168.199.246

# Copy service file
sudo cp /home/pi/open-TPT/openTPT.service /etc/systemd/system/

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
2. Deploy to Pi: `./deploy_to_pi.sh pi@192.168.199.246`
3. Test on Pi
4. If production, restart service:
   ```bash
   ssh pi@192.168.199.246 "sudo systemctl restart openTPT.service"
   ```

---

**Note**: Always test thoroughly on Pi before deploying to vehicle!
