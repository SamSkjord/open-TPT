# Changelog - openTPT

## [v0.18.1] - 2026-01-17

### Unified Route System & CoPilot Improvements

#### Route Integration

- **Unified route/track system** - Lap timing and CoPilot now share route data
  - CoPilot automatically uses lap timing track centerline for junction guidance
  - Eliminates need for separate GPX route loading when track is loaded
  - Both circuit tracks (KMZ) and point-to-point stages (GPX) supported
- **GPX file support in lap timing** - Load GPX routes as point-to-point stages
  - First trackpoint = start line, last trackpoint = finish line
  - Synthetic S/F line created perpendicular to track direction
  - New `load_track()` auto-detects format from file extension
- **Load Route File menu** - New option in Lap Timing menu
  - Scan `~/.opentpt/routes/` for GPX and KMZ files
  - Shows file type indicator (GPX/KMZ)
  - Supports up to 15 route files

#### CoPilot Menu Improvements

- **Use Lap Timing Track** - New option in CoPilot Routes menu
  - Appears when a track is loaded in lap timing
  - Shows "[Using] Track Name" when active
  - Automatically switches to Route Follow mode
- **Track/Route labels** - Display shows source of route data
  - "Track: name" when using lap timing track
  - "Route: name" when using dedicated GPX route
  - "Stage: name" for point-to-point routes in lap timing

#### Bluetooth Audio Metadata

- **MPRIS D-Bus interface** - Show "Now Playing" info on Bluetooth car head units
  - Callout text displayed as track title via AVRCP
  - Album art (splash.png) exposed to connected head units
  - Updates metadata when callouts play, resets to "CoPilot Ready" when stopped
  - Works with car stereos, Bluetooth speakers, and head units supporting AVRCP

#### Display Fixes

- **Status bar padding** - CoPilot page now accounts for top/bottom status bars
  - Header and footer positioned within content area
  - Main corner indicator and callouts properly centred
  - Path info panel positioned correctly

#### Technical Details

- `LapTimingHandler.get_route_waypoints()` - Exposes track centerline for CoPilot
- `LapTimingHandler.load_track_from_file()` - Unified GPX/KMZ loading
- `LapTimingHandler.is_point_to_point()` - Check if track is a stage
- `CoPilotHandler` now accepts `lap_timing_handler` parameter
- `Track` dataclass extended with `is_point_to_point` and `source_file` fields

#### Modified Files

- `copilot/mpris.py` - New MPRIS D-Bus service for Bluetooth metadata
- `copilot/audio.py` - MPRIS integration for callout metadata
- `copilot/splash.png` - Album art for Bluetooth head units
- `gui/copilot_display.py` - Status bar padding for content area
- `gui/menu.py` - Route integration menus, Load Route File option
- `hardware/copilot_handler.py` - Lap timing integration
- `hardware/lap_timing_handler.py` - Route exposure methods
- `lap_timing/data/track_loader.py` - GPX parsing, unified loader
- `main.py` - Pass lap_timing to CoPilot handler

---

## [v0.18.0] - 2026-01-17

### CoPilot Rally Callout System

#### New Features

- **CoPilot integration** - Rally-style audio callouts for upcoming corners
  - Uses OSM map data to detect corners, junctions, bridges, and hazards
  - Audio callouts via espeak-ng TTS or Janne Laahanen rally samples
  - Corner severity on ASC 1-6 scale (1=flat out, 6=hairpin)
  - Lookahead distance configurable (500m-1500m)
- **GPS heading extraction** - Added course-over-ground parsing from RMC sentences
  - Required for CoPilot road path projection
  - 10Hz updates from PA1616S GPS module
- **CoPilot display page** - Dedicated UI page showing:
  - Large corner indicator with direction arrow and severity
  - Distance to next corner with colour coding (green/yellow/red)
  - Current mode, route name, and status information
- **CoPilot modes** - Two operating modes:
  - Just Drive: Follow whatever road you're on, detecting corners ahead
  - Route Follow: Follow a loaded GPX route file
- **Corner overlay** - Shows next corner on all display pages
  - Direction arrow (left/right)
  - Severity number
  - Distance countdown
- **CoPilot menu** - Full settings submenu:
  - Enable/disable, Audio on/off, Lookahead distance
  - Mode selection, Route loading from GPX files

#### Technical Details

- Map data stored on NVMe (`/mnt/nvme/copilot/maps/`) due to 6.4GB size
- Symlinked from `~/.opentpt/copilot/maps/`
- Pre-processed roads.db with R-tree spatial indexing for fast queries
- Threaded worker with bounded queue following openTPT patterns
- GPS adapter bridges openTPT GPSHandler to CoPilot interface

#### Configuration

- `COPILOT_ENABLED` - Enable/disable system
- `COPILOT_MAP_DIR` - Path to roads.db files
- `COPILOT_LOOKAHEAD_M` - Corner detection distance (default 1000m)
- `COPILOT_AUDIO_ENABLED` - Enable audio callouts
- `COPILOT_OVERLAY_ENABLED` - Show corner indicator overlay

#### Modified Files

- `main.py` - CoPilot handler and display integration
- `gui/menu.py` - CoPilot settings submenu
- `gui/display.py` - Corner indicator overlay method
- `hardware/gps_handler.py` - Heading extraction from RMC
- `utils/config.py` - COPILOT_* configuration options

#### New Files

- `copilot/` - Rally callout module (map_loader, path_projector, corners, pacenotes, audio)
- `hardware/copilot_handler.py` - CoPilot integration handler with GPS adapter
- `gui/copilot_display.py` - CoPilot UI page

---

## [v0.17.9] - 2026-01-16

### Fuel Tracking, Temperature Overlays & Code Quality

#### New Features

- **Fuel tracking with OBD2 integration** - Real-time fuel monitoring for hybrid vehicles
  - Reads fuel level from OBD2 (standard PID 0x2F)
  - Average fuel consumption per lap calculation
  - Estimated laps remaining based on consumption rate
  - Fuel used this session tracking
- **Fuel display modes** - Multiple visualisation options
  - Percentage mode: current fuel level as percentage
  - Laps remaining mode: estimated laps until empty
  - Consumption mode: average litres per lap
- **Refuelling detection** - Automatic session reset on fuel increase
  - Detects when fuel level increases (refuelling)
  - Resets session fuel tracking after pit stop
  - Configurable threshold to avoid false triggers
- **Global fuel warnings** - Visual alerts for low fuel
  - Warning threshold configurable (default 10%)
  - Critical threshold configurable (default 5%)
  - Status bar colour changes to indicate fuel state
- **Temperature overlays on tyre zones** - Visual temp display on heatmaps
  - Shows numeric temperature values on left/centre/right zones
  - Colour-coded text based on temperature thresholds
  - Also added to brake temperature displays
- **Config reload functionality** - Hot-reload settings without restart
  - Reload configuration from menu
  - Validates settings before applying
  - Logs changes for debugging

#### Improvements

