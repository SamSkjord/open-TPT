"""
Camera module for openTPT.
Handles rear-view camera display and toggling.
"""

import pygame
import numpy as np
import time
import threading
import queue
from utils.config import (
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    MOCK_MODE,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    CAMERA_FPS,
)

# Optional import - only needed for actual camera functionality
try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class Camera:
    """Camera handler for rear-view display."""

    def __init__(self, surface):
        """
        Initialize the camera handler.

        Args:
            surface: The pygame surface to draw on
        """
        self.surface = surface
        self.camera = None
        self.active = False
        self.error_message = None
        self.frame = None

        # Threading related attributes
        self.frame_queue = queue.Queue(maxsize=2)  # Small queue for maximum performance
        self.capture_thread = None
        self.thread_running = False

        # Camera settings - compromise between quality and performance
        self.camera_width = CAMERA_WIDTH
        self.camera_height = CAMERA_HEIGHT
        self.camera_fps = CAMERA_FPS

        # Direct rendering optimization
        self.direct_buffer = None
        self.display_array = None

        # FPS tracking variables
        self.frame_count = 0
        self.fps = 0
        self.last_time = time.time()
        self.update_interval = 1.0  # Update FPS every 1 second

    def _capture_thread_function(self):
        """Thread function that continuously captures frames from the camera."""
        print("Camera capture thread started")

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
        print(f"Actual FPS: {self.camera.get(cv2.CAP_PROP_FPS)}")

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

        # Thread loop - continuously capture frames as fast as possible
        while self.thread_running:
            if not self.camera.isOpened():
                self.error_message = "Camera disconnected"
                break

            # Capture frame using grab/retrieve for maximum speed
            if self.camera.grab():
                ret, frame = self.camera.retrieve()
                if not ret:
                    continue

                # Update FPS counter
                # thread_frame_count += 1
                # elapsed = time.time() - thread_start_time
                # if elapsed >= 1.0:
                #     thread_fps = thread_frame_count / elapsed
                #     print(f"Camera thread FPS: {thread_fps:.1f}")
                #     thread_frame_count = 0
                #     thread_start_time = time.time()
                #     self.fps = thread_fps

                # Pre-process frame for direct rendering
                try:
                    # Flip horizontally and convert to RGB in one step
                    frame = cv2.flip(frame, 1)
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    # Resize using fastest interpolation
                    resized_frame = cv2.resize(
                        rgb_frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST
                    )

                    # Create processed frame data for direct rendering
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

                except Exception as e:
                    print(f"Error processing frame: {e}")
                    continue

        print("Camera capture thread stopped")

    def initialize(self, camera_index=0):
        """Initialize the camera with the specified device index."""
        if not CV2_AVAILABLE:
            self.error_message = "OpenCV (cv2) not available - camera disabled"
            print(self.error_message)
            return False

        try:
            self.close()
            self.camera = cv2.VideoCapture(camera_index)

            if not self.camera.isOpened():
                self.error_message = f"Failed to open camera at index {camera_index}"
                return False

            self.error_message = None
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
            if not self.thread_running and not MOCK_MODE and CV2_AVAILABLE:
                self.thread_running = True
                self.capture_thread = threading.Thread(
                    target=self._capture_thread_function, daemon=True
                )
                self.capture_thread.start()
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

        if MOCK_MODE or not CV2_AVAILABLE or not self.camera:
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

        # Update FPS counter
        self.frame_count += 1
        current_time = time.time()
        elapsed = current_time - self.last_time

        if elapsed >= self.update_interval:
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.last_time = current_time

        return result

    def _generate_test_pattern(self):
        """Generate a test pattern frame for mock mode."""
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
        """Render the camera feed using direct pixel manipulation for maximum speed."""
        if not self.active or self.frame is None:
            if self.error_message:
                font = pygame.font.SysFont(None, 24)
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

            # Clear the display to black
            self.display_array.fill(0)

            if isinstance(self.frame, dict):
                # Direct rendering from processed frame data
                frame_data = self.frame["data"]
                width = self.frame["width"]
                height = self.frame["height"]
                x_offset = self.frame["x_offset"]
                y_offset = self.frame["y_offset"]

                # Direct pixel copy - fastest possible rendering
                self.display_array[
                    x_offset : x_offset + width, y_offset : y_offset + height
                ] = frame_data.swapaxes(0, 1)

            else:
                # Fallback for mock mode or direct frames
                if MOCK_MODE or not CV2_AVAILABLE:
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

            # Release the pixel array to update the display
            del self.display_array
            self.display_array = None

            # Draw status text using standard pygame methods (minimal overhead)
            # font = pygame.font.SysFont(None, 24)
            # fps_text = font.render(f"FPS: {self.fps:.1f}", True, (255, 255, 0))
            # self.surface.blit(fps_text, (10, 10))

            # thread_status = "THREADED" if self.thread_running else "DIRECT"
            # thread_text = font.render(f"Mode: {thread_status}", True, (255, 255, 0))
            # self.surface.blit(thread_text, (10, 40))

            # if MOCK_MODE or not CV2_AVAILABLE:
            #     mock_text = font.render("MOCK CAMERA VIEW", True, (255, 0, 0))
            #     self.surface.blit(mock_text, (10, 70))

            return True

        except Exception as e:
            # Ensure we release the pixel array even on error
            if self.display_array is not None:
                del self.display_array
                self.display_array = None
            self.error_message = f"Render error: {str(e)}"
            return False

    def is_active(self):
        """Check if camera view is currently active."""
        return self.active
