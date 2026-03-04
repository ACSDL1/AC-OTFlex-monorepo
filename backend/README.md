# Backend

## Purpose
Main control system for the OTFlex self-driving lab. Contains the core Python libraries for controlling IoT devices via MQTT, high-level device abstractions (Opentrons, Robot Arm), and workflow execution through Jupyter notebooks.

## Structure
- `src/` - Python source code
  - `controller/` - MQTT controller and workflow executor
  - `devices/` - High-level device abstractions (Opentrons, Robot Arm)
  - `utils/` - Utility functions and helpers
- `workflows/` - Jupyter notebooks defining experiments and workflows
- `tests/` - Unit and integration tests
- `requirements.txt` - Python dependencies

## Usage
Import device libraries in Jupyter notebooks to construct workflows:
```python
from src.devices.opentrons import pickup_plate, dispense
from src.devices.robot_arm import move, grip
```
