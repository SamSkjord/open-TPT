"""
Configuration settings for the openTPT system.
Contains constants for display, hardware, and feature configuration.

Organised into logical sections:
1. Display & UI (resolution, colours, assets, scaling, layout)
2. Units & Thresholds (temperature, pressure, speed)
3. Hardware - I2C Bus (addresses, mux, timing)
4. Hardware - Sensors (tyre, brake, TOF, TPMS, IMU)
5. Hardware - Cameras (resolution, devices, transforms)
6. Hardware - Input Devices (NeoKey, encoder, NeoDriver, OLED)
7. Hardware - CAN Bus (OBD2, Ford Hybrid, Radar)
8. Hardware - GPS (serial, timeouts)
9. Features - Lap Timing (tracks, corners, sectors)
10. Features - Fuel Tracking (tank, thresholds)
11. Features - CoPilot (maps, callouts, audio)
12. Threading & Performance (queues, timeouts)
"""

import logging
import os

logger = logging.getLogger("openTPT.config")

# Project root for asset paths
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


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
TYRE_TEMP_VALID_MIN = 5.0  # Minimum valid reading (Celsius)
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

# ==============================================================================
# TOF DISTANCE THRESHOLDS (millimetres)
# ==============================================================================

# Colour transitions for ride height display
TOF_DISTANCE_MIN = 50  # Minimum expected distance (very compressed)
TOF_DISTANCE_OPTIMAL = 120  # Optimal ride height (green)
TOF_DISTANCE_RANGE = 20  # Range around optimal (±20mm = green zone)
TOF_DISTANCE_MAX = 200  # Maximum expected distance (full extension)


# ##############################################################################
#
#                           3. HARDWARE - I2C BUS
#
# ##############################################################################

# ==============================================================================
# I2C BUS SETTINGS
# ==============================================================================

I2C_BUS = 1  # Default I2C bus on Raspberry Pi 4

# ==============================================================================
# I2C MULTIPLEXER (TCA9548A)
# ==============================================================================

I2C_MUX_ADDRESS = 0x70  # TCA9548A default address
I2C_MUX_RESET_PIN = (
    17  # GPIO pin for TCA9548A reset (active-low, uses internal pull-up)
)
I2C_MUX_RESET_FAILURES = 3  # Consecutive failures before triggering mux reset

# ==============================================================================
# I2C DEVICE ADDRESSES
# ==============================================================================

ADS_ADDRESS = 0x48  # ADS1115/ADS1015 ADC default address
TOF_I2C_ADDRESS = 0x29  # VL53L0X default address

# MCP9601 thermocouple amplifier addresses (two per corner for inner/outer pads)
MCP9601_ADDRESSES = {
    "inner": 0x65,  # Inner pad sensor
    "outer": 0x66,  # Outer pad sensor
}

# ==============================================================================
# I2C TIMING CONFIGURATION
# ==============================================================================

I2C_TIMEOUT_S = 0.5  # Timeout for I2C operations (seconds)
I2C_SETTLE_DELAY_S = 0.005  # Delay after I2C operations for bus settle (seconds)
I2C_MUX_RESET_PULSE_S = 0.001  # Mux reset pulse duration (seconds)
I2C_MUX_STABILISE_S = 0.010  # Delay after mux reset for stabilisation (seconds)

# ==============================================================================
# I2C EXPONENTIAL BACKOFF (for error recovery)
# ==============================================================================

I2C_BACKOFF_INITIAL_S = 1.0  # Initial backoff delay (seconds)
I2C_BACKOFF_MULTIPLIER = 2  # Backoff multiplier per failure
I2C_BACKOFF_MAX_S = 64.0  # Maximum backoff delay (seconds)


# ##############################################################################
#
#                          4. HARDWARE - SENSORS
#
# ##############################################################################

# ==============================================================================
# TYRE SENSORS (Thermal)
# ==============================================================================

# Per-tyre sensor type selection
# Options: "pico" for Pico I2C slave with MLX90640, "mlx90614" for single-point IR sensor
TYRE_SENSOR_TYPES = {
    "FL": "pico",  # Front Left
    "FR": "pico",  # Front Right
    "RL": "pico",  # Rear Left
    "RR": "pico",  # Rear Right
}

# Pico I2C slave modules (MLX90640 thermal cameras)
# Maps tyre positions to I2C multiplexer channels
PICO_MUX_CHANNELS = {
    "FL": 0,  # Front Left on channel 0
    "FR": 1,  # Front Right on channel 1
    "RL": 2,  # Rear Left on channel 2
    "RR": 3,  # Rear Right on channel 3
}

# MLX90614 single-point IR sensors
# Maps tyre positions to I2C multiplexer channels
MLX90614_MUX_CHANNELS = {
    "FL": 0,  # Front Left on channel 0
    "FR": 1,  # Front Right on channel 1
    "RL": 2,  # Rear Left on channel 2
    "RR": 3,  # Rear Right on channel 3
}