- **Comprehensive logging** - Replaced print statements with proper logging
  - All modules now use Python logging framework
  - Consistent log levels (DEBUG, INFO, WARNING, ERROR)
  - Improved log messages with context
  - Fixed British spelling throughout
- **Code quality improvements**
  - Fixed race condition in recording setter
  - Consolidated unit conversion functions
  - Removed dead code and unused imports
  - Fixed crash log race condition
  - Added `frozen=True` to `HardwareSnapshot` dataclass for true immutability
  - Replaced 18 broad `except Exception` catches with specific types in `unified_corner_handler.py`
  - Fixed boot profiling debug messages with meaningful labels (was `\1` control chars)
  - Removed unnecessary `sys.path` manipulation from hardware handlers
- **ExponentialBackoff helper class** - Reusable backoff logic in `utils/hardware_base.py`
  - Consistent backoff behaviour across all hardware handlers
  - Configurable initial delay, multiplier, and max delay

#### Bug Fixes

- **Lap timing settings** - Fixed settings not persisting correctly
- **Camera menu crash log** - Fixed race condition when writing crash logs
- **FordHybridHandler import** - Fixed broken import path that prevented module loading
- **SettingsManager singleton race condition** - Fixed double-checked locking pattern
- **Deque access race conditions** - Added IndexError handling in `unified_corner_handler.py`
  for thread-safe access to `tyre_queue`, `brake_queue`, `tof_queue`
- **Resource cleanup leaks** - Fixed I2C and CAN bus cleanup:
  - `unified_corner_handler.py`: Now closes `i2c_busio` in `stop()`
  - `obd2_handler.py`: Shuts down CAN bus before reconnection attempts
- **Settings file corruption** - Atomic writes via temp file + rename
- **Missing UTF-8 encoding** - Added explicit encoding to file operations in
  `settings.py` and `telemetry_recorder.py`
- **British English violations** - Fixed `FPS_COUNTER_COLOR` → `FPS_COUNTER_COLOUR`,
  "Colorkey" → "Colourkey", "Tire" → "Tyre" in docstrings
- **Update rate calculation** - Fixed formula in `get_update_rate()` to correctly
  calculate Hz from queue timestamps
- **GPS serial port leak** - Fixed resource leak in `_configure_mtk3339()` when
  exceptions occur during baud rate configuration
- **Brake surface allocation** - Cached brake gradient surfaces to avoid
  `pygame.Surface()` allocation every frame in render loop
- **WiFi connectivity drops** - Disabled WiFi power save mode which was
  causing intermittent connection losses

#### Improvements

- **NeoDriver startup animation** - Re-enabled rainbow sweep animation on boot
  for visual feedback that LED strip is working

#### Modified Files

- `hardware/obd2_handler.py` - Added fuel level PID reading, CAN bus cleanup on reconnect
- `hardware/ford_hybrid_handler.py` - Fixed import path
- `hardware/unified_corner_handler.py` - Specific exception types, thread-safe deque access, i2c_busio cleanup
- `hardware/gps_handler.py` - Fixed serial port leak in MTK3339 configuration
- `hardware/neodriver_handler.py` - Re-enabled startup animation
- `utils/fuel_tracker.py` - New fuel tracking module
- `utils/hardware_base.py` - Frozen dataclass, ExponentialBackoff helper class
- `utils/settings.py` - Thread-safe singleton, atomic writes, UTF-8 encoding
- `utils/config.py` - British English: `FPS_COUNTER_COLOUR`
- `utils/telemetry_recorder.py` - UTF-8 encoding
- `gui/display.py` - Temperature overlay rendering, British English fixes, brake surface caching
- `gui/menu.py` - Fuel display mode menu, config reload
- `main.py` - Fuel tracker integration, boot profiling labels
- `hardware/radar_handler.py` - Removed sys.path hack
- `hardware/tpms_input_optimized.py` - Removed sys.path hack
- Multiple modules - Logging improvements

---

## [v0.17.8] - 2026-01-15

### Expanded OBD2 Telemetry Logging

#### New Features

- **Extended OBD2 data logging** - Comprehensive vehicle telemetry recording
  - High-priority (7Hz): speed, RPM, throttle position
  - Low-priority (rotated 1Hz): coolant temp, oil temp, intake temp, MAP, MAF
  - Derived: boost pressure (MAP - atmospheric)
  - Ford hybrid: battery SOC (Mode 22)
  - Placeholders for brake pressure input/output (manufacturer-specific)
- **Separate speed sources** - `obd_speed_kmh` and `gps_speed_kmh` logged independently
- **GPS data logging** - latitude, longitude, speed, heading from GPS receiver
- **Lap timing data logging** - lap number, time, delta, sector, track position

#### Technical Details

- OBD2 handler refactored with generic PID polling
- Auto-disables unsupported PIDs after 5 failures
- Smoothing applied to high-frequency data (speed, RPM, throttle)

#### Modified Files

- `hardware/obd2_handler.py` - Expanded PID polling with priority rotation
- `utils/telemetry_recorder.py` - Added OBD, GPS, lap timing fields
- `main.py` - Wired up all telemetry data sources
- `README.md` - Added configurable OBD2 PIDs to TODO

---

## [v0.17.7] - 2026-01-15

### Lap Timing Persistence & Page Toggle Menu

#### New Features

- **Lap timing persistence** - Best laps now saved to SQLite database
  - Stores best lap times per track with sector splits
  - Saves reference lap GPS traces for delta calculations
  - Best lap loaded automatically when track is selected
  - Data persists in `~/.opentpt/lap_timing/lap_timing.db`
- **Pages menu** - Toggle UI pages on/off in rotation
  - New Settings > Pages submenu
  - Enable/disable Telemetry, G-Meter, Lap Timing pages
  - Disabled pages skipped when cycling with page button
  - At least one page must remain enabled
  - Settings persist across restarts
- **Extended telemetry recording** - Added GPS and lap timing fields
  - GPS: latitude, longitude, speed, heading
  - Lap timing: lap number, lap time, delta, sector, track position

#### Modified Files

- `utils/lap_timing_store.py` - New SQLite storage for lap times
- `utils/config.py` - Added UI_PAGES configuration
- `gui/menu.py` - Added Pages submenu with toggle items
- `main.py` - Dynamic page cycling based on enabled settings
- `hardware/lap_timing_handler.py` - Integrated with persistent store
- `utils/telemetry_recorder.py` - Extended TelemetryFrame with GPS/lap fields

---

## [v0.17.6] - 2026-01-05

### Early Boot Splash Screen

#### New Features

- **fbi boot splash** - Framebuffer splash appears ~4 seconds into boot
  - Uses fbi to display splash.png before Python/pygame loads
  - Wait loop ensures /dev/fb0 is ready before displaying
  - Seamless handoff: main.py kills fbi when pygame display is ready
- **Faster visual feedback** - Reduces blank screen time during boot

#### Modified Files

- `config/boot/fbi-splash.service` - New systemd service for early splash
- `main.py` - Kill fbi process after pygame display initialises
- `openTPT.service` - Order after fbi-splash.service

---

## [v0.17.5] - 2025-12-11

