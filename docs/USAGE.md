# Usage Guide

## Running Tests

### Component Testing

Test individual components before running workflows:

```bash
# Test Opentrons Flex
python tests/test_opentrons.py --test connection --ip 169.254.179.32

# Test xArm ARM
python tests/test_arm.py --test availability --dry-run

# Test Arduino Furnace
python tests/test_furnace.py --test calibration

# Test Workflow Parsing
python tests/test_workflows.py --test json-validation --workflow data/workflows/simple_test_workflow.json

# Run All Tests
python tests/run_all_tests.py --dry-run
```

## Creating Workflows

### Workflow JSON Structure

```json
{
  "workflow": {
    "nodes": [
      {
        "id": "unique_node_id",
        "type": "nodetype",
        "params": {
          // node-specific parameters
        }
      }
    ],
    "edges": [
      {
        "source": "node_id_1",
        "target": "node_id_2",
        "metadata": {
          "parallel": false,
          "timeout_seconds": 300
        }
      }
    ]
  },
  "devices": {
    "otflex": { /* ... */ },
    "arm": { /* ... */ }
  }
}
```

### Node Types

#### Opentrons Flex Operations

**otflexTransfer - Liquid Transfer**
```json
{
  "id": "transfer_1",
  "type": "otflexTransfer",
  "params": {
    "from": {
      "labware": "source_plate",
      "well": "A1",
      "offsetX": 0,
      "offsetY": 0,
      "offsetZ": 2
    },
    "to": {
      "labware": "dest_plate",
      "well": "B1",
      "offsetZ": -2
    },
    "volume_uL": 100,
    "move_speed": 150,
    "pipette": "flex_1channel_50",
    "tiprack": "tiprack_200ul"
  }
}
```

**otflexGripper - Labware Movement**
```json
{
  "id": "pick_plate",
  "type": "otflexGripper",
  "params": {
    "action": "pick",  // or "place"
    "labware": "source_plate",
    "from_slot": "A1",
    "to_slot": "D3",
    "gripWidth": 50,
    "grip_force": 1.0
  }
}
```

**otflexFurnace - Furnace Control**
```json
{
  "id": "heat_sample",
  "type": "otflexFurnace",
  "params": {
    "cartridge_id": 0,
    "action": "heat",  // or "cool", "pulse", "stop"
    "setpoint_celsius": 100,
    "duration_seconds": 600,
    "ramp_rate": 5  // degrees per minute
  }
}
```

**otflexPump - Pump Control**
```json
{
  "id": "pump_in",
  "type": "otflexPump",
  "params": {
    "pump_id": 0,
    "action": "pump",  // or "aspirate", "dispense", "stop"
    "volume_mL": 5.0,
    "duration_seconds": 30
  }
}
```

**otflexElectrode - Electrode Switching**
```json
{
  "id": "switch_electrode",
  "type": "otflexElectrode",
  "params": {
    "target_channel": 1,
    "electrode_type": "working"
  }
}
```

**otflexReactor - Reactor Control**
```json
{
  "id": "mix_reactor",
  "type": "otflexReactor",
  "params": {
    "action": "mix",  // or "heat", "stir", "vent", "seal"
    "duration_seconds": 60,
    "speed": 500,  // RPM
    "temperature": 50
  }
}
```

**otflexWash - Well Washing**
```json
{
  "id": "wash_well",
  "type": "otflexWash",
  "params": {
    "labware": "reaction_plate",
    "wells": ["A1", "A2", "A3"],
    "num_rinses": 3,
    "wash_volume_uL": 200
  }
}
```

#### xArm ARM Operations

**myxArmPosition - Move ARM to Position**
```json
{
  "id": "move_arm_1",
  "type": "myxArmPosition",
  "params": {
    "pose": [300, 0, 200, 180, 0, 0],  // [x, y, z, rx, ry, rz]
    "speed": 100,
    "wait": true
  }
}
```

**myxArmGripper - Gripper Control**
```json
{
  "id": "gripper_close",
  "type": "myxArmGripper",
  "params": {
    "action": "close",  // or "open"
    "width": 50,  // gripper width
    "speed": 500   // gripper speed
  }
}
```

**myxArmRunSequence - Pre-programmed Sequences**
```json
{
  "id": "place_to_reactor",
  "type": "myxArmRunSequence",
  "params": {
    "sequence": "placePlateToReactor"  // or "reactorToFurnace", "furnaceToReactor"
  }
}
```

### Example Workflows

#### Simple Liquid Transfer

```json
{
  "workflow": {
    "nodes": [
      {
        "id": "transfer",
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

#### Sequential Operations

```json
{
  "workflow": {
    "nodes": [
      {
        "id": "heat",
        "type": "otflexFurnace",
        "params": {
          "cartridge_id": 0,
          "action": "heat",
          "setpoint_celsius": 100,
          "duration_seconds": 300
        }
      },
      {
        "id": "cool",
        "type": "otflexFurnace",
        "params": {
          "cartridge_id": 0,
          "action": "cool",
          "duration_seconds": 600
        }
      }
    ],
    "edges": [
      {
        "source": "heat",
        "target": "cool",
        "metadata": {"parallel": false}
      }
    ]
  }
}
```

#### Parallel Operations

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
          "volume_uL": 50
        }
      },
      {
        "id": "transfer_2",
        "type": "otflexTransfer",
        "params": {
          "from": {"labware": "source", "well": "A2"},
          "to": {"labware": "dest", "well": "B2"},
          "volume_uL": 50
        }
      }
    ],
    "edges": [
      {
        "source": "transfer_1",
        "target": "transfer_2",
        "metadata": {"parallel": true}
      }
    ]
  }
}
```

## Running Workflows

### Dry-Run Mode (Recommended First Step)

