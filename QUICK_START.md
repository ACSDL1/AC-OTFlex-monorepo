# Quick Reference Guide

## Installation (2 minutes)

```bash
# 1. Navigate to project
cd AC_OTFlex_Workflow

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and edit configuration
cp config/example_config.json config/user_config.json
# Edit IPs/ports in user_config.json
```

## Testing (1 minute)

```bash
# Test all components (dry-run, no hardware needed)
python tests/run_all_tests.py --dry-run

# Test individual components
python tests/test_opentrons.py --test connection
python tests/test_arm.py --test availability --dry-run
python tests/test_furnace.py --test find-port
```

## Running Workflows (1 minute)

```bash
# List available workflows
python tests/test_workflows.py --test list

# Dry-run a workflow
python src/workflows/run_workflow.py --json data/workflows/simple_test_workflow.json --dry-run

# Production execution
python src/workflows/run_workflow.py --json data/workflows/completeflexelectrodep_workflow-FILLED.json
```

## Creating a Simple Workflow

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

## Documentation

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Overview and quick start |
| [docs/SETUP.md](docs/SETUP.md) | Installation and configuration |
| [docs/USAGE.md](docs/USAGE.md) | Workflow creation and execution |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and layers |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Development guidelines |

## Directory Structure

```
AC_OTFlex_Workflow/
├── src/                 # Source code
│   ├── adapters/       # Device adapters
│   ├── core/           # Runtime modules
│   └── workflows/      # Workflow orchestration
├── tests/              # Test suite
├── config/             # Configuration
├── data/               # Workflows and definitions
├── docs/               # Documentation
├── scripts/            # Utility scripts
├── README.md           # Main documentation
└── requirements.txt    # Python dependencies
```

## Common Commands

```bash
# Run tests
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

## Getting Help

1. Read [docs/SETUP.md](docs/SETUP.md) for installation issues
2. Read [docs/USAGE.md](docs/USAGE.md) for workflow questions
3. Run tests with `--dry-run` for debugging
4. Check [REORGANIZATION_SUMMARY.md](REORGANIZATION_SUMMARY.md) for file locations

## Key Features

✅ **Organized Structure** - Files grouped logically  
✅ **Configuration Management** - Centralized settings  
✅ **Comprehensive Tests** - Test without hardware (dry-run mode)  
✅ **Full Documentation** - Setup, usage, architecture, contributing  
✅ **Clean Git** - Proper .gitignore included  
✅ **Python Packages** - Proper module structure with __init__.py  
✅ **Modular Design** - Easy to extend with new devices/adapters  
✅ **Type Hints** - Better IDE support and code documentation  

---

For detailed information, see [README.md](README.md)