### Shift Light Start Threshold & Ford Hybrid PID Tester

#### New Features

- **Shift light start RPM** - Lights stay off at idle, illuminate only above threshold
  - New `NEODRIVER_START_RPM` config (default 3000)
  - Scale now runs from start_rpm to max_rpm for full LED range
  - At least 1 pixel lights when above threshold
- **Ford Hybrid PID tester** - Standalone Windows script for testing Ford hybrid PIDs
  - Uses CANable 2.0 PRO via gs_usb or slcan interface
  - Tests all 14 Ford Hybrid UDS PIDs (Mode 0x22)
  - Real-time display and CSV logging

#### Modified Files

- `hardware/neodriver_handler.py` - Added start_rpm parameter and threshold logic
- `main.py` - Pass NEODRIVER_START_RPM to handler
- `utils/config.py` - Added NEODRIVER_START_RPM = 3000
- `tools/ford_hybrid_pid_tester.py` - New standalone Windows test script

---

## [v0.17.4] - 2025-12-03

### I2C Resilience & Delta Mode Improvements

#### New Features

- **Delta mode improvements** - Non-linear scale and corrected colours
  - Thresholds: 0.1s, 0.5s, 1.0s, 5.0s for progressive display
  - Colours now match top bar: red=slower, green=faster
- **Symmetrical light animations** - Centre-out and edges-in now light in proper pairs
- **Brightness sync** - Light strip brightness follows display brightness setting

#### Bug Fixes

- **I2C retry logic** - All seesaw devices now retry on init failure
  - Encoder, NeoKey, NeoDriver all have 3 retry attempts with delays
  - Silent error handling reduces log spam during bus contention
- **Delta value wiring** - Fixed timing: delta now read after value is set
- **Light Strip menu** - Mode and Direction are now proper submenus

#### Removed

- **TOF distance sensors** - Disabled VL53L0X ride height measurement (unreliable)

#### Modified Files

- `gui/encoder_input.py` - Init retry logic, silent I2C error handling
- `gui/input_threaded.py` - NeoKey init retry logic, silent error handling
- `gui/menu.py` - Light Strip menu restructured with Mode/Direction submenus
- `hardware/neodriver_handler.py` - Symmetrical rendering, non-linear delta scale
- `main.py` - Fixed delta/brightness update order
- `utils/config.py` - TOF_ENABLED set to False

---

## [v0.17.3] - 2025-12-03

### NeoDriver Menu & OBD2 RPM

#### New Features

- **Light Strip settings menu** - Configure mode and direction from Settings menu
  - Mode selection: Shift, Delta, Overtake, Off
  - Direction selection: Centre Out, Edges In, Left to Right, Right to Left
- **OBD2 RPM reading** - Engine RPM now read from vehicle
  - Automatic shift light updates based on live RPM
  - Configurable max RPM and shift point
- **Animation directions** - All render modes now support configurable direction
  - Centre Out: grow from middle pixel outward
  - Edges In: grow from edges toward centre
  - Left to Right / Right to Left: linear fill

#### Modified Files

- `gui/menu.py` - Light Strip submenu with mode/direction settings
- `hardware/obd2_handler.py` - Added RPM reading (PID 0x0C)
- `hardware/neodriver_handler.py` - Direction enum and direction-aware rendering
- `utils/config.py` - Added NEODRIVER_MAX_RPM, NEODRIVER_SHIFT_RPM, NEODRIVER_DEFAULT_DIRECTION
- `main.py` - Wire RPM to NeoDriver, pass neodriver_handler to MenuSystem

---

## [v0.17.2] - 2025-12-03

### NeoDriver LED Strip Support

#### New Features

- **Adafruit NeoDriver support** - I2C to NeoPixel driver at 0x60
  - Multiple display modes: off, delta, overtake, shift, rainbow
  - Thread-safe 15Hz updates
  - Configurable pixel count and brightness
  - Delta mode: green ahead, red behind (lap time delta)
  - Overtake mode: colour-coded warnings from radar
  - Shift mode: RPM-based shift lights with colour gradient
  - Rainbow mode: test/demo animation
  - Startup animation: rainbow sweep on/off

#### Bug Fixes

- **NeoDriver init retry** - Added retry logic with delays for I2C bus contention during startup

#### Modified Files

- `hardware/neodriver_handler.py` - New NeoDriver handler
- `utils/config.py` - NeoDriver configuration options
- `main.py` - NeoDriver integration

---

## [v0.17.1] - 2025-12-03

### Menu Scrolling & Encoder-Based Settings

#### New Features

- **Menu scrolling** - Long menus now scroll automatically
  - Auto-scroll keeps selection visible as you navigate
  - "▲ more" / "▼ more" indicators show hidden items
  - Scroll offset resets when opening a menu
  - Proper wrap-around scrolling (top↔bottom)

- **Encoder-based volume control** - Adjust volume with the rotary encoder
  - Click Volume to enter edit mode (shown as `[ Volume: 50% ]`)
  - Rotate encoder to adjust (5% per detent)
  - Click again to save and exit edit mode
  - Removed old Volume Up/Down menu items

- **Encoder-based brightness control** - Same pattern as volume
  - Click Brightness in Display menu to enter edit mode
  - Rotate encoder to adjust brightness
  - Click again to save

#### Bug Fixes

- **PulseAudio access** - Volume commands now use `XDG_RUNTIME_DIR=/run/user/1000` to access user session
- **Connect menu** - Now shows both paired AND trusted devices (some devices lose pairing but keep trust)
- **Brightness sync** - Menu brightness changes now sync to display handler

#### Modified Files

- `gui/menu.py` - Menu scrolling, encoder volume/brightness editing, trusted device support
- `main.py` - Pass input_handler to MenuSystem for brightness sync

---

## [v0.17.0] - 2025-12-02

### Telemetry Recording, Bluetooth Audio & Encoder Fixes

#### New Features

- **Telemetry recording** - Record sensor data to CSV files
  - Hold button 0 for 1 second to start/stop recording
  - LED feedback: dim red (idle), green (recording)
  - Recording menu with Cancel/Save/Delete options
  - Records TPMS, tyre temps, brake temps, IMU, and OBD2 speed
  - Files saved to `/home/pi/telemetry/telemetry_YYYYMMDD_HHMMSS.csv`
  - 10 Hz recording rate (matches sensor/GPS max rate, configurable via RECORDING_RATE_HZ)

- **Bluetooth audio menu** - Full Bluetooth audio device management
  - Scan for devices (non-blocking, 8 second background scan)
  - Auto power-on Bluetooth before scanning
  - Pair new devices (filters MAC-only names, shows friendly names only)
  - Connect to paired devices with audio confirmation sound
  - Disconnect current device
  - Forget/unpair devices
  - Volume control (display, up/down adjustment)
  - Refresh BT Services (restarts PulseAudio→Bluetooth in correct order)
  - Status display shows connected device or dependency warning
  - PulseAudio dependency check with "! Install pulseaudio" warning if missing
  - D-Bus policy for pi user to access A2DP audio profiles