```bash
python src/workflows/run_workflow.py \
  --json data/workflows/simple_test_workflow.json \
  --dry-run
```

Expected output:
```
[Workflow] Loading workflow from...
[Workflow] Initialized OTFlex adapter
[Workflow] Initialized ARM adapter
[OTFlex] Connecting to robot (dry-run mode)
[Workflow] Node transfer: type=otflexTransfer, params={...}
[OTFlex] Transfer: source.A1 -> dest.B1 (100uL)
[Workflow] Workflow completed successfully
```

### Production Mode

```bash
python src/workflows/run_workflow.py \
  --json data/workflows/completeflexelectrodep_workflow-FILLED.json
```

### With Custom Configuration

```bash
python src/workflows/run_workflow.py \
  --json data/workflows/simple_test_workflow.json \
  --config config/user_config.json
```

## Workflow List

### Available Test Workflows

```bash
python tests/test_workflows.py --test list
```

**Available Workflows:**
- `simple_test_workflow.json` - Basic liquid transfer
- `reactor.json` - Reactor operations
- `parallelTest.json` - Parallel execution test
- `furnaceTest.json` - Furnace control test
- `completeTest.json` - Full integration test
- `completeflexelectrodep_workflow-FILLED.json` - Complete electrodeposition

## Debugging

### Enable Verbose Logging

Edit `config/user_config.json`:
```json
{
  "system": {
    "verbose_logging": true
  }
}
```

### View Logs

```bash
# Linux/macOS
tail -f logs/workflow.log

# Windows
Get-Content logs\workflow.log -Wait
```

### Inspect Workflow

```bash
python tests/test_workflows.py --test json-validation --workflow data/workflows/simple_test_workflow.json
python tests/test_workflows.py --test graph-validation --workflow data/workflows/simple_test_workflow.json
```

## Input Parameters

### CSV Input Files

**params.csv** - Sample parameters
```
Well ID,solution A position,solution A volume,...
1,A1,50,B3,25,...
2,A2,40,B1,10,...
```

**sources.csv** - Chemical sources
```
compound_name,source_well,concentration_mM
FeCl3,A1,100
CrCl3,A2,100
```

### JSON Configuration

**experimentParams.json** - Experiment definition
```json
{
  "experimentName": "Selective test",
  "sourcePlates": {
    "FeCl3": {
      "sourcePlate": "vial_rack",
      "sourceWell": ["A1", "B1"],
      "amount_mL": 15,
      "concentration_mM": 100
    }
  }
}
```

## Device Configuration

### Device Section in Workflow JSON

```json
{
  "devices": {
    "otflex": {
      "module": "OTFLEX_WORKFLOW_Iliya_dryrun.py",
      "controller_ip": "169.254.179.32",
      "arduino": {
        "port": "COM4",
        "baudrate": 115200
      },
      "deck": {
        "slots": {
          "A1": {
            "name": "source_plate",
            "labware": "opentrons_flex_96_tiprack_1000ul"
          }
        }
      }
    },
    "arm": {
      "module": "myxArm_Utils_dryrun.py",
      "ip": "192.168.1.113",
      "port": 5001
    }
  }
}
```

## Tips & Best Practices

### 1. Start with Dry-Run
Always test with `--dry-run` first before running on real hardware.

### 2. Small Steps
Create simple workflows first, then build complexity.

### 3. Use IDs
Clear node IDs make workflows easier to debug:
```json
{
  "id": "transfer_source_A1_to_dest_B1",
  "type": "otflexTransfer"
}
```

### 4. Add Comments
Document complex workflows:
```json
{
  "id": "heating_step",
  "type": "otflexFurnace",
  "description": "Heat sample to 100C for 10 minutes",
  "params": {
    "setpoint_celsius": 100,
    "duration_seconds": 600
  }
}
```

### 5. Test Edge Cases
- Empty wells
- Missing labware
- Network disconnections

### 6. Version Control
Track workflow changes:
```bash
git add data/workflows/my_workflow.json
git commit -m "Add new electrodeposition workflow"
```

## Troubleshooting

### Workflow Won't Start

1. **Check JSON syntax:**
   ```bash
   python tests/test_workflows.py --test json-validation --workflow your_file.json
   ```

2. **Check dependencies:**
   ```bash
   python tests/test_workflows.py --test graph-validation --workflow your_file.json
   ```

3. **Check hardware:**
   ```bash
   python tests/run_all_tests.py --dry-run
   ```

### Workflow Hangs

1. **Check timeouts** in edges
2. **Check resource locks** (device conflicts)
3. **Verify hardware** is responsive

### Device Not Responding

1. Check device IP/port
2. Check network connectivity
3. Restart device
4. Check logs for errors

## Advanced Usage

### Custom Adapters

To create a custom device adapter:

1. Copy existing adapter structure
2. Implement device-specific methods
3. Register in workflow runner
4. Test thoroughly

### Workflow Generation

Generate workflows programmatically:

```python
import json

workflow = {
  "workflow": {
    "nodes": [],
    "edges": []
  }
}

# Add nodes programmatically
for i in range(10):
  workflow["workflow"]["nodes"].append({
    "id": f"transfer_{i}",
    "type": "otflexTransfer",
    "params": {
      "from": {"labware": "source", "well": f"A{i+1}"},
      "to": {"labware": "dest", "well": f"B{i+1}"},
      "volume_uL": 100
    }
  })

with open("generated_workflow.json", "w") as f:
  json.dump(workflow, f, indent=2)
```

## Performance Tuning

### Parallelization
- Mark independent operations with `"parallel": true`
- Reduces total workflow time significantly

### Batch Operations
- Group similar operations together
- Reduces device overhead

### Network Optimization
- Use local configuration files
- Minimize device communication