# MLX90640 thermal camera settings (24x32 pixels)
# Used by Pico I2C slaves for full thermal imaging
MLX_WIDTH = 32
MLX_HEIGHT = 24
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
# BRAKE SENSORS
# ==============================================================================

# Per-corner brake sensor type selection
# Options: "adc" for IR sensors via ADS1115, "mlx90614" for single-point IR,
#          "mcp9601" for thermocouple via MCP9601, "obd" for CAN/OBD-II
BRAKE_SENSOR_TYPES = {
    "FL": "mcp9601",  # Front Left - MCP9601 thermocouples (inner/outer)
    "FR": "adc",  # Front Right - ADC IR sensor
    "RL": None,  # Rear Left - No sensor connected
    "RR": None,  # Rear Right - No sensor connected
}

# ADC channel mapping for IR brake sensors (ADS1115)
# Used when sensor type is "adc"
ADC_BRAKE_CHANNELS = {
    "FL": 0,  # A0
    "FR": 1,  # A1
    "RL": 2,  # A2
    "RR": 3,  # A3
}

# MLX90614 I2C multiplexer channel mapping
# Used when sensor type is "mlx90614"
# Shares same mux channels as tyre sensors (one channel per corner)
MLX90614_BRAKE_MUX_CHANNELS = {
    "FL": 0,  # Channel 0 - shared with tyre sensor
    "FR": 1,  # Channel 1 - shared with tyre sensor
    "RL": 2,  # Channel 2 - shared with tyre sensor
    "RR": 3,  # Channel 3 - shared with tyre sensor
}

# MCP9601 I2C multiplexer channel mapping
# Shares same mux channels as other corner sensors
MCP9601_MUX_CHANNELS = {
    "FL": 0,  # Channel 0
    "FR": 1,  # Channel 1
    "RL": 2,  # Channel 2
    "RR": 3,  # Channel 3
}

# MCP9601 Thermocouple Amplifier Configuration
# Supports dual sensors per corner (inner and outer brake pads)
# Set to True to enable dual-zone brake temperature monitoring
MCP9601_DUAL_ZONE = {
    "FL": True,  # Inner (0x65) and outer (0x66) thermocouples installed
    "FR": False,
    "RL": False,
    "RR": False,
}

# Mock data for testing dual-zone brake display without hardware
# Set to True to show animated test data for dual-zone brakes
BRAKE_DUAL_ZONE_MOCK = False

# OBD/CAN brake temperature mapping
# Used when sensor type is "obd"
# Maps brake positions to CAN signal names (if available)
OBD_BRAKE_SIGNALS = {
    "FL": None,  # Not typically available via OBD-II
    "FR": None,  # Most cars don't broadcast brake temps
    "RL": None,  # Would need custom CAN implementation
    "RR": None,  # or aftermarket ECU
}

# Brake display positions
BRAKE_POSITIONS = {
    "FL": scale_position((379, 136)),
    "FR": scale_position((420, 136)),
    "RL": scale_position((379, 344)),
    "RR": scale_position((420, 344)),
}

# Brake rotor emissivity values
# Emissivity ranges from 0.0 to 1.0, where 1.0 is a perfect black body
#
# IMPORTANT: MLX90614 and other IR sensors have a factory default emissivity
# setting of 1.0 (perfect black body). Since brake rotors have lower emissivity,
# the sensor will read LOWER than the actual temperature. The software applies
# correction using apply_emissivity_correction() to compensate.
#
# NOTE: This is different from tyre sensors (MLX90640 via Pico), where emissivity
# is configured in the Pico firmware (default 0.95 for rubber tyres) and applied
# during temperature calculation. Brake sensors use software correction because
# MLX90614/ADC sensors operate at their factory default ε = 1.0.
#
# How it works:
#   1. MLX90614 sensor assumes ε = 1.0 (factory default, not changed)
#   2. Actual brake rotor has ε = 0.95 (oxidised cast iron)
#   3. Sensor reads lower than actual (less radiation from non-black-body surface)
#   4. Software correction adjusts reading upward: T_actual = T_measured / ε^0.25
#
# Typical rotor emissivity values:
#   - Cast iron (rusty/oxidised): 0.95
#   - Cast iron (machined/clean): 0.60-0.70
#   - Steel (oxidised): 0.80
#   - Steel (polished): 0.15-0.25
#   - Ceramic composite: 0.90-0.95
#
# Adjust per-corner values below to match your specific rotor materials.
BRAKE_ROTOR_EMISSIVITY = {
    "FL": 0.95,  # Front Left - typical oxidised cast iron
    "FR": 0.95,  # Front Right
    "RL": 0.95,  # Rear Left
    "RR": 0.95,  # Rear Right
}

