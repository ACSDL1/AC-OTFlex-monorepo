# OTFlex Workflow - Automated Laboratory Workflow System

This repository contains a workflow execution system for coordinating automated laboratory equipment, specifically the Opentrons Flex liquid handling robot and UFactory xArm robotic arm. The system executes workflows defined in JSON format, managing device connections, parameter normalization, and parallel/sequential task execution.

## Overview

The system follows a layered architecture where workflow definitions are parsed and executed through adapters that normalize parameters and route commands to device-specific runtime modules. This design allows for clean separation between workflow logic, device abstraction, and hardware control.

## Data Flow Architecture

```
workflow.json
    ↓
run_workflow.py (Workflow Parser & Executor)
    ↓
adapters/ (Parameter Normalization & Device Abstraction)
    ├── otflex_adapter.py
    └── arm_adapter.py
    ↓
runtime/ (Device-Specific Runtime Wrappers)
    ├── otflex_runtime.py
    └── arm_runtime.py
    ↓
low-level clients/ (Hardware Communication)
    ├── opentrons.py
    └── myxArm_Utils.py
```

## Main Files

### 1. `workflow.json`
**Purpose**: Defines the complete workflow structure including nodes, edges, and device configurations.

**Structure**:
- **nodes**: Individual workflow steps (e.g., liquid transfers, gripper operations, furnace control)
- **edges**: Defines dependencies and execution order between nodes
- **devices**: Configuration for each device (OT-Flex deck layout, xArm IP, Arduino ports, etc.)
- **executionMetadata**: Optional metadata for execution hints

**Key Features**:
- Supports parallel and sequential execution modes via edge properties
- Contains device-specific configurations (deck layouts, IP addresses, serial ports)
- Allows referencing external device configuration files

**Example**:
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
    "edges": [{"source": "transfer_1", "target": "transfer_2"}]
  },
  "devices": {
    "otflex": {
      "controller_ip": "169.254.179.32",
      "deck": {"slots": {...}}
    }
  }
}
```

---

### 2. `run_workflow.py`
**Purpose**: Main entry point that parses workflow JSON files and orchestrates execution.

**Responsibilities**:
- Parses workflow JSON and builds execution graph
- Manages device connections (connects/disconnects adapters)
- Implements topological sorting for node execution
- Handles parallel vs sequential execution based on edge properties
- Manages resource locks to prevent conflicts
- Implements retry logic and timeout handling

**Key Functions**:
- `WorkflowRunner.__init__()`: Loads workflow JSON and initializes device adapters
- `WorkflowRunner.run()`: Main execution loop using Kahn's algorithm for topological sorting
- `WorkflowRunner._run_node()`: Executes individual workflow nodes
- `WorkflowRunner._run_otflex()` / `_run_arm()`: Routes commands to appropriate device adapters

**Execution Flow**:
1. Load workflow JSON
2. Initialize device adapters (OTFlex, MyxArm)
3. Connect to all devices
4. Build dependency graph from edges
5. Execute nodes in topological order (respecting parallel/sequential constraints)
6. Disconnect devices on completion

---

### 3. `adapters/otflex_adapter.py`
**Purpose**: Adapter layer for Opentrons Flex device that normalizes parameters and provides a unified interface.

**Responsibilities**:
- Normalizes parameter formats from workflow JSON to runtime-compatible format
- Maps deck slot labels (handles numeric slots 1-9 to Flex labels A1-C3)
- Dynamically loads the appropriate runtime module (can use dry-run or real implementations)
- Provides async wrapper functions for all OT-Flex operations

**Key Functions**:
- `_normalize_transfer()`: Converts nested `from`/`to` objects to flat `from_labware`/`to_labware` format
- `_normalize_deck()`: Maps numeric slot keys to Flex slot labels (A1, B1, C1, etc.)
- `connect()`: Initializes OT-Flex runtime with device configuration
- `transfer()`, `gripper()`, `furnace()`, `pump()`, etc.: Async wrappers for device operations

**Parameter Normalization Example**:
```python
# Input (from workflow.json):
{
  "from": {"labware": "source", "well": "A1", "offsetX": 0, "offsetY": 0, "offsetZ": 2},
  "to": {"labware": "dest", "well": "B1"},
  "volume_uL": 100
}

