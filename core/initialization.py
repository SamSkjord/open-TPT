"""
Initialization mixin for openTPT.

Provides hardware subsystem initialization with splash screen progress.
"""

import logging
import os
import time

import pygame

from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    FONT_PATH,
    # Radar configuration
    RADAR_ENABLED,
    RADAR_CHANNEL,
    CAR_CHANNEL,
    RADAR_INTERFACE,
    RADAR_BITRATE,
    RADAR_DBC,
    CONTROL_DBC,
    RADAR_TRACK_TIMEOUT,
    # Encoder configuration
    ENCODER_ENABLED,
    ENCODER_I2C_ADDRESS,
    ENCODER_POLL_RATE,
    ENCODER_LONG_PRESS_MS,
    ENCODER_BRIGHTNESS_STEP,
    # NeoDriver configuration
    NEODRIVER_ENABLED,
    NEODRIVER_I2C_ADDRESS,
    NEODRIVER_NUM_PIXELS,
    NEODRIVER_BRIGHTNESS,
    NEODRIVER_DEFAULT_MODE,
    NEODRIVER_DEFAULT_DIRECTION,
    NEODRIVER_MAX_RPM,
    NEODRIVER_SHIFT_RPM,
    NEODRIVER_START_RPM,
)
from utils.settings import get_settings

# Import handlers
from gui.camera import Camera
from gui.input_threaded import InputHandlerThreaded as InputHandler
from gui.encoder_input import EncoderInputHandler
from gui.menu import MenuSystem
from hardware.neodriver_handler import NeoDriverHandler, NeoDriverMode, NeoDriverDirection
from hardware.tpms_input_optimized import TPMSHandler
from hardware.unified_corner_handler import UnifiedCornerHandler

logger = logging.getLogger('openTPT.init')

# Boot timing reference (will be set by main.py)
_boot_start = None


def set_boot_start(start_time):
    """Set boot start time for timing logs."""
    global _boot_start
    _boot_start = start_time


