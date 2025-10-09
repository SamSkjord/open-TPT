# open-TPT System Design and Project Plan
**Full Revision: Multi-CAN, Modular Radar with CAN-Env Simulator, OBD/Fuel, Tyre Zones, HUD, SOC**

---

## 1. Objective
Raspberry Pi-based motorsport HUD/logger that:
- Reads and displays tyres, brakes, laps, radar, OBD, hybrid SOC
- Logs all channels with timestamps and config/version metadata
- Runs on mixed CAN topologies (HS/MS/OBD/radar) with swappable radar drivers
- Survives real-world conditions and never blocks the render loop

---

## 2. Hardware

| Subsystem | Baseline |
|---|---|
| Compute | Raspberry Pi 4 / 5 (4–8 GB) |
| Display | Sunlight-readable TFT (e.g., HyperPixel), KMS/DRM |
| Power | OBD pin 16 → DC-DC 12→5 V; return to pin 4; single-point tie to pin 5 |
| Storage | 64–128 GB microSD; read-only root; `/data` writable |
| I/O Buses | SPI, I²C, USB, GPIO |
| CAN | Waveshare Dual-CAN HAT+ (MCP2517FD) × 1–N; CANable 2.0 USB |
| Sensors | MLX90640 (tyre), IR brake (I²C/ADC), GPS ≥ 10 Hz (USB/UART), rear camera (USB UVC), radar (Tesla/Bosch/Denso) |
| Inputs | NeoKey 1×4 (I²C seesaw + NeoPixel) |

### OBD-II Connector Pins
| Pin | Function | Notes |
|---|---|---|
| 16 | +12 V | Power in → regulator |
| 4 | Chassis GND | Power return |
| 5 | Signal GND | Logic reference only |
| 6 / 14 | HS-CAN | 500 kbit/s |
| 3 / 11 | MS-CAN | 125 kbit/s |

**Grounding:** use pin 4 for power return; pin 5 as logic reference; tie 4↔5 once on your board (star point).

---

## 3. Software Architecture
- **Language:** Python 3.11+
- **Concurrency:** threads + bounded queues; no blocking in render path
- **Graphics:** SDL2/pygame on KMS/DRM (30–60 FPS)
- **CAN:** SocketCAN; ISO-TP for OBD/UDS; multi-bus scheduler
- **Optimisation:** NumPy; optional Numba JIT for thermal edge math
- **Config:** YAML with schema validation; environment overrides
- **Services:** systemd per module; restart on stall; journald logging
- **FS Layout:** overlayfs read-only root; `/data` for sessions
- **Logging:** binary records + CSV/Parquet exporters; include git commit + config hash

---

## 4. Repository Layout
```text
openTPT/
  drivers/
    tpms.py
    brake_ir.py
    mlx90640.py
    gps.py
    camera.py
    can_bus.py
    obd/
      isotp.py
      pid_table.py
      api.py
    hybrid/
      soc_reader.py
  radar/
    core/
      api.py
      scheduler.py
      sim.py
      dbc.py
      utils.py
    drivers/
      bosch_tesla/
        driver.py
        frames.py
        sim_profile.yaml
        tests/
      denso_genX/
        driver.py
        frames.py
        sim_profile.yaml
        tests/
      continental_ars4xx/
        driver.py (placeholder)
  perception/
    tyre_zones.py
    radar_tracker.py
    fuel_usage.py
    soc_smoothing.py
    shiftlights.py
    radar_alerts.py
  laptimer/
    gates.py
    state.py
    delta.py
  ui/
    screens/
    overlays/
      delta_bar.py
      radar_overlay.py
      tyre_overlay.py
      fuel_widget.py
      soc_bar.py
  logging/
    recorder.py
    export.py
  tools/
    gates_editor.py
    radar_calib.py
    thermal_tester.py
    replay.py
  config/
    default.yaml
  docs/
```

---

## 5. Multi-CAN Architecture

### 5.1 Bus Roles and Naming
| Interface | Device | Role | Bitrate (kbps) |
|---|---|---|---|
| `can0` | Waveshare HAT+ #1 ch A | Radar | 500 |
| `can1` | Waveshare HAT+ #1 ch B | Spare/expansion | 500 |
| `obd0` | CANable 2.0 USB | OBD / ISO-TP | 500 |
| `can2` | Waveshare HAT+ #2 ch A | HS-CAN | 500 |
| `can3` | Waveshare HAT+ #2 ch B | MS-CAN | 125 |
| `can4+` | Extra HATs | Additional buses | profile-defined |

