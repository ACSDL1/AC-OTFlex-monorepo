# AC-OTFlex Monorepo

Acceleration Consortium SDL1 lab group project: A unified self-driving lab automation system combining hardware control, MQTT communication, and notebook-based workflow orchestration for electrochemical experiments. This monorepo gathers all components into a single codebase for easier development and maintenance.

**Language:** Primarily Python 3.8+ and C++ for IoT firmware

## Project Overview

The system integrates:
- **Core Control**: Python-based system with device abstractions and MQTT communication
- **Modular Devices**: IoT device libraries (pump, heater, furnace, reactor, etc.)
- **Workflows**: Jupyter notebook-based experiment scripts for reproducible automation
- **Configuration**: MQTT broker and device parameter management
- **Data**: Labware definitions and experiment outputs

## Directory Structure

```
AC-OTFlex-monorepo/
├── config/                        # Runtime configs and MQTT broker settings
│   ├── mqtt/                     # Mosquitto config, ACL, and broker README
│   ├── default_config.json       # Baseline runtime configuration
│   ├── user.json                 # User-specific settings
│   └── README.md
├── data/                          # Experiment inputs and labware assets
│   ├── device_configs/           # Device parameter definitions
│   ├── labware_definitions/      # Opentrons-compatible labware JSON
│   └── out/                      # Generated outputs/artifacts
├── devices/                       # Hardware module repositories by device type
│   ├── furnace/
│   ├── heater/
│   ├── pump/
│   ├── reactor/
│   ├── syringe-pump/
│   └── README.md
├── docs/                          # Project documentation (architecture/setup/usage)
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   ├── USAGE.md
│   ├── CONTRIBUTING.md
│   ├── workflows/
│   └── README.md
├── notebooks/                     # Primary notebook-based workflow entry points
│   ├── workflows/                # Workflow notebooks used by users
│   ├── MQTT_Demo.ipynb
│   └── README.md
├── scripts/                       # Utility and hardware helper scripts
│   ├── archived_potentiostat/
│   ├── home_opentrons.py
│   └── README.md
├── src/                           # Core Python package for orchestration and adapters
│   ├── adapters/                 # Device and MQTT adapter implementations
│   ├── core/                     # Runtime control logic
│   ├── workflows/                # Workflow engine modules
│   ├── utils/                    # Shared utilities
│   └── config_manager.py
├── requirements.txt               # Top-level Python dependencies
└── README.md                      # This file
```

## Getting Started

Start here: **Jump to [docs/README.md](docs/README.md) :**

1. **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — Understand the system design and all components we're using
2. **[SETUP.md](docs/SETUP.md)** — Get this monorepo running on your machine (prerequisites and configuration)
3. **[USAGE.md](docs/USAGE.md)** — Learn how to run notebooks, change experiment parameters, and work with the system

> **Note:** Since this is a large codebase with many working parts, we recommend reading all READMEs in order to build a complete understanding. Start with the architecture to see the big picture, then setup for environment preparation, and finally usage for day-to-day work.

Component-specific documentation is available in individual README files (e.g., `devices/*/README.md`, `config/mqtt/README.md`).

## Getting Help

1. Check [docs/SETUP.md](docs/SETUP.md) for installation issues
2. Consult [docs/USAGE.md](docs/USAGE.md) for workflow and notebook questions
3. Review component READMEs in `devices/` and `config/` directories for device-specific help
4. See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines

## License

_To be added_

## Version History

### January 2026
- **v0.0.0** - Clone Iliya's code for OTFlex project
- **v0.1.0** - Move Alan's MQTT IoT server code into this monorepo

### February 2026
- **v0.1.0** - Revise deprecated JSON workflow files and setup to run Ilya's JSON-based workflows in this monorepo

### March 2026
- **v1.0.0** - Redesign workflow system to use Jupyter notebooks instead of JSON files, and implement the Python MQTT API for device control 
