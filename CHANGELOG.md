# Changelog - openTPT

## [v0.7] - 2025-11-13

### Radar Overlay Integration 📡

#### ✅ New Features
- **Optional Toyota radar overlay** - CAN bus radar integration with collision warnings
- **Radar track visualization** - Green/yellow/red chevron arrows showing relative positions
- **Overtake warnings** - Blue side arrows for rapidly approaching vehicles
- **Distance and speed display** - Real-time relative speed in m/s and km/h
- **Graceful degradation** - System automatically disables radar if hardware unavailable

#### 📦 New Files

```
hardware/
└── radar_handler.py               # Toyota radar CAN handler with bounded queues

gui/
└── radar_overlay.py               # Radar overlay renderer (chevrons, overtake alerts)
```

#### 🔄 Modified Files

- `main.py` - Added radar handler initialization and cleanup
- `gui/camera.py` - Integrated radar overlay rendering
- `utils/config.py` - Added comprehensive radar configuration section

#### ⚙️ Configuration

**Radar Settings** (in `utils/config.py`):
```python
RADAR_ENABLED = False              # Disabled by default
RADAR_CHANNEL = "can0"             # CAN channel for radar data
CAR_CHANNEL = "can1"               # CAN channel for keepalive
RADAR_INTERFACE = "socketcan"      # python-can interface
RADAR_BITRATE = 500000             # CAN bitrate
RADAR_DBC = "opendbc/toyota_prius_2017_adas.dbc"
CONTROL_DBC = "opendbc/toyota_prius_2017_pt_generated.dbc"

# Display settings
RADAR_CAMERA_FOV = 106.0           # Camera field of view (degrees)
RADAR_TRACK_COUNT = 3              # Number of tracks to display
RADAR_MAX_DISTANCE = 120.0         # Maximum distance (metres)
RADAR_WARN_YELLOW_KPH = 10.0       # Yellow warning threshold
RADAR_WARN_RED_KPH = 20.0          # Red warning threshold

# Overtake warning settings
RADAR_OVERTAKE_TIME_THRESHOLD = 1.0       # Time threshold (seconds)
RADAR_OVERTAKE_MIN_CLOSING_KPH = 5.0      # Minimum closing speed (km/h)
RADAR_OVERTAKE_MIN_LATERAL = 0.5          # Minimum lateral offset (metres)
RADAR_OVERTAKE_ARROW_DURATION = 1.0       # Arrow display duration (seconds)
```

#### 📊 Architecture

**Bounded Queue Integration**
- Radar handler extends `BoundedQueueHardwareHandler`
- Lock-free track access for render path
- Double-buffered data snapshots (queue depth = 2)
- No blocking operations in overlay rendering

**Three-Level Optional Checking**
1. `RADAR_ENABLED` config flag (default: False)
2. `RADAR_AVAILABLE` import check (toyota_radar_driver)
3. `radar_handler.is_enabled()` runtime check

#### 🧪 Testing

- ✅ Camera initializes correctly with `radar_handler=None`
- ✅ Radar handler gracefully disables when hardware unavailable
- ✅ `get_tracks()` returns empty dict when disabled
- ✅ Camera doesn't create overlay when radar disabled
- ✅ Configuration defaults are safe (RADAR_ENABLED = False)
- ✅ Integration tested on Mac and Pi

#### 📝 Dependencies (Optional)

For radar support:
```bash
pip3 install python-can cantools
```

Copy `toyota_radar_driver.py` from `scratch/sources/toyota-radar/` or install as package.

---

## [v0.6] - 2025-11-12

### Major Performance Refactoring

#### ✅ Fixed
- **NameError in TPMS handler** - Fixed `TirePosition` being used before TPMS library check
- **Infinite recursion in MLXHandler** - Fixed backwards compatibility wrapper
- **British English throughout** - Changed all "Tire" → "Tyre", "Optimized" → "Optimised", "Initialize" → "Initialise"

#### 🚀 Performance Optimisations Added

**Bounded Queue Architecture**
- Lock-free data snapshots for render path
- Zero blocking in render loop (≤ 12 ms/frame target)
- Double-buffering with queue depth = 2
- Automatic frame dropping when queue full

**Numba-Optimised Thermal Processing**
- I/C/O (Inner/Centre/Outer) zone analysis
- Edge detection with hysteresis (±2 px)
- Trimmed median filtering
- EMA smoothing (α ≈ 0.3)
- Slew-rate limiting (~50 °C/s)
- **Performance**: < 1 ms/frame/sensor ✓

