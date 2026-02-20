# Setup Guide

## Prerequisites

- **Python:** 3.8 or higher
- **pip:** Package installer for Python
- **Git:** Version control (optional but recommended)

## System Requirements

### OS Support
Windows, macOS, or Linux with Python 3.8+

### Network Requirements
- Opentrons Flex: Network connectivity (default IP: 169.254.179.32)
- xArm Robot: Network connectivity (default IP: 192.168.1.113)
- Arduino: USB serial connection (default: COM4)

## Installation Steps

### 1. Clone or Download Repository

```bash
git clone <repository-url>
cd AC_OTFlex_Workflow
```

Or download and extract the ZIP file.

### 2. Verify Python Installation

```bash
python --version
# Should output: Python 3.8.0 or higher

python -m venv --help
# Verify venv module is available
```

### 3. Create Virtual Environment

```bash
# On Windows:
python -m venv venv
venv\Scripts\activate

# On macOS/Linux:
python -m venv venv
source venv/bin/activate
```

You should see `(venv)` prefix in your terminal.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs all required packages including:
- `requests` - HTTP client for Opentrons
- `xarm-python-sdk` - xArm robot control
- `pyserial` - Arduino serial communication
- `pandas` - Data handling
- `numpy` - Numerical computation

### 5. Verify Installation

```bash
python -c "import requests; import pandas; import numpy; print('✓ Core packages installed')"
```

For xArm SDK (optional):
```bash
python -c "from xarm.wrapper import XArmAPI; print('✓ xArm SDK installed')"
```

## Configuration

### 1. Create User Configuration File

```bash
cp config/example_config.json config/user_config.json
```

### 2. Edit Configuration

Open `config/user_config.json` and update:

```json
{
  "opentrons": {
    "controller_ip": "YOUR_ROBOT_IP",  // e.g., 169.254.179.32
    "robot_type": "flex"
  },
  "arm": {
    "controller_ip": "YOUR_ARM_IP",    // e.g., 192.168.1.113
    "port": 5001
  },
  "arduino": {
    "fallback_port": "COM4",           // On Linux: /dev/ttyUSB0
    "baud_rate": 115200
  }
}
```

### 3. Device-Specific Configuration

#### Opentrons Flex

1. **Find IP Address:**
   - Power on Opentrons Flex
   - On robot's touchscreen: Settings → Network → IP Address
   - Default: `169.254.179.32`

2. **Test Connection:**
   ```bash
   python tests/test_opentrons.py --ip 169.254.179.32 --test connection
   ```

#### xArm Robot

1. **Find IP Address:**
   - Power on xArm
   - Check xArm controller or network router
   - Default: `192.168.1.113`

2. **Test Connection:**
   ```bash
   python tests/test_arm.py --ip 192.168.1.113 --dry-run
   ```

#### Arduino Furnace

1. **Find Serial Port:**
   ```bash
   python tests/test_furnace.py --test find-port
   ```
   
   **Windows:** Look for COM3, COM4, COM5, etc.
   
   **Linux/macOS:** Look for /dev/ttyUSB0, /dev/ttyACM0, etc.

2. **Update Configuration:**
   ```json
   {
     "arduino": {
       "fallback_port": "COM4"  // Or /dev/ttyUSB0
     }
   }
   ```

3. **Test Connection:**
   ```bash
   python tests/test_furnace.py --port COM4 --test connection
   ```

## Verify Installation

### Quick Test

```bash
# Dry-run all component tests
python tests/run_all_tests.py --dry-run
```

Expected output:
```
=== Opentrons Flex Test Suite ===
✓ Opentrons connectivity: PASSED
✓ Labware loading: PASSED
...

=== UFactory xArm Test Suite ===
✓ xArm SDK availability: PASSED
...

=== Arduino Furnace Control Test Suite ===
✓ Arduino serial connection: PASSED
...

=== Overall Results ===
All tests PASSED ✓
```

### Component-Specific Tests

```bash
# Test Opentrons only
python tests/test_opentrons.py --test all

# Test ARM only
python tests/test_arm.py --test all --dry-run

# Test Arduino only
python tests/test_furnace.py --test all

# Test workflow parsing
python tests/test_workflows.py --test list
```

## Troubleshooting

### Python Version Issues

**Error:** `ModuleNotFoundError: No module named 'asyncio'`

**Solution:** Upgrade Python to 3.8+
```bash
python --version
# If < 3.8, install Python 3.8+
```

### Virtual Environment Issues

