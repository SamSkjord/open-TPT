"""
Bluetooth Audio menu mixin for openTPT.
"""

import logging
import os
import pwd
import re
import subprocess
import threading
import time
from typing import Optional, Tuple

logger = logging.getLogger('openTPT.menu.bluetooth')


def _get_audio_user() -> Tuple[str, int, str]:
    """
    Get the username, UID, and XDG_RUNTIME_DIR for audio/Bluetooth commands.

    Returns:
        Tuple of (username, uid, runtime_dir)
    """
    # Check for existing session buses to find active user
    run_user = os.path.join('/run', 'user')
    if os.path.exists(run_user):
        for uid_name in sorted(os.listdir(run_user)):
            try:
                uid = int(uid_name)
                if uid == 0:
                    continue  # Skip root
                bus_path = os.path.join(run_user, uid_name, 'bus')
                if os.path.exists(bus_path):
                    # Found active session, get username
                    try:
                        pw = pwd.getpwuid(uid)
                        return pw.pw_name, uid, os.path.join(run_user, uid_name)
                    except KeyError:
                        continue
            except (ValueError, PermissionError):
                continue

    # Fall back to 'pi' user if available
    try:
        pi_user = pwd.getpwnam('pi')
        return 'pi', pi_user.pw_uid, f'/run/user/{pi_user.pw_uid}'
    except KeyError:
        pass

    # Last resort: first non-root user
    for pw in pwd.getpwall():
        if pw.pw_uid >= 1000:
            return pw.pw_name, pw.pw_uid, f'/run/user/{pw.pw_uid}'

    # Absolute fallback
    return 'pi', 1000, '/run/user/1000'


