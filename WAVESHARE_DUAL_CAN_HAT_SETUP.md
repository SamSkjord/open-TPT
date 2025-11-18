# Raspberry Pi CM4 - Dual Waveshare 2-CH CAN HAT+ Setup

Complete configuration guide for dual Waveshare 2-CH CAN HAT+ boards on CM4-POE-UPS-BASE carrier running Raspberry Pi OS Trixie.

> Since November 2025 the top-level `install.sh` script applies the device-tree overlays and persistent CAN naming rules described below. Run the script after every pull to keep the configuration in sync, and use the manual steps here for verification or for bespoke setups.

## Quick Start

1. On the Raspberry Pi, run `sudo ./install.sh` from the project root (installs dependencies, writes the `config.txt` block, and deploys the udev rule from `config/can/80-can-persistent-names.rules`).
2. Reboot so the kernel loads the new overlays and udev renames the interfaces.
3. Enable whichever buses you need, for example:
   ```bash
   sudo ip link set can_b1_0 up type can bitrate 500000
   sudo ip link set can_b2_1 up type can bitrate 500000   # OBD-II
   ```
4. Verify stable naming via `ip -details link show can_b2_1` (the interface sticks to `spi0.1` regardless of probe order).

The rest of this document captures the underlying wiring details in case you need to audit or modify the automated steps.

## Hardware Configuration

### CAN HAT Stack
**Board 1 (Bottom/First)** - Default Configuration
- SPI1 bus
- CAN_0: SPI1 CE1 (GPIO7), interrupt GPIO22
- CAN_1: SPI1 CE2 (GPIO16), interrupt GPIO13

**Board 2 (Top/Second)** - Modified Configuration
- SPI0 bus
- CAN_0: SPI0 CE0 (GPIO8), interrupt GPIO23
- CAN_1: SPI0 CE1 (GPIO7), interrupt GPIO25

### Board 2 Jumper Settings

**CAN SELECTION (Left side):**
- INT_0: D23 (GPIO23)
- INT_1: D25 (GPIO25)
- CE_0: CE0 (middle position - GPIO8)
- CE_1: CE1 (middle position - GPIO7) <- NOT D18!

**SPI SELECTION (Right side):**
All 5 jumpers moved to SPI0 positions:
- MISO: SPI0 MISO
- MOSI: SPI0 MOSI
- SCK: SPI0 SCLK
- Plus the CE jumpers above

**Critical Note:** GPIO18 (D18) is SPI1 CE0, NOT SPI0 CE1. CE_1 must be on the middle "CE1" position which is GPIO7 for SPI0 operation.

## Boot Configuration

### `/boot/firmware/config.txt`

`install.sh` ensures the following block (wrapped in `# ==== openTPT Dual Waveshare 2-CH CAN HAT+ ====` markers) exists at the bottom of `/boot/firmware/config.txt` (or `/boot/config.txt` on older images). Remove any conflicting `dtparam=i2s` / `spi` lines before re-running the script if you have hand-edited the file.

```ini
# For more options and information see
# http://rptl.io/configtxt
# Some settings may impact device functionality. See link above for details

disable_splash=1

# ============================================================================
# Hardware Interface Configuration
# ============================================================================
dtparam=i2c_arm=on
dtparam=i2s=off        # Disabled to free GPIO19 for SPI1_MISO
dtparam=spi=on

# Enable audio (loads snd_bcm2835)
#dtparam=audio=on

# ============================================================================
# System Configuration
# ============================================================================
# Automatically load overlays for detected cameras
camera_auto_detect=1

# Automatically load overlays for detected DSI displays
display_auto_detect=1

# Automatically load initramfs files, if found
auto_initramfs=1

# Enable DRM VC4 V3D driver
dtoverlay=vc4-kms-v3d
max_framebuffers=2

# Don't have the firmware create an initial video= setting in cmdline.txt.
# Use the kernel's default instead.
disable_fw_kms_setup=1

# Run in 64-bit mode
arm_64bit=1

# Disable compensation for displays with overscan
disable_overscan=1

# Run as fast as firmware / board allows
arm_boost=1

# ============================================================================
# Platform-Specific Configuration
# ============================================================================
[cm4]
# Enable host mode on the 2711 built-in XHCI USB controller.
# This line should be removed if the legacy DWC2 controller is required
# (e.g. for USB device mode) or if USB support is not required.
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

# ============================================================================
# Common Configuration (all platforms)
# ============================================================================
[all]

# Waveshare CM4-POE-UPS-BASE peripherals
dtparam=i2c_vc=on
dtoverlay=i2c-rtc,pcf85063a,i2c_csi_dsi              # RTC clock
dtoverlay=i2c-fan,emc2301,i2c_csi_dsi,midtemp=45000,maxtemp=65000  # Fan control

# ============================================================================
# Dual Waveshare 2-CH CAN HAT+ Configuration
# ============================================================================
# NOTE: Interface names (can0-can3) are determined by hardware probe order,
#       NOT by the declaration order below. Use udev rules for persistent naming.
#
# Typical probe order (varies between boots):
#   Board 1: CAN_0 (spi1.1), CAN_1 (spi1.2)
#   Board 2: CAN_0 (spi0.0), CAN_1 (spi0.1)
#
# Physical mapping depends on which bus probes first - use udev rules!

# Board 1 configuration (SPI1)
dtoverlay=spi1-3cs
dtoverlay=mcp2515,spi1-1,oscillator=16000000,interrupt=22  # Board 1, CAN_0
dtoverlay=mcp2515,spi1-2,oscillator=16000000,interrupt=13  # Board 1, CAN_1

# Board 2 configuration (SPI0)
dtoverlay=spi0-2cs
dtoverlay=mcp2515,spi0-0,oscillator=16000000,interrupt=23  # Board 2, CAN_0
dtoverlay=mcp2515,spi0-1,oscillator=16000000,interrupt=25  # Board 2, CAN_1 (OBD-II)
```

