"""
Camera module for openTPT.
Handles rear-view camera display and toggling.
"""

import pygame
import numpy as np
import time
from utils.config import DISPLAY_WIDTH, DISPLAY_HEIGHT, MOCK_MODE

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

    def initialize(self, camera_index=0):
        """
        Initialize the camera with the specified device index.

        Args:
            camera_index: Camera device index (default 0)

        Returns:
            bool: True if successfully initialized, False otherwise
        """
        # If OpenCV is not available, we can't open a real camera
        if not CV2_AVAILABLE:
            self.error_message = "OpenCV (cv2) not available - camera disabled"
            print(self.error_message)
            return False

        try:
            # Close any existing camera
            self.close()

            # Try to open the camera
            self.camera = cv2.VideoCapture(camera_index)

            # Check if camera opened successfully
            if not self.camera.isOpened():
                self.error_message = f"Failed to open camera at index {camera_index}"
                return False

            # Use the camera's native resolution (usually 1920x1080 for most webcams)
            # Instead of forcing it to the display size
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

            self.error_message = None
            return True

        except Exception as e:
            self.error_message = f"Camera init error: {str(e)}"
            return False

    def toggle(self):
        """
        Toggle the camera view on/off.

        Returns:
            bool: New state (True = active, False = inactive)
        """
        if not self.camera or not self.camera.isOpened():
            if not self.initialize():
                return False

        # Toggle the active state
        self.active = not self.active
        return self.active

    def close(self):
        """Close the camera and release resources."""
        if self.camera:
            self.camera.release()
            self.camera = None
        self.active = False

    def update(self):
        """
        Update the camera frame. Should be called in the main loop.

        Returns:
            bool: True if new frame captured, False otherwise
        """
        if not self.active:
            return False

        # If in mock mode or OpenCV is not available, generate a test pattern
        if MOCK_MODE or not CV2_AVAILABLE or not self.camera:
            self._generate_test_pattern()
            return True

        # Otherwise try to capture a real frame
        if not self.camera.isOpened():
            return False

        try:
            # Read a frame from the camera
            ret, frame = self.camera.read()

            if not ret:
                self.error_message = "Failed to capture frame"
                return False

            # Store the frame for rendering
            self.frame = frame
            return True

        except Exception as e:
            self.error_message = f"Camera error: {str(e)}"
            return False

    def _generate_test_pattern(self):
        """Generate a test pattern frame for mock mode."""
        # Use 16:9 aspect ratio which is common for webcams (1920x1080)
        mock_width = 1920
        mock_height = 1080

        # Create a simple test pattern at the native camera resolution
        frame = np.zeros((mock_height, mock_width, 3), dtype=np.uint8)

        # Draw a grid pattern
        grid_size = 100  # Larger grid for higher resolution
        for y in range(0, mock_height, grid_size):
            for x in range(0, mock_width, grid_size):
                if (x // grid_size + y // grid_size) % 2 == 0:
                    color = (0, 0, 128)  # Dark blue
                else:
                    color = (0, 0, 64)  # Darker blue

                # Draw a filled rectangle
                cv2_rect = (
                    x,
                    y,
                    min(grid_size, mock_width - x),
                    min(grid_size, mock_height - y),
                )
                frame[
                    cv2_rect[1] : cv2_rect[1] + cv2_rect[3],
                    cv2_rect[0] : cv2_rect[0] + cv2_rect[2],
                ] = color

        # Add a centered text "MOCK CAMERA"
        font_scale = 3.0  # Larger font for higher resolution
        thickness = 3
        text = "MOCK CAMERA"

        # Calculate text size and position
        if CV2_AVAILABLE:
            # Use OpenCV if available
            (text_width, text_height), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
            )
            text_x = (mock_width - text_width) // 2
            text_y = (mock_height + text_height) // 2
            cv2.putText(
                frame,
                text,
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (255, 255, 255),
                thickness,
                cv2.LINE_AA,
            )

        # Add aspect ratio markers at corners to verify correct scaling
        corner_size = 100
        # Top-left corner marker (red)
        frame[:corner_size, :corner_size] = (0, 0, 255)
        # Top-right corner marker (green)
        frame[:corner_size, -corner_size:] = (0, 255, 0)
        # Bottom-left corner marker (blue)
        frame[-corner_size:, :corner_size] = (255, 0, 0)
        # Bottom-right corner marker (yellow)
        frame[-corner_size:, -corner_size:] = (0, 255, 255)

        # Add a moving element to show it's updating
        t = int(time.time() * 2) % mock_width
        for y in range(mock_height):
            if 0 <= t < mock_width:  # Ensure t is within bounds
                frame[y, t] = (255, 255, 0)  # Yellow line

        self.frame = frame

    def render(self):
        """
        Render the camera feed to the surface if active.

        Returns:
            bool: True if rendered, False otherwise
        """
        if not self.active:
            return False

        if self.frame is None:
            if self.error_message:
                # Display error message
                font = pygame.font.SysFont(None, 24)
                text = font.render(self.error_message, True, (255, 0, 0))
                text_rect = text.get_rect(
                    center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2)
                )
                self.surface.blit(text, text_rect)
            return False

        try:
            # For mock mode without OpenCV, frame is already RGB
            if not CV2_AVAILABLE and (MOCK_MODE or not self.camera):
                rgb_frame = self.frame
            else:
                # Convert from BGR (OpenCV) to RGB (PyGame)
                rgb_frame = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
                rgb_frame = cv2.flip(rgb_frame, 1)  # Flip horizontally

            # Resize frame to fit display while preserving aspect ratio
            if CV2_AVAILABLE:
                # Calculate the scaling factor to fit within the display
                h, w = rgb_frame.shape[:2]
                scale = min(DISPLAY_WIDTH / w, DISPLAY_HEIGHT / h)

                # Calculate new dimensions while preserving aspect ratio
                new_w = int(w * scale)
                new_h = int(h * scale)

                # Resize the frame while preserving aspect ratio
                rgb_frame = cv2.resize(rgb_frame, (new_w, new_h))

                # Create a black background of display size
                black_bg = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.uint8)

                # Calculate position to center the frame
                x_offset = (DISPLAY_WIDTH - new_w) // 2
                y_offset = (DISPLAY_HEIGHT - new_h) // 2

                # Place the resized frame on the black background
                black_bg[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = (
                    rgb_frame
                )
                rgb_frame = black_bg
            else:
                # Simple resize if OpenCV is not available
                rgb_frame = np.repeat(
                    np.repeat(rgb_frame, DISPLAY_WIDTH // rgb_frame.shape[1], axis=1),
                    DISPLAY_HEIGHT // rgb_frame.shape[0],
                    axis=0,
                )

            # Create a PyGame surface from the frame
            frame_surface = pygame.surfarray.make_surface(rgb_frame.swapaxes(0, 1))

            # Blit to the display surface
            self.surface.blit(frame_surface, (0, 0))

            # Draw a simple border to indicate camera mode
            # pygame.draw.rect(
            #    self.surface, (255, 0, 0), (0, 0, DISPLAY_WIDTH, DISPLAY_HEIGHT), 2
            # )

            # Add a small indicator in the corner
            font = pygame.font.SysFont(None, 24)
            if MOCK_MODE or not CV2_AVAILABLE:
                text = font.render("MOCK CAMERA VIEW", True, (255, 0, 0))
                self.surface.blit(text, (10, 10))

            return True

        except Exception as e:
            self.error_message = f"Render error: {str(e)}"
            return False

    def is_active(self):
        """
        Check if camera view is currently active.

        Returns:
            bool: True if active, False otherwise
        """
        return self.active
