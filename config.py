"""
Configuration settings for the openTPT system.
Contains constants for display, hardware, and feature configuration.

Organised into logical sections:
1. Display & UI (resolution, colours, assets, scaling, layout)
2. Units & Thresholds (temperature, pressure, speed)
3. Hardware - I2C Bus (addresses, mux, timing)
4. Hardware - Sensors (tyre, brake, TPMS, IMU)
5. Hardware - Cameras (resolution, devices, transforms)
6. Hardware - Input Devices (NeoKey, encoder, NeoDriver, OLED)
7. Hardware - CAN Bus (OBD2, Corner Sensors CAN, Radar)
8. Hardware - GPS (serial, timeouts)
9. Features - Lap Timing (tracks, corners, sectors)
10. Features - Fuel Tracking (tank, thresholds)
11. Features - CoPilot (maps, callouts, audio)
12. Threading & Performance (queues, timeouts)
13. Features - Pit Timer (waypoints, countdown, speed)
14. Hardware - Ford Hybrid (HV battery SOC)
"""

import logging
import os

logger = logging.getLogger("openTPT.config")

# ==============================================================================
# APPLICATION VERSION
# ==============================================================================
# Update this when releasing new versions
# Format: MAJOR.MINOR.PATCH (e.g., "0.19.0")
APP_VERSION = "0.19.11"

# Project root for asset paths
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Bundled assets directory (read-only, shipped with application)
BUNDLED_ASSETS_DIR = os.path.join(_PROJECT_ROOT, "assets")

# USB data template (for setting up new USB drives)
USB_DATA_TEMPLATE_DIR = os.path.join(_PROJECT_ROOT, "usb_data", ".opentpt")
BUNDLED_TRACKS_DIR = os.path.join(USB_DATA_TEMPLATE_DIR, "lap_timing", "tracks")

# ==============================================================================
# DATA STORAGE (USB preferred for read-only rootfs robustness)
# ==============================================================================
# USB mount point for persistent data storage
USB_MOUNT_PATH = "/mnt/usb"
USB_DATA_DIR = os.path.join(USB_MOUNT_PATH, ".opentpt")

# Local fallback (used if USB not mounted)
LOCAL_DATA_DIR = os.path.expanduser("~/.opentpt")


def _is_usb_mounted() -> bool:
    """Check if USB drive is mounted at the expected path."""
    return os.path.ismount(USB_MOUNT_PATH)


def get_data_dir() -> str:
    """
    Get the base data directory for persistent storage.

    Returns USB path if mounted, otherwise local fallback.
    For read-only rootfs setups, USB should always be used.
    """
    if _is_usb_mounted():
        return USB_DATA_DIR
    return LOCAL_DATA_DIR


def is_usb_storage_available() -> bool:
    """Check if USB storage is available for persistent data."""
    return _is_usb_mounted()


def ensure_tracks_available(data_dir: str) -> bool:
    """
    Ensure track data is available in the data directory.

    Copies bundled tracks to the data directory if they don't exist.
    This allows read-only rootfs installations to have tracks on USB.

    Args:
        data_dir: The data directory to check/populate

    Returns:
        True if tracks are available (either existed or were copied)
    """
    import shutil

    tracks_dir = os.path.join(data_dir, "lap_timing", "tracks")
    tracks_db = os.path.join(tracks_dir, "tracks.db")
    racelogic_db = os.path.join(tracks_dir, "racelogic.db")

    # Check if tracks already exist
    if os.path.exists(tracks_db) and os.path.exists(racelogic_db):
        return True

    # Check if bundled tracks exist
    if not os.path.exists(BUNDLED_TRACKS_DIR):
        logger.warning("No bundled tracks found at %s", BUNDLED_TRACKS_DIR)
        return False

    bundled_tracks_db = os.path.join(BUNDLED_TRACKS_DIR, "tracks.db")
    bundled_racelogic_db = os.path.join(BUNDLED_TRACKS_DIR, "racelogic.db")

    if not os.path.exists(bundled_tracks_db):
        logger.warning("Bundled tracks.db not found")
        return False

    # Create tracks directory
    try:
        os.makedirs(tracks_dir, exist_ok=True)
    except Exception as e:
        logger.error("Could not create tracks directory: %s", e)
        return False

    # Copy bundled tracks to data directory
    try:
        logger.info("Copying bundled tracks to %s", tracks_dir)

        # Copy databases
        if not os.path.exists(tracks_db) and os.path.exists(bundled_tracks_db):
            shutil.copy2(bundled_tracks_db, tracks_db)
            logger.info("Copied tracks.db")

        if not os.path.exists(racelogic_db) and os.path.exists(bundled_racelogic_db):
            shutil.copy2(bundled_racelogic_db, racelogic_db)
            logger.info("Copied racelogic.db")

        # Copy maps directory (custom tracks)
        bundled_maps = os.path.join(BUNDLED_TRACKS_DIR, "maps")
        maps_dir = os.path.join(tracks_dir, "maps")
        if not os.path.exists(maps_dir) and os.path.exists(bundled_maps):
            shutil.copytree(bundled_maps, maps_dir)
            logger.info("Copied custom tracks (maps/)")

        # Copy racelogic directory (KMZ files)
        bundled_racelogic = os.path.join(BUNDLED_TRACKS_DIR, "racelogic")
        racelogic_dir = os.path.join(tracks_dir, "racelogic")
        if not os.path.exists(racelogic_dir) and os.path.exists(bundled_racelogic):
            shutil.copytree(bundled_racelogic, racelogic_dir)
            logger.info("Copied racelogic tracks")

        logger.info("Track data copied successfully")
        return True

    except Exception as e:
        logger.error("Error copying bundled tracks: %s", e)
        return False


# Resolve data directory at import time
DATA_DIR = get_data_dir()
USB_STORAGE_AVAILABLE = is_usb_storage_available()


# ##############################################################################
#
#                              1. DISPLAY & UI
#
# ##############################################################################

# ==============================================================================
# REFERENCE RESOLUTION
# ==============================================================================