#### Bug Fixes

- **Encoder brightness sync** - Encoder now starts at DEFAULT_BRIGHTNESS (0.8) instead of hardcoded 0.5
- **Encoder I2C stability** - Added protection against spurious rotation events
  - Position jumps >10 ignored as I2C glitches
  - Brightness delta capped at ±3 per poll
- **Encoder long press** - Now triggers after 500ms while held (no need to release)
- **Recording LED state** - Property setter forces immediate LED update when recording state changes
- **Status bar brightness** - SOC and lap delta bars now affected by brightness dimming
- **Bluetooth audio permissions** - D-Bus policy allows pi user to access A2DP profiles

#### New Files

- `utils/telemetry_recorder.py` - TelemetryRecorder class and TelemetryFrame dataclass

#### Modified Files

- `main.py` - Recording integration, telemetry frame capture
- `gui/input_threaded.py` - Recording button hold detection, LED feedback
- `gui/menu.py` - Recording menu, Bluetooth audio menu with full device management
- `gui/encoder_input.py` - I2C stability fixes, brightness sync
- `utils/config.py` - Added BUTTON_RECORDING and RECORDING_HOLD_DURATION
- `install.sh` - Added PulseAudio packages, D-Bus policy, bluetooth group for audio support
- `README.md` - Added Bluetooth audio optional install step

---

## [v0.16.0] - 2025-12-02

### Rotary Encoder Input & Menu System

#### New Features

- **Rotary encoder support** - Adafruit I2C QT Rotary Encoder with NeoPixel
  - Rotation controls brightness (default mode)
  - Short press = select/confirm
  - Long press = back/exit menu
  - NeoPixel feedback for state indication

- **On-screen menu system** - Navigate settings via encoder or keyboard
  - TPMS sensor pairing (FL, FR, RL, RR)
  - Bluetooth audio pairing for CopePilot
  - Display brightness control
  - Semi-transparent overlay with navigation hints

- **TPMS pairing via UI** - Pair sensors directly from the menu
  - Visual feedback during pairing (orange NeoPixel pulse)
  - Success/failure indication (green/red flash)

- **Bluetooth audio pairing** - Scan and connect Bluetooth devices
  - Uses system `bluetoothctl` for pairing

#### New Files

- `gui/encoder_input.py` - Threaded encoder handler with event queue
- `gui/menu.py` - Menu system with hierarchical navigation

#### Modified Files

- `main.py` - Integrated encoder and menu system
- `utils/config.py` - Added encoder configuration
- `requirements.txt` - Updated seesaw comment

---

## [v0.15.3] - 2025-12-01

### TPMS Library Update

#### Improvements

- **Updated to TPMS library v2.1.0** - Library now uses British spelling throughout
  - `TirePosition` → `TyrePosition`
  - `TireState` → `TyreState`
  - `register_tire_state_callback` → `register_tyre_state_callback`

- **Added TPMS to requirements.txt** - `tpms>=2.1.0` now explicitly listed

#### Modified Files

- `hardware/tpms_input_optimized.py` - Updated imports and method calls to use British spelling
- `requirements.txt` - Added TPMS dependency

---

## [v0.15.2] - 2025-11-26

### Bug Fixes & Stability Improvements

#### Bug Fixes

- **Fixed intermittent "invalid color argument" crash** - Added None checks to colour calculations:
  - `gui/display.py`: `get_color_for_temp()` now returns GREY for None values
  - `ui/widgets/horizontal_bar.py`: `_get_colour_for_value()` handles empty zones and None values
  - `ui/widgets/horizontal_bar.py`: `HorizontalBar.draw()` and `DualDirectionBar.draw()` handle None values

- **Improved crash logging** - Full traceback now written to `/tmp/opentpt_crash.log` on crash for easier debugging

#### Improvements

- **Reduced IMU log spam** - IMU I2C errors now only logged after 3+ consecutive failures (was 1)
  - Single errors from I2C bus contention are common and recover immediately
  - Prevents log flooding while still reporting persistent issues

#### Modified Files

- `main.py` - Added crash log file output
- `gui/display.py` - Added None check to `get_color_for_temp()`
- `ui/widgets/horizontal_bar.py` - Added None/empty checks to colour and draw methods
- `hardware/imu_handler.py` - Changed error log threshold from 1 to 3

---

## [v0.15] - 2025-11-23

### Configuration File Reorganisation

#### Improvements

- **Logical section grouping** - Config file reorganised into 10 clear sections:
  1. Display & UI Settings
  2. Colours & Assets
  3. Unit Settings
  4. I2C Hardware Configuration (all addresses grouped together)
  5. Camera Configuration
  6. Per-Corner Sensor Configuration (Tyre, Brake, TOF, Pressure)
  7. IMU/G-Meter Configuration
  8. CAN Bus Configuration (OBD2, Ford Hybrid, Radar)
  9. Input Configuration
  10. Helper Functions

- **I2C addresses consolidated** - All I2C addresses now in single section:
  - `I2C_BUS`, `I2C_MUX_ADDRESS`, `I2C_MUX_RESET_PIN`
  - `ADS_ADDRESS`, `TOF_I2C_ADDRESS`
  - `MCP9601_ADDRESSES`

- **Sensor thresholds co-located** - Temperature/distance thresholds now adjacent to sensor configuration
  - Tyre temp thresholds with tyre sensor config
  - Brake temp thresholds with brake sensor config
  - TOF distance thresholds with TOF sensor config

- **Module docstring** - Added table of contents listing all sections

#### Modified Files

- `utils/config.py` - Complete reorganisation (no functional changes)

---

## [v0.14] - 2025-11-22

### MCP9601 Thermocouple Brake Sensors

#### New Features

- **MCP9601 thermocouple support** - K-type thermocouple amplifiers for brake temperature
  - Supports dual sensors per corner (inner and outer brake pads)
  - I2C addresses: 0x65 (inner), 0x66 (outer)
  - Uses I2C multiplexer like other corner sensors

- **Dual-zone brake heatmap display** - Split visualisation with gradient blending
  - When both inner and outer sensors present, heatmap splits into two zones
  - Smooth gradient blend in the middle (20% of width)
  - Correct orientation: inner pad faces centre of car
  - Falls back to single-zone display when only one sensor present

- **Independent backoff per sensor type** - Extended from v0.13
  - Tyre, brake, and TOF sensors each have fully separate backoff tracking

#### Configuration

New settings in `utils/config.py`:
- `BRAKE_SENSOR_TYPES` - Now supports "mcp9601" option
- `MCP9601_DUAL_ZONE` - Per-corner enable for dual sensors
- `MCP9601_ADDRESSES` - I2C addresses for inner/outer sensors
- `MCP9601_MUX_CHANNELS` - Mux channel mapping
- `BRAKE_DUAL_ZONE_MOCK` - Test mode with animated mock data

#### 📦 Dependencies

```bash
pip3 install --break-system-packages adafruit-circuitpython-mcp9600
```

---

## [v0.13] - 2025-11-22

### VL53L0X TOF Distance Sensors

