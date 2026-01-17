"""
Event handling mixin for openTPT.

Provides pygame event processing, button handling, and UI state management.
"""

import logging
import time

import pygame

from utils.config import (
    BUTTON_PAGE_SETTINGS,
    BUTTON_CATEGORY_SWITCH,
    BUTTON_VIEW_MODE,
    UI_PAGES,
)

logger = logging.getLogger('openTPT.events')


class EventHandlerMixin:
    """Mixin providing event handling and UI state management methods."""

    def _handle_events(self):
        """Handle pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                # Exit on ESC key
                if event.key == pygame.K_ESCAPE:
                    self.running = False

                # Cycle brightness with up arrow key
                elif event.key == pygame.K_UP:
                    self.input_handler.simulate_button_press(0)  # Brightness cycle

                # Page settings with 'T' key or down arrow
                elif event.key == pygame.K_t or event.key == pygame.K_DOWN:
                    self.input_handler.simulate_button_press(BUTTON_PAGE_SETTINGS)

                # Switch within category with spacebar
                elif event.key == pygame.K_SPACE:
                    self.input_handler.simulate_button_press(BUTTON_CATEGORY_SWITCH)

                # Switch between camera/UI modes with right arrow
                elif event.key == pygame.K_RIGHT:
                    self.input_handler.simulate_button_press(BUTTON_VIEW_MODE)

            # Reset UI auto-hide timer on any user interaction
            if event.type in (
                pygame.KEYDOWN,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEMOTION,
            ):
                self.ui_last_interaction_time = time.time()
                if not self.input_handler.ui_manually_toggled:
                    self.input_handler.ui_visible = True
                    self.ui_fade_alpha = 255
                    self.ui_fading = False

    def _update_ui_visibility(self):
        """Update UI visibility based on timer and manual toggle state."""
        current_time = time.time()

        # If manually toggled, respect that setting completely
        if self.input_handler.ui_manually_toggled:
            # When manually toggled, UI state is fixed until user changes it
            self.ui_fade_alpha = 255 if self.input_handler.ui_visible else 0
            self.ui_fading = False
            return

        # Auto-hide after delay if not manually toggled
        if (
            current_time - self.ui_last_interaction_time > self.ui_auto_hide_delay
            and not self.ui_fading
            and self.ui_fade_alpha > 0
        ):
            self.ui_fading = True

        # Handle fade animation
        if self.ui_fading:
            # Decrease alpha by 10 per frame for a smooth fade effect
            self.ui_fade_alpha = max(0, self.ui_fade_alpha - 10)

            # When fully faded, update visibility state
            if self.ui_fade_alpha == 0:
                self.input_handler.ui_visible = False
                self.ui_fading = False

    def _handle_page_settings(self):
        """Handle button 1: Context-sensitive page settings."""
        if self.current_category == "camera":
            # Camera page: Toggle radar overlay (if radar enabled)
            if self.radar:
                # Toggle radar overlay visibility
                pass  # TODO: Add radar overlay toggle when implemented
        elif self.current_category == "ui":
            if self.current_ui_page == "telemetry":
                # Telemetry page: Toggle UI overlay visibility
                self.input_handler.toggle_ui_visibility()
            elif self.current_ui_page == "gmeter":
                # G-meter page: Reset peak values
                self.gmeter.reset_peaks()
                logger.info("G-meter peaks reset")
            elif self.current_ui_page == "lap_timing":
                # Lap timing page: Toggle between timer and map view
                if self.lap_timing_display:
                    self.lap_timing_display.toggle_view_mode()

    def _switch_view_mode(self):
        """Handle button 2: Switch between camera and UI categories."""
        if self.current_category == "camera":
            self.current_category = "ui"
            # Deactivate camera
            if self.camera.is_active():
                self.camera.toggle()  # Turn off camera
            logger.debug("Switched to UI pages (current: %s)", self.current_ui_page)
        else:
            self.current_category = "camera"
            # Activate camera if not already active
            if not self.camera.is_active():
                self.camera.toggle()  # Turn on camera
            logger.debug("Switched to camera pages (current: %s)", self.current_camera_page)

        # Request LED update
        self.input_handler.request_led_update()

    def _get_enabled_pages(self) -> list:
        """Get list of enabled UI page IDs based on settings."""
        from utils.settings import get_settings
        settings = get_settings()
        enabled = []
        for page_config in UI_PAGES:
            page_id = page_config["id"]
            default = page_config.get("default_enabled", True)
            if settings.get(f"pages.{page_id}.enabled", default):
                enabled.append(page_id)
        # Always return at least one page (fallback to telemetry)
        return enabled if enabled else ["telemetry"]

    def _switch_within_category(self):
        """Handle button 3: Switch within current category."""
        if self.current_category == "camera":
            # Switch between rear and front cameras
            if self.camera.is_active():
                self.camera.switch_camera()
                # Update tracking of which camera is active
                self.current_camera_page = self.camera.current_camera
                logger.debug("Switched to %s camera", self.current_camera_page)
        else:
            # Switch between enabled UI pages
            enabled_pages = self._get_enabled_pages()
            if len(enabled_pages) > 1:
                # Find current page index and cycle to next
                try:
                    current_index = enabled_pages.index(self.current_ui_page)
                    next_index = (current_index + 1) % len(enabled_pages)
                except ValueError:
                    # Current page not in enabled list, go to first enabled
                    next_index = 0
                self.current_ui_page = enabled_pages[next_index]
                # Get display name for logging
                page_name = self.current_ui_page
                for pc in UI_PAGES:
                    if pc["id"] == self.current_ui_page:
                        page_name = pc["name"]
                        break
                logger.debug("Switched to %s page", page_name)
            else:
                logger.debug("Only one page enabled: %s", self.current_ui_page)

        # Request LED update
        self.input_handler.request_led_update()

    def _handle_recording_toggle(self):
        """Handle recording start/stop toggle from button hold."""
        if self.recorder.is_recording():
            # Show recording menu (Cancel/Save/Delete)
            self.menu.show_recording_menu(
                on_cancel=self._recording_cancel,
                on_save=self._recording_save,
                on_delete=self._recording_delete,
            )
        else:
            # Start recording
            self.recorder.start_recording()
            self.input_handler.recording = True

    def _recording_cancel(self):
        """Cancel - close menu and continue recording."""
        pass  # Recording continues, menu closes automatically

    def _recording_save(self):
        """Save recording and stop."""
        self.recorder.stop_recording()
        filepath = self.recorder.save()
        self.input_handler.recording = False
        if filepath:
            logger.info("Recording saved to %s", filepath)

    def _recording_delete(self):
        """Delete recording without saving."""
        self.recorder.stop_recording()
        self.recorder.discard()
        self.input_handler.recording = False
        logger.info("Recording discarded")

    def _process_input_events(self):
        """Process NeoKey and encoder input events."""
        current_time = time.time()

        # Check for NeoKey inputs (non-blocking, handled by background thread)
        input_events = self.input_handler.check_input()

        # Handle button 1: Page-specific settings
        if input_events.get("page_settings", False):
            self._handle_page_settings()

        # Handle button 2: Switch within category
        if input_events.get("category_switch", False):
            self._switch_within_category()

        # Handle button 3: Switch view mode (camera <-> UI)
        if input_events.get("view_mode", False):
            self._switch_view_mode()

        # When UI is toggled via button, reset the fade state and timer
        if input_events.get("ui_toggled", False):
            self.ui_fade_alpha = 255 if self.input_handler.ui_visible else 0
            self.ui_fading = False
            # Reset the interaction timer when manually toggled on
            if self.input_handler.ui_visible:
                self.ui_last_interaction_time = current_time

        # Handle recording toggle (button 0 held for 1 second)
        if input_events.get("recording_toggle", False):
            self._handle_recording_toggle()

        # Check for encoder inputs (if available)
        if self.encoder:
            encoder_event = self.encoder.check_input()

            if self.menu.is_visible():
                # Menu is open - route encoder to menu
                if encoder_event.rotation_delta != 0:
                    self.menu.navigate(encoder_event.rotation_delta)
                if encoder_event.short_press:
                    self.menu.select()
                if encoder_event.long_press:
                    self.menu.back()
            else:
                # Menu closed - rotation controls brightness, long press opens menu
                if encoder_event.rotation_delta != 0:
                    self.encoder.adjust_brightness(encoder_event.rotation_delta)
                    # Sync brightness with input handler for consistency
                    self.input_handler.brightness = self.encoder.get_brightness()
                if encoder_event.long_press:
                    self.menu.show()