# Reference resolution for scaling (default 800x480)
REFERENCE_WIDTH = 800
REFERENCE_HEIGHT = 480

# Display dimensions (Waveshare 1024x600 HDMI)
# Change these values to match your display resolution
DISPLAY_WIDTH = 1024
DISPLAY_HEIGHT = 600

# Calculate scaling factors based on reference resolution
SCALE_X = DISPLAY_WIDTH / REFERENCE_WIDTH
SCALE_Y = DISPLAY_HEIGHT / REFERENCE_HEIGHT


def scale_position(pos):
    """Scale a position tuple (x, y) according to the current display resolution."""
    return (int(pos[0] * SCALE_X), int(pos[1] * SCALE_Y))


def scale_size(size):
    """Scale a size tuple (width, height) according to the current display resolution."""
    return (int(size[0] * SCALE_X), int(size[1] * SCALE_Y))


# ==============================================================================
# FRAME RATE & BRIGHTNESS
# ==============================================================================

FPS_TARGET = 60  # Target frame rate
DEFAULT_BRIGHTNESS = 0.8  # 0.0 to 1.0
BRIGHTNESS_PRESETS = [0.3, 0.5, 0.7, 0.9, 1.0]  # Cycle through these brightness levels
ROTATION = 90  # Degrees: 0, 90, 180, 270

# FPS Counter settings
FPS_COUNTER_ENABLED = False  # Show FPS counter on screen
FPS_COUNTER_POSITION = (
    "top-right"  # Options: "top-left", "top-right", "bottom-left", "bottom-right"
)
FPS_COUNTER_COLOUR = (0, 255, 0)  # RGB colour (default: green)

# Status bar configuration
STATUS_BAR_HEIGHT = 20  # Height of status bars in pixels (scaled)
STATUS_BAR_ENABLED = True  # Show status bars at top and bottom

# Memory Monitoring settings (for long runtime stability diagnostics)
MEMORY_MONITORING_ENABLED = True  # Log detailed memory stats every 60 seconds
# Logs: GPU memory (malloc/reloc), system RAM, Python process RSS/VMS, surface count
# Useful for diagnosing memory fragmentation issues during extended operation

# Thermal display settings
THERMAL_STALE_TIMEOUT = 1.0  # Seconds to show last good data before showing offline

# ==============================================================================
# UI PAGES
# ==============================================================================

# Available pages with their internal ID and display name
# Pages can be enabled/disabled via settings (pages.<id>.enabled)
UI_PAGES = [
    {"id": "telemetry", "name": "Telemetry", "default_enabled": True},
    {"id": "gmeter", "name": "G-Meter", "default_enabled": True},
    {"id": "lap_timing", "name": "Lap Timing", "default_enabled": True},
    {"id": "fuel", "name": "Fuel", "default_enabled": True},
    {"id": "copilot", "name": "CoPilot", "default_enabled": True},
    {"id": "pit_timer", "name": "Pit Timer", "default_enabled": True},
]

# Available OLED Bonnet pages with their internal ID and display name
# Pages can be enabled/disabled via settings (oled.pages.<id>.enabled)
OLED_PAGES = [
    {"id": "fuel", "name": "Fuel", "default_enabled": True},
    {"id": "delta", "name": "Delta", "default_enabled": True},
    {"id": "pit", "name": "Pit Timer", "default_enabled": True},
    {"id": "speed", "name": "Speed", "default_enabled": True},
    {"id": "max_speed", "name": "Max Speed", "default_enabled": False},
    {"id": "lap_timing", "name": "Lap Timing", "default_enabled": False},
    {"id": "lap_count", "name": "Lap Count", "default_enabled": False},
    {"id": "predictive", "name": "Predictive", "default_enabled": False},
    {"id": "longitudinal_g", "name": "Long. G", "default_enabled": False},
    {"id": "lateral_g", "name": "Lateral G", "default_enabled": False},
]

# ==============================================================================
# COLOURS
# ==============================================================================

GREY = (128, 128, 128)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
BLUE = (0, 0, 255)

# ==============================================================================
# ASSETS & FONTS
# ==============================================================================

OVERLAY_PATH = "assets/overlay.png"
TYRE_ICON_PATH = "assets/icons/icons8-tire-60.png"
BRAKE_ICON_PATH = "assets/icons/icons8-brake-discs-60.png"

# Font configuration (Noto Sans for consistent cross-platform typography)
FONT_PATH = os.path.join(_PROJECT_ROOT, "fonts", "NotoSans-Regular.ttf")
FONT_PATH_BOLD = os.path.join(_PROJECT_ROOT, "fonts", "NotoSans-Bold.ttf")

# Font sizes (scaled)
FONT_SIZE_LARGE = int(60 * min(SCALE_X, SCALE_Y))
FONT_SIZE_MEDARGE = int(24 * min(SCALE_X, SCALE_Y))  # TPMS pressure font
FONT_SIZE_MEDIUM = int(24 * min(SCALE_X, SCALE_Y))
FONT_SIZE_SMALL = int(18 * min(SCALE_X, SCALE_Y))

# Icon settings (scaled)
ICON_SIZE = scale_size((40, 40))
TYRE_ICON_POSITION = scale_position((725, 35))
BRAKE_ICON_POSITION = scale_position((35, 35))

# ==============================================================================
# UI LAYOUT DIMENSIONS
# ==============================================================================

# Reference coordinates (will be scaled)
MENU_ITEM_HEIGHT = 40  # Menu item height in pixels (before scaling)
SCALE_BAR_WIDTH = 200  # Scale bar width in pixels (before scaling)
SCALE_BAR_HEIGHT = 30  # Scale bar height in pixels (before scaling)
CAR_ICON_WIDTH = 100  # Car icon width in pixels (before scaling)
CAR_ICON_HEIGHT = 200  # Car icon height in pixels (before scaling)

# Text cache settings (for radar overlay and other cached text)
TEXT_CACHE_MAX_SIZE = 64  # Maximum entries in text render cache (LRU)

