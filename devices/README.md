# IoT Devices

## Purpose
Self-contained modules for each IoT hardware device. Each device folder contains source code, firmware, mechanical/electrical documentation, and tests.

## Structure
Each device (runze-pump, heater, furnace) contains:
- `src/` - Python library code
  - `__init__.py` - Device class and main functions
  - Additional module files
- `firmware/` - Device firmware (Arduino/ESP32/etc.)
- `mechanical/` - CAD models and mechanical designs
- `electrical/` - Schematics, PCB layouts, wiring diagrams
- `documentation/` - Device-specific documentation
- `README.md` - Device overview (to be filled in)

## Device Modules
- **runze-pump** - Peristaltic pump control library
- **heater** - Temperature control device library
- **furnace** - Furnace control library

## Usage
Import device libraries directly:
```python
from devices.runze_pump.src import RunzePump
from devices.heater.src import Heater
from devices.furnace.src import Furnace
```
