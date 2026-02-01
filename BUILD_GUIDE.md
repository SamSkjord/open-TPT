# Build Guide - Main Controller

This guide covers the assembly and wiring of the main controller enclosure containing the Raspberry Pi 5 and associated hardware.

For corner sensor and laser ranger builds, see:
- [BUILD_PICO_TYRE.md](BUILD_PICO_TYRE.md) - Tyre temperature sensor nodes
- [BUILD_PICO_RANGER.md](BUILD_PICO_RANGER.md) - Laser distance sensor

For power system details, see [POWER_ARCHITECTURE.md](POWER_ARCHITECTURE.md).

---

## Bill of Materials

### Core Components

| Component | Quantity | Notes |
|-----------|----------|-------|
| Raspberry Pi 5 | 1 | 2GB+ RAM |
| Waveshare Dual CAN HAT | 2 | MCP2515-based, provides 4 CAN channels |
| 5V 10A buck converter | 1 | 12/24V input, powers Pi |
| 12V 3A buck converter | 1 | 8-40V input, powers sensor bus |

### I2C Devices (at monitor)

| Component | Address | Notes |
|-----------|---------|-------|
| NeoKey 1x4 | 0x30 | Physical buttons with NeoPixels |
| Seesaw Rotary Encoder | 0x36 | With NeoPixel feedback |
| OLED Bonnet 128x32 | 0x3C | SSD1305 display |
| MCP23017 GPIO Expander | 0x20 | OLED Bonnet buttons |
| NeoDriver | 0x60 | LED strip controller |

### I2C Devices (at Pi)

| Component | Address | Notes |
|-----------|---------|-------|
| ICM20649 IMU | 0x68 | G-meter (accelerometer/gyro) |

### Differential I2C

| Component | Quantity | Notes |
|-----------|----------|-------|
| SparkFun QwiicBus (PCA9615) | 2 | One at Pi, one at monitor |
| Cat5 cable | 1 | Length as required |

### Serial Devices

| Component | Notes |
|-----------|-------|
| PA1616S GPS module | 10Hz GNSS with PPS |
| TPMS receiver | Bluetooth to UART bridge |

### USB Devices

| Component | Notes |
|-----------|-------|
| USB camera (rear) | UVC compatible |
| USB camera (front) | UVC compatible |
| ANT+ USB dongle | Garmin ANT+ USB-m or compatible |

### Display

| Component | Notes |
|-----------|-------|
| Waveshare 1024x600 HDMI | 7" IPS display |

### Connectors

| Type | Quantity | Purpose |
|------|----------|---------|
| M8 4-pin male | As required | CAN bus outputs |
| M8 4-pin female | As required | CAN bus cables |
| OBD-II male | 1 | Vehicle power and OBD2 CAN |
| Cat5 jacks/plugs | As required | Differential I2C, radar |

---

## Wiring Overview

```
                                    ┌─────────────────────────────┐
                                    │         MONITOR             │
                                    │  ┌─────────┐ ┌───────────┐  │
                                    │  │ NeoKey  │ │  Encoder  │  │
                                    │  │  0x30   │ │   0x36    │  │
                                    │  └────┬────┘ └─────┬─────┘  │
                                    │       │           │         │
                                    │  ┌────┴───────────┴────┐    │
                                    │  │    I2C Bus (local)  │    │
                                    │  └──────────┬──────────┘    │
                                    │  ┌──────────┴──────────┐    │
                                    │  │  OLED    │ NeoDriver │    │
                                    │  │  0x3C    │   0x60    │    │
                                    │  │  0x20    │           │    │
                                    │  └──────────┬──────────┘    │
                                    │             │               │
                                    │      ┌──────┴──────┐        │
                                    │      │  PCA9615    │        │
                                    │      │  (QwiicBus) │        │
                                    │      └──────┬──────┘        │
                                    └─────────────┼───────────────┘
                                                  │
                                             Cat5 cable
                                        (differential I2C)
                                                  │
┌─────────────────────────────────────────────────┼───────────────────────────────────────┐
│                              MAIN ENCLOSURE     │                                       │
│                                                 │                                       │
│    ┌──────────────┐                     ┌───────┴───────┐              ┌─────────────┐  │
│    │  Pi 5        │◄── I2C Bus 1 ──────►│   PCA9615     │              │  ICM20649   │  │
│    │              │                     │   (QwiicBus)  │              │  IMU 0x68   │  │
│    │  GPIO 2/3    │                     └───────────────┘              └──────┬──────┘  │
│    │              │                                                           │         │
│    │              │◄──────────────────── I2C Bus 1 ──────────────────────────┘         │
│    │              │                                                                     │
│    │  SPI0/1      │◄───────────────────►┌───────────────────────────────────────┐      │
│    │  + IRQ pins  │                     │         Dual CAN HAT x2               │      │
│    │              │                     │  ┌─────────┐ ┌─────────┐              │      │
│    │              │                     │  │ Board 1 │ │ Board 2 │              │      │
│    │              │                     │  │ can_b1_0│ │ can_b2_0│ ──► Corner   │      │
│    │              │                     │  │ can_b1_1│ │ can_b2_1│     Sensors  │      │
│    │              │                     │  └────┬────┘ └────┬────┘     + Ranger │      │
│    │              │                     └───────┼───────────┼───────────────────┘      │
│    │              │                             │           │                          │
│    │  UART0       │◄── GPS (/dev/serial0)       │           │                          │
│    │  GPIO 14/15  │    + PPS (GPIO 18)          │           │                          │
│    │              │                             │           │                          │
│    │  UART2       │◄── TPMS (/dev/ttyAMA2)      │           │                          │
│    │  GPIO 4/5    │                             │           │                          │
│    │              │                             │           │                          │
│    │  USB         │◄── Cameras, ANT+ dongle     │           │                          │
│    │              │                             │           │                          │
│    │  HDMI        │◄── Display                  │           │                          │
│    └──────────────┘                             │           │                          │
│                                                 │           │                          │
│    ┌──────────────┐        ┌──────────────┐     │           │                          │
│    │ 5V Buck      │◄──┬───►│ 12V Buck     │     │           │                          │
│    │ (Pi power)   │   │    │ (sensor bus) │     │           │                          │
│    └──────────────┘   │    └──────┬───────┘     │           │                          │
│                       │           │             │           │                          │
│              Vehicle 12V          │             │           │                          │
│              (from OBD)           │             │           │                          │
│                                   │             │           │                          │
└───────────────────────────────────┼─────────────┼───────────┼──────────────────────────┘
                                    │             │           │
                              ┌─────┴─────┐   ┌───┴───┐   ┌───┴───┐
                              │ 12V Bus   │   │ Radar │   │ OBD2  │
                              │ (Cat5/M8) │   │ (Cat5)│   │ (OBD) │
                              └─────┬─────┘   └───────┘   └───────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
              │ Pico-Tyre │   │ Pico-Tyre │   │Pico-Ranger│
              │ (x4)      │   │           │   │           │
              └───────────┘   └───────────┘   └───────────┘
```