# Input event queue settings
INPUT_EVENT_QUEUE_SIZE = 10  # Maximum queued input events


# ##############################################################################
#
#                           2. UNITS & THRESHOLDS
#
# ##############################################################################

# ==============================================================================
# UNIT SETTINGS
# ==============================================================================

# Temperature unit: 'C' for Celsius, 'F' for Fahrenheit
TEMP_UNIT = "C"
# Pressure unit: 'PSI', 'BAR', or 'KPA'
PRESSURE_UNIT = "PSI"
# Speed unit: 'KMH' for km/h, 'MPH' for mph
SPEED_UNIT = "KMH"

# Note: The thresholds below are set according to the chosen units above.
# If you change the units, you should also adjust these thresholds appropriately.
# For reference:
# - Temperature conversion: F = (C * 9/5) + 32
# - Pressure conversion: 1 PSI = 0.0689476 BAR = 6.89476 kPa

# ==============================================================================
# TYRE TEMPERATURE THRESHOLDS (Celsius)
# ==============================================================================

TYRE_TEMP_COLD = 40.0  # Blue
TYRE_TEMP_OPTIMAL = 80.0  # Green
TYRE_TEMP_OPTIMAL_RANGE = 7.5  # Range around optimal temperature
TYRE_TEMP_HOT = 100.0  # Yellow to red
TYRE_TEMP_HOT_TO_BLACK = 50.0  # Range over which red fades to black after HOT

# Tyre temperature validation (reject implausible readings from I2C corruption)
TYRE_TEMP_VALID_MIN = -20.0  # Minimum valid reading (Celsius)
TYRE_TEMP_VALID_MAX = 150.0  # Maximum valid reading (Celsius)
TYRE_TEMP_MAX_SPIKE = 20.0  # Maximum change per reading (spike filter)

# ==============================================================================
# BRAKE TEMPERATURE THRESHOLDS (Celsius)
# ==============================================================================

BRAKE_TEMP_MIN = 75.0  # Min temperature for scale
BRAKE_TEMP_OPTIMAL = 200.0  # Optimal operating temperature
BRAKE_TEMP_OPTIMAL_RANGE = 50.0  # Range around optimal temperature
BRAKE_TEMP_HOT = 300.0  # Yellow to red
BRAKE_TEMP_HOT_TO_BLACK = 100.0  # Range over which red fades to black after HOT

# ==============================================================================
# TYRE PRESSURE THRESHOLDS
# ==============================================================================

PRESSURE_OFFSET = 5.0  # Offset from optimal pressure (+/- this value)
PRESSURE_FRONT_OPTIMAL = 32.0  # Front tyre optimal pressure
PRESSURE_REAR_OPTIMAL = 34.0  # Rear tyre optimal pressure
# Low/high thresholds are now calculated as optimal +/- offset

# ##############################################################################
#
#                           3. HARDWARE - I2C BUS
#
# ##############################################################################

# ==============================================================================
# I2C BUS SETTINGS
# ==============================================================================

I2C_BUS = 1  # Default I2C bus on Raspberry Pi 4



# ##############################################################################
#
#                          4. HARDWARE - SENSORS
#
# ##############################################################################

# ==============================================================================
# TYRE SENSORS (Thermal via CAN)
# ==============================================================================

# MLX90640 thermal camera settings (24x32 pixels)
# Used by Pico corner sensors for full thermal imaging
MLX_WIDTH = 32
MLX_HEIGHT = 24

# Tyre temperature display flip (swap inner/outer interpretation per corner)
# When True, left and right zones are swapped for display
# Useful when sensor is mounted in opposite orientation
TYRE_FLIP_INNER_OUTER_DEFAULT = False
MLX_POSITIONS = {
    "FL": scale_position((206, 50)),
    "FR": scale_position((443, 50)),
    "RL": scale_position((206, 258)),
    "RR": scale_position((443, 258)),
}
MLX_DISPLAY_WIDTH = int(
    150 * SCALE_X
)  # Width of displayed heatmap - to cover the complete tyre width
MLX_DISPLAY_HEIGHT = int(172 * SCALE_Y)  # Height of displayed heatmap

# ==============================================================================
# BRAKE SENSORS (via CAN from corner sensors)
# ==============================================================================

# Brake temperatures are now provided by CAN corner sensors via BrakeTemps messages.
# Each corner sensor reports inner/outer brake temps with sensor status.
# See CORNER_SENSOR_CAN_IDS for message IDs.

# Brake display positions
BRAKE_POSITIONS = {
    "FL": scale_position((379, 136)),
    "FR": scale_position((420, 136)),
    "RL": scale_position((379, 344)),
    "RR": scale_position((420, 344)),
}

# Emissivity for corner sensors
# Emissivity is configured in the corner sensor firmware (default 0.95) and
# reported via the CAN Status message. No software correction is needed as
# emissivity is applied during temperature calculation on the sensor itself.

# ==============================================================================
# TPMS (Tyre Pressure Monitoring System)
# ==============================================================================

# TPMS receiver thresholds (hardware alerts, in sensor native units)
TPMS_HIGH_PRESSURE_KPA = 310  # High pressure alert threshold (kPa)
TPMS_LOW_PRESSURE_KPA = 180  # Low pressure alert threshold (kPa)
TPMS_HIGH_TEMP_C = 75  # High temperature alert threshold (Celsius)
TPMS_DATA_TIMEOUT_S = 30.0  # Seconds before marking sensor as stale
TPMS_SERIAL_PORT = "/dev/ttyAMA3"  # UART3 on GPIO4/5 (None for USB auto-detect)