- Unique chip-selects and IRQ GPIOs per MCP2517FD.
- udev rules for persistent names; systemd templated bring-up sets bitrate and brings interfaces up.

### 5.2 Example Bring-up
```bash
systemctl enable --now can@can0.service 500000
systemctl enable --now can@can1.service 500000
systemctl enable --now can@can2.service 500000
systemctl enable --now can@can3.service 125000
systemctl enable --now can@obd0.service 500000
```

### 5.3 Config Snippet
```yaml
buses:
  can0: {bitrate: 500000, role: radar}
  can1: {bitrate: 500000, role: spare}
  can2: {bitrate: 500000, role: hs}
  can3: {bitrate: 125000, role: ms}
  obd0: {bitrate: 500000, role: obd}

vehicle:
  name: "Ford Puma MHEV"
  profile: "ford_ms_hs"
  allow_fd: false
```

### 5.4 Per-Signal Routing
```yaml
signals:
  rpm:        {source: obd,        bus: "obd0", mode: 0x01, pid: 0x0C, hz: 20}
  speed:      {source: obd,        bus: "obd0", mode: 0x01, pid: 0x0D, hz: 10}
  lambda_eq:  {source: obd,        bus: "can3", mode: 0x01, pid: 0x34, hz: 5}
  soc_pct:    {source: can_native, bus: "can3", id: 0x3A1, start: 16, len: 8, scale: 0.5, hz: 5}
  radar_objs: {source: radar,      bus: "can0", hz: 25}
```

### 5.5 Scheduler
- One thread per active bus; independent rate limiting
- Coalesce OBD PIDs per bus; ISO-TP sessions per interface
- Priority order per bus: radar > OBD > nice-to-have
- Enlarge socket buffers (`rmem_max`) and `txqueuelen`

---

## 6. Radar: Modular Plugins + CAN-Environment Simulator

### 6.1 Unified Radar API
```python
from dataclasses import dataclass
from typing import Protocol, List, Dict

@dataclass(frozen=True)
class RadarObject:
  obj_id:int; time:float; range_m:float; range_rate_mps:float
  azimuth_deg:float; lateral_vel_mps:float; prob_exist:float

@dataclass(frozen=True)
class RadarStatus:
  time:float; mode:str  # "OK"|"DEGRADED"|"BLOCKED"|"NO_DATA"
  objects_tracked:int; firmware:str|None=None; diag:int=0

class RadarDriver(Protocol):
  def required_buses(self) -> List[str]: ...
  def bringup(self, busmap: Dict[str, str]) -> None: ...
  def start(self) -> None: ...
  def stop(self) -> None: ...
  def get_status(self) -> RadarStatus: ...
  def get_objects(self, max_age_ms:int=300) -> List[RadarObject]: ...
```

### 6.2 CAN-Environment Simulator (Profiles)
```yaml
# radar/core/sim.py profile schema example
buses:
  veh:   {iface: "can2", bitrate: 500000}
  radar: {iface: "can0", bitrate: 500000}
frames:
  - id: 0x120            # ego speed
    bus: veh
    rate_hz: 50
    payload: "00 00 00 00 00 00 00 00"
    encode:
      - {at: 0, len: 16, type: u16_be, expr: "int(veh_speed_kph/0.1)"}
      - {at: 7, len: 8,  type: u8,     expr: "crc8(poly=0x1D, bytes[:7])"}
    sources:
      veh_speed_kph: {type: ramp, start: 0, end: 120, period_s: 20}
  - id: 0x220            # steering angle, with counter/CRC (omitted)
    bus: veh
    rate_hz: 100
  - id: 0x700            # gateway/radar alive
    bus: radar
    rate_hz: 10
  - isotp:
      bus: radar
      req_id: 0x7DF; resp_id: 0x7E0
      sequence:
        - {tx: "10 03", expect: "50 03"}      # diag session
        - {tx: "27 01", expect: "67 01 .."}   # seed/key if needed
```

**Tools**: `sniff2profile.py` (scaffold profile from capture), `validate.py` (period/CRC checks), `replay.py` (multi-bus playback).

### 6.3 Vendor Drivers

**Bosch/Tesla**
- Buses: `["radar"]` (control/env/objects all on same bus)
- Bring-up: optional UDS session; send ego speed/steer/yaw and gateway alive on `radar`
- Parser: object list families; scaling; quality flags

