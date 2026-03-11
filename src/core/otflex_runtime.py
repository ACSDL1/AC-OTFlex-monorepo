#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
otflex_runtime.py

Runtime wrapper for OT-Flex + MQTT-controlled IoT peripherals.
Implements the required entrypoints used by adapters/otflex_adapter.py:
  - otflex_connect(cfg)
  - otflex_disconnect()
  - otflex_transfer(params)
  - otflex_gripper(params)
  - otflex_wash(params)
  - otflex_furnace(params)
  - otflex_pump(params)
  - otflex_electrode(params)
  - otflex_reactor(params)
  - otflex_echem_measure(params)

This module intentionally does NOT import OTFLEX_WORKFLOW_Iliya.py to avoid
executing its top-level code during import. Instead it talks to
opentronsClient and to IoT devices through the MQTT adapter layer.
"""

from __future__ import annotations
import os
import sys
import time
from typing import Any, Dict, Optional
from pathlib import Path
import importlib.util

# Add root directory to Python path for imports
_root_dir = Path(__file__).parent.parent.parent
if str(_root_dir) not in sys.path:
    sys.path.append(str(_root_dir))

# Also add src directory for utils import
_src_dir = Path(__file__).parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

try:
    from utils.tip_tracker import TipTracker, id_to_well
except ImportError:
    try:
        # Fallback: try with src prefix
        from src.utils.tip_tracker import TipTracker, id_to_well
    except ImportError:
        # Create minimal stubs if module cannot be imported
        class TipTracker:
            def __init__(self, *args, **kwargs):
                pass
        def id_to_well(well_id):
            return "A1"

# Optional deps (prefer project client, then external package if compatible)
try:
    from src.core.opentrons import opentronsClient  # type: ignore
except Exception:
    try:
        from opentrons import opentronsClient  # type: ignore
    except Exception:
        opentronsClient = None  # type: ignore

try:
    from src.adapters.iot_mqtt import FurnaceMQTT, HeatMQTT, PumpMQTT, ReactorMQTT, UltraMQTT  # type: ignore
except Exception:
    from adapters.iot_mqtt import FurnaceMQTT, HeatMQTT, PumpMQTT, ReactorMQTT, UltraMQTT  # type: ignore


class _OTFlexRuntime:
    def __init__(self):
        self.oc = None
        self.deck = {}
        self.pipettes = {}
        self.mqtt_pumps: Optional[PumpMQTT] = None
        self.mqtt_ultra: Optional[UltraMQTT] = None
        self.mqtt_heat: Optional[HeatMQTT] = None
        self.mqtt_reactor: Optional[ReactorMQTT] = None
        self.mqtt_furnace: Optional[FurnaceMQTT] = None
        self.lw_ids: Dict[str, str] = {}
        self.root_dir = Path.cwd()
        self.tip_tracker: Optional[TipTracker] = None
        # Preserve gripper slot poses from devices.otflex.deck.gripper_slots
        self.gripper_slots: Dict[str, Any] = {}

    # ---------- lifecycle ----------
    def connect(self, cfg: Dict[str, Any]):
        # Prepare deck
        deck_norm = (cfg or {}).get("deck_norm", {})
        slots = deck_norm.get("slots", {}) or ((cfg or {}).get("deck", {}) or {}).get("slots", {})
        self.deck = {k: v for k, v in slots.items() if v}
        # Also preserve gripper slot poses for gripper moves
        try:
            self.gripper_slots = (((cfg or {}).get("deck", {}) or {}).get("gripper_slots", {})) or {}
        except Exception:
            self.gripper_slots = {}
        rd = (cfg or {}).get("_root_dir")
        if rd:
            try:
                self.root_dir = Path(rd)
            except Exception:
                pass

        # Connect MQTT IoT adapters if provided
        mqtt_cfg = (cfg or {}).get("mqtt") or {}
        topics = mqtt_cfg.get("topics", {}) or {}
        if mqtt_cfg and topics:
            common = dict(
                broker=mqtt_cfg.get("broker", "localhost"),
                port=int(mqtt_cfg.get("port", 1883)),
                username=mqtt_cfg.get("username"),
                password=mqtt_cfg.get("password"),
            )
            try:
                if topics.get("pumps"):
                    self.mqtt_pumps = PumpMQTT(**common, base_topic=topics["pumps"], client_id="otflex-pumps")
                    self.mqtt_pumps.ensure_connected()
                if topics.get("ultra"):
                    self.mqtt_ultra = UltraMQTT(**common, base_topic=topics["ultra"], client_id="otflex-ultra")
                    self.mqtt_ultra.ensure_connected()
                if topics.get("heat"):
                    self.mqtt_heat = HeatMQTT(**common, base_topic=topics["heat"], client_id="otflex-heat")
                    self.mqtt_heat.ensure_connected()
                if topics.get("reactor"):
                    self.mqtt_reactor = ReactorMQTT(**common, base_topic=topics["reactor"], client_id="otflex-reactor")
                    self.mqtt_reactor.ensure_connected()
                if topics.get("furnace"):
                    self.mqtt_furnace = FurnaceMQTT(**common, base_topic=topics["furnace"], client_id="otflex-furnace")
                    self.mqtt_furnace.ensure_connected()
            except Exception as e:
                print(f"[OTFlex][WARN] MQTT IoT adapter connection failed: {e}")

        # Connect Opentrons (allow overriding opentrons.py via cfg['opentrons_path'])
        ip = (cfg or {}).get("controller_ip") or os.environ.get("OT_IP") or "127.0.0.1"
        oc_ctor = None
        used_file = None

        ext_path = (cfg or {}).get("opentrons_path")
        if isinstance(ext_path, str) and ext_path:
            try:
                p = Path(ext_path)
                if p.exists():
                    spec = importlib.util.spec_from_file_location("opentrons_ext", str(p))
                    mod = importlib.util.module_from_spec(spec)
                    assert spec and spec.loader
                    spec.loader.exec_module(mod)  # type: ignore
                    if hasattr(mod, 'opentronsClient'):
                        oc_ctor = getattr(mod, 'opentronsClient')
                        used_file = str(p)
                        print(f"[OTFlex][INFO] Using external opentrons client from: {used_file}")
                else:
                    print(f"[OTFlex][WARN] opentrons_path not found: {ext_path}")
            except Exception as e:
                print(f"[OTFlex][WARN] Failed loading opentrons_path {ext_path}: {e}")

        if oc_ctor is None:
            if opentronsClient is None:
                print("[OTFlex][WARN] opentronsClient not available; Flex disabled (dry)")
                return
            oc_ctor = opentronsClient
            try:
                mod_name = oc_ctor.__module__
                used_file = sys.modules.get(mod_name).__file__ if sys.modules.get(mod_name) else None
            except Exception:
                used_file = None

        self.oc = oc_ctor(strRobotIP=ip, strRobot='flex')
        print(f"[OTFlex][REAL] OpenTrons connected to {ip} using module: {used_file}")

        # Load pipettes if declared
        pips = ((cfg or {}).get("deck", {}) or {}).get("pipettes", {}) or {}
        for side, rec in pips.items():
            model = rec.get("model")
            mount = rec.get("mount", side)
            if model:
                try:
                    self.oc.loadPipette(strPipetteName=model, strMount=mount)
                except Exception as e:
                    print(f"[OTFlex][WARN] loadPipette failed: {model}@{mount}: {e}")

        # Load labware on deck (standard models only; custom requires file path)
        for sk, rec in self.deck.items():
            slot = rec.get("slot_label") or sk  # if cfg already uses A1..D3 keys
            model = rec.get("labware")
            name = rec.get('name')
            if not model:
                continue
            print(f"[OTFlex][DEBUG] Loading labware: slot={slot}, model={model}, name={name}")
            try:
                if model.startswith("opentrons_") or model.startswith("corning_") or model.startswith("nest_"):
                    lid = self.oc.loadLabware(slot, model)
                    # store both name and model for lookup
                    if name:
                        self.lw_ids[name] = lid
                        print(f"[OTFlex][DEBUG] Registered labware name '{name}' -> ID '{lid}'")
                    self.lw_ids[model] = lid
                    print(f"[OTFlex][DEBUG] Registered labware model '{model}' -> ID '{lid}'")
                else:
                    # Try custom labware JSON if provided as absolute/relative path
                    path_hint = rec.get("file") or model
                    if isinstance(path_hint, str) and path_hint.endswith('.json'):
                        norm_hint = path_hint.replace('\\', '/')
                        hint_path = Path(norm_hint)
                        if not hint_path.is_absolute():
                            candidates = [
                                (self.root_dir / hint_path),
                                (Path.cwd() / hint_path),
                            ]
                            if hint_path.parts and hint_path.parts[0].lower() == 'labware':
                                candidates.append(self.root_dir.parent / 'labware_definitions' / hint_path.name)
                                candidates.append(Path.cwd() / 'data' / 'labware_definitions' / hint_path.name)

                            chosen = None
                            for cand in candidates:
                                if cand.exists():
                                    chosen = cand
                                    break
                            resolved_path = str(chosen) if chosen else norm_hint
                        else:
                            resolved_path = str(hint_path)

                        lid = self.oc.loadCustomLabwareFromFile(slot, resolved_path)
                        if name:
                            self.lw_ids[name] = lid
                            print(f"[OTFlex][DEBUG] Registered custom labware name '{name}' -> ID '{lid}'")
                        self.lw_ids[model] = lid
                        print(f"[OTFlex][DEBUG] Registered custom labware model '{model}' -> ID '{lid}'")
                    else:
                        print(f"[OTFlex][INFO] Skip non-standard labware at {slot}: {model} (no JSON file path)")
            except Exception as e:
                print(f"[OTFlex][WARN] load labware failed at {slot}: {model}: {e}")

        # Tip tracker file
        tip_file = (cfg or {}).get('tip_tracker_file')
        if not tip_file:
            tip_file = str(self.root_dir / '.state' / 'tips_1000ul.json')
        try:
            self.tip_tracker = TipTracker(Path(tip_file))
        except Exception as e:
            print('[OTFlex][WARN] TipTracker init failed:', e)

    def disconnect(self):
        if self.oc:
            try:
                self.oc.homeRobot()
            except Exception:
                pass
        for dev in (self.mqtt_pumps, self.mqtt_ultra, self.mqtt_heat, self.mqtt_reactor, self.mqtt_furnace):
            if dev is not None:
                try:
                    dev.disconnect()
                except Exception:
                    pass
        self.oc = None

    # ---------- high-level OT actions ----------
    def transfer(self, p: Dict[str, Any]):
        if not self.oc:
            print("[OTFlex][DRY] transfer:", p)
            return
        src = p
        pip = p.get('pipette') or 'p1000_single_flex'
        move_speed = float(p.get('move_speed') or 100)
        safe_transit_height = float(p.get('safe_height', 20.0))  # Configurable safe height

        print(f"[OTFlex][DEBUG] Raw transfer params: {p}")
        print(f"[OTFlex][DEBUG] Using pipette: {pip}")

        def mv(lw, well, dX=0, dY=0, dZ=0):
            # Resolve labware name to ID
            lw_id = self.lw_ids.get(lw, lw)  # fallback to original name if not found

            self.oc.moveToWell(strLabwareName=lw_id, strWellName=well, strPipetteName=pip,
                               strOffsetStart='top', fltOffsetX=dX, fltOffsetY=dY, fltOffsetZ=dZ, intSpeed=int(move_speed))

        def asp(lw, well, vol, dX=0, dY=0, dZ=0):
            # Resolve labware name to ID
            lw_id = self.lw_ids.get(lw, lw)  # fallback to original name if not found
            self.oc.aspirate(strLabwareName=lw_id, strWellName=well, strPipetteName=pip,
                             intVolume=int(vol), strOffsetStart='bottom', fltOffsetX=dX, fltOffsetY=dY, fltOffsetZ=dZ)

        def dsp(lw, well, vol, dX=0, dY=0, dZ=0):
            # Resolve labware name to ID
            lw_id = self.lw_ids.get(lw, lw)  # fallback to original name if not found
            self.oc.dispense(strLabwareName=lw_id, strWellName=well, strPipetteName=pip,
                             intVolume=int(vol), strOffsetStart='bottom', fltOffsetX=dX, fltOffsetY=dY, fltOffsetZ=dZ)

        # Handle both old and new parameter formats
        from_lw = p.get('from_labware') or p.get('from', {}).get('labware')
        to_lw = p.get('to_labware') or p.get('to', {}).get('labware')
        from_well = p.get('from_well') or p.get('from', {}).get('well') or 'A1'
        to_well = p.get('to_well') or p.get('to', {}).get('well') or 'A1'
        vol = int(p.get('volume_uL') or 0)
        fdX, fdY, fdZ = p.get('from_dX', 0), p.get('from_dY', 0), p.get('from_dZ', 2)
        tdX, tdY, tdZ = p.get('to_dX', 0), p.get('to_dY', 0), p.get('to_dZ', 20)

        print(f"[OTFlex][DEBUG] Transfer params: from_lw={from_lw}, to_lw={to_lw}")
        print(f"[OTFlex][DEBUG] Available labware IDs: {list(self.lw_ids.keys())}")
        print(f"[OTFlex][DEBUG] Resolving '{from_lw}' -> '{self.lw_ids.get(from_lw, 'NOT_FOUND')}'")
        print(f"[OTFlex][DEBUG] Resolving '{to_lw}' -> '{self.lw_ids.get(to_lw, 'NOT_FOUND')}')")

        # autopick tip if configured
        if self.tip_tracker and p.get('autopick_tip', True):
            tiprack_name = p.get('tiprack') or 'tiprack_1000ul'
            tiprack_id = self.lw_ids.get(tiprack_name) or self.lw_ids.get('opentrons_flex_96_tiprack_1000ul')
            if tiprack_id:
                try:
                    _, tip_well = self.tip_tracker.next_tip()
                    self.oc.moveToWell(strLabwareName=tiprack_id, strWellName=tip_well, strPipetteName=pip,
                                       strOffsetStart='top', fltOffsetX=0, fltOffsetY=0, fltOffsetZ=0, intSpeed=int(move_speed))
                    self.oc.pickUpTip(strLabwareName=tiprack_id, strPipetteName=pip, strWellName=tip_well, fltOffsetY=0)
                except Exception as e:
                    print('[OTFlex][WARN] pick tip failed:', e)

        # naive sequence
        to_well_list = to_well if isinstance(to_well, list) else [to_well]
        repeats = len(to_well_list)
        for i in range(repeats):
            print(f"[OTFlex] transfer cycle {i+1}/{repeats}, moving to {from_lw}.{from_well}")
            # Move to source with safe transit height
            mv(from_lw, from_well, fdX, fdY, 0)
            # Aspirate at specified depth
            asp(from_lw, from_well, vol, fdX, fdY, fdZ)
            # Move to destination with safe transit height
            mv(to_lw, to_well_list[i], tdX, tdY, 0)
            # Dispense at specified depth
            dsp(to_lw, to_well_list[i], vol, tdX, tdY, tdZ)

        # drop tip to trash if available
        if p.get('autopick_tip', True):

            trash_id = self.lw_ids.get('trash') or self.lw_ids.get('opentrons_flex_trash')

            print('[OTFlex]trash id:', trash_id)
            try:
                # Since trash registration is unreliable, just use disposal location
                print('[OTFlex] Dropping tip using disposal location (trash registration failed)')
                self.oc.dropTip(strPipetteName=pip, boolDropInDisposal=True)
            except Exception as e:
                print(f'[OTFlex][WARN] tip drop failed: {e}')

    def toolTransfer(self, p: Dict[str, Any]):
        if not self.oc:
            print("[OTFlex][DRY] electrode transfer:", p)
            return
        pip = p.get('pipette') or 'p1000_single_flex'

        print(f"[OTFlex][DEBUG] Raw transfer params: {p}")
        print(f"[OTFlex][DEBUG] Using pipette: {pip}")

        # Handle both old and new parameter formats
        from_lw = p.get('from_labware') or p.get('from', {}).get('labware')
        to_lw = p.get('to_labware') or p.get('to', {}).get('labware')
        from_well = p.get('from_well') or p.get('from', {}).get('well') or 'A1'
        to_well = p.get('to_well') or p.get('to', {}).get('well') or 'A1'

        print(f"[OTFlex][DEBUG] Transfer params: from_lw={from_lw}, to_lw={to_lw}")
        print(f"[OTFlex][DEBUG] Available labware IDs: {list(self.lw_ids.keys())}")
        print(f"[OTFlex][DEBUG] Resolving '{from_lw}' -> '{self.lw_ids.get(from_lw, 'NOT_FOUND')}'")
        print(f"[OTFlex][DEBUG] Resolving '{to_lw}' -> '{self.lw_ids.get(to_lw, 'NOT_FOUND')}')")

        from_lw_id = self.lw_ids.get(from_lw, from_lw)
        to_lw_id = self.lw_ids.get(to_lw, to_lw)

        # Geometry controls (all configurable from workflow JSON)
        pickup_offset_x = float(p.get('from_dX', p.get('from', {}).get('offsetX', 0.5)))
        pickup_offset_y = float(p.get('from_dY', p.get('from', {}).get('offsetY', 1.0)))
        pickup_offset_z = float(p.get('from_dZ', p.get('from', {}).get('offsetZ', 0.0)))

        target_offset_x = float(p.get('to_dX', p.get('to', {}).get('offsetX', -3.5)))
        target_offset_y = float(p.get('to_dY', p.get('to', {}).get('offsetY', -34.5)))
        target_offset_z = float(p.get('to_dZ', p.get('to', {}).get('offsetZ', 0.0)))

        approach_offset_z = float(p.get('approach_offset_z', 0.0))
        insert_pause_s = float(p.get('insert_pause_s', 2.0))
        return_dz = float(p.get('return_dZ', 12.0))

        print(f"[OTFlex] Picking up electrode tip from {from_lw_id}.{from_well}")
        self.oc.pickUpTip(
            strLabwareName=from_lw_id,
            strPipetteName=pip,
            strWellName=from_well,
            fltOffsetX=pickup_offset_x,
            fltOffsetY=pickup_offset_y,
            fltOffsetZ=pickup_offset_z
        )

        print(f"[OTFlex] Moving electrode to {to_lw_id}.{to_well} (approach)")
        self.oc.moveToWell(
            strLabwareName=to_lw_id,
            strWellName=to_well,
            strPipetteName=pip,
            strOffsetStart='top',
            fltOffsetX=target_offset_x,
            fltOffsetY=target_offset_y,
            fltOffsetZ=approach_offset_z,
            intSpeed=50
        )

        print(f"[OTFlex] Moving electrode to measurement position")
        self.oc.moveToWell(
            strLabwareName=to_lw_id,
            strWellName=to_well,
            strPipetteName=pip,
            strOffsetStart='bottom',
            fltOffsetX=target_offset_x,
            fltOffsetY=target_offset_y,
            fltOffsetZ=target_offset_z,
            intSpeed=50
        )

        import time
        time.sleep(insert_pause_s)
        
        # Retract electrode (back to high position)
        print(f"[OTFlex] Retracting electrode")
        self.oc.moveToWell(
            strLabwareName=to_lw_id,
            strWellName=to_well,
            strPipetteName=pip,
            strOffsetStart='top',
            fltOffsetX=target_offset_x,
            fltOffsetY=target_offset_y,
            fltOffsetZ=approach_offset_z,
            intSpeed=50
        )
        
        # Return to electrode station
        print(f"[OTFlex] Returning electrode tip to station")
        self.oc.moveToWell(
            strLabwareName=from_lw_id,
            strWellName=from_well,
            strPipetteName=pip,
            strOffsetStart='top',
            fltOffsetX=pickup_offset_x,
            fltOffsetY=pickup_offset_y,
            fltOffsetZ=10,
            intSpeed=100
        )
        
        # Drop electrode tip back to station
        print(f"[OTFlex] Dropping electrode tip back to station")
        self.oc.dropTip(
            strPipetteName=pip,
            boolDropInDisposal=False,
            strLabwareName=from_lw_id,
            strWellName=from_well,
            strOffsetStart="bottom",
            fltOffsetX=pickup_offset_x,
            fltOffsetY=pickup_offset_y,
            fltOffsetZ=return_dz
        )
        
        print(f"[OTFlex] Electrode tool transfer completed")

    def flushWell(self, p: Dict[str, Any]):
        """Combined electrode positioning and MQTT pump flushing"""
        if not self.oc:
            print("[OTFlex][DRY] flush well:", p)
            return

        pip = p.get('pipette', 'p1000_single_flex')

        # Handle both normalized (from adapter) and direct parameter formats
        if 'from_labware' in p:
            # Normalized format from adapter
            from_lw = p.get('from_labware')
            from_well = p.get('from_well', 'A1')
            to_lw = p.get('to_labware')
            to_well = p.get('to_well', 'A1')

            pickup_offset_x = float(p.get('from_dX', 0.5))
            pickup_offset_y = float(p.get('from_dY', 1.0))
            pickup_offset_z = float(p.get('from_dZ', 0.0))

            target_offset_x = float(p.get('to_dX', -3.5))
            target_offset_y = float(p.get('to_dY', -34.5))
            target_offset_z = float(p.get('to_dZ', 0.0))
        else:
            # Direct nested format
            from_obj = p.get('from', {})
            to_obj = p.get('to', {})

            from_lw = from_obj.get('labware')
            from_well = from_obj.get('well', 'A1')
            to_lw = to_obj.get('labware')
            to_well = to_obj.get('well', 'A1')

            pickup_offset_x = float(from_obj.get('offsetX', 0.5))
            pickup_offset_y = float(from_obj.get('offsetY', 1.0))
            pickup_offset_z = float(from_obj.get('offsetZ', 0.0))

            target_offset_x = float(to_obj.get('offsetX', -3.5))
            target_offset_y = float(to_obj.get('offsetY', -34.5))
            target_offset_z = float(to_obj.get('offsetZ', 0.0))

        # Pump-cycle parameters (defaults keep previous behavior if not provided)
        time_ms = float(p.get('time_ms', 10.0))
        repeats = int(p.get('repeats', 1))
        in_pump_id = int(p.get('in_pump_id', 2))
        out_pump_id = int(p.get('out_pump_id', 0))
        purge_ms = float(p.get('purge_ms', 1000))
        return_dz = float(p.get('return_dZ', 12.0))

        # Validate required parameters
        if not from_lw or not to_lw:
            raise ValueError(f"Missing required labware: from_lw={from_lw}, to_lw={to_lw}")

        # Handle well arrays for multi-well operations
        to_wells = to_well if isinstance(to_well, list) else [to_well]

        print(f"[OTFlex][DEBUG] Flush well operation")
        print(f"[OTFlex][DEBUG] From: {from_lw}.{from_well}")
        print(f"[OTFlex][DEBUG] To: {to_lw}.{to_wells}")
        print(f"[OTFlex][DEBUG] Repeats: {repeats} times, duration: {time_ms}ms")
        print(f"[OTFlex][DEBUG] Pump cycle: in={in_pump_id} for {time_ms}ms, out={out_pump_id} for {time_ms}ms")

        from_lw_id = self.lw_ids.get(from_lw, from_lw)
        to_lw_id = self.lw_ids.get(to_lw, to_lw)

        # Step 1: Pick up electrode
        print(f"[OTFlex] Picking up electrode from {from_lw_id}.{from_well}")
        self.oc.pickUpTip(
            strLabwareName=from_lw_id,
            strPipetteName=pip,
            strWellName=from_well,
            fltOffsetX=pickup_offset_x,
            fltOffsetY=pickup_offset_y,
            fltOffsetZ=pickup_offset_z
        )

        # Step 2-3: Loop through all target wells
        for i, current_well in enumerate(to_wells):
            if i > 0:
                prev_well = to_wells[i - 1]
                print(f"[OTFlex] Lifting from {prev_well} before moving to {current_well}")
                self.oc.moveToWell(
                    strLabwareName=to_lw_id,
                    strWellName=prev_well,
                    strPipetteName=pip,
                    strOffsetStart='top',
                    fltOffsetX=target_offset_x,
                    fltOffsetY=target_offset_y,
                    fltOffsetZ=target_offset_z,
                    intSpeed=50
                )

            print(f"[OTFlex] Moving electrode to flush position {to_lw_id}.{current_well} ({i+1}/{len(to_wells)})")
            self.oc.moveToWell(
                strLabwareName=to_lw_id,
                strWellName=current_well,
                strPipetteName=pip,
                strOffsetStart='bottom',
                fltOffsetX=target_offset_x,
                fltOffsetY=target_offset_y,
                fltOffsetZ=target_offset_z,
                intSpeed=50
            )

            # Run MQTT pump flushing
            print(f"[OTFlex] Starting operation at {current_well} for {time_ms}ms")
            for _ in range(repeats):
                self._run_pump_flush(in_pump_id, time_ms)
                self._run_pump_flush(out_pump_id, time_ms)
                if purge_ms > 0:
                    self._run_pump_flush(out_pump_id, purge_ms)
            print(f"[OTFlex] Completed all pump cycles at {current_well}")

        # Step 4: Retract electrode from last well
        last_well = to_wells[-1]
        print(f"[OTFlex] Retracting electrode from {last_well}")
        self.oc.moveToWell(
            strLabwareName=to_lw_id,
            strWellName=last_well,
            strPipetteName=pip,
            strOffsetStart='top',
            fltOffsetX=target_offset_x,
            fltOffsetY=target_offset_y,
            fltOffsetZ=target_offset_z,
            intSpeed=50
        )

        # Step 5: Conditionally return electrode
        print(f"[OTFlex] Returning electrode to station")
        self.oc.moveToWell(
            strLabwareName=from_lw_id,
            strWellName=from_well,
            strPipetteName=pip,
            strOffsetStart='top',
            fltOffsetX=pickup_offset_x,
            fltOffsetY=pickup_offset_y,
            fltOffsetZ=10,
            intSpeed=100
        )

        self.oc.dropTip(
            strPipetteName=pip,
            boolDropInDisposal=False,
            strLabwareName=from_lw_id,
            strWellName=from_well,
            strOffsetStart="bottom",
            fltOffsetX=pickup_offset_x,
            fltOffsetY=pickup_offset_y,
            fltOffsetZ=return_dz
        )

        if bool(p.get('home_after', False)):
                    try:
                        self.oc.homeRobot()
                    except Exception:
                        pass

        print(f"[OTFlex] Flush well operation completed with electrode return")


    def _run_pump_flush(self, pump_id, duration):
        """Run pump flushing operation using MQTT-backed otflex_pump helper."""
        try:
            print(f"[OTFlex] Activating MQTT pump channel: {pump_id}")

            # Create pump parameters for the existing otflex_pump function
            pump_params = {
                "pump_id": pump_id,
                "time_ms": duration
            }

            print(f"[OTFlex] Calling otflex_pump with params: {pump_params}")

            # Use the existing otflex_pump function
            otflex_pump(pump_params)

            # MQTT timed ON publishes immediately; explicitly block so robot
            # stays in the current well until this pump step is complete.
            wait_s = max(0.0, float(duration) / 1000.0)
            if wait_s > 0:
                print(f"[OTFlex] Waiting {wait_s:.3f}s for pump {pump_id} to finish")
                time.sleep(wait_s)

            print(f"[OTFlex] Pump operation completed")

        except Exception as e:
            print(f"[OTFlex] ERROR in pump flush operation: {e}")
            # Continue with simulation
            wait_s = max(0.0, float(duration) / 1000.0)
            time.sleep(wait_s)
            print(f"[OTFlex] Fallback: Simulated {pump_id} for {wait_s:.3f}s")

    def potentExperiment(self, p: Dict[str, Any]):
        """Combined electrode positioning and potentiostat experiment"""
        if not self.oc:
            print("[OTFlex][DRY] potentiostat experiment:", p)
            return

        pip = p.get('pipette', 'p1000_single_flex')

        # Handle both normalized (from adapter) and direct parameter formats
        # Normalized format: from_labware, from_well, from_dX, etc.
        # Direct format: from: {labware, well, offsetX}, to: {labware, well, offsetX}

        if 'from_labware' in p:
            # Normalized format from adapter
            from_lw = p.get('from_labware')
            from_well = p.get('from_well', 'A1')
            to_lw = p.get('to_labware')
            to_well = p.get('to_well', 'A1')

            pickup_offset_x = float(p.get('from_dX', 0.5))
            pickup_offset_y = float(p.get('from_dY', 1.0))
            pickup_offset_z = float(p.get('from_dZ', 0.0))

            target_offset_x = float(p.get('to_dX', -3.5))
            target_offset_y = float(p.get('to_dY', -34.5))
            target_offset_z = float(p.get('to_dZ', 10.0))
        else:
            # Direct nested format
            from_obj = p.get('from', {})
            to_obj = p.get('to', {})

            from_lw = from_obj.get('labware')
            from_well = from_obj.get('well', 'A1')
            to_lw = to_obj.get('labware')
            to_well = to_obj.get('well', 'A1')

            pickup_offset_x = float(from_obj.get('offsetX', 0.5))
            pickup_offset_y = float(from_obj.get('offsetY', 1.0))
            pickup_offset_z = float(from_obj.get('offsetZ', 0.0))

            target_offset_x = float(to_obj.get('offsetX', -3.5))
            target_offset_y = float(to_obj.get('offsetY', -34.5))
            target_offset_z = float(to_obj.get('offsetZ', 10.0))

        # Potentiostat experiment parameters
        potentiostat_configs = p.get('potentiostat_configs', [])
        data_folder = p.get('data_folder', r"C:\Users\sdl1_\OneDrive\Documents\Echem")

        # CV parameters
        cv_params = p.get('cv_params', {
            'min_V': -2.3,
            'max_V': -2.5,
            'cycles': 100,
            'mV_s': 200,
            'step_hz': 1000
        })

        # Validate required parameters
        if not from_lw or not to_lw:
            raise ValueError(f"Missing required labware: from_lw={from_lw}, to_lw={to_lw}")

        if not potentiostat_configs:
            raise ValueError("No potentiostat configurations provided")

        print(f"[OTFlex][DEBUG] Potentiostat CV experiment")
        print(f"[OTFlex][DEBUG] From: {from_lw}.{from_well}")
        print(f"[OTFlex][DEBUG] To: {to_lw}.{to_well}")
        print(f"[OTFlex][DEBUG] Potentiostats: {len(potentiostat_configs)}")

        from_lw_id = self.lw_ids.get(from_lw, from_lw)
        to_lw_id = self.lw_ids.get(to_lw, to_lw)

        # Step 1: Pick up electrode
        print(f"[OTFlex] Picking up electrode from {from_lw_id}.{from_well}")
        self.oc.pickUpTip(
            strLabwareName=from_lw_id,
            strPipetteName=pip,
            strWellName=from_well,
            fltOffsetX=pickup_offset_x,
            fltOffsetY=pickup_offset_y,
            fltOffsetZ=pickup_offset_z
        )

        # Step 2: Move electrode to measurement position
        print(f"[OTFlex] Moving electrode to measurement position {to_lw_id}.{to_well}")
        self.oc.moveToWell(
            strLabwareName=to_lw_id,
            strWellName=to_well,
            strPipetteName=pip,
            strOffsetStart='bottom',
            fltOffsetX=target_offset_x,
            fltOffsetY=target_offset_y,
            fltOffsetZ=target_offset_z,
            intSpeed=50
        )

        # Step 3: Run potentiostat CV experiment
        print(f"[OTFlex] Starting CV experiment with {len(potentiostat_configs)} potentiostats")
        time.sleep(5)
        # self._run_potentiostat_experiment(potentiostat_configs, data_folder, cv_params)

        # Step 4: Retract electrode
        print(f"[OTFlex] Retracting electrode")
        self.oc.moveToWell(
            strLabwareName=to_lw_id,
            strWellName=to_well,
            strPipetteName=pip,
            strOffsetStart='top',
            fltOffsetX=target_offset_x,
            fltOffsetY=target_offset_y,
            fltOffsetZ=target_offset_z,
            intSpeed=50
        )

        # Step 5: Conditionally return electrode
        print(f"[OTFlex] Returning electrode to station")
        self.oc.moveToWell(
            strLabwareName=from_lw_id,
            strWellName=from_well,
            strPipetteName=pip,
            strOffsetStart='top',
            fltOffsetX=pickup_offset_x,
            fltOffsetY=pickup_offset_y,
            fltOffsetZ=10,
            intSpeed=100
        )

        self.oc.dropTip(
            strPipetteName=pip,
            boolDropInDisposal=False,
            strLabwareName=from_lw_id,
            strWellName=from_well,
            strOffsetStart="bottom",
            fltOffsetZ=12
        )
        print(f"[OTFlex] Potentiostat experiment completed with electrode return")

    def _run_potentiostat_experiment(self, configs, data_folder, cv_params):
        """Run the potentiostat CV experiment sequentially"""
        try:
            import time

            print(f"[OTFlex] Starting sequential CV experiment...")
            start_time = time.time()

            # Run each potentiostat sequentially
            for i, config in enumerate(configs):
                print(f"[OTFlex] Running potentiostat {i+1}/{len(configs)}: {config['com_port']}")
                _run_cv_process_standalone(config, data_folder, cv_params)

            end_time = time.time()
            print(f"[OTFlex] Sequential CV completed in {end_time - start_time:.2f} seconds")

        except ImportError as e:
            print(f"[OTFlex] ERROR: Missing potentiostat dependencies: {e}")
            print(f"[OTFlex] Simulating CV experiment...")
            import time
            time.sleep(5)  # Simulate experiment time
            print(f"[OTFlex] Simulated CV experiment completed")
        except Exception as e:
            print(f"[OTFlex] ERROR in potentiostat experiment: {e}")
            raise





    def gripper(self, p: Dict[str, Any]):
        if not self.oc:
            print("[OTFlex][DRY] gripper:", p)
            return
        # Expect params: {action: 'move'|'open'|'close'|'pick_and_place', from_slot, to_slot}
        action = (p.get('action') or 'move').lower()
        # Prefer gripper slots captured during connect();
        # fallback to any provided inline in params.
        gs = (self.gripper_slots or {})
        if not gs and isinstance(p, dict):
            gs = (p.get('gripper_slots') or {})

        def pose_for(slot: Optional[str], key: str) -> Optional[tuple]:
            if not slot:
                return None
            rec = gs.get(slot)
            if not rec:
                return None
            arr = rec.get(key)
            if isinstance(arr, (list, tuple)) and len(arr) >= 3:
                return float(arr[0]), float(arr[1]), float(arr[2])
            return None

        def safe_z(slot: Optional[str]) -> float:
            rec = gs.get(slot or '', {})
            return float(rec.get('safe_z', 150))

        if action == 'open':
            print(f"[OTFlex] Gripper opening: {p}")
            if self.oc:
                try:
                    self.oc.openGripper()
                    print("[OTFlex] Gripper opened successfully")
                except Exception as e:
                    print(f"[OTFlex][WARN] Gripper open failed: {e}")
            return

        if action == 'close':
            print(f"[OTFlex] Gripper closing: {p}")
            if self.oc:
                try:
                    self.oc.closeGripper()
                    print("[OTFlex] Gripper closed successfully")
                except Exception as e:
                    print(f"[OTFlex][WARN] Gripper close failed: {e}")
            return

        # Handle gripper movement
        if action == 'move':
            from_slot = p.get('from_slot')
            to_slot = p.get('to_slot')
            print(f"[OTFlex] Moving gripper from {from_slot} to {to_slot}")

            # Get target position
            # default to move above the target using its 'safe_z' unless override
            # allow 'phase': 'above'|'pick'|'place'
            phase = (p.get('phase') or 'pick').lower()
            if phase == 'above':
                base = pose_for(to_slot, 'pick') or pose_for(to_slot, 'place')
                if base:
                    x, y, _ = base
                    z = safe_z(to_slot)
                    target_pos = (x, y, z)
                else:
                    target_pos = None
            else:
                key = 'place' if phase == 'place' else 'pick'
                target_pos = pose_for(to_slot, key)
            if target_pos:
                x, y, z = target_pos
                print(f"[OTFlex] Target position: x={x}, y={y}, z={z}")
                if self.oc:
                    try:
                        self.oc.moveGripper(x, y, z)
                        print(f"[OTFlex] Gripper moved to {to_slot} successfully")
                    except Exception as e:
                        print(f"[OTFlex][WARN] Gripper move failed: {e}")
                else:
                    print(f"[OTFlex][DRY] Would move gripper to x={x}, y={y}, z={z}")
            else:
                print(f"[OTFlex][WARN] No position found for slot {to_slot}")
            return

        if action in ('pick_and_place', 'sequence'):
            from_slot = p.get('from_slot')
            to_slot = p.get('to_slot')
            print(f"[OTFlex] Pick-and-place from {from_slot} -> {to_slot}")

            pick_pose = pose_for(from_slot, 'pick')
            place_pose = pose_for(to_slot, 'place') or pose_for(to_slot, 'pick') #?
            if not pick_pose or not place_pose:
                print(f"[OTFlex][WARN] Missing pick/place pose for from={from_slot} to={to_slot}")
                return

            fx, fy, fz_pick = pick_pose
            tx, ty, tz_place = place_pose
            fz_above = safe_z(from_slot)
            tz_above = safe_z(to_slot)

            move_speed = float(p.get('move_speed') or 100)

            ensure_open = bool(p.get('ensure_open', True))
            close_after_release = bool(p.get('close_after_release', False))

            try:
                # Move above pickup
                self.oc.moveGripper(float(fx), float(fy), float(fz_above))
                if ensure_open:
                    self.oc.openGripper()
                # Down to pick
                self.oc.moveGripper(float(fx), float(fy), float(fz_pick))
                self.oc.closeGripper()
                # Up
                self.oc.moveGripper(float(fx), float(fy), float(fz_above))
                # Move above place
                self.oc.moveGripper(float(tx), float(ty), float(tz_above))
                # Down to place
                self.oc.moveGripper(float(tx), float(ty), float(tz_place))
                # Release at place depth
                self.oc.openGripper()
                # Up before optional close
                self.oc.moveGripper(float(tx), float(ty), float(tz_above))
                if close_after_release:
                    self.oc.closeGripper()
                # Optional home
                if bool(p.get('home_after', False)):
                    try:
                        self.oc.homeRobot()
                    except Exception:
                        pass
                print("[OTFlex] Pick-and-place sequence completed")
            except Exception as e:
                print(f"[OTFlex][WARN] pick_and_place failed: {e}")
            return

        print(f"[OTFlex][WARN] Unknown gripper action: {action}")
        return

    # ---------- MQTT-backed IoT helpers ----------
    def furnace(self, p: Dict[str, Any]):
        if not self.mqtt_furnace:
            print("[OTFlex][WARN] MQTT furnace not configured; skipping:", p)
            return
        open_ = bool(p.get('open', False))
        dur = p.get('duration_ms')
        if open_:
            self.mqtt_furnace.open(dur)
        else:
            self.mqtt_furnace.close(dur)

    def pump(self, p: Dict[str, Any]):
        if not self.mqtt_pumps:
            print("[OTFlex][WARN] MQTT pumps not configured; skipping:", p)
            return
        pump_id = int(p.get('pump_id', 0))
        if 'time_ms' in p:
            self.mqtt_pumps.on(pump_id, int(p['time_ms']))
        else:
            on = bool(p.get('on', True))
            if on:
                self.mqtt_pumps.on(pump_id)
            else:
                self.mqtt_pumps.off(pump_id)

    def electrode(self, p: Dict[str, Any]):
        print("[OTFlex][WARN] otflex_electrode is not supported in MQTT-only mode; skipping:", p)

    def reactor(self, p: Dict[str, Any]):
        if not self.mqtt_reactor:
            print("[OTFlex][WARN] MQTT reactor not configured; skipping:", p)
            return
        state = (p.get('state') or '').lower()
        if state in ('open','opened','unlock','on'):
            self.mqtt_reactor.forward(p.get('duration_ms'))
        elif state in ('close','closed','lock','off'):
            self.mqtt_reactor.reverse(p.get('duration_ms'))
        else:
            on = bool(p.get('on', True))
            if on:
                self.mqtt_reactor.forward(p.get('duration_ms'))
            else:
                self.mqtt_reactor.reverse(p.get('duration_ms'))

    def wash(self, p: Dict[str, Any]):
        if not self.mqtt_ultra:
            print("[OTFlex][WARN] MQTT ultrasonic not configured; skipping:", p)
            return
        # Example: {"ultrasound": {"relay": 7, "duration_s": 20}}
        us = p.get('ultrasound') or {}
        channel = int(us.get('channel', us.get('relay', 1)))
        if 'duration_s' in us:
            self.mqtt_ultra.on(channel, int(float(us['duration_s']) * 1000))
        elif 'on' in us:
            if bool(us['on']):
                self.mqtt_ultra.on(channel)
            else:
                self.mqtt_ultra.off(channel)

    def echem_measure(self, p: Dict[str, Any]):
        print("[OTFlex][INFO] echem_measure placeholder:", p)


_RT = _OTFlexRuntime()


# ===== Adapter entrypoints =====
def otflex_connect(cfg: dict):
    _RT.connect(cfg or {})


def otflex_disconnect():
    _RT.disconnect()


def otflex_transfer(params: dict):
    _RT.transfer(params or {})


def otflex_toolTransfer(params: dict):
    _RT.toolTransfer(params or {})

def _run_cv_process_standalone(config, data_folder, cv_params):
    """Run a single potentiostat measurement in a separate process"""
    try:
        from pathlib import Path
        from datetime import datetime
        from poten_old import Potentiostat, DAC

        com_port = config["com_port"]
        row = config["row"]
        base = config["file_name"]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path(data_folder) / f"{base}_{ts}"

        print(f"Process {row} - Starting on {com_port}")
        ps = Potentiostat(serial_port=com_port)
        ps.connect()
        ps.write_switch(0)
        ps.write_dac(channels=[DAC.CE_IN, DAC.A_REF, DAC.V_AN], voltages=[0, -5, 0])
        ocp = ps.read_ocp()
        print(f"Process {row} - OCP = {ocp:.3f} V")

        print(f"Process {row} - Starting CV measurement...")
        data = ps.perform_CV(
            min_V=cv_params['min_V'],
            max_V=cv_params['max_V'],
            cycles=cv_params['cycles'],
            mV_s=cv_params['mV_s'],
            step_hz=cv_params['step_hz']
        )

        ps.process_CV(data=data, file_basename=out_path)
        print(f"Process {row} - CV data saved to {out_path}")

    except Exception as e:
        print(f"Process {row} - Error: {e}")
    finally:
        try:
            ps.write_switch(0)
            ps.disconnect()
        except Exception:
            pass
        print(f"Process {row} - Done")

def otflex_potentExperiment(params: dict):
    _RT.potentExperiment(params or {})

def otflex_flushWell(params: dict):
    _RT.flushWell(params or {})

def otflex_gripper(params: dict):
    _RT.gripper(params or {})

def otflex_wash(params: dict):
    _RT.wash(params or {})


def otflex_furnace(params: dict):
    _RT.furnace(params or {})


def otflex_pump(params: dict):
    _RT.pump(params or {})


def otflex_electrode(params: dict):
    _RT.electrode(params or {})


def otflex_reactor(params: dict):
    '''
    {
    "id": "turn_on_reactor",
    "type": "otflexReactor",
    "label": "Turn On Reactor", 
    "params": {
        "state": "on"
    }
    },
    '''
    _RT.reactor(params or {})


def otflex_echem_measure(params: dict):
    _RT.echem_measure(params or {})


