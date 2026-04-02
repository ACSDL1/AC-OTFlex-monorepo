"""Single-electrode potentiostat reference API.

This module provides a stable import path (`ps1_ref`) for the single-electrode
workflow while reusing the proven Matter Labs potentiostat implementation.
"""

from archived_potentiostat.ps4_ref import ADC, DAC, Resistors
from archived_potentiostat.ps4_ref import Potentiostat as _BasePotentiostat


class Potentiostat(_BasePotentiostat):
    """Single-electrode potentiostat wrapper with practical defaults."""

    def __init__(self, serial_port="/dev/ttyACM0", baudrate=115200, device_ID=1):
        super().__init__(serial_port=serial_port, baudrate=baudrate, device_ID=device_ID)


__all__ = ["Potentiostat", "ADC", "DAC", "Resistors"]
