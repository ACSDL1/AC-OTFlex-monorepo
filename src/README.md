# src backend overview

This folder contains the Python backend that turns workflow JSON into hardware actions.

## Mental model

A workflow node is **not** selected by its `id`.

A node has four important fields:

- `id`: unique graph key used by edges and `--start-node`
- `type`: selects which backend handler runs
- `label`: human-readable name shown in logs/UI
- `params`: arguments passed to the selected handler

Example:

```json
{
  "id": "step_07",
  "type": "mqttFurnace",
  "label": "Close furnace",
  "params": {
    "action": "close",
    "duration_ms": 15000
  }
}
```

## Can node IDs be simple numbers?

Yes.

The `id` only needs to be unique inside the workflow and match any edge references.
It does **not** map to a hardcoded Python function name.

These are all valid styles:

- `0`, `1`, `2`
- `step_0`, `step_1`, `step_2`
- `open_furnace_0`, `open_furnace_1`

What matters:

1. every node has a unique `id`
2. every edge `source` and `target` points to a real node `id`
3. if you use `--start-node`, it must match a real `id`

## What is hardcoded and what is not?

### Not hardcoded

- node `id`
- node `label`
- most parameter values in `params`
- workflow graph structure in `edges`

### Hardcoded / backend-defined

- supported `type` families: `otflex*`, `mqtt*`, `myxArm*`, `sdl1*`
- dispatch rules for those families
- the parameter names each action expects

So:

- `id` can be renamed freely
- `label` can be renamed freely
- `type` cannot be arbitrary; it must match a supported backend action

## Dispatch path

The execution path is:

1. `src/workflows/run_workflow.py`
   - loads the JSON
   - builds the graph from `nodes` + `edges`
   - executes nodes in dependency order
   - routes each node by `type`

2. Family dispatch:
   - `otflex*` -> `src/adapters/otflex_adapter.py`
   - `mqtt*` -> `src/adapters/iot_mqtt.py` wrappers via `run_workflow.py`
   - `sdl1*` -> `src/adapters/potentiostat_adapter.py`
   - `myxArm*` -> `src/adapters/arm_adapter.py`

3. Adapter/runtime layer
   - OTFlex adapter normalizes `params` and calls runtime entrypoints in `src/core/otflex_runtime.py`
   - MQTT nodes usually execute directly through MQTT adapter objects in `run_workflow.py`
   - potentiostat nodes call `PotentiostatAdapter.echem_measure()`

## How `type` is interpreted

The system first looks at the prefix:

- `otflexTransfer` -> OTFlex family
- `otflexFlushWell` -> OTFlex family
- `mqttFurnace` -> MQTT family
- `mqttReactor` -> MQTT family
- `sdl1ElectrochemicalMeasurement` -> potentiostat family

Inside a family, the backend often uses substring matching.

Examples:

- any OTFlex type containing `transfer` maps to transfer logic
- any OTFlex type containing `flushwell` maps to flush logic
- any MQTT type containing `furnace` maps to furnace logic

That means `type` names should stay descriptive and compatible with the dispatcher.

## Example: how flushing works

Your flush node:

```json
{
  "id": "flush_col1_with_flush_tool",
  "type": "otflexFlushWell",
  "params": {
    "from": {"labware": "single_electrode_module", "well": "C1"},
    "to": {"labware": "autreactor", "well": ["A1", "B1"]},
    "in_pump_id": 1,
    "out_pump_id": 3,
    "time_ms": 3000
  }
}
```

Backend path:

1. `run_workflow.py` sees `type = otflexFlushWell`
2. `_run_otflex()` dispatches to `self.otflex.flushWell(params)`
3. `otflex_adapter.py` normalizes nested JSON into flat keys like:
   - `from_labware`
   - `to_well`
   - `in_pump_id`
   - `out_pump_id`
4. adapter calls runtime entrypoint `otflex_flushWell()`
5. `src/core/otflex_runtime.py` runs `_OTFlexRuntime.flushWell()`
6. runtime moves the Opentrons tool and triggers MQTT pump actions

So yes: **flushing is a real implemented backend function**, not just a workflow label.

## Example: how furnace works

A furnace node does **not** go through `otflex_runtime.py` unless you explicitly use an `otflexFurnace` node.

For your current workflow:

- `type = mqttFurnace`
- `run_workflow.py` handles it directly in `_run_mqtt()`
- that calls `FurnaceMQTT.open()` or `FurnaceMQTT.close()`

## Recommended workflow naming style

If you want cleaner JSON, use:

- short IDs for graph references
- descriptive labels for humans

Example:

```json
{
  "id": "step_0",
  "type": "mqttFurnace",
  "label": "Open furnace",
  "params": {
    "action": "open",
    "duration_ms": 8000
  }
}
```

Then:

- edges point to `step_0`
- logs still show `Open furnace`
- `--start-node step_0` still works

## Rule of thumb

- use `id` for machine references
- use `label` for readability
- use `type` to select backend behavior
- use `params` to configure that behavior
- use `devices` for shared hardware connection settings
