"""
Configuration settings for the openTPT system.
Contains constants for display, positions, colors, and thresholds.
"""

# Display settings
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480
FPS_TARGET = 60
DEFAULT_BRIGHTNESS = 0.8  # 0.0 to 1.0

# Unit settings
# Temperature unit: 'C' for Celsius, 'F' for Fahrenheit
TEMP_UNIT = "C"
# Pressure unit: 'PSI', 'BAR', or 'KPA'
PRESSURE_UNIT = "PSI"

# Note: The thresholds below are set according to the chosen units above.
# If you change the units, you should also adjust these thresholds appropriately.
# For reference:
# - Temperature conversion: F = (C * 9/5) + 32
# - Pressure conversion: 1 PSI = 0.0689476 BAR = 6.89476 kPa

# Tyre Pressure thresholds
PRESSURE_LOW = 28.0
PRESSURE_OPTIMAL = 32.0
PRESSURE_HIGH = 36.0

# Tyre Temperature thresholds (Celsius)
TEMP_COLD = 40.0  # Blue
TEMP_OPTIMAL = 80.0  # Green
TEMP_HOT = 100.0  # Yellow
TEMP_DANGER = 120.0  # Red

# Brake temperature thresholds
BRAKE_TEMP_MIN = 100.0  # Min temperature for scale
BRAKE_TEMP_MAX = 800.0  # Max temperature for scale
BRAKE_OPTIMAL = 400.0  # Optimal operating temperature


# NeoKey 1x4 button mappings
BUTTON_BRIGHTNESS_UP = 0
BUTTON_BRIGHTNESS_DOWN = 1
BUTTON_CAMERA_TOGGLE = 2
BUTTON_RESERVED = 3

# Mock mode settings
MOCK_MODE = True  # Set to True to enable mock data without hardware
MOCK_PRESSURE_VARIANCE = 2.0  # Random variance for mock pressure values
MOCK_TEMP_VARIANCE = 5.0  # Random variance for mock temperature values

# I2C settings
I2C_BUS = 1  # Default I2C bus on Raspberry Pi 4
I2C_MUX_ADDRESS = 0x70  # TCA9548A default address
ADS_ADDRESS = 0x48  # ADS1115/ADS1015 default address

# Font settings
FONT_SIZE_LARGE = 60
FONT_SIZE_MEDIUM = 24
FONT_SIZE_SMALL = 18


# Paths
# TEMPLATE_PATH = "assets/template.png"
OVERLAY_PATH = "assets/overlay.png"


# Icons
TYRE_ICON_PATH = "assets/icons/icons8-tire-60.png"
BRAKE_ICON_PATH = "assets/icons/icons8-brake-discs-60.png"
ICON_SIZE = (40, 40)
TYRE_ICON_POSITION = (725, 35)
BRAKE_ICON_POSITION = (35, 35)


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
    "FL": (379, 136),
    "FR": (420, 136),
    "RL": (379, 344),
    "RR": (420, 344),
}

# MLX90640 thermal camera settings
MLX_WIDTH = 32
MLX_HEIGHT = 24
MLX_POSITIONS = {
    "FL": (206, 50),
    "FR": (443, 50),
    "RL": (206, 258),
    "RR": (443, 258),
}
MLX_DISPLAY_WIDTH = 150  # Width of displayed heatmap - to cover the complete tire width
MLX_DISPLAY_HEIGHT = 172  # Height of displayed heatmap

# TPMS positions dynamically calculated based on MLX positions
# The pressure text is centered above each tire's thermal display
TPMS_POSITIONS = {
    # Calculate pressure position as centered horizontally above the MLX display
    "FL": {
        "pressure": (
            MLX_POSITIONS["FL"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["FL"][1] - 18,
        ),
        "temp": (MLX_POSITIONS["FL"][0], MLX_POSITIONS["FL"][1] - 10),
    },
    "FR": {
        "pressure": (
            MLX_POSITIONS["FR"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["FR"][1] - 18,
        ),
        "temp": (MLX_POSITIONS["FR"][0], MLX_POSITIONS["FR"][1] - 10),
    },
    "RL": {
        "pressure": (
            MLX_POSITIONS["RL"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["RL"][1] + 195,
        ),
        "temp": (MLX_POSITIONS["RL"][0], MLX_POSITIONS["RL"][1] - 10),
    },
    "RR": {
        "pressure": (
            MLX_POSITIONS["RR"][0] + MLX_DISPLAY_WIDTH // 2,
            MLX_POSITIONS["RR"][1] + 195,
        ),
        "temp": (MLX_POSITIONS["RR"][0], MLX_POSITIONS["RR"][1] - 10),
    },
}
