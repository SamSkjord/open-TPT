"""
Camera module for openTPT.
Handles rear-view camera display and toggling.
"""

import logging
import pygame
import numpy as np
import time
import threading
import queue

logger = logging.getLogger('openTPT.camera')

# Debug flag - set to True for verbose camera logging (impacts performance)
DEBUG_CAMERA = False

from config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    CAMERA_FPS,
    FONT_PATH,
    FONT_PATH_BOLD,
    CAMERA_REAR_MIRROR,
    CAMERA_REAR_ROTATE,
    CAMERA_FRONT_MIRROR,
    CAMERA_FRONT_ROTATE,
    CAMERA_FOV_DEGREES,
    CAMERA_FPS_UPDATE_INTERVAL_S,
    LASER_RANGER_DISPLAY_ENABLED,
    LASER_RANGER_MAX_DISPLAY_M,
    LASER_RANGER_WARN_DISTANCE_M,
    LASER_RANGER_CAUTION_DISTANCE_M,
    LASER_RANGER_DISPLAY_POSITION,
    LASER_RANGER_TEXT_SIZE,
    LASER_RANGER_TEXT_SIZES,
    LASER_RANGER_OFFSET_M,
    RADAR_DISTANCE_DISPLAY_ENABLED,
    RADAR_DISTANCE_DISPLAY_POSITION,
    RADAR_DISTANCE_TEXT_SIZE,
    RADAR_DISTANCE_TEXT_SIZES,
    RADAR_DISTANCE_MAX_DISPLAY_M,
    RADAR_DISTANCE_GAP_RED_S,
    RADAR_DISTANCE_GAP_YELLOW_S,
    RADAR_DISTANCE_MIN_SPEED_KMH,
    SCALE_X,
    SCALE_Y,
)
from utils.settings import get_settings

