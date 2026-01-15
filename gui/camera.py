"""
Camera module for openTPT.
Handles rear-view camera display and toggling.
"""

import pygame
import numpy as np
import time
import threading
import queue

# Debug flag - set to True for verbose camera logging (impacts performance)
DEBUG_CAMERA = False

from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    CAMERA_FPS,
    FONT_PATH,
    CAMERA_REAR_MIRROR,
    CAMERA_REAR_ROTATE,
    CAMERA_FRONT_MIRROR,
    CAMERA_FRONT_ROTATE,
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

    def __init__(self, surface, radar_handler=None):
        """
        Initialise the camera handler.

        Args:
            surface: The pygame surface to draw on
            radar_handler: Optional radar handler for overlay (rear camera only)
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

        # Radar integration (rear camera only)
        self.radar_handler = radar_handler
        self.radar_overlay = None
        if radar_handler and radar_handler.is_enabled():
            try:
                from gui.radar_overlay import RadarOverlayRenderer
                self.radar_overlay = RadarOverlayRenderer(
                    display_width=DISPLAY_WIDTH,
                    display_height=DISPLAY_HEIGHT,
                    camera_fov=106.0,  # Adjust based on your camera
                    mirror_output=True,  # Match camera mirroring
                )
                print("Radar overlay enabled for rear camera")
            except ImportError as e:
                print(f"Warning: Could not load radar overlay: {e}")

        # Threading related attributes
        self.frame_queue = queue.Queue(maxsize=2)  # Small queue for maximum performance
        self.capture_thread = None
        self.thread_running = False

        # Camera settings - compromise between quality and performance
        self.camera_width = CAMERA_WIDTH
        self.camera_height = CAMERA_HEIGHT
        self.camera_fps = CAMERA_FPS

        # Direct rendering optimisation
        self.direct_buffer = None
        self.display_array = None

        # FPS tracking variables
        self.frame_count = 0
        self.fps = 0
        self.last_time = time.time()
        self.update_interval = 1.0  # Update FPS every 1 second

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
        if was_active:
            self._stop_capture_thread()

        # Release old camera to free up the device
        old_camera = self.current_camera
        if self.cameras[old_camera]:
            print(f"Releasing {old_camera} camera")
            self.cameras[old_camera].release()
            self.cameras[old_camera] = None

        # Switch camera
        self.current_camera = 'front' if self.current_camera == 'rear' else 'rear'

        # Restore last frame during initialization to avoid checkerboard
        self.frame = last_frame

        # Initialize new camera
        camera_device = f"/dev/video-{self.current_camera}"
        print(f"Initializing {self.current_camera} camera at {camera_device}")
        if not self.initialize(camera_device=camera_device):
            # Failed to initialize new camera, try to restore old one
            print(f"Failed to initialize {self.current_camera} camera")
            self.current_camera = old_camera
            old_device = f"/dev/video-{old_camera}"
            if self.initialize(camera_device=old_device):
                print(f"Restored {old_camera} camera")
                if was_active:
                    self._start_capture_thread()
            return False

        # Start capture thread with new camera
        if was_active:
            self._start_capture_thread()

        print(f"Switched to {self.current_camera} camera")
        return True

    def _start_capture_thread(self):
        """Start the capture thread."""
        if not self.thread_running and CV2_AVAILABLE and self.camera:
            if DEBUG_CAMERA:
                print(f"DEBUG: Starting capture thread for {self.current_camera} camera")
                print(f"DEBUG: Camera object exists: {self.camera is not None}")
                print(f"DEBUG: Camera is opened: {self.camera.isOpened() if self.camera else False}")
            self.thread_running = True
            self.capture_thread = threading.Thread(
                target=self._capture_thread_function, daemon=True
            )
            self.capture_thread.start()
        elif DEBUG_CAMERA:
            print(f"DEBUG: Cannot start capture thread - thread_running={self.thread_running}, CV2={CV2_AVAILABLE}, camera={self.camera is not None}")

    def _capture_thread_function(self):
        """Thread function that continuously captures frames from the camera."""
        print(f"Camera capture thread started for {self.current_camera} camera")
        if DEBUG_CAMERA:
            print(f"DEBUG: Thread running flag: {self.thread_running}")
            print(f"DEBUG: Camera object: {self.camera}")

        # Set camera properties for maximum performance
        self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)
        self.camera.set(cv2.CAP_PROP_FPS, self.camera_fps)
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.camera.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)

        # Set thread priority
        try:
            import os

            os.nice(-20)
        except (ImportError, OSError, PermissionError):
            pass

        print(
            f"Camera configured: {self.camera_width}x{self.camera_height} @ {self.camera_fps}fps"
        )
        actual_fps = self.camera.get(cv2.CAP_PROP_FPS)
        actual_width = self.camera.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_height = self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
        actual_fourcc = int(self.camera.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
        print(f"Actual settings: {actual_width:.0f}x{actual_height:.0f} @ {actual_fps}fps, codec: {fourcc_str}")

        # Pre-calculate scaling factors
        scale = min(
            DISPLAY_WIDTH / self.camera_width, DISPLAY_HEIGHT / self.camera_height
        )
        target_w = int(self.camera_width * scale)
        target_h = int(self.camera_height * scale)
        x_offset = (DISPLAY_WIDTH - target_w) // 2
        y_offset = (DISPLAY_HEIGHT - target_h) // 2

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
            print(f"DEBUG: Entering capture loop for {self.current_camera} camera")
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

                    # Resize using fastest interpolation
                    resized_frame = cv2.resize(
                        rgb_frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST
                    )
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
                    if thread_elapsed >= 5.0:  # Print every 5 seconds
                        capture_fps = thread_frame_count / thread_elapsed
                        print(f"{self.current_camera.capitalize()} camera capture FPS: {capture_fps:.1f}")
                        if DEBUG_CAMERA:
                            print(f"DEBUG: Grab stats - Success: {grab_success_count}, Fail: {grab_fail_count}, Retrieve fail: {retrieve_fail_count}")
                            # Print profiling info
                            if profile_count > 0:
                                print(f"  Capture profile (avg ms): grab={profile_times['grab']/profile_count:.1f}, "
                                      f"retrieve={profile_times['retrieve']/profile_count:.1f}, "
                                      f"transform={profile_times['transform']/profile_count:.1f}, "
                                      f"cvt={profile_times['cvt']/profile_count:.1f}, "
                                      f"resize={profile_times['resize']/profile_count:.1f}, "
                                      f"queue={profile_times['queue']/profile_count:.1f}")
                        # Reset counters (always, to prevent overflow)
                        grab_success_count = 0
                        grab_fail_count = 0
                        retrieve_fail_count = 0
                        profile_times = {'grab': 0, 'retrieve': 0, 'transform': 0, 'cvt': 0, 'resize': 0, 'queue': 0}
                        profile_count = 0
                        thread_frame_count = 0
                        thread_start_time = time.time()

                except Exception as e:
                    print(f"Error processing frame: {e}")
                    continue
            else:
                grab_fail_count += 1
                continue

        print(f"Camera capture thread stopped for {self.current_camera} camera")
        if DEBUG_CAMERA:
            print(f"DEBUG: Final stats - Grab success: {grab_success_count}, Grab fail: {grab_fail_count}, Retrieve fail: {retrieve_fail_count}")

    def initialize(self, camera_index=None, camera_device=None):
        """
        Initialize the camera with the specified device index or device path.
        Args:
            camera_index: Integer index (0-5) or None for auto-detect
            camera_device: Device path (e.g., "/dev/video-rear") or None
        """
        if not CV2_AVAILABLE:
            self.error_message = "OpenCV (cv2) not available - camera disabled"
            print(self.error_message)
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
                print(f"Trying camera device: {camera_device}")
            elif camera_index is not None:
                camera_to_open = camera_index
            else:
                # Auto-detect: try named devices first, then indices
                named_device = f"/dev/video-{self.current_camera}"
                test_camera = cv2.VideoCapture(named_device)
                if test_camera.isOpened():
                    test_camera.release()
                    camera_to_open = named_device
                    print(f"Found {self.current_camera} camera at {named_device}")
                else:
                    # Fall back to auto-detect by index
                    for idx in range(6):  # Try indices 0-5
                        test_camera = cv2.VideoCapture(idx)
                        if test_camera.isOpened():
                            test_camera.release()
                            camera_to_open = idx
                            print(f"Auto-detected camera at index {idx}")
                            break

            if camera_to_open is None:
                self.error_message = f"No {self.current_camera} camera found"
                print(self.error_message)
                return False

            # Use device path directly - udev symlinks provide deterministic identification
            # OpenCV will handle the symlink resolution internally
            if DEBUG_CAMERA:
                print(f"DEBUG: Opening camera at {camera_to_open}")

            # Open camera without explicit backend specification, let OpenCV choose best one
            self.camera = cv2.VideoCapture(camera_to_open)

            if not self.camera.isOpened():
                self.error_message = f"Failed to open camera at index {camera_index}"
                return False

            # Configure camera resolution and FPS
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            self.camera.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

            self.error_message = None
            print(f"Camera initialized successfully at index {camera_index}")
            return True

        except Exception as e:
            self.error_message = f"Camera init error: {str(e)}"
            return False

    def toggle(self):
        """Toggle the camera view on/off."""
        if not self.camera or not self.camera.isOpened():
            if not self.initialize():
                return False

        self.active = not self.active

        if self.active:
            self._start_capture_thread()
        else:
            self._stop_capture_thread()

        return self.active

    def _stop_capture_thread(self):
        """Stop the capture thread if it's running."""
        if self.thread_running:
            self.thread_running = False
            if self.capture_thread and self.capture_thread.is_alive():
                self.capture_thread.join(timeout=1.0)
            while not self.frame_queue.empty():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    break
            self.capture_thread = None
            # Clear the last frame to avoid showing stale image on next activation
            self.frame = None

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
                    if not self.frame_queue.empty():
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
                    color = (0, 0, 128)
                else:
                    color = (0, 0, 64)
                frame[y : y + grid_size, x : x + grid_size] = color

        # Add moving element
        t = int(time.time() * 2) % mock_width
        frame[:, t : t + 2] = (255, 255, 0)

        self.frame = frame

    def render(self):
        """Render the camera feed with optional radar overlay."""
        if not self.active or self.frame is None:
            if self.error_message:
                font = pygame.font.Font(FONT_PATH, 24)
                text = font.render(self.error_message, True, (255, 0, 0))
                text_rect = text.get_rect(
                    center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2)
                )
                self.surface.blit(text, text_rect)
            return False

        try:
            # Get direct access to the display buffer for maximum speed
            if self.display_array is None:
                self.display_array = pygame.surfarray.pixels3d(self.surface)

            if isinstance(self.frame, dict):
                # Direct rendering from processed frame data
                frame_data = self.frame["data"]
                width = self.frame["width"]
                height = self.frame["height"]
                x_offset = self.frame["x_offset"]
                y_offset = self.frame["y_offset"]

                # Direct pixel copy with swapaxes for pygame format
                self.display_array[
                    x_offset : x_offset + width, y_offset : y_offset + height
                ] = frame_data.swapaxes(0, 1)

            else:
                # Fallback for test pattern or direct frames
                if not CV2_AVAILABLE:
                    rgb_frame = self.frame
                else:
                    rgb_frame = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)

                # Calculate scaling
                h, w = rgb_frame.shape[:2]
                scale = min(DISPLAY_WIDTH / w, DISPLAY_HEIGHT / h)
                target_w = int(w * scale)
                target_h = int(h * scale)
                x_offset = (DISPLAY_WIDTH - target_w) // 2
                y_offset = (DISPLAY_HEIGHT - target_h) // 2

                # Resize and copy directly
                resized = cv2.resize(
                    rgb_frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST
                )
                self.display_array[
                    x_offset : x_offset + target_w, y_offset : y_offset + target_h
                ] = resized.swapaxes(0, 1)

            # Must unlock surface before blitting radar overlay
            # Only show radar on rear camera
            if self.radar_overlay and self.radar_handler and self.current_camera == 'rear':
                # Release the pixel array to unlock the surface
                del self.display_array
                self.display_array = None

            # Render radar overlay if enabled (rear camera only)
            if self.radar_overlay and self.radar_handler and self.current_camera == 'rear':
                tracks = self.radar_handler.get_tracks()
                if tracks:
                    self.radar_overlay.render(self.surface, tracks)
            else:
                # No radar - unlock surface if still locked
                if self.display_array is not None:
                    del self.display_array
                    self.display_array = None

            return True

        except Exception as e:
            # Unlock surface on error
            if self.display_array is not None:
                del self.display_array
                self.display_array = None
            self.error_message = f"Render error: {str(e)}"
            return False

    def is_active(self):
        """Check if camera view is currently active."""
        return self.active
