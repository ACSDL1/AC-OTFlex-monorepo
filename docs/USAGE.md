# Usage Guide

## Safety

**IMPORTANT: Read this section before operating any equipment.**

### OTFlex Homing
- The Opentrons Flex must be homed in its resting position before any workflow runs
- Use the homing scripts in the [scripts](#scripts) section to initialize the robot
- Refer to `scripts/home_opentrons.py` for the homing procedure

### xArm Homing
- The xArm robotic arm must be in the upright (home) position before operation
- Ensure the arm is fully retracted and in rest position
- Check the device-specific documentation in [devices/arm](#single-device-debugging)

### E-Stop Buttons
- **Locate all E-stop buttons on both the Opentrons Flex and xArm before operating**
- Familiarize yourself with their locations and operation
- Test E-stop functionality during setup to ensure proper response
- In case of emergency, press the nearest E-stop to immediately halt all motion

## Scripts

All utility and setup scripts are located in the `scripts/` directory. Here are the available scripts:

### Common Scripts

**`home_opentrons.py`** - Home the Opentrons Flex robot
```bash
python scripts/home_opentrons.py --ip 169.254.179.32
```
- Initializes the Flex arm to the home position
- **Must be run before starting any workflow**
- Use this after hardware changes or emergency stops
- IP address can be found on the Opentrons Flex display or use the default `169.254.179.32`

**`eject_tips_opentrons.py`** - Safely eject tips from pipette
```bash
python scripts/eject_tips_opentrons.py --ip 169.254.179.32
```
- Manually eject any tips stuck in the pipette
- Use if a workflow fails mid-transfer
- IP address must match your Opentrons Flex controller IP


### Archived Scripts

Scripts in `scripts/archived_potentiostat/` are experimental potentiostat-related utilities - refer to those files for specialized electrochemistry operations.

## Running Workflows

### About Workflow Notebooks

All workflows are implemented as Jupyter notebooks in the `notebooks/workflows/` directory. Each notebook file represents a complete workflow, and each cell within a notebook represents a single task or function execution.

### Creating and Editing Workflows

1. **Navigate to workflow notebooks:**
   ```
   notebooks/workflows/
   ```

2. **How workflows are organized:**
   - Each `.ipynb` file is an independent workflow
   - Each cell in the notebook is a single task or system function call
   - Cells execute sequentially by default unless designed otherwise

3. **Running workflows:**
   - **Single cell**: Click on a cell and press `Shift+Enter` to run just that step
   - **Multiple cells**: Run cells in sequence to execute portions of the workflow
   - **Full workflow**: Run all cells from top to bottom to execute the entire workflow

4. **Editing workflow parameters:**
   - Open any workflow notebook in Jupyter
   - Each cell contains parameters that can be edited before execution
   - Modify parameters such as volumes, temperatures, positions, and timing as needed
   - Re-run cells after editing to test parameter changes

### Example Workflow Notebooks

- `OTFLEX_WORKFLOW_Gavin.ipynb` - Main Opentrons Flex workflow
- Additional workflow notebooks document specific operations and sequences

## Single Device Debugging

When troubleshooting a specific device or component, navigate to the appropriate device folder:

```
devices/
  furnace/          # Furnace heating control
  heater/           # Heater components  
  potentiostat/     # Electrochemistry measurements
  pump/             # Pump control
  raspi-camera/     # Camera interface
  reactor/          # Reactor operations
  syringe-pump/     # Syringe pump control
  ultrasonic/       # Ultrasonic operations
```

### Device-Level Debugging

Each device folder contains:
- **README.md** - Device-specific setup and operation instructions
- **src/** - Source code for device control
- **firmware/** - Device firmware if applicable
- **electrical/** - Electrical schematics and documentation
- **mechanical/** - Mechanical drawings and CAD files

### To debug a specific device:

1. Navigate to the device folder: `cd devices/[device_name]/`
2. Read the **README.md** for that device
3. Follow device-specific testing and calibration procedures
4. Use device-level scripts or test functions to validate operation
5. Check logs and error messages for troubleshooting

## MQTT Debugging

The system uses MQTT for controlling IoT devices (pumps, furnaces, heaters, reactors, etc.). To test MQTT connections and IoT device control:

1. **Open the MQTT Demo notebook:**
   ```
   notebooks/MQTT_Demo.ipynb
   ```

2. **Use this notebook to:**
   - Test MQTT broker connectivity
   - Send commands to individual IoT devices
   - Verify device responses
   - Monitor real-time device status
   - Troubleshoot connection issues

3. **Common MQTT topics to test:**
   - Pump operations
   - Furnace heating/cooling
   - Reactor control
   - Heater control
   - Ultrasonic operations

This notebook is useful for isolating MQTT-related issues from workflow execution issues.

## Lower Level Function Definitions

### Architecture Overview

The system is organized into adapters and device-level libraries that abstract hardware communication. Here's the basic architecture:

```
src/
├── adapters/              # High-level hardware adapters
│   ├── otflex_adapter.py         # Opentrons Flex interface
│   ├── iot_mqtt.py              # MQTT IoT device control
│   └── pi_cam.py                # Raspberry Pi camera interface
├── core/                  # Core runtime and workflow execution
│   ├── otflex_runtime.py         # OTFlex command runtime
│   └── opentrons.py             # Opentrons client wrapper
└── utils/                 # Utility libraries
    ├── tip_tracker.py           # Pipette tip tracking
    └── ...                      # Other utilities
```

### Adapters and Device Libraries

**adapters/** folder provides the main entry points for device control:

- **`otflex_adapter.py`** - Main Opentrons Flex interface
  - Implements high-level operations: transfer, gripper, furnace, pump, wash, electrode
  - Translates workflow commands into robot actions
  - Handle device errors and safety checks

- **`iot_mqtt.py`** - MQTT-based IoT device control
  - `FurnaceMQTT` - Control heating furnaces
  - `HeatMQTT` - Control heating elements
  - `PumpMQTT` - Control pumps
  - `ReactorMQTT` - Control reactors
  - `UltraMQTT` - Control ultrasonic devices

- **`pi_cam.py`** - Raspberry Pi camera interface
  - Capture images from the camera
  - Store and process images

### Core Runtime

**`src/core/otflex_runtime.py`** is the fundamental runtime that:

1. **Initializes connections:**
   - Connect to Opentrons Flex robot
   - Connect to MQTT broker for IoT devices
   - Load deck configuration and labware definitions

2. **Provides device-neutral operation methods:**
   - `transfer()` - Liquid transfer operations
   - `toolTransfer()` - Electrode positioning 
   - `gripper()` - Labware gripping and placement
   - `furnace()` - Furnace heating/cooling
   - `pump()` - Pump operation
   - `reactor()` - Reactor control
   - `wash()` - Well washing
   - `electrode()` - Electrode switching
   - `echem_measure()` - Electrochemistry measurement

3. **Exports adapter entry points:**
   - Functions like `otflex_connect()`, `otflex_transfer()`, etc.
   - Called by workflow execution engine
   - Abstracted from low-level hardware details

### How Workflows Use These Libraries

1. **Workflow notebook cells** call high-level Python functions
2. **Functions use adapters** from `src/adapters/` 
3. **Adapters call runtime** methods in `src/core/otflex_runtime.py`
4. **Runtime executes** device-specific operations via Opentrons client and MQTT
5. **Results returned** back to workflow for logging/decision-making

This layered architecture allows:
- Easy replacement of individual device implementations
- Reusable operations across different workflows
- Clear separation of concerns
- Simplified testing and debugging

