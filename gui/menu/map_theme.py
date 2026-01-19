"""
Map theme menu mixin for openTPT.
Provides menu functionality for selecting map view themes.
"""

import logging

from config import MAP_THEME_DEFAULT
from utils.settings import get_settings
from utils.theme_loader import get_theme_loader

logger = logging.getLogger('openTPT.menu.map_theme')


class MapThemeMenuMixin:
    """Mixin providing map theme menu functionality."""

    def _get_map_theme_label(self) -> str:
        """Get current map theme label for menu display."""
        settings = get_settings()
        current_theme_id = settings.get("map.theme", MAP_THEME_DEFAULT)
        loader = get_theme_loader()
        theme = loader.get_theme(current_theme_id)
        if theme:
            return f"Map Theme: {theme.name}"
        return f"Map Theme: {current_theme_id}"

    def _cycle_map_theme(self) -> str:
        """Cycle to the next map theme."""
        settings = get_settings()
        current_theme_id = settings.get("map.theme", MAP_THEME_DEFAULT)
        loader = get_theme_loader()
        next_theme_id = loader.get_next_theme_id(current_theme_id)
        settings.set("map.theme", next_theme_id)

        # Signal theme change (transient, for immediate display update)
        settings.set("map.theme_changed", True, save=False)

        theme = loader.get_theme(next_theme_id)
        theme_name = theme.name if theme else next_theme_id
        logger.debug("Map theme changed to: %s", theme_name)
        return f"Theme: {theme_name}"

    def _show_map_theme_menu(self):
        """Show submenu with all available themes."""
        from gui.menu.base import Menu, MenuItem

        theme_menu = Menu("Map Themes")
        loader = get_theme_loader()
        settings = get_settings()
        current_theme_id = settings.get("map.theme", MAP_THEME_DEFAULT)

        for theme_id in loader.get_theme_ids():
            theme = loader.get_theme(theme_id)
            if theme:
                # Mark current theme with asterisk
                label = f"* {theme.name}" if theme_id == current_theme_id else theme.name
                theme_menu.add_item(
                    MenuItem(
                        label,
                        action=lambda tid=theme_id: self._set_map_theme(tid),
                    )
                )

        theme_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        theme_menu.parent = self.current_menu
        self.current_menu = theme_menu
        theme_menu.show()

    def _set_map_theme(self, theme_id: str) -> str:
        """Set a specific map theme by ID."""
        settings = get_settings()
        settings.set("map.theme", theme_id)

        # Signal theme change (transient, for immediate display update)
        settings.set("map.theme_changed", True, save=False)

        loader = get_theme_loader()
        theme = loader.get_theme(theme_id)
        theme_name = theme.name if theme else theme_id
        logger.debug("Map theme set to: %s", theme_name)
        return f"Theme: {theme_name}"