---

## GPIO Pin Allocation

### I2C (Bus 1)

| GPIO | Function |
|------|----------|
| 2 | I2C1 SDA |
| 3 | I2C1 SCL |

### UART

| GPIO | Function | Device |
|------|----------|--------|
| 4 | UART2 TX | TPMS receiver |
| 5 | UART2 RX | TPMS receiver |
| 14 | UART0 TX | GPS PA1616S |
| 15 | UART0 RX | GPS PA1616S |
| 18 | PPS input | GPS pulse-per-second |

### SPI/CAN (Board 1 - Radar)

| GPIO | Function |
|------|----------|
| 17 | SPI1 CE1 (can_b1_0) |
| 16 | SPI1 CE2 (can_b1_1) |
| 19 | SPI1 MISO |
| 20 | SPI1 MOSI |
| 21 | SPI1 SCLK |
| 22 | can_b1_0 IRQ |
| 13 | can_b1_1 IRQ |

### SPI/CAN (Board 2 - Sensors/OBD2)

| GPIO | Function |
|------|----------|
| 8 | SPI0 CE0 (can_b2_0) |
| 7 | SPI0 CE1 (can_b2_1) |
| 9 | SPI0 MISO |
| 10 | SPI0 MOSI |
| 11 | SPI0 SCLK |
| 23 | can_b2_0 IRQ |
| 25 | can_b2_1 IRQ |

### Available GPIO

| GPIO | Notes |
|------|-------|
| 6 | Free |
| 12 | Free (UART5 TX only) |
| 24 | Free |
| 26 | Free |
| 27 | Free |

---

## CAN Bus Channels

| Channel | Board | Purpose | Bitrate |
|---------|-------|---------|---------|
| can_b1_0 | 1, CAN_0 | Radar keep-alive (TX) | 500 kbps |
| can_b1_1 | 1, CAN_1 | Radar tracks (RX) | 500 kbps |
| can_b2_0 | 2, CAN_0 | Corner sensors + Laser ranger | 500 kbps |
| can_b2_1 | 2, CAN_1 | OBD2 vehicle data | 500 kbps |

---

## Differential I2C (QwiicBus)

The PCA9615 provides bidirectional differential I2C over twisted pair, enabling long cable runs to the monitor without signal degradation.

### Wiring (Cat5)

| Cat5 Pair | Wire Colours | Signal |
|-----------|--------------|--------|
| 1 | Orange/White-Orange | DSDA+/DSDA- |
| 2 | Green/White-Green | DSCL+/DSCL- |
| 3 | Blue/White-Blue | GND |
| 4 | Brown/White-Brown | VCC (3.3V or 5V) |

### Configuration

- **Pi side:** PCA9615 connected to I2C Bus 1 (GPIO 2/3)
- **Monitor side:** PCA9615 with all I2C devices daisy-chained via Qwiic/Stemma QT

The IMU (0x68) remains local to the Pi enclosure for vibration isolation.

---

## CAN Bus Connectors

### M8 4-Pin Pinout