# Optional import - only needed for actual camera functionality
try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class Camera:
    """Camera handler for multi-camera display with optional radar overlay."""

    def __init__(self, surface, radar_handler_rear=None, radar_handler_front=None, corner_sensors=None):
        """
        Initialise the camera handler.

        Args:
            surface: The pygame surface to draw on
            radar_handler_rear: Optional radar handler for chevron overlay (rear camera)
            radar_handler_front: Optional radar handler for distance overlay (front camera)
            corner_sensors: Optional corner sensor handler (provides laser ranger for front camera)
        """
        self.surface = surface

        # Multi-camera support
        self.cameras = {
            'rear': None,
            'front': None
        }
        self.current_camera = 'rear'  # Start with rear camera
        self.active = False
        self.error_message = None
        self.frame = None

        # Radar integration
        self.radar_handler = radar_handler_rear       # Rear camera chevrons (backward compat name)
        self.radar_handler_front = radar_handler_front # Front camera distance overlay
        self.radar_overlay = None
        if radar_handler_rear and radar_handler_rear.is_enabled():
            try:
                from gui.radar_overlay import RadarOverlayRenderer
                self.radar_overlay = RadarOverlayRenderer(
                    display_width=DISPLAY_WIDTH,
                    display_height=DISPLAY_HEIGHT,
                    camera_fov=CAMERA_FOV_DEGREES,
                    mirror_output=True,  # Match camera mirroring
                )
                logger.info("Radar overlay enabled for rear camera")
            except ImportError as e:
                logger.warning("Could not load radar overlay: %s", e)

        # Corner sensors (provides laser ranger for front camera)
        self.corner_sensors = corner_sensors
        self._distance_fonts = {}  # Cache fonts per size to avoid recreation

        # Speed sources for radar distance gap calculation (wired post-init)
        self.obd2_handler = None
        self.gps_handler = None
        self._radar_distance_fonts = {}  # Cache fonts per size to avoid recreation
        if corner_sensors and corner_sensors.laser_ranger_enabled():
            logger.info("Laser ranger available for front camera overlay")

        # Threading related attributes
        self.frame_queue = queue.Queue(maxsize=2)  # Small queue for maximum performance
        self.capture_thread = None
        self.thread_running = False

        # Camera settings - compromise between quality and performance
        self.camera_width = CAMERA_WIDTH
        self.camera_height = CAMERA_HEIGHT
        self.camera_fps = CAMERA_FPS

        # FPS tracking variables
        self.frame_count = 0
        self.fps = 0
        self.last_time = time.time()
        self.update_interval = CAMERA_FPS_UPDATE_INTERVAL_S

        # Persistent settings (with config.py as defaults)
        self._settings = get_settings()

        # Camera transform settings (persistent, config.py as defaults)
        self.camera_settings = {
            'rear': {
                'mirror': self._settings.get("camera.rear.mirror", CAMERA_REAR_MIRROR),
                'rotate': self._settings.get("camera.rear.rotate", CAMERA_REAR_ROTATE),
            },
            'front': {
                'mirror': self._settings.get("camera.front.mirror", CAMERA_FRONT_MIRROR),
                'rotate': self._settings.get("camera.front.rotate", CAMERA_FRONT_ROTATE),
            },
        }

    @property
    def camera(self):
        """Get the currently active camera object."""
        return self.cameras[self.current_camera]

    @camera.setter
    def camera(self, value):
        """Set the currently active camera object."""
        self.cameras[self.current_camera] = value

    def get_mirror(self, camera_name: str = None) -> bool:
        """Get mirror setting for a camera."""
        name = camera_name or self.current_camera
        return self.camera_settings.get(name, {}).get('mirror', False)

    def set_mirror(self, value: bool, camera_name: str = None):
        """Set mirror setting for a camera."""
        name = camera_name or self.current_camera
        if name in self.camera_settings:
            self.camera_settings[name]['mirror'] = value
            self._settings.set(f"camera.{name}.mirror", value)

    def toggle_mirror(self, camera_name: str = None) -> bool:
        """Toggle mirror setting for a camera. Returns new value."""
        name = camera_name or self.current_camera
        current = self.get_mirror(name)
        self.set_mirror(not current, name)
        return not current

    def get_rotate(self, camera_name: str = None) -> int:
        """Get rotation setting for a camera (0, 90, 180, 270)."""
        name = camera_name or self.current_camera
        return self.camera_settings.get(name, {}).get('rotate', 0)

    def set_rotate(self, value: int, camera_name: str = None):
        """Set rotation setting for a camera (0, 90, 180, 270)."""
        name = camera_name or self.current_camera
        if name in self.camera_settings:
            # Normalise to valid values
            normalised = value % 360
            self.camera_settings[name]['rotate'] = normalised
            self._settings.set(f"camera.{name}.rotate", normalised)

    def cycle_rotate(self, camera_name: str = None) -> int:
        """Cycle rotation setting (0 -> 90 -> 180 -> 270 -> 0). Returns new value."""
        name = camera_name or self.current_camera
        current = self.get_rotate(name)
        new_value = (current + 90) % 360
        self.set_rotate(new_value, name)
        return new_value

    def switch_camera(self):
        """Switch between rear and front cameras."""
        if not self.active:
            return False  # Don't switch if camera view is not active

        # Save the last frame to display during transition
        last_frame = self.frame

        # Stop current camera capture thread
        was_active = self.active
        thread_stopped = True
        if was_active:
            thread_stopped = self._stop_capture_thread()

        # Only release camera if thread actually stopped (safe to do so)
        # If thread is still running, it may still be accessing the camera
        old_camera = self.current_camera
        if thread_stopped and self.cameras[old_camera]:
            logger.info("Releasing %s camera", old_camera)
            self.cameras[old_camera].release()
            self.cameras[old_camera] = None
        elif not thread_stopped and self.cameras[old_camera]:
            logger.warning("Cannot release %s camera - capture thread still running", old_camera)

        # Switch camera
        self.current_camera = 'front' if self.current_camera == 'rear' else 'rear'

        # Restore last frame during initialization to avoid checkerboard
        self.frame = last_frame

        # Initialise new camera
        camera_device = f"/dev/video-{self.current_camera}"
        logger.info("Initialising %s camera at %s", self.current_camera, camera_device)
        if not self.initialise(camera_device=camera_device):
            # Failed to initialise new camera, try to restore old one
            logger.error("Failed to initialise %s camera", self.current_camera)
            self.current_camera = old_camera
            old_device = f"/dev/video-{old_camera}"
            if self.initialise(camera_device=old_device):
                logger.info("Restored %s camera", old_camera)
                if was_active:
                    self._start_capture_thread()
            return False

        # Start capture thread with new camera
        if was_active:
            self._start_capture_thread()

        logger.info("Switched to %s camera", self.current_camera)
        return True

    def switch_to(self, camera_name: str) -> bool:
        """Switch to a specific camera ('rear' or 'front')."""
        if camera_name not in ('rear', 'front'):
            return False
        if self.current_camera == camera_name:
            return True  # Already on requested camera
        return self.switch_camera()

    def _start_capture_thread(self):
        """Start the capture thread."""
        if not self.thread_running and CV2_AVAILABLE and self.camera:
            if DEBUG_CAMERA:
                logger.debug("Starting capture thread for %s camera", self.current_camera)
                logger.debug("Camera object exists: %s", self.camera is not None)
                logger.debug("Camera is opened: %s", self.camera.isOpened() if self.camera else False)
            self.thread_running = True
            self.capture_thread = threading.Thread(
                target=self._capture_thread_function, daemon=True
            )
            self.capture_thread.start()
        elif DEBUG_CAMERA:
            logger.debug("Cannot start capture thread - thread_running=%s, CV2=%s, camera=%s",
                        self.thread_running, CV2_AVAILABLE, self.camera is not None)

    def _capture_thread_function(self):
        """Thread function that continuously captures frames from the camera."""
        logger.info("Camera capture thread started for %s camera", self.current_camera)
        if DEBUG_CAMERA:
            logger.debug("Thread running flag: %s", self.thread_running)
            logger.debug("Camera object: %s", self.camera)

        # Set camera properties for maximum performance
        self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)
        self.camera.set(cv2.CAP_PROP_FPS, self.camera_fps)
        # Note: Removed BUFFERSIZE=1 - it causes frame starvation with slow processing
        self.camera.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)

        # Set thread priority
        try:
            import os

            os.nice(-20)
        except (ImportError, OSError, PermissionError):
            pass

        logger.info("Camera configured: %dx%d @ %dfps",
                    self.camera_width, self.camera_height, self.camera_fps)
        actual_fps = self.camera.get(cv2.CAP_PROP_FPS)
        actual_width = self.camera.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_height = self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
        actual_fourcc = int(self.camera.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
        logger.info("Actual settings: %.0fx%.0f @ %sfps, codec: %s",
                   actual_width, actual_height, actual_fps, fourcc_str)

        # Pre-calculate scaling factors
        scale = min(
            DISPLAY_WIDTH / self.camera_width, DISPLAY_HEIGHT / self.camera_height
        )
        target_w = int(self.camera_width * scale)
        target_h = int(self.camera_height * scale)
        x_offset = (DISPLAY_WIDTH - target_w) // 2
        y_offset = (DISPLAY_HEIGHT - target_h) // 2
        # Skip resize if dimensions match (scale == 1.0)
        needs_resize = (target_w != self.camera_width or target_h != self.camera_height)

        # Variables for FPS tracking within the thread
        thread_frame_count = 0
        thread_start_time = time.time()

        # Profiling variables
        profile_times = {'grab': 0, 'retrieve': 0, 'transform': 0, 'cvt': 0, 'resize': 0, 'queue': 0}
        profile_count = 0

        # Debug counters
        grab_success_count = 0
        grab_fail_count = 0
        retrieve_fail_count = 0

        # Thread loop - continuously capture frames as fast as possible
        if DEBUG_CAMERA:
            logger.debug("Entering capture loop for %s camera", self.current_camera)
        while self.thread_running:
            if not self.camera.isOpened():
                self.error_message = "Camera disconnected"
                break

            # Capture frame using grab/retrieve for maximum speed
            t0 = time.time()
            if self.camera.grab():
                grab_success_count += 1
                t1 = time.time()
                profile_times['grab'] += (t1 - t0) * 1000

                ret, frame = self.camera.retrieve()
                t2 = time.time()
                profile_times['retrieve'] += (t2 - t1) * 1000

                if not ret:
                    retrieve_fail_count += 1
                    continue

                # Pre-process frame for direct rendering
                try:
                    t3 = time.time()
                    # Apply camera transforms (rotate then mirror)
                    settings = self.camera_settings.get(self.current_camera, {})
                    rotate = settings.get('rotate', 0)
                    mirror = settings.get('mirror', False)

                    # Apply rotation
                    if rotate == 90:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                    elif rotate == 180:
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    elif rotate == 270:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                    # Apply mirror (horizontal flip)
                    if mirror:
                        frame = cv2.flip(frame, 1)

                    t3b = time.time()
                    profile_times['transform'] += (t3b - t3) * 1000

                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    t4 = time.time()
                    profile_times['cvt'] += (t4 - t3b) * 1000

                    # Resize only if needed (skip when scale == 1.0)
                    if needs_resize:
                        resized_frame = cv2.resize(
                            rgb_frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST
                        )
                    else:
                        resized_frame = rgb_frame
                    t5 = time.time()
                    profile_times['resize'] += (t5 - t4) * 1000

                    # Create processed frame data for direct rendering
                    # Note: swapaxes done in render thread to keep capture thread fast
                    processed_frame = {
                        "data": resized_frame,
                        "width": target_w,
                        "height": target_h,
                        "x_offset": x_offset,
                        "y_offset": y_offset,
                    }

                    # Update queue with latest frame
                    if self.frame_queue.full():
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self.frame_queue.put(processed_frame, block=False)
                    t6 = time.time()
                    profile_times['queue'] += (t6 - t5) * 1000

                    # Track capture FPS and profiling
                    thread_frame_count += 1
                    profile_count += 1
                    thread_elapsed = time.time() - thread_start_time
                    if thread_elapsed >= 5.0:  # Log every 5 seconds
                        capture_fps = thread_frame_count / thread_elapsed
                        logger.info("%s camera capture FPS: %.1f", self.current_camera.capitalize(), capture_fps)
                        if DEBUG_CAMERA:
                            logger.debug("Grab stats - Success: %d, Fail: %d, Retrieve fail: %d",
                                        grab_success_count, grab_fail_count, retrieve_fail_count)
                            # Log profiling info
                            if profile_count > 0:
                                logger.debug("Capture profile (avg ms): grab=%.1f, retrieve=%.1f, "
                                            "transform=%.1f, cvt=%.1f, resize=%.1f, queue=%.1f",
                                            profile_times['grab']/profile_count,
                                            profile_times['retrieve']/profile_count,
                                            profile_times['transform']/profile_count,
                                            profile_times['cvt']/profile_count,
                                            profile_times['resize']/profile_count,
                                            profile_times['queue']/profile_count)
                        # Reset counters (always, to prevent overflow)
                        grab_success_count = 0
                        grab_fail_count = 0
                        retrieve_fail_count = 0
                        profile_times = {'grab': 0, 'retrieve': 0, 'transform': 0, 'cvt': 0, 'resize': 0, 'queue': 0}
                        profile_count = 0
                        thread_frame_count = 0
                        thread_start_time = time.time()

                except Exception as e:
                    logger.warning("Error processing frame: %s", e)
                    continue
            else:
                grab_fail_count += 1
                continue

        logger.info("Camera capture thread stopped for %s camera", self.current_camera)
        if DEBUG_CAMERA:
            logger.debug("Final stats - Grab success: %d, Grab fail: %d, Retrieve fail: %d",
                        grab_success_count, grab_fail_count, retrieve_fail_count)

    def initialise(self, camera_index=None, camera_device=None):
        """
        Initialise the camera with the specified device index or device path.
        Args:
            camera_index: Integer index (0-5) or None for auto-detect
            camera_device: Device path (e.g., "/dev/video-rear") or None
        """
        if not CV2_AVAILABLE:
            self.error_message = "OpenCV (cv2) not available - camera disabled"
            logger.warning(self.error_message)
            return False

        try:
            # Close existing camera for this slot
            if self.cameras[self.current_camera]:
                self.cameras[self.current_camera].release()
                self.cameras[self.current_camera] = None

            # Determine which camera to open
            camera_to_open = None

            if camera_device:
                # Use specific device path (e.g., /dev/video-rear)
                camera_to_open = camera_device
                logger.debug("Trying camera device: %s", camera_device)
            elif camera_index is not None:
                camera_to_open = camera_index
            else:
                # Auto-detect: try named devices first, then indices
                named_device = f"/dev/video-{self.current_camera}"
                test_camera = cv2.VideoCapture(named_device, cv2.CAP_V4L2)
                if test_camera.isOpened():
                    test_camera.release()
                    camera_to_open = named_device
                    logger.info("Found %s camera at %s", self.current_camera, named_device)
                else:
                    # Fall back to auto-detect by index
                    for idx in range(6):  # Try indices 0-5
                        test_camera = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                        if test_camera.isOpened():
                            test_camera.release()
                            camera_to_open = idx
                            logger.info("Auto-detected camera at index %d", idx)
                            break

            if camera_to_open is None:
                self.error_message = f"No {self.current_camera} camera found"
                logger.warning(self.error_message)
                return False

            # Use device path directly - udev symlinks provide deterministic identification
            # OpenCV will handle the symlink resolution internally
            if DEBUG_CAMERA:
                logger.debug("Opening camera at %s", camera_to_open)

            # Open camera with V4L2 backend for better performance
            self.camera = cv2.VideoCapture(camera_to_open, cv2.CAP_V4L2)

            if not self.camera.isOpened():
                self.error_message = f"Failed to open camera at index {camera_index}"
                return False

            # Configure camera - FOURCC must be set before resolution
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            self.camera.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

            self.error_message = None
            logger.info("Camera initialised successfully at index %s", camera_index)
            return True

        except Exception as e:
            self.error_message = f"Camera init error: {str(e)}"
            logger.warning("Camera initialisation failed: %s", e)
            return False

    def toggle(self):
        """Toggle the camera view on/off."""
        if not self.camera or not self.camera.isOpened():
            if not self.initialise():
                self.active = False  # Ensure consistent state on init failure
                return False

        self.active = not self.active

        if self.active:
            self._start_capture_thread()
        else:
            self._stop_capture_thread()

        return self.active

    def _stop_capture_thread(self) -> bool:
        """Stop the capture thread if it's running.

        Returns:
            True if thread stopped successfully or wasn't running,
            False if thread failed to stop within timeout.
        """
        if self.thread_running:
            self.thread_running = False
            if self.capture_thread and self.capture_thread.is_alive():
                self.capture_thread.join(timeout=1.0)
                # Check if thread actually stopped
                if self.capture_thread.is_alive():
                    logger.warning("Camera capture thread did not stop within timeout")
                    # Don't drain queue if thread still running (would race)
                    self.capture_thread = None
                    self.frame = None
                    return False  # Thread didn't stop - unsafe to release camera
            # Thread stopped - safe to drain queue
            while True:
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    break
            self.capture_thread = None
            # Clear the last frame to avoid showing stale image on next activation
            self.frame = None
        return True  # Thread stopped or wasn't running

    def close(self):
        """Close the camera and release resources."""
        self._stop_capture_thread()
        if self.camera:
            self.camera.release()
            self.camera = None
        self.active = False

    def update(self):
        """Update the camera frame."""
        if not self.active:
            return False

        result = False

        if not CV2_AVAILABLE or not self.camera:
            # Only generate test pattern if we don't have a frame yet
            # This allows smooth transitions by keeping the last frame visible
            if self.frame is None:
                self._generate_test_pattern()
                result = True
        else:
            if (
                self.thread_running
                and self.capture_thread
                and self.capture_thread.is_alive()
            ):
                try:
                    self.frame = self.frame_queue.get_nowait()
                    result = True
                except queue.Empty:
                    pass

        # Update FPS counter - only count when we got a new frame
        if result:
            self.frame_count += 1
            current_time = time.time()
            elapsed = current_time - self.last_time

            if elapsed >= self.update_interval:
                self.fps = self.frame_count / elapsed
                self.frame_count = 0
                self.last_time = current_time

        return result

    def _generate_test_pattern(self):
        """Generate a test pattern frame when camera is not available."""
        mock_width = 1280
        mock_height = 720
        frame = np.zeros((mock_height, mock_width, 3), dtype=np.uint8)

        # Simple grid pattern
        grid_size = 50
        for y in range(0, mock_height, grid_size):
            for x in range(0, mock_width, grid_size):
                if (x // grid_size + y // grid_size) % 2 == 0:
                    colour = (0, 0, 128)
                else:
                    colour = (0, 0, 64)
                frame[y : y + grid_size, x : x + grid_size] = colour

        # Add moving element
        t = int(time.time() * 2) % mock_width
        frame[:, t : t + 2] = (255, 255, 0)

        self.frame = frame

    def render(self):
        """Render the camera feed with optional radar overlay."""
        # Capture frame reference atomically (Python assignment is atomic)
        # to prevent race with capture thread modifying self.frame
        frame = self.frame

        if not self.active or frame is None:
            if self.error_message:
                font = pygame.font.Font(FONT_PATH, 24)
                text = font.render(self.error_message, True, (255, 0, 0))
                text_rect = text.get_rect(
                    center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2)
                )
                self.surface.blit(text, text_rect)
            return False

        try:
            # Use frombuffer+blit for faster rendering (39% faster than direct pixel copy)
            if isinstance(frame, dict):
                # Direct rendering from processed frame data
                frame_data = frame["data"]
                width = frame["width"]
                height = frame["height"]
                x_offset = frame["x_offset"]
                y_offset = frame["y_offset"]

                # Create surface from buffer and blit (faster than array copy)
                frame_surface = pygame.image.frombuffer(
                    frame_data.tobytes(), (width, height), 'RGB'
                )
                self.surface.blit(frame_surface, (x_offset, y_offset))

            else:
                # Fallback for test pattern or direct frames
                if not CV2_AVAILABLE:
                    rgb_frame = frame
                else:
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Calculate scaling
                h, w = rgb_frame.shape[:2]
                scale = min(DISPLAY_WIDTH / w, DISPLAY_HEIGHT / h)
                target_w = int(w * scale)
                target_h = int(h * scale)
                x_offset = (DISPLAY_WIDTH - target_w) // 2
                y_offset = (DISPLAY_HEIGHT - target_h) // 2

                # Resize and blit
                resized = cv2.resize(
                    rgb_frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST
                )
                frame_surface = pygame.image.frombuffer(
                    resized.tobytes(), (target_w, target_h), 'RGB'
                )
                self.surface.blit(frame_surface, (x_offset, y_offset))

            # Render radar overlay if enabled and visible (rear camera only)
            if (self.radar_overlay and self.radar_handler and
                    self.current_camera == 'rear' and self.radar_handler.overlay_visible):
                tracks = self.radar_handler.get_tracks()
                if tracks:
                    self.radar_overlay.render(self.surface, tracks)

            # Render distance overlay if enabled (front camera only)
            if (LASER_RANGER_DISPLAY_ENABLED and self.corner_sensors and
                    self.corner_sensors.laser_ranger_enabled() and
                    self.current_camera == 'front'):
                self._render_distance_overlay()

            # Render radar distance overlay if enabled and visible (front camera only)
            if (self.radar_handler_front and self.radar_handler_front.is_enabled() and
                    self.radar_handler_front.overlay_visible and
                    self.current_camera == 'front'):
                self._render_radar_distance_overlay()

            return True

        except Exception as e:
            self.error_message = f"Render error: {str(e)}"
            logger.warning("Camera render error: %s", e)
            return False

    def _render_distance_overlay(self):
        """Render distance overlay on front camera."""
        if not self.corner_sensors:
            return

        # Read settings fresh each frame (not cached) so menu changes apply immediately
        settings = get_settings()

        # Check if overlay is enabled in settings
        if not settings.get("laser_ranger.display_enabled", LASER_RANGER_DISPLAY_ENABLED):
            return

        distance_m = self.corner_sensors.get_laser_distance_m()
        if distance_m is None:
            return

        # Validate distance (filter invalid values from sensor errors)
        if not isinstance(distance_m, (int, float)) or distance_m < 0 or distance_m != distance_m:
            return  # NaN check: NaN != NaN

        # Apply mounting offset (sensor position to front of vehicle)
        offset_m = settings.get("laser_ranger.offset_m", LASER_RANGER_OFFSET_M)
        distance_m = distance_m - offset_m

        # Don't display if negative (object behind sensor mount point) or beyond maximum
        if distance_m < 0 or distance_m > LASER_RANGER_MAX_DISPLAY_M:
            return

        # Get and validate text size from settings
        text_size = settings.get("laser_ranger.text_size", LASER_RANGER_TEXT_SIZE)
        if text_size not in LASER_RANGER_TEXT_SIZES:
            text_size = LASER_RANGER_TEXT_SIZE  # Fall back to default
        base_font_size = LASER_RANGER_TEXT_SIZES[text_size]

        # Get or create cached font for this size (avoid recreation every frame)
        if not hasattr(self, '_distance_fonts'):
            self._distance_fonts = {}
        if text_size not in self._distance_fonts:
            font_size = int(base_font_size * min(SCALE_X, SCALE_Y))
            self._distance_fonts[text_size] = pygame.font.Font(FONT_PATH_BOLD, font_size)
        font = self._distance_fonts[text_size]

        # Choose colour based on distance
        if distance_m <= LASER_RANGER_WARN_DISTANCE_M:
            colour = (255, 0, 0)  # Red - close
        elif distance_m <= LASER_RANGER_CAUTION_DISTANCE_M:
            colour = (255, 255, 0)  # Yellow - caution
        else:
            colour = (0, 255, 0)  # Green - safe

        # Format distance text
        if distance_m < 1.0:
            text = f"{int(distance_m * 100)} cm"
        else:
            text = f"{distance_m:.1f} m"

        # Render text with shadow for visibility
        shadow = font.render(text, True, (0, 0, 0))
        text_surface = font.render(text, True, colour)

        # Get and validate position from settings
        position = settings.get("laser_ranger.display_position", LASER_RANGER_DISPLAY_POSITION)
        if position not in ("top", "bottom"):
            position = LASER_RANGER_DISPLAY_POSITION
        edge_offset = int(50 * SCALE_Y)
        shadow_offset = int(2 * SCALE_Y)  # Consistent with edge_offset scaling

        if position == "top":
            y_pos = edge_offset
        else:  # bottom
            y_pos = DISPLAY_HEIGHT - edge_offset

        text_rect = text_surface.get_rect(center=(DISPLAY_WIDTH // 2, y_pos))
        shadow_rect = shadow.get_rect(center=(DISPLAY_WIDTH // 2 + shadow_offset, y_pos + shadow_offset))

        self.surface.blit(shadow, shadow_rect)
        self.surface.blit(text_surface, text_rect)

    def is_active(self):
        """Check if camera view is currently active."""
        return self.active

    def set_speed_sources(self, obd2_handler=None, gps_handler=None):
        """Set speed data sources for radar distance gap calculation."""
        self.obd2_handler = obd2_handler
        self.gps_handler = gps_handler

    def _get_vehicle_speed_kmh(self) -> float:
        """Get current vehicle speed in km/h. Prefers OBD2, falls back to GPS."""
        if self.obd2_handler:
            try:
                speed = self.obd2_handler.get_speed_kmh()
                if speed > 0:
                    return float(speed)
            except Exception:
                pass
        if self.gps_handler:
            try:
                speed = self.gps_handler.get_speed()
                if speed > 0:
                    return float(speed)
            except Exception:
                pass
        return 0.0

    def _render_radar_distance_overlay(self):
        """Render radar distance overlay on front camera showing nearest car ahead."""
        if not self.radar_handler_front:
            return

        # Read settings fresh each frame (not cached) so menu changes apply immediately
        settings = get_settings()

        # Check if overlay is enabled in settings
        if not settings.get("radar_distance.display_enabled", RADAR_DISTANCE_DISPLAY_ENABLED):
            return

        # Get tracks and find nearest ahead (smallest positive long_dist)
        tracks = self.radar_handler_front.get_tracks()
        if not tracks:
            return

        nearest_dist = None
        nearest_rel_speed = None
        for track in tracks.values():
            long_dist = track.get("long_dist", 0)
            if long_dist > 0:
                if nearest_dist is None or long_dist < nearest_dist:
                    nearest_dist = long_dist
                    nearest_rel_speed = track.get("rel_speed", 0)

        if nearest_dist is None or nearest_dist > RADAR_DISTANCE_MAX_DISPLAY_M:
            return

        # Get vehicle speed for time gap calculation
        vehicle_speed_kmh = self._get_vehicle_speed_kmh()
        has_speed = vehicle_speed_kmh >= RADAR_DISTANCE_MIN_SPEED_KMH

        # Calculate time gap (seconds)
        time_gap_s = None
        if has_speed:
            vehicle_speed_ms = vehicle_speed_kmh / 3.6
            time_gap_s = nearest_dist / vehicle_speed_ms

        # Choose colour based on time gap (if available) or distance
        if time_gap_s is not None:
            if time_gap_s < RADAR_DISTANCE_GAP_RED_S:
                colour = (255, 0, 0)      # Red - dangerously close
            elif time_gap_s < RADAR_DISTANCE_GAP_YELLOW_S:
                colour = (255, 255, 0)    # Yellow - caution
            else:
                colour = (0, 255, 0)      # Green - safe gap
        else:
            # Fallback: distance-based colour (no speed available)
            if nearest_dist < 15.0:
                colour = (255, 0, 0)
            elif nearest_dist < 40.0:
                colour = (255, 255, 0)
            else:
                colour = (0, 255, 0)

        # Get and validate text size from settings
        text_size = settings.get("radar_distance.text_size", RADAR_DISTANCE_TEXT_SIZE)
        if text_size not in RADAR_DISTANCE_TEXT_SIZES:
            text_size = RADAR_DISTANCE_TEXT_SIZE
        base_font_size = RADAR_DISTANCE_TEXT_SIZES[text_size]

        # Get or create cached font for this size
        if text_size not in self._radar_distance_fonts:
            font_size = int(base_font_size * min(SCALE_X, SCALE_Y))
            self._radar_distance_fonts[text_size] = pygame.font.Font(FONT_PATH_BOLD, font_size)
        font = self._radar_distance_fonts[text_size]

        # Build text lines
        lines = []

        # Line 1: Distance (always)
        lines.append(f"{nearest_dist:.1f} m")

        # Line 2: Time gap (only when moving)
        if time_gap_s is not None:
            lines.append(f"{time_gap_s:.1f}s")

        # Line 3: Closing rate (only if significant)
        # rel_speed is relative speed in m/s (negative = closing, positive = opening)
        # Display convention: positive = closing (gap shrinking), negative = opening
        if nearest_rel_speed is not None:
            closing_kmh = -nearest_rel_speed * 3.6  # Negate: rel_speed negative = closing
            if abs(closing_kmh) >= 0.5:
                sign = "+" if closing_kmh > 0 else ""
                lines.append(f"{sign}{closing_kmh:.1f} km/h")

        # Position from settings
        position = settings.get("radar_distance.display_position", RADAR_DISTANCE_DISPLAY_POSITION)
        if position not in ("top", "bottom"):
            position = RADAR_DISTANCE_DISPLAY_POSITION
        edge_offset = int(50 * SCALE_Y)
        shadow_offset = int(2 * SCALE_Y)
        line_spacing = int(base_font_size * min(SCALE_X, SCALE_Y) * 1.1)

        # Calculate starting Y based on position
        if position == "top":
            start_y = edge_offset
        else:
            # Stack upward from bottom
            start_y = DISPLAY_HEIGHT - edge_offset - (len(lines) - 1) * line_spacing

        # Render each line
        for i, text in enumerate(lines):
            y_pos = start_y + i * line_spacing

            shadow_surface = font.render(text, True, (0, 0, 0))
            text_surface = font.render(text, True, colour)

            text_rect = text_surface.get_rect(center=(DISPLAY_WIDTH // 2, y_pos))
            shadow_rect = shadow_surface.get_rect(
                center=(DISPLAY_WIDTH // 2 + shadow_offset, y_pos + shadow_offset)
            )

            self.surface.blit(shadow_surface, shadow_rect)
            self.surface.blit(text_surface, text_rect)
