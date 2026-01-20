"""
Persistent settings manager for openTPT.
Stores user preferences in a JSON file that persists across restarts.

Settings file location:
    Linux/Pi: ~/.opentpt_settings.json (typically /home/pi/.opentpt_settings.json)
    macOS: ~/.opentpt_settings.json

If the settings file is corrupt (invalid JSON), it will be deleted and
defaults will be used. A warning is logged on startup in this case.
"""

import json
import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger('openTPT.settings')

# Default settings file location
SETTINGS_FILE = os.path.expanduser("~/.opentpt_settings.json")


class SettingsManager:
    """
    Manages persistent user settings.

    Settings are loaded from JSON on startup and saved when changed.
    Thread-safe for concurrent access.
    """

    _instance: Optional['SettingsManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern - only one settings manager instance."""
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._initialised = False
                cls._instance = instance  # Assign only after fully initialised
        return cls._instance

    def __init__(self):
        """Initialise the settings manager."""
        if self._initialised:
            return

        self._settings = {}
        self._file_path = SETTINGS_FILE
        self._save_lock = threading.Lock()
        self._load()
        self._initialised = True

    def _load(self):
        """Load settings from JSON file."""
        try:
            if os.path.exists(self._file_path):
                with open(self._file_path, 'r', encoding='utf-8') as f:
                    self._settings = json.load(f)
                logger.info("Settings loaded from %s", self._file_path)
            else:
                logger.debug("No settings file found, using defaults")
                self._settings = {}
        except json.JSONDecodeError as e:
            logger.warning(
                "Corrupt settings file deleted, using defaults: %s", e
            )
            self._delete_corrupt_file()
            self._settings = {}
        except Exception as e:
            logger.warning("Could not load settings: %s", e)
            self._settings = {}

    def _delete_corrupt_file(self):
        """Delete a corrupt settings file."""
        try:
            if os.path.exists(self._file_path):
                os.remove(self._file_path)
                logger.info("Removed corrupt settings file: %s", self._file_path)
        except OSError as e:
            logger.error("Failed to remove corrupt settings file: %s", e)

    def _save(self):
        """Save settings to JSON file atomically."""
        with self._save_lock:
            temp_path = self._file_path + '.tmp'
            try:
                # Write to temp file first, then rename for atomic operation
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._settings, f, indent=2)
                os.replace(temp_path, self._file_path)
            except Exception as e:
                logger.warning("Could not save settings: %s", e)
                # Clean up temp file if it was created
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Args:
            key: Setting key (can use dot notation for nested, e.g. "camera.rear.mirror")
            default: Default value if setting not found

        Returns:
            Setting value or default
        """
        keys = key.split('.')
        value = self._settings

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any, save: bool = True):
        """
        Set a setting value.

        Args:
            key: Setting key (can use dot notation for nested)
            value: Value to set
            save: Whether to save to file immediately (default True)
        """
        keys = key.split('.')
        settings = self._settings

        # Navigate to the correct nested dict, creating as needed
        for k in keys[:-1]:
            if k not in settings:
                settings[k] = {}
            settings = settings[k]

        # Set the value
        settings[keys[-1]] = value

        if save:
            self._save()

    def get_all(self) -> dict:
        """Get all settings as a dictionary."""
        return self._settings.copy()

    def reset(self):
        """Reset all settings to defaults (empty)."""
        self._settings = {}
        self._save()


# Convenience function to get the singleton instance
def get_settings() -> SettingsManager:
    """Get the settings manager singleton."""
    return SettingsManager()