### Key Configuration Notes

**I2S Disabled:** GPIO19 is shared between I2S (LRCLK) and SPI1 (MISO). Since we need SPI1 for the first CAN HAT, I2S must be disabled with `dtparam=i2s=off`.

**SPI Limitations:** SPI1 (auxiliary SPI) only has 3 chip selects (CE0, CE1, CE2). To support 4 CAN controllers, we must use both SPI0 and SPI1.

**Device Tree Order:** The order of mcp2515 overlays in config.txt does NOT control interface naming. Use udev rules for consistent names.

## Persistent CAN Interface Naming

### Problem
Kernel assigns `can0`, `can1`, `can2`, `can3` based on probe order, which can vary between boots causing OBD-II to move from `can2` to `can0` etc.

### Solution - Udev Rules

**Source template:** `config/can/80-can-persistent-names.rules`  
**Destination:** `/etc/udev/rules.d/80-can-persistent-names.rules`

```
# Persistent CAN interface naming for dual Waveshare 2-CH CAN HAT+ stack
#
# This ensures CAN interfaces always have consistent names regardless of
# kernel probe order, based on their physical SPI bus and chip select.
#
# Physical mapping:
#   can_b1_0 = Board 1 (bottom), CAN_0 connector (spi1.1, GPIO22 interrupt)
#   can_b1_1 = Board 1 (bottom), CAN_1 connector (spi1.2, GPIO13 interrupt)
#   can_b2_0 = Board 2 (top),    CAN_0 connector (spi0.0, GPIO23 interrupt)
#   can_b2_1 = Board 2 (top),    CAN_1 connector (spi0.1, GPIO25 interrupt) <- OBD-II

SUBSYSTEM=="net", KERNELS=="spi1.1", NAME="can_b1_0"
SUBSYSTEM=="net", KERNELS=="spi1.2", NAME="can_b1_1"
SUBSYSTEM=="net", KERNELS=="spi0.0", NAME="can_b2_0"
SUBSYSTEM=="net", KERNELS=="spi0.1", NAME="can_b2_1"
```

`install.sh` copies the template into `/etc/udev/rules.d/` and reloads udev for you. To apply it manually or on a different system:
```bash
sudo cp config/can/80-can-persistent-names.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger -s net
sudo reboot
```

**Usage:**
```bash
# OBD-II is always on can_b2_1
sudo ip link set can_b2_1 up type can bitrate 500000

# Bring up all interfaces
sudo ip link set can_b1_0 up type can bitrate 500000
sudo ip link set can_b1_1 up type can bitrate 500000
sudo ip link set can_b2_0 up type can bitrate 500000
sudo ip link set can_b2_1 up type can bitrate 500000
```

## I2C Device Configuration

### Bus Layout

**i2c-0** (via i2c-22 mux, channel 0):
- 0x51: PCF85063A RTC

**i2c-1** (main ARM I2C - all user devices):
- 0x30: Neokey 1x4
- 0x68: IMU (MPU6050/MPU9250/ICM20948)
- 0x70: TCA9548A I2C Multiplexer
  - Channel 0: MLX90640 (0x33), ADS1015 ADC (0x48)
  - Channels 1-7: Available for additional sensors

**i2c-10** (via i2c-22 mux, channel 1):
- 0x43: Unknown (carrier board hardware)

**i2c-22** (VC I2C - carrier board peripherals):
- Base bus for RTC/fan mux

**i2c-20, i2c-21** (phantom buses):
- Floating CSI/DSI camera I2C buses
- Created by camera_auto_detect=1 and display_auto_detect=1
- Respond to every address (0x08-0x6F)
- Safe to ignore

### I2C Address Conflicts with TCA9548A

**Important:** The TCA9548A multiplexer does NOT isolate the main bus. When a channel is selected, it electrically connects that channel TO the main i2c-1 bus.

