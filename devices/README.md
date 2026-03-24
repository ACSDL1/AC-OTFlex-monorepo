# Devices

## Overview

This directory contains all hardware devices used in the AC-OTFlex system. Each device is self-contained, modular, and can be accessed or replaced independently without affecting other components.

Each device is designed to be used atomically and modularly:
- Atomic: each hardware subsystem can be tested and operated on its own
- Modular: each subsystem can be swapped or updated with minimal impact on other devices

## Device Structure

Each device folder contains some or all of the following:
- **README.md** - Device overview, how it works, and setup instructions
- **src/** - Python library code for device control
- **firmware/** - Device firmware (ESP32/etc.)
- **electrical/** - Wiring diagrams, schematics, and circuit documentation
- **mechanical/** - CAD models, mechanical designs, and assembly instructions
- **documentation/** - Additional device-specific documentation

Every device should have a device-level `README.md` that explains:
- how the device works
- how to set it up
- where wiring documentation and setup/duplication images are located

## Device Notes

- **furnace/** - Firmware controls the linear actuator used to open the furnace door
- **heater/** - Heater module (kept as currently documented)
- **potentiostat/** - Biologic potentiostat integration (no repository control code yet)
- **pump/** - Pump module (kept as currently implemented)
- **raspi-camera/** - Raspberry Pi 5 camera system using `picamera2`, initially configured via mobile hotspot, controlled from host via Paramiko
- **reactor/** - Autoreactor with 2 linear actuators to raise/lower the reactor for substrate plate pickup
- **syringe-pump/** - 12-channel syringe-pump setup for multi-liquid dispensing through the same outlet tube
- **ultrasonic/** - Ultrasonic sonic-cleaner module

## Getting Started with a Device

1. **Navigate to the device folder:**
   ```bash
   cd devices/[device_name]/
   ```

2. **Read the device README:**
   - Open `README.md` in the device folder
   - Learn how the device works
   - Follow setup and configuration instructions

3. **Review wiring documentation:**
   - Check `electrical/` directory for wiring diagrams
   - Review connection schematics
   - Verify pin configurations

4. **Access device firmware and code:**
   - Device firmware is in `firmware/` directory
   - Python control code is in `src/` directory
   - Use these to understand and modify device behavior

## Using Devices in Workflows

Devices are accessed through the adapters layer in `src/adapters/`. Individual device operations are exposed as high-level functions that can be called from workflow notebooks.