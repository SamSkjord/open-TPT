"""
Unit tests for the SettingsManager class.
Tests dot-notation access and persistence.
"""

import pytest
import json
import os
import tempfile
from unittest.mock import patch


class TestSettingsManagerGetSet:
    """Tests for SettingsManager get/set operations."""

    @pytest.fixture
    def settings_manager(self, temp_settings_file):
        """Create a fresh SettingsManager instance with temp file."""
        # Import here to avoid singleton issues
        from utils.settings import SettingsManager

        # Create a new instance bypassing singleton for testing
        manager = object.__new__(SettingsManager)
        manager._initialised = False
        manager._settings = {}
        manager._file_path = temp_settings_file
        manager._save_lock = __import__('threading').Lock()
        manager._initialised = True
        return manager

    @pytest.mark.unit
    def test_get_simple_key(self, settings_manager):
        """Test getting a simple (non-nested) key."""
        settings_manager._settings = {'brightness': 0.8}
        result = settings_manager.get('brightness')
        assert result == 0.8

    @pytest.mark.unit
    def test_get_missing_key_returns_default(self, settings_manager):
        """Test getting a missing key returns default."""
        result = settings_manager.get('nonexistent', default='fallback')
        assert result == 'fallback'

    @pytest.mark.unit
    def test_get_missing_key_default_none(self, settings_manager):
        """Test getting a missing key with no default returns None."""
        result = settings_manager.get('nonexistent')
        assert result is None

    @pytest.mark.unit
    def test_get_nested_key(self, settings_manager):
        """Test getting a nested key with dot notation."""
        settings_manager._settings = {
            'display': {
                'brightness': 0.8,
                'theme': 'dark'
            }
        }
        result = settings_manager.get('display.brightness')
        assert result == 0.8

    @pytest.mark.unit
    def test_get_deeply_nested_key(self, settings_manager):
        """Test getting a deeply nested key."""
        settings_manager._settings = {
            'camera': {
                'rear': {
                    'mirror': True,
                    'rotate': 0
                }
            }
        }
        result = settings_manager.get('camera.rear.mirror')
        assert result is True

    @pytest.mark.unit
    def test_get_partial_path_missing(self, settings_manager):
        """Test getting a key where intermediate path is missing."""
        settings_manager._settings = {'display': {'brightness': 0.8}}
        result = settings_manager.get('display.nonexistent.value', default='missing')
        assert result == 'missing'

    @pytest.mark.unit
    def test_set_simple_key(self, settings_manager):
        """Test setting a simple key."""
        settings_manager.set('brightness', 0.5, save=False)
        assert settings_manager._settings['brightness'] == 0.5

    @pytest.mark.unit
    def test_set_nested_key_creates_parents(self, settings_manager):
        """Test that setting a nested key creates parent dictionaries."""
        settings_manager.set('display.brightness', 0.8, save=False)
        assert settings_manager._settings == {'display': {'brightness': 0.8}}

    @pytest.mark.unit
    def test_set_deeply_nested_key(self, settings_manager):
        """Test setting a deeply nested key."""
        settings_manager.set('camera.rear.mirror', True, save=False)
        expected = {'camera': {'rear': {'mirror': True}}}
        assert settings_manager._settings == expected

    @pytest.mark.unit
    def test_set_overwrites_existing(self, settings_manager):
        """Test that set overwrites existing values."""
        settings_manager._settings = {'brightness': 0.5}
        settings_manager.set('brightness', 0.9, save=False)
        assert settings_manager._settings['brightness'] == 0.9

    @pytest.mark.unit
    def test_set_nested_overwrites_existing(self, settings_manager):
        """Test that nested set overwrites existing values."""
        settings_manager._settings = {'display': {'brightness': 0.5}}
        settings_manager.set('display.brightness', 0.9, save=False)
        assert settings_manager._settings['display']['brightness'] == 0.9

    @pytest.mark.unit
    def test_set_preserves_siblings(self, settings_manager):
        """Test that setting a nested key preserves sibling keys."""
        settings_manager._settings = {'display': {'brightness': 0.5, 'theme': 'dark'}}
        settings_manager.set('display.brightness', 0.9, save=False)
        assert settings_manager._settings['display']['theme'] == 'dark'

    @pytest.mark.unit
    def test_get_all_returns_copy(self, settings_manager):
        """Test that get_all returns a copy, not the original."""
        settings_manager._settings = {'brightness': 0.8}
        result = settings_manager.get_all()
        result['brightness'] = 0.5
        # Original should be unchanged
        assert settings_manager._settings['brightness'] == 0.8

    @pytest.mark.unit
    def test_reset_clears_settings(self, settings_manager):
        """Test that reset clears all settings."""
        settings_manager._settings = {'brightness': 0.8, 'theme': 'dark'}
        settings_manager.reset()
        assert settings_manager._settings == {}


