"""
Theme loader for map view themes.
Loads JSON theme files and provides RGB colour tuples for rendering.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List

logger = logging.getLogger('openTPT.theme_loader')

# Theme directory relative to project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_DIR = os.path.join(_PROJECT_ROOT, "assets", "themes")


def hex_to_rgb(hex_colour: str) -> Tuple[int, int, int]:
    """
    Convert hex colour string to RGB tuple.

    Args:
        hex_colour: Hex colour string (e.g., "#FF0000" or "FF0000")

    Returns:
        RGB tuple (r, g, b) with values 0-255
    """
    hex_colour = hex_colour.lstrip('#')
    if len(hex_colour) != 6:
        raise ValueError(f"Invalid hex colour: {hex_colour}")
    return (
        int(hex_colour[0:2], 16),
        int(hex_colour[2:4], 16),
        int(hex_colour[4:6], 16),
    )


@dataclass(frozen=True)
class MapTheme:
    """
    Immutable theme data for map view rendering.

    All colour values are RGB tuples (r, g, b).
    """
    name: str
    description: str
    bg: Tuple[int, int, int]
    road_primary: Tuple[int, int, int]
    road_secondary: Tuple[int, int, int]
    road_default: Tuple[int, int, int]
    car_marker: Tuple[int, int, int]
    sf_line: Tuple[int, int, int]
    text: Tuple[int, int, int]

    @classmethod
    def from_dict(cls, data: Dict) -> 'MapTheme':
        """Create a MapTheme from a dictionary (parsed JSON)."""
        return cls(
            name=data.get('name', 'Unknown'),
            description=data.get('description', ''),
            bg=hex_to_rgb(data.get('bg', '#000000')),
            road_primary=hex_to_rgb(data.get('road_primary', '#FFFFFF')),
            road_secondary=hex_to_rgb(data.get('road_secondary', '#3C3C3C')),
            road_default=hex_to_rgb(data.get('road_default', '#808080')),
            car_marker=hex_to_rgb(data.get('car_marker', '#00FF00')),
            sf_line=hex_to_rgb(data.get('sf_line', '#FF0000')),
            text=hex_to_rgb(data.get('text', '#FFFFFF')),
        )


class ThemeLoader:
    """
    Singleton class for loading and caching map themes.

    Themes are loaded from JSON files in the assets/themes directory.
    """

    _instance: Optional['ThemeLoader'] = None
    _themes: Dict[str, MapTheme]
    _theme_order: List[str]

    def __new__(cls) -> 'ThemeLoader':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._themes = {}
            cls._instance._theme_order = []
            cls._instance._load_themes()
        return cls._instance

    def _load_themes(self) -> None:
        """Load all theme files from the themes directory."""
        if not os.path.isdir(THEMES_DIR):
            logger.warning("Themes directory not found: %s", THEMES_DIR)
            return

        # Define preferred order (default first, then alphabetical)
        preferred_order = ['default']

        # Find all theme files
        theme_files = []
        for filename in os.listdir(THEMES_DIR):
            if filename.endswith('.json'):
                theme_files.append(filename)

        # Sort: default first, then alphabetically
        def sort_key(filename):
            name = filename[:-5]  # Remove .json
            if name == 'default':
                return (0, name)
            return (1, name)

        theme_files.sort(key=sort_key)

        # Load each theme
        for filename in theme_files:
            theme_id = filename[:-5]  # Remove .json extension
            filepath = os.path.join(THEMES_DIR, filename)

            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                theme = MapTheme.from_dict(data)
                self._themes[theme_id] = theme
                self._theme_order.append(theme_id)
                logger.debug("Loaded theme: %s (%s)", theme_id, theme.name)
            except (json.JSONDecodeError, ValueError, OSError) as e:
                logger.error("Failed to load theme %s: %s", filename, e)

        logger.info("Loaded %d map themes", len(self._themes))

    def get_theme(self, theme_id: str) -> Optional[MapTheme]:
        """
        Get a theme by ID.

        Args:
            theme_id: Theme identifier (filename without .json)

        Returns:
            MapTheme instance or None if not found
        """
        return self._themes.get(theme_id)

    def get_theme_ids(self) -> List[str]:
        """Get list of available theme IDs in display order."""
        return self._theme_order.copy()

    def get_themes(self) -> Dict[str, MapTheme]:
        """Get all loaded themes."""
        return self._themes.copy()

    def get_next_theme_id(self, current_id: str) -> str:
        """
        Get the next theme ID in the cycle.

        Args:
            current_id: Current theme ID

        Returns:
            Next theme ID in the cycle
        """
        if not self._theme_order:
            return 'default'

        try:
            current_index = self._theme_order.index(current_id)
            next_index = (current_index + 1) % len(self._theme_order)
            return self._theme_order[next_index]
        except ValueError:
            # Current theme not found, return first theme
            return self._theme_order[0]


# Module-level accessor function
_loader: Optional[ThemeLoader] = None


def get_theme_loader() -> ThemeLoader:
    """Get the singleton ThemeLoader instance."""
    global _loader
    if _loader is None:
        _loader = ThemeLoader()
    return _loader
