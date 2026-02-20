# adapters/arm_adapter.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
from typing import Dict, Any, Optional
import importlib.util
from pathlib import Path

def _load_module(py_path: Path):
    spec = importlib.util.spec_from_file_location("arm_mod", str(py_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod

class MyxArm:
    def __init__(self, device_cfg: Dict[str, Any], root_dir: Path):
        self.device_cfg = device_cfg or {}
        self.root_dir = root_dir
        # 允许通过 devices.arm.module 指定加载的模块文件（默认 dryrun）
        module_file = self.device_cfg.get("module") or "myxArm_Utils_dryrun.py"
        mod_path = self.root_dir / module_file
        if not mod_path.exists():
            raise FileNotFoundError(f"Arm module not found: {mod_path}")
        self.mod = _load_module(mod_path)
        print(f"[Arm] Loaded module: {mod_path.name}")

    async def connect(self):
        fn = getattr(self.mod, "arm_connect", None)
        if callable(fn):
            await asyncio.to_thread(fn, self.device_cfg)

    async def disconnect(self):
        fn = getattr(self.mod, "arm_disconnect", None)
        if callable(fn):
            await asyncio.to_thread(fn)

    async def move(self, p: Dict[str, Any]):
        """
        期望 p 包含:
          - frame: "world"/"arm_base"/"ot_deck"
          - pose: {x,y,z,rx,ry,rz} 或 {x,y,z,qx,qy,qz,qw}
          - speed, accel, blend, safe_z, tool_offset 等
        """
        fn = getattr(self.mod, "arm_move", None)
        if not callable(fn):
            raise RuntimeError("Please implement arm_move(params) in myxArm_Utils.")
        # 规范化 pose: 允许 list[6] -> {x,y,z,rx,ry,rz}
        pose = p.get("pose")
        if isinstance(pose, list) and len(pose) == 6:
            p = {**p, "pose": {
                "x": float(pose[0]), "y": float(pose[1]), "z": float(pose[2]),
                "rx": float(pose[3]), "ry": float(pose[4]), "rz": float(pose[5])
            }}
        await asyncio.to_thread(fn, p)

    async def gripper(self, p: Dict[str, Any]):
        """
        期望 p 包含:
          - action: "open"/"close"/"hold"
          - width_mm / force
        """
        fn = getattr(self.mod, "arm_gripper", None)
        if not callable(fn):
            raise RuntimeError("Please implement arm_gripper(params) in myxArm_Utils.")
        await asyncio.to_thread(fn, p)

    async def run_sequence(self, p: Dict[str, Any]):
        """
        Run a complete pre-programmed xArm sequence
        Expected params:
        - sequence: "placePlate" / "removePlate" / "full_run"
        """
        fn = getattr(self.mod, "arm_run_sequence", None)
        if not callable(fn):
            raise RuntimeError("Please implement arm_run_sequence(params) in myxArm_Utils.")
        await asyncio.to_thread(fn, p)