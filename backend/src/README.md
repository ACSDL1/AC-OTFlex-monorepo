# Backend Source Code

## Structure
- `controller/` - MQTT messaging and workflow execution logic
- `devices/` - High-level abstractions for robot devices
  - `opentrons.py` - Opentrons OT-2 wrapper functions
  - `robot_arm.py` - Robot arm wrapper functions
- `utils/` - Shared utilities and configuration helpers
- `__init__.py` - Package initialization

## Device Abstractions
Rather than low-level movement commands, devices expose high-level functions:
- **Opentrons**: `pickup_plate()`, `dispense()`, `transfer()`, etc.
- **Robot Arm**: `move()`, `grip()`, `release()`, `position()`, etc.