# ==============================================================================
# TOF DISTANCE SENSORS (VL53L0X)
# ==============================================================================

# Enable/disable TOF distance sensors per corner
# VL53L0X sensors measure distance to ground (ride height) in millimetres
# Disabled: VL53L0X not reliable enough for ride height measurement
TOF_ENABLED = False  # Master enable for all TOF sensors

# Per-corner TOF sensor enable
# Set to True/False to enable/disable individual corners
TOF_SENSOR_ENABLED = {
    "FL": True,  # Front Left
    "FR": True,  # Front Right
    "RL": True,  # Rear Left
    "RR": True,  # Rear Right
}

# I2C multiplexer channel mapping for VL53L0X sensors
# Shares same mux channels as tyre/brake sensors (one channel per corner)
TOF_MUX_CHANNELS = {
    "FL": 0,  # Channel 0 - shared with tyre sensor
    "FR": 1,  # Channel 1 - shared with tyre sensor
    "RL": 2,  # Channel 2 - shared with tyre sensor
    "RR": 3,  # Channel 3 - shared with tyre sensor
}

# Display configuration for TOF distance readings
# Positions are calculated relative to tyre thermal display positions
# Distance text appears to the side of each tyre
TOF_DISPLAY_POSITIONS = {
    # Left side tyres: distance shown to the left of thermal display
    "FL": scale_position((170, 130)),  # Left of FL thermal
    "RL": scale_position((170, 338)),  # Left of RL thermal
    # Right side tyres: distance shown to the right of thermal display
    "FR": scale_position((630, 130)),  # Right of FR thermal
    "RR": scale_position((630, 338)),  # Right of RR thermal
}

# TOF sensor history window (for smoothing/analysis)
TOF_HISTORY_WINDOW_S = 10.0  # Seconds of TOF data to retain
TOF_HISTORY_SAMPLES = 100  # Maximum number of samples to retain

# ==============================================================================
# TPMS (Tyre Pressure Monitoring System)
# ==============================================================================

# TPMS receiver thresholds (hardware alerts, in sensor native units)
TPMS_HIGH_PRESSURE_KPA = 310  # High pressure alert threshold (kPa)
TPMS_LOW_PRESSURE_KPA = 180  # Low pressure alert threshold (kPa)
TPMS_HIGH_TEMP_C = 75  # High temperature alert threshold (Celsius)
TPMS_DATA_TIMEOUT_S = 30.0  # Seconds before marking sensor as stale

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
OLED_MCP23017_DEBOUNCE_MS = 50  # Button debounce time (milliseconds)


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
# FORD HYBRID (Battery State of Charge)
# ==============================================================================

# Enable/disable Ford Hybrid battery monitoring
FORD_HYBRID_ENABLED = (
    False  # Set to True to enable Ford hybrid SOC and power monitoring
)

# Ford Hybrid CAN configuration
# Available interfaces: can_b1_0, can_b1_1, can_b2_0, can_b2_1
# Ford Hybrid module is on can_b2_0 (Board 2, CAN_0 connector)
FORD_HYBRID_CHANNEL = "can_b2_0"  # CAN channel for Ford hybrid data
FORD_HYBRID_BITRATE = 500000  # Standard CAN bitrate (500 kbps)

# Ford Hybrid polling and timing
FORD_HYBRID_POLL_INTERVAL_S = 0.5  # Seconds between Ford Hybrid queries (2 Hz)
FORD_HYBRID_SEND_TIMEOUT_S = 0.1  # Timeout for CAN message sends (seconds)

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

# Lap timing data directory
LAP_TIMING_DATA_DIR = os.path.expanduser("~/.opentpt/lap_timing")

# Track database paths (relative to LAP_TIMING_DATA_DIR)
LAP_TIMING_TRACKS_DIR = os.path.join(LAP_TIMING_DATA_DIR, "tracks")
LAP_TIMING_TRACKS_DB = os.path.join(LAP_TIMING_TRACKS_DIR, "tracks.db")
LAP_TIMING_RACELOGIC_DB = os.path.join(LAP_TIMING_TRACKS_DIR, "racelogic.db")
LAP_TIMING_CUSTOM_TRACKS_DIR = os.path.join(LAP_TIMING_TRACKS_DIR, "maps")
LAP_TIMING_RACELOGIC_TRACKS_DIR = os.path.join(LAP_TIMING_TRACKS_DIR, "racelogic")

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
# Higher values = smoother but slower response
FUEL_SMOOTHING_SAMPLES = 5

# Number of laps to average for consumption estimate
FUEL_LAP_HISTORY_COUNT = 5


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
COPILOT_MAP_DIR = os.path.expanduser("~/.opentpt/copilot/maps")

# Cache directory for CoPilot data
COPILOT_CACHE_DIR = os.path.expanduser("~/.opentpt/copilot/cache")

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
    30.0  # Roads within this angle of heading are "straight on"
)

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
