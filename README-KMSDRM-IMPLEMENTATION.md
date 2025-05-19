# openTPT KMSDRM Implementation

This document describes the configuration and implementation of openTPT to run with pygame full-screen on boot without X11 or a logged-in user, using KMSDRM to render directly to `/dev/fb0`.

## Implementation Overview

The implementation achieves the following:

- KMSDRM driver for SDL2
- Systemd autostart on boot
- Proper rotation of all UI elements
- Support for HyperPixel 4 display
- No X11 window manager required
- Direct framebuffer rendering

## Key Components

1. **SDL with KMSDRM Support**: The install script builds SDL 2.33.0 from source with specific flags enabling KMSDRM support while disabling X11 and Wayland.

2. **Pygame Rotation**: The application properly rotates all UI elements by drawing each component to its own surface before applying rotation to the entire frame.

3. **Systemd Service**: The service configuration ensures the application starts automatically on boot and specifies the required environment variables.

4. **Environment Variables**: Key environment variables are set: 
   - `SDL_VIDEODRIVER=KMSDRM` - Forces SDL to use the KMSDRM driver
   - `SDL_NOMOUSE=1` - Prevents input errors when running without a mouse
   - `PYGAME_HIDE_SUPPORT_PROMPT=1` - Suppresses pygame welcome message

## Installation Instructions

1. On a fresh Raspberry Pi OS Lite (Bookworm) installation, clone the repository:
   ```
   git clone https://github.com/yourusername/open-TPT.git
   cd open-TPT
   ```

2. Run the provided installation script:
   ```
   ./install.sh
   ```
   This will:
   - Install all required dependencies
   - Build SDL2 with KMSDRM support
   - Build SDL_ttf for font support
   - Reinstall pygame to use the system SDL
   - Configure the systemd service for auto-start

3. After installation completes:
   - Reboot the Raspberry Pi: `sudo reboot`
   - The application should start automatically after boot
   - Check the status with: `sudo systemctl status openTPT.service`
   - View logs with: `sudo journalctl -u openTPT.service`

## Rotation Fix Implementation

The main rotation issue was fixed by modifying how UI elements are drawn to the screen. Previously, elements like TPMS data, thermal images, and brake temperatures were drawn directly to the screen surface before rotation, causing them to appear in incorrect positions when the final rotation was applied.

The solution:
1. Each UI component now renders to its own temporary surface
2. All surfaces are combined onto the main render surface
3. The final combined surface is rotated 270 degrees before display
4. This ensures all elements maintain their correct relative positions after rotation

## Manual Testing

To verify the installation is working correctly:

1. After installation, test with: `SDL_VIDEODRIVER=KMSDRM python3 main.py`
2. You should see the openTPT interface with all elements properly rotated
3. The scale bars, TPMS data, thermal displays, and brake indicators should all be visible and aligned correctly

## Troubleshooting

- If the display doesn't appear, check that SDL is properly built with KMSDRM support
- Verify SDL version with: `python3 -c "import pygame; print(pygame.get_sdl_version())"`
- Check logs with: `sudo journalctl -u openTPT.service`
- If needed, modify display rotation in main.py by changing the rotation value in the line: `rotated_surface = pygame.transform.rotate(render_surface, 270)`
