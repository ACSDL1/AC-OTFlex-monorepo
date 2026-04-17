# Pump Serial Controller

A standalone device driver for controlling two peristaltic pumps via an ESP32 microcontroller with SparkFun Qwiic Quad Relay module.

## Features

- **Serial Control**: Simple text-based serial protocol (115200 baud)
- **Timed Operation**: Set pump runtime in milliseconds
- **Dual Pump Support**: Independent control of two pumps
- **Hardware Feedback**: Status monitoring via serial
- **Low-power**: Relay-based switching with opposite state control logic

## Project Structure

```
devices/pump_serial/
├── firmware/
│   └── pump_serial.ino          # ESP32 Arduino firmware
├── src/
│   └── pump_serial.py           # Python control adapter
├── notebooks/
│   └── Pump_Serial_Controller.ipynb  # Interactive usage examples
└── README.md                    # This file
```

## Hardware Setup

### Components
- ESP32 microcontroller (tested on ESP32-POE-ISO)
- SparkFun Qwiic Quad Relay (I2C address 0x7F)
- Two 12V DC peristaltic pumps
- 12V DC power supply

### Wiring Configuration
- All relay NO (normally open) contacts → +12V
- All relay NC (normally closed) contacts → -12V (connected together)

### Pump Connections
- **Pump 1**: negative on relay 1, positive on relay 2
- **Pump 2**: negative on relay 3, positive on relay 4

## Relay Control Logic

Since commands are sent via opposite relay states:

- **Pump ON**: Relay_neg ON (+12V), Relay_pos OFF (-12V) → 24V across pump
- **Pump OFF**: Both relays same state → 0V across pump

Example:
- `PUMP1:ON` → Relay 1 ON, Relay 2 OFF
- `PUMP1:OFF` → Relay 1 OFF, Relay 2 OFF

## Serial Commands

| Command | Description |
|---------|-------------|
| `PUMP1:ON` | Turn pump 1 on indefinitely |
| `PUMP1:OFF` | Turn pump 1 off |
| `PUMP1:ON:3000` | Turn pump 1 on for 3000 ms |
| `PUMP2:ON` | Turn pump 2 on indefinitely |
| `PUMP2:OFF` | Turn pump 2 off |
| `PUMP2:ON:2000` | Turn pump 2 on for 2000 ms |
| `STATUS` | Print current pump states |

## Python Usage

### Installation

```bash
pip install pyserial
```

### Basic Example

```python
from devices.pump_serial.src.pump_serial import PumpSerial

# Connect to pump controller
pump = PumpSerial("/dev/ttyUSB0")

# Turn pump 1 on for 3 seconds
pump.on(1, 3000)

# Turn pump 2 on indefinitely
pump.on(2)

# Check status
pump.status()

# Turn pumps off
pump.off(1)
pump.off(2)

# Close connection
pump.close()
```

### Context Manager

```python
with PumpSerial("/dev/ttyUSB0") as pump:
    pump.on(1, 5000)
    pump.status()
    pump.off(1)
# Connection automatically closed
```

## Firmware Upload

### Arduino CLI

```bash
cd devices/pump_serial/firmware
arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32-poe-iso pump_serial.ino
```

### Arduino IDE

1. Open `pump_serial.ino` in Arduino IDE
2. Select board: **Espressif Systems → ESP32-POE-ISO**
3. Select port: **/dev/ttyUSB0** (or your device)
4. Click Upload

## Testing

Run the included Jupyter notebook:

```bash
jupyter notebook devices/pump_serial/notebooks/Pump_Serial_Controller.ipynb
```

Or test directly from Python:

```bash
python devices/pump_serial/src/pump_serial.py /dev/ttyUSB0
```

## Troubleshooting

### Relay not detected
- Check I2C address (default 0x7F)
- Verify Qwiic connections
- Check if `Wire.begin()` completes successfully

### Pump won't start
- Verify opposite relay states (check `[ACTION]` log messages)
- Confirm 12V power supply is connected
- Check pump connections to relay terminals

### Serial port issues
- Verify device appears as `/dev/ttyUSB0` (Linux) or `COM3` (Windows)
- Check baud rate is 115200
- Ensure USB cable supports data transfer

## License

Part of AC-OTFlex monorepo