#### New Features

- **Per-corner TOF distance sensors** - VL53L0X Time-of-Flight sensors for ride height monitoring
  - Supports one sensor per corner (FL, FR, RL, RR) via I2C multiplexer
  - Displays current distance in millimetres with colour coding
  - Shows minimum distance from last 10 seconds (true raw minimum, not smoothed)
  - Graceful handling when sensors not connected or out of range

- **Independent backoff per sensor type** - Sensor failures no longer affect other sensor types
  - Tyre, brake, and TOF sensors each have separate backoff tracking
  - A failed Pico sensor won't block TOF reads on the same corner
  - Improves reliability when running with partial sensor configurations

#### 🎨 Display

- Current distance shown in colour-coded text (red → green → yellow based on thresholds)
- "mm" unit label below current value
- Minimum distance from last 10 seconds shown below with "min:" prefix
- Shows "--" when sensor out of range or not connected (no spam)

#### Configuration

New settings in `utils/config.py`:
- `TOF_ENABLED` - Master enable for all TOF sensors
- `TOF_SENSOR_ENABLED` - Per-corner enable dict
- `TOF_MUX_CHANNELS` - I2C mux channel mapping (shares channels with tyre sensors)
- `TOF_I2C_ADDRESS` - Default 0x29
- `TOF_DISPLAY_POSITIONS` - UI positions next to each tyre
- `TOF_DISTANCE_MIN/OPTIMAL/RANGE/MAX` - Thresholds for colour coding

#### Modified Files

- `utils/config.py` - Added TOF configuration section
- `hardware/unified_corner_handler.py` - Added VL53L0X support with separate backoff
- `gui/display.py` - Added `draw_tof_distance()` method
- `main.py` - Integrated TOF rendering in main loop

#### 📦 Dependencies

```bash
pip3 install --break-system-packages adafruit-circuitpython-vl53l0x
```

---

## [v0.12] - 2025-11-22

### I2C Bus Reliability Fix

#### Bug Fixes

- **I2C bus contention resolved** - Added threading lock to serialise access between smbus2 and busio libraries
  - Both libraries access the same physical I2C bus (bus 1)
  - Without synchronisation, partial transactions could leave devices in bad states
  - Pico thermal sensors (via smbus2) and MLX90614/ADS1115 (via busio) now properly serialised
  - Prevents I2C bus lockups that required power cycling to recover

- **Pico firmware v1.1** - Improved I2C slave reliability (pico-tyre-temp repo)
  - Minimal critical section - pre-calculate all values before disabling interrupts
  - Reduced interrupt-disabled time from ~100µs to <10µs
  - Prevents NACKs when Pi polls during register updates (root cause of intermittent reads)
  - Added 5-second watchdog timer for automatic hang recovery

- **I2C mux hardware reset** - GPIO-controlled recovery for TCA9548A
  - Connect TCA9548A RESET pin to GPIO17 for hardware-level recovery
  - Auto-triggers after 3 consecutive I2C read failures
  - Uses Pi's internal pull-up resistor (no external components needed)
  - Logs reset events for debugging

- **Stale data caching for heatmaps** - Prevents display flashing
  - Display runs at 35 FPS but thermal/brake data updates at 7-10 Hz
  - Previously showed grey "offline" state when no fresh data available
  - Now caches last valid data for up to 1 second (configurable via `THERMAL_STALE_TIMEOUT`)
  - Applies to both thermal heatmaps and brake temperature displays
  - Smooth display even during brief sensor read delays

- **Exponential backoff for failed sensors** - Prevents I2C bus hammering
  - Missing/failed sensors no longer spam the I2C bus with constant read attempts
  - Backoff starts at 1s, doubles each failure (1s → 2s → 4s → ... → 64s max)
  - Logs only at key intervals (1, 3, 10, 50, then every 100 failures)
  - Resets immediately on successful read with recovery message
  - Prevents bus lockups when sensors are disconnected or not yet installed

#### Modified Files

- `hardware/unified_corner_handler.py`
  - Added `threading` import
  - Added `self._i2c_lock = threading.Lock()` in `__init__`
  - Wrapped all I2C operations with `with self._i2c_lock:` context manager
  - Protected methods: `_read_pico_sensor`, `_read_tyre_mlx90614`, `_read_brake_adc`, `_read_brake_mlx90614`

- `main.py`
  - Added `THERMAL_STALE_TIMEOUT` import from config
  - Added `_thermal_cache` and `_brake_cache` dicts for stale data caching
  - Modified render loop to use cached data when fresh data unavailable

- `utils/config.py`
  - Added `THERMAL_STALE_TIMEOUT = 1.0` setting

#### Technical Details

**Root Cause:**
The unified corner handler used two different I2C libraries:
- `smbus2` - For Pico thermal sensor communication (custom I2C slave)
- `busio` (Adafruit) - For MLX90614 and ADS1115 sensors

Both libraries accessed I2C bus 1 without synchronisation. When one library was mid-transaction and the other attempted access, partial transactions could corrupt the bus state, causing devices (particularly the Pico) to hold SDA low indefinitely.

**Solution:**
A `threading.Lock()` now ensures only one I2C transaction occurs at a time, preventing bus contention.

#### 🧪 Testing

-I2C bus no longer locks up during extended operation
-All sensors continue to read correctly
-Soak testing in progress

---

## [v0.11] - 2025-11-21

### Brake Temperature Emissivity Correction

#### New Features
- **Automatic emissivity correction** - Software compensation for IR sensor readings
- **Per-corner emissivity configuration** - Adjust values to match rotor materials
- **Stefan-Boltzmann correction** - Accurate temperature calculation: `T_actual = T_measured / ε^0.25`
- **Material-specific defaults** - Pre-configured for oxidised cast iron (ε = 0.95)

#### 📝 Overview

All IR sensors (MLX90614 and ADC-based) have factory default emissivity of 1.0, assuming a perfect black body. Since brake rotors have lower emissivity (typically 0.95 for oxidised cast iron), sensors read lower than actual temperature. This update adds automatic software correction to compensate.

**How it works:**
1. MLX90614/IR sensor operates at factory default ε = 1.0 (not changed in hardware)
2. Actual brake rotor has lower emissivity (configurable per corner)
3. Sensor reads lower than actual due to less radiation from non-black-body surface
4. Software correction adjusts reading upward using Stefan-Boltzmann law

#### Modified Files

- `utils/config.py` - Added emissivity configuration and correction function
  - New function: `apply_emissivity_correction()` (lines 148-187)
  - New config: `BRAKE_ROTOR_EMISSIVITY` dictionary (lines 469-496)
  - Comprehensive documentation of emissivity values for different materials
- `hardware/unified_corner_handler.py` - Applied correction to brake sensors
  - MLX90614 brake sensors: Lines 470-504 with emissivity correction
  - ADC brake sensors: Lines 443-468 with emissivity correction
  - Added detailed docstrings explaining correction process

#### Configuration