**Error:** `python: No module named venv`

**Solution:** Install venv module
```bash
# Ubuntu/Debian
sudo apt-get install python3-venv

# macOS
brew install python3

# Windows
# Reinstall Python with venv option
```

### Package Installation Issues

**Error:** `pip: command not found`

**Solution:** Use python -m pip
```bash
python -m pip install -r requirements.txt
```

**Error:** `Permission denied` when installing

**Solution:** Use --user flag
```bash
pip install --user -r requirements.txt
```

### Cannot Connect to Opentrons

**Error:** `Connection refused` or `timeout`

**Checklist:**
1. Is Opentrons powered on? ✓
2. Is IP address correct? ✓
3. Are you on the same network? ✓
4. Is firewall blocking port 31950? ✓

**Test:**
```bash
ping 169.254.179.32
# Should respond with pings

curl -X GET http://169.254.179.32:31950/runs
# Should return JSON response
```

### Cannot Connect to xArm

**Error:** `Connection timeout`

**Checklist:**
1. Is xArm powered on? ✓
2. Is xArm connected to network? ✓
3. Is IP address correct? ✓
4. Is port 5001 open? ✓

**Test:**
```bash
python -c "from xarm.wrapper import XArmAPI; arm = XArmAPI('192.168.1.113'); print(arm.get_version())"
```

### Cannot Find Arduino

**Error:** `No Arduino ports found`

**Checklist:**
1. Is Arduino plugged in? ✓
2. Is Arduino recognized by OS? ✓
3. Is driver installed? ✓

**Diagnose:**
```bash
# Windows - List COM ports
wmic logicaldisk get name
wmic pnpdevice where "DeviceID like 'COM%'" list
Get-WmiObject Win32_PnPEntity | Where-Object { $_.Name -match "COM" }

# Linux/macOS
ls /dev/tty*
ls /dev/cu.*
```

**Install Drivers:**
- CH340 chip: https://sparks.gogo.co.nz/ch340.html
- FTDI chip: https://www.ftdichip.com/Drivers/D2XX.htm

### Import Errors

**Error:** `ModuleNotFoundError: No module named 'xarm'`

**Solution:**
```bash
pip install xarm-python-sdk
```

**Error:** `ModuleNotFoundError: No module named 'requests'`

**Solution:**
```bash
pip install -r requirements.txt
```

## Development Setup

### Clone Repository with Git

```bash
git clone <repository-url>
cd AC_OTFlex_Workflow
```

### For Code Editors

#### VS Code

1. Install Python extension
2. Select Python interpreter:
   - Command: Python: Select Interpreter
   - Choose: `./venv/bin/python`

3. Install useful extensions:
   - Python Docstring Generator
   - Pylance
   - Git History

#### PyCharm

1. Open project
2. Configure interpreter:
   - Settings → Project → Python Interpreter
   - Add venv: `./venv/bin/python`

## Production Deployment

### Before First Run

1. **Backup Configurations:**
   ```bash
   cp config/user_config.json config/user_config.json.backup
   ```

2. **Check Hardware:**
   - Opentrons: Test run simple commands
   - xArm: Home robot and check motion
   - Arduino: Verify serial communication

3. **Run Validation:**
   ```bash
   python tests/test_workflows.py --test all
   ```

### Emergency Stop

If something goes wrong:

1. **Kill Python Process:**
   ```bash
   # Windows
   taskkill /IM python.exe /F

   # Linux/macOS
   killall python3
   ```

2. **Kill Important Processes:**
   ```bash
   # Windows
   taskkill /IM opentrons.exe /F

   # Hardware disconnect
   ```

3. **Check Logs:**
   ```bash
   cat logs/workflow.log  # Linux/macOS
   type logs\workflow.log  # Windows
   ```

## Next Steps

1. Review [USAGE.md](USAGE.md) for how to create workflows
2. Check [ARCHITECTURE.md](ARCHITECTURE.md) for system design
3. Review example workflows in `data/workflows/`
4. Run tests to verify setup

## Getting Help

1. **Check Logs:**
   ```bash
   tail -f logs/workflow.log
   ```

2. **Run Diagnostic Tests:**
   ```bash
   python tests/run_all_tests.py --dry-run
   ```

3. **Consult Documentation:**
   - [ARCHITECTURE.md](ARCHITECTURE.md) - System design
   - [USAGE.md](USAGE.md) - How to use
   - Test files - Example code

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review test output
3. Check documentation
4. Contact system administrator
