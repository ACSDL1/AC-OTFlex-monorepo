# Workflows

This directory contains the workflow runner and supporting code for executing SDL1 experiment workflows.

---

## Overview

Workflows are JSON files (stored in `data/workflows/`) that describe a directed graph of experiment steps. The runner (`run_workflow.py`) reads the graph, resolves dependencies between steps, and dispatches each step to the right hardware adapter.

```
data/workflows/my_experiment.json
        │
        ▼
src/workflows/run_workflow.py   ← graph scheduler
        │
        ├── OTFlex adapter      ← Opentrons liquid handler
        ├── MyxArm adapter      ← robotic arm
        ├── MQTT devices        ← pumps / ultrasonic / heater / reactor / furnace
        └── Potentiostat adapter ← electrochemical measurements
```

---

## Running a workflow

```bash
# From the monorepo root
python -m src.workflows.run_workflow --json data/workflows/my_experiment.json

# Disable the robotic arm (e.g. for bench testing)
python -m src.workflows.run_workflow --json data/workflows/my_experiment.json --no-arm
```

---

## Workflow JSON structure

```jsonc
{
  "metadata": { "name": "My Experiment", ... },

  "workflow": {
    "nodes": [ ... ],   // steps
    "edges": [ ... ]    // execution order / parallelism
  },

  "devices": {          // hardware configuration
    "otflex":      { ... },
    "arm":         { ... },
    "potentiostat":{ ... },
    "mqtt":        { ... }   // see MQTT section below
  }
}
```

### Nodes

Every node must have an `"id"` and a `"type"`. The type prefix determines which adapter handles it:

| Type prefix        | Handler          | Description                        |
|--------------------|------------------|------------------------------------|
| `input` / `output` | —                | Graph boundary (no-op)             |
| `otflex*`          | OTFlex adapter   | Liquid transfers, gripper, wash…   |
| `otflexMyxArm*`    | Arm adapter      | Robotic arm sequences              |
| `myxArm*`          | Arm adapter      | Robotic arm sequences              |
| `mqtt*`            | MQTT bus         | Pumps, ultrasonic, heat, reactor…  |
| `sdl1*`            | Potentiostat     | Electrochemical measurements       |

Node params are type-specific. See [MQTT node types](#mqtt-node-types) below.

### Edges

```jsonc
{
  "id": "step1-to-step2",
  "source": "node_a",
  "target": "node_b",
  "mode": "sequential"    // "sequential" (default) or "parallel"
}
```

- **sequential** — `node_b` runs after `node_a` finishes.
- **parallel** — all edges from the same parent marked `"parallel"` launch concurrently with `asyncio.gather()`.

### Per-node options

Any node's `params` block may include:

| Field           | Type    | Default | Description                                     |
|-----------------|---------|---------|-------------------------------------------------|
| `retries`       | int     | `0`     | Number of extra attempts on failure             |
| `timeout`       | float   | `null`  | Per-attempt timeout in seconds                  |
| `resourceLocks` | list    | `[]`    | Named resources that must not run concurrently  |

`resourceLocks` example: `["deck:slot3", "furnace:chamber1"]` — two nodes sharing a lock will never overlap.

---

## Devices configuration

### OTFlex

```jsonc
"otflex": {
  "controller_ip": "169.254.x.x",
  "pipette": "p1000_single_flex"
}
```

You can also point to a shared config file:

```jsonc
"otflex_file": "device_configs/otflex_deck_default.json"
```

### Robotic arm

```jsonc
"arm": {
  "enabled": true,
  "ip": "192.168.1.x"
}
```

Set `"enabled": false` (or use `--no-arm` on the CLI) to skip arm nodes entirely.

### Potentiostat

```jsonc
"potentiostat": {
  "baudrate": 115200,
  "timeout_s": 2.0,
  "device_id": 1
}
```

### MQTT

```jsonc
"mqtt": {
  "broker":   "localhost",
  "port":     1883,
  "username": "pyctl-controller",
  "password": "controller",
  "topics": {
    "pumps":   "pumps/01",
    "ultra":   "ultra/01",
    "heat":    "heat/01",
    "reactor": "reactor/01",
    "furnace": "furnace/01"
  }
}
```

Any key under `"topics"` can be omitted to disable that device. The runner will automatically start a `ControllerBeacon` (ONLINE/OFFLINE heartbeat) using the same broker credentials.

---

## MQTT node types

### `mqttWait`

```jsonc
{
  "type": "mqttWait",
  "params": {
    "duration_s": 5
    // or "duration_ms": 5000
  }
}
```

Adds an explicit workflow pause/sleep without toggling any hardware channel.

### `mqttPump` / `mqttPumpOff`

```jsonc
{
  "type": "mqttPump",
  "params": {
    "channel":     1,       // 1–3
    "duration_ms": 3000     // optional auto-off timer
  }
}
```

```jsonc
{ "type": "mqttPumpOff", "params": { "channel": 1 } }
```

### `mqttUltra` / `mqttUltraOff`

```jsonc
{
  "type": "mqttUltra",
  "params": {
    "channel":     2,
    "duration_ms": 5000
  }
}
```

### `mqttHeat` / `mqttHeatOff`

```jsonc
{
  "type": "mqttHeat",
  "params": {
    "channel":  1,
    "target_c": 62.0,
    "pid":      true,     // enable PID loop on ESP (default: true)
    "wait_s":   120       // optional: block workflow for N seconds
  }
}
```

```jsonc
{ "type": "mqttHeatOff", "params": { "channel": 1 } }
```

`mqttHeatOff` sends `PID:OFF`, sets PWM to 0, and turns the relay off.

### `mqttReactor` / `mqttReactorStop`

```jsonc
{
  "type": "mqttReactor",
  "params": {
    "direction":   "forward",   // "forward" or "reverse"
    "duration_ms": 3000
  }
}
```

```jsonc
{ "type": "mqttReactorStop", "params": {} }
```

### `mqttFurnace` / `mqttFurnaceStop`

```jsonc
{
  "type": "mqttFurnace",
  "params": {
    "action":      "open",   // "open" or "close"
    "duration_ms": 4000
  }
}
```

---

## Example workflow snippet

The following fragment runs a pump and ultrasonic simultaneously (parallel), then runs a heater step after both finish:

```jsonc
"nodes": [
  { "id": "start",   "type": "input",      "params": {} },
  { "id": "pump1",   "type": "mqttPump",   "params": { "channel": 1, "duration_ms": 5000 } },
  { "id": "ultra1",  "type": "mqttUltra",  "params": { "channel": 2, "duration_ms": 5000 } },
  { "id": "heat1",   "type": "mqttHeat",   "params": { "channel": 1, "target_c": 42.0, "wait_s": 60 } },
  { "id": "finish",  "type": "output",     "params": {} }
],
"edges": [
  { "id": "e1", "source": "start",  "target": "pump1",  "mode": "parallel" },
  { "id": "e2", "source": "start",  "target": "ultra1", "mode": "parallel" },
  { "id": "e3", "source": "pump1",  "target": "heat1"  },
  { "id": "e4", "source": "ultra1", "target": "heat1"  },
  { "id": "e5", "source": "heat1",  "target": "finish" }
]
```

---

## Files

| File               | Purpose                                            |
|--------------------|----------------------------------------------------|
| `run_workflow.py`  | Graph scheduler + all device dispatch logic        |
| `OTFLEX_WORKFLOW_Iliya.py` | Legacy procedural workflow (for reference) |
| `OTFLEX_WORKFLOW_Iliya_dryrun.py` | Dry-run variant of the above        |
