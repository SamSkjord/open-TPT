# Build Guide - Pico-Ranger Laser Distance Sensor

This guide covers the assembly and wiring of the Pico-Ranger laser distance sensor. The sensor provides forward distance measurement displayed as an overlay on the front camera view.

For main controller build, see [BUILD_GUIDE.md](BUILD_GUIDE.md).
For power system details, see [POWER_ARCHITECTURE.md](POWER_ARCHITECTURE.md).

---

## Overview

The Pico-Ranger consists of:
- RP2040 microcontroller with CAN transceiver
- Time-of-flight (TOF) laser distance sensor
- 12V to 5V regulation
- CAN bus interface

The sensor broadcasts distance data on CAN bus `can_b2_0` at 500 kbps, sharing the bus with the corner sensors.

---

## Bill of Materials

### Core Components

| Component | Quantity | Notes |
|-----------|----------|-------|
| Adafruit RP2040 CAN Bus Feather | 1 | RP2040 + MCP2515 CAN controller |
| VL53L1X TOF sensor | 1 | Up to 4m range, I2C interface |
| Pololu D45V5F5 | 1 | 12V to 5V synchronous buck, 5A |

### Connectors and Passive Components

| Component | Quantity | Notes |
|-----------|----------|-------|
| M8 4-pin panel connector | 1 | Power + CAN input |
| Qwiic/Stemma QT cable | 1 | TOF sensor connection |
| 470uF 25V electrolytic | 1 | Input bulk capacitor |
| 1uF ceramic | 2 | Input/output decoupling |
| 0.1uF ceramic | 2 | Device decoupling |
| 120Ω resistor | 1 | CAN bus termination |

### Enclosure

| Component | Notes |
|-----------|-------|
| Weatherproof enclosure | IP65+ rated, small form factor |
| Cable gland | For M8 connector |
| Clear window | For laser aperture |
| Mounting hardware | Front-facing mount |

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
            │         ┌──────────┴──────────┐         │
            │         │                     │         │
            │         │  RP2040 CAN Feather │         │
            │         │                     │         │
            └────────►│  USB (5V in)        │         │
                      │                     │         │
                      │  I2C ──────────┐    │         │
                      │  (SDA/SCL)     │    │         │
                      │                │    │         │
                      │  CAN ──────────┼────┼─────────┘
                      │      120Ω     │    │
                      │   terminator  │    │
                      └────────────────┼────┘
                                       │
                                 ┌─────┴─────┐
                                 │  VL53L1X  │
                                 │   TOF     │
                                 │  Sensor   │
                                 └─────┬─────┘
                                       │
                                  (laser beam
                                   forward)
