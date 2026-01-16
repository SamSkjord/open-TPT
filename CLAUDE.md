# Claude Context - openTPT Project

**Version:** 0.17.9 | **Updated:** 2026-01-16

---

## Project Overview

**openTPT** (Open Tyre Pressure and Temperature Telemetry) - Raspberry Pi motorsport telemetry for real-time tyre, brake, camera, and radar monitoring.

| Attribute | Value |
|-----------|-------|
| Language | Python 3.11+ |
| Platform | Raspberry Pi 4/5 |
| Display | Waveshare 1024×600 HDMI |
| Graphics | SDL2/pygame with KMS/DRM |
| Architecture | Multi-threaded, bounded queues, lock-free rendering |
| Performance | 60 FPS, ≤12ms render time |
| **Spelling** | **British English throughout** |

---

## Critical Conventions

### British English - NON-NEGOTIABLE
| Use | Never |
|--------|---------|
| Tyre | Tire |
| Optimised | Optimized |
| Initialise | Initialize |
| Colour | Color |
| Centre | Center |

### Code Rules
1. **Always read files before editing** - Use Read tool, then Edit tool
2. **Never Write to existing files** - Only for new files
3. **Preserve indentation** - Match exact tabs/spaces from source
4. **Hardware requires sudo** - All I/O needs elevated privileges
5. **Lock-free rendering** - No blocking in render path
6. **Bounded queues** - All hardware handlers extend `BoundedQueueHardwareHandler`
7. **No emojis** - Never use emojis in code, comments, or documentation

---

## Production Environment

| Setting | Value |
|---------|-------|
| Pi IP | `192.168.199.246` |
| User | `pi` |
| Path | `/home/pi/open-TPT` |
| Service | `openTPT.service` |

### Hardware Status
- TPMS: 4/4 sensors (FL, FR, RL, RR)
- Multi-Camera: Dual USB (`/dev/video-rear`, `/dev/video-front`)
- NeoKey 1x4: Physical buttons
- Rotary Encoder: I2C QT with NeoPixel (0x36)
- Pico Thermal: 1/4 MLX90640 (FL)
- TOF Distance: Disabled (VL53L0X unreliable for ride height)
- Brake Temps: FL (MCP9601 dual 0x65/0x66), FR (ADC) - rear disabled
- Toyota Radar: can_b1_0 (keep-alive), can_b1_1 (tracks)
- OBD2: Speed, RPM, fuel level, Ford Mode 22 HV Battery SOC
- GPS: PA1616S at 10Hz (serial /dev/ttyS0) for lap timing
- NeoDriver: I2C LED strip at 0x60 (shift/delta/overtake modes)

---

## Directory Structure

```
openTPT/
├── main.py                          # Entry point
├── gui/
│   ├── display.py                   # Rendering + temperature overlays
│   ├── camera.py                    # Multi-camera + radar overlay
│   ├── menu.py                      # On-screen menu system
│   └── radar_overlay.py             # Radar visualisation
├── hardware/
│   ├── unified_corner_handler.py    # All tyre sensors
│   ├── tpms_input_optimized.py      # TPMS (tpms>=2.1.0)
│   ├── radar_handler.py             # Toyota radar
│   ├── obd2_handler.py              # OBD2/CAN
│   ├── gps_handler.py               # GPS serial NMEA parsing
│   ├── neodriver_handler.py         # NeoDriver LED strip
│   └── lap_timing_handler.py        # Lap timing logic
├── utils/
│   ├── config.py                    # ALL configuration
│   ├── settings.py                  # Persistent user settings
│   ├── hardware_base.py             # Bounded queue base class
│   ├── fuel_tracker.py              # Fuel consumption tracking
│   ├── lap_timing_store.py          # SQLite lap time persistence
│   └── telemetry_recorder.py        # CSV telemetry recording
└── opendbc/*.dbc                    # CAN message definitions
```

---

## I2C Hardware Map

### Addresses
| Address | Device | Purpose |
|---------|--------|---------|
| `0x08` | Pico | MLX90640 thermal slave (per corner) |
| `0x29` | VL53L0X | TOF distance (per corner) |
| `0x30` | NeoKey | 1x4 button input with NeoPixels |
| `0x36` | Seesaw | Rotary encoder with NeoPixel |
| `0x48` | ADS1115 | ADC for brake IR sensors |
| `0x5A` | MLX90614 | Single-point IR (per corner) |
| `0x60` | NeoDriver | I2C to NeoPixel LED strip |
| `0x65/0x66` | MCP9601 | Thermocouple (inner/outer brake) |
| `0x68` | ICM20649 | IMU for G-meter |
| `0x70` | TCA9548A | I2C mux (8 channels) |

### Mux Channels
| Channel | Corner | Bitmask |
|---------|--------|---------|
| 0 | FL | `0x01` |
| 1 | FR | `0x02` |
| 2 | RL | `0x04` |
| 3 | RR | `0x08` |

---

## Pico I2C Registers (Address 0x08)

### Key Registers
| Register | Name | Notes |
|----------|------|-------|
| `0x10` | Firmware Version | Read-only |
| `0x14` | Tyre Detected | 0/1 flag |
| `0x15` | Confidence | 0-100% |
| `0x20-21` | Left Temp | int16, tenths °C |
| `0x22-23` | Centre Temp | int16, tenths °C |
| `0x24-25` | Right Temp | int16, tenths °C |

