#!/usr/bin/env python3
"""
run_workflow.py
---------------
Reads a Canvas-exported JSON workflow and executes it against the SDL1 hardware stack.

Execution model
  - Nodes are dispatched by their "type" prefix (e.g. otflex*, myxArm*, mqtt*, sdl1*)
  - Edges can carry a "mode" field of "sequential" (default) or "parallel"
  - Parallel sibling groups are launched concurrently with asyncio.gather()
  - Resource locks prevent conflicting nodes from running at the same time

Hardware adapters
  - OTFlex       (otflex_adapter.py)     – Opentrons liquid handler
  - MyxArm       (arm_adapter.py)        – robotic arm
  - MQTT bus     (iot_mqtt.py)           – pumps, ultrasonic, heater, reactor, furnace
  - Potentiostat (potentiostat_adapter.py) – electrochemical measurements

CLI usage
  python -m src.workflows.run_workflow --json data/workflows/my_workflow.json
  python -m src.workflows.run_workflow --json data/workflows/my_workflow.json --no-arm
    python -m src.workflows.run_workflow --json data/workflows/my_workflow.json --start-node my_node_id
"""

import argparse
import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..adapters.arm_adapter import MyxArm
from ..adapters.iot_mqtt import (
    ControllerBeacon,
    FurnaceMQTT,
    HeatMQTT,
    PumpMQTT,
    ReactorMQTT,
    UltraMQTT,
    _best_effort_all_off,
)
from ..adapters.otflex_adapter import OTFlex
from ..adapters.potentiostat_adapter import PotentiostatAdapter


# ---------------------------------------------------------------------------
# Resource locking — prevents two nodes from using the same hardware slot
# ---------------------------------------------------------------------------

class ResourceLocks:
    """Minimal async lock pool. Each named resource gets its own asyncio.Lock."""

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}

    def get(self, name: str) -> asyncio.Lock:
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]

    @asynccontextmanager
    async def acquire_many(self, names: List[str]):
        """Acquire multiple locks in a consistent (sorted) order to avoid deadlocks."""
        locks = [self.get(n) for n in sorted(set(n for n in names if n))]
        for lk in locks:
            await lk.acquire()
        try:
            yield
        finally:
            for lk in reversed(locks):
                lk.release()


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

class RetryError(Exception):
    pass


async def with_retry(coro_func, *, retries: int = 0, timeout: Optional[float] = None,
                     retry_delay: float = 0.5, desc: str = ""):
    """
    Run coro_func() up to (retries + 1) times.
    Optional per-attempt timeout in seconds.
    """
    for attempt in range(retries + 1):
        try:
            if timeout:
                return await asyncio.wait_for(coro_func(), timeout=timeout)
            return await coro_func()
        except Exception as exc:
            if attempt < retries:
                await asyncio.sleep(retry_delay)
            else:
                raise RetryError(
                    f"[FAILED after {retries + 1} attempt(s)] {desc}: {exc}"
                ) from exc


# ---------------------------------------------------------------------------
# MQTT device bundle — wraps all IoT nodes from a single "mqtt" config block
# ---------------------------------------------------------------------------

