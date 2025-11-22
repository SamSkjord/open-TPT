"""
Configuration settings for the openTPT system.
Contains constants for display, positions, colors, and thresholds.
"""

import os
import json

# Display settings
# Reference resolution for scaling (default 800x480)
REFERENCE_WIDTH = 800
REFERENCE_HEIGHT = 480

# Load display settings from config file
CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "display_config.json"
)

FPS_TARGET = 60  # Increased to allow higher camera FPS
DEFAULT_BRIGHTNESS = 0.8  # 0.0 to 1.0
BRIGHTNESS_PRESETS = [0.3, 0.5, 0.7, 0.9, 1.0]  # Cycle through these brightness levels
ROTATION = 90  # Degrees: 0, 90, 180, 270


# Unit settings
# Temperature unit: 'C' for Celsius, 'F' for Fahrenheit
TEMP_UNIT = "C"
# Pressure unit: 'PSI', 'BAR', or 'KPA'
PRESSURE_UNIT = "PSI"

# FPS Counter settings
FPS_COUNTER_ENABLED = False  # Show FPS counter on screen
FPS_COUNTER_POSITION = (
    "top-right"  # Options: "top-left", "top-right", "bottom-left", "bottom-right"
)
FPS_COUNTER_COLOR = (0, 255, 0)  # RGB color (default: green)

# Memory Monitoring settings (for long runtime stability diagnostics)
MEMORY_MONITORING_ENABLED = True  # Log detailed memory stats every 60 seconds
# Logs: GPU memory (malloc/reloc), system RAM, Python process RSS/VMS, surface count
# Useful for diagnosing memory fragmentation issues during extended operation

CAMERA_WIDTH = 800
CAMERA_HEIGHT = 600
CAMERA_FPS = 30

# Multi-camera configuration
# Set which cameras are available in your system
CAMERA_REAR_ENABLED = True  # Rear camera (with radar overlay if radar enabled)
CAMERA_FRONT_ENABLED = True  # Front camera (no radar overlay)

# Camera device paths (if using udev rules for persistent naming)
# Leave as None to auto-detect
CAMERA_REAR_DEVICE = "/dev/video-rear"  # or None for auto-detect
CAMERA_FRONT_DEVICE = "/dev/video-front"  # or None for auto-detect

# Note: The thresholds below are set according to the chosen units above.
# If you change the units, you should also adjust these thresholds appropriately.
# For reference:
# - Temperature conversion: F = (C * 9/5) + 32
# - Pressure conversion: 1 PSI = 0.0689476 BAR = 6.89476 kPa

# Tyre Pressure thresholds
PRESSURE_OFFSET = 5.0  # Offset from optimal pressure (+/- this value)
PRESSURE_FRONT_OPTIMAL = 32.0  # Front tyre optimal pressure
PRESSURE_REAR_OPTIMAL = 34.0  # Rear tyre optimal pressure
# Low/high thresholds are now calculated as optimal +/- offset

# Tyre Temperature thresholds (Celsius)
TYRE_TEMP_COLD = 40.0  # Blue
TYRE_TEMP_OPTIMAL = 80.0  # Green
TYRE_TEMP_OPTIMAL_RANGE = 7.5  # Range around optimal temperature
TYRE_TEMP_HOT = 100.0  # Yellow to red
TYRE_TEMP_HOT_TO_BLACK = 50.0  # Range over which red fades to black after HOT


# Brake temperature thresholds
BRAKE_TEMP_MIN = 75.0  # Min temperature for scale
BRAKE_TEMP_OPTIMAL = 200.0  # Optimal operating temperature
BRAKE_TEMP_OPTIMAL_RANGE = 50.0  # Range around optimal temperature
BRAKE_TEMP_HOT = 300.0  # Yellow to red
BRAKE_TEMP_HOT_TO_BLACK = 100.0  # Range over which red fades to black after HOT


# NeoKey 1x4 button mappings
BUTTON_BRIGHTNESS_CYCLE = 0  # Cycle through brightness presets
BUTTON_PAGE_SETTINGS = 1  # Toggle page-specific settings (context-sensitive per page)
BUTTON_CATEGORY_SWITCH = 2  # Switch within category (camera↔camera OR UI page↔UI page)
BUTTON_VIEW_MODE = 3  # Switch between categories (camera pages ↔ UI pages)

# I2C settings
I2C_BUS = 1  # Default I2C bus on Raspberry Pi 4
I2C_MUX_ADDRESS = 0x70  # TCA9548A default address
I2C_MUX_RESET_PIN = 17  # GPIO pin for TCA9548A reset (active-low, uses internal pull-up)
I2C_MUX_RESET_FAILURES = 3  # Consecutive failures before triggering mux reset

# ==============================================================================
# IMU Configuration (for G-meter)
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

