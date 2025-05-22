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

            # Set camera resolution close to display size
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, DISPLAY_WIDTH)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, DISPLAY_HEIGHT)

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
        # Create a simple test pattern
        frame = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.uint8)

        # Draw a grid pattern
        grid_size = 50
        for y in range(0, DISPLAY_HEIGHT, grid_size):
            for x in range(0, DISPLAY_WIDTH, grid_size):
                if (x // grid_size + y // grid_size) % 2 == 0:
                    color = (0, 0, 128)  # Dark blue
                else:
                    color = (0, 0, 64)  # Darker blue

                # Draw a filled rectangle
                cv2_rect = (
                    x,
                    y,
                    min(grid_size, DISPLAY_WIDTH - x),
                    min(grid_size, DISPLAY_HEIGHT - y),
                )
                frame[
                    cv2_rect[1] : cv2_rect[1] + cv2_rect[3],
                    cv2_rect[0] : cv2_rect[0] + cv2_rect[2],
                ] = color

        # Add a centered text "MOCK CAMERA"
        font_scale = 1.5
        thickness = 2
        text = "MOCK CAMERA"

        # Calculate text size and position
        if CV2_AVAILABLE:
            # Use OpenCV if available
            (text_width, text_height), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
            )
            text_x = (DISPLAY_WIDTH - text_width) // 2
            text_y = (DISPLAY_HEIGHT + text_height) // 2
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

        # Add a moving element to show it's updating
        t = int(time.time() * 2) % DISPLAY_WIDTH
        cv2_line = (t, 0, t, DISPLAY_HEIGHT)
        for y in range(DISPLAY_HEIGHT):
            frame[y, cv2_line[0]] = (255, 0, 0)  # Red line

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

            # Resize to fit display if needed
            if (
                rgb_frame.shape[1] != DISPLAY_WIDTH
                or rgb_frame.shape[0] != DISPLAY_HEIGHT
            ):
                if CV2_AVAILABLE:
                    rgb_frame = cv2.resize(rgb_frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
                else:
                    # Simple resize if OpenCV is not available
                    rgb_frame = np.repeat(
                        np.repeat(
                            rgb_frame, DISPLAY_WIDTH // rgb_frame.shape[1], axis=1
                        ),
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
