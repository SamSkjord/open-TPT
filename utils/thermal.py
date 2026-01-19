"""
Thermal sensor utilities for openTPT.

Provides emissivity correction for infrared temperature sensors.
"""


def apply_emissivity_correction(temp_celsius: float, emissivity: float) -> float:
    """
    Apply emissivity correction to infrared temperature reading.

    MLX sensors assume emissivity of 1.0 (perfect black body). Real materials
    have lower emissivity, causing the sensor to read lower than actual temperature.

    Stefan-Boltzmann law: Power = e * T^4
    Therefore: T_actual = T_measured / e^0.25

    Args:
        temp_celsius: Temperature reading from sensor in Celsius (-40 to 380C for MLX sensors)
        emissivity: Material emissivity (0.0-1.0)

    Returns:
        float: Corrected temperature in Celsius

    Raises:
        ValueError: If temperature is outside sensor range or emissivity is invalid

    Note:
        - Emissivity of 1.0 returns the original temperature (no correction)
        - Lower emissivity results in higher corrected temperature
        - Calculation done in Kelvin, returned in Celsius
    """
    # Validate temperature is within MLX sensor range
    if not (-40 <= temp_celsius <= 380):
        raise ValueError(
            f"Temperature {temp_celsius:.1f}C outside MLX sensor range (-40 to 380C)"
        )

    # Validate emissivity is in valid range
    if not (0.0 < emissivity <= 1.0):
        raise ValueError(f"Emissivity {emissivity:.3f} must be in range (0.0, 1.0]")

    # No correction needed for perfect black body (using epsilon comparison for float)
    if abs(emissivity - 1.0) < 1e-9:
        return temp_celsius

    # Convert to Kelvin for calculation
    temp_kelvin = temp_celsius + 273.15

    # Apply correction: T_actual = T_measured / e^0.25
    corrected_kelvin = temp_kelvin / (emissivity**0.25)

    # Convert back to Celsius
    corrected_celsius = corrected_kelvin - 273.15

    return corrected_celsius
