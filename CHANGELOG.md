# Changelog - openTPT

## [v0.19.9] - 2026-01-21

### USB-Based Persistent Storage

All persistent data now stored on USB drive for read-only rootfs robustness. Protects against SD card corruption from random power loss.

#### Storage Locations

| Data | USB Path |
|------|----------|
| Settings | `/mnt/usb/.opentpt/settings.json` |
| Lap times | `/mnt/usb/.opentpt/lap_timing/lap_timing.db` |
| Pit waypoints | `/mnt/usb/.opentpt/pit_timer/pit_waypoints.db` |
| CoPilot cache | `/mnt/usb/.opentpt/copilot/cache/` |
| CoPilot maps | `/mnt/usb/.opentpt/copilot/maps/` (always USB) |

#### Startup Warning

If USB is not mounted at boot:
- Yellow warning on splash: "NO USB - Settings will not persist"
- Log warning with fallback path
- Falls back to `~/.opentpt/` (won't persist on read-only rootfs)

#### Modified Files

- `config.py` - Added USB_MOUNT_PATH, DATA_DIR, get_data_dir(), is_usb_storage_available()
- `core/initialization.py` - USB warning on splash, storage location logging
- `utils/settings.py` - Uses DATA_DIR from config
- `utils/lap_timing_store.py` - Uses LAP_TIMING_DATA_DIR from config

---

## [v0.19.8] - 2026-01-21

### OLED Fuel Display: Range When No Track

The OLED fuel page now shows estimated range (km) instead of laps remaining when no track is selected. This provides useful information during road driving or when a track hasn't been loaded yet.

- **Track selected:** Shows "5.2 laps" (existing behaviour)
- **No track:** Shows "125km" estimated range

Modified: `hardware/oled_bonnet_handler.py` - `_render_fuel()` checks for track and displays range accordingly

---

### Shift Light RPM Thresholds in Menu

Added user-configurable RPM thresholds for the NeoDriver shift light to the Thresholds menu.

#### New Menu Items

**Thresholds > Shift Light:**
- **Start RPM** - RPM at which lights begin illuminating (default: 3000, range: 1000-8000, step: 100)
- **Shift RPM** - RPM at which redline flash activates (default: 6500, range: 2000-10000, step: 100)
- **Max RPM** - Maximum RPM for the shift light scale (default: 7000, range: 3000-12000, step: 100)

#### Features

- **Live preview** - Shift light updates immediately as values are adjusted
- **Persistent settings** - Values saved to `thresholds.shift.start`, `thresholds.shift.light`, `thresholds.shift.max`
- **Boot-time loading** - NeoDriver initialises with user settings instead of config defaults

#### Modified Files

- `config.py` - Bumped APP_VERSION to 0.19.8
- `gui/menu/base.py` - Added shift light threshold definitions, submenu, and parent assignment
- `gui/menu/settings.py` - Added live NeoDriver update when shift thresholds change
- `core/initialization.py` - NeoDriver loads RPM settings from user preferences

---

## [v0.19.7] - 2026-01-21

### In-Car Test Fixes

First in-car test revealed several issues that are now fixed.

#### Bug Fixes

- **Ford Hybrid SOC bar not showing data** - Added missing configuration constants (`FORD_HYBRID_ENABLED`, `FORD_HYBRID_CHANNEL`, `FORD_HYBRID_BITRATE`, `FORD_HYBRID_POLL_INTERVAL_S`, `FORD_HYBRID_SEND_TIMEOUT_S`) to `config.py`. The handler was importing these but they didn't exist.

- **CoPilot stuck on 'no path found'** - Increased heading tolerance from 30 to 45 degrees and search radius from 100m to 150m. Added fallback to find nearest road (within 30m) when no heading-aligned road is found. This handles cases where GPS heading is unreliable at low speeds.

- **Lap timer "Failed to load" track** - `select_track_by_name()` now falls back to searching the full track database when the track isn't found in nearby tracks (which requires GPS proximity). Previously only worked if you were physically near the track.

- **Fuel level jumping causing garbage estimates** - Implemented proper fuel smoothing for motorsport use:
  - Increased smoothing samples from 5 to 30 (now ~4.5 seconds of data at OBD2 poll rate)
  - Added median filter option (enabled by default) which is better at rejecting outliers from fuel slosh
  - Added minimum distance requirement (5km) before calculating range estimates

#### New Features

- **Version number on splash screen** - Application version now displays in the top-right corner of the splash screen during boot. This allows visual confirmation that USB patches have been applied.

- **USB log sync** - New service to export openTPT logs to USB drive for offline review:
  - Automatic full sync on shutdown/reboot
  - Incremental sync every 30 seconds (only new log entries appended)
  - Daily log files: `/mnt/usb/logs/opentpt_YYYYMMDD.log`
  - Keeps last 7 days of logs, auto-cleans older ones
  - Enable with: `sudo systemctl enable usb-log-sync.service` (shutdown sync)
  - Enable periodic: `sudo systemctl enable usb-log-sync.timer` (30s incremental)

#### New Configuration Constants

| Constant | Default | Purpose |
|----------|---------|---------|
| `APP_VERSION` | `"0.19.7"` | Application version displayed on splash |
| `FORD_HYBRID_ENABLED` | `True` | Enable Ford Hybrid CAN handler |
| `FORD_HYBRID_CHANNEL` | `can_b2_1` | CAN channel (same as OBD2) |
| `FORD_HYBRID_BITRATE` | `500000` | CAN bitrate |
| `FORD_HYBRID_POLL_INTERVAL_S` | `0.2` | PID query interval |
| `FORD_HYBRID_SEND_TIMEOUT_S` | `0.05` | CAN send timeout |
| `COPILOT_ROAD_SEARCH_RADIUS_M` | `150` | Max distance to search for current road |
| `FUEL_USE_MEDIAN_FILTER` | `True` | Use median filter for fuel smoothing |
| `FUEL_MIN_DISTANCE_FOR_ESTIMATE_KM` | `5.0` | Min distance before range estimates |

#### Modified Files

- `config.py` - Added APP_VERSION, Ford Hybrid config section, CoPilot search radius, fuel smoothing options
- `core/initialization.py` - Display version on splash screen
- `copilot/path_projector.py` - Configurable search radius, fallback road finding
- `hardware/lap_timing_handler.py` - Fallback to full database search for tracks
- `utils/fuel_tracker.py` - Median filter, minimum distance check
- `install.sh` - Install USB log sync service
- `services/logging/usb-log-sync.sh` - Log export script
- `services/logging/usb-log-sync.service` - Shutdown sync service
- `services/logging/usb-log-sync.timer` - Periodic sync timer
- `services/logging/usb-log-sync-periodic.service` - Periodic sync service

---

## [v0.19.6] - 2026-01-21

### Config Scaffolding for CAN Corner Sensors

Added configuration foundation for future CAN-based corner sensors. The `can_b2_0` channel (previously allocated to Ford Hybrid, which uses HS-CAN via OBD2) is now designated for corner sensor CAN bus.

#### New Configuration Constants

| Constant | Default | Purpose |
|----------|---------|---------|
| `CORNER_SENSOR_CAN_ENABLED` | `False` | Master enable for CAN corner sensors |
| `CORNER_SENSOR_CAN_CHANNEL` | `can_b2_0` | CAN interface (Board 2, CAN_0) |
| `CORNER_SENSOR_CAN_BITRATE` | `500000` | Standard 500 kbps |
| `CORNER_SENSOR_CAN_IDS` | `0x100-0x103` | Tyre temp message IDs (FL/FR/RL/RR) |
| `CORNER_SENSOR_CAN_BRAKE_IDS` | `0x110-0x113` | Brake temp message IDs |
| `CORNER_SENSOR_CAN_TIMEOUT_S` | `0.5` | Stale data timeout |

#### CAN Message Format (8 bytes)

**Tyre temps (0x100-0x103):**
- Bytes 0-1: Left temp (int16, tenths C, big-endian)
- Bytes 2-3: Centre temp (int16, tenths C, big-endian)
- Bytes 4-5: Right temp (int16, tenths C, big-endian)
- Byte 6: Confidence (0-100%)
- Byte 7: Flags (bit 0: tyre detected)

**Brake temps (0x110-0x113):**
- Bytes 0-1: Inner temp (int16, tenths C, big-endian)
- Bytes 2-3: Outer temp (int16, tenths C, big-endian)
- Bytes 4-7: Reserved

#### Modified Files

- `config.py` - New CORNER_SENSOR_CAN_* section, updated section list
- `hardware/unified_corner_handler.py` - Added TODO for CAN implementation
- `CLAUDE.md` - Updated CAN bus section reference

---

## [v0.19.5] - 2026-01-21

### Bug Fixes

- **Fix null check for camera in reverse-gear auto-switch** - Added guard to prevent `AttributeError` if camera handler failed to initialise when OBD2 detects reverse gear (`main.py:435`)

---

## [v0.19.4] - 2026-01-20

### VBOX-Style OLED Pages

Added 7 new OLED Bonnet display pages inspired by VBOX OLED Display DSP07-L modes.

#### New Pages

| Page | Description | Button Action |
|------|-------------|---------------|
| **Speed** | Large GPS speed with fix indicator | None |
| **Max Speed** | Session max speed tracking | Select = reset max |
| **Lap Timing** | Lap number, current/last/best times | None |
| **Lap Count** | Large lap number with session total | None |
| **Predictive** | Delta bar with predicted finish time | None |
| **Longitudinal G** | Accel/brake G-force with bar and peak | Select = reset peaks |
| **Lateral G** | Cornering G-force with bar and peak | Select = reset peaks |

#### Layout Consistency

All new pages follow the existing fuel/delta layout pattern:
- Line 1: Bar/value display
- Line 2: Labels and secondary data

#### Modified Files

- `config.py` - Added 7 new entries to `OLED_PAGES`
- `hardware/oled_bonnet_handler.py` - Extended enum, added GPS/IMU handlers, 7 render methods, button actions
- `core/initialization.py` - Wire GPS and IMU handlers to OLED Bonnet
- `gui/menu/oled.py` - Added mode names and 14 toggle methods for new pages

---

## [v0.19.3] - 2026-01-20

### Tyre Temps Menu

New menu under System > Tyre Temps for tyre temperature sensor configuration and diagnostics.

#### New Features

- **Per-corner submenus** (FL, FR, RL, RR) with sensor status display
- **Full Frame View** - 24×32 thermal heatmap modal for installation verification
  - Auto-ranging colour map (blue→cyan→green→yellow→red)
  - Shows min/avg/max temperature stats
  - 5-second timeout or encoder click to close
  - Uses Pico register 0x51 with i2c_rdwr block transfer
  - Validates data range, retries up to 3 times if invalid
- **Flip Inner/Outer** - Per-corner toggle to swap left/right zone interpretation
  - Persisted to settings (`tyre_temps.flip.{FL,FR,RL,RR}`)
  - Applies to zone data, thermal array, and full frame view
  - Useful when sensor mounted in opposite orientation

#### New Files

- `gui/menu/tyre_temps.py` - TyreTempsMenuMixin with all menu functionality

#### Modified Files

- `config.py` - Added `TYRE_FLIP_INNER_OUTER_DEFAULT`
- `hardware/unified_corner_handler.py` - Added `get_sensor_info()`, `read_full_frame()`, flip support in `get_zone_data()`
- `gui/menu/base.py` - Imported mixin, added to MenuSystem class, built submenu structure
- `core/initialization.py` - Pass `corner_sensors` to MenuSystem
- `CLAUDE.md` - Added 0x51 register documentation, tyre_temps.py to structure
- `README.md` - Ticked off tyre temps menu TODO

---

## [v0.19.2] - 2026-01-20

### Remove TOF Sensor Support

Removed all VL53L0X TOF (Time-of-Flight) distance sensor code. The sensors were unreliable for ride height measurement due to vibration and surface reflectivity issues in motorsport environments.

#### Removed

- TOF distance display on telemetry page
- TOF sensor initialisation, reading, and reinitialisation logic
- TOF-specific exponential backoff and history tracking
- `TOF_ENABLED`, `TOF_SENSOR_ENABLED`, `TOF_MUX_CHANNELS` configuration
- `TOF_DISPLAY_POSITIONS`, `TOF_DISTANCE_*` threshold constants
- `TOF_HISTORY_WINDOW_S`, `TOF_HISTORY_SAMPLES` configuration
- `get_tof_distance()`, `get_tof_distances()`, `get_tof_min_distance()` API methods
- `draw_tof_distance()`, `_get_tof_colour()` display methods
- VL53L0X from I2C address documentation

#### Modified Files

- `config.py` - Removed all TOF constants and configuration
- `hardware/unified_corner_handler.py` - Removed TOF sensor handling, simplified to two-queue architecture
- `core/rendering.py` - Removed TOF rendering block
- `gui/display.py` - Removed TOF display methods
- `main.py` - Removed TOF cache
- `CLAUDE.md` - Updated documentation to remove TOF references

---

## [v0.19.1] - 2026-01-20

### Thread Safety and Resource Management Fixes

Addresses 9 critical and high priority issues related to thread safety, resource management, and error recovery.

#### Critical Fixes

- **Camera frame access race** (`gui/camera.py`) - `render()` now captures `self.frame` into local variable atomically to prevent race with capture thread
- **Camera resource leak** (`gui/camera.py`) - `_stop_capture_thread()` returns bool; `switch_camera()` only releases camera if thread actually stopped
- **OBD2 dict access race** (`hardware/obd2_handler.py`) - `get_data()` returns empty dict instead of iterating `self.current_data` during concurrent modification
- **GPS serial port leak** (`hardware/gps_handler.py`) - `_initialise()` ensures serial port is closed in except block if opened before failure
- **UnifiedCornerHandler thread sync** (`hardware/unified_corner_handler.py`) - Replaced three `deque(maxlen=2)` with `queue.Queue(maxsize=2)` and atomic snapshot references for lock-free consumer access
- **Main loop crash recovery** (`main.py`) - Added inner try-except that recovers from pygame/IO errors up to 5 times before exiting

#### High Priority Fixes

- **Settings temp file cleanup** (`utils/settings.py`) - `_save()` cleans up temp file if `os.replace()` fails
- **GPS time validation** (`hardware/gps_handler.py`) - `_sync_system_time()` validates year is 2024-2030 before syncing system time
- **TOF init timeout** (`hardware/unified_corner_handler.py`) - VL53L0X constructor and range access wrapped in `_i2c_with_timeout()` to prevent indefinite blocking

#### Modified Files

- `gui/camera.py` - Frame access race fix, camera resource leak fix
- `hardware/unified_corner_handler.py` - Thread-safe queues, atomic snapshots, TOF timeout
- `hardware/gps_handler.py` - Serial port leak fix, time validation
- `hardware/obd2_handler.py` - Dict access race fix
- `utils/settings.py` - Temp file cleanup
- `main.py` - Crash recovery with counter

---

## [v0.19.0] - 2026-01-20

### Pit Lane Timer

VBOX-style pit lane timer with GPS-based entry/exit detection, countdown timing, and speed monitoring.

#### Features

- **Two timing modes**: Entrance-to-Exit (total pit time) vs Stationary-only (box time)
- **GPS waypoint marking**: Button press records pit entry/exit lines perpendicular to heading
- **Crossing detection**: Uses cross-product algorithm (same as lap timing S/F line)
- **Countdown timer**: Configurable minimum stop time with visual countdown
- **Speed monitoring**: Warning when approaching limit, violation tracking
- **Per-track storage**: Pit waypoints and session history saved per track in SQLite
- **State machine**: ON_TRACK -> IN_PIT_LANE -> STATIONARY -> ON_TRACK

#### OLED Bonnet Integration

- New PIT mode added to OLED page rotation
- Button actions when PIT page selected:
  - Prev (<): Mark entry line at current GPS position
  - Next (>): Mark exit line at current GPS position
  - Select: Toggle timing mode

#### Main GUI Page

- Large timer display with colour-coded states (grey/orange/blue/green/red)
- Speed bar with warning zone indicator
- GO/WAIT indicators for countdown
- Track name, waypoint status, mode, and last pit time display

#### New Files

- `hardware/pit_timer_handler.py` - Core handler with state machine and GPS crossing detection
- `utils/pit_lane_store.py` - SQLite persistence for pit waypoints and session history
- `gui/pit_timer_display.py` - Main GUI page with timer, speed bar, countdown
- `gui/menu/pit_timer.py` - Menu mixin for pit timer settings

#### Modified Files

- `config.py` - Added PIT_TIMER_* constants (section 13), pit_timer to UI_PAGES
- `hardware/oled_bonnet_handler.py` - Added PIT mode, _render_pit(), button actions
- `core/initialization.py` - Pit timer handler initialisation and wiring
- `core/rendering.py` - Added pit_timer page rendering case
- `main.py` - PitTimerDisplay import/instantiation, cleanup
- `gui/menu/base.py` - PitTimerMenuMixin, pit_timer_handler param, Pit Timer submenu
- `CLAUDE.md` - Directory structure, Pit Timer documentation

#### Configuration

New constants in `config.py`:
- `PIT_TIMER_ENABLED` - Enable/disable pit timer (default: True)
- `PIT_SPEED_LIMIT_DEFAULT_KMH` - Default speed limit (default: 60)
- `PIT_SPEED_WARNING_MARGIN_KMH` - Warning margin (default: 5)
- `PIT_TIMER_DEFAULT_MODE` - Default timing mode (default: "entrance_to_exit")
- `PIT_LINE_WIDTH_M` - Crossing line width in metres (default: 15)
- `PIT_STATIONARY_SPEED_KMH` - Stationary threshold (default: 2)
- `PIT_STATIONARY_DURATION_S` - Stationary detection time (default: 1)
- `PIT_MIN_STOP_TIME_DEFAULT_S` - Countdown target (default: 0)
- `PIT_TIMER_DATA_DIR` - SQLite database location

#### Menu Settings

Track & Timing > Pit Timer submenu provides:
- Enable/disable pit timer
- Mark entry/exit lines
- Toggle timing mode
- Adjust speed limit (+/- 5 km/h)
- Adjust minimum stop time (+/- 5s)
- Clear waypoints
- View current track and last pit time

---

## [v0.18.15] - 2026-01-20

### OLED Bonnet Button Support

Added MCP23017 GPIO expander support for physical button control of the OLED Bonnet display.

#### Features

- **3-button navigation**: Prev (A0), Select (A1), Next (A2) via MCP23017 at 0x20
- **Page cycling**: Prev/next buttons manually cycle between Fuel and Delta pages
- **Selection mode**: Hold select (500ms) to enter "selected" mode, pausing auto-cycle
- **Page-specific actions**: When selected, buttons reserved for future page interactions (e.g., pit timer)
- **Visual indicator**: Small dot in top-right corner when page is selected
- **Configurable**: Address, pins, hold time, debounce all configurable via config.py

#### I2C Bus Speed

Reduced I2C bus speed from 1MHz to 400kHz for improved reliability in motorsport EMI environment. Data throughput is only ~2.7 KB/s (7% capacity), so faster speeds provide no benefit while reducing noise margin.

#### Modified Files

- `config.py` - Added MCP23017 button configuration constants
- `hardware/oled_bonnet_handler.py` - Button polling, navigation, page actions
- `core/initialization.py` - Wire up MCP23017 config to handler
- `CLAUDE.md` - Added MCP23017 to I2C address table, bus speed documentation
- `DEPLOYMENT.md` - Added I2C bus speed configuration
- `install.sh` - Added adafruit-circuitpython-mcp230xx dependency

---

## [v0.18.14] - 2026-01-20

### USB Patch Deployment

Added boot-time USB patch system for updating openTPT on a vehicle-mounted Pi without network access.

#### Features

- **Boot-time patching**: Checks `/mnt/usb` for patch archive before hardware initialisation
- **Archive formats**: Supports both `.tar.gz` and `.zip` formats
- **Auto-rename**: Archives renamed after application to prevent re-extraction on subsequent boots
- **Logging**: All patch operations logged to `~/.opentpt/patch.log`
- **Integrity check**: Archives verified before extraction (corrupt archives skipped)

#### Boot Sequence

```
Power On -> [sysinit.target] -> [usb-patch.service] -> [splash.service] -> [openTPT.service]
```

#### Creating Patches

```bash
# Patch specific files
tar -czvf opentpt-patch.tar.gz main.py hardware/gps_handler.py

# Patch entire directory
tar -czvf opentpt-patch.tar.gz hardware/

# Using zip
zip -r opentpt-patch.zip main.py config.py gui/
```

#### New Files

- `services/patch/usb-patch.sh` - Boot script for USB patch extraction
- `services/patch/usb-patch.service` - Systemd service unit

#### Modified Files

- `openTPT.service` - Added `usb-patch.service` to After directive
- `install.sh` - Added USB patch service installation
- `CLAUDE.md` - Added USB Patch Deployment subsystem reference
- `QUICKSTART.md` - Added USB patch deployment workflow

---

## [v0.18.13] - 2026-01-19

### OLED Bonnet Handler

Added support for Adafruit 128x32 OLED Bonnet (SSD1306) as secondary display for fuel and lap delta information.

#### Features

- **Two display modes**: Fuel (level bar, laps remaining, litres) and Delta (delta bar, last/best lap times)
- **Auto-cycle**: Cycles between modes every 10 seconds (configurable)
- **Splash screen**: Shows "Skjord Motorsport" on startup/shutdown (5 seconds)
- **Menu integration**: System > OLED Display submenu for mode/auto-cycle control
- **Late binding**: Connects to lap_timing and fuel_tracker after initialisation
- **Mock mode**: Runs without hardware for `--windowed` testing

#### Configuration (config.py)

- `OLED_BONNET_ENABLED` - Enable/disable (currently False - hardware damaged)
- `OLED_BONNET_I2C_ADDRESS` - Default 0x3C
- `OLED_BONNET_DEFAULT_MODE` - "fuel" or "delta"
- `OLED_BONNET_AUTO_CYCLE` - Toggle auto-cycling
- `OLED_BONNET_CYCLE_INTERVAL` - Seconds between mode changes

#### New Files

- `hardware/oled_bonnet_handler.py` - OLED handler with threading model
- `gui/menu/oled.py` - Menu mixin for OLED settings

#### Modified Files

- `config.py` - Added OLED configuration section
- `core/initialization.py` - OLED handler initialisation and integration
- `gui/menu/base.py` - Added OLEDMenuMixin and OLED Display submenu

#### TODO

- Pitlane timer mode for minidisplay

### Corner Detection Integration

Fixed broken corner detection integration from the standalone lap-timing-system import.

#### What Was Missing

- Corner detection not called when tracks loaded
- CornerAnalyzer not initialised
- Lap positions not tracked during GPS processing
- Lap.positions field not populated on lap completion
- Corner analysis not called on lap completion

#### Fixes Applied

- Added `LAP_TIMING_CORNER_*` config settings for detector selection and tuning
- `_detect_corners()` method creates detector based on config (hybrid, asc, curvefinder, threshold)
- `set_track()` now detects corners after loading track
- `_process_gps_point()` tracks positions during lap (required for corner analysis)
- `_handle_lap_crossing()` populates `lap.positions`, calls `corner_analyzer.analyze_lap()`
- `_publish_state()` includes corner data in snapshot

#### Corner Analysis Output

- Corner speeds: min, entry, exit, average (m/s)
- G-forces: lateral and longitudinal
- Best corner speeds tracked across session
- Delta vs best available for each corner

#### Bug Fixes (Code Review)

- **Array sync fix**: GPS points and positions now only added when both valid, preventing index mismatch in corner analysis
- **ASCCornerDetector**: Removed incorrect `merge_same_direction` parameter mapping (was using chicane config for wrong purpose)
- **CurveFinderDetector**: Now respects `LAP_TIMING_CORNER_MIN_RADIUS_M` and `LAP_TIMING_CORNER_MIN_ANGLE_DEG` config values

### Magic Number Consolidation

Moved all hardcoded values to config.py for easier tuning and consistency.

#### New Config Sections Added

**TPMS Thresholds:**
- `TPMS_HIGH_PRESSURE_KPA`, `TPMS_LOW_PRESSURE_KPA`, `TPMS_HIGH_TEMP_C`, `TPMS_DATA_TIMEOUT_S`

**I2C Timing Configuration:**
- `I2C_TIMEOUT_S`, `I2C_SETTLE_DELAY_S`, `I2C_MUX_RESET_PULSE_S`, `I2C_MUX_STABILISE_S`
- `I2C_BACKOFF_INITIAL_S`, `I2C_BACKOFF_MULTIPLIER`, `I2C_BACKOFF_MAX_S`
- `TOF_HISTORY_WINDOW_S`, `TOF_HISTORY_SAMPLES`

**OBD2 Timing and Smoothing:**
- `OBD_POLL_INTERVAL_S`, `OBD_RECONNECT_INTERVAL_S`, `OBD_SEND_TIMEOUT_S`
- `OBD_SPEED_SMOOTHING_SAMPLES`, `OBD_RPM_SMOOTHING_SAMPLES`, `OBD_THROTTLE_SMOOTHING_SAMPLES`

**Ford Hybrid Timing:**
- `FORD_HYBRID_POLL_INTERVAL_S`, `FORD_HYBRID_SEND_TIMEOUT_S`

**Radar Timing:**
- `RADAR_POLL_INTERVAL_S`, `RADAR_NOTIFIER_TIMEOUT_S`

**GPS Serial Timeouts:**
- `GPS_SERIAL_TIMEOUT_S`, `GPS_SERIAL_WRITE_TIMEOUT_S`, `GPS_COMMAND_TIMEOUT_S`

**Handler & Threading:**
- `HANDLER_QUEUE_DEPTH`, `HANDLER_STOP_TIMEOUT_S`
- `THREAD_JOIN_TIMEOUT_S`, `THREAD_SHUTDOWN_TIMEOUT_S`
- `IMU_RECONNECT_INTERVAL_S`, `NEODRIVER_UPDATE_RATE_HZ`, `NEODRIVER_STARTUP_DELAY_S`
- `PERFORMANCE_WARNING_HISTORY`

**Camera Settings:**
- `CAMERA_FOV_DEGREES`, `CAMERA_FPS_UPDATE_INTERVAL_S`

**UI Layout:**
- `MENU_ITEM_HEIGHT`, `SCALE_BAR_WIDTH`, `SCALE_BAR_HEIGHT`
- `CAR_ICON_WIDTH`, `CAR_ICON_HEIGHT`, `TEXT_CACHE_MAX_SIZE`, `INPUT_EVENT_QUEUE_SIZE`

**CoPilot Callout Distances:**
- `COPILOT_CORNER_CALLOUT_DISTANCES`, `COPILOT_MULTI_CALLOUT_DISTANCES`
- `COPILOT_DEFAULT_CALLOUT_DISTANCE_M`, `COPILOT_NOTE_MERGE_DISTANCE_M`
- `COPILOT_SIMULATION_FETCH_RADIUS_M`, `COPILOT_REFETCH_THRESHOLD_M`
- `COPILOT_CORNER_MIN_CUT_DISTANCE_M`, `COPILOT_CORNER_MAX_CHICANE_GAP_M`

#### Files Updated

**Hardware:**
- `hardware/tpms_input_optimized.py` - TPMS thresholds and timeout
- `hardware/unified_corner_handler.py` - I2C timing and backoff
- `hardware/obd2_handler.py` - OBD2 polling and smoothing
- `hardware/ford_hybrid_handler.py` - Ford Hybrid timing
- `hardware/radar_handler.py` - Radar polling
- `hardware/gps_handler.py` - GPS serial timeouts
- `hardware/neodriver_handler.py` - NeoDriver update rate
- `hardware/imu_handler.py` - IMU reconnect interval
- `utils/hardware_base.py` - Queue depth and stop timeout

**GUI:**
- `gui/camera.py` - Camera FOV and FPS interval
- `gui/menu/base.py` - Menu item height
- `gui/radar_overlay.py` - Text cache size
- `gui/input_threaded.py` - Event queue size
- `gui/encoder_input.py` - Event queue size

**CoPilot:**
- `copilot/pacenotes.py` - Callout distances and merge distance
- `copilot/main.py` - Corner detection params, simulation fetch radius
- `copilot/simulator.py` - Simulation fetch radius

### Config Reorganisation

Restructured config.py from 23 mixed sections into 12 clear categories for better maintainability.

#### New Structure

1. **Display & UI** - Resolution, colours, assets, scaling, layout
2. **Units & Thresholds** - Temperature, pressure, speed units and limits
3. **Hardware - I2C Bus** - Addresses, mux, timing, backoff
4. **Hardware - Sensors** - Tyre, brake, TOF, TPMS, IMU
5. **Hardware - Cameras** - Resolution, devices, transforms
6. **Hardware - Input Devices** - NeoKey, encoder, NeoDriver, OLED
7. **Hardware - CAN Bus** - OBD2, Ford Hybrid, Radar
8. **Hardware - GPS** - Serial, timeouts
9. **Features - Lap Timing** - Tracks, corners, sectors
10. **Features - Fuel Tracking** - Tank, thresholds
11. **Features - CoPilot** - Maps, callouts, audio
12. **Threading & Performance** - Queues, timeouts

#### Key Improvements

- Display scaling now at top with resolution (was buried after cameras)
- Temperature thresholds grouped together (tyre/brake were 100 lines apart)
- I2C timing/backoff clearly separated from device addresses
- Hardware vs Features distinction makes adding new modules easier
- Consistent numbered section headers throughout

---

### Config Cleanup

Removed standalone CLI code and consolidated configuration files into main config.py.

#### Changes

- **copilot/main.py**: Removed 130 lines of argparse CLI code (never used standalone)
- **copilot/config.py**: Deleted entirely, all settings moved to main config with COPILOT_ prefix
- **lap_timing/config.py**: Deleted, track paths moved to main config with LAP_TIMING_ prefix
- **config.py**: Added all COPILOT_ and LAP_TIMING_ configuration constants
- Updated copilot modules (audio.py, corners.py, main.py, pacenotes.py, path_projector.py) to import from main config

#### Consolidated CoPilot Settings (COPILOT_ prefix)

- Lookahead and navigation: `COPILOT_LOOKAHEAD_M`, `COPILOT_ROAD_FETCH_RADIUS_M`, `COPILOT_REFETCH_DISTANCE_M`, `COPILOT_UPDATE_INTERVAL_S`
- Corner detection (road-tuned): `COPILOT_CORNER_MIN_RADIUS_M`, `COPILOT_CORNER_MIN_ANGLE_DEG`
- Junction detection: `COPILOT_JUNCTION_WARN_DISTANCE_M`, `COPILOT_HEADING_TOLERANCE_DEG`
- Audio: `COPILOT_TTS_VOICE`, `COPILOT_TTS_SPEED`

#### Consolidated Lap Timing Settings (LAP_TIMING_ prefix)

- Track paths: `LAP_TIMING_TRACKS_DB`, `LAP_TIMING_RACELOGIC_DB`, `LAP_TIMING_CUSTOM_TRACKS_DIR`, `LAP_TIMING_RACELOGIC_TRACKS_DIR`

Note: CoPilot corner detection (`COPILOT_CORNER_*`) is tuned for road driving with larger radii. Lap timing uses separate track-optimised detection.

---

## [v0.18.12] - 2026-01-19

### Project Structure Reorganisation

Cleaner separation between Python configuration and Pi service files.

#### Changes

- **Moved `config.py` to root level** - Was `utils/config.py`, now `config.py`
  - Clearer project structure with configuration at top level
  - Updated all 34 Python imports from `from utils.config` to `from config`
  - Fixed `_PROJECT_ROOT` calculation (single dirname, not double)

- **Renamed `/config/` to `/services/`** - Contains Pi deployment files
  - `services/boot/` - Boot optimisation, splash service
  - `services/camera/` - Camera udev rules
  - `services/can/` - CAN bus udev rules
  - `services/gps/` - GPS config service
  - `services/systemd/` - CAN setup service

- **Updated CoPilot AVRCP metadata**
  - Artist: "CoPilot" → "Skjord Motorsport"
  - Album: "openTPT" → "CoPilot"

#### Modified Files

- `config.py` - Moved from utils/, fixed _PROJECT_ROOT
- `services/` - Renamed from config/
- `copilot/mpris.py` - Updated AVRCP artist/album
- 34 Python files - Updated imports
- Documentation - README, QUICKSTART, DEPLOYMENT, CLAUDE.md

---

## [v0.18.11] - 2026-01-19

### Camera Performance Optimisation

Comprehensive camera performance improvements, increasing frame rates significantly.

#### Changes

- **V4L2 Backend** - Explicitly specify `cv2.CAP_V4L2` backend for VideoCapture
  - OpenCV's default backend selection was slower than direct V4L2
  - Applied to main camera open and test camera detection

- **Removed BUFFERSIZE=1** - Was causing frame starvation
  - With slow processing (~20ms), BUFFERSIZE=1 forced waiting for each new frame
  - Default buffering allows reading already-captured frames immediately
  - Reduced grab() time from 45ms to 33ms

- **Skip No-Op Resize** - Avoid cv2.resize() when scale=1.0
  - At 800x600 camera on 1024x600 display, no scaling needed (letterboxed)
  - OpenCV still copied the array even with same dimensions, wasting 2.5ms

- **FOURCC Order** - Set MJPG format before resolution in init path
  - Some cameras need codec set first for proper resolution negotiation

- **Faster Render with frombuffer** - Replace direct pixel array copy with frombuffer+blit
  - 39% faster rendering (19ms → 12ms per frame)
  - tobytes: 2.1ms, frombuffer: 0.1ms, blit: 3.2ms, flip: 6.2ms

- **Increased FPS Targets** - Allow faster cameras to reach their potential
  - `CAMERA_FPS`: 30 → 60 (cameras deliver what they can)
  - `FPS_TARGET`: 30 → 60 (render loop cap)

#### Results

- Rear camera: **27fps** (was 15-16fps) - at hardware limit
- Front camera: **38fps** (was 15-16fps) - with 55fps-capable camera

#### Modified Files

- `gui/camera.py` - V4L2 backend, removed BUFFERSIZE, conditional resize, frombuffer render
- `utils/config.py` - CAMERA_FPS=60, FPS_TARGET=60

---

## [v0.18.10] - 2026-01-19

### Menu Restructure

Simplified the main menu from 10 top-level items to 4 focused items, moving "set and forget" options into System.

#### Changes

- **Simplified Menu Structure** - Reduced top-level items from 10 to 4:
  - **Track & Timing** - Select Track, Load Route, Current Track, Best Lap, Map Theme, Clear Best Laps, Clear Track
  - **CoPilot** - Enabled, Mode, Route, Lookahead, Audio, Status
  - **Thresholds** - Promoted to top level (Tyre Temps, Brake Temps, Pressures, Boost Range)
  - **System** - Consolidated all "set and forget" options

- **System Menu Reorganisation** - Grouped related settings into submenus:
  - Bluetooth Audio (moved to top per user request)
  - Display (Brightness + Pages submenu)
  - Cameras
  - Light Strip
  - Units
  - Status (GPS, Sensors, Radar, Network, Storage, Uptime)
  - Hardware (TPMS Pairing, IMU Calibration, Speed Source)
  - Reboot/Shutdown at bottom

- **Renamed Root Menu** - Changed title from "Settings" to "Menu"

#### Modified Files

- `gui/menu/base.py` - Rewrote `_build_menus()` with new 4-item structure
- `gui/menu/lap_timing.py` - Updated parent references to use `track_timing_menu`

---

## [v0.18.9] - 2026-01-19

### Code Quality Improvements

Minor fixes identified during code review to improve robustness and clarity.

#### Bug Fixes

- **Boost Bar Zero-Point Scaling** - Fixed DualDirectionBar to scale positive and negative values independently
  - Zero is now always at visual centre regardless of min/max range
  - Previously, asymmetric ranges (e.g. -15 to +25 PSI) placed zero at the wrong position
  - Fixes boost gauge showing 0 at ~11 PSI instead of atmospheric pressure

- **WiFi Dropout Fix** - Removed `wpa_supplicant` from disabled services in boot optimisation script
  - WiFi now remains enabled after boot optimisation
  - Existing installations: run `sudo systemctl unmask wpa_supplicant && sudo systemctl enable --now wpa_supplicant`

- **CoPilot Init Speed** - Reduced CoPilot map initialisation from ~15s to ~1s
  - Changed `get_bounds()` to query R-tree index instead of full nodes table scan
  - Added metadata caching for bounds (instant lookup on subsequent boots)
  - Backwards compatible with existing databases (auto-migrates schema)

- **Splash Service Fix** - Consolidated redundant splash services and added framebuffer wait
  - Removed `fbi-splash.service`, now using single `splash.service`
  - Added wait loop for `/dev/fb0` (up to 5 seconds) to handle early boot timing
  - Updated `openTPT.service` dependency

- **Defensive Dict Access** - Fixed potential KeyError in `unified_corner_handler.py` if snapshot format changes unexpectedly
  - `get_thermal_data()`, `get_zone_data()`, `get_temps()`, `get_tof_distances()` now use safe `.get()` pattern
  - Prevents render thread crashes from malformed snapshots

- **Clearer Integer Arithmetic** - Simplified SOC calculation in `obd2_handler.py` from `* (1 / 5) / 100` to `/ 500`

#### Documentation

- **Corrected Threading Comment** - Updated `unified_corner_handler.py` docstring to clarify queue publishes are "together" not "atomic"

#### Modified Files

- `gui/horizontal_bar.py` - Fixed zero-point scaling in DualDirectionBar
- `hardware/unified_corner_handler.py` - Safe dict access, corrected atomicity comment
- `hardware/obd2_handler.py` - Simplified SOC arithmetic
- `config/boot/optimize-boot.sh` - Keep wpa_supplicant enabled for WiFi
- `config/boot/splash.service` - Added framebuffer wait loop, consolidated from fbi-splash.service
- `copilot/sqlite_cache.py` - Fast bounds lookup via R-tree and metadata caching
- `openTPT.service` - Updated splash service dependency

---

## [v0.18.8] - 2026-01-18

### Boost Pressure Display and UI Improvements

Added boost pressure display on the status bar when no track/route is active, with configurable range and improved encoder behaviour.

#### New Features

- **Boost Pressure on Delta Bar** - When no track or route is active, the top status bar shows turbo boost/vacuum pressure instead of greyed-out delta time
  - Cyan bar for positive boost, grey for vacuum
  - Respects user's pressure unit setting (PSI, BAR, kPa)
  - Automatic switching between boost and delta modes based on track state

- **Configurable Boost Range** - Menu > System > Thresholds > Boost Range
  - Min (vacuum): -30 to 0 PSI (default -15)
  - Max (boost): 5 to 50 PSI (default 25)
  - Values stored in PSI, converted to user's preferred unit for display

- **High Priority Boost Polling** - MAP/Boost PID moved from low priority (~1Hz) to high priority (~7Hz) for responsive gauge updates

- **Reverse Camera Auto-Switch** - Automatically switches to rear camera when reverse gear detected (PID 0xA4), restores previous view when exiting reverse
  - Requires vehicle support for transmission gear PID (auto-disabled if unsupported)

- **USB Telemetry Storage** - Telemetry recordings now saved to USB drive (`/mnt/usb/telemetry`) if available, with automatic fallback to SD card

#### Performance Improvements

- **Reduced Frame Rate Target** - Lowered from 60 to 30 FPS (matches camera hardware limit), significantly reducing CPU usage
- **Explicit CPU Yield** - Added 1ms sleep after frame tick to prevent busy-waiting on Linux
- **Non-blocking CoPilot Enable** - CoPilot map loading now runs in background thread to prevent UI lockup

#### Bug Fixes

- **Encoder Long Press Consistency** - Long pressing the encoder when menu is open now always closes the menu entirely, rather than sometimes going back one level
- **Boost Range Menu Back Button** - Fixed missing parent assignment that prevented Back button from working
- **Menu Status Message Position** - Moved status messages up 10px to sit within the menu box

#### Modified Files

- `main.py` - Boost pressure display, reduced FPS target, reverse camera auto-switch
- `hardware/obd2_handler.py` - MAP/Boost high priority, gear PID 0xA4 for reverse detection
- `gui/camera.py` - Added switch_to() method for specific camera selection
- `gui/menu/base.py` - Boost range settings, status message positioning
- `gui/menu/copilot.py` - Background thread for CoPilot start
- `core/event_handlers.py` - Changed menu long press from back() to hide()
- `utils/config.py` - FPS_TARGET reduced to 30
- `utils/telemetry_recorder.py` - USB storage with SD card fallback

---

## [v0.18.7] - 2026-01-18

### Map Themes for Lap Timing Display

Added JSON-based theme support for the lap timing map view, allowing customisation of track colours and backgrounds. Dark themes adapted from [maptoposter](https://github.com/originalankur/maptoposter).

#### New Features

- **Map Theme System** - Five built-in dark themes selectable via menu:
  - Default - Dark motorsport style with white track
  - Noir - Pure black with white/grey roads
  - Midnight Blue - Deep navy with gold/copper accents
  - Blueprint - Architectural blueprint aesthetic
  - Neon Cyberpunk - Electric pink and cyan night city vibes

- **Theme Persistence** - Selected theme saved to settings and restored on restart
- **Immediate Theme Switching** - Theme changes apply instantly without restart

#### Menu Integration

- Menu > Lap Timing > Map Theme - Opens theme selection submenu
- Current theme shown in menu label
- Selected theme marked with asterisk in submenu

#### Theme Colours

Each theme controls:
- Background colour
- Track edge (primary road)
- Track surface (secondary road)
- Car marker
- Start/finish line
- Text colour

#### New Files

- `assets/themes/*.json` - Theme definition files (5 dark themes)
- `utils/theme_loader.py` - Theme loading and caching singleton
- `gui/menu/map_theme.py` - Map theme menu mixin

#### Modified Files

- `utils/config.py` - Added MAP_THEME_DEFAULT constant
- `gui/menu/base.py` - Added MapThemeMenuMixin and menu item
- `gui/lap_timing_display.py` - Theme loading and application

---

## [v0.18.6] - 2026-01-18

### Unit Test Framework

Added comprehensive pytest-based unit testing with GitHub Actions CI/CD integration.

#### Test Coverage (367 tests, 39% codebase coverage)

- **Conversions** (54 tests) - Temperature, pressure, display scaling, emissivity correction
- **Geometry** (31 tests) - Haversine distance, bearing, curvature, GPS calculations
- **Settings** (27 tests) - Dot-notation access, persistence, edge cases
- **Hardware Base** (30 tests) - Exponential backoff, bounded queues, snapshots
- **Fuel Tracker** (44 tests) - Consumption calculations, lap tracking, state management
- **GPS Parsing** (21 tests) - NMEA sentence parsing (RMC, GGA), checksum validation
- **OBD2 Parsing** (36 tests) - PID response parsing (speed, RPM, temps, fuel, MAP, MAF)
- **Corner Detection** (53 tests) - ASC algorithm, severity classification, chicane merging
- **Lap Timing Store** (25 tests) - SQLite persistence, best laps, reference laps, statistics
- **Pacenotes** (46 tests) - Rally callout generation, distance brackets, note merging

#### Module Coverage

| Module | Coverage |
|--------|----------|
| utils/config.py | 100% |
| copilot/geometry.py | 97% |
| utils/fuel_tracker.py | 93% |
| utils/hardware_base.py | 90% |
| utils/lap_timing_store.py | 88% |
| copilot/corners.py | 84% |
| utils/settings.py | 74% |
| copilot/pacenotes.py | 66% |

#### CI/CD Integration

- GitHub Actions workflow runs tests on push/PR to main
- Coverage reporting via Codecov
- Test and coverage badges added to README

#### New Files

- `tests/` - Test directory structure with conftest.py, fixtures
- `tests/unit/` - All unit test modules
- `tests/pytest.ini` - Pytest configuration
- `requirements-dev.txt` - Development dependencies (pytest, pytest-cov, pytest-mock)
- `.github/workflows/tests.yml` - GitHub Actions workflow
- `codecov.yml` - Codecov configuration

---

## [v0.18.5] - 2026-01-18

### Remaining High Priority Fixes

#### Thread Lifecycle and I2C Safety

- **Add lap_timing.stop() to cleanup** - Ensures lap timing worker thread stops gracefully
- **Add I2C timeout wrapper** - Prevents bus hangs from blocking worker thread indefinitely
  - Added `_i2c_with_timeout()` method using ThreadPoolExecutor
  - Wrapped smbus2 mux select and Pico sensor reads with 500ms timeout
  - Added I2C executor shutdown in stop() method

#### Thermal Data Memory

- **Verified no memory leak** - Queues already use `maxlen=2`, render caches limited to 4 positions

#### Modified Files

- `main.py` - Added lap_timing.stop() to cleanup sequence
- `hardware/unified_corner_handler.py` - Added I2C timeout wrapper and executor

---

## [v0.18.4] - 2026-01-18

### Critical and High Priority Bug Fixes

#### Thread Safety and Race Conditions

- **Fixed Bluetooth connection race condition** - `_bt_connecting` flag now protected by lock during check-and-set
- **Fixed boot timing race condition** - Added warning log if boot start time not set by main.py

#### Initialisation Safety

- **All optional handlers initialised to None** - Prevents AttributeError if init fails partway through
  - Added: `encoder`, `neodriver`, `obd2`, `gps`, `lap_timing`, `copilot`, `ford_hybrid`, `menu`
- **Status bar null check** - Now checks both `top_bar` and `bottom_bar` exist before rendering
- **CoPilot handler encapsulation** - Added `has_gpx_route` property; menu no longer accesses private attributes

#### Performance Improvements

- **Moved import outside render loop** - `COPILOT_OVERLAY_POSITION` now imported at module level in rendering.py
- **Bluetooth device list limits** - Connect, pair, and forget menus now limited to 20 devices max

#### New Features

- **Radar overlay toggle** - Button 1 on camera page now toggles radar overlay visibility
  - Added `toggle_overlay()` method to radar handler
  - Added `overlay_visible` property for runtime toggle
- **MenuItem error handling** - `get_label()` now catches exceptions from dynamic labels

#### Modified Files

- `main.py` - Optional handlers initialised to None
- `core/rendering.py` - Import moved to module level, status bar null check
- `core/event_handlers.py` - Radar overlay toggle implementation
- `core/initialization.py` - Boot timing warning
- `gui/menu/base.py` - MenuItem exception handling
- `gui/menu/bluetooth.py` - Race condition fix, device limits
- `gui/menu/copilot.py` - Use public properties instead of private attributes
- `gui/camera.py` - Check overlay_visible before rendering radar
- `hardware/radar_handler.py` - Added toggle_overlay(), overlay_visible
- `hardware/copilot_handler.py` - Added has_gpx_route property

---

## [v0.18.3] - 2026-01-17

### Main Application Refactoring

#### Code Organisation

- **Modular main application** - Split monolithic `main.py` (2063 lines) into focused modules
  - Each subsystem is now a separate mixin class for maintainability
  - main.py reduced to 569 lines (72% reduction)
  - Clear separation of concerns by functionality

#### New Structure

```
core/
├── __init__.py           # Exports all mixins
├── initialization.py     # Hardware subsystem init (~445 lines)
├── event_handlers.py     # Input/event processing (~261 lines)
├── rendering.py          # Display pipeline (~377 lines)
├── telemetry.py          # Telemetry recording (~148 lines)
└── performance.py        # Power/memory monitoring (~394 lines)
```

#### Architecture

- **Mixin pattern** - OpenTPT class inherits from all core mixins
  - `PerformanceMixin` - Power status, memory stats, periodic maintenance
  - `TelemetryMixin` - Telemetry frame recording
  - `EventHandlerMixin` - Pygame events, input handling, UI state
  - `InitializationMixin` - Hardware subsystem setup with splash progress
  - `RenderingMixin` - Display rendering pipeline
- **Same public interface** - No changes to main.py entry point
- **No functional changes** - All behaviour preserved

#### Modified Files

- `main.py` - Reduced from 2063 to 569 lines, now uses mixins
- `core/__init__.py` - New package exports
- `core/performance.py` - Power/memory monitoring functions and mixin
- `core/telemetry.py` - Telemetry recording mixin
- `core/event_handlers.py` - Event handling mixin
- `core/initialization.py` - Hardware initialization mixin
- `core/rendering.py` - Display rendering mixin
- `CLAUDE.md` - Updated directory structure and version

---

## [v0.18.2] - 2026-01-17

### Menu System Refactoring

#### Code Organisation

- **Modular menu system** - Split monolithic `gui/menu.py` (2848 lines) into focused modules
  - Each subsystem is now a separate mixin class for maintainability
  - Largest file now 1115 lines (was 2848)
  - Clear separation of concerns by functionality

#### New Structure

```
gui/menu/
├── __init__.py       # Exports Menu, MenuItem, MenuSystem
├── base.py           # Core menu classes (Menu, MenuItem, MenuSystem)
├── bluetooth.py      # Bluetooth Audio + TPMS pairing
├── camera.py         # Camera settings
├── copilot.py        # CoPilot rally callout settings
├── lap_timing.py     # Lap timing + track selection
├── lights.py         # NeoDriver LED strip
├── settings.py       # Display, Units, Thresholds, Pages
└── system.py         # GPS, IMU, Radar, System Status
```

#### Architecture

- **Mixin pattern** - MenuSystem inherits from all subsystem mixins
- **Backwards compatible** - `from gui.menu import MenuSystem` unchanged
- **No functional changes** - All menu behaviour preserved

#### Modified Files

- `gui/menu.py` - Removed (replaced by gui/menu/ package)
- `gui/menu/__init__.py` - New package exports
- `gui/menu/base.py` - Core Menu, MenuItem, MenuSystem classes
- `gui/menu/bluetooth.py` - Bluetooth Audio and TPMS pairing mixin
- `gui/menu/camera.py` - Camera settings mixin
- `gui/menu/copilot.py` - CoPilot settings mixin
- `gui/menu/lap_timing.py` - Lap timing mixin
- `gui/menu/lights.py` - NeoDriver LED strip mixin
- `gui/menu/settings.py` - Display/Units/Thresholds/Pages mixin
- `gui/menu/system.py` - GPS/IMU/Radar/System Status mixin
- `CLAUDE.md` - Updated directory structure

---

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
