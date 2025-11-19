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
ROTATION = 90  # Degrees: 0, 90, 180, 270


# Unit settings
# Temperature unit: 'C' for Celsius, 'F' for Fahrenheit
TEMP_UNIT = "C"
# Pressure unit: 'PSI', 'BAR', or 'KPA'
PRESSURE_UNIT = "PSI"

CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30

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
BUTTON_BRIGHTNESS_UP = 0
BUTTON_BRIGHTNESS_DOWN = 1
BUTTON_CAMERA_TOGGLE = 2
BUTTON_RESERVED = 3

# I2C settings
I2C_BUS = 1  # Default I2C bus on Raspberry Pi 4
I2C_MUX_ADDRESS = 0x70  # TCA9548A default address
ADS_ADDRESS = 0x48  # ADS1115/ADS1015 default address


try:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            display_config = json.load(f)
            DISPLAY_WIDTH = display_config.get("width", REFERENCE_WIDTH)
            DISPLAY_HEIGHT = display_config.get("height", REFERENCE_HEIGHT)
    else:
        # Create default config file if it doesn't exist
        default_config = {
            "width": REFERENCE_WIDTH,
            "height": REFERENCE_HEIGHT,
            "notes": "Default resolution. Change values to match your HDMI display resolution.",
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)
        DISPLAY_WIDTH = REFERENCE_WIDTH
        DISPLAY_HEIGHT = REFERENCE_HEIGHT
        print(f"Created default display config at {CONFIG_FILE}")
except Exception as e:
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
    "FL": "pico",      # Front Left
    "FR": "pico",      # Front Right
    "RL": "pico",      # Rear Left
    "RR": "pico",      # Rear Right
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
            MLX_POSITIONS["FL"][1] - int(18 * SCALE_Y),
        ),
        "temp": (MLX_POSITIONS["FL"][0], MLX_POSITIONS["FL"][1] - int(10 * SCALE_Y)),
    },
    "FR": {
        "pressure": (
            MLX_POSITIONS["FR"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["FR"][1] - int(18 * SCALE_Y),
        ),
        "temp": (MLX_POSITIONS["FR"][0], MLX_POSITIONS["FR"][1] - int(10 * SCALE_Y)),
    },
    "RL": {
        "pressure": (
            MLX_POSITIONS["RL"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["RL"][1] + int(195 * SCALE_Y),
        ),
        "temp": (MLX_POSITIONS["RL"][0], MLX_POSITIONS["RL"][1] - int(10 * SCALE_Y)),
    },
    "RR": {
        "pressure": (
            MLX_POSITIONS["RR"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["RR"][1] + int(195 * SCALE_Y),
        ),
        "temp": (MLX_POSITIONS["RR"][0], MLX_POSITIONS["RR"][1] - int(10 * SCALE_Y)),
    },
}

# ==============================================================================
# Radar Configuration (Optional)
# ==============================================================================

# Enable/disable radar overlay
RADAR_ENABLED = False  # Set to True to enable radar overlay on camera

# Toyota radar CAN configuration
RADAR_CHANNEL = "can0"  # CAN channel for radar data
CAR_CHANNEL = "can1"    # CAN channel for car keep-alive
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
