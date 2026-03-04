# Configuration

## Purpose
Centralized configuration files for the system including MQTT broker setup and device/experiment parameters.

## Structure
- `mqtt/` - MQTT broker configuration
  - `mosquitto.conf` - Broker configuration
  - `aclfile.txt` - Access control list
  - `README.md` - Setup instructions
- `device_configs/` - Individual device configuration JSON files
- `experiment_params/` - Experiment parameter files

## Usage
Configure MQTT broker in `config/mqtt/` and device settings in `config/device_configs/`
