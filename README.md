# AC_OTFlex_Workflow - Automated Laboratory Workflow System

An integrated system for coordinating automated laboratory equipment including Opentrons Flex liquid handling robot, UFactory xArm robotic arm, and Arduino-controlled furnace systems. Workflows are defined in JSON format and executed with support for parallel/sequential task execution.

**Language:** Primarily Python 3.8+

## Quick Start

### Prerequisites
- Python 3.8+
- Opentrons Flex robot (IP: 169.254.179.32)
- UFactory xArm robot (IP: 192.168.1.113)
- Arduino-based furnace system (Serial: COM4)

### Installation

1. **Clone repository:**
   ```bash
   git clone <repository-url>
   cd AC_OTFlex_Workflow
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure system:**
   ```bash
   cp config/example_config.json config/user_config.json
   # Edit config/user_config.json with your IP addresses and settings
   ```

### Running Tests

Test individual components before running full workflows:

```bash
# Test Opentrons connectivity
python tests/test_opentrons.py --ip 169.254.179.32

# Test xArm connectivity
python tests/test_arm.py --ip 192.168.1.113 --dry-run

# Test Arduino furnace
python tests/test_furnace.py --port COM4 --dry-run

# Test workflow parsing
python tests/test_workflows.py --workflow data/workflows/simple_test_workflow.json

# Run all tests
python tests/run_all_tests.py --dry-run
```

### Running Workflows

```bash
# List available workflows
python tests/test_workflows.py --test list

# Execute a workflow (dry-run mode)
python src/workflows/run_workflow.py --json data/workflows/simple_test_workflow.json --dry-run

# Execute a workflow (production mode)
python src/workflows/run_workflow.py --json data/workflows/completeflexelectrodep_workflow-FILLED.json
```

## Directory Structure

```
AC_OTFlex_Workflow/
├── src/                           # Main source code
│   ├── core/                      # Core runtime modules
│   │   ├── opentrons.py          # Opentrons Flex client
│   │   ├── myxArm_Utils.py       # xArm robot utilities
│   │   ├── myxArm_Utils_dryrun.py # xArm dry-run mode
│   │   ├── arm_runtime.py        # ARM runtime wrapper
│   │   └── otflex_runtime.py     # Opentrons runtime wrapper
│   ├── adapters/                  # Device adapters (parameter normalization)
│   │   ├── otflex_adapter.py     # Opentrons adapter
│   │   └── arm_adapter.py        # ARM adapter
│   ├── workflows/                 # Workflow execution engine
│   │   ├── run_workflow.py       # Main workflow orchestrator
│   │   ├── OTFLEX_WORKFLOW_Iliya.py      # Live workflow
│   │   └── OTFLEX_WORKFLOW_Iliya_dryrun.py # Dry-run workflow
│   ├── __init__.py
│   └── config_manager.py         # Configuration management
│
├── config/                        # Configuration files
│   ├── default_config.json       # Default configuration
│   ├── example_config.json       # Example configuration
│   └── experimentParams.json     # Experiment parameters
│
├── data/                          # Data files and definitions
│   ├── workflows/                 # Workflow definitions (JSON)
│   │   ├── simple_test_workflow.json
│   │   ├── completeflexelectrodep_workflow-FILLED.json
│   │   ├── reactor.json
│   │   ├── parallelTest.json
│   │   ├── furnaceTest.json
│   │   └── completeTest.json
│   ├── labware_definitions/       # Opentrons labware definitions
│   ├── device_configs/            # Device-specific configurations
│   ├── params.csv                 # Experiment parameters
│   └── sources.csv                # Chemical source definitions
│
├── tests/                         # Test scripts for components
│   ├── test_opentrons.py         # Opentrons connectivity tests
│   ├── test_arm.py               # ARM connectivity tests
│   ├── test_furnace.py           # Arduino furnace tests
│   ├── test_workflows.py         # Workflow execution tests
│   └── run_all_tests.py          # Master test runner
│
├── scripts/                       # Utility and maintenance scripts
│   ├── fix_indentation.py        # Code formatting utility
│   ├── test_imports.py           # Dependency verification
│   ├── inspect_workflow.py       # Workflow inspection tool
│   ├── gripper_tuner.py          # Gripper tuning utility
│   └── archived_potentiostat/    # Old potentiostat code
│
├── docs/                          # Documentation
│   ├── ARCHITECTURE.md           # System architecture
│   ├── SETUP.md                  # Setup instructions
│   ├── USAGE.md                  # Usage guide
│   └── CONTRIBUTING.md           # Contributing guidelines
│
├── README.md                      # This file
├── .gitignore                     # Git ignore rules
├── requirements.txt               # Python dependencies
└── .venv/                         # Virtual environment (not tracked)
```

## System Architecture

The system follows a **layered architecture** for clean separation of concerns:

```
┌─────────────────────────┐
│   Workflow JSON File    │
└────────────┬────────────┘
             │
             ▼