**Hardware Handler Refactoring**
- `MLXHandlerOptimised` - Thermal cameras with zone processing
- `BrakeTemperatureHandlerOptimised` - IR brake sensors with EMA
- `TPMSHandlerOptimised` - TPMS with callback-based updates

**Performance Monitoring**
- Real-time render time tracking
- Hardware update rate monitoring
- Thermal processing time validation
- Automatic target checking with warnings
- Periodic performance summaries

#### 📦 New Files

```
utils/
├── hardware_base.py           # Bounded queue base class
└── performance.py             # Performance monitoring

perception/
└── tyre_zones.py              # Numba thermal processor

hardware/
├── mlx_handler_optimized.py   # Optimised handlers
├── ir_brakes_optimized.py
└── tpms_input_optimized.py

tools/
├── performance_test.py        # Validation tests
└── quick_sync.sh              # Fast Mac→Pi deployment

# Deployment scripts
deploy_to_pi.sh                # Full deployment
requirements.txt               # Python dependencies

# Documentation
PERFORMANCE_OPTIMISATIONS.md   # Technical details
DEPLOYMENT.md                  # Deployment guide
```

#### 🔄 Modified Files

- `main.py` - Integrated optimised handlers with performance monitoring
- All optimised handlers use British English spelling

#### ⚙️ Configuration

**Automatic Fallback**
- System tries optimised handlers first
- Falls back to original handlers if import fails
- Graceful degradation without hardware

**Dependencies (Optional)**
- `numba` - JIT compilation for thermal processing (10x speed improvement)
- Install with: `pip3 install numba`

#### 📊 Performance Targets (from System Plan)

| Component | Target | Status |
|-----------|--------|--------|
| Render loop | ≤ 12 ms/frame | ✅ |
| Thermal zones | < 1 ms/sensor | ✅ |
| Lock-free access | < 0.1 ms | ✅ |
| FPS | 30-60 FPS | ✅ |

#### 🧪 Testing

**Run Performance Tests**
```bash
python3 tools/performance_test.py
```

**Run Application (Mock Mode)**
```bash
./main.py --windowed
```

**Deploy to Pi**
```bash
./deploy_to_pi.sh pi@raspberrypi.local
```

#### 🎯 Deployment Workflow (Mac → Pi)

1. **Develop on Mac**
   ```bash
   ./main.py --windowed  # Test in mock mode
   ```

2. **Deploy to Pi**
   ```bash
   # Full deployment
   ./deploy_to_pi.sh pi@raspberrypi.local

   # Or quick sync (code only)
   ./tools/quick_sync.sh pi@raspberrypi.local
   ```

3. **Test on Pi**
   ```bash
   ssh pi@raspberrypi.local
   cd /home/pi/openTPT
   python3 tools/performance_test.py
   ./main.py
   ```

#### 📝 British English Changes

- Tyre (not Tire)
- Optimised (not Optimized)
- Initialise (not Initialize)
- Colour (not Color) - applied consistently
- Metres (not Meters) - in comments
- Centre (not Center) - in zone names

#### 🔮 Next Steps (from System Plan)

- [ ] Radar module with modular plugins
- [ ] Multi-CAN scheduler (HS/MS/OBD/radar)
- [ ] OBD ISO-TP implementation
- [ ] GPS lap timing with predictive delta
- [ ] Binary telemetry logging

---

## Testing Checklist

- [x] Handlers import without errors
- [x] App starts in mock mode
- [x] No NameError or recursion issues
- [x] British English throughout
- [x] Backwards compatibility maintained
- [x] Performance monitoring integrated
- [x] Test on Pi with actual hardware
- [x] Validate thermal zone processing
- [x] Check render loop timing
- [x] Verify hardware update rates
- [x] Radar overlay integration
- [x] Radar graceful degradation

---

**Status**: Deployed and tested on Pi 🎉

### Pi Hardware Status
- ✅ TPMS: 4/4 sensors auto-paired (FL, FR, RL, RR)
- ✅ NeoKey 1x4: Working (brightness, camera toggle, UI toggle)
- ⚠️ MLX90640: 1/4 cameras connected (FL operational)
- ⚠️ ADS1115: Not detected (brake temps unavailable)
- ⚠️ Radar: Not configured (RADAR_ENABLED = False by default)