**Brake Rotor Emissivity** (in `utils/config.py`):
```python
BRAKE_ROTOR_EMISSIVITY = {
    "FL": 0.95,  # Front Left - typical oxidised cast iron
    "FR": 0.95,  # Front Right
    "RL": 0.95,  # Rear Left
    "RR": 0.95,  # Rear Right
}
```

**Typical rotor emissivity values:**
- Cast iron (rusty/oxidised): **0.95** (default, most common)
- Cast iron (machined/clean): 0.60-0.70
- Steel (oxidised): 0.80
- Steel (polished): 0.15-0.25
- Ceramic composite: 0.90-0.95

#### Technical Details

**Correction Formula:**
```
T_actual (K) = T_measured (K) / ε^0.25
```

**Example:** If MLX90614 reads 295°C and rotor has ε = 0.95:
- Sensor assumes ε = 1.0 (factory default)
- Correction: 568.15 K / 0.95^0.25 = 575.17 K
- Corrected: ~302°C (7°C higher than uncorrected reading)

**Impact:**
- Using incorrect emissivity can result in temperature errors of 5-20°C
- Polished/clean rotors (ε = 0.60-0.70) may show significantly different readings
- Correction applied automatically to ALL brake temperature readings

#### 📖 Documentation Updates

- Updated `README.md` with brake sensor configuration section
- Updated `AI_CONTEXT.md` with emissivity correction details
- Added troubleshooting section for incorrect brake temperatures
- Enhanced inline code documentation in handler and config files
- Documented difference between tyre (Pico firmware) and brake (software) emissivity handling
- Clarified that MLX90640 tyre sensors apply emissivity via Pico firmware (0.95 for rubber)
- Explained why brake sensors use software correction (MLX90614/ADC default to ε = 1.0)

#### Security Fixes

- **CAN bus array access** - Restructured conditionals to check length before array access (obd2_handler.py)
- **Bare except clauses** - Replaced with specific exception types in unified_corner_handler.py
- **Input validation** - Added comprehensive validation to emissivity correction function
- **Thermal array validation** - Added second validation check in display.py
- **Division by zero prevention** - Added validation in brightness cycle handler
- **Display dimension validation** - Enhanced security checks for config file parsing
- **Emissivity bounds checking** - Validates emissivity values between 0.0 and 1.0

#### Long Runtime Stability Features

- **Voltage monitoring** - Checks Pi power status at startup and every 60 seconds
  - Detects undervoltage and throttling conditions
  - Logs critical power issues with actionable recommendations
  - Historical tracking (issues that occurred since boot)
  - Live monitoring (issues happening right now)
- **Automatic garbage collection** - Runs every 60 seconds
  - Frees unreferenced Python objects
  - Logs collection statistics (objects collected/freed)
  - Prevents memory accumulation during extended runtime
- **pygame surface cache management** - Clears cached surfaces every 10 minutes
  - Prevents GPU memory buildup
  - No visible impact to user (no screen flicker)
  - Reduces pygame/SDL memory fragmentation

**Fixes 6-hour crash issue:**
- G-meter page would crash after ~6 hours of continuous operation
- Root cause 1: CAN message object leak in radar driver (30,000 Message objects/minute)
- Root cause 2: pygame/SDL memory fragmentation causing `display.flip()` to block (17+ seconds)
- Solution: Removed unused BufferedReader + Periodic GC + surface cache clearing

**Memory leak fix (toyota_radar_driver.py):**
- **Issue:** `can.BufferedReader()` was accumulating all CAN messages with no limit
- **Impact:** At 320 Hz radar rate, created 19,200+ Message objects/minute
- **Growth:** Object count grew from 83k to 4 million in 90 minutes
- **Fix:** Removed unused BufferedReader from Notifier (line 224-231)
- **Result:** Object count now stable at ~55k (±3-66/minute)
- **Verification:** Message objects no longer appear in top 10 object types
- **Memory profiling added:** Logs top object types and growth deltas every 60s

#### ⚡ Performance Optimisations

**Replaced manual list management with `collections.deque`**
- **Files modified:** `hardware/obd2_handler.py`, `hardware/ford_hybrid_handler.py`
- **Improvement:** O(n) → O(1) for rolling window operations
- **Details:**
  - OBD2 handler: Replaced `speed_history` and `map_history` list management
  - Ford Hybrid handler: Replaced `soc_history` list management
  - Used `deque(maxlen=N)` for automatic size limiting (no manual `pop(0)` needed)
  - Cleaner code with same functionality and better performance
  - Particularly beneficial for real-time sensor data smoothing at 2-5 Hz poll rates

**Before (O(n) operation):**
```python
self.speed_history = []
self.speed_history.append(speed)
if len(self.speed_history) > self.speed_history_size:
    self.speed_history.pop(0)  # O(n) - shifts all elements
```

**After (O(1) operation):**
```python
self.speed_history = deque(maxlen=5)
self.speed_history.append(speed)  # O(1) - auto-drops oldest
```

#### 🧪 Testing

-Emissivity correction applied to both ADC and MLX90614 brake sensors
-Invalid emissivity values (≤0 or >1.0) safely handled
-Default emissivity (1.0) returns uncorrected temperature
-Configuration properly documented with typical material values
-Voltage monitoring detects power issues on CM4-POE-UPS carrier
-Garbage collection runs every 60s, freeing 500-700 objects per cycle
-Surface cache clearing has no visible impact on display
-Deque optimisation maintains identical functionality with better performance

---

## [v0.10] - 2025-11-20

### Toyota Radar Overlay Integration

#### New Features
- **Toyota radar overlay** - Real-time collision warning on rear camera
- **Radar track detection** - Displays 1-3 nearest vehicles with green/yellow/red chevrons
- **Solid-filled chevrons** - 3x larger (120×108px), highly visible markers
- **Distance and speed display** - Shows range in metres and relative speed
- **Overtake warnings** - Blue side arrows for rapidly approaching vehicles
- **Automatic track merging** - Combines nearby tracks within 1m radius

#### 📦 New Files

```
hardware/
└── toyota_radar_driver.py        # Toyota radar CAN driver with keep-alive

opendbc/
├── toyota_prius_2017_adas.dbc    # Radar message definitions
├── toyota_prius_2017_pt_generated.dbc  # Powertrain messages
└── toyota_corolla_2017_pt_generated.dbc
```

#### Modified Files

- `hardware/radar_handler.py` - Fixed radar driver import and configuration
  - Changed import to `from hardware.toyota_radar_driver import ...`
  - Disabled auto_setup (CAN interfaces managed by systemd)
  - Added debug logging for track reception
  - Corrected CAN channel assignment
- `gui/radar_overlay.py` - Enlarged chevrons and made solid-filled
  - Increased chevron size from 40×36px to 120×108px (3x larger)
  - Removed hollow center cutout for better visibility
  - Solid-filled triangles for clear visibility
- `utils/config.py` - Enabled radar and configured CAN channels
  - `RADAR_ENABLED = True`
  - `RADAR_CHANNEL = "can_b1_1"` (radar outputs tracks here)
  - `CAR_CHANNEL = "can_b1_0"` (keep-alive sent here)