Convert: `temp_celsius = int16_value / 10.0`

---

## Common Commands

### Deployment
```bash
./tools/quick_sync.sh pi@192.168.199.246    # Sync code
ssh pi@192.168.199.246 'sudo systemctl restart openTPT.service'
```

### Service Management
```bash
sudo systemctl status openTPT.service       # Status
sudo systemctl restart openTPT.service      # Restart
sudo journalctl -u openTPT.service -f       # Live logs
```

### Debug Commands
```bash
# I2C scan
sudo i2cdetect -y 1

# Select mux channel (FL=0x01, FR=0x02, RL=0x04, RR=0x08)
sudo i2cset -y 1 0x70 0x01

# TOF sensor check (FR)
sudo python3 -c "import board,busio,adafruit_tca9548a,adafruit_vl53l0x; i2c=busio.I2C(board.SCL,board.SDA); mux=adafruit_tca9548a.TCA9548A(i2c); print(f'FR TOF: {adafruit_vl53l0x.VL53L0X(mux[1]).range}mm')"

# Power status
vcgencmd get_throttled  # 0x0=OK, 0x50000=historical undervoltage
```

### Log Filtering
```bash
# By component
sudo journalctl -u openTPT.service -f | grep -iE "tof|pico|radar|imu"

# By corner
sudo journalctl -u openTPT.service --since "30 min ago" | grep "FL"

# Failures
sudo journalctl -u openTPT.service -f | grep -E "failures|error|backoff"
```

---

## Known Issues & Solutions

| Issue | Solution |
|-------|----------|
| **IMU I/O errors** | Non-critical, auto-retries. Restart service if persistent |
| **TOF dropouts** | Auto-reinit with backoff (v0.15.1+) |
| **I2C bus lockup** | Auto mux reset on GPIO17 (v0.12+). Power cycle if severe |
| **Heatmaps grey/offline** | Stale data cached 1s (v0.12+). Adjust `THERMAL_STALE_TIMEOUT` |
| **6+ hour crashes** | Fixed v0.11+ (GC every 60s, surface clear every 10min) |
| **Brake temps wrong** | Check `BRAKE_ROTOR_EMISSIVITY` in config.py (default 0.95) |
| **throttled=0x50000** | Historical undervoltage, normal on CM4-POE-UPS. Check bits 0-3 for current issues |

---

## Key Design Patterns

### Bounded Queue Handler
```python
from utils.hardware_base import BoundedQueueHardwareHandler

class MyHandler(BoundedQueueHardwareHandler):
    def __init__(self):
        super().__init__(queue_depth=2)

    def _poll_loop(self):
        while self._running:
            data = self.sensor.read()
            self._publish_snapshot(data)
            time.sleep(0.1)

    def get_snapshot(self):
        return self._get_snapshot()  # Lock-free
```

### Configuration
All settings in `utils/config.py`:
- Display/scaling, I2C addresses, sensor types
- Camera devices, radar/OBD2 channels
- Temperature thresholds, emissivity values

---

## Subsystem Quick Reference

### Multi-Camera (v0.8)
- Two USB cameras via udev rules (USB port to device name)
- Freeze-frame transitions (no checkerboard)
- Radar overlay on rear camera only

### Toyota Radar (v0.10)
- can_b1_1: Track data (RX), can_b1_0: Keep-alive (TX)
- Chevrons: green safe, yellow moderate, red rapid approach, blue overtaking
- Requires `cantools` package

### GPS and Lap Timing (v0.17)
- PA1616S GPS at 10Hz via /dev/ttyS0
- PPS time sync via chrony
- Lap times persisted to SQLite (`~/.opentpt/lap_timing/lap_timing.db`)
- Best lap loaded automatically when track selected

### Fuel Tracking (v0.17.9)
- OBD2 fuel level PID 0x2F
- Average consumption per lap calculation
- Refuelling detection with session reset
- Configurable warning/critical thresholds

### NeoDriver LED Strip (v0.17.2)
- I2C address 0x60, configurable pixel count
- Modes: shift (RPM), delta (lap time), overtake (radar), off
- Direction: centre-out, edges-in, left-to-right, right-to-left

### Brake Emissivity
- MLX90614/ADC sensors use e=1.0 default
- Software correction: `T_actual = T_measured / e^0.25`
- Configure per corner in `BRAKE_ROTOR_EMISSIVITY`
- Cast iron oxidised: 0.95, machined: 0.60-0.70

---

## Git Workflow

```bash
# British English in commits
git commit -m "Optimise thermal processing"  # correct
git commit -m "Optimize thermal processing"  # wrong
```

### Before Committing
- [ ] British English spelling
- [ ] No blocking in render path
- [ ] Test in mock mode (`./main.py --windowed`)
- [ ] Deploy and test on Pi
- [ ] Update CHANGELOG.md

---

## Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Project overview |
| `CHANGELOG.md` | Version history |
| `QUICKSTART.md` | Quick commands |
| `DEPLOYMENT.md` | Pi deployment |

---

## Final Notes

1. **British English is non-negotiable**
2. **Read before editing** - Always use Read tool first
3. **Lock-free rendering** - Never block in render path
4. **Test on Pi** - Mock mode doesn't catch hardware issues
5. **Bounded queues** - All hardware handlers must use them
6. **Graceful degradation** - System works with missing hardware
