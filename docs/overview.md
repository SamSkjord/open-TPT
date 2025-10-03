# openTPT Codebase Orientation

This document gives newcomers a tour of the openTPT project so you can find the right modules quickly, understand how data flows through the system, and identify topics worth exploring next.

## Big Picture

openTPT turns a Raspberry Pi into an in-car telemetry dash. The `main.py` entry point boots pygame, configures the chosen display resolution, and orchestrates three subsystems: GUI rendering, hardware data acquisition, and user input. During each frame the app pulls the latest tyre/brake/thermal data from background threads, draws either telemetry or a rear camera feed, and overlays UI elements whose brightness and visibility can be toggled from the NeoKey keypad or keyboard shortcuts.【F:main.py†L10-L188】

Most files are pure Python organized by responsibility:

```text
main.py            # Application lifecycle, game loop, event handling
assets/            # Static artwork (GUI overlay, icons)
configure_display.py
                   # CLI helper for writing display_config.json
hardware/          # Sensor interfaces (TPMS, brakes, thermal camera, I2C mux)
gui/               # pygame rendering, rear camera, keypad handling, overlays
utils/config.py    # All resolution-aware layout constants and thresholds
```

Understanding three pillars—configuration, hardware interfaces, and GUI rendering—will make the rest of the project feel familiar.

## Configuration and Scaling

The project can target any display size. `utils/config.py` loads `display_config.json` at startup, computes scaling factors relative to the 800×480 reference design, and exposes helper functions that translate layout coordinates to the current resolution.【F:utils/config.py†L1-L118】 Font sizes, icon positions, colour definitions, and layout dictionaries (e.g., `TPMS_POSITIONS`, `BRAKE_POSITIONS`, `MLX_POSITIONS`) all use these scaling helpers so new assets automatically fit the configured screen.【F:utils/config.py†L120-L196】

Temperature/pressure thresholds, NeoKey button assignments, and I2C bus settings live in the same module. When you introduce new UI elements, use the provided `scale_position`/`scale_size` functions and reuse these constants so behaviour remains resolution independent.

## Hardware Layer

Each hardware integration sits in `hardware/` behind a thread-safe handler class that hides connection details:

- `tpms_input.TPMSHandler` wraps the vendor library (if available), maintains the latest pressure/temperature per wheel, and normalizes status codes such as `NO_SIGNAL` or `LEAKING` for the GUI.【F:hardware/tpms_input.py†L1-L142】
- `ir_brakes.BrakeTemperatureHandler` polls ADS1115/1015 ADC channels to produce brake rotor temperatures (and can fall back to mock values when hardware is absent).
- `mlx_handler.MLXHandler` handles the MLX90640 thermal camera array via the TCA9548A I2C multiplexer and converts frames into numpy arrays ready for the GUI heatmap renderer.
- `i2c_mux.I2CMux` centralizes multiplexer selection logic shared by other modules.

Handlers expose `start()`, `stop()`, and `get_*()` methods. `main.py` launches each handler in its own thread so sensor polling never blocks the render loop.【F:main.py†L101-L142】 If you are working without hardware, run `main.py --mock`; the hardware classes have guard rails and simulated data paths designed for development.

## GUI and Input Layer

The GUI is pygame-based and divided into focused components: `Display` draws telemetry, `Camera` shows the full-screen USB video feed, `ScaleBars` and `IconHandler` render additional UI, and `InputHandler` unifies the physical NeoKey keypad and keyboard fallbacks.【F:gui/display.py†L1-L170】【F:main.py†L49-L100】 Key behaviours to notice:

- `Display` applies unit conversions, colouring rules, and thermal colormaps before drawing onto the main surface.【F:gui/display.py†L171-L302】 It also loads the static overlay artwork (`assets/overlay.png`) and resizes it to the active resolution.【F:gui/display.py†L34-L74】
- The main loop composes layers: optional rear camera, telemetry widgets, UI overlays that can auto-fade after inactivity, and finally a brightness-adjustment mask based on keypad input.【F:main.py†L143-L263】
- UI visibility combines manual toggles (button 3 / `T` key) with an auto-hide timer. Understanding `_update_ui_visibility` and the `InputHandler` flags is important when extending the HUD.【F:main.py†L164-L214】

When adding new visual elements, render them to an intermediate surface if they should participate in the fade animation, and respect the brightness overlay logic.

## CLI and Services

`configure_display.py` is a small argparse-powered utility for editing `display_config.json` (inspect it to learn how detection and manual overrides work). The repository also contains a `openTPT.service` unit file and an `install.sh` helper, illustrating how to deploy the app as a systemd service on the Raspberry Pi.

## Suggested Next Steps

1. **Run in mock mode** (`./main.py --windowed --mock`) so you can see the dashboard without hardware; inspect the mock data generators in each handler to understand expected value ranges.
2. **Study the sensor handlers** to learn the threading pattern and how status values map into GUI colours; this is crucial if you plan to add logging, alerts, or new sensor types.
3. **Review `gui/input.py`** to see how NeoKey events translate into brightness/camera/UI toggles—handy if you want to remap controls or add new actions.
4. **Experiment with layouts** by editing `display_config.json` and observing how scaling affects `TPMS_POSITIONS`, brake rectangles, and thermal blocks; this is the foundation for supporting additional screen sizes.
5. **Plan for data persistence or networking**: if you need to record telemetry or broadcast it, look at how threads currently share data and consider adding queues or async publishing without blocking the main loop.

By following these steps you should quickly get comfortable navigating the codebase and be ready to extend openTPT for your racing team’s needs.
