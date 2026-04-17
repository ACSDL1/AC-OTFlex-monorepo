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

# Device Sketches

A collection of Arduino sketches for each module in the MQTT tower system. Each sketch is organized by device type in its own sketch folder, as required by the Arduino framework.

Arduino IDE or Arduino CLI can be used to compile and upload these sketches to the respective hardware modules.

The Arduino CLI method is recommended for better version control and automation, especially when working in a team or managing multiple devices.

## Hardware

ESP32-based modules (Olimex ESP32-POE-ISO).

## Networking
- Host: running MQTT broker (Mosquitto) and Python controller script
	- set IPv4 address: 192.168.100.1
- ESP32 devices: connect to MQTT broker over Wi-Fi or Ethernet (depending on module)

### Modules
- Heater Module
	- 192.168.0.50
- Ultrasonic Module
	- 192.168.0.51
- Pump Module
	- 192.168.0.52

## Workflow

### Arduino CLI

1. **Install Arduino CLI**: Follow instructions at https://arduino.github.io/arduino-cli/latest/installation/

	- Currently using version 1.4.1 (W26 term)

2. **Install the ESP32 board package:**

```bash
arduino-cli core update-index
arduino-cli core install esp32:esp32
```

3. **Install required libraries:** (Arduino IDE can also be used here via Library Manager if preferred)

	**Arduino CLI libraries**

	```bash
	arduino-cli lib install "WiFi"
	arduino-cli lib install "PubSubClient"
	arduino-cli lib install "Adafruit ADS1X15"
	arduino-cli lib install "AutoPID"
	```

	**Manual installs (from vendor GitHub)**

	- SparkFun Qwiic Relay
	- SparkFun SerLCD


#### Compile and Upload

Navigate to the sketch folder and compile/upload:

```bash
cd <path_to_sketch>
arduino-cli compile --fqbn esp32:esp32:esp32-poe-iso <sketch_name>.ino
arduino-cli upload -p <PORT> --fqbn esp32:esp32:esp32-poe-iso <sketch_name>.ino
```

**Note**: On Windows, `<PORT>` is typically `COM3`, `COM4`, etc. On Linux/macOS, it's typically `/dev/ttyUSB0` or `/dev/ttyACM0`.