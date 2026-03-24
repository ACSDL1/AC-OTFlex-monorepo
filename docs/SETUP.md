# Setup Guide

## Prerequisites

- **Python:** 3.8 or higher (just get latest)
- **pip:** Package installer for Python
- **Git:** Version control (optional but recommended)
- **Mosquitto MQTT Broker:** For MQTT communication

## System Requirements

### OS Support
Windows, macOS, or Linux with Python 3.8+

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/ACSDL1/AC-OTFlex-monorepo.git
cd AC-OTFlex-monorepo
```

### 2. Create Virtual Environment

```bash
# On Windows:
python -m venv .venv
.venv\Scripts\activate

# On macOS/Linux:
python -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` prefix in your terminal.
This is where all dependencies will be installed, keeping your system Python clean.

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Networking Config 
> IMPORTANT: MQTT AND XARM RELIES ON CORRECT IPV4 ADDRESS OF HOST MACHINE

Set these host-side IPv4 addresses:
- MQTT network: `192.168.0.100/24`
- xArm network: `192.168.1.100/24`

You can add both addresses to the same NIC (if that is how your lab network is wired) or split them across two NICs.

### Linux

1. Find your interface name:

```bash
ip -br addr
```

2. Add the addresses (replace `enp4s0` with your interface):

```bash
sudo ip addr add 192.168.0.100/24 dev enp4s0
sudo ip addr add 192.168.1.100/24 dev enp4s0
```

This matches your working setup style (for example, using `enp4s0`).

3. Verify:

```bash
ip -br addr show dev enp4s0
```

Note: `ip addr add` is temporary and resets on reboot unless persisted via NetworkManager/netplan/systemd-networkd.

### Windows

Run PowerShell as Administrator.

1. Find your adapter name:

```powershell
Get-NetAdapter
```

2. Add both addresses (replace `Ethernet` with your adapter alias):

```powershell
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.0.100 -PrefixLength 24 -AddressFamily IPv4
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.1.100 -PrefixLength 24 -AddressFamily IPv4
```

3. Verify:

```powershell
Get-NetIPAddress -InterfaceAlias "Ethernet" -AddressFamily IPv4
```

Alternative (GUI):
Control Panel > Network and Sharing Center > Change adapter settings > Right-click adapter > Properties > Internet Protocol Version 4 (TCP/IPv4) > Advanced > Add both IP addresses.



## MQTT Config 
The system uses MQTT for communication between the core control and devices. You can use Mosquitto as the MQTT broker.

Jump to Alan's [MQTT Setup README](../config/mqtt/README.md) for detailed setup instructions

## Hardware Setup
Refer to the individual device repositories in `devices/` for hardware-specific setup instructions. Each device type (pump, heater, furnace, reactor, etc.) has its own README with wiring diagrams, connection instructions, and testing procedures.
> this should already be setup and tested by GavinT, but listed here for completeness

## Usage
Jump to [docs/USAGE.md](USAGE.md) for how to run the system and execute workflows.

