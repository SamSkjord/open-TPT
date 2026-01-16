"""
Template module for openTPT.
Handles loading and rendering of the static GUI Template.
"""

import logging
import os
import pygame

logger = logging.getLogger('openTPT.template')
from utils.config import TEMPLATE_PATH, DISPLAY_WIDTH, DISPLAY_HEIGHT


class Template:
    def __init__(self, surface):
        """
        Initialise the Template manager.

        Args:
            surface: The pygame surface to draw on
        """
        self.surface = surface
        self.Template_image = None
        self.load_Template()

    def load_Template(self):
        """Load the Template image from the assets directory."""
        try:
            # Check if Template file exists
            if os.path.exists(TEMPLATE_PATH):
                self.Template_image = pygame.image.load(TEMPLATE_PATH)
                # Scale to fit display if needed
                if (
                    self.Template_image.get_width(),
                    self.Template_image.get_height(),
                ) != (DISPLAY_WIDTH, DISPLAY_HEIGHT):
                    self.Template_image = pygame.transform.scale(
                        self.Template_image, (DISPLAY_WIDTH, DISPLAY_HEIGHT)
                    )
                logger.info("Template loaded successfully: %s", TEMPLATE_PATH)
            else:
                logger.warning("Template file not found at %s", TEMPLATE_PATH)
                # Create a basic placeholder Template
                self.create_placeholder_Template()
        except Exception as e:
            logger.warning("Error loading Template: %s", e)
            # Create a basic placeholder Template on error
            self.create_placeholder_Template()

    def create_placeholder_Template(self):
        """Create a basic placeholder Template if the image can't be loaded."""
        self.Template_image = pygame.Surface(
            (DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA
        )

        # Fill with a transparent dark gray
        self.Template_image.fill((40, 40, 40, 200))

        # Draw placeholder boxes for each tire
        positions = [
            # FL
            (50, 50, 200, 200),
            # FR
            (DISPLAY_WIDTH - 250, 50, 200, 200),
            # RL
            (50, DISPLAY_HEIGHT - 250, 200, 200),
            # RR
            (DISPLAY_WIDTH - 250, DISPLAY_HEIGHT - 250, 200, 200),
        ]

        for rect in positions:
            pygame.draw.rect(
                self.Template_image, (60, 60, 60, 150), rect, border_radius=10
            )

        # Draw a simple car outline in the center
        center_x, center_y = DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2
        car_width, car_height = 100, 200
        car_rect = (
            center_x - car_width // 2,
            center_y - car_height // 2,
            car_width,
            car_height,
        )
        pygame.draw.rect(
            self.Template_image, (80, 80, 80, 180), car_rect, border_radius=15
        )

        logger.debug("Created placeholder Template")

    def render(self):
        """Render the Template onto the provided surface."""
        if self.Template_image:
            self.surface.blit(self.Template_image, (0, 0))
