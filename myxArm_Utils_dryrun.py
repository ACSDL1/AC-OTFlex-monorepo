# -*- coding: utf-8 -*-
"""
myxArm_Utils_dryrun.py
简化版本，用于dry run测试，不依赖xarm等外部库
"""

# ===== DRY RUN adapter entrypoints =====

def arm_connect(cfg: dict):
    """DRY RUN: 连接到机械臂，使能电机，设定默认速度/加速度"""
    print(f"[DRY RUN] ARM CONNECT")
    print(f"  Config: {cfg}")
    print()

def arm_disconnect():
    """DRY RUN: 断开机械臂连接"""
    print(f"[DRY RUN] ARM DISCONNECT")
    print()

def arm_move(params: dict):
    """DRY RUN: 机械臂移动操作"""
    print(f"[DRY RUN] ARM MOVE")
    print(f"  Params: {params}")
    print()

def arm_gripper(params: dict):
    """DRY RUN: 机械臂夹爪操作"""
    print(f"[DRY RUN] ARM GRIPPER")
    print(f"  Params: {params}")
    print()