**Denso genX**
- Buses: `["veh","radar"]` (env on vehicle bus; objects on radar bus)
- Bring-up: VIN/keepalive; env on `veh`, alive on `radar`
- Parser: paginated objects; existence probability

**Config**
```yaml
radar:
  driver: "denso_genX"      # or "bosch_tesla"
  sim: true
  buses:
    veh: "can2"
    radar: "can0"
  logs:
    raw_frames: true
    objects: true
```

---

## 7. Perception Modules
- **Tyre zones (MLX90640):** centre-band average; gradient edges; hysteresis ±2 px; split into thirds; trimmed median; EMA α≈0.3; slew-limit ~50 °C/s (Numba optional)
- **Radar tracking:** α-β filter; score by range, closing speed, lateral offset; age-out > 300 ms
- **Fuel usage:** PID 5E (L/h) if present; else `L/h = (MAF[g/s]/(AFR*ρ))*3600` with AFR=14.7, ρ≈0.74 kg/L; integrate per lap; compute laps remaining
- **SOC smoothing:** EMA of SOC%; classify state via current/power thresholds
- **Shift lights:** RPM bands (% of redline) with hysteresis; gear derived (speed/RPM/ratios)
- **NeoKey radar alerts:** closing ≥ 8 m/s or TTC ≤ 3 s (< 60 m) → flash all blue; overtake → side-only 2 s

---

## 8. Laptimer
- GPS ≥ 10 Hz; gates (lat/lon/width); hysteresis; min_lap_s guard
- Predictive time via arc-length model vs reference; sector PBs
- CSV/Parquet export per session

---

## 9. HUD Elements
| Overlay | Source | Notes |
|---|---|---|
| Tyre temps | MLX90640 | 3-zone bars per wheel |
| Brake temps | IR sensors | Numeric or ring |
| Lap delta | GPS | Bar + numeric; predictive |
| Radar | Radar driver | Arcs/dots on rear camera |
| Shift lights | OBD RPM | LED strip or on-screen bar |
| Fuel | OBD/MAF | Lap burn; remaining; laps left |
| SOC | CAN/UDS | Bottom progress bar; colour by state |
| Alerts | Radar→NeoKey | Blue flashes (approach/overtake) |

---

## 10. OBD ISO-TP
```yaml
obd:
  sessions:
    - {iface: "obd0", req_id: 0x7DF, resp_id: 0x7E8, ext_29bit: false}
    - {iface: "can3", req_id: 0x7DF, resp_id: 0x7E8, ext_29bit: false}  # MS-CAN, if used
  poll:
    rpm:        {iface: "obd0", mode: 0x01, pid: 0x0C, hz: 20}
    speed:      {iface: "obd0", mode: 0x01, pid: 0x0D, hz: 10}
    coolant:    {iface: "obd0", mode: 0x01, pid: 0x05, hz: 2}
    fuel_rate:  {iface: "obd0", mode: 0x01, pid: 0x5E, hz: 5}
```

---

## 11. Logging Layout
```text
/data/sessions/YYYY-MM-DD_HHMMSS/
  meta.yaml            # track, vehicle profile, config hash, git commit
  telemetry.bin        # tagged binary records with timestamps
  index.csv            # lap boundaries, lap times, fuel/lap
  thermal_FL.csv       # optional per-wheel I/C/O for analysis
```
Tag each record with `source`, `bus`, and `id` (if CAN). Flush in small chunks; fsync on ignition-off.

---

## 12. Performance Targets
| Path | Target |
|---|---|
| Render loop | ≤ 12 ms/frame (30–60 FPS) |
| Thermal zones | < 1 ms/frame/sensor |
| Radar parse | < 3 ms for 40 objects |
| CAN scheduler | < 10% CPU for 4 classic CAN buses |
| Camera → display | < 80 ms median |
| Log writer | < 10 ms/s avg |

SPI @ 20 MHz provides ample headroom; ensure separate IRQs and sane buffers.

---

## 13. Testing & Calibration
- **Bench:** multi-bus replay; radar sim profiles validated (`validate.py`)
- **Tyre:** heat-gun pattern; verify I/C/O ordering across steering range
- **Radar:** car-park passes; ensure status OK after env sim
- **Lap timer:** repeatability < 0.1 s on known circuit logs
- **OBD:** PID support per vehicle; graceful fallbacks
- **SOC:** CAN mapping + thresholds
- **Power-loss:** ignition-off flush; safe shutdown

---