# TPMS positions on screen dynamically calculated based on MLX positions
# The pressure text is centred above each tyre's thermal display
TPMS_POSITIONS = {
    # Calculate pressure position as centred horizontally above the MLX display
    "FL": {
        "pressure": (
            MLX_POSITIONS["FL"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["FL"][1] - int(12 * SCALE_Y),
        ),
        "temp": (MLX_POSITIONS["FL"][0], MLX_POSITIONS["FL"][1] - int(10 * SCALE_Y)),
    },
    "FR": {
        "pressure": (
            MLX_POSITIONS["FR"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["FR"][1] - int(12 * SCALE_Y),
        ),
        "temp": (MLX_POSITIONS["FR"][0], MLX_POSITIONS["FR"][1] - int(10 * SCALE_Y)),
    },
    "RL": {
        "pressure": (
            MLX_POSITIONS["RL"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["RL"][1] + int(189 * SCALE_Y),
        ),
        "temp": (MLX_POSITIONS["RL"][0], MLX_POSITIONS["RL"][1] - int(10 * SCALE_Y)),
    },
    "RR": {
        "pressure": (
            MLX_POSITIONS["RR"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["RR"][1] + int(189 * SCALE_Y),
        ),
        "temp": (MLX_POSITIONS["RR"][0], MLX_POSITIONS["RR"][1] - int(10 * SCALE_Y)),
    },
}

# ==============================================================================
# IMU (G-Meter)
# ==============================================================================

# IMU sensor type - supported types:
# - "ICM20649" - ICM-20649 6-axis IMU (±30g accelerometer)
# - "MPU6050" - MPU-6050 6-axis IMU (±16g accelerometer)
# - "LSM6DS3" - LSM6DS3 6-axis IMU (±16g accelerometer)
# - "ADXL345" - ADXL345 3-axis accelerometer (±16g)
IMU_TYPE = "ICM20649"
IMU_ENABLED = True  # Enable IMU for G-meter functionality
IMU_I2C_ADDRESS = 0x68  # Default I2C address (ICM20649: 0x68 or 0x69)
IMU_SAMPLE_RATE = 50  # Hz - how often to read IMU data

# IMU axis mapping - maps physical IMU axes to vehicle axes
# Set based on how IMU is mounted in vehicle
# Options: "x", "-x", "y", "-y", "z", "-z" (negative inverts axis)
IMU_AXIS_LATERAL = "x"  # Vehicle left/right (positive = right)
IMU_AXIS_LONGITUDINAL = "y"  # Vehicle forward/back (positive = forward/accel)
IMU_AXIS_VERTICAL = "z"  # Vehicle up/down (positive = up)

# IMU calibration file (stores zero offsets for persistence)
IMU_CALIBRATION_FILE = "config/imu_calibration.json"

# G-meter display settings
GMETER_MAX_G = 2.0  # Maximum G-force to display (±2g is typical for road cars)
GMETER_HISTORY_SECONDS = 5.0  # How many seconds of history to show on trace

# IMU reconnection interval
IMU_RECONNECT_INTERVAL_S = 5.0  # Seconds between IMU reconnection attempts


# ##############################################################################
#
#                          5. HARDWARE - CAMERAS
#
# ##############################################################################

# ==============================================================================
# CAMERA RESOLUTION & FRAMERATE
# ==============================================================================

CAMERA_WIDTH = 800
CAMERA_HEIGHT = 600
CAMERA_FPS = 60  # Request max; each camera delivers what it can

# Camera field of view (used for radar overlay projection)
CAMERA_FOV_DEGREES = 106.0  # Horizontal field of view in degrees

# Camera FPS update interval (for display)
CAMERA_FPS_UPDATE_INTERVAL_S = 1.0  # Seconds between FPS counter updates

# ==============================================================================
# CAMERA DEVICES
# ==============================================================================

# Multi-camera configuration
# Set which cameras are available in your system
CAMERA_REAR_ENABLED = True  # Rear camera (with radar overlay if radar enabled)
CAMERA_FRONT_ENABLED = True  # Front camera (no radar overlay)

# Camera device paths (if using udev rules for persistent naming)
# Leave as None to auto-detect
CAMERA_REAR_DEVICE = "/dev/video-rear"  # or None for auto-detect
CAMERA_FRONT_DEVICE = "/dev/video-front"  # or None for auto-detect

# ==============================================================================
# CAMERA TRANSFORMS
# ==============================================================================

# Mirror: horizontally flip the image (True = rear-view mirror effect)
# Rotate: rotate image clockwise (0, 90, 180, 270 degrees)
CAMERA_REAR_MIRROR = True  # Default True for rear-view mirror effect
CAMERA_REAR_ROTATE = 0  # 0, 90, 180, 270 degrees
CAMERA_FRONT_MIRROR = False  # Default False for normal view
CAMERA_FRONT_ROTATE = 0  # 0, 90, 180, 270 degrees


# ##############################################################################
#
#                       6. HARDWARE - INPUT DEVICES
#
# ##############################################################################

# ==============================================================================
# NEOKEY 1x4 (Physical Buttons)
# ==============================================================================

# NeoKey 1x4 button mappings (inverted - board mounted upside down)
BUTTON_RECORDING = 3  # Start/stop telemetry recording (hold for 1 second)
BUTTON_PAGE_SETTINGS = 2  # Toggle page-specific settings (context-sensitive per page)
BUTTON_CATEGORY_SWITCH = 1  # Switch within category (camera↔camera OR UI page↔UI page)
BUTTON_VIEW_MODE = 0  # Switch between categories (camera pages ↔ UI pages)

# Recording configuration
RECORDING_HOLD_DURATION = 1.0  # Seconds to hold button 0 to start/stop recording
RECORDING_RATE_HZ = 10  # Telemetry recording rate (10 Hz matches sensor/GPS max rate)

# ==============================================================================
# ROTARY ENCODER (Adafruit I2C QT)
# ==============================================================================

ENCODER_ENABLED = True
ENCODER_I2C_ADDRESS = 0x36  # Default address, can be 0x36-0x3D
ENCODER_POLL_RATE = 20  # Hz - polling frequency
ENCODER_LONG_PRESS_MS = 500  # Milliseconds for long press detection
ENCODER_BRIGHTNESS_STEP = 0.05  # Brightness change per detent

# ==============================================================================
# NEODRIVER LED STRIP (Adafruit NeoDriver - I2C to NeoPixel)
# ==============================================================================

NEODRIVER_ENABLED = True
NEODRIVER_I2C_ADDRESS = 0x60  # Default NeoDriver address
NEODRIVER_NUM_PIXELS = 9  # Number of NeoPixels in strip
NEODRIVER_BRIGHTNESS = 0.3  # LED brightness (0.0-1.0)
NEODRIVER_DEFAULT_MODE = "shift"  # off, delta, overtake, shift, rainbow
NEODRIVER_DEFAULT_DIRECTION = (
    "centre_out"  # left_right, right_left, centre_out, edges_in
)
NEODRIVER_MAX_RPM = 7000  # Maximum RPM for shift light scale
NEODRIVER_SHIFT_RPM = 6500  # RPM at which shift indicator flashes (redline)
NEODRIVER_START_RPM = (
    3000  # RPM at which shift lights begin illuminating (0 = always on)
)

# NeoDriver timing
NEODRIVER_UPDATE_RATE_HZ = 15  # LED update rate (Hz)
NEODRIVER_STARTUP_DELAY_S = 0.05  # Delay per pixel during startup animation

# ==============================================================================
# OLED BONNET (Adafruit 128x32 SSD1305)
# ==============================================================================

OLED_BONNET_ENABLED = True
OLED_BONNET_I2C_ADDRESS = 0x3C  # Default SSD1305 address
OLED_BONNET_WIDTH = 128  # Display width in pixels
OLED_BONNET_HEIGHT = 32  # Display height in pixels
OLED_BONNET_DEFAULT_MODE = "fuel"  # fuel, delta
OLED_BONNET_AUTO_CYCLE = True  # Auto-cycle between modes
OLED_BONNET_CYCLE_INTERVAL = 10.0  # Seconds between mode changes
OLED_BONNET_BRIGHTNESS = 0.8  # Display contrast (0.0-1.0)
OLED_BONNET_UPDATE_RATE = 5  # Display refresh rate in Hz

# MCP23017 GPIO Expander for OLED buttons
OLED_MCP23017_ENABLED = True
OLED_MCP23017_I2C_ADDRESS = 0x20  # Default MCP23017 address (A0-A2 grounded)
OLED_MCP23017_BUTTON_PREV = 0  # GPA0 - Previous (page or function)
OLED_MCP23017_BUTTON_SELECT = 1  # GPA1 - Select (hold to enter/exit page)
OLED_MCP23017_BUTTON_NEXT = 2  # GPA2 - Next (page or function)
OLED_MCP23017_HOLD_TIME_MS = 500  # Hold duration for select button (milliseconds)
OLED_MCP23017_DEBOUNCE_MS = 75  # Button debounce time (milliseconds)


# ##############################################################################
#
#                         7. HARDWARE - CAN BUS
#
# ##############################################################################

# ==============================================================================
# SPEED SOURCE
# ==============================================================================

# Speed source: "obd" for OBD2/CAN, "gps" for GPS module
SPEED_SOURCE = "obd"

# ==============================================================================
# OBD2 (Vehicle Data)
# ==============================================================================

# Enable/disable OBD2 speed reading
OBD_ENABLED = True  # Set to False to disable OBD2 speed

# OBD2 CAN configuration
# Available interfaces: can_b1_0, can_b1_1, can_b2_0, can_b2_1
# OBD-II is connected to can_b2_1 (Board 2, CAN_1 connector)
OBD_CHANNEL = "can_b2_1"  # CAN channel for OBD2 data
OBD_BITRATE = 500000  # Standard OBD2 bitrate (500 kbps)

# OBD2 polling and timing
OBD_POLL_INTERVAL_S = 0.15  # Seconds between OBD2 queries
OBD_RECONNECT_INTERVAL_S = 5.0  # Seconds between reconnection attempts
OBD_SEND_TIMEOUT_S = 0.05  # Timeout for CAN message sends (seconds)

# OBD2 data smoothing (moving average window sizes)
OBD_SPEED_SMOOTHING_SAMPLES = 5  # Samples for speed smoothing
OBD_RPM_SMOOTHING_SAMPLES = 3  # Samples for RPM smoothing
OBD_THROTTLE_SMOOTHING_SAMPLES = 2  # Samples for throttle smoothing

# ==============================================================================
# CORNER SENSORS CAN (Tyre/Brake temps via CAN bus)
# ==============================================================================

# Enable/disable CAN-based corner sensors
# Corner sensors use Adafruit RP2040 CAN Bus Feather with MLX90640 thermal camera
CORNER_SENSOR_CAN_ENABLED = True

# Corner sensor CAN configuration
# Available interfaces: can_b1_0, can_b1_1, can_b2_0, can_b2_1
# Corner sensors use Board 2, CAN_0 connector (can_b2_0)
CORNER_SENSOR_CAN_CHANNEL = "can_b2_0"
CORNER_SENSOR_CAN_BITRATE = 500000  # Standard CAN bitrate (500 kbps)

# DBC file for decoding corner sensor CAN messages
CORNER_SENSOR_CAN_DBC = "opendbc/pico_tyre_temp.dbc"

# CAN message IDs per corner (from pico_tyre_temp.dbc)
# Each corner has: TyreTemps, TyreDetection, BrakeTemps, Status, FrameData
CORNER_SENSOR_CAN_IDS = {
    "FL": {"tyre": 0x100, "detection": 0x101, "brake": 0x102, "status": 0x110, "frame": 0x11C},
    "FR": {"tyre": 0x120, "detection": 0x121, "brake": 0x122, "status": 0x130, "frame": 0x13C},
    "RL": {"tyre": 0x140, "detection": 0x141, "brake": 0x142, "status": 0x150, "frame": 0x15C},
    "RR": {"tyre": 0x160, "detection": 0x161, "brake": 0x162, "status": 0x170, "frame": 0x17C},
}

# Command message IDs (sent by openTPT to sensors)
CORNER_SENSOR_CAN_CMD_IDS = {
    "frame_request": 0x7F3,  # Request full thermal frame from specific wheel
    "config_request": 0x7F1,  # Request configuration from all sensors
}

# Corner sensor CAN timing
CORNER_SENSOR_CAN_TIMEOUT_S = 0.5  # Data considered stale after this time
CORNER_SENSOR_CAN_NOTIFIER_TIMEOUT_S = 0.1  # CAN notifier timeout

# ==============================================================================
# RADAR (Toyota Radar Overlay)
# ==============================================================================

# Enable/disable radar overlay
RADAR_ENABLED = True  # Set to True to enable radar overlay on camera

# Toyota radar CAN configuration
# Available interfaces: can_b1_0, can_b1_1, can_b2_0, can_b2_1
# Radar outputs tracks on Board 1, CAN_1 connector (can_b1_1)
# Car keep-alive sent on Board 1, CAN_0 connector (can_b1_0)
RADAR_CHANNEL = "can_b1_1"  # CAN channel for radar data (tracks come FROM radar)
CAR_CHANNEL = "can_b1_0"  # CAN channel for car keep-alive (we send TO radar)
RADAR_INTERFACE = "socketcan"  # python-can interface
RADAR_BITRATE = 500000  # CAN bitrate

# DBC files for radar decoding
RADAR_DBC = "opendbc/toyota_prius_2017_adas.dbc"
CONTROL_DBC = "opendbc/toyota_prius_2017_pt_generated.dbc"

# Radar tracking parameters
RADAR_TRACK_TIMEOUT = 0.5  # Seconds before removing stale tracks
RADAR_MAX_DISTANCE = 120.0  # Maximum distance to display (metres)

# Radar overlay display settings
RADAR_CAMERA_FOV = 106.0  # Camera horizontal field of view (degrees)
RADAR_TRACK_COUNT = 3  # Number of nearest tracks to display
RADAR_MERGE_RADIUS = 1.0  # Merge tracks within this radius (metres)

# Warning thresholds
RADAR_WARN_YELLOW_KPH = 10.0  # Speed delta for yellow warning
RADAR_WARN_RED_KPH = 20.0  # Speed delta for red warning

# Overtake warning settings
RADAR_OVERTAKE_TIME_THRESHOLD = 1.0  # Time-to-overtake threshold (seconds)
RADAR_OVERTAKE_MIN_CLOSING_KPH = 5.0  # Minimum closing speed (km/h)
RADAR_OVERTAKE_MIN_LATERAL = 0.5  # Minimum lateral offset (metres)
RADAR_OVERTAKE_ARROW_DURATION = 1.0  # Duration to show arrow (seconds)

# Radar polling and timing
RADAR_POLL_INTERVAL_S = 0.05  # Seconds between radar reads (20 Hz)
RADAR_NOTIFIER_TIMEOUT_S = 0.1  # CAN notifier timeout (seconds)


# ##############################################################################
#
#                          8. HARDWARE - GPS
#
# ##############################################################################

# ==============================================================================
# GPS CONFIGURATION
# ==============================================================================

# Enable/disable GPS module
GPS_ENABLED = True  # Set to False to disable GPS

# Serial port for GPS (Raspberry Pi UART)
# GPIO 14 (TX) and GPIO 15 (RX) map to /dev/ttyS0 (mini UART on Pi 4/5)
GPS_SERIAL_PORT = "/dev/ttyS0"
GPS_BAUD_RATE = 38400  # 38400 for 10Hz update rate (configure GPS module to match)

# GPS serial timeout settings
GPS_SERIAL_TIMEOUT_S = 0.15  # Read timeout for serial port (seconds)
GPS_SERIAL_WRITE_TIMEOUT_S = 0.5  # Write timeout for serial port (seconds)
GPS_COMMAND_TIMEOUT_S = 5.0  # Timeout waiting for command response (seconds)


# ##############################################################################
#
#                        9. FEATURES - LAP TIMING
#
# ##############################################################################

# ==============================================================================
# LAP TIMING CONFIGURATION
# ==============================================================================

# Enable/disable lap timing system
LAP_TIMING_ENABLED = True  # Set to False to disable lap timing

# Track auto-detection
TRACK_AUTO_DETECT = True  # Automatically detect track from GPS position
TRACK_SEARCH_RADIUS_KM = 10.0  # Search radius for nearby tracks (kilometres)

# Delta bar display range
DELTA_BAR_RANGE = 10.0  # Maximum delta to display (seconds, +/-)

# Lap timing data directory (uses USB if available)
LAP_TIMING_DATA_DIR = os.path.join(DATA_DIR, "lap_timing")

# Track database paths (relative to LAP_TIMING_DATA_DIR)
LAP_TIMING_TRACKS_DIR = os.path.join(LAP_TIMING_DATA_DIR, "tracks")
LAP_TIMING_TRACKS_DB = os.path.join(LAP_TIMING_TRACKS_DIR, "tracks.db")
LAP_TIMING_RACELOGIC_DB = os.path.join(LAP_TIMING_TRACKS_DIR, "racelogic.db")
LAP_TIMING_CUSTOM_TRACKS_DIR = os.path.join(LAP_TIMING_TRACKS_DIR, "maps")
LAP_TIMING_RACELOGIC_TRACKS_DIR = os.path.join(LAP_TIMING_TRACKS_DIR, "racelogic")

# Routes directory for GPX/KMZ files (uses USB if available)
LAP_TIMING_ROUTES_DIR = os.path.join(DATA_DIR, "routes")

# Sector configuration
LAP_TIMING_SECTOR_COUNT = 3  # Number of sectors per lap

# Corner detection configuration (for track corner analysis)
# These are tuned for track use - tighter thresholds than CoPilot road settings
LAP_TIMING_CORNER_DETECTOR = "hybrid"  # hybrid, asc, curvefinder, or threshold
LAP_TIMING_CORNER_MIN_RADIUS_M = 100.0  # Max radius to classify as corner (metres)
LAP_TIMING_CORNER_MIN_ANGLE_DEG = 15.0  # Min angle to classify as corner (degrees)
LAP_TIMING_CORNER_MIN_CUT_DISTANCE_M = 15.0  # Min distance between cuts (metres)
LAP_TIMING_CORNER_STRAIGHT_FILL_M = 100.0  # Add cuts every N metres in straights
LAP_TIMING_CORNER_MERGE_CHICANES = True  # Merge consecutive opposite-direction corners

# Map theme (theme files in assets/themes/)
MAP_THEME_DEFAULT = "default"


# ##############################################################################
#
#                       10. FEATURES - FUEL TRACKING
#
# ##############################################################################

# ==============================================================================
# FUEL TRACKING CONFIGURATION
# ==============================================================================

# Enable/disable fuel tracking system
FUEL_TRACKING_ENABLED = True  # Set to False to disable fuel tracking

# Default fuel tank capacity (user-settable via settings menu)
# This value is used when no user preference is stored
FUEL_TANK_CAPACITY_LITRES_DEFAULT = 50.0

# Fuel warning thresholds (percentage of tank capacity)
FUEL_LOW_THRESHOLD_PERCENT = 20.0  # Yellow warning threshold
FUEL_CRITICAL_THRESHOLD_PERCENT = 10.0  # Red warning threshold

# Smoothing for fuel level readings (number of samples to average)
# Higher values = smoother but slower response to actual fuel changes
# 30 samples at 0.15s poll interval = ~4.5 seconds of smoothing
# Motorsport fuel slosh requires significant smoothing for stable readings
FUEL_SMOOTHING_SAMPLES = 30

# Use median filter for fuel level smoothing (better at rejecting outliers from fuel slosh)
# If False, uses simple moving average
FUEL_USE_MEDIAN_FILTER = True

# Number of laps to average for consumption estimate
FUEL_LAP_HISTORY_COUNT = 5

# Minimum distance (km) before calculating range estimates
# Prevents garbage data from short trips with unreliable consumption calculation
FUEL_MIN_DISTANCE_FOR_ESTIMATE_KM = 5.0


# ##############################################################################
#
#                        11. FEATURES - COPILOT
#
# ##############################################################################

# ==============================================================================
# COPILOT CONFIGURATION (Rally Callouts)
# ==============================================================================

# Enable/disable CoPilot system
COPILOT_ENABLED = True  # Set to False to disable CoPilot

# Map data directory (SQLite .roads.db files)
# Download regional PBF files from Geofabrik and convert to .roads.db
# Note: Maps are large (6+ GB) so always on USB, not affected by DATA_DIR
COPILOT_MAP_DIR = os.path.join(USB_MOUNT_PATH, ".opentpt/copilot/maps")

# Routes directory for GPX files (uses USB if available)
COPILOT_ROUTES_DIR = os.path.join(DATA_DIR, "copilot/routes")

# Cache directory for CoPilot data (uses USB if available)
COPILOT_CACHE_DIR = os.path.join(DATA_DIR, "copilot/cache")

# ==============================================================================
# COPILOT - LOOKAHEAD & ROAD FETCHING
# ==============================================================================

# Lookahead distance for corner detection (metres)
# Higher values give earlier warnings but may be less accurate
COPILOT_LOOKAHEAD_M = 1000

# Road data fetching
COPILOT_ROAD_FETCH_RADIUS_M = 2000  # Radius to cache roads around current position
COPILOT_REFETCH_DISTANCE_M = 500  # Refetch roads when moved this far from last fetch

# Update interval in seconds
# Lower values give more responsive callouts but use more CPU
COPILOT_UPDATE_INTERVAL_S = 0.5

# ==============================================================================
# COPILOT - CORNER DETECTION
# ==============================================================================

# Corner detection (tuned for road driving - larger radii than track)
COPILOT_CORNER_MIN_RADIUS_M = 300.0  # Minimum radius to consider a corner (metres)
COPILOT_CORNER_MIN_ANGLE_DEG = (
    10.0  # Minimum total angle to consider a corner (degrees)
)

# Corner detector parameters (for pacenotes)
COPILOT_CORNER_MIN_CUT_DISTANCE_M = 10.0  # Minimum distance between cuts
COPILOT_CORNER_MAX_CHICANE_GAP_M = 15.0  # Maximum gap for chicane detection

# ==============================================================================
# COPILOT - JUNCTION DETECTION
# ==============================================================================

COPILOT_JUNCTION_WARN_DISTANCE_M = 200  # Warn about T-junctions this far ahead
COPILOT_HEADING_TOLERANCE_DEG = (
    45.0  # Roads within this angle of heading are "straight on" (increased for real-world use)
)
COPILOT_ROAD_SEARCH_RADIUS_M = 150  # Maximum distance from GPS to search for current road

# ==============================================================================
# COPILOT - AUDIO
# ==============================================================================

COPILOT_AUDIO_ENABLED = True  # Enable audio callouts
COPILOT_AUDIO_VOLUME = 0.8  # Audio volume (0.0-1.0)
COPILOT_TTS_VOICE = "Daniel"  # British male voice (macOS), falls back to en-gb on Linux
COPILOT_TTS_SPEED = 210  # Words per minute (faster for rally style)

# ==============================================================================
# COPILOT - OVERLAY
# ==============================================================================

COPILOT_OVERLAY_ENABLED = True  # Show corner indicator on screen
COPILOT_OVERLAY_POSITION = (
    "bottom-left"  # top-left, top-right, bottom-left, bottom-right
)

# Status bar settings
COPILOT_STATUS_ENABLED = True  # Show last callout in status bar

# ==============================================================================
# COPILOT - CALLOUT DISTANCES
# ==============================================================================

# Corner callout distances (metres) - at what distances to call corners
COPILOT_CORNER_CALLOUT_DISTANCES = [1000, 500, 300, 200, 100]

# Multi-hazard callout distances (metres) - for consecutive hazards
COPILOT_MULTI_CALLOUT_DISTANCES = [500, 300, 100]

# Default callout distance (metres) - used when no specific distance needed
COPILOT_DEFAULT_CALLOUT_DISTANCE_M = 100

# Note merging distance (metres) - merge notes closer than this
COPILOT_NOTE_MERGE_DISTANCE_M = 50

# ==============================================================================
# COPILOT - SIMULATION MODE
# ==============================================================================

COPILOT_SIMULATION_FETCH_RADIUS_M = 5000  # Radius for road data fetch in simulation
COPILOT_REFETCH_THRESHOLD_M = 2500  # Distance before triggering refetch


# ##############################################################################
#
#                     12. THREADING & PERFORMANCE
#
# ##############################################################################

# ==============================================================================
# BOUNDED QUEUE HANDLER SETTINGS
# ==============================================================================

# Used by all hardware handlers for lock-free producer-consumer pattern
HANDLER_QUEUE_DEPTH = 2  # Depth of snapshot queue
HANDLER_STOP_TIMEOUT_S = 5.0  # Timeout waiting for handler thread to stop

# ==============================================================================
# THREAD SHUTDOWN TIMEOUTS
# ==============================================================================

THREAD_JOIN_TIMEOUT_S = 2.0  # Default timeout for thread.join() calls
THREAD_SHUTDOWN_TIMEOUT_S = 1.0  # Timeout for background thread shutdown

# ==============================================================================
# PERFORMANCE MONITORING
# ==============================================================================

PERFORMANCE_WARNING_HISTORY = 10  # Number of performance warnings to retain

# Unit conversion functions moved to utils/conversions.py
# Import them from there: from utils.conversions import celsius_to_fahrenheit, etc.

# Helper functions moved to utils/
# - Emissivity correction: from utils.thermal import apply_emissivity_correction


# ##############################################################################
#
#                        13. FEATURES - PIT TIMER
#
# ##############################################################################

# ==============================================================================
# PIT TIMER CONFIGURATION
# ==============================================================================

# Enable/disable pit timer system
PIT_TIMER_ENABLED = True  # Set to False to disable pit timer

# Pit lane speed limit defaults (user-configurable via menu)
PIT_SPEED_LIMIT_DEFAULT_KMH = 60.0  # Default pit lane speed limit
PIT_SPEED_WARNING_MARGIN_KMH = 5.0  # Warn when within this margin of limit

# Timing modes
# "entrance_to_exit" - Total pit time from entry line to exit line
# "stationary_only" - Only time spent stationary in pit box
PIT_TIMER_DEFAULT_MODE = "entrance_to_exit"

# Pit line configuration
PIT_LINE_WIDTH_M = 15.0  # Width of crossing detection lines (metres)

# Stationary detection
PIT_STATIONARY_SPEED_KMH = 2.0  # Speed below which car is considered stationary
PIT_STATIONARY_DURATION_S = 1.0  # Seconds below threshold to trigger stationary

# Minimum stop time (countdown target)
PIT_MIN_STOP_TIME_DEFAULT_S = 0.0  # No minimum by default (user-configurable)

# Data storage directory (uses USB if available)
PIT_TIMER_DATA_DIR = os.path.join(DATA_DIR, "pit_timer")


# ##############################################################################
#
#                       14. HARDWARE - LASER RANGER
#
# ##############################################################################

# ==============================================================================
# LASER RANGER CAN (Front Distance Sensor)
# ==============================================================================

# Enable/disable laser ranger (TOF distance sensor on CAN bus)
LASER_RANGER_ENABLED = True

# Laser ranger CAN configuration
# Uses same channel as corner sensors (can_b2_0)
LASER_RANGER_CAN_CHANNEL = "can_b2_0"
LASER_RANGER_CAN_BITRATE = 500000  # Standard CAN bitrate (500 kbps)

# DBC file for decoding laser ranger CAN messages
LASER_RANGER_CAN_DBC = "opendbc/pico_can_ranger.dbc"

# CAN message IDs (Sensor ID 0 = base 0x200)
# Supports up to 4 sensors (IDs 0-3) with 0x20 spacing
LASER_RANGER_SENSOR_ID = 0  # Default sensor ID
LASER_RANGER_RANGE_DATA_ID = 0x200  # RangeData message (base + sensor_id * 0x20)
LASER_RANGER_STATUS_ID = 0x210  # Status message (base + 0x10 + sensor_id * 0x20)

# Laser ranger timing
LASER_RANGER_TIMEOUT_S = 1.0  # Data considered stale after this time

# Display settings (when shown on front camera)
LASER_RANGER_DISPLAY_ENABLED = True  # Show distance overlay on front camera
LASER_RANGER_MAX_DISPLAY_M = 50.0  # Maximum distance to display (metres)
LASER_RANGER_WARN_DISTANCE_M = 5.0  # Distance for warning colour (red)
LASER_RANGER_CAUTION_DISTANCE_M = 15.0  # Distance for caution colour (yellow)
LASER_RANGER_DISPLAY_POSITION = "bottom"  # Position: "top" or "bottom"
LASER_RANGER_TEXT_SIZE = "medium"  # Text size: "small", "medium", "large"

# Text size presets (base font sizes before scaling)
LASER_RANGER_TEXT_SIZES = {
    "small": 32,
    "medium": 48,
    "large": 64,
}


# ##############################################################################
#
#                       15. HARDWARE - FORD HYBRID
#
# ##############################################################################

# ==============================================================================
# FORD HYBRID CAN (HV Battery SOC via Mode 22 PIDs)
# ==============================================================================

# Enable/disable Ford Hybrid CAN handler
# Reads HV battery state of charge and power data via Ford-specific PIDs
FORD_HYBRID_ENABLED = True

# Ford Hybrid CAN configuration
# Uses the same OBD2 channel (HS-CAN) since Ford Mode 22 PIDs go over standard OBD
FORD_HYBRID_CHANNEL = "can_b2_1"  # Same as OBD_CHANNEL (HS-CAN)
FORD_HYBRID_BITRATE = 500000  # Standard CAN bitrate (500 kbps)

# Ford Hybrid polling and timing
FORD_HYBRID_POLL_INTERVAL_S = 0.2  # Seconds between PID queries (slower to avoid bus flooding)
FORD_HYBRID_SEND_TIMEOUT_S = 0.05  # Timeout for CAN message sends (seconds)