| Pin | Signal | Notes |
|-----|--------|-------|
| 1 | +12V | From 12V buck |
| 2 | GND | Common ground |
| 3 | CAN-H | |
| 4 | CAN-L | |

### Bus Topology

```
                        Pi (can_b2_0)
                             │
                          Y-split
                         ╱       ╲
                     Front       Rear
                       │           │
                    X-split     X-split
                   ╱   │   ╲   ╱   │   ╲
                 FL    │    FR RL  │    RR
                       │           │
                    Ranger      120Ω
                    (120Ω     terminator
                   internal)
```

The X-splits at front and rear create a linear bus with FL, FR, RL, and RR as short stubs:
- **Front termination:** Internal to ranger enclosure
- **Rear termination:** Dedicated terminator plug

If the ranger is removed, replace with a terminator plug to maintain bus termination.

### Termination

120 ohm resistor between CAN-H and CAN-L at each end of the bus.

**Rear terminator construction (M8 plug):**

| Pin | Connection |
|-----|------------|
| 1 (+12V) | Not connected |
| 2 (GND) | Not connected |
| 3 (CAN-H) | ← 120Ω resistor → |
| 4 (CAN-L) | ← 120Ω resistor → |

Build as an M8 male connector with the resistor soldered across pins 3-4, then potted with epoxy or hot glue for weather resistance.

Keep a spare terminator plug available in case the ranger needs to be disconnected.

### Cable Options

| Type | Use Case |
|------|----------|
| Pre-made M8 cables | Production/reliability |
| Cat5 with M8 connectors | DIY/prototyping |

When using Cat5 for CAN:
- Use one twisted pair for CAN-H/CAN-L
- Use one twisted pair for +12V/GND
- Remaining pairs unused (or spare)

---

## Radar Connection

The Toyota radar module connects via Cat5 to the main enclosure.

### Cat5 Wiring

| Cat5 Pair | Signal | CAN Channel |
|-----------|--------|-------------|
| 1 | CAN-H/CAN-L (keep-alive) | can_b1_0 |
| 2 | CAN-H/CAN-L (tracks) | can_b1_1 |
| 3 | +12V/GND | Radar power |
| 4 | Spare | |

The radar requires its own 12V supply and uses two CAN channels:
- **can_b1_0:** Pi sends keep-alive messages to radar
- **can_b1_1:** Radar sends track data to Pi

---

## Serial Connections

### GPS (PA1616S)

| GPS Pin | Pi GPIO | Notes |
|---------|---------|-------|
| TX | 15 (RX) | 38400 baud |
| RX | 14 (TX) | |
| PPS | 18 | Pulse-per-second for chrony |
| VCC | 3.3V | |
| GND | GND | |

### TPMS Receiver

| TPMS Pin | Pi GPIO | Notes |
|----------|---------|-------|
| TX | 5 (RX) | 19200 baud |
| RX | 4 (TX) | |
| VCC | 5V | |
| GND | GND | |

Device path varies by Pi model:
- **Pi 5:** `/dev/ttyAMA2`
- **Pi 4:** `/dev/ttyAMA3`

---

## USB Connections

### Camera Assignment

Cameras are assigned to device paths via udev rules based on USB port.

| Camera | Device Path | USB Port |
|--------|-------------|----------|
| Rear | /dev/video-rear | USB 1.1 |
| Front | /dev/video-front | USB 1.2 |

See `services/udev/99-camera-names.rules` for the udev configuration.

### ANT+ Dongle

The ANT+ USB dongle can use any available USB port. Install the udev rules from `services/udev/99-ant-usb.rules` for non-root access.

---

## Power Connections

See [POWER_ARCHITECTURE.md](POWER_ARCHITECTURE.md) for detailed power distribution documentation.

### Summary

| Source | Converter | Output | Load |
|--------|-----------|--------|------|
| Vehicle 12V | 5V 10A buck | 5V | Pi 5 |
| Vehicle 12V | 12V 3A buck | 12V | Sensor bus (Cat5/M8) |

### Input Protection

At OBD-II connector:
- TVS diode (1.5KE33A)
- 2A inline fuse
- 3300uF bulk capacitor

---

## Assembly Notes

### HAT Stacking

The two Waveshare Dual CAN HATs stack on the Pi GPIO header. Ensure:
- Standoffs between boards for mechanical support
- Good contact on all GPIO pins
- Adequate ventilation

### I2C Bus Speed

The I2C bus runs at 400kHz (Fast Mode) for EMI resilience in the motorsport environment. This is configured in `/boot/config.txt`:

```
dtparam=i2c_arm=on,i2c_arm_baudrate=400000
```

### CAN Bus Setup

CAN interfaces are configured via device tree overlays. See `services/boot/config.txt` for the required overlay configuration.

Verify CAN is working:
```bash
candump can_b2_0    # Should show corner sensor messages
```

### Testing I2C

Scan for I2C devices:
```bash
sudo i2cdetect -y 1
```

Expected addresses with all devices connected:
- 0x20 (MCP23017)
- 0x30 (NeoKey)
- 0x36 (Encoder)
- 0x3C (OLED)
- 0x60 (NeoDriver)
- 0x68 (IMU)