class MQTTDevices:
    """
    Manages all MQTT-based devices as a group.

    Expected JSON block in workflow "devices.mqtt":
    {
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

    Any "topics" entry can be omitted to disable that device.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        broker   = cfg.get("broker", "localhost")
        port     = int(cfg.get("port", 1883))
        username = cfg.get("username")
        password = cfg.get("password")
        topics   = cfg.get("topics", {})

        common = dict(broker=broker, port=port, username=username, password=password)

        self.pumps:   Optional[PumpMQTT]    = None
        self.ultra:   Optional[UltraMQTT]   = None
        self.heat:    Optional[HeatMQTT]    = None
        self.reactor: Optional[ReactorMQTT] = None
        self.furnace: Optional[FurnaceMQTT] = None
        self.beacon:  Optional[ControllerBeacon] = None

        if topics.get("pumps"):
            self.pumps   = PumpMQTT(**common,    base_topic=topics["pumps"],   client_id="wf-pumps")
        if topics.get("ultra"):
            self.ultra   = UltraMQTT(**common,   base_topic=topics["ultra"],   client_id="wf-ultra")
        if topics.get("heat"):
            self.heat    = HeatMQTT(**common,    base_topic=topics["heat"],    client_id="wf-heat")
        if topics.get("reactor"):
            self.reactor = ReactorMQTT(**common, base_topic=topics["reactor"], client_id="wf-reactor")
        if topics.get("furnace"):
            self.furnace = FurnaceMQTT(**common, base_topic=topics["furnace"], client_id="wf-furnace")

        # Controller beacon publishes ONLINE/OFFLINE and a heartbeat for ESP watchdogs
        beacon_topic    = cfg.get("status_topic",    "pyctl/status")
        heartbeat_topic = cfg.get("heartbeat_topic", "pyctl/heartbeat")
        self.beacon = ControllerBeacon(
            broker=broker, port=port, username=username, password=password,
            client_id="wf-controller",
            status_topic=beacon_topic,
            heartbeat_topic=heartbeat_topic,
        )

    def connect(self) -> None:
        """Start the controller beacon and connect any configured devices."""
        self.beacon.start()
        for dev in (self.pumps, self.ultra, self.heat, self.reactor, self.furnace):
            if dev is not None:
                dev.ensure_connected()
        time.sleep(0.5)  # let connections settle
        print("[MQTT] All devices connected.")

    def disconnect(self) -> None:
        """Best-effort shutdown: turn everything off, then disconnect."""
        _best_effort_all_off(
            pumps=self.pumps,
            ultra=self.ultra,
            heat=self.heat,
            reactor=self.reactor,
            furnace=self.furnace,
        )
        for dev in (self.pumps, self.ultra, self.heat, self.reactor, self.furnace):
            if dev is not None:
                try:
                    dev.disconnect()
                except Exception:
                    pass
        if self.beacon:
            self.beacon.stop()
        print("[MQTT] All devices disconnected.")


# ---------------------------------------------------------------------------
# Workflow runner
# ---------------------------------------------------------------------------

class WorkflowRunner:
    """
    Loads a workflow JSON and runs it.

    Node routing:
      type starts with "otflex"   → OTFlex liquid handler
      type starts with "myxArm"   → robotic arm
      type starts with "mqtt"     → MQTT IoT devices (pump / ultra / heat / reactor / furnace)
      type starts with "sdl1"     → potentiostat / electrochemical measurement
      type == "input" / "output"  → no-op (graph boundaries)
    """

    def __init__(
        self,
        wf: Dict[str, Any],
        root_dir: Path,
        use_arm: bool = True,
        start_node: Optional[str] = None,
    ) -> None:
        self.wf          = wf
        self.root_dir    = root_dir
        self.nodes_by_id = {n["id"]: n for n in wf["workflow"]["nodes"]}
        self.edges       = wf["workflow"]["edges"]
        self.resources   = ResourceLocks()
        self.start_node  = start_node

        if self.start_node is not None and self.start_node not in self.nodes_by_id:
            raise ValueError(f"Unknown --start-node '{self.start_node}'")

        self.active_node_ids = self._collect_downstream_nodes(self.start_node)

        devices = wf.get("devices", {})

        # --- MQTT IoT devices ---
        mqtt_cfg = devices.get("mqtt") or {}

        # --- OTFlex ---
        otflex_cfg = dict(devices.get("otflex", {}) or {})
        if mqtt_cfg and "mqtt" not in otflex_cfg:
            otflex_cfg["mqtt"] = mqtt_cfg
        # Allow a separate file reference so one config can be reused across workflows
        otflex_ref = devices.get("otflex_file")
        if otflex_ref:
            try:
                ref_path = (root_dir / otflex_ref).resolve()
                otflex_cfg = json.loads(ref_path.read_text(encoding="utf-8"))
                print(f"[Workflow] OTFlex config loaded from {otflex_ref}")
            except Exception as exc:
                print(f"[Workflow][WARN] Could not load otflex_file '{otflex_ref}': {exc}")
        self.otflex = OTFlex(otflex_cfg, root_dir=root_dir)

        # --- Potentiostat ---
        self.potentiostat = PotentiostatAdapter(
            devices.get("potentiostat") or {}, root_dir=root_dir
        )

        # --- MQTT IoT devices ---
        self.mqtt = MQTTDevices(mqtt_cfg) if mqtt_cfg else None

        # --- Robotic arm ---
        arm_cfg = devices.get("arm") or {}
        self.use_arm = use_arm and arm_cfg.get("enabled", True)
        self.arm: Optional[MyxArm] = MyxArm(arm_cfg, root_dir=root_dir) if self.use_arm else None
        if not self.use_arm:
            print("[Workflow] Arm disabled.")

        if self.start_node is not None:
            print(
                f"[Workflow] Starting from node '{self.start_node}' "
                f"(executing {len(self.active_node_ids)} downstream node(s))."
            )

    def _collect_downstream_nodes(self, start_node: Optional[str]) -> Set[str]:
        """Return all nodes reachable from start_node (inclusive)."""
        if start_node is None:
            return set(self.nodes_by_id.keys())

        children_all = {nid: [] for nid in self.nodes_by_id}
        for edge in self.edges:
            src, dst = edge["source"], edge["target"]
            if src in self.nodes_by_id and dst in self.nodes_by_id:
                children_all[src].append(dst)

        seen: Set[str] = set()
        stack = [start_node]
        while stack:
            curr = stack.pop()
            if curr in seen:
                continue
            seen.add(curr)
            stack.extend(children_all.get(curr, []))
        return seen

    # -----------------------------------------------------------------------
    # Graph construction
    # -----------------------------------------------------------------------

    def _build_graph(self):
        """Build parent/child adjacency maps and a per-edge property dict."""
        node_ids   = self.active_node_ids
        parents    = {nid: set()  for nid in node_ids}
        children   = {nid: []     for nid in node_ids}
        edge_props = {}

        for edge in self.edges:
            src, dst = edge["source"], edge["target"]
            if src not in self.nodes_by_id or dst not in self.nodes_by_id:
                missing = []
                if src not in self.nodes_by_id:
                    missing.append(f"source='{src}'")
                if dst not in self.nodes_by_id:
                    missing.append(f"target='{dst}'")
                edge_id = edge.get("id", "<no-id>")
                raise ValueError(
                    f"Invalid workflow edge {edge_id}: unresolved node reference(s): {', '.join(missing)}"
                )
            if src not in node_ids or dst not in node_ids:
                continue
            children[src].append(dst)
            parents[dst].add(src)
            edge_props[(src, dst)] = edge

        return parents, children, edge_props

    # -----------------------------------------------------------------------
    # Main execution loop
    # -----------------------------------------------------------------------

    async def run(self) -> None:
        # Connect all devices
        await self.otflex.connect()
        await self.potentiostat.connect()
        if self.arm:
            await self.arm.connect()
        if self.mqtt:
            await asyncio.to_thread(self.mqtt.connect)

        parents, children, edge_props = self._build_graph()

        def edge_mode(src: str, dst: str) -> str:
            """Return the execution mode ('sequential' or 'parallel') for an edge."""
            e = edge_props.get((src, dst), {})
            return (e.get("data") or {}).get("mode") or e.get("mode", "sequential")

        def parallel_groups(node: str) -> List[List[str]]:
            """
            Group the children of 'node' by how they should be launched.
            Parallel-mode children are returned as a single group; each
            sequential child is its own single-element group.
            """
            seq, par = [], []
            for child in children.get(node, []):
                if edge_mode(node, child) == "parallel":
                    par.append(child)
                else:
                    seq.append(child)
            groups = []
            if par:
                groups.append(par)
            for s in seq:
                groups.append([s])
            return groups

        # Kahn-style traversal with parallel group support
        ready: Set[str] = {nid for nid, p in parents.items() if not p}
        if self.start_node is not None:
            ready = {self.start_node}
        done:  Set[str] = set()

        while ready:
            curr = ready.pop()
            if curr in done:
                continue

            await self._run_node(curr)
            done.add(curr)

            for group in parallel_groups(curr):
                # Only launch a group when every member's parents are finished
                runnable = [n for n in group if parents[n].issubset(done)]
                if len(group) == 1:
                    if runnable:
                        ready.add(runnable[0])
                elif set(runnable) == set(group):
                    await asyncio.gather(*(self._run_node(n) for n in group))
                    done.update(group)

            # Re-scan: some nodes may now be unblocked
            for nid, pset in parents.items():
                if nid not in done and pset.issubset(done):
                    ready.add(nid)

        # Disconnect everything
        if self.arm:
            await self.arm.disconnect()
        await self.potentiostat.disconnect()
        await self.otflex.disconnect()
        if self.mqtt:
            await asyncio.to_thread(self.mqtt.disconnect)

        print("[Workflow] Finished.")

    # -----------------------------------------------------------------------
    # Node dispatcher
    # -----------------------------------------------------------------------

    async def _run_node(self, nid: str) -> None:
        node    = self.nodes_by_id[nid]
        ntype   = node["type"]
        label   = node.get("label") or node.get("data", {}).get("label", ntype)
        params  = node.get("params") or node.get("data", {}).get("params") or {}
        locks   = params.get("resourceLocks") or node.get("resourceLocks") or []
        retries = params.get("retries", 0)
        timeout = params.get("timeout", None)

        async def _execute():
            print(f"[Node {nid}] {label} :: {ntype}")

            if ntype in ("input", "output"):
                return  # graph boundary nodes — nothing to do

            key = ntype.lower()

            if key.startswith("otflexmyxarm") or key.startswith("myxarm"):
                await self._run_arm(ntype, params, locks)

            elif key.startswith("otflex"):
                await self._run_otflex(ntype, params, locks)

            elif key.startswith("mqtt"):
                await self._run_mqtt(ntype, params, locks)

            elif key.startswith("sdl1"):
                await self._run_sdl1(ntype, params, locks)

            else:
                print(f"[Node {nid}] Unknown type '{ntype}' — skipping.")

        await with_retry(_execute, retries=retries, timeout=timeout, desc=f"node {nid}")

    # -----------------------------------------------------------------------
    # Per-family handlers
    # -----------------------------------------------------------------------

    async def _run_otflex(self, ntype: str, params: Dict[str, Any], locks: List[str]) -> None:
        """Dispatch OTFlex liquid-handling nodes."""
        async with self.resources.acquire_many(locks):
            key = ntype.lower()
            if   "tooltransfer"     in key: await self.otflex.toolTransfer(params)
            elif "potentexperiment" in key: await self.otflex.potentExperiment(params)
            elif "flushwell"        in key: await self.otflex.flushWell(params)
            elif "transfer"         in key: await self.otflex.transfer(params)
            elif "gripper"          in key: await self.otflex.gripper(params)
            elif "wash"             in key: await self.otflex.wash(params)
            elif "furnace"          in key: await self.otflex.furnace(params)
            elif "electrode"        in key: await self.otflex.electrode(params)
            elif "reactor"          in key: await self.otflex.reactor(params)
            else:
                print(f"[OTFlex] Unrecognised node type: {ntype}")

    async def _run_arm(self, ntype: str, params: Dict[str, Any], locks: List[str]) -> None:
        """Dispatch robotic arm nodes."""
        if not self.arm:
            print(f"[Arm] Arm disabled — skipping node '{ntype}'.")
            return
        async with self.resources.acquire_many(locks):
            key = ntype.lower()
            if   "run" in key or "sequence" in key: await self.arm.run_sequence(params)
            elif "position" in key or "move" in key: await self.arm.move(params)
            elif "gripper"  in key:                  await self.arm.gripper(params)
            else:
                print(f"[Arm] Unrecognised node type: {ntype}")

    async def _run_mqtt(self, ntype: str, params: Dict[str, Any], locks: List[str]) -> None:
        """
        Dispatch MQTT IoT nodes.

        Node types and expected params
        ┌─────────────────┬────────────────────────────────────────────────────┐
        │ mqttWait        │ duration_s (float, optional), duration_ms (int)    │
        │ mqttPump        │ channel (int), duration_ms (int, optional)         │
        │ mqttPumpOff     │ channel (int)                                      │
        │ mqttUltra       │ channel (int), duration_ms (int, optional)         │
        │ mqttUltraOff    │ channel (int)                                      │
        │ mqttHeat        │ channel (int), target_c (float)                    │
        │                 │ pid (bool, default true), wait_s (float, optional) │
        │ mqttHeatOff     │ channel (int)                                      │
        │ mqttReactor     │ direction ("forward"/"reverse"), duration_ms (int) │
        │ mqttReactorStop │ —                                                  │
        │ mqttFurnace     │ action ("open"/"close"), duration_ms (int)         │
        └─────────────────┴────────────────────────────────────────────────────┘
        """
        if self.mqtt is None:
            print(f"[MQTT] No mqtt config in workflow — skipping node '{ntype}'.")
            return

        async with self.resources.acquire_many(locks):
            key = ntype.lower()
            m   = self.mqtt

            # --- Workflow timing helper ---
            if "wait" in key or "delay" in key or "pause" in key:
                wait_s = params.get("duration_s")
                if wait_s is None:
                    wait_ms = params.get("duration_ms")
                    wait_s = (float(wait_ms) / 1000.0) if wait_ms is not None else 0.0
                wait_s = max(0.0, float(wait_s))
                print(f"[MQTT] Waiting for {wait_s:.3f}s")
                await asyncio.sleep(wait_s)
                return

            # --- Pumps ---
            if "pump" in key:
                if m.pumps is None:
                    print("[MQTT] Pump device not configured.")
                    return
                ch = int(params.get("channel", 1))
                if "off" in key:
                    await asyncio.to_thread(m.pumps.off, ch)
                else:
                    dur = params.get("duration_ms")
                    await asyncio.to_thread(m.pumps.on, ch, dur)

            # --- Ultrasonic ---
            elif "ultra" in key:
                if m.ultra is None:
                    print("[MQTT] Ultrasonic device not configured.")
                    return
                ch = int(params.get("channel", 1))
                if "off" in key:
                    await asyncio.to_thread(m.ultra.off, ch)
                else:
                    dur = params.get("duration_ms")
                    await asyncio.to_thread(m.ultra.on, ch, dur)

            # --- Heater ---
            elif "heat" in key:
                if m.heat is None:
                    print("[MQTT] Heat device not configured.")
                    return
                ch = int(params.get("channel", 1))
                if "off" in key:
                    await asyncio.to_thread(m.heat.pid_off, ch)
                    await asyncio.to_thread(m.heat.set_pwm, ch, 0)
                    await asyncio.to_thread(m.heat.off, ch)
                else:
                    target_c = float(params["target_c"])
                    use_pid  = bool(params.get("pid", True))
                    await asyncio.to_thread(m.heat.set_target, ch, target_c)
                    if use_pid:
                        await asyncio.to_thread(m.heat.pid_on, ch)
                    # Optional blocking wait for the temperature to stabilise
                    wait_s = params.get("wait_s")
                    if wait_s:
                        await asyncio.sleep(float(wait_s))

            # --- Reactor linear actuator ---
            elif "reactor" in key:
                if m.reactor is None:
                    print("[MQTT] Reactor device not configured.")
                    return
                if "stop" in key:
                    await asyncio.to_thread(m.reactor.stop)
                else:
                    direction = params.get("direction", "forward").lower()
                    dur       = params.get("duration_ms")
                    if direction == "forward":
                        await asyncio.to_thread(m.reactor.forward, dur)
                    else:
                        await asyncio.to_thread(m.reactor.reverse, dur)
                    # Keep Python-side timing aligned with firmware auto-stop windows.
                    # This mirrors manual demo usage where a sleep follows timed motion.
                    if dur is not None:
                        wait_s = max(0.0, float(dur) / 1000.0)
                        if wait_s > 0:
                            print(f"[MQTT] Reactor command duration {wait_s:.3f}s; waiting in Python")
                            await asyncio.sleep(wait_s)

            # --- Furnace door ---
            elif "furnace" in key:
                if m.furnace is None:
                    print("[MQTT] Furnace device not configured.")
                    return
                if "stop" in key:
                    await asyncio.to_thread(m.furnace.stop)
                else:
                    action = params.get("action", "open").lower()
                    dur    = params.get("duration_ms")
                    if action == "open":
                        await asyncio.to_thread(m.furnace.open, dur)
                    else:
                        await asyncio.to_thread(m.furnace.close, dur)
                    if dur is not None:
                        wait_s = max(0.0, float(dur) / 1000.0)
                        if wait_s > 0:
                            print(f"[MQTT] Furnace command duration {wait_s:.3f}s; waiting in Python")
                            await asyncio.sleep(wait_s)

            else:
                print(f"[MQTT] Unrecognised node type: {ntype}")

    async def _run_sdl1(self, ntype: str, params: Dict[str, Any], locks: List[str]) -> None:
        """Dispatch SDL1 electrochemical measurement nodes."""
        async with self.resources.acquire_many(locks):
            key = ntype.lower()
            if "electrochemicalmeasurement" in key or "echem" in key or "potent" in key:
                await self.potentiostat.echem_measure(params)
            else:
                print(f"[SDL1] Unrecognised node type: {ntype}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an SDL1 workflow JSON against the hardware stack."
    )
    parser.add_argument("--json",   required=True, help="Path to workflow JSON file")
    parser.add_argument("--no-arm", action="store_true", help="Disable robotic arm")
    parser.add_argument(
        "--start-node",
        default=None,
        help="Node ID to start execution from; only this node and its downstream path are executed.",
    )
    args = parser.parse_args()

    wf_path = Path(args.json)
    wf      = json.loads(wf_path.read_text(encoding="utf-8"))

    runner = WorkflowRunner(
        wf,
        root_dir=wf_path.parent,
        use_arm=not args.no_arm,
        start_node=args.start_node,
    )
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
