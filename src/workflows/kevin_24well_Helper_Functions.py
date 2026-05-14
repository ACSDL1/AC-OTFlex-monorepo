from __future__ import annotations

import asyncio
import csv
import json
import os
import posixpath
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


REACTOR_WELLS_24 = [
    f"{row}{col}"
    for col in range(1, 7)
    for row in ("A", "B", "C", "D")
]


def find_repo_root(start: Path | None = None) -> Path:
    root = (start or Path.cwd()).resolve()
    while root != root.parent and not (root / "src").exists():
        root = root.parent
    if not (root / "src").exists():
        raise RuntimeError("Could not find repository root containing src/")
    return root


def load_plan(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        plan = json.load(f)
    validate_plan(plan)
    return plan


def save_plan(plan: dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
        f.write("\n")


def enabled_experiments(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [exp for exp in plan.get("experiments", []) if exp.get("enabled", True)]


def validate_plan(plan: dict[str, Any]) -> None:
    defaults = plan.get("defaults", {})
    max_volume = float(defaults.get("max_reactor_volume_uL", 2664))
    experiments = plan.get("experiments", [])
    if len(experiments) != 24:
        raise ValueError(f"Expected 24 experiments, found {len(experiments)}")

    seen = set()
    for exp in experiments:
        well = exp.get("well")
        if well not in REACTOR_WELLS_24:
            raise ValueError(f"Invalid reactor well: {well!r}")
        if well in seen:
            raise ValueError(f"Duplicate reactor well: {well}")
        seen.add(well)

        solution = exp.get("solution", [])
        if not solution:
            raise ValueError(f"{well}: solution list is empty")
        total = 0.0
        for component in solution:
            volume = float(component.get("volume_uL", 0))
            if volume <= 0:
                raise ValueError(f"{well}: solution volume must be > 0: {component}")
            if not component.get("source_well"):
                raise ValueError(f"{well}: component is missing source_well: {component}")
            total += volume
        if total > max_volume:
            raise ValueError(f"{well}: total solution volume {total} uL exceeds {max_volume} uL")

        biologic = merged_biologic_params(plan, exp)
        if not biologic.get("techniques"):
            raise ValueError(f"{well}: biologic.techniques is empty")


def experiments_dataframe(plan: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for exp in plan.get("experiments", []):
        solution = exp.get("solution", [])
        biologic = merged_biologic_params(plan, exp)
        rows.append(
            {
                "enabled": exp.get("enabled", True),
                "well": exp.get("well"),
                "experiment_id": expand_experiment_id(plan, exp),
                "solution_total_uL": sum(float(x.get("volume_uL", 0)) for x in solution),
                "solution": "; ".join(
                    f"{x.get('liquid', x.get('source_well'))}:{x.get('volume_uL')}uL"
                    for x in solution
                ),
                "biologic_channel": biologic.get("channel"),
                "biologic_techniques": ", ".join(t.get("type", "?") for t in biologic.get("techniques", [])),
            }
        )
    return pd.DataFrame(rows)


def expand_experiment_id(plan: dict[str, Any], exp: dict[str, Any]) -> str:
    batch_id = plan.get("batch_id") or datetime.now().strftime("%Y%m%d_%H%M%S")
    well = exp["well"]
    template = (
        exp.get("biologic", {}).get("experiment_id")
        or plan.get("defaults", {}).get("biologic", {}).get("experiment_id")
        or "{batch_id}_{well}"
    )
    return str(template).format(batch_id=batch_id, well=well)


def merged_biologic_params(plan: dict[str, Any], exp: dict[str, Any]) -> dict[str, Any]:
    default_bio = dict(plan.get("defaults", {}).get("biologic", {}))
    exp_bio = dict(exp.get("biologic", {}))
    merged = {**default_bio, **exp_bio}
    merged["experiment_id"] = expand_experiment_id(plan, exp)
    return merged


def solution_transfer_groups(plan: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = plan.get("defaults", {})
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}

    for exp in enabled_experiments(plan):
        target_well = exp["well"]
        for component in exp.get("solution", []):
            source_labware = component.get("source_labware", defaults.get("source_labware", "source_plate"))
            source_well = component["source_well"]
            volume_uL = float(component["volume_uL"])
            key = (
                source_labware,
                source_well,
                volume_uL,
                component.get("from_offsetZ", defaults.get("solution_from_offset", {}).get("offsetZ", 5)),
                component.get("to_offsetZ", defaults.get("solution_to_offset", {}).get("offsetZ", 20)),
            )
            group = groups.setdefault(
                key,
                {
                    "source_labware": source_labware,
                    "source_well": source_well,
                    "volume_uL": volume_uL,
                    "liquid": component.get("liquid", source_well),
                    "target_wells": [],
                    "from_offset": dict(defaults.get("solution_from_offset", {"offsetX": 0, "offsetY": 0, "offsetZ": 5})),
                    "to_offset": dict(defaults.get("solution_to_offset", {"offsetX": 0, "offsetY": 0, "offsetZ": 20})),
                },
            )
            group["target_wells"].append(target_well)

    return list(groups.values())


async def fill_reactor_from_plan(otflex: Any, plan: dict[str, Any], *, dry_run: bool = True) -> list[dict[str, Any]]:
    defaults = plan.get("defaults", {})
    transfers = []
    for group in solution_transfer_groups(plan):
        params = {
            "from": {
                "labware": group["source_labware"],
                "well": group["source_well"],
                **group["from_offset"],
            },
            "to": {
                "labware": defaults.get("reactor_labware", "auto_reactor"),
                "well": group["target_wells"],
                **group["to_offset"],
            },
            "volume_uL": int(round(group["volume_uL"])),
            "move_speed": defaults.get("solution_move_speed", 120),
            "pipette": defaults.get("pipette", "p1000_single_flex"),
            "tiprack": defaults.get("tiprack", "tiprack_1000ul"),
            "autopick_tip": defaults.get("autopick_tip", True),
        }
        transfers.append(params)
        if dry_run:
            print("[DRY RUN] transfer", params)
        else:
            await otflex.transfer(params)
    return transfers


def flush_well_params(
    plan: dict[str, Any],
    *,
    wells: list[str] | None = None,
    source_labware: str | None = None,
    source_well: str | None = None,
    to_offset_z: float | None = None,
    in_pump_id: int | None = None,
    out_pump_id: int | None = None,
    in_time_ms: int | None = None,
    out_time_ms: int | None = None,
    repeats: int | None = None,
    purge_ms: int | None = None,
    return_dz: float | None = None,
    home_after: bool | None = None,
) -> dict[str, Any]:
    defaults = plan.get("defaults", {})
    flush_defaults = defaults.get("flush", {})
    target_wells = wells or [exp["well"] for exp in enabled_experiments(plan)]

    return {
        "from": {
            "labware": source_labware
            or flush_defaults.get("source_labware")
            or defaults.get("electrode_source_labware", "electrode_module"),
            "well": source_well or flush_defaults.get("source_well", "C1"),
            "offsetX": float(flush_defaults.get("source_offsetX", 0.0)),
            "offsetY": float(flush_defaults.get("source_offsetY", 0.0)),
            "offsetZ": float(flush_defaults.get("source_offsetZ", 0.0)),
        },
        "to": {
            "labware": defaults.get("reactor_labware", "auto_reactor"),
            "well": target_wells,
            "offsetX": float(flush_defaults.get("target_offsetX", 0.0)),
            "offsetY": float(flush_defaults.get("target_offsetY", 0.0)),
            "offsetZ": float(to_offset_z if to_offset_z is not None else flush_defaults.get("target_offsetZ", 5.0)),
        },
        "pipette": defaults.get("pipette", "p1000_single_flex"),
        "in_pump_id": int(in_pump_id if in_pump_id is not None else flush_defaults.get("in_pump_id", 2)),
        "out_pump_id": int(out_pump_id if out_pump_id is not None else flush_defaults.get("out_pump_id", 3)),
        "in_time_ms": int(in_time_ms if in_time_ms is not None else flush_defaults.get("in_time_ms", 2000)),
        "out_time_ms": int(out_time_ms if out_time_ms is not None else flush_defaults.get("out_time_ms", 5000)),
        "repeats": int(repeats if repeats is not None else flush_defaults.get("repeats", 4)),
        "purge_ms": int(purge_ms if purge_ms is not None else flush_defaults.get("purge_ms", 0)),
        "return_dZ": float(return_dz if return_dz is not None else flush_defaults.get("return_dZ", 12.0)),
        "home_after": bool(home_after if home_after is not None else flush_defaults.get("home_after", False)),
    }


async def flush_wells_from_plan(
    otflex: Any,
    plan: dict[str, Any],
    *,
    dry_run: bool = True,
    wells: list[str] | None = None,
    **flush_overrides: Any,
) -> dict[str, Any]:
    params = flush_well_params(plan, wells=wells, **flush_overrides)
    if dry_run:
        print("[DRY RUN] flush wells", params)
        return params

    if otflex is None:
        raise RuntimeError("Run the setup/connect notebook first in this same kernel. Missing: otflex")
    rt = getattr(getattr(otflex, "mod", None), "_RT", None)
    if rt is None or getattr(rt, "mqtt_pumps", None) is None:
        raise RuntimeError("OTFlex runtime MQTT pumps are not configured. Run the Connect Devices cell first.")

    await otflex.flushWell(params)
    return params


def require_setup_namespace(ns: dict[str, Any], names: list[str]) -> None:
    missing = [name for name in names if name not in ns or ns[name] is None]
    if missing:
        raise RuntimeError(
            "Run the setup/connect notebook first in this same kernel. Missing: "
            + ", ".join(missing)
        )


def setup_status(ns: dict[str, Any], *, require_connected_otflex: bool = True) -> tuple[bool, list[str]]:
    missing = []
    otflex = ns.get("otflex")
    if otflex is None:
        missing.append("otflex")
    elif require_connected_otflex:
        rt = getattr(getattr(otflex, "mod", None), "_RT", None)
        if rt is None or getattr(rt, "oc", None) is None:
            missing.append("connected OTFlex runtime (run Connect Devices)")
    return not missing, missing


def auto_dry_run(ns: dict[str, Any], configured: bool | None = None) -> tuple[bool, list[str]]:
    ready, missing = setup_status(ns)
    if configured is None:
        return (not ready), missing
    return bool(configured), missing


def _rt_from_otflex(otflex: Any) -> Any:
    rt = getattr(getattr(otflex, "mod", None), "_RT", None)
    if rt is None or getattr(rt, "oc", None) is None:
        raise RuntimeError("OTFlex runtime controller is not available. Run setup/connect cells first.")
    return rt


async def pick_electrode_tool(otflex: Any, ec_state: dict[str, Any], defaults: dict[str, Any]) -> None:
    rt = _rt_from_otflex(otflex)
    source_labware = defaults.get("electrode_source_labware", "electrode_module")
    source_well = defaults.get("electrode_source_well", "A1")
    pipette = defaults.get("pipette", "p1000_single_flex")
    source_id = rt.lw_ids.get(source_labware, source_labware)
    await asyncio.to_thread(
        rt.oc.pickUpTip,
        strLabwareName=source_id,
        strPipetteName=pipette,
        strWellName=source_well,
        fltOffsetX=0.0,
        fltOffsetY=0.0,
        fltOffsetZ=0.0,
    )
    ec_state.update({"tool_attached": True, "current_well": None, "at_ultrasonic": False})
    print(f"Picked electrode tool from {source_labware}.{source_well}")


async def move_electrode_to_well(
    otflex: Any,
    ec_state: dict[str, Any],
    well: str,
    defaults: dict[str, Any],
) -> None:
    if not ec_state.get("tool_attached", False):
        raise RuntimeError("No electrode tool attached. Run pick_electrode_tool first.")
    rt = _rt_from_otflex(otflex)
    reactor_labware = defaults.get("reactor_labware", "auto_reactor")
    pipette = defaults.get("pipette", "p1000_single_flex")
    descent_mm = float(defaults.get("electrode_descent_at_well_mm", 25.0))
    move_speed = int(defaults.get("electrode_move_speed", 80))
    reactor_id = rt.lw_ids.get(reactor_labware, reactor_labware)

    current_well = ec_state.get("current_well")
    if current_well:
        await asyncio.to_thread(
            rt.oc.moveToWell,
            strLabwareName=reactor_id,
            strWellName=current_well,
            strPipetteName=pipette,
            strOffsetStart="top",
            fltOffsetX=0.0,
            fltOffsetY=0.0,
            fltOffsetZ=0.0,
            intSpeed=move_speed,
        )

    for z in (0.0, -descent_mm):
        await asyncio.to_thread(
            rt.oc.moveToWell,
            strLabwareName=reactor_id,
            strWellName=well,
            strPipetteName=pipette,
            strOffsetStart="top",
            fltOffsetX=0.0,
            fltOffsetY=0.0,
            fltOffsetZ=z,
            intSpeed=move_speed,
        )
    ec_state.update({"current_well": well, "at_ultrasonic": False})
    print(f"Electrode positioned in {reactor_labware}.{well}")


async def return_electrode_tool(otflex: Any, ec_state: dict[str, Any], defaults: dict[str, Any]) -> None:
    if not ec_state.get("tool_attached", False):
        return
    rt = _rt_from_otflex(otflex)
    source_labware = defaults.get("electrode_source_labware", "electrode_module")
    source_well = defaults.get("electrode_source_well", "A1")
    pipette = defaults.get("pipette", "p1000_single_flex")
    source_id = rt.lw_ids.get(source_labware, source_labware)
    await asyncio.to_thread(
        rt.oc.moveToWell,
        strLabwareName=source_id,
        strWellName=source_well,
        strPipetteName=pipette,
        strOffsetStart="top",
        fltOffsetX=0.0,
        fltOffsetY=0.0,
        fltOffsetZ=10.0,
        intSpeed=100,
    )
    await asyncio.to_thread(
        rt.oc.dropTip,
        strPipetteName=pipette,
        boolDropInDisposal=False,
        strLabwareName=source_id,
        strWellName=source_well,
        strOffsetStart="bottom",
        fltOffsetX=0.0,
        fltOffsetY=0.0,
        fltOffsetZ=float(defaults.get("electrode_return_dZ", 12.0)),
    )
    ec_state.update({"tool_attached": False, "current_well": None, "at_ultrasonic": False})
    print(f"Returned electrode tool to {source_labware}.{source_well}")


async def _raise_toolhead_to_slot(
    rt: Any,
    *,
    slot: str,
    pipette: str,
    minimum_z_height: int,
    move_speed: int,
) -> None:
    import requests

    command = {
        "data": {
            "commandType": "moveToAddressableArea",
            "params": {
                "minimumZHeight": int(minimum_z_height),
                "forceDirect": False,
                "speed": int(move_speed),
                "pipetteId": rt.oc.pipettes[pipette]["id"],
                "addressableAreaName": slot,
                "stayAtHighestPossibleZ": True,
                "offset": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            "intent": "setup",
        }
    }
    response = await asyncio.to_thread(
        requests.post,
        url=rt.oc.commandURL,
        headers=rt.oc.headers,
        params={"waitUntilComplete": True},
        data=json.dumps(command),
    )
    if response.status_code != 201:
        raise RuntimeError(f"Failed to raise toolhead before sonicator move: {response.status_code} {response.text}")


async def move_electrode_to_ultrasonic(
    otflex: Any,
    ec_state: dict[str, Any],
    defaults: dict[str, Any],
    *,
    station: str = "A",
    immersion_depth_mm: float | None = None,
    minimum_z_height: int | None = None,
    move_speed: int | None = None,
) -> None:
    if not ec_state.get("tool_attached", False):
        raise RuntimeError("No electrode tool attached. Pick up the electrode tool before ultrasonic cleaning.")

    rt = _rt_from_otflex(otflex)
    station = station.upper()
    if station not in {"A", "B"}:
        raise ValueError("station must be 'A' or 'B'")

    pipette = defaults.get("pipette", "p1000_single_flex")
    slot = defaults.get("ultra_slot", "B3")
    sonicator_labware = defaults.get("sonicator_labware", "sonicator_bath")
    target_well = defaults.get(f"sonicator_well_{station.lower()}", "A1" if station == "A" else "A2")
    bath_id = rt.lw_ids.get(sonicator_labware, sonicator_labware)
    immersion_mm = float(
        immersion_depth_mm
        if immersion_depth_mm is not None
        else defaults.get("sonicator_immersion_mm", 35.0)
    )
    speed = int(move_speed if move_speed is not None else defaults.get("electrode_move_speed", 80))
    minimum_z = int(minimum_z_height if minimum_z_height is not None else defaults.get("sonicator_minimum_z_height", 80))
    if immersion_mm < 0:
        raise ValueError("immersion_depth_mm must be >= 0")

    await _raise_toolhead_to_slot(rt, slot=slot, pipette=pipette, minimum_z_height=minimum_z, move_speed=speed)
    for z in (0.0, -immersion_mm):
        await asyncio.to_thread(
            rt.oc.moveToWell,
            strLabwareName=bath_id,
            strWellName=target_well,
            strPipetteName=pipette,
            strOffsetStart="top",
            fltOffsetX=0.0,
            fltOffsetY=0.0,
            fltOffsetZ=z,
            intSpeed=speed,
        )
    ec_state.update({"current_well": None, "at_ultrasonic": True, "ultrasonic_station": station})
    print(f"Tool moved to {sonicator_labware}.{target_well} for ultrasonic station {station}")


async def run_ultrasonic_clean(
    ultra: Any,
    ec_state: dict[str, Any],
    *,
    channel: int = 1,
    duration_s: float = 15.0,
    use_auto_off_ms: bool = True,
    dry_run: bool = True,
) -> None:
    if dry_run:
        print(f"[DRY RUN] ultrasonic clean: channel {channel}, duration {duration_s}s")
        return
    if not ec_state.get("at_ultrasonic", False):
        raise RuntimeError("Tool is not at an ultrasonic position.")
    if ultra is None:
        raise RuntimeError("Ultrasonic MQTT client is not configured. Run the Connect Devices cell first.")

    duration_s = float(duration_s)
    if duration_s <= 0:
        raise ValueError("duration_s must be > 0")
    duration_ms = max(1, int(round(duration_s * 1000)))
    channel = int(channel)

    ultra.ensure_connected()
    if use_auto_off_ms:
        ultra.on(channel, duration_ms)
    else:
        ultra.on(channel)
    try:
        await asyncio.sleep(duration_s)
    finally:
        ultra.off(channel)
    print(f"Ultrasonic clean complete on channel {channel}")


async def ultrasonic_clean_electrode(
    otflex: Any,
    ultra: Any,
    ec_state: dict[str, Any],
    defaults: dict[str, Any],
    *,
    dry_run: bool = True,
    stations: tuple[str, ...] = ("A", "B"),
    channel: int = 1,
    duration_s: float = 15.0,
) -> None:
    if dry_run:
        print(f"[DRY RUN] ultrasonic cleaning at stations {', '.join(stations)} for {duration_s}s each")
        return

    if not ec_state.get("tool_attached", False):
        await pick_electrode_tool(otflex, ec_state, defaults)
    try:
        for station in stations:
            await move_electrode_to_ultrasonic(otflex, ec_state, defaults, station=station)
            await run_ultrasonic_clean(ultra, ec_state, channel=channel, duration_s=duration_s, dry_run=False)
    finally:
        if ec_state.get("tool_attached", False):
            await return_electrode_tool(otflex, ec_state, defaults)


def _auto_key_file(key_file: str | None) -> str:
    if key_file:
        return key_file
    for candidate in [
        Path.home() / ".ssh" / "id_rsa",
        Path.home() / ".ssh" / "id_ed25519",
    ]:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("SSH key not found. Set key_file or place a key in ~/.ssh/")


def _win_path(path_value: str) -> str:
    return str(path_value).replace("/", "\\")


def _remote_abs(path_value: str, base_dir: str) -> str:
    path_value = str(path_value).replace("\\", "/")
    if path_value.startswith("/") or (len(path_value) > 1 and path_value[1] == ":"):
        return path_value
    return posixpath.join(base_dir, path_value)


def _run_remote(ssh: Any, cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    _stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    return exit_code, out, err


def _remote_script(
    *,
    channel: int,
    usb_port: str,
    experiment_id: str,
    remote_results_dir: str,
    biologic_params: dict[str, Any],
    techniques: list[dict[str, Any]],
) -> str:
    return f"""
from pathlib import Path
import os
import subprocess
import sys
import time
import traceback

from biologic import BANDWIDTH, I_RANGE, E_RANGE
from client import biologic_stream
from experiment_helper import run_experiment
from techniques_builder import make_ca, make_ocv

CHANNEL = int({channel})
USB_PORT = {usb_port!r}
EXPERIMENT_ID = {experiment_id!r}
RAW_DIR = Path({remote_results_dir!r})
TECHNIQUES = {json.dumps(techniques)}
OCV_CHECK_DURATION_S = float({biologic_params.get("ocv_check_duration_s", 2)})
HOST_START_TIMEOUT_S = float({biologic_params.get("host_start_timeout_s", 45)})

RAW_DIR.mkdir(parents=True, exist_ok=True)


def build_technique(spec):
    kind = spec.get("type", "ocv").lower()
    params = dict(spec.get("params", {{}}))
    if kind == "ocv":
        return make_ocv(**params)
    if kind == "ca":
        return make_ca(**params)
    raise ValueError(f"Unsupported technique type: {{kind}}")


def run_ocv_connection_check():
    check = make_ocv(
        rest_time_s=OCV_CHECK_DURATION_S,
        record_every_dT=0.2,
        record_every_dE=10,
        E_range=E_RANGE.E_RANGE_2_5V,
        bandwidth=BANDWIDTH.BW_5,
    )
    points = 0
    for _payload in biologic_stream(channel=CHANNEL, techniques=[check], usb_port=USB_PORT):
        points += 1
    return points


def start_biologic_host():
    stdout_path = RAW_DIR / "biologic_host_stdout.log"
    stderr_path = RAW_DIR / "biologic_host_stderr.log"
    stdout_file = open(stdout_path, "ab", buffering=0)
    stderr_file = open(stderr_path, "ab", buffering=0)
    cmd = [sys.executable, "-c", "import biologic_host; biologic_host.main()"]
    kwargs = dict(
        cwd=os.getcwd(),
        stdin=subprocess.DEVNULL,
        stdout=stdout_file,
        stderr=stderr_file,
        close_fds=True,
    )
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    process = subprocess.Popen(cmd, **kwargs)
    print("[REMOTE] Started biologic_host.py with PID", process.pid)


def ensure_biologic_host_ready():
    try:
        points = run_ocv_connection_check()
        print("[REMOTE] OCV preflight succeeded. Points:", points)
        return
    except Exception as first_error:
        print("[REMOTE] OCV preflight failed:", first_error)
        start_biologic_host()

    deadline = time.time() + HOST_START_TIMEOUT_S
    last_error = None
    while time.time() < deadline:
        time.sleep(2)
        try:
            points = run_ocv_connection_check()
            print("[REMOTE] OCV preflight succeeded after host start. Points:", points)
            return
        except Exception as retry_error:
            last_error = retry_error
            print("[REMOTE] Waiting for biologic_host.py:", retry_error)
    raise RuntimeError("biologic_host.py did not pass OCV preflight: " + str(last_error))


try:
    print("[REMOTE] Python:", sys.executable)
    print("[REMOTE] Working directory:", Path.cwd())
    print("[REMOTE] Result directory:", RAW_DIR.resolve())
    print("[REMOTE] Experiment ID:", EXPERIMENT_ID)
    print("[REMOTE] Channel:", CHANNEL, "USB port:", USB_PORT)
    ensure_biologic_host_ready()
    techniques = [build_technique(spec) for spec in TECHNIQUES]
    run_experiment(CHANNEL, USB_PORT, techniques, RAW_DIR, EXPERIMENT_ID)
    print("[REMOTE] Experiment complete. Matching files:")
    for path in sorted(RAW_DIR.glob(EXPERIMENT_ID + "*")):
        print("[REMOTE_RESULT]", path.name)
except Exception:
    traceback.print_exc()
    raise
"""


@dataclass
class BiologicBatchRunner:
    biologic_params: dict[str, Any]
    ssh: Any = None
    home_dir: str | None = None
    remote_work_dir: str | None = None

    def connect(self) -> None:
        import paramiko

        key_file = _auto_key_file(self.biologic_params.get("key_file"))
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(
            self.biologic_params["host"],
            port=int(self.biologic_params.get("ssh_port", 22)),
            username=self.biologic_params["username"],
            key_filename=key_file,
            timeout=10,
        )
        code, home, err = _run_remote(self.ssh, 'cmd.exe /C "echo %USERPROFILE%"', timeout=5)
        home = home.replace("\\", "/")
        if code != 0 or not home or home == "%USERPROFILE%":
            raise RuntimeError(f"Could not resolve remote Windows home directory: {err}")
        self.home_dir = home
        self.remote_work_dir = _remote_abs(self.biologic_params.get("remote_work_dir", "AC_OTflex_remote"), home)
        code, _, err = _run_remote(
            self.ssh,
            f'cmd.exe /C if not exist "{_win_path(self.remote_work_dir)}" mkdir "{_win_path(self.remote_work_dir)}"',
            timeout=10,
        )
        if code != 0:
            raise RuntimeError(f"Could not create remote work dir {self.remote_work_dir}: {err}")
        print(f"[OK] SSH connected to {self.biologic_params['username']}@{self.biologic_params['host']}")

    def close(self) -> None:
        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None

    def run_experiment(
        self,
        plan: dict[str, Any],
        exp: dict[str, Any],
        local_batch_dir: Path,
    ) -> dict[str, Any]:
        if self.ssh is None or self.remote_work_dir is None:
            raise RuntimeError("BiologicBatchRunner is not connected")

        batch_id = plan.get("batch_id") or datetime.now().strftime("%Y%m%d_%H%M%S")
        well = exp["well"]
        bio = merged_biologic_params(plan, exp)
        experiment_id = bio["experiment_id"]
        date_label = datetime.now().strftime("%b%d").lower()
        remote_results_cfg = self.biologic_params.get("remote_results_dir")
        if remote_results_cfg is None:
            remote_results_dir = posixpath.join(self.remote_work_dir, "raw_electrochemical_data", f"{date_label}_expt")
        else:
            remote_results_dir = _remote_abs(
                str(remote_results_cfg).format(
                    batch_id=batch_id,
                    well=well,
                    experiment_id=experiment_id,
                    date=date_label,
                ),
                self.remote_work_dir,
            )

        code, _, err = _run_remote(
            self.ssh,
            f'cmd.exe /C if not exist "{_win_path(remote_results_dir)}" mkdir "{_win_path(remote_results_dir)}"',
            timeout=10,
        )
        if code != 0:
            raise RuntimeError(f"Could not create remote result dir {remote_results_dir}: {err}")

        script_path = posixpath.join(self.remote_work_dir, f"run_{experiment_id}.py")
        runner_path = posixpath.join(self.remote_work_dir, f"run_{experiment_id}.bat")
        py = self.biologic_params.get("python_executable", "python")
        conda_env = self.biologic_params.get("conda_env", "ot2_workflow")
        remote_script = _remote_script(
            channel=int(bio.get("channel", self.biologic_params.get("channel", 4))),
            usb_port=bio.get("usb_port", self.biologic_params.get("device_address", "USB0")),
            experiment_id=experiment_id,
            remote_results_dir=remote_results_dir,
            biologic_params=self.biologic_params,
            techniques=bio["techniques"],
        )
        runner_script = f"""@echo off
cd /d "{_win_path(self.remote_work_dir)}"
call conda activate {conda_env}
if errorlevel 1 exit /b %errorlevel%
{py} "%~dp0{Path(script_path).name}"
"""

        sftp = self.ssh.open_sftp()
        try:
            with sftp.file(script_path, "w") as f:
                f.write(remote_script)
            with sftp.file(runner_path, "w") as f:
                f.write(runner_script)
        finally:
            sftp.close()

        cmd = f'cmd.exe /C "{_win_path(runner_path)}"'
        _stdin, stdout, stderr = self.ssh.exec_command(cmd, timeout=int(bio.get("timeout_s", 900)))
        output_lines = [line.rstrip() for line in stdout]
        error_lines = [line.rstrip() for line in stderr if line.rstrip()]
        exit_code = stdout.channel.recv_exit_status()

        local_dir = Path(local_batch_dir) / well
        local_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []
        sftp = self.ssh.open_sftp()
        try:
            names = sorted(name for name in sftp.listdir(remote_results_dir) if name.startswith(experiment_id))
            for name in names:
                remote_path = posixpath.join(remote_results_dir, name)
                local_path = local_dir / name
                sftp.get(remote_path, str(local_path))
                downloaded.append(local_path)
        finally:
            sftp.close()

        log_file = local_dir / "experiment_log.txt"
        log_file.write_text(
            "\n".join(
                [
                    "=== Biologic Batch Experiment Log ===",
                    f"batch_id: {batch_id}",
                    f"well: {well}",
                    f"experiment_id: {experiment_id}",
                    f"remote_results_dir: {remote_results_dir}",
                    "",
                    "=== STDOUT ===",
                    *output_lines,
                    "",
                    "=== STDERR ===",
                    *error_lines,
                ]
            ),
            encoding="utf-8",
        )

        combined_csv = None
        csv_files = [path for path in downloaded if path.suffix.lower() == ".csv"]
        if csv_files:
            frames = []
            for path in csv_files:
                frame = pd.read_csv(path)
                frame.insert(0, "source_file", path.name)
                frame.insert(0, "well", well)
                frame.insert(0, "experiment_id", experiment_id)
                frames.append(frame)
            combined = pd.concat(frames, ignore_index=True, sort=False)
            combined_csv = local_dir / "experiment_data.csv"
            combined.to_csv(combined_csv, index=False)

        result = {
            "batch_id": batch_id,
            "well": well,
            "experiment_id": experiment_id,
            "remote_exit_code": exit_code,
            "remote_results_dir": remote_results_dir,
            "downloaded_files": [path.name for path in downloaded],
            "local_dir": str(local_dir),
            "combined_csv": combined_csv.name if combined_csv else None,
            "status": "ok" if exit_code == 0 and downloaded else "error",
            "error": "\n".join(error_lines),
        }
        with open(local_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(result | {"experiment": exp, "biologic": bio}, f, indent=2)

        try:
            _run_remote(
                self.ssh,
                f'cmd.exe /C del /Q "{_win_path(script_path)}" "{_win_path(runner_path)}"',
                timeout=5,
            )
        except Exception:
            pass

        if exit_code != 0:
            raise RuntimeError(f"{well}: remote Biologic experiment failed with exit code {exit_code}")
        if not downloaded:
            raise RuntimeError(f"{well}: no files beginning with {experiment_id!r} were downloaded")
        return result


def write_batch_summary(results: list[dict[str, Any]], local_batch_dir: Path) -> pd.DataFrame:
    local_batch_dir = Path(local_batch_dir)
    local_batch_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results)
    df.to_csv(local_batch_dir / "batch_summary.csv", index=False)
    with open(local_batch_dir / "batch_summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return df
