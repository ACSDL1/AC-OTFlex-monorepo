# -*- coding: utf-8 -*-
"""
OTFLEX_WORKFLOW_Iliya_dryrun.py
简化版本，用于dry run测试，不依赖opentrons等外部库
"""

# ===== DRY RUN adapter entrypoints =====

def otflex_connect(cfg: dict):
    """DRY RUN: 初始化串口/IP连接、加载labware、复位"""
    print(f"[DRY RUN] OTFlex CONNECT")
    print(f"  Config: {cfg}")
    deck_norm = (cfg or {}).get("deck_norm", {})
    slots = deck_norm.get("slots", {})
    if slots:
        print("  Deck slots (resolved):")
        for sk, rec in slots.items():
            print(f"    slot {sk:>2} -> {rec.get('slot_label')} : {rec.get('labware')} ({rec.get('name','')})")
    print()

def otflex_disconnect():
    """DRY RUN: 断开连接"""
    print(f"[DRY RUN] OTFlex DISCONNECT")
    print()

def otflex_transfer(params: dict):
    """DRY RUN: 液体转移操作"""
    print(f"[DRY RUN] OTFlex TRANSFER")
    print(f"  Params: {params}")
    print()

def otflex_toolTransfer(params: dict):
    """DRY RUN: 工具转移操作"""
    print(f"[DRY RUN] OTFlex TOOL TRANSFER")
    print(f"  Params: {params}")
    print()

def otflex_gripper(params: dict):
    """DRY RUN: 夹爪操作"""
    print(f"[DRY RUN] OTFlex GRIPPER")
    print(f"  Params: {params}")
    print()

def otflex_wash(params: dict):
    """DRY RUN: 清洗操作"""
    print(f"[DRY RUN] OTFlex WASH")
    print(f"  Params: {params}")
    print()

def otflex_furnace(params: dict):
    """DRY RUN: 加热炉操作"""
    print(f"[DRY RUN] OTFlex FURNACE")
    print(f"  Params: {params}")
    print()

def otflex_pump(params: dict):
    """DRY RUN: 泵操作"""
    print(f"[DRY RUN] OTFlex PUMP")
    print(f"  Params: {params}")
    print()

def otflex_electrode(params: dict):
    """DRY RUN: 电极操作"""
    print(f"[DRY RUN] OTFlex ELECTRODE")
    print(f"  Params: {params}")
    print()

def otflex_reactor(params: dict):
    """DRY RUN: 反应器操作"""
    print(f"[DRY RUN] OTFlex REACTOR")
    print(f"  Params: {params}")
    print()

def otflex_echem_measure(params: dict):
    """DRY RUN: 电化学测量"""
    print(f"[DRY RUN] OTFlex ECHEM_MEASURE")
    print(f"  Params: {params}")
    print()