class TestSettingsManagerPersistence:
    """Tests for SettingsManager file persistence."""

    @pytest.fixture
    def settings_manager(self, temp_settings_file):
        """Create a fresh SettingsManager instance with temp file."""
        from utils.settings import SettingsManager

        manager = object.__new__(SettingsManager)
        manager._initialised = False
        manager._settings = {}
        manager._file_path = temp_settings_file
        manager._save_lock = __import__('threading').Lock()
        manager._initialised = True
        return manager

    @pytest.mark.unit
    def test_save_creates_file(self, settings_manager, temp_settings_file):
        """Test that save creates the settings file."""
        # Remove existing file
        if os.path.exists(temp_settings_file):
            os.remove(temp_settings_file)

        settings_manager.set('test', 'value')

        assert os.path.exists(temp_settings_file)

    @pytest.mark.unit
    def test_save_writes_valid_json(self, settings_manager, temp_settings_file):
        """Test that saved file contains valid JSON."""
        settings_manager.set('brightness', 0.8)

        with open(temp_settings_file, 'r') as f:
            data = json.load(f)

        assert data == {'brightness': 0.8}

    @pytest.mark.unit
    def test_load_reads_file(self, temp_settings_with_data):
        """Test that load reads settings from file."""
        from utils.settings import SettingsManager

        manager = object.__new__(SettingsManager)
        manager._initialised = False
        manager._settings = {}
        manager._file_path = temp_settings_with_data
        manager._save_lock = __import__('threading').Lock()
        manager._load()
        manager._initialised = True

        assert manager.get('display.brightness') == 0.8
        assert manager.get('camera.rear.mirror') is True

    @pytest.mark.unit
    def test_load_missing_file_uses_empty_dict(self, temp_settings_file):
        """Test that loading a missing file uses empty dict."""
        from utils.settings import SettingsManager

        # Remove the temp file
        if os.path.exists(temp_settings_file):
            os.remove(temp_settings_file)

        manager = object.__new__(SettingsManager)
        manager._initialised = False
        manager._settings = {}
        manager._file_path = temp_settings_file
        manager._save_lock = __import__('threading').Lock()
        manager._load()
        manager._initialised = True

        assert manager._settings == {}

    @pytest.mark.unit
    def test_load_corrupt_file_uses_empty_dict(self, temp_settings_file):
        """Test that loading a corrupt file deletes it and uses empty dict."""
        from utils.settings import SettingsManager

        # Write invalid JSON
        with open(temp_settings_file, 'w') as f:
            f.write('not valid json {{{')

        manager = object.__new__(SettingsManager)
        manager._initialised = False
        manager._settings = {}
        manager._file_path = temp_settings_file
        manager._save_lock = __import__('threading').Lock()
        manager._load()
        manager._initialised = True

        assert manager._settings == {}
        # Corrupt file should be deleted
        assert not os.path.exists(temp_settings_file)


class TestSettingsManagerEdgeCases:
    """Edge case tests for SettingsManager."""

    @pytest.fixture
    def settings_manager(self, temp_settings_file):
        """Create a fresh SettingsManager instance."""
        from utils.settings import SettingsManager

        manager = object.__new__(SettingsManager)
        manager._initialised = False
        manager._settings = {}
        manager._file_path = temp_settings_file
        manager._save_lock = __import__('threading').Lock()
        manager._initialised = True
        return manager

    @pytest.mark.unit
    def test_set_various_types(self, settings_manager):
        """Test setting various data types."""
        settings_manager.set('string', 'hello', save=False)
        settings_manager.set('int', 42, save=False)
        settings_manager.set('float', 3.14, save=False)
        settings_manager.set('bool', True, save=False)
        settings_manager.set('list', [1, 2, 3], save=False)
        settings_manager.set('dict', {'a': 1}, save=False)
        settings_manager.set('none', None, save=False)

        assert settings_manager.get('string') == 'hello'
        assert settings_manager.get('int') == 42
        assert settings_manager.get('float') == 3.14
        assert settings_manager.get('bool') is True
        assert settings_manager.get('list') == [1, 2, 3]
        assert settings_manager.get('dict') == {'a': 1}
        assert settings_manager.get('none') is None

    @pytest.mark.unit
    def test_empty_key_components(self, settings_manager):
        """Test handling of keys with empty components."""
        # This is an edge case - empty string between dots
        # Behaviour depends on implementation, just ensure no crash
        try:
            settings_manager.set('a..b', 'value', save=False)
            result = settings_manager.get('a..b')
            # If it doesn't crash, that's acceptable
        except (KeyError, ValueError):
            # Also acceptable to raise an error
            pass

    @pytest.mark.unit
    def test_get_non_dict_intermediate(self, settings_manager):
        """Test getting nested key where intermediate is not a dict."""
        settings_manager._settings = {'value': 'string'}
        result = settings_manager.get('value.nested', default='default')
        assert result == 'default'
