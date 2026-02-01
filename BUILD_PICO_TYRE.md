# Build Guide - Pico-Tyre Corner Sensor

This guide covers the assembly and wiring of the Pico-Tyre corner sensor nodes. Each corner of the vehicle has one sensor node providing tyre temperatures and brake temperatures via CAN bus.

For main controller build, see [BUILD_GUIDE.md](BUILD_GUIDE.md).
For power system details, see [POWER_ARCHITECTURE.md](POWER_ARCHITECTURE.md).

---

## Overview

Each Pico-Tyre node consists of:
- RP2040 microcontroller with CAN transceiver
- MLX90640 thermal camera (24x32 pixels) for tyre surface temperatures
- Thermocouple amplifier(s) for brake disc temperatures
- 12V to 5V regulation
- CAN bus interface

The four nodes broadcast data on CAN bus `can_b2_0` at 500 kbps using message IDs specific to each corner.

---

## Bill of Materials (per node)

### Core Components

| Component | Quantity | Notes |
|-----------|----------|-------|
| Adafruit RP2040 CAN Bus Feather | 1 | RP2040 + MCP2515 CAN controller |
| MLX90640 thermal camera | 1 | 24x32 pixels, 55 or 110 degree FOV |
| Pololu D45V5F5 | 1 | 12V to 5V synchronous buck, 5A |
| K-type thermocouple amplifier | 2 | MAX31855 or similar, inner/outer brake |
| K-type thermocouples | 2 | High-temperature rated for brake use |

### Connectors and Passive Components

| Component | Quantity | Notes |
|-----------|----------|-------|
| M8 4-pin panel connector | 1 | Power + CAN input |
| Qwiic/Stemma QT cable | 1 | MLX90640 connection |
| 470uF 25V electrolytic | 1 | Input bulk capacitor |
| 1uF ceramic | 2 | Input/output decoupling |
| 0.1uF ceramic | 3 | Device decoupling |
| 120 ohm resistor | 0-1 | CAN termination (bus ends only) |

### Enclosure

| Component | Notes |
|-----------|-------|
| Weatherproof enclosure | IP65+ rated |
| Cable glands | For M8 and sensor cables |
| Mounting hardware | Bracket for wheel arch mounting |

---

## Wiring Diagram

```
                                    M8 4-Pin Input
                                         │
                            ┌────────────┴────────────┐
                            │  1: +12V    2: GND      │
                            │  3: CAN-H   4: CAN-L    │
                            └────────────┬────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
               +12V │                   GND              CAN-H/L
                    │                    │                    │
              ┌─────┴─────┐              │                    │
              │  470uF    │              │                    │
              │  + 1uF    │              │                    │
              │  + 0.1uF  │              │                    │
              └─────┬─────┘              │                    │
                    │                    │                    │
              ┌─────┴─────┐              │                    │
              │  Pololu   │              │                    │
              │  D45V5F5  │              │                    │
              │  12V→5V   │              │                    │
              └─────┬─────┘              │                    │
                    │                    │                    │
                   5V                   GND                   │
                    │                    │                    │
    ┌───────────────┼────────────────────┼────────────────────┤
    │               │                    │                    │
    │         ┌─────┴────────────────────┴─────┐              │
    │         │                                │              │
    │         │      RP2040 CAN Feather        │              │
    │         │                                │              │
    │         │  USB ─── (programming only)    │              │
    │         │                                │              │
    │         │  I2C ─────────────────────┐    │              │
    │         │  (SDA/SCL)                │    │              │
    │         │                           │    │              │
    │         │  SPI ─────────────────┐   │    │              │
    │         │  (SCK/MOSI/MISO)      │   │    │              │
    │         │                       │   │    │              │
    │         │  CS0 ────────────┐    │   │    │              │
    │         │  CS1 ───────┐    │    │   │    │              │
    │         │             │    │    │   │    │              │
    │         │  CAN ───────┼────┼────┼───┼────┼──────────────┘
    │         │             │    │    │   │    │
    │         └─────────────┼────┼────┼───┼────┘
    │                       │    │    │   │
    │                 ┌─────┘    │    │   │
    │                 │          │    │   │
    │           ┌─────┴─────┐    │    │   │
    │           │ MAX31855  │    │    │   │
    │           │ (Inner)   │    │    │   │
    │           └─────┬─────┘    │    │   │
    │                 │          │    │   │
    │            Thermocouple    │    │   │
    │            (inner brake)   │    │   │
    │                            │    │   │
    │                      ┌─────┘    │   │
    │                      │          │   │
    │                ┌─────┴─────┐    │   │
    │                │ MAX31855  │    │   │
    │                │ (Outer)   │    │   │
    │                └─────┬─────┘    │   │
    │                      │          │   │
    │                 Thermocouple    │   │
    │                 (outer brake)   │   │
    │                                 │   │
    │                           ┌─────┘   │
    │                           │         │
    │                     ┌─────┴─────┐   │
    │                     │ MLX90640  │   │
    │                     │ Thermal   │───┘
    │                     │ Camera    │
    │                     └───────────┘
    │                           │
    │                      (aimed at
    │                       tyre surface)
    │
    └──► 5V to all devices (0.1uF at each)
```

---

## Pin Assignments

### RP2040 CAN Feather

| Pin | Function | Connection |
|-----|----------|------------|
| 3V3 | 3.3V output | MLX90640 VCC |
| GND | Ground | All devices |
| USB | 5V input | From Pololu regulator |
| SDA | I2C data | MLX90640 |
| SCL | I2C clock | MLX90640 |
| SCK | SPI clock | Thermocouple amplifiers |
| MOSI | SPI data out | (unused by MAX31855) |
| MISO | SPI data in | Thermocouple amplifiers |
| D4 | Chip select 0 | Inner thermocouple |
| D5 | Chip select 1 | Outer thermocouple |
| CAN-H | CAN high | M8 connector pin 3 |
| CAN-L | CAN low | M8 connector pin 4 |