# Output (to runtime):
{
  "from_labware": "source", "from_well": "A1",
  "from_dX": 0.0, "from_dY": 0.0, "from_dZ": 2.0,
  "to_labware": "dest", "to_well": "B1",
  "volume_uL": 100
}
```

---

### 4. `adapters/arm_adapter.py`
**Purpose**: Adapter layer for UFactory xArm robotic arm.

**Responsibilities**:
- Normalizes pose parameters (converts list format to dict format)
- Dynamically loads arm runtime module (supports dry-run mode)
- Provides async wrappers for arm operations

**Key Functions**:
- `connect()`: Initializes xArm connection
- `move()`: Normalizes pose format and calls runtime
- `gripper()`: Controls gripper open/close
- `run_sequence()`: Executes pre-programmed sequences (e.g., "placePlateToReactor", "reactorToFurnace")

**Pose Normalization**:
```python
# Input: [x, y, z, rx, ry, rz]
# Output: {"x": x, "y": y, "z": z, "rx": rx, "ry": ry, "rz": rz}
```

---

### 5. `otflex_runtime.py`
**Purpose**: Runtime wrapper that implements actual OT-Flex device operations.

**Responsibilities**:
- Manages Opentrons Flex HTTP API client (`opentronsClient`)
- Manages Arduino serial communication for peripherals (furnace, pumps, reactor)
- Loads labware onto deck based on configuration
- Tracks tip usage with `TipTracker`
- Implements high-level operations: transfer, gripper, furnace, pump, electrode, reactor, wash

**Key Classes**:
- `_ArduinoClient`: Handles serial communication with Arduino for peripheral control
- `_OTFlexRuntime`: Main runtime class managing device state and operations

**Key Functions**:
- `otflex_connect()`: Initializes Opentrons client, loads labware, connects Arduino
- `otflex_transfer()`: Performs liquid transfers with automatic tip pickup/drop
- `otflex_gripper()`: Controls gripper for labware movement
- `otflex_furnace()`, `otflex_pump()`, `otflex_reactor()`: Control Arduino peripherals
- `otflex_toolTransfer()`, `otflex_potentExperiment()`, `otflex_flushWell()`: Specialized electrode operations

**Device Management**:
- Maintains labware ID mapping (`lw_ids`) for name-to-ID resolution
- Tracks pipette configurations
- Manages gripper slot poses for pick-and-place operations

---

### 6. `arm_runtime.py`
**Purpose**: Runtime wrapper for UFactory xArm robot.

**Responsibilities**:
- Manages xArm API connection
- Implements low-level robot control (position, gripper)
- Handles robot state management (error clearing, mode setting)

**Key Functions**:
- `arm_connect()`: Connects to xArm, clears errors, enables motion
- `arm_move()`: Moves robot to specified pose (x, y, z, rx, ry, rz)
- `arm_gripper()`: Controls gripper open/close with width and speed
- `arm_disconnect()`: Safely disconnects from robot

**Note**: This is a minimal runtime. For complex sequences, see `myxArm_Utils.py`.

---

### 7. `opentrons.py`
**Purpose**: Low-level HTTP client for Opentrons Flex robot API.

**Responsibilities**:
- Communicates with Opentrons robot via HTTP REST API (port 31950)
- Creates and manages runs
- Sends commands (loadLabware, loadPipette, aspirate, dispense, moveToWell, etc.)
- Handles command responses and error checking

**Key Class**: `opentronsClient`

**Key Methods**:
- `__init__()`: Creates a new run on the robot
- `loadLabware()` / `loadCustomLabware()`: Loads labware onto deck
- `loadPipette()`: Loads pipette onto mount
- `aspirate()` / `dispense()`: Liquid handling operations
- `pickUpTip()` / `dropTip()`: Tip management
- `moveToWell()`: Moves pipette to specific well
- `moveLabware()`: Uses gripper to move labware between locations
- `openGripper()` / `closeGripper()`: Gripper control

**Communication**:
- All commands sent as JSON POST requests to `http://{robotIP}:31950/runs/{runID}/commands`
- Commands include `waitUntilComplete` parameter for synchronous execution
- Responses checked for status codes and error conditions

---

### 8. `myxArm_Utils.py`
**Purpose**: Low-level utilities and pre-programmed sequences for xArm robot.

**Responsibilities**:
- Provides `RobotMain` class for robot state management
- Implements complete pre-programmed sequences:
  - `run_place_plate_to_reactor()`: Places plate from storage to reactor
  - `run_reactor_to_furnace()`: Moves plate from reactor to furnace
  - `run_furnace_to_reactor()`: Moves plate from furnace back to reactor
  - `run()`: Complete workflow sequence
- Provides adapter entrypoints: `arm_connect()`, `arm_disconnect()`, `arm_move()`, `arm_gripper()`, `arm_run_sequence()`

**Key Features**:
- Error handling and state checking
- Speed and acceleration control
- Gripper position control
- Supports both position-based and joint-angle-based movement

**Sequence Execution**:
- Sequences consist of multiple `set_position()` and `set_servo_angle()` calls
- Includes gripper operations at appropriate points
- Handles timing and wait conditions

---

## Complete Data Flow Example

### Example: Liquid Transfer Workflow