```

---

## Pin Assignments

### RP2040 CAN Feather

| Pin | Function | Connection |
|-----|----------|------------|
| 3V3 | 3.3V output | VL53L1X VCC |
| GND | Ground | All devices |
| USB | 5V input | From Pololu regulator |
| SDA | I2C data | VL53L1X |
| SCL | I2C clock | VL53L1X |
| CAN-H | CAN high | M8 connector pin 3 |
| CAN-L | CAN low | M8 connector pin 4 |

### CAN Termination

Install a 120Ω resistor between CAN-H and CAN-L inside the enclosure. This can be soldered directly across the CAN-H and CAN-L pads on the RP2040 CAN Feather, or at the M8 connector terminals.

---

## CAN Protocol

### Message IDs (Sensor ID 0)

| ID | Name | Rate | Purpose |
|----|------|------|---------|
| 0x200 | RangeData | ~4 Hz | Distance, status, error code |
| 0x210 | Status | 1 Hz | Measurement rate, firmware, sensor ID |

### Message Contents

**RangeData (0x200)**
- Distance: uint16, millimetres
- Status: 0=OK, 1=Error
- Error code: sensor-specific
- Measurement count: rolling counter

**Status (0x210)**
- Measurement rate: Hz x 10
- Firmware version
- Sensor ID
- Total measurements: uint32

### DBC File

The CAN protocol is defined in `opendbc/pico_can_ranger.dbc`.

---

## CAN Bus Termination

The Pico-Ranger connects to the same CAN bus as the corner sensors (can_b2_0).

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

**Termination:** The ranger provides front bus termination with an **internal 120Ω resistor** between CAN-H and CAN-L.

If the ranger is removed for maintenance, replace with a terminator plug on the front X-split to maintain bus termination. See [BUILD_GUIDE.md](BUILD_GUIDE.md) for terminator construction details.

---

## Sensor Mounting

### Position

Mount the sensor at the front of the vehicle, facing forward:
- Clear line of sight ahead
- Protected from road spray
- Accessible for cleaning

### Offset Configuration

The sensor measures from its mounting position, not the front of the vehicle. Configure the offset in openTPT settings:

**Menu:** Front Camera > Laser Ranger > Mount Offset

Set this to the distance from the sensor to the frontmost point of the vehicle.

### Laser Safety

The VL53L1X is a Class 1 laser device (eye-safe). No special precautions required for normal use.

---

## Display Behaviour

The distance reading appears as an overlay on the front camera view:

| Distance | Colour |
|----------|--------|
| > 15m | Green |
| 5-15m | Yellow |
| < 5m | Red |
| > 50m or error | Hidden |

### Display Settings

Configurable via menu (Front Camera > Laser Ranger):

| Setting | Options | Default |
|---------|---------|---------|
| Display enabled | On/Off | On |
| Position | Top/Bottom | Bottom |
| Text size | Small/Medium/Large | Medium |
| Mount offset | 0.0-5.0m | 0.0m |

---

## Power Entry

### Input Decoupling

At the M8 connector, before the Pololu regulator:
- 470uF electrolytic (25V minimum)
- 1uF ceramic
- 0.1uF ceramic

### Regulator

The Pololu D45V5F5 provides:
- Input: 4.5-42V (handles 12V bus with margin)
- Output: 5V regulated, up to 5A
- Built-in overcurrent, short-circuit, and thermal protection

### Device Power

- RP2040 Feather: 5V via USB connection or VBUS pin
- VL53L1X: 3.3V from Feather's onboard regulator

Add 0.1uF ceramic at VCC of the TOF sensor for local decoupling.

---

## Firmware

The Pico-Ranger firmware is maintained in a separate repository.

### Configuration

The sensor ID is configured in firmware (default: 0). Multiple rangers would use different IDs with offset message IDs.

### Programming

Connect via USB for initial programming. The USB connection is also used for firmware updates and debugging.

---

## Enclosure

### Requirements

- IP65 or better for front-of-vehicle environment
- Clear window for laser (glass or polycarbonate)
- Compact form factor
- Vibration resistant mounting

### Laser Window

The TOF sensor requires a clear aperture:
- Clean, scratch-free surface
- Perpendicular to sensor
- No condensation (consider ventilation or sealed with desiccant)

### Cable Entry

- M8 panel connector for power + CAN
- Consider strain relief

---

## Testing

### Bench Testing

1. **Power check:** Verify 5V output from Pololu with 12V input
2. **CAN check:** Connect to main controller, run `candump can_b2_0`
3. **I2C check:** Verify VL53L1X responds (address 0x29)
4. **Range check:** Verify distance readings to known targets

### Vehicle Testing

1. **Message verification:** RangeData at ~4 Hz, Status at 1 Hz
2. **Range accuracy:** Compare to measured distances
3. **Offset calibration:** Verify mount offset is correct
4. **Display:** Overlay appearing correctly on front camera

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| No CAN messages | Power, CAN wiring, bus connection |
| Distance reads 0 | Sensor blocked, window dirty, I2C issue |
| Erratic readings | Reflective surfaces, window condensation |
| Always shows error | Sensor fault, I2C communication |
| Overlay not showing | Display disabled in settings, distance > 50m |

### Debug Commands

```bash
# Check for CAN messages
candump can_b2_0 | grep -E "200|210"

# Check openTPT logs
sudo journalctl -u openTPT.service -f | grep -i ranger
```
