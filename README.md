# AC-OTFlex Monorepo

A unified self-driving lab automation system combining hardware control, MQTT communication, and workflow orchestration.

**Language:** Primarily Python 3.8+

## Project Overview

AC-OTFlex is a modular automation platform for self-driving laboratories. This monorepo consolidates all components into a single, cohesive codebase:

- **Backend**: Core Python control system with device abstractions
- **Devices**: Modular IoT device libraries (Runze Pump, Heater, Furnace)
- **Config**: Centralized MQTT broker and device configuration
- **Docs**: System architecture, setup, and usage documentation
- **Workflows**: Jupyter notebook-based experiment scripts and orchestration

## Quick Start (2 minutes)

### Prerequisites
- Python 3.8+
- MQTT broker installed and running
- Hardware devices configured (Opentrons, Robot Arm, IoT devices)

### Installation

```bash
# 1. Navigate to project
cd AC-OTFlex-monorepo

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and edit configuration
cp config/example_config.json config/user_config.json
# Edit IPs/ports in user_config.json
```

### Testing (1 minute)

```bash
# Test all components (dry-run, no hardware needed)
python tests/run_all_tests.py --dry-run

# Test individual components
python tests/test_opentrons.py --test connection
python tests/test_arm.py --test availability --dry-run
python tests/test_furnace.py --test find-port
```

### Running Workflows (1 minute)

```bash
# List available workflows
python tests/test_workflows.py --test list

# Dry-run a workflow
python src/workflows/run_workflow.py --json data/workflows/simple_test_workflow.json --dry-run

# Production execution
python src/workflows/run_workflow.py --json data/workflows/completeflexelectrodep_workflow-FILLED.json
```

### Creating a Simple Workflow

```json
{
  "workflow": {
    "nodes": [
      {
        "id": "transfer_sample",
        "type": "otflexTransfer",
        "params": {
          "from": {"labware": "source", "well": "A1"},
          "to": {"labware": "dest", "well": "B1"},
          "volume_uL": 100
        }
      }
    ],
    "edges": []
  }
}
```

Save as `data/workflows/my_workflow.json` and run:
```bash
python src/workflows/run_workflow.py --json data/workflows/my_workflow.json --dry-run
```

## Documentation Index

| Document | Purpose |
|----------|---------|
| [docs/SETUP.md](docs/SETUP.md) | Installation and configuration |
| [docs/USAGE.md](docs/USAGE.md) | Workflow creation and execution |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and layers |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Development guidelines |
| [config/mqtt/README.md](config/mqtt/README.md) | MQTT broker setup |

## Common Commands

```bash
# Run all tests
python tests/run_all_tests.py --dry-run

# Test specific component
python tests/test_opentrons.py --test all
python tests/test_arm.py --test all --dry-run
python tests/test_furnace.py --test calibration

# Validate workflow JSON
python tests/test_workflows.py --test json-validation --workflow data/workflows/my_workflow.json

# Run workflow (dry-run)
python src/workflows/run_workflow.py --json data/workflows/my_workflow.json --dry-run

# Get help
python tests/test_opentrons.py --help
python src/workflows/run_workflow.py --help
```

## Configuration

Edit `config/user_config.json` for your setup:

```json
{
  "opentrons": {
    "controller_ip": "192.168.1.X"
  },
  "arm": {
    "controller_ip": "192.168.1.Y"
  },
  "arduino": {
    "fallback_port": "COM4"
  }
}
```

## Troubleshooting

### Can't import modules?
```bash
# Verify installation
pip install -r requirements.txt

# Check Python path
python -c "import sys; print(sys.path)"
```

### Can't find robot?
```bash
# Test connectivity
python tests/test_opentrons.py --test connection
python tests/test_arm.py --test availability --dry-run
python tests/test_furnace.py --test find-port
```

### JSON validation error?
```bash
# Validate workflow
python tests/test_workflows.py --test json-validation --workflow your_workflow.json
```

## Directory Structure

```
AC-OTFlex-monorepo/
├── backend/                       # Main control system
│   ├── src/                       # Python libraries
│   │   ├── controller/           # MQTT & workflow execution
│   │   ├── devices/              # High-level device abstractions
│   │   └── utils/                # Utilities
│   ├── workflows/                # Jupyter notebooks for experiments
│   ├── tests/                    # Test suite
│   ├── requirements.txt          # Backend dependencies
│   └── README.md
│
├── devices/                       # IoT device modules
│   ├── runze-pump/               # Peristaltic pump
│   │   ├── src/
│   │   ├── firmware/
│   │   ├── mechanical/
│   │   ├── electrical/
│   │   └── documentation/
│   ├── heater/                   # Temperature control
│   │   ├── src/
│   │   ├── firmware/
│   │   ├── mechanical/
│   │   ├── electrical/
│   │   └── documentation/
│   ├── furnace/                  # Furnace control
│   │   ├── src/
│   │   ├── firmware/
│   │   ├── mechanical/
│   │   ├── electrical/
│   │   └── documentation/
│   └── README.md
│
├── config/                        # System configuration
│   ├── mqtt/                     # MQTT broker configuration
│   ├── device_configs/           # Device parameter files
│   ├── experiment_params/        # Experiment parameter files
│   └── README.md
│
├── data/                          # Workflows and datasets
│   ├── workflows/                # Workflow JSON files
│   ├── device_configs/           # Device definitions
│   └── labware_definitions/      # Opentrons labware
│
├── docs/                          # Documentation
│   ├── ARCHITECTURE.md           # System design
│   ├── SETUP.md                  # Installation guide
│   ├── USAGE.md                  # Usage guide
│   ├── CONTRIBUTING.md           # Contribution guidelines
│   ├── workflows/                # Workflow documentation
│   ├── api/                      # API references
│   └── README.md
│
├── scripts/                       # Build & utility scripts
│   ├── utilities/                # Helpers and build tools
│   ├── archived/                 # Legacy scripts
│   └── README.md
│
├── src/                           # General source code
│   ├── adapters/                 # Device adapters
│   ├── core/                     # Runtime modules
│   └── workflows/                # Workflow orchestration
│
├── tests/                         # Test suite
├── README.md                      # This file
├── QUICK_START.md                 # Quick reference guide
├── .gitignore
├── requirements.txt               # Top-level dependencies
└── CONTRIBUTING.md
```

## Device Modules

Each IoT device is self-contained with its own importable library:

```python
from devices.runze_pump.src import RunzePump
from devices.heater.src import Heater
from devices.furnace.src import Furnace
```

## Backend Device Abstractions

High-level device interfaces for Opentrons and Robot Arm:

```python
from src.devices.opentrons import pickup_plate, dispense, transfer
from src.devices.robot_arm import move, grip, release, position
```

## Key Features

✅ **Organized Structure** - Files grouped logically  
✅ **Configuration Management** - Centralized settings  
✅ **Comprehensive Tests** - Test without hardware (dry-run mode)  
✅ **Full Documentation** - Setup, usage, architecture, contributing  
✅ **Clean Git** - Proper .gitignore included  
✅ **Python Packages** - Proper module structure with __init__.py  
✅ **Modular Design** - Easy to extend with new devices/adapters  
✅ **Type Hints** - Better IDE support and code documentation  

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Getting Help

1. Read [docs/SETUP.md](docs/SETUP.md) for installation issues
2. Read [docs/USAGE.md](docs/USAGE.md) for workflow questions
3. Run tests with `--dry-run` for debugging
4. Check component READMEs for device-specific help

## License

_To be added_

## Version History

- **v0.1.0** (March 2026) - Monorepo reorganization from separate repositories