1. **User creates `workflow.json`**:
   ```json
   {
     "workflow": {
       "nodes": [{
         "id": "transfer",
         "type": "otflexTransfer",
         "params": {
           "from": {"labware": "source", "well": "A1"},
           "to": {"labware": "dest", "well": "B1"},
           "volume_uL": 100
         }
       }]
     }
   }
   ```

2. **`run_workflow.py` parses JSON**:
   - Loads workflow structure
   - Initializes `OTFlex` adapter with device config
   - Builds execution graph

3. **`otflex_adapter.py` normalizes parameters**:
   - Converts `from.labware` → `from_labware`
   - Converts `from.well` → `from_well`
   - Normalizes offset parameters

4. **`otflex_runtime.py` executes operation**:
   - Calls `opentronsClient.loadLabware()` to ensure labware loaded
   - Uses `TipTracker` to find next available tip
   - Calls `opentronsClient.pickUpTip()`
   - Calls `opentronsClient.aspirate()` at source well
   - Calls `opentronsClient.dispense()` at destination well
   - Calls `opentronsClient.dropTip()`

5. **`opentrons.py` sends HTTP commands**:
   - POST to `/runs/{runID}/commands` with JSON command
   - Waits for completion
   - Checks response status

6. **Opentrons robot executes**:
   - Robot physically moves pipette
   - Performs liquid handling operation
   - Returns status

---

## Device Configuration

### OT-Flex Configuration
Located in `workflow.json` under `devices.otflex`:
```json
{
  "otflex": {
    "module": "otflex_runtime.py",
    "controller_ip": "169.254.179.32",
    "arduino": {
      "port": "COM4",
      "baudrate": 115200
    },
    "deck": {
      "slots": {
        "A1": {
          "name": "source_plate",
          "labware": "opentrons_flex_96_tiprack_1000ul",
          "slot_label": "A1"
        }
      }
    }
  }
}
```

### xArm Configuration
Located in `workflow.json` under `devices.arm`:
```json
{
  "arm": {
    "module": "arm_runtime.py",
    "ip": "192.168.1.233"
  }
}
```

---

## Usage

### Running a Workflow
```bash
python run_workflow.py --json path/to/workflow.json
```

### Workflow JSON Structure
- **nodes**: Array of workflow steps
- **edges**: Array of dependencies (source → target)
- **devices**: Device configurations
- **executionMetadata**: Optional execution hints

### Supported Node Types

**OT-Flex Operations**:
- `otflexTransfer`: Liquid transfer
- `otflexGripper`: Labware movement
- `otflexFurnace`: Furnace control
- `otflexPump`: Pump control
- `otflexElectrode`: Electrode switching
- `otflexReactor`: Reactor control
- `otflexWash`: Washing operations
- `otflexToolTransfer`: Electrode tool transfer
- `otflexPotentExperiment`: Potentiostat experiments
- `otflexFlushWell`: Well flushing operations

**xArm Operations**:
- `myxArmPosition`: Move to position
- `myxArmGripper`: Gripper control
- `myxArmRunSequence`: Pre-programmed sequences

---

## Directory Structure

```
OER_Flex/
├── adapters/              # Device adapter layer
│   ├── otflex_adapter.py  # OT-Flex adapter
│   └── arm_adapter.py     # xArm adapter
├── devices/               # Device configuration files
├── labware/               # Custom labware definitions (JSON)
├── utils/                 # Utility modules (tip tracking, etc.)
├── opentrons.py           # Opentrons HTTP client
├── otflex_runtime.py      # OT-Flex runtime wrapper
├── arm_runtime.py         # xArm runtime wrapper
├── myxArm_Utils.py        # xArm utilities and sequences
├── run_workflow.py        # Main workflow executor
└── workflow.json          # Example workflow definition
```

---

## Key Design Patterns

1. **Adapter Pattern**: Adapters normalize parameters between workflow format and device-specific formats
2. **Runtime Wrapper Pattern**: Runtime modules wrap low-level clients with higher-level operations
3. **Dependency Graph Execution**: Workflow nodes executed in topological order respecting dependencies
4. **Resource Locking**: Prevents concurrent access to shared resources (slots, devices)
5. **Dry-Run Support**: All adapters support simulation mode when hardware unavailable

---

## Dependencies

- **Opentrons**: HTTP API client (requests library)
- **xArm**: xarm Python SDK (`xarm.wrapper.XArmAPI`)
- **Arduino**: Serial communication (pyserial)
- **Python**: 3.7+ with asyncio support

---

## Notes

- The system supports both real hardware execution and dry-run simulation
- Workflow JSON can reference external device configuration files
- Parallel execution is supported via edge properties (`mode: "parallel"`)
- Tip tracking is automatic for liquid transfer operations
- All device operations are wrapped in retry logic with configurable timeouts