class InitializationMixin:
    """Mixin providing hardware initialization methods."""

    def _show_splash(self, status_text, progress=None):
        """Show splash screen with optional progress bar."""
        # Fill with dark background
        self.screen.fill((20, 20, 30))

        # Try to load and display splash image
        try:
            splash_path = os.path.join(os.path.dirname(__file__), "..", "assets", "splash.png")
            if os.path.exists(splash_path):
                splash_img = pygame.image.load(splash_path)
                # Scale to fit screen while maintaining aspect ratio
                img_rect = splash_img.get_rect()
                scale = min(DISPLAY_WIDTH / img_rect.width, DISPLAY_HEIGHT / img_rect.height) * 0.6
                new_size = (int(img_rect.width * scale), int(img_rect.height * scale))
                splash_img = pygame.transform.smoothscale(splash_img, new_size)
                img_rect = splash_img.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2 - 50))
                self.screen.blit(splash_img, img_rect)
        except (pygame.error, FileNotFoundError, IOError, OSError):
            pass  # Continue without splash image

        # Draw status text
        try:
            font = pygame.font.Font(FONT_PATH, 24)
        except (pygame.error, FileNotFoundError, IOError, OSError):
            font = pygame.font.Font(None, 24)
        text_surface = font.render(status_text, True, (200, 200, 200))
        text_rect = text_surface.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT - 80))
        self.screen.blit(text_surface, text_rect)

        # Draw progress bar if provided
        if progress is not None:
            bar_width = 300
            bar_height = 8
            bar_x = (DISPLAY_WIDTH - bar_width) // 2
            bar_y = DISPLAY_HEIGHT - 50
            # Background
            pygame.draw.rect(self.screen, (60, 60, 70), (bar_x, bar_y, bar_width, bar_height))
            # Progress
            fill_width = int(bar_width * min(1.0, max(0.0, progress)))
            if fill_width > 0:
                pygame.draw.rect(self.screen, (0, 180, 220), (bar_x, bar_y, fill_width, bar_height))

        pygame.display.flip()

    def _init_subsystems(self):
        """Initialise the hardware subsystems."""
        global _boot_start
        if _boot_start is None:
            _boot_start = time.time()

        # Import optional handlers
        try:
            from hardware.radar_handler import RadarHandler
            RADAR_AVAILABLE = True
        except ImportError:
            RADAR_AVAILABLE = False
            RadarHandler = None

        try:
            from hardware.imu_handler import IMUHandler
            from utils.config import IMU_ENABLED
            IMU_AVAILABLE = True
        except ImportError:
            IMU_AVAILABLE = False
            IMUHandler = None
            IMU_ENABLED = False

        try:
            from hardware.obd2_handler import OBD2Handler
            from utils.config import OBD_ENABLED
            OBD2_AVAILABLE = True
        except ImportError:
            OBD2_AVAILABLE = False
            OBD2Handler = None
            OBD_ENABLED = False

        try:
            from hardware.gps_handler import GPSHandler
            from utils.config import GPS_ENABLED
            GPS_AVAILABLE = True
        except ImportError:
            GPS_AVAILABLE = False
            GPSHandler = None
            GPS_ENABLED = False

        try:
            from hardware.ford_hybrid_handler import FordHybridHandler
            from utils.config import FORD_HYBRID_ENABLED
            FORD_HYBRID_AVAILABLE = True
        except ImportError:
            FORD_HYBRID_AVAILABLE = False
            FordHybridHandler = None
            FORD_HYBRID_ENABLED = False

        try:
            from hardware.lap_timing_handler import LapTimingHandler
            from utils.config import LAP_TIMING_ENABLED
            LAP_TIMING_AVAILABLE = True
        except ImportError as e:
            LAP_TIMING_AVAILABLE = False
            LapTimingHandler = None
            LAP_TIMING_ENABLED = False
            logger.warning("Lap timing not available: %s", e)

        try:
            from utils.fuel_tracker import FuelTracker
            from utils.config import FUEL_TRACKING_ENABLED
            FUEL_TRACKING_AVAILABLE = True
        except ImportError as e:
            FUEL_TRACKING_AVAILABLE = False
            FuelTracker = None
            FUEL_TRACKING_ENABLED = False
            logger.warning("Fuel tracking not available: %s", e)

        try:
            from hardware.copilot_handler import CoPilotHandler
            from utils.config import (
                COPILOT_ENABLED,
                COPILOT_MAP_DIR,
                COPILOT_LOOKAHEAD_M,
                COPILOT_UPDATE_INTERVAL_S,
                COPILOT_AUDIO_ENABLED,
                COPILOT_AUDIO_VOLUME,
            )
            COPILOT_AVAILABLE = True
        except ImportError as e:
            COPILOT_AVAILABLE = False
            CoPilotHandler = None
            COPILOT_ENABLED = False
            logger.debug("CoPilot not available: %s", e)

        # Initialise radar handler (optional)
        self._show_splash("Initialising radar...", 0.05)
        if RADAR_ENABLED and RADAR_AVAILABLE and RadarHandler:
            try:
                # Load radar enabled state from persistent settings (default True)
                settings = get_settings()
                radar_enabled = settings.get("radar.enabled", True)
                self.radar = RadarHandler(
                    radar_channel=RADAR_CHANNEL,
                    car_channel=CAR_CHANNEL,
                    interface=RADAR_INTERFACE,
                    bitrate=RADAR_BITRATE,
                    radar_dbc=RADAR_DBC,
                    control_dbc=CONTROL_DBC,
                    track_timeout=RADAR_TRACK_TIMEOUT,
                    enabled=radar_enabled,
                )
                self.radar.start()
                logger.info("Radar overlay enabled")
            except (IOError, OSError, RuntimeError, ValueError) as e:
                logger.warning("Could not initialise radar: %s", e)
                self.radar = None

        # Initialise camera (with optional radar)
        self._show_splash("Initialising cameras...", 0.15)
        logger.debug("camera init start t=%.1fs", time.time()-_boot_start)
        self.camera = Camera(self.screen, radar_handler=self.radar)
        logger.debug("camera init done t=%.1fs", time.time()-_boot_start)

        # Initialise input handler (NeoKey)
        self._show_splash("Initialising buttons...", 0.25)
        logger.debug("input init start t=%.1fs", time.time()-_boot_start)
        self.input_handler = InputHandler(self.camera)
        logger.debug("input init done t=%.1fs", time.time()-_boot_start)

        # Initialise encoder input handler (optional)
        self._show_splash("Initialising encoder...", 0.35)
        logger.debug("encoder init start t=%.1fs", time.time()-_boot_start)
        self.encoder = None
        if ENCODER_ENABLED:
            try:
                self.encoder = EncoderInputHandler(
                    i2c_address=ENCODER_I2C_ADDRESS,
                    poll_rate=ENCODER_POLL_RATE,
                    long_press_ms=ENCODER_LONG_PRESS_MS,
                    brightness_step=ENCODER_BRIGHTNESS_STEP,
                )
                if self.encoder.is_available():
                    logger.info("Encoder input handler initialised")
                else:
                    logger.warning("Encoder not detected")
                    self.encoder = None
            except (IOError, OSError, RuntimeError, ValueError) as e:
                logger.warning("Could not initialise encoder: %s", e)
                self.encoder = None
        logger.debug("encoder init done t=%.1fs", time.time()-_boot_start)

        # Initialise NeoDriver LED strip (optional)
        self._show_splash("Initialising LED strip...", 0.45)
        logger.debug("neodriver init start t=%.1fs", time.time()-_boot_start)
        self.neodriver = None
        if NEODRIVER_ENABLED:
            try:
                # Convert mode string to enum
                mode_map = {
                    "off": NeoDriverMode.OFF,
                    "delta": NeoDriverMode.DELTA,
                    "overtake": NeoDriverMode.OVERTAKE,
                    "shift": NeoDriverMode.SHIFT,
                    "rainbow": NeoDriverMode.RAINBOW,
                }
                direction_map = {
                    "left_right": NeoDriverDirection.LEFT_RIGHT,
                    "right_left": NeoDriverDirection.RIGHT_LEFT,
                    "centre_out": NeoDriverDirection.CENTRE_OUT,
                    "edges_in": NeoDriverDirection.EDGES_IN,
                }
                default_mode = mode_map.get(NEODRIVER_DEFAULT_MODE, NeoDriverMode.OFF)
                default_direction = direction_map.get(NEODRIVER_DEFAULT_DIRECTION, NeoDriverDirection.CENTRE_OUT)

                self.neodriver = NeoDriverHandler(
                    i2c_address=NEODRIVER_I2C_ADDRESS,
                    num_pixels=NEODRIVER_NUM_PIXELS,
                    brightness=NEODRIVER_BRIGHTNESS,
                    default_mode=default_mode,
                    default_direction=default_direction,
                    max_rpm=NEODRIVER_MAX_RPM,
                    shift_rpm=NEODRIVER_SHIFT_RPM,
                    start_rpm=NEODRIVER_START_RPM,
                )
                if self.neodriver.is_available():
                    self.neodriver.start()
                    logger.info("NeoDriver initialised with %d pixels, mode: %s", NEODRIVER_NUM_PIXELS, NEODRIVER_DEFAULT_MODE)
                else:
                    logger.warning("NeoDriver not detected")
                    self.neodriver = None
            except (IOError, OSError, RuntimeError, ValueError) as e:
                logger.warning("Could not initialise NeoDriver: %s", e)
                self.neodriver = None
        logger.debug("neodriver init done t=%.1fs", time.time()-_boot_start)

        # Create hardware handlers
        self._show_splash("Initialising sensors...", 0.55)
        self.tpms = TPMSHandler()
        logger.debug("tpms init done t=%.1fs", time.time()-_boot_start)
        self.corner_sensors = UnifiedCornerHandler()  # Unified tyre+brake handler
        logger.debug("corner sensors init done t=%.1fs", time.time()-_boot_start)

        # Aliases for backward compatibility
        self.thermal = self.corner_sensors  # Tyre data access
        self.brakes = self.corner_sensors   # Brake data access

        # Initialise IMU handler (optional, for G-meter)
        self._show_splash("Initialising IMU...", 0.65)
        logger.debug("imu init start t=%.1fs", time.time()-_boot_start)
        if IMU_ENABLED and IMU_AVAILABLE and IMUHandler:
            try:
                self.imu = IMUHandler()
                self.imu.start()
                logger.info("IMU handler initialised for G-meter")
            except (IOError, OSError, RuntimeError, ValueError) as e:
                logger.warning("Could not initialise IMU: %s", e)
                self.imu = None

        logger.debug("imu init done t=%.1fs", time.time()-_boot_start)

        # Initialise OBD2 handler (optional, for vehicle speed)
        self._show_splash("Initialising OBD2...", 0.75)
        if OBD_ENABLED and OBD2_AVAILABLE and OBD2Handler:
            try:
                self.obd2 = OBD2Handler()
                logger.info("OBD2 handler initialised for vehicle speed")
            except (IOError, OSError, RuntimeError, ValueError) as e:
                logger.warning("Could not initialise OBD2: %s", e)
                self.obd2 = None
        else:
            self.obd2 = None

        # Initialise GPS handler (optional, for GPS speed)
        self._show_splash("Initialising GPS...", 0.78)
        if GPS_ENABLED and GPS_AVAILABLE and GPSHandler:
            try:
                self.gps = GPSHandler()
                logger.info("GPS handler initialised for speed")
            except (IOError, OSError, RuntimeError, ValueError) as e:
                logger.warning("Could not initialise GPS: %s", e)
                self.gps = None
        else:
            self.gps = None

        # Initialise Fuel Tracker (optional, requires OBD2)
        self._show_splash("Initialising fuel tracking...", 0.79)
        if FUEL_TRACKING_ENABLED and FUEL_TRACKING_AVAILABLE and FuelTracker and self.obd2:
            try:
                self.fuel_tracker = FuelTracker()
                self.fuel_display.set_tracker(self.fuel_tracker)
                logger.info("Fuel tracker initialised")
            except (IOError, OSError, RuntimeError, ValueError) as e:
                logger.warning("Could not initialise fuel tracker: %s", e)
                self.fuel_tracker = None
        else:
            self.fuel_tracker = None
            if FUEL_TRACKING_ENABLED and not self.obd2:
                logger.debug("Fuel tracking disabled: OBD2 required but not available")

        # Initialise Lap Timing handler (optional, requires GPS)
        self._show_splash("Initialising lap timing...", 0.80)
        if LAP_TIMING_ENABLED and LAP_TIMING_AVAILABLE and LapTimingHandler and self.gps:
            try:
                self.lap_timing = LapTimingHandler(gps_handler=self.gps, fuel_tracker=self.fuel_tracker)
                self.lap_timing.start()
                self.lap_timing_display.set_handler(self.lap_timing)
                logger.info("Lap timing handler initialised")
            except (IOError, OSError, RuntimeError, ValueError) as e:
                logger.warning("Could not initialise lap timing: %s", e)
                self.lap_timing = None
        else:
            self.lap_timing = None
            if LAP_TIMING_ENABLED and not self.gps:
                logger.warning("Lap timing disabled: GPS required but not available")

        # Initialise CoPilot handler (optional, requires GPS for rally callouts)
        self._show_splash("Initialising CoPilot...", 0.82)
        self.copilot = None
        if COPILOT_ENABLED and COPILOT_AVAILABLE and CoPilotHandler and self.gps:
            try:
                from pathlib import Path
                self.copilot = CoPilotHandler(
                    gps_handler=self.gps,
                    map_path=Path(COPILOT_MAP_DIR),
                    lookahead_m=COPILOT_LOOKAHEAD_M,
                    update_interval_s=COPILOT_UPDATE_INTERVAL_S,
                    audio_enabled=COPILOT_AUDIO_ENABLED,
                    audio_volume=COPILOT_AUDIO_VOLUME,
                    lap_timing_handler=self.lap_timing,
                )
                self.copilot.start()
                self.copilot_display.set_handler(self.copilot)
                logger.info("CoPilot initialised")
            except (IOError, OSError, RuntimeError, ValueError, ImportError) as e:
                logger.warning("Could not initialise CoPilot: %s", e)
                self.copilot = None
        else:
            if COPILOT_ENABLED and not self.gps:
                logger.debug("CoPilot disabled: GPS required but not available")

        # Initialise Ford Hybrid handler (optional, for battery SOC)
        if FORD_HYBRID_ENABLED and FORD_HYBRID_AVAILABLE and FordHybridHandler:
            try:
                self.ford_hybrid = FordHybridHandler()
                self.ford_hybrid.initialise()
                logger.info("Ford Hybrid handler initialised for battery SOC")
            except (IOError, OSError, RuntimeError, ValueError) as e:
                logger.warning("Could not initialise Ford Hybrid: %s", e)
                self.ford_hybrid = None
        else:
            self.ford_hybrid = None
        logger.debug("ford hybrid init done t=%.1fs", time.time()-_boot_start)

        # Initialise menu system
        self._show_splash("Initialising menu...", 0.85)
        logger.debug("menu init start t=%.1fs", time.time()-_boot_start)
        self.menu = MenuSystem(
            tpms_handler=self.tpms,
            encoder_handler=self.encoder,
            input_handler=self.input_handler,
            neodriver_handler=self.neodriver,
            imu_handler=self.imu,
            gps_handler=self.gps,
            radar_handler=self.radar,
            camera_handler=self.camera,
            lap_timing_handler=self.lap_timing,
            copilot_handler=self.copilot,
        )
        logger.debug("menu init done t=%.1fs", time.time()-_boot_start)

        # Start monitoring threads
        self._show_splash("Starting threads...", 0.95)
        logger.debug("threads starting t=%.1fs", time.time()-_boot_start)
        self.input_handler.start()  # Start NeoKey polling thread
        if self.encoder:
            self.encoder.start()  # Start encoder polling thread
        self.tpms.start()
        self.corner_sensors.start()
        self._show_splash("Ready!", 1.0)
        logger.debug("threads started t=%.1fs", time.time()-_boot_start)