**This means:**
- ✗ CANNOT use same address on main bus + any mux channel (conflict when channel active)
- ✓ CAN use same address on different mux channels (e.g., four MLX90640s at 0x33, one per channel)

**Best practice:**
- Unique-address devices (Neokey, IMU) → main i2c-1 bus
- Duplicate-address devices (multiple MLX90640s, VL53L1X) → behind mux on separate channels

### I2C Scanning Tool

Python script to scan i2c-1 and TCA9548A mux channels:

```python
#!/usr/bin/env python3
"""Scan i2c-1 and TCA9548A multiplexer channels for connected devices."""
# Uses i2cdetect and i2cset from i2c-tools package
# Run with: sudo python3 scan_i2c_devices.py
```

Install i2c-tools: `sudo apt install i2c-tools`

## Troubleshooting

### CAN Interfaces Not Appearing

**Check dmesg for errors:**
```bash
dmesg | grep -i mcp251
```

**Common errors:**

1. **"MCP251x didn't enter in conf mode after reset" (error -110)**
   - Board not powered/connected
   - Wrong SPI jumper configuration
   - Incorrect interrupt GPIO in device tree

2. **"pin gpio19 already requested by fe203000.i2s"**
   - I2S is claiming GPIO19 (SPI1 MISO)
   - Fix: Set `dtparam=i2s=off` in config.txt

3. **"spi spi0.0: chipselect 0 already in use"**
   - Conflicting device tree overlay
   - Check for duplicate spi0-2cs or other SPI overlays

### CAN Interface Names Change Between Boots

**Symptom:** OBD-II moves from can2 to can0 on reboot

**Cause:** Kernel probe order varies based on initialization timing (SPI0 vs SPI1 race)

**Solution:** Use udev rules (see Persistent CAN Interface Naming section above)

### I2C Devices Not Detected

**Verify bus exists:**
```bash
i2cdetect -l
```

**Scan specific bus:**
```bash
sudo i2cdetect -y 1  # Scan i2c-1
```

**Check device tree is loaded:**
```bash
ls /sys/bus/i2c/devices/
```

## Hardware Connections Summary

### CAN Connections
- **can_b1_0** (Board 1, CAN_0): Available
- **can_b1_1** (Board 1, CAN_1): Available
- **can_b2_0** (Board 2, CAN_0): Available
- **can_b2_1** (Board 2, CAN_1): **OBD-II connected here**

### I2C Connections (i2c-1)
**Direct on main bus:**
- Neokey 1x4 (0x30)
- IMU sensor (0x68)

**Behind TCA9548A mux (0x70):**
- Channel 0: MLX90640 thermal camera (0x33), ADS1015 ADC (0x48)
- Channels 1-7: Available for additional MLX90640, VL53L1X ToF sensors

## Application Notes

### Toyota/Lexus Radar Work
- Multiple CAN channels available for radar units
- Use can_b1_0, can_b1_1, can_b2_0 for radar research
- can_b2_1 reserved for OBD-II vehicle diagnostics

### Thermal Tire Analysis
- MLX90640 sensors on TCA9548A mux channels
- Multiple sensors possible (all at 0x33) on separate channels
- No address conflict since mux isolates channels

### OBD-II RPM Polling
Python script defaults to can_b2_1 (update from can2):
```bash
sudo python3 obd2_rpm_can2.py -i can_b2_1 --setup
```

## References

- [Waveshare 2-CH CAN HAT+ Wiki](https://www.waveshare.com/wiki/2-CH_CAN_HAT+)
- [Waveshare 2-CH CAN HAT+ Schematic](https://files.waveshare.com/wiki/2-CH-CAN-HAT%2B/2-CH_CAN_HAT%2B.pdf)
- [Waveshare CM4-POE-UPS-BASE Wiki](https://www.waveshare.com/wiki/CM4-POE-UPS-BASE)
- [Raspberry Pi Device Tree Documentation](https://www.raspberrypi.com/documentation/computers/configuration.html#device-trees-overlays-and-parameters)

## Lessons Learned

1. **I2S must be disabled** when using SPI1 on Raspberry Pi due to GPIO19 conflict
2. **SPI1 has only 3 chip selects** - need both SPI0 and SPI1 for 4 CAN controllers
3. **GPIO18 is SPI1 CE0, NOT SPI0 CE1** - critical jumper configuration detail
4. **CAN interface probe order is non-deterministic** - udev rules required for stable naming
5. **TCA9548A doesn't isolate main bus** - devices on i2c-1 appear in all mux channel scans
6. **Camera/display detection creates phantom I2C buses** - i2c-20/21 are floating and respond to all addresses
7. **Device tree overlay order doesn't control interface naming** - kernel assigns based on hardware probe timing

---

*Configuration completed: November 2025*  
*Hardware: Raspberry Pi CM4 on Waveshare CM4-POE-UPS-BASE*  
*OS: Raspberry Pi OS (Trixie)*
