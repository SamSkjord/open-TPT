"""
Handles loading and rendering of PNG icons on the interface.
"""

import logging
import os
import pygame

logger = logging.getLogger('openTPT.icons')
from utils.config import (
    TYRE_ICON_PATH,
    BRAKE_ICON_PATH,
    TYRE_ICON_POSITION,
    BRAKE_ICON_POSITION,
    ICON_SIZE,
)


class IconHandler:
    def __init__(self, surface):
        """
        Initialise the icon handler.

        Args:
            surface: The pygame surface to draw on
        """
        self.surface = surface
        self.icons = {}
        self.load_icons()

    def load_icons(self):
        """Load all defined icons from files."""
        icon_paths = {
            "tyre": TYRE_ICON_PATH,
            "brake": BRAKE_ICON_PATH,
        }

        for name, path in icon_paths.items():
            try:
                if os.path.exists(path):
                    # Load the image
                    image = pygame.image.load(path).convert_alpha()

                    # Resize if ICON_SIZE is defined
                    if ICON_SIZE:
                        image = pygame.transform.scale(image, ICON_SIZE)

                    self.icons[name] = image
                    logger.debug("Loaded icon: %s from %s", name, path)
                else:
                    logger.warning("Icon file not found at %s", path)
                    self.icons[name] = None
            except Exception as e:
                logger.warning("Error loading icon %s from %s: %s", name, path, e)
                self.icons[name] = None

    def render_icon(self, name, position=None):
        """
        Render a specific icon at a given position.

        Args:
            name: Icon name ("tyre" or "brake")
            position: Optional (x, y) position override. If None, uses configured position.

        Returns:
            bool: True if rendered successfully, False otherwise
        """
        if name not in self.icons or self.icons[name] is None:
            return False

        # Determine position (use override if provided, otherwise use config)
        if position is None:
            if name == "tyre":
                position = TYRE_ICON_POSITION
            elif name == "brake":
                position = BRAKE_ICON_POSITION
            else:
                return False

        # Blit the icon to the surface
        try:
            self.surface.blit(self.icons[name], position)
            return True
        except Exception as e:
            logger.debug("Error rendering icon %s: %s", name, e)
            return False

    def render_all(self):
        """Render all icons at their configured positions."""
        self.render_icon("tyre")
        self.render_icon("brake")

    def reload_icon(self, name):
        """
        Reload a specific icon from file.
        Useful if icons are changed during runtime.

        Args:
            name: Icon name to reload

        Returns:
            bool: True if reloaded successfully, False otherwise
        """
        if name == "tyre":
            path = TYRE_ICON_PATH
        elif name == "brake":
            path = BRAKE_ICON_PATH
        else:
            return False

        try:
            if os.path.exists(path):
                image = pygame.image.load(path).convert_alpha()

                # Resize if ICON_SIZE is defined
                if ICON_SIZE:
                    image = pygame.transform.scale(image, ICON_SIZE)

                self.icons[name] = image
                return True
            else:
                logger.warning("Icon file not found during reload: %s", path)
                return False
        except Exception as e:
            logger.warning("Error reloading icon %s from %s: %s", name, path, e)
            return False

    def render_to_surface(self, surface):
        """Render all icons to the provided surface."""
        # Store original surface
        original_surface = self.surface

        # Set to new surface temporarily
        self.surface = surface

        # Render the icons
        self.render_all()

        # Restore original surface
        self.surface = original_surface