class BluetoothMenuMixin:
    """Mixin providing Bluetooth Audio menu functionality."""

    # Volume methods

    def _get_volume_label(self) -> str:
        """Get volume label with editing indicator."""
        vol = self._get_bt_volume()
        if self.volume_editing:
            return f"[ Volume: {vol}% ]"
        return f"Volume: {vol}%"

    def _toggle_volume_editing(self) -> str:
        """Toggle volume editing mode."""
        self.volume_editing = not self.volume_editing
        if self.volume_editing:
            return "Rotate to adjust, press to save"
        return "Volume saved"

    def _check_bt_audio_deps(self) -> bool:
        """Check if Bluetooth audio dependencies are installed."""
        try:
            # Check if PulseAudio is installed
            result = subprocess.run(
                ["which", "pulseaudio"], capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug("Failed to check PulseAudio: %s", e)
            return False

    # Bluetooth scanning and device methods

    def _scan_bluetooth(self) -> str:
        """Scan for Bluetooth devices (non-blocking)."""

        def do_scan():
            try:
                username, _, _ = _get_audio_user()
                # Ensure Bluetooth is powered on
                subprocess.run(
                    ["sudo", "rfkill", "unblock", "bluetooth"],
                    capture_output=True,
                    timeout=5,
                )
                subprocess.run(
                    ["sudo", "-u", username, "bluetoothctl", "power", "on"],
                    capture_output=True,
                    timeout=5,
                )
                # Run scan for 8 seconds
                subprocess.run(
                    [
                        "sudo",
                        "-u",
                        username,
                        "bluetoothctl",
                        "--timeout",
                        "8",
                        "scan",
                        "on",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                # Update status when done
                if self.current_menu:
                    self.current_menu.set_status("Scan complete")
            except subprocess.TimeoutExpired:
                if self.current_menu:
                    self.current_menu.set_status("Scan timed out")
            except (OSError, subprocess.SubprocessError) as e:
                logger.debug("Bluetooth scan failed: %s", e)
                if self.current_menu:
                    self.current_menu.set_status(f"Scan error: {e}")

        # Start scan in background thread
        scan_thread = threading.Thread(target=do_scan, daemon=True)
        scan_thread.start()
        return "Scanning... (8 sec)"

    def _is_mac_address(self, name: str) -> bool:
        """Check if a name is just a MAC address (no friendly name)."""
        # MAC addresses look like XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
        mac_pattern = r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$"
        return bool(re.match(mac_pattern, name.replace("-", ":")))

    def _get_bt_discovered_devices(self) -> list:
        """Get list of discovered Bluetooth devices as (mac, name) tuples."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices"], capture_output=True, text=True, timeout=5
            )
            devices = []
            paired = set(mac for mac, _ in self._get_bt_paired_devices_raw())
            for line in result.stdout.strip().split("\n"):
                # Format: "Device XX:XX:XX:XX:XX:XX Device Name"
                if line.startswith("Device "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = parts[2]
                        # Only include devices not already paired and with friendly names
                        if mac not in paired and not self._is_mac_address(name):
                            devices.append((mac, name))
            return devices
        except Exception as e:
            logger.debug("Failed to get unpaired BT devices: %s", e)
            return []

    def _get_bt_paired_devices_raw(self) -> list:
        """Get list of paired Bluetooth devices (internal, no filtering)."""
        try:
            # Use 'devices Paired' filter (works on bluetoothctl 5.82+)
            result = subprocess.run(
                ["bluetoothctl", "devices", "Paired"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            devices = []
            for line in result.stdout.strip().split("\n"):
                if line.startswith("Device "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        devices.append((parts[1], parts[2]))
            return devices
        except Exception as e:
            logger.debug("Failed to get paired BT devices: %s", e)
            return []

    def _get_bt_paired_devices(self) -> list:
        """Get list of paired or trusted Bluetooth devices as (mac, name) tuples."""
        try:
            # First try paired devices
            result = subprocess.run(
                ["bluetoothctl", "devices", "Paired"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            devices = []
            seen_macs = set()
            for line in result.stdout.strip().split("\n"):
                if line.startswith("Device "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = parts[2]
                        devices.append((mac, name))
                        seen_macs.add(mac)

            # Also include trusted devices (may have lost pairing but can reconnect)
            result = subprocess.run(
                ["bluetoothctl", "devices", "Trusted"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                if line.startswith("Device "):
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = parts[2]
                        if mac not in seen_macs:
                            devices.append((mac, name))
                            seen_macs.add(mac)

            return devices
        except Exception as e:
            logger.debug("Failed to get BT paired/trusted devices: %s", e)
            return []

    def _get_bt_connected_device(self) -> Optional[tuple]:
        """Get currently connected Bluetooth audio device as (mac, name) or None."""
        try:
            # Check each paired device for connection status
            devices = self._get_bt_paired_devices()
            for mac, name in devices:
                result = subprocess.run(
                    ["bluetoothctl", "info", mac],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if "Connected: yes" in result.stdout:
                    return (mac, name)
            return None
        except Exception as e:
            logger.debug("Failed to get connected BT device: %s", e)
            return None

    def _get_bt_status_label(self) -> str:
        """Get Bluetooth status label for menu."""
        # Check if PulseAudio is installed
        if not self._bt_audio_available:
            return "! Install pulseaudio"

        connected = self._get_bt_connected_device()
        if connected:
            _, name = connected
            # Truncate long names
            if len(name) > 20:
                name = name[:17] + "..."
            return f"Connected: {name}"
        return "Status: Not connected"

    def _show_bt_connect_menu(self) -> str:
        """Show submenu with paired devices to connect."""
        # Import here to avoid circular imports
        from gui.menu.base import Menu, MenuItem

        devices = self._get_bt_paired_devices()
        if not devices:
            return "No paired devices"

        # Build connect submenu dynamically (limit to 20 devices)
        connect_menu = Menu("Connect Device")
        for mac, name in devices[:20]:
            # Use default argument to capture mac in closure
            connect_menu.add_item(
                MenuItem(
                    name[:25] if len(name) > 25 else name,
                    action=lambda m=mac, n=name: self._bt_connect(m, n),
                )
            )
        connect_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        connect_menu.parent = self.bt_menu

        # Switch to connect menu
        self.current_menu.hide()
        self.current_menu = connect_menu
        connect_menu.show()
        return ""

    def _bt_connect(self, mac: str, name: str) -> str:
        """Connect to a Bluetooth device (runs in background)."""
        # Debounce - prevent rapid reconnect attempts
        # Hold lock while checking and setting flag to avoid race condition
        with self._bt_connect_lock:
            if self._bt_connecting:
                return "Connection in progress..."
            self._bt_connecting = True

        def do_connect():
            try:
                username, uid, runtime_dir = _get_audio_user()

                # Check if device is paired first
                info_result = subprocess.run(
                    ["bluetoothctl", "info", mac],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                is_paired = "Paired: yes" in info_result.stdout

                # If not paired, try to pair first
                if not is_paired:
                    pair_result = subprocess.run(
                        ["bluetoothctl", "pair", mac],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    if pair_result.returncode != 0:
                        if self.current_menu:
                            self.current_menu.set_status("Pairing failed - check device")
                        return

                    # Verify pairing succeeded
                    verify = subprocess.run(
                        ["bluetoothctl", "info", mac],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if "Paired: yes" not in verify.stdout:
                        if self.current_menu:
                            self.current_menu.set_status("Pairing incomplete")
                        return

                # Trust the device for auto-reconnect
                trust_result = subprocess.run(
                    ["bluetoothctl", "trust", mac],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if trust_result.returncode != 0:
                    logger.debug("Trust failed: %s", trust_result.stderr)

                # Connect as the audio user so PulseAudio profiles work
                result = subprocess.run(
                    ["sudo", "-u", username, "bluetoothctl", "connect", mac],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )

                # Check connection status by querying device info
                status = subprocess.run(
                    ["bluetoothctl", "info", mac],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if "Connected: yes" in status.stdout:
                    self._play_bt_test_sound()
                    if self.current_menu:
                        self.current_menu.set_status(f"Connected to {name}")
                elif "profile-unavailable" in result.stderr:
                    if self.current_menu:
                        self.current_menu.set_status("Audio profile unavailable")
                elif result.returncode != 0:
                    # Parse specific error from stderr
                    if "page-timeout" in result.stderr:
                        msg = "Device not responding"
                    elif "not available" in result.stderr:
                        msg = "Device not found"
                    else:
                        msg = "Connection failed"
                    if self.current_menu:
                        self.current_menu.set_status(msg)
                else:
                    if self.current_menu:
                        self.current_menu.set_status("Connection failed")

            except subprocess.TimeoutExpired:
                if self.current_menu:
                    self.current_menu.set_status("Connection timed out")
            except Exception as e:
                logger.debug("Bluetooth connect failed: %s", e)
                if self.current_menu:
                    self.current_menu.set_status(f"Error: {e}")
            finally:
                with self._bt_connect_lock:
                    self._bt_connecting = False

        # Run connection in background thread
        connect_thread = threading.Thread(target=do_connect, daemon=True)
        connect_thread.start()
        return f"Connecting to {name}..."

    def _play_bt_test_sound(self):
        """Play a test sound to confirm Bluetooth audio is working."""
        # Cancel any previous sound thread (don't pile up)
        if self._bt_sound_thread and self._bt_sound_thread.is_alive():
            return  # Previous sound still playing, skip

        def do_play():
            try:
                # Try system bell sound first, fall back to generated tone
                sound_files = [
                    "/usr/share/sounds/freedesktop/stereo/complete.oga",
                    "/usr/share/sounds/freedesktop/stereo/bell.oga",
                    "/usr/share/sounds/alsa/Front_Center.wav",
                ]
                for sound in sound_files:
                    if os.path.exists(sound):
                        result = subprocess.run(
                            ["paplay", sound], capture_output=True, timeout=5
                        )
                        if result.returncode == 0:
                            return
                # Fallback: generate a simple beep using speaker-test
                subprocess.run(
                    ["speaker-test", "-t", "sine", "-f", "1000", "-l", "1"],
                    capture_output=True,
                    timeout=2,
                )
            except Exception as e:
                logger.debug("Audio test failed: %s", e)

        # Run in background to not block menu, track thread
        self._bt_sound_thread = threading.Thread(target=do_play, daemon=True)
        self._bt_sound_thread.start()

    def _run_pactl(self, args: list) -> subprocess.CompletedProcess:
        """Run pactl command as the audio user with correct environment."""
        username, uid, runtime_dir = _get_audio_user()
        env_cmd = ["sudo", "-u", username, "env", f"XDG_RUNTIME_DIR={runtime_dir}"]
        return subprocess.run(
            env_cmd + ["pactl"] + args, capture_output=True, text=True, timeout=5
        )

    def _get_bt_volume(self) -> int:
        """Get current PulseAudio volume as percentage."""
        try:
            result = self._run_pactl(["get-sink-volume", "@DEFAULT_SINK@"])
            # Output like: "Volume: front-left: 32768 /  50% / -18.06 dB, ..."
            if "%" in result.stdout:
                # Extract first percentage
                match = re.search(r"(\d+)%", result.stdout)
                if match:
                    return int(match.group(1))
            return 50  # Default
        except Exception as e:
            logger.debug("Failed to get BT volume: %s", e)
            return 50

    def _bt_volume_adjust(self, delta: int) -> str:
        """Adjust PulseAudio volume by delta percent."""
        try:
            current = self._get_bt_volume()
            new_vol = max(0, min(100, current + delta))
            self._run_pactl(["set-sink-volume", "@DEFAULT_SINK@", f"{new_vol}%"])
            return f"Volume: {new_vol}%"
        except subprocess.TimeoutExpired:
            return "Volume adjust timed out"
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug("Volume adjust failed: %s", e)
            return f"Error: {e}"

    def _show_bt_pair_menu(self) -> str:
        """Show submenu with discovered devices to pair."""
        # Import here to avoid circular imports
        from gui.menu.base import Menu, MenuItem

        devices = self._get_bt_discovered_devices()
        if not devices:
            return "No new devices found. Scan first."

        # Build pair submenu dynamically (limit to 20 devices)
        pair_menu = Menu("Pair Device")
        for mac, name in devices[:20]:
            pair_menu.add_item(
                MenuItem(
                    name[:25] if len(name) > 25 else name,
                    action=lambda m=mac, n=name: self._bt_pair(m, n),
                )
            )
        pair_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        pair_menu.parent = self.bt_menu

        # Switch to pair menu
        self.current_menu.hide()
        self.current_menu = pair_menu
        pair_menu.show()
        return ""

    def _bt_pair(self, mac: str, name: str) -> str:
        """Pair with a Bluetooth device."""
        try:
            username, _, _ = _get_audio_user()
            # Trust the device first (allows auto-reconnect)
            subprocess.run(
                ["sudo", "-u", username, "bluetoothctl", "trust", mac],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Pair with the device (default agent works better than NoInputNoOutput)
            result = subprocess.run(
                ["sudo", "-u", username, "bluetoothctl", "pair", mac],
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout + result.stderr

            # Handle stuck state - remove and retry once
            if "AlreadyExists" in output:
                subprocess.run(
                    ["sudo", "-u", username, "bluetoothctl", "remove", mac],
                    capture_output=True,
                    timeout=5,
                )
                return "Cleared stuck state - try again"

            if "Pairing successful" in output:
                # Try to connect after pairing
                connect_result = self._bt_connect(mac, name)
                if "Connected" in connect_result:
                    return f"Paired & connected: {name}"
                return "Paired (connect manually)"
            elif "AuthenticationFailed" in output:
                return "Put device in pairing mode"
            elif "ConnectionAttemptFailed" in output:
                return "Device not responding"
            elif "Failed" in output:
                return "Pairing failed - retry"
            return f"Pairing {name}..."
        except subprocess.TimeoutExpired:
            return "Pairing timed out"
        except Exception as e:
            logger.debug("Bluetooth pairing failed: %s", e)
            return f"Error: {e}"

    def _bt_disconnect(self) -> str:
        """Disconnect current Bluetooth device."""
        connected = self._get_bt_connected_device()
        if not connected:
            return "No device connected"

        mac, name = connected
        try:
            username, _, _ = _get_audio_user()
            result = subprocess.run(
                ["sudo", "-u", username, "bluetoothctl", "disconnect", mac],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "Successful" in result.stdout or "Disconnected" in result.stdout:
                return f"Disconnected from {name}"
            return "Disconnect requested"
        except subprocess.TimeoutExpired:
            return "Disconnect timed out"
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug("Bluetooth disconnect failed: %s", e)
            return f"Error: {e}"

    def _show_bt_forget_menu(self) -> str:
        """Show submenu to forget/unpair devices."""
        # Import here to avoid circular imports
        from gui.menu.base import Menu, MenuItem

        devices = self._get_bt_paired_devices()
        if not devices:
            return "No paired devices"

        # Build forget submenu dynamically (limit to 20 devices)
        forget_menu = Menu("Forget Device")
        for mac, name in devices[:20]:
            forget_menu.add_item(
                MenuItem(
                    name[:25] if len(name) > 25 else name,
                    action=lambda m=mac, n=name: self._bt_forget(m, n),
                )
            )
        forget_menu.add_item(MenuItem("Back", action=lambda: self._go_back()))
        forget_menu.parent = self.bt_menu

        # Switch to forget menu
        self.current_menu.hide()
        self.current_menu = forget_menu
        forget_menu.show()
        return ""

    def _bt_forget(self, mac: str, name: str) -> str:
        """Forget/unpair a Bluetooth device."""
        try:
            username, _, _ = _get_audio_user()
            result = subprocess.run(
                ["sudo", "-u", username, "bluetoothctl", "remove", mac],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "removed" in result.stdout.lower() or result.returncode == 0:
                return f"Forgot {name}"
            return f"Failed to forget {name}"
        except subprocess.TimeoutExpired:
            return "Forget timed out"
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug("Bluetooth forget device failed: %s", e)
            return f"Error: {e}"

    def _bt_refresh_services(self) -> str:
        """Restart PulseAudio and Bluetooth in correct order for audio profiles."""

        def do_refresh():
            try:
                # Restart PulseAudio first to register audio endpoints
                subprocess.run(
                    ["systemctl", "--user", "restart", "pulseaudio"], timeout=10
                )
                time.sleep(2)
                # Then restart Bluetooth to pick up the endpoints
                subprocess.run(
                    ["sudo", "systemctl", "restart", "bluetooth"], timeout=10
                )
                time.sleep(2)
                if self.current_menu:
                    self.current_menu.set_status("BT services refreshed")
            except subprocess.TimeoutExpired:
                if self.current_menu:
                    self.current_menu.set_status("Refresh timed out")
            except (OSError, subprocess.SubprocessError) as e:
                logger.debug("Bluetooth refresh services failed: %s", e)
                if self.current_menu:
                    self.current_menu.set_status(f"Refresh failed: {e}")

        # Run in background
        refresh_thread = threading.Thread(target=do_refresh, daemon=True)
        refresh_thread.start()
        return "Refreshing BT services..."