#### Configuration

**Radar Settings** (in `utils/config.py`):
```python
RADAR_ENABLED = True                    # Enable radar overlay on camera
RADAR_CHANNEL = "can_b1_1"              # CAN channel for radar data
CAR_CHANNEL = "can_b1_0"                # CAN channel for car keep-alive
RADAR_INTERFACE = "socketcan"           # python-can interface
RADAR_BITRATE = 500000                  # CAN bitrate

# Display settings
RADAR_CAMERA_FOV = 106.0                # Camera horizontal field of view
RADAR_TRACK_COUNT = 3                   # Number of nearest tracks to display
RADAR_MAX_DISTANCE = 120.0              # Maximum distance (metres)
RADAR_WARN_YELLOW_KPH = 10.0            # Yellow warning threshold
RADAR_WARN_RED_KPH = 20.0               # Red warning threshold
```

#### Architecture

**CAN Channel Assignment**
- **can_b1_0**: Car keep-alive messages (TX from Pi to radar)
- **can_b1_1**: Radar track output (RX from radar to Pi)
- Radar outputs ~960 track messages in 3 seconds (~320 Hz)

**Chevron Color Coding**
- **Green**: Vehicle detected, safe distance (<10 km/h closing)
- **Yellow**: Moderate closing speed (10-20 km/h)
- **Red**: Rapid approach (>20 km/h closing speed)
- **Blue side arrows**: Overtaking vehicle warning

**Track Processing**
- Bounded queue (depth=2) for lock-free render access
- Automatic merging of tracks within 1m radius
- 0.5s timeout for stale tracks
- Displays 3 nearest tracks within 120m range

#### Bug Fixes

- Fixed radar driver import path (was looking for global module)
- Disabled CAN interface auto-setup (conflicts with systemd management)
- Corrected radar/car channel swap (tracks now received correctly)
- Copied missing DBC files from scratch/sources

#### 🧪 Testing

-Radar successfully receives 1-3 tracks
-CAN bus confirmed active (960 track messages in 3 seconds)
-Chevrons render on rear camera view (not on front camera)
-3x larger solid-filled chevrons highly visible
-No CAN interface conflicts with systemd

#### 📝 Dependencies (Raspberry Pi)

```bash
# Install cantools for DBC file parsing
pip3 install --break-system-packages cantools
```

#### 🎯 Hardware Requirements

- Waveshare Dual CAN HAT (Board 1)
- Toyota radar module (Prius/Corolla 2017+)
- CAN connections:
  - Board 1, CAN_0 (can_b1_0): Car keep-alive
  - Board 1, CAN_1 (can_b1_1): Radar track output

---

## [v0.9] - 2025-11-20

### Status Bars & OBD2 Simulation

#### New Features
- **Application-level status bars** - Top and bottom bars visible on all pages
- **MAP-based SOC simulation** - Uses intake manifold pressure for desk testing without vehicle
- **Dynamic color coding** - Real-time visual feedback for charge/discharge state
- **Instant SOC updates** - Direct MAP-to-SOC mapping for responsive display
- **Clean camera transitions** - Stale frames cleared when switching away from camera
- **Correct front camera orientation** - Front camera shows normal view (not mirrored)

#### Modified Files

- `main.py` - Moved status bars from gmeter to application level
  - Status bars now update on ALL pages, not just G-meter
  - Fixed status bar update logic (was only updating on gmeter page)
  - Added OBD2 MAP-based SOC with dynamic color zones
- `gui/gmeter.py` - Removed status bar code (moved to main.py)
  - Removed status bar initialization and rendering
  - Removed set_soc() and set_lap_delta() methods
- `hardware/obd2_handler.py` - Enhanced for SOC simulation
  - Added MAP (manifold absolute pressure) reading via PID 0x0B
  - Implemented direct MAP-to-SOC conversion (instant updates)
  - Reduced MAP history window from 10 to 3 samples for faster response
  - Fixed state calculation (increasing MAP = discharging, decreasing MAP = charging)
- `gui/camera.py` - Camera improvements
  - Clear last frame when stopping camera (prevents stale frame flash)
  - Conditional horizontal flip (rear camera only, not front)
- `ui/widgets/horizontal_bar.py` - Status bar widgets (no changes, used by main.py)

#### Configuration

**OBD2 Settings** (in `utils/config.py`):
```python
OBD_ENABLED = True              # Enable OBD2 speed and MAP reading
OBD_CHANNEL = "can_b2_1"        # CAN channel for OBD2 data
OBD_BITRATE = 500000            # Standard OBD2 bitrate (500 kbps)
```

**Status Bar Settings** (in `utils/config.py`):
```python
STATUS_BAR_ENABLED = True       # Show status bars at top and bottom
STATUS_BAR_HEIGHT = 20          # Height of status bars in pixels
```

#### Architecture

**Status Bars**
- **Top Bar**: Lap time delta (simulated for testing)
  - Green = faster than reference lap
  - Red = slower than reference lap
  - ⚪ Grey = same pace
- **Bottom Bar**: Battery State of Charge
  - Blue = idle (steady throttle)
  - Green = charging (throttle decreasing, MAP down, SOC up)
  - Red = discharging (throttle increasing, MAP up, SOC down)

**MAP-to-SOC Mapping**
```python
# Direct mapping (instant updates)
MAP 20 kPa  → 100% SOC (minimum throttle)
MAP 30 kPa  → 87% SOC  (idle)
MAP 60 kPa  → 50% SOC  (moderate throttle)
MAP 100 kPa → 0% SOC   (wide open throttle)
```

**State Detection**
- Uses 3-sample rolling window for rate-of-change
- Threshold: ±0.3 kPa/reading for idle detection
- At 5Hz polling (200ms), 3 samples = 600ms averaging window

**Camera Behavior**
- **Rear camera**: Horizontally flipped (mirrored) for backing up
- **Front camera**: Normal view (not flipped) for road ahead
- **Frame clearing**: Last frame cleared when switching away from camera

#### Bug Fixes

- **Status bars only updating on gmeter page** - Fixed by moving update logic outside page conditional
- **Slow SOC updates** - Changed from rate-of-change to direct mapping (instant response)
- **Incorrect SOC color states** - Fixed state calculation (MAP increasing = discharging = red)
- **Stale camera frame on reactivation** - Clear frame buffer when stopping camera
- **Front camera mirrored** - Only flip rear camera, not front

#### 🧪 Testing

-Status bars visible on all pages (telemetry, gmeter, camera)
-SOC updates instantly when MAP changes
-Colors correct (green=charging, red=discharging, blue=idle)
-Camera doesn't show stale frame after switching back
-Front camera shows normal view (not mirrored)
-Rear camera remains mirrored for backing up

#### 🎯 Use Cases

**Desk Testing**
- Connect to vehicle OBD2 port without driving
- Rev engine to see SOC bar change color instantly
- Idle: Blue bar at ~87% SOC
- Throttle up: Red bar, SOC decreases
- Throttle down: Green bar, SOC increases