┌──────────────────────────────┐
│  WorkflowRunner              │
│  (Parsing & Orchestration)   │
└────────────┬─────────────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
┌─────────────┐   ┌──────────────┐
│ OTFlex      │   │ MyxArm       │
│ Adapter     │   │ Adapter      │
│ (normalize) │   │ (normalize)  │
└────────────┬┘   └──────────┬───┘
             │               │
    ┌────────▼───────────────▼┐
    │   Device Runtimes       │
    │ (otflex_runtime.py,     │
    │  arm_runtime.py)        │
    └────────┬───────────────┬┘
             │               │
    ┌────────▼────┐   ┌──────▼──────┐
    │  opentrons  │   │ myxArm      │
    │  (hardware) │   │ (hardware)  │
    └─────────────┘   └─────────────┘
```

## Configuration Management

All hardcoded values have been extracted to configuration files:

### Opentrons Configuration
- **IP Address:** `config.opentrons.controller_ip` (default: 169.254.179.32)
- **Robot Type:** `config.opentrons.robot_type` (default: flex)
- **Pipette Settings:** Move speed, aspirate/dispense flow rates
- **Deck Layout:** Configured in workflow JSON

### ARM Configuration
- **IP Address:** `config.arm.controller_ip` (default: 192.168.1.113)
- **Port:** `config.arm.port` (default: 5001)
- **Motion Parameters:** TCP speed, acceleration, angle parameters

### Arduino Configuration
- **Port:** `config.arduino.fallback_port` (default: COM4)
- **Baud Rate:** `config.arduino.baud_rate` (default: 115200)
- **Pump Calibration:** Per-pump slope and intercept values
- **Heater Setpoints:** Per-cartridge temperature settings

### Usage
```python
from src.config_manager import get_config

config = get_config()
otflex_ip = config.get("opentrons.controller_ip")
arm_ip = config.get("arm.controller_ip")
```

## Workflow Format

Workflows are defined in JSON with the following structure:

```json
{
  "workflow": {
    "nodes": [
      {
        "id": "transfer_1",
        "type": "otflexTransfer",
        "params": {
          "from": {"labware": "source", "well": "A1"},
          "to": {"labware": "dest", "well": "B1"},
          "volume_uL": 100
        }
      }
    ],
    "edges": [
      {
        "source": "transfer_1",
        "target": "transfer_2",
        "metadata": {"parallel": false}
      }
    ]
  },
  "devices": {
    "otflex": {...},
    "arm": {...}
  }
}
```

## Testing

The project includes comprehensive test suites for each component:

```bash
# Test individual components
python tests/test_opentrons.py --test connection
python tests/test_arm.py --test availability
python tests/test_furnace.py --test calibration
python tests/test_workflows.py --test json-validation

# Run full test suite
python tests/run_all_tests.py --dry-run

# Test with specific configuration
python tests/test_opentrons.py --ip 169.254.179.32 --test all
```

## Dry-Run Mode

All components support dry-run mode for testing without hardware:

```bash
# Dry-run test
python tests/run_all_tests.py --dry-run

# Dry-run workflow execution
python src/workflows/run_workflow.py --json data/workflows/simple_test_workflow.json --dry-run
```

## Common Issues

### Cannot connect to Opentrons Flex
- Check IP address: 169.254.179.32 (auto-assigned, may vary)
- Verify network connection to robot
- Check firewall settings
- Run: `python tests/test_opentrons.py --test connection`

### Cannot connect to xArm
- Check xArm is powered on and connected to network
- Verify IP address (usually 192.168.1.113)
- Check port 5001 is open
- Ensure xArm SDK is installed: `pip install xarm-python-sdk`

### Arduino not found
- Check serial port: `python tests/test_furnace.py --test find-port`
- Common Windows ports: COM3, COM4, COM5
- Common Linux ports: /dev/ttyUSB0, /dev/ttyACM0

### Module import errors
- Run `pip install -r requirements.txt`
- Verify Python version >= 3.8
- Check all __init__.py files are present in src/ subdirectories

## Workflow Examples

### Simple Liquid Transfer
See `data/workflows/simple_test_workflow.json`

### Complete Electrodeposition
See `data/workflows/completeflexelectrodep_workflow-FILLED.json`

### Parallel Operations
See `data/workflows/parallelTest.json`

### Furnace Control
See `data/workflows/furnaceTest.json`

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [Setup Guide](docs/SETUP.md) - Installation and configuration
- [Usage Guide](docs/USAGE.md) - How to use the system
- [Contributing](docs/CONTRIBUTING.md) - Contributing guidelines

## License

[Add your license information here]

## Contact

[Add contact information here]

## Version History

- **v1.0.0** (Feb 2026) - Initial organized release with comprehensive documentation

