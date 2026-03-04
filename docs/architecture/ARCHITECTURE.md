# System Architecture

## Overview

The AC_OTFlex_Workflow system is designed with a layered, modular architecture to support complex laboratory automation tasks. The design separates concerns between workflow logic, device abstraction, and hardware communication.

## Architectural Layers

### Layer 1: Workflow Definition
**Files:** `data/workflows/*.json`

Workflows are defined in JSON format with nodes (tasks) and edges (dependencies). This layer is device-agnostic and focuses on the logical flow of experiments.

**Characteristics:**
- Declarative format for experiment procedures
- Supports conditional execution
- Parallel and sequential task definitions
- Device-independent task types

### Layer 2: Workflow Orchestration
**Files:** `src/workflows/run_workflow.py`

Parses workflow definitions and manages execution flow using dependency graph algorithms.

**Responsibilities:**
- Parse and validate workflow JSON
- Build execution graph from nodes/edges
- Implement topological sorting (Kahn's algorithm)
- Manage parallel execution with locks
- Handle error recovery and retries
- Track execution state and logs

**Key Algorithms:**
- **Topological Sort:** Ensures nodes execute in dependency order
- **Resource Locking:** Prevents concurrent access to shared resources
- **Retry Logic:** Handles transient failures with exponential backoff

### Layer 3: Device Adapters
**Files:** `src/adapters/*.py`

Normalize device-specific parameters and provide a unified interface.

**Components:**
- **OTFlex Adapter** (`otflex_adapter.py`)
  - Normalizes Opentrons Flex parameters
  - Maps deck slot labels
  - Loads appropriate runtime module
  
- **ARM Adapter** (`arm_adapter.py`)
  - Normalizes xArm motion parameters
  - Converts pose formats
  - Handles gripper control abstraction

**Key Features:**
- Parameter validation
- Unit conversion (e.g., microliters to milliliters)
- Device-specific format conversion
- Dry-run vs. production mode switching

### Layer 4: Device Runtimes
**Files:** `src/core/otflex_runtime.py`, `src/core/arm_runtime.py`

Implement device-specific operations using low-level clients.

**OTFlex Runtime:**
- Manages Opentrons HTTP API client
- Manages Arduino serial communication
- Implements high-level operations (transfer, gripper, furnace, etc.)
- Tracks labware locations and tip usage
- Handles device-specific state

**ARM Runtime:**
- Manages xArm API connection
- Implements motion control
- Handles gripper operations
- Manages robot state and error recovery

### Layer 5: Hardware Clients
**Files:** `src/core/opentrons.py`, `src/core/myxArm_Utils.py`

Low-level communication with hardware devices.

**Opentrons Client:**
- HTTP REST API communication
- Command building and serialization
- Response parsing and error handling

**xArm Utilities:**
- xArm SDK wrapper
- Pre-programmed motion sequences
- State management
- Error handling

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Workflow Definition (JSON)                                   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. WorkflowRunner (Parsing & Orchestration)                    │
│    - Parse JSON                                                 │
│    - Build execution graph                                      │
│    - Manage device connections                                 │
│    - Coordinate execution                                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────────┐  ┌───────────────────────┐
│ 3a. OTFlex Adapter   │  │ 3b. ARM Adapter       │
│    (normalize        │  │    (normalize         │
│     parameters)      │  │     parameters)       │
└──────────┬───────────┘  └───────────┬───────────┘
           │                          │
           ▼                          ▼
┌──────────────────────┐  ┌───────────────────────┐
│ 4a. OTFlex Runtime   │  │ 4b. ARM Runtime       │
│    (device ops)      │  │    (device ops)       │
└──────────┬───────────┘  └───────────┬───────────┘
           │                          │
    ┌──────┴────────┐                │
    ▼               ▼                ▼
┌─────────┐  ┌──────────┐  ┌──────────────┐
│Opentrons│  │ Arduino  │  │ xArm SDK     │
│ Client  │  │  Serial  │  │              │
└─────────┘  └──────────┘  └──────────────┘
    │            │              │
    └────────────┴──────────────┘
                 │
                 ▼
    ┌───────────────────────────┐
    │ Hardware Devices          │
    │ - Opentrons Flex Robot    │
    │ - xArm Robot              │
    │ - Arduino Furnace Control │
    └───────────────────────────┘
```

## Component Interaction

### Example: Simple Liquid Transfer

1. **Workflow Definition:**
   ```json
   {
     "id": "transfer_1",
     "type": "otflexTransfer",
     "params": {
       "from": {"labware": "source", "well": "A1"},
       "to": {"labware": "dest", "well": "B1"},
       "volume_uL": 100
     }
   }
   ```

2. **WorkflowRunner:**
   - Parses node
   - Route to OTFlex adapter (identified by node type)
   - Call: `otflex_adapter.transfer(params)`

3. **OTFlex Adapter:**
   - Normalize parameters
   - Validate hardware compatibility
   - Call: `otflex_runtime.otflex_transfer(normalized_params)`

4. **OTFlex Runtime:**
   - Resolve labware names to IDs
   - Calculate tip location
   - Build command sequence:
     1. `moveToWell(tiprack)`
     2. `pickUpTip()`
     3. `moveToWell(source, A1)`
     4. `aspirate(100uL)`
     5. `moveToWell(dest, B1)`
     6. `dispense(100uL)`
     7. `moveToWell(trash)`
     8. `dropTip()`

5. **Opentrons Client:**
   - For each step, build HTTP command
   - POST to: `http://169.254.179.32:31950/runs/{runID}/commands`
   - Wait for completion
   - Check response status

6. **Opentrons Robot:**
   - Execute physical motion
   - Perform liquid handling
   - Return completion status

## Configuration Management

Configuration is centralized through `src/config_manager.py`:

```python
from src.config_manager import get_config

config = get_config()

# Access configuration
otflex_ip = config.get("opentrons.controller_ip")
arm_ip = config.get("arm.controller_ip")
arduino_port = config.get("arduino.fallback_port")

# Get entire sections
opentrons_config = config.get_section("opentrons")
arm_config = config.get_section("arm")
```

**Configuration Files:**
- `config/default_config.json` - Default values
- `config/example_config.json` - User template
- `config/user_config.json` - User customization (gitignored)

## Execution Model

### Topological Sorting (Kahn's Algorithm)

The workflow executor uses topological sorting to determine execution order:

1. Build dependency graph from workflow edges
2. Identify nodes with no dependencies
3. Execute nodes with no dependencies (may be parallel)
4. Remove executed nodes and their edges
5. Repeat until all nodes complete

**Advantages:**
- Respects all dependencies
- Allows maximum parallelization
- Easy to identify bottlenecks

### Resource Locking

Prevents concurrent access to shared resources:

```python
async def execute_task(task_id, resources):
    async with resource_locks.acquire_many(resources):
        # Execute task
        pass
```

**Locked Resources:**
- Deck slots
- Pipettes
- Gripper
- Arduino connections

## Error Handling Strategy

### Hierarchical Error Recovery

1. **Hardware Errors** (otflex_runtime, arm_runtime)
   - Retry with exponential backoff
   - Log error details
   - Escalate to workflow executor

2. **Workflow Errors** (run_workflow.py)
   - Attempt recovery if possible
   - Rollback partial states
   - Terminate workflow if unrecoverable

3. **Configuration Errors** (adapters)
   - Validate at initialization
   - Fail fast with clear error messages

### Retry Logic

```python
async def with_retry(coro_func, *, retries=2, timeout=300):
    for attempt in range(retries + 1):
        try:
            return await asyncio.wait_for(coro_func(), timeout=timeout)
        except Exception as e:
            if attempt < retries:
                await asyncio.sleep(0.5 * 2**attempt)  # Exponential backoff
            else:
                raise
```

## Testing Architecture

Tests are organized by component:

- **`test_opentrons.py`** - Robot connectivity and operations
- **`test_arm.py`** - ARM availability and motion
- **`test_furnace.py`** - Arduino furnace control
- **`test_workflows.py`** - Workflow parsing and validation
- **`run_all_tests.py`** - Master test runner

All tests support dry-run mode for testing without hardware.

## Performance Considerations

### Parallelization
- Nodes with no dependencies execute in parallel
- Resource locks prevent conflicts
- Async/await for I/O operations

### Optimization Tips
- Batch similar operations together
- Minimize robot movements
- Pre-load labware when possible
- Use parallel paths in workflow graph

## Future Improvements

1. **Advanced Scheduling:** Task scheduling algorithm for optimal execution
2. **Dynamic Workflow:** Conditional branching based on sensor data
3. **Real-Time Monitoring:** Live dashboards for experiment progress
4. **Machine Learning:** Intelligent parameter tuning
5. **Remote Execution:** Execute workflows on networked systems
