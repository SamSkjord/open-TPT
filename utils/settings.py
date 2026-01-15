"""
Persistent settings manager for openTPT.
Stores user preferences in a JSON file that persists across restarts.
"""

import json
import os
import threading
from typing import Any, Optional

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
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialised = False
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
                with open(self._file_path, 'r') as f:
                    self._settings = json.load(f)
                print(f"Settings loaded from {self._file_path}")
            else:
                print(f"No settings file found, using defaults")
                self._settings = {}
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid settings file, using defaults: {e}")
            self._settings = {}
        except Exception as e:
            print(f"Warning: Could not load settings: {e}")
            self._settings = {}

    def _save(self):
        """Save settings to JSON file."""
        with self._save_lock:
            try:
                with open(self._file_path, 'w') as f:
                    json.dump(self._settings, f, indent=2)
            except Exception as e:
                print(f"Warning: Could not save settings: {e}")

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
