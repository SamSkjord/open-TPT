# Power & Protection Architecture

## Overview

The system is powered from the vehicle via the OBD-II port and consists of two primary branches:

1. **Main controller branch**
   Vehicle 12-13 V → 5 V buck → Raspberry Pi 5

2. **Distributed sensor branch**
   Vehicle 12-13 V → 12 V buck ("clean bus") → Cat5 → remote Pico sensor nodes

All branches share a single protected vehicle entry point with transient suppression and fusing.

Peak measured system draw is approximately 15 W @ 13 V (~1.15 A).

---

## 1. Vehicle Entry & Front-End Protection (OBD-II)

### Electrical protection

- **TVS diode:** 1.5KE33A
  - Mounted inside the OBD connector
  - Clamps automotive transients and spike events
- **Inline fuse:** 2 A (3 A acceptable if nuisance blowing occurs)
  - Located in harness after OBD plug
  - Protects downstream wiring and electronics
- **Vehicle fuse:** existing OBD circuit fuse provides upstream protection

### Bulk energy storage

- **3300 uF, 35 V electrolytic**
  - Located immediately after the fuse at the system split point
  - Absorbs slow transients and aggregate load steps

### Future considerations

- **Reverse polarity protection:** TVS does not protect against sustained reverse voltage from miswiring. A series Schottky diode or P-FET circuit at the vehicle entry would provide this protection.
- **Inrush limiting:** The 3300 uF bulk capacitor plus two buck converter input stages will draw significant inrush current on connection. An NTC thermistor in series would limit this if nuisance fuse blows occur.

### Result

A protected vehicle 12 V node suitable for feeding multiple converters.

---

## 2. Power Split (Star Topology)

After the inline fuse and bulk capacitor, the supply is split into two independent branches:

```
OBD → TVS → Fuse → 12V Protected Node
                        ├─ Branch A: 5V buck → Pi 5
                        └─ Branch B: 12V buck → Cat5 sensor bus
```

This prevents load steps on the Pi 5 from modulating the distributed sensor supply.

---

## 3. Branch A - Main Controller (Pi 5)

### Supply path

Vehicle 12-13 V → 5 V buck converter → Raspberry Pi 5

### Converter

- **5 V 10 A buck converter**
  - Input: 12/24 V nominal (tested 7-25 V)
  - Output: 5 V regulated, 10 A capacity
  - Provides ample headroom for Pi 5 plus peripherals

### Local conditioning

- **At buck input:**
  - 1 uF + 0.1 uF ceramics (>=25 V)
- **At buck output / Pi input:**
  - Ensure adequate output bulk (typically >=470 uF low-ESR)
  - Additional 1 uF + 0.1 uF near Pi 5 power entry

### Protection

- **Buck converter internal:**
  - Over-current protection
  - Thermal shutdown
- Upstream fuse and TVS protect against vehicle faults

---

## 4. Branch B - Distributed 12 V Sensor Bus

### Supply path

Vehicle 12-13 V → 12 V buck converter → Cat5 distribution

### Converter

- **12 V 3 A buck converter**
  - Input: 8-40 V (wide input range handles vehicle voltage variation)
  - Output: 12 V regulated, 3 A capacity
  - Maintains stable bus voltage even during cranking dips

### Output conditioning (at 12 V buck)

- 1 uF + 0.1 uF ceramics
- Optional 470-1000 uF electrolytic if many nodes switch simultaneously

---

## 5. Distribution Cabling (Cat5)

### From enclosure to nodes

- **Length:** ~2 m
- **Power:**
  - One twisted pair for +12 V
  - One twisted pair for GND
- **CAN:**
  - Dedicated twisted pair (CAN-H / CAN-L)

At ~1.15 A total load, voltage drop over 2 m is ~0.4 V, which is well within margin.

### Ground topology

All grounds reference the vehicle chassis/battery negative via the single protected entry point. The star topology at the enclosure (each node has its own Cat5 back to the central point) ensures a clean common ground with no daisy-chain ground shift between nodes.

---

## 6. Remote Node Power Entry

At each node, before regulation:

### Local decoupling (mandatory)

- 470 uF electrolytic (25-35 V)
- 1 uF ceramic
- 0.1 uF ceramic

**Purpose:**
- Localise switching currents
- Prevent cable inductance effects
- Reduce noise injection into CAN

No series resistor is fitted; this is acceptable due to low current and use of high-quality regulators.

---

## 7. Remote Node Regulation

### Regulator

- **Pololu D45V5F5**
  - 12 V → 5 V synchronous buck
  - Wide input tolerance
  - Built-in OCP, SCP, thermal protection

### Loads

- 5 V → Raspberry Pi Pico (via USB)
- Pico onboard 3.3 V regulator powers:
  - MLX90640
  - Thermocouple amplifiers

### Local load decoupling

- 0.1 uF + 1 uF at each 3.3 V device

---

## 8. Fault & Noise Behaviour

| Scenario | Mitigation |
|----------|------------|
| Vehicle transient | Clamped at OBD by TVS |
| Short at node | Handled locally by Pololu regulator |
| Node failure | Does not collapse main bus |
| CAN integrity | Protected by power localisation and twisted-pair routing |

---

## 9. Design Envelope (Validated)

| Parameter | Value |
|-----------|-------|
| Input voltage | 12-14.5 V nominal |
| Peak power | ~15 W |
| Peak current | ~1.15 A @ 13 V |
| Cat5 length | ~2 m |
| Power pairs | 1 out + 1 back |
| Nodes | Pico-based sensor modules |

---

## Summary

The system uses a single transient-protected vehicle entry feeding independent 5 V and 12 V conversion branches, with local energy storage and high-quality regulators ensuring stable, low-noise operation of a Pi-controlled distributed sensor network.