## 14. Config Examples
```yaml
fuel:
  tank_size_l: 50.0
  afr: 14.7
  density_kgpl: 0.74
  warn_laps: 5

shift_lights:
  redline_rpm: 8000
  bands: [0.85, 0.92, 0.97, 1.00]
  blink_hz: 6

radar:
  driver: "bosch_tesla"        # or "denso_genX"
  sim: true
  buses: {radar: "can0"}       # denso: {veh: "can2", radar: "can0"}
  logs: {raw_frames: true, objects: true}

radar_alerts:
  enable_neokey: true
  closing_speed_mps: 8.0
  ttc_s: 3.0
  max_range_m: 60.0
  flash_hz: 4.0
  overtake_hold_s: 2.0
  left_keys: [0, 1]
  right_keys: [2, 3]
```

---

## 15. Roadmap
| Version | Deliverables |
|---|---|
| v0.1 | Core app, config loader, logger scaffold |
| v0.2 | GPS + lap timing |
| v0.3 | TPMS + brake temps |
| v0.4 | Tyre I/C/O zones (Numba path) |
| v0.5 | Rear camera HUD |
| v0.6 | Radar core + Tesla/Bosch driver + sim profile |
| v0.7 | Denso driver (split-bus) + sim profile |
| v0.8 | NeoKey radar alerts |
| v0.9 | OBD (CANable), RPM/temps |
| v0.10 | Shift lights |
| v0.11 | Fuel usage + laps remaining |
| v0.12 | Hybrid SOC bar |
| v0.13 | Multi-CAN scheduler + HS/MS profiles + udev/systemd bring-up |
| v1.0 | Docs, calibration tools, reliability pass |

---

## 16. Technical Notes
- Ground pin 4 for power return; pin 5 as logic ref; single-point bond
- SPI 20 MHz is fine for 4 MCP2517FD; dedicate IRQs; keep traces short
- Buffers: `sysctl -w net.core.rmem_max=262144`; `ip link set canX txqueuelen 2048`
- OBD polling: keep total requests < 20–30/s per bus; cache unsupported PIDs
- Safety: never inject simulator frames into a live vehicle bus; use a bench harness with proper termination
- Cold start: warm up Numba-compiled functions at boot
- https://github.com/commaai/laika/ for GPS
- Ford Hybrid PIDs https://torque-bhp.com/community/main-forum/ford-and-lincoln-hybrid-vehicle-custom-pid/
PID     LONG NAME                       SHORT NAME     MIN   MAX   SCALE  UNIT      EQUATION
224801  HV Battery State of Charge      SoC            0     100   x1     %        ((((A*256)+B)*(1/5))/100)
224800	HV Battery Temperature          HV Temp        0     150   x1     DegF     ((A*18)-580)/100
22480b	HV Battery current in Amps      HV Amps        -200  200   x1     Amps     ((((Signed(A)*256)+B)/5)/10)*-1
22480d	HV Battery Voltage              HV Volts       0     400   x1     Volts    (((A*256)+B)/100)
22dd04	Temperature inside car          Inside Temp    0     160   x1     DegF     ((A*18)-400)/10
224815	Maximum Discharge Power Limit   Mx Dis Lmt     0     500   x1     kW       (A*25)/10
224816	Maximum Charge Power Limit      Mx Chg Lmt     0     500   x1     kW       (A*25)/10 
224841	Average Battery Module Voltage  Avg Bat Vtg    0     500   x1     Volts    (((A*256)+B)*(1/10))/10
224810	Battery Age                     Bat Age        0     999   x1     Months   (((A*256)+B)*(1/20))/10
221E1C	Transmission Temp               Trans Temp     0     300   x1     DegF     (((A*256)+B)*(9/8)+320)/10
224832	Motor Electronics Coolant Temp  Elec Clt Temp  0     300   x1     DegF     (A*18+320)/10
22F41F 	Engine Run time                 Eng Run Tme    0     999   x1     Minutes  (((A*256)+B)*(25/16))/10
22481E	Generator Inverter Temp         Gen Inv Tmp    0     300   x1     DegF     (((A*256)+B)*18+320)/10
224824	Motor Inverter Temp             Mtr Inv Tmp    0     300   x1     DegF     (((A*256)+B)*18+320)/10 



---

**Summary:** Modular, multi-bus open-TPT with swappable radar drivers and a built-in CAN-environment simulator. Each signal declares its bus, radar and OBD are isolated, and the HUD remains responsive under load. Configuration flips vehicle profiles without code changes.