# G-meter display settings
GMETER_MAX_G = 2.0  # Maximum G-force to display (±2g is typical for road cars)
GMETER_HISTORY_SECONDS = 5.0  # How many seconds of history to show on trace
ADS_ADDRESS = 0x48  # ADS1115/ADS1015 default address


def validate_display_dimensions(width, height):
    """
    Validate display dimensions for security and sanity.

    Args:
        width: Display width in pixels
        height: Display height in pixels

    Returns:
        tuple: (validated_width, validated_height)

    Raises:
        ValueError: If dimensions are invalid
    """
    # Check types
    if not isinstance(width, (int, float)):
        raise ValueError(f"Display width must be numeric, got {type(width).__name__}")
    if not isinstance(height, (int, float)):
        raise ValueError(f"Display height must be numeric, got {type(height).__name__}")

    # Convert to int
    width = int(width)
    height = int(height)

    # Validate ranges (reasonable display sizes)
    # Min: QVGA (320x240), Max: 8K (7680x4320)
    if not (320 <= width <= 7680):
        raise ValueError(f"Display width {width} out of valid range (320-7680)")
    if not (240 <= height <= 4320):
        raise ValueError(f"Display height {height} out of valid range (240-4320)")

    # Check for potential division by zero
    if width == 0 or height == 0:
        raise ValueError("Display dimensions cannot be zero")

    return width, height


def apply_emissivity_correction(temp_celsius: float, emissivity: float) -> float:
    """
    Apply emissivity correction to infrared temperature reading.

    MLX sensors assume emissivity of 1.0 (perfect black body). Real materials
    have lower emissivity, causing the sensor to read lower than actual temperature.

    Stefan-Boltzmann law: Power ∝ ε * T^4
    Therefore: T_actual = T_measured / ε^0.25

    Args:
        temp_celsius: Temperature reading from sensor in Celsius (-40 to 380°C for MLX sensors)
        emissivity: Material emissivity (0.0-1.0)

    Returns:
        float: Corrected temperature in Celsius

    Raises:
        ValueError: If temperature is outside sensor range or emissivity is invalid

    Note:
        - Emissivity of 1.0 returns the original temperature (no correction)
        - Lower emissivity results in higher corrected temperature
        - Calculation done in Kelvin, returned in Celsius
    """
    # Validate temperature is within MLX sensor range
    if not (-40 <= temp_celsius <= 380):
        raise ValueError(
            f"Temperature {temp_celsius:.1f}°C outside MLX sensor range (-40 to 380°C)"
        )

    # Validate emissivity is in valid range
    if not (0.0 < emissivity <= 1.0):
        raise ValueError(
            f"Emissivity {emissivity:.3f} must be in range (0.0, 1.0]"
        )

    # No correction needed for perfect black body (using epsilon comparison for float)
    if abs(emissivity - 1.0) < 1e-9:
        return temp_celsius

    # Convert to Kelvin for calculation
    temp_kelvin = temp_celsius + 273.15

    # Apply correction: T_actual = T_measured / ε^0.25
    corrected_kelvin = temp_kelvin / (emissivity ** 0.25)

    # Convert back to Celsius
    corrected_celsius = corrected_kelvin - 273.15

    return corrected_celsius


try:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            display_config = json.load(f)
            raw_width = display_config.get("width", REFERENCE_WIDTH)
            raw_height = display_config.get("height", REFERENCE_HEIGHT)

            # Validate dimensions
            DISPLAY_WIDTH, DISPLAY_HEIGHT = validate_display_dimensions(raw_width, raw_height)
            print(f"Loaded display config: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    else:
        # Create default config file if it doesn't exist
        DISPLAY_WIDTH, DISPLAY_HEIGHT = validate_display_dimensions(REFERENCE_WIDTH, REFERENCE_HEIGHT)
        default_config = {
            "width": DISPLAY_WIDTH,
            "height": DISPLAY_HEIGHT,
            "notes": "Default resolution. Change values to match your HDMI display resolution.",
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)
        print(f"Created default display config at {CONFIG_FILE}: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
except ValueError as e:
    # Validation error - use safe defaults
    print(f"Invalid display config: {e}. Using safe defaults.")
    DISPLAY_WIDTH = REFERENCE_WIDTH
    DISPLAY_HEIGHT = REFERENCE_HEIGHT
except Exception as e:
    # Other errors (file I/O, JSON parsing, etc.)
    print(f"Error loading display config: {e}. Using reference values.")
    DISPLAY_WIDTH = REFERENCE_WIDTH
    DISPLAY_HEIGHT = REFERENCE_HEIGHT

# Calculate scaling factors based on reference resolution
SCALE_X = DISPLAY_WIDTH / REFERENCE_WIDTH
SCALE_Y = DISPLAY_HEIGHT / REFERENCE_HEIGHT


# Function to scale a position tuple
def scale_position(pos):
    """Scale a position tuple (x, y) according to the current display resolution."""
    return (int(pos[0] * SCALE_X), int(pos[1] * SCALE_Y))


# Function to scale a size tuple
def scale_size(size):
    """Scale a size tuple (width, height) according to the current display resolution."""
    return (int(size[0] * SCALE_X), int(size[1] * SCALE_Y))


# Font settings
FONT_SIZE_LARGE = int(60 * min(SCALE_X, SCALE_Y))
FONT_SIZE_MEDARGE = int(45 * min(SCALE_X, SCALE_Y))
FONT_SIZE_MEDIUM = int(24 * min(SCALE_X, SCALE_Y))
FONT_SIZE_SMALL = int(18 * min(SCALE_X, SCALE_Y))


# Paths
# TEMPLATE_PATH = "assets/template.png"
OVERLAY_PATH = "assets/overlay.png"


# Icons
TYRE_ICON_PATH = "assets/icons/icons8-tire-60.png"
BRAKE_ICON_PATH = "assets/icons/icons8-brake-discs-60.png"
ICON_SIZE = scale_size((40, 40))
TYRE_ICON_POSITION = scale_position((725, 35))
BRAKE_ICON_POSITION = scale_position((35, 35))


# Colors (RGB)
GREY = (128, 128, 128)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
BLUE = (0, 0, 255)


# Brake temperature positions
BRAKE_POSITIONS = {
    "FL": scale_position((379, 136)),
    "FR": scale_position((420, 136)),
    "RL": scale_position((379, 344)),
    "RR": scale_position((420, 344)),
}

# Tyre Temperature Sensor Configuration
# Per-tyre sensor type selection
# Options: "pico" for Pico I2C slave with MLX90640, "mlx90614" for single-point IR sensor
TYRE_SENSOR_TYPES = {
    "FL": "pico",  # Front Left
    "FR": "pico",  # Front Right
    "RL": "pico",  # Rear Left
    "RR": "pico",  # Rear Right
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

# I2C Multiplexer Channel Assignments
# Maps tyre positions to I2C multiplexer channels for each sensor type

# Pico I2C slave modules (MLX90640 thermal cameras)
PICO_MUX_CHANNELS = {
    "FL": 0,  # Front Left on channel 0
    "FR": 1,  # Front Right on channel 1
    "RL": 2,  # Rear Left on channel 2
    "RR": 3,  # Rear Right on channel 3
}

# MLX90614 single-point IR sensors
MLX90614_MUX_CHANNELS = {
    "FL": 0,  # Front Left on channel 0
    "FR": 1,  # Front Right on channel 1
    "RL": 2,  # Rear Left on channel 2
    "RR": 3,  # Rear Right on channel 3
}


# TPMS positions dynamically calculated based on MLX positions
# The pressure text is centered above each tyre's thermal display
TPMS_POSITIONS = {
    # Calculate pressure position as centered horizontally above the MLX display
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
# OBD2 Configuration (for vehicle speed)
# ==============================================================================

# Enable/disable OBD2 speed reading
OBD_ENABLED = True  # Set to False to disable OBD2 speed

# OBD2 CAN configuration
# Available interfaces: can_b1_0, can_b1_1, can_b2_0, can_b2_1
# OBD-II is connected to can_b2_1 (Board 2, CAN_1 connector)
OBD_CHANNEL = "can_b2_1"  # CAN channel for OBD2 data
OBD_BITRATE = 500000  # Standard OBD2 bitrate (500 kbps)

# ==============================================================================
# Ford Hybrid Configuration (for battery state of charge)
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

# Status bar configuration
STATUS_BAR_HEIGHT = 20  # Height of status bars in pixels (scaled)
STATUS_BAR_ENABLED = True  # Show status bars at top and bottom

# ==============================================================================
# Radar Configuration (Optional)
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

# ==============================================================================
# Brake Temperature Sensor Configuration
# ==============================================================================

# Per-corner brake sensor type selection
# Options: "adc" for IR sensors via ADS1115, "mlx90614" for single-point IR, "obd" for CAN/OBD-II
BRAKE_SENSOR_TYPES = {
    "FL": "mlx90614",  # Front Left - MLX90614 IR sensor
    "FR": "adc",  # Front Right - ADC IR sensor
    "RL": "adc",  # Rear Left - ADC IR sensor
    "RR": "adc",  # Rear Right - ADC IR sensor
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

# OBD/CAN brake temperature mapping
# Used when sensor type is "obd"
# Maps brake positions to CAN signal names (if available)
OBD_BRAKE_SIGNALS = {
    "FL": None,  # Not typically available via OBD-II
    "FR": None,  # Most cars don't broadcast brake temps
    "RL": None,  # Would need custom CAN implementation
    "RR": None,  # or aftermarket ECU
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
