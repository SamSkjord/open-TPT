#!/usr/bin/env python3
"""
Configuration utility for openTPT display settings.
This script helps set the correct resolution for HDMI displays.
"""

import os
import json
import pygame
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Configure display settings for openTPT"
    )
    parser.add_argument("--width", type=int, help="Display width in pixels")
    parser.add_argument("--height", type=int, help="Display height in pixels")
    parser.add_argument(
        "--detect", action="store_true", help="Attempt to detect display resolution"
    )
    parser.add_argument(
        "--show", action="store_true", help="Show current configuration"
    )

    args = parser.parse_args()

    # Path to config file
    config_path = Path(__file__).parent.absolute() / "display_config.json"

    # Default configuration
    default_config = {
        "width": 800,
        "height": 480,
        "notes": "Default resolution. Change values to match your HDMI display resolution.",
    }

    # Load current configuration if exists
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                current_config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            current_config = default_config
    else:
        current_config = default_config

    # Show current configuration
    if args.show or (not args.width and not args.height and not args.detect):
        print("\nCurrent Display Configuration:")
        print(f"Width: {current_config.get('width', 800)} pixels")
        print(f"Height: {current_config.get('height', 480)} pixels")
        print(f"Notes: {current_config.get('notes', '')}")
        print("\nTo change configuration, use --width and --height parameters.")
        print("Example: python3 configure_display.py --width 1280 --height 720")
        print("Or try to auto-detect: python3 configure_display.py --detect")
        return

    # Auto-detect resolution
    if args.detect:
        try:
            pygame.init()
            info = pygame.display.Info()
            pygame.quit()

            width = info.current_w
            height = info.current_h

            # Ignore common desktop resolutions which are likely not the display we want
            if width > 1920 or height > 1080:
                print("Could not auto-detect a suitable display resolution.")
                print("Please specify resolution manually with --width and --height.")
                return

            print(f"Detected display resolution: {width}x{height}")

            # Confirm with user
            confirm = input(f"Use this resolution ({width}x{height})? [y/N]: ").lower()
            if confirm == "y":
                current_config["width"] = width
                current_config["height"] = height

                # Save configuration
                try:
                    with open(config_path, "w") as f:
                        json.dump(current_config, f, indent=4)
                    print("\nDisplay configuration updated.")
                    print("Please restart openTPT for changes to take effect.")
                except Exception as e:
                    print(f"Error saving config: {e}")
            else:
                print("Resolution not updated.")
        except Exception as e:
            print(f"Error detecting display resolution: {e}")
            print("Please specify resolution manually with --width and --height.")
        return

    # Manual resolution setting
    if args.width and args.height:
        current_config["width"] = args.width
        current_config["height"] = args.height

        # Save configuration
        try:
            with open(config_path, "w") as f:
                json.dump(current_config, f, indent=4)
            print(f"\nDisplay resolution set to {args.width}x{args.height}.")
            print("Please restart openTPT for changes to take effect.")
        except Exception as e:
            print(f"Error saving config: {e}")
    elif args.width or args.height:
        print("Error: Both --width and --height must be specified together.")


if __name__ == "__main__":
    main()
