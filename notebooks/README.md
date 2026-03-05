# Python MQTT API — ESP32-POE-ISO Device Control

This document explains how to use the **Python MQTT API (`iot_mqtt.py`)** to control ESP32-POE-ISO device nodes (pumps, heaters, ultrasonic drivers) via MQTT communication.

## Quick Links

- **[Broker Setup](../mosquitto_config/README.md)** - Mosquitto installation and configuration
- **[Device Firmware](../devices/)** - ESP32 firmware for pumps, heaters, and ultrasonic controllers
- **[Hardware Assembly](../hardware/README.md)** - 3D printable enclosures and assembly

---

## 1. Overview

The MQTT network consists of:
- **Broker:** Mosquitto server (usually on your PC or Raspberry Pi)
- **Controller:** Python beacon (publishes heartbeat + commands)
- **ESP32 Nodes:** individual clients (pumps, ultrasonic, heater)

Each device uses authentication and a dedicated topic subtree for clean separation.

## 2. Installation

```bash
# Install Python dependencies
pip install paho-mqtt>=1.6.0

# Or use requirements.txt
pip install -r requirements.txt
```

---

## 3. Broker Setup (Mosquitto)

> **Note**: For detailed broker setup instructions, see [Mosquitto Configuration Guide](../mosquitto_config/README.md).

### Installation
**Windows**
```bash
choco install mosquitto
````

**Linux**

```bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl enable mosquitto
```

### Configuration

Edit `mosquitto_config/mosquitto.conf`:

```conf
listener 1883
allow_anonymous false
password_file "C:/Program Files/mosquitto/passwd"
acl_file      "C:/Program Files/mosquitto/aclfile.txt"
persistence true
persistence_location "C:/Program Files/mosquitto/data/"
```

### Create Users

```bash
mosquitto_passwd -c passwd pyctl-controller
mosquitto_passwd    passwd pump1
mosquitto_passwd    passwd ultra1
mosquitto_passwd    passwd heat1
```

### Launch Broker

```bash
mosquitto -v -c "C:/Program Files/mosquitto/mosquitto.conf"
```

---

## 3. Access Control

Example ACL (`mosquitto_config/aclfile.txt`):

```text
# Controller
user pyctl-controller
topic write pyctl/#
topic read  pumps/01/#
topic read  ultra/01/#
topic read  heat/01/#

# Pump
user pump1
topic read pyctl/#
topic write pumps/01/#

# Ultrasonic
user ultra1
topic read pyctl/#
topic write ultra/01/#

# Heater
user heat1
topic read pyctl/#
topic write heat/01/#
```

---

## 4. Python MQTT Library (`iot_mqtt.py`)

### Quick Example

```python
# iot_mqtt_demo.py
import time
from iot_mqtt import start_broker_if_needed, stop_broker
from iot_mqtt import PumpMQTT, UltraMQTT, HeatMQTT

# Optional: start a local Mosquitto on Windows if not already running
proc = start_broker_if_needed()  # comment if your broker is already running

# Start controller beacon
beacon = ControllerBeacon(
    broker=broker,
    username="pyctl-controller", password="controller",
    status_topic="pyctl/status", heartbeat_topic="pyctl/heartbeat",
    heartbeat_interval=5.0, keepalive=30,
)
beacon.start()

# Create clients (replace IP with your broker's LAN IP)
pumps = PumpMQTT(broker="192.168.0.101", username="pico1",  password="pump",
                 base_topic="pumps/01", client_id="pyctl-pumps")
ultra = UltraMQTT(broker="192.168.0.101", username="ultra1", password="ultra",
                  base_topic="ultra/01", client_id="pyctl-ultra")
heat  = HeatMQTT(broker="192.168.0.101", username="heat1",  password="heat",
                 base_topic="heat/01",  client_id="pyctl-heat")

# Connect + start background loops
pumps.ensure_connected(); ultra.ensure_connected(); heat.ensure_connected()
time.sleep(1)  # let subscriptions settle

# Quick status snapshots (retained + live)
pumps.status(seconds=2.0)
ultra.status(seconds=2.0)
heat.status(seconds=2.0)

# ---- Control examples ----
# Pumps
pumps.on(1); time.sleep(1)
pumps.on(1, 2000)            # auto-off after 2s
time.sleep(2.5)

# Ultrasonic
ultra.on_for(2, 1500)        # ch2 for 1.5s
time.sleep(2)

# Heaters (PID demo)
heat.set_base_temp(1, 42.0)  # retained at heat/01/target/1
heat.pid_on(1)

# Read temp for ~30s
for _ in range(30):
    try:
        t = heat.get_base_temp(1, timeout_s=2.0)
        print("Heater1 Temp =", t)
    except TimeoutError:
        print("Temp read timeout")
    time.sleep(1)

# Stop PID and ensure OFF
heat.pid_off(1)
heat.set_pwm(1, 0)
heat.off(1)

# Cleanup
pumps.disconnect(); ultra.disconnect(); heat.disconnect()
stop_broker(proc)
```

### Command Payloads

| Category    | Command                | Example Payload | Description                           |
| ----------- | ---------------------- | --------------- | ------------------------------------- |
| **General** | `ON`, `OFF`, `ON:<ms>` | `ON:2000`       | Turn relay ON for given ms (auto-off) |
| **Heater**  | `PWM:<0–100>`          | `PWM:50`        | Apply PWM % output                    |
|             | `SET:<temp>`           | `SET:42.0`      | Set PID target                        |
|             | `PID:ON` / `PID:OFF`   | —               | Enable/disable PID loop               |
|             | `GET`                  | —               | Request temperature publish           |

---

## 5. Topic Map Summary

| Topic               | Direction        | Description               |
| ------------------- | ---------------- | ------------------------- |
| `<base>/cmd/<n>`    | Controller → ESP | Command for channel n     |
| `<base>/state/<n>`  | ESP → Controller | Actuator state            |
| `<base>/temp/<n>`   | ESP → Controller | Temperature (heater)      |
| `<base>/target/<n>` | ESP → Controller | PID target                |
| `<base>/status`     | ESP ↔ Controller | ONLINE/OFFLINE (retained) |
| `<base>/heartbeat`  | ESP ↔ Controller | “1” periodically          |
| `pyctl/status`      | Controller ↔ ESP | Controller ONLINE/OFFLINE |
| `pyctl/heartbeat`   | Controller ↔ ESP | Controller heartbeat      |

---

## 6. Safety Behavior

| Condition               | Action                                            |
| ----------------------- | ------------------------------------------------- |
| No controller heartbeat | All outputs OFF                                   |
| MQTT disconnected       | All outputs OFF                                   |
| Ethernet down           | All outputs OFF                                   |
| Controller crash        | LWT sets `pyctl/status = OFFLINE` → all nodes OFF |
| ON command no duration  | Auto OFF after lease (`MAX_ON_LEASE_MS`)          |

---

## 7. Troubleshooting

* **Broker rejects connection:** recheck user/pass and ACL.
* **No telemetry:** verify ESP node IP and Ethernet link.
* **Device doesn’t turn OFF after PC crash:** check LWT enabled and controller beacon running.
* **“CTRL timeout” warnings:** ensure first heartbeat received before timeout starts.

---

## 8. References

* [Mosquitto Docs](https://mosquitto.org/documentation/)
* [Paho MQTT Python Client](https://pypi.org/project/paho-mqtt/)
* [ESP32 Arduino PubSubClient](https://github.com/knolleary/pubsubclient)

---

## 🪪 License

MIT © 2025 Alan Yang