---

## CAN Protocol

### Message IDs

Each corner uses a unique set of message IDs:

| Corner | TyreTemps | Detection | BrakeTemps | Status | FrameData |
|--------|-----------|-----------|------------|--------|-----------|
| FL | 0x100 | 0x101 | 0x102 | 0x110 | 0x11C |
| FR | 0x120 | 0x121 | 0x122 | 0x130 | 0x13C |
| RL | 0x140 | 0x141 | 0x142 | 0x150 | 0x15C |
| RR | 0x160 | 0x161 | 0x162 | 0x170 | 0x17C |

### Message Contents

**TyreTemps (10 Hz)**
- Left/Centre/Right median temperatures
- Lateral gradient
- Format: int16, 0.1 degC resolution

**TyreDetection (10 Hz)**
- Tyre detected flag
- Warning flags
- Confidence level
- Tyre width estimate

**BrakeTemps (10 Hz)**
- Inner zone temperature
- Outer zone temperature
- Status: 0=OK, 1=Disconnected, 2=Error, 3=NotFound

**Status (1 Hz)**
- Frame rate (FPS)
- Firmware version
- Wheel ID
- Emissivity setting

**FrameData (on request)**
- Full 768-pixel thermal frame
- 256 segments x 3 pixels
- Requested via command ID 0x7F3

### DBC File

The CAN protocol is defined in `opendbc/pico_tyre_temp.dbc`.

---

## CAN Bus Termination

The CAN bus requires 120 ohm termination at each end.

**Bus topology:**

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

**Termination placement:**
- **Front:** Internal to ranger (see [BUILD_PICO_RANGER.md](BUILD_PICO_RANGER.md))
- **Rear:** Dedicated terminator plug off X-split
- **No termination inside corner sensor enclosures** - all are stubs off junctions

Any corner sensor can be disconnected without affecting bus termination. See [BUILD_GUIDE.md](BUILD_GUIDE.md) for terminator construction details.

---

## Thermal Camera Mounting

### Field of View

The MLX90640 is available in two FOV options:
- **55 degree:** Higher resolution, closer mounting
- **110 degree:** Wider view, more flexible mounting

### Mounting Position

The camera should be positioned to view the full tyre width with some margin:
- Typical mounting: inner wheel arch
- Distance: 100-300mm from tyre surface
- Angle: perpendicular to tyre surface

### Emissivity

Tyre rubber emissivity is approximately 0.95. This is configured in the sensor firmware.

---

## Thermocouple Installation

### Placement

- **Inner:** Aimed at inner portion of brake disc
- **Outer:** Aimed at outer portion of brake disc

For non-contact measurement, position thermocouples to measure:
- Radiated heat from disc surface, or
- Caliper body temperature as a proxy

### Wiring

K-type thermocouple polarity matters:
- Yellow wire: positive
- Red wire: negative (counterintuitive)

Use thermocouple extension wire (not standard copper) for long runs.

---

## Power Entry

### Input Decoupling

At the M8 connector, before the Pololu regulator:
- 470uF electrolytic (25V minimum)
- 1uF ceramic
- 0.1uF ceramic

This localises switching currents and prevents noise injection into the CAN bus.

### Regulator

The Pololu D45V5F5 provides:
- Input: 4.5-42V (handles 12V bus with margin)
- Output: 5V regulated, up to 5A
- Built-in overcurrent, short-circuit, and thermal protection

### Device Power

- RP2040 Feather: 5V via USB connection or VBUS pin
- MLX90640: 3.3V from Feather's onboard regulator
- Thermocouple amplifiers: 3.3V from Feather's onboard regulator

Add 0.1uF ceramic at VCC of each device for local decoupling.

---

## Firmware

The Pico-Tyre firmware is maintained in a separate repository.

### Configuration

Each sensor must be configured with its wheel position:
- 0: Front Left (FL)
- 1: Front Right (FR)
- 2: Rear Left (RL)
- 3: Rear Right (RR)

This determines the CAN message IDs used by that sensor.

### Programming

Connect via USB for initial programming. The USB connection is also used for firmware updates and debugging.

---

## Enclosure

### Requirements

- IP65 or better for wheel arch environment
- Withstand road spray, mud, heat from brakes
- Vibration resistant mounting

### Thermal Considerations

The enclosure must allow:
- Clear view for thermal camera (window or opening)
- Thermocouple cables to exit for brake measurement
- Heat dissipation from electronics

### Cable Entry

- M8 panel connector for power + CAN
- Glands for thermocouple cables
- Consider strain relief for all connections

---

## Testing

### Bench Testing

1. **Power check:** Verify 5V output from Pololu with 12V input
2. **CAN check:** Connect to main controller, run `candump can_b2_0`
3. **I2C check:** Verify MLX90640 responds (address 0x33)
4. **SPI check:** Verify thermocouple readings

### Vehicle Testing

1. **Message verification:** All message types appearing at expected rates
2. **Temperature sanity:** Readings reasonable for ambient conditions
3. **Detection:** Tyre detection working with wheel in view
4. **Brake temps:** Responding to brake heat cycles

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| No CAN messages | Power, CAN wiring, termination |
| Erratic temperatures | Decoupling capacitors, EMI shielding |
| Tyre not detected | Camera alignment, FOV, emissivity setting |
| Brake temps stuck | Thermocouple polarity, connection, amplifier |
| Intermittent operation | Vibration, loose connections, power brownout |