**In-Vehicle Use** (future)
- Ford Hybrid SOC will replace simulated MAP-based SOC
- Same status bar interface, different data source
- Seamless transition from development to production

---

## [v0.8] - 2025-11-19

### Multi-Camera Support

#### New Features
- **Dual USB camera support** - Seamless switching between rear and front cameras
- **Deterministic camera identification** - Udev rules for consistent device naming across reboots
- **Smooth camera transitions** - No checkerboard flash during switching, freeze-frame transition
- **Proper resource management** - Only one camera initialized at a time to prevent conflicts
- **Dual FPS counters** - Shows both camera feed FPS and overall system FPS
- **Radar overlay on rear camera only** - Front camera displays clean video feed

#### 📦 New Files

```
config/
└── camera/
    └── 99-camera-names.rules      # Udev rules for persistent camera naming
```

#### Modified Files

- `gui/camera.py` - Complete rewrite of camera switching logic
  - Added proper camera release before switching
  - Implemented freeze-frame transition to prevent checkerboard
  - Fixed test pattern override during transitions
  - Removed symlink resolution (use symlinks directly)
- `utils/config.py` - Added multi-camera configuration settings
- `README.md` - Added comprehensive multi-camera setup documentation
- `install.sh` - Added automatic camera udev rules installation
- `CHANGELOG.md` - This entry

#### Configuration

**Multi-Camera Settings** (in `utils/config.py`):
```python
# Multi-camera configuration
CAMERA_REAR_ENABLED = True   # Rear camera (with radar overlay if radar enabled)
CAMERA_FRONT_ENABLED = True  # Front camera (no radar overlay)

# Camera device paths (if using udev rules for persistent naming)
CAMERA_REAR_DEVICE = "/dev/video-rear"   # or None for auto-detect
CAMERA_FRONT_DEVICE = "/dev/video-front"  # or None for auto-detect
```

**Udev Rules** (`config/camera/99-camera-names.rules`):
```bash
# Camera on USB port 1.1 = Rear camera
SUBSYSTEM=="video4linux", KERNELS=="1-1.1", ATTR{index}=="0", SYMLINK+="video-rear"

# Camera on USB port 1.2 = Front camera
SUBSYSTEM=="video4linux", KERNELS=="1-1.2", ATTR{index}=="0", SYMLINK+="video-front"
```

#### Installation

The `install.sh` script now automatically installs camera udev rules:
```bash
sudo ./install.sh
```

For manual installation:
```bash
sudo cp config/camera/99-camera-names.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Verify symlinks:
```bash
ls -l /dev/video-*
# Should show:
# /dev/video-rear -> video0
# /dev/video-front -> video3
```

#### Bug Fixes

- **Fixed checkerboard during camera switching** - Implemented freeze-frame transition
- **Fixed resource conflicts** - Properly release old camera before initializing new one
- **Fixed test pattern override** - Only generate test pattern if no frame exists
- **Fixed deterministic identification** - Use udev symlinks directly without resolving to device paths

#### Architecture

**Camera Switching Flow**
1. Save last frame for smooth transition
2. Stop current camera capture thread
3. Release old camera device
4. Switch to new camera
5. Restore saved frame (prevents checkerboard)
6. Initialize new camera
7. Start capture thread for new camera

**USB Port Assignment**
- Rear camera → USB port 1.1 (creates `/dev/video-rear`)
- Front camera → USB port 1.2 (creates `/dev/video-front`)

Common USB port mappings on Raspberry Pi 4:
- `1-1.1` = Top-left USB 2.0 port
- `1-1.2` = Bottom-left USB 2.0 port
- `1-1.3` = Top-right USB 2.0 port
- `1-1.4` = Bottom-right USB 2.0 port

#### 🧪 Testing

-Both cameras initialize correctly
-Camera switching works in all directions (telemetry ↔ rear ↔ front)
-No checkerboard flash during transitions
-Deterministic identification survives reboots
-Radar overlay only appears on rear camera
-Dual FPS counters display correctly
-Resource management prevents conflicts

#### 🎯 Controls

- **Button 2** (or **Spacebar**): Cycle through views
  - Telemetry → Rear Camera → Front Camera → Telemetry
- Camera switching is seamless with smooth freeze-frame transitions
- FPS counters show camera feed performance

---

## [v0.7] - 2025-11-13

### Radar Overlay Integration

#### New Features
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

#### Modified Files

- `main.py` - Added radar handler initialization and cleanup
- `gui/camera.py` - Integrated radar overlay rendering
- `utils/config.py` - Added comprehensive radar configuration section

#### Configuration

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

#### Architecture

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

-Camera initializes correctly with `radar_handler=None`
-Radar handler gracefully disables when hardware unavailable
-`get_tracks()` returns empty dict when disabled
-Camera doesn't create overlay when radar disabled
-Configuration defaults are safe (RADAR_ENABLED = False)
-Integration tested on Mac and Pi

#### 📝 Dependencies (Optional)

For radar support:
```bash
pip3 install python-can cantools
```

Copy `toyota_radar_driver.py` from `scratch/sources/toyota-radar/` or install as package.

---

## [v0.6] - 2025-11-12

### Major Performance Refactoring

#### Fixed
- **NameError in TPMS handler** - Fixed `TirePosition` being used before TPMS library check
- **Infinite recursion in MLXHandler** - Fixed backwards compatibility wrapper
- **British English throughout** - Changed all "Tire" → "Tyre", "Optimized" → "Optimised", "Initialize" → "Initialise"

#### Performance Optimisations Added

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
- **Performance**: < 1 ms/frame/sensor

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

# Installation and requirements
install.sh                     # Raspberry Pi installation script
requirements.txt               # Python dependencies

# Documentation
DEPLOYMENT.md                  # Deployment guide
```

#### Modified Files

- `main.py` - Integrated optimised handlers with performance monitoring
- All optimised handlers use British English spelling

#### Configuration

**Automatic Fallback**
- System tries optimised handlers first
- Falls back to original handlers if import fails
- Graceful degradation without hardware

**Dependencies (Optional)**
- `numba` - JIT compilation for thermal processing (10x speed improvement)
- Install with: `pip3 install numba`

#### Performance Targets (from System Plan)

| Component | Target | Status |
|-----------|--------|--------|
| Render loop | ≤ 12 ms/frame | Done |
| Thermal zones | < 1 ms/sensor | Done |
| Lock-free access | < 0.1 ms | Done |
| FPS | 30-60 FPS | Done |

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
# SSH to Pi and pull latest changes
ssh pi@raspberrypi.local
cd /home/pi/open-TPT
git pull
sudo ./install.sh  # If dependencies changed
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

**Status**: Deployed and tested on Pi

### Pi Hardware Status
-TPMS: 4/4 sensors auto-paired (FL, FR, RL, RR)
-NeoKey 1x4: Working (brightness, camera toggle, UI toggle)
- MLX90640: 1/4 cameras connected (FL operational)
- ADS1115: Not detected (brake temps unavailable)
- Radar: Not configured (RADAR_ENABLED = False by default)
