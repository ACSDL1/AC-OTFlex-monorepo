#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
arm_runtime.py

Runtime wrapper for UFactory xArm.
Implements the required entrypoints used by adapters/arm_adapter.py:
  - arm_connect(cfg)
  - arm_disconnect()
  - arm_move(params)
  - arm_gripper(params)

This file does not import myxArm_Utils.py to avoid unrelated top-level
execution; it uses xarm.wrapper.XArmAPI directly if available.
"""

from __future__ import annotations
from typing import Any, Dict

try:
    from xarm.wrapper import XArmAPI  # type: ignore
except Exception:
    XArmAPI = None  # type: ignore


class _Arm:
    def __init__(self):
        self.api = None

    def connect(self, cfg: Dict[str, Any]):
        if XArmAPI is None:
            print("[ARM][WARN] xarm not available; dry mode")
            return
        ip = (cfg or {}).get('ip') or '192.168.1.207'
        self.api = XArmAPI(ip)
        self.api.clean_warn(); self.api.clean_error()
        self.api.motion_enable(True)
        self.api.set_mode(0)
        self.api.set_state(0)

    def disconnect(self):
        if not self.api:
            return
        try:
            self.api.motion_enable(False)
        except Exception:
            pass
        self.api = None

    def move(self, p: Dict[str, Any]):
        if not self.api:
            print("[ARM][DRY] move:", p)
            return
        pose = p.get('pose') or {}
        if isinstance(pose, dict):
            x = float(pose.get('x', 0)); y=float(pose.get('y', 0)); z=float(pose.get('z', 0))
            rx=float(pose.get('rx', 0)); ry=float(pose.get('ry', 0)); rz=float(pose.get('rz', 0))
        elif isinstance(pose, (list, tuple)) and len(pose) == 6:
            x,y,z,rx,ry,rz = map(float, pose)
        else:
            print("[ARM][WARN] invalid pose, skip:", pose); return
        speed = float(p.get('speed', 100)); acc=float(p.get('accel', 200)); blend=float(p.get('blend', 0))
        self.api.set_position(x, y, z, rx, ry, rz, speed=speed, mvacc=acc, radius=blend, wait=False)

    def gripper(self, p: Dict[str, Any]):
        if not self.api:
            print("[ARM][DRY] gripper:", p)
            return
        action = p.get('action','close').lower()
        width = int(p.get('width_mm', 30))
        speed = int(p.get('speed', 5000))
        # Assuming integrated gripper; mapping width to position value may differ per setup.
        pos = max(0, min(850, int(width * 10)))
        if action == 'open':
            pos = 850
        elif action == 'close':
            pos = max(0, pos)
        self.api.set_gripper_position(pos, wait=True, speed=speed, auto_enable=True)


_ARM = _Arm()


def arm_connect(cfg: dict):
    _ARM.connect(cfg or {})


def arm_disconnect():
    _ARM.disconnect()


def arm_move(params: dict):
    _ARM.move(params or {})


def arm_gripper(params: dict):
    _ARM.gripper(params or {})

