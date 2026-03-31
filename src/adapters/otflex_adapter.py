# adapters/otflex_adapter.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
from typing import Dict, Any, Optional
import importlib.util
from pathlib import Path

# 动态加载你的原脚本
def _load_module(py_path: Path):
    spec = importlib.util.spec_from_file_location("otflex_mod", str(py_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod

class OTFlex:
    def __init__(self, device_cfg: Dict[str, Any], root_dir: Path):
        self.device_cfg = device_cfg or {}
        self.root_dir = root_dir
        # 允许通过 devices.otflex.module 指定加载的模块文件（默认 dryrun）
        module_file = self.device_cfg.get("module") or "OTFLEX_WORKFLOW_Iliya_dryrun.py"
        
        # Search in multiple locations for flexibility
        search_paths = [
            self.root_dir / module_file,  # Workflow directory (preferred)
            Path(__file__).parent.parent / "core" / module_file,  # src/core/
            Path(__file__).parent.parent / "workflows" / module_file,  # src/workflows/
        ]
        
        # Try to resolve relative imports like "../src/core/module.py"
        if module_file.startswith(".."):
            abs_path = (self.root_dir / module_file).resolve()
            if abs_path.exists():
                search_paths.insert(0, abs_path)
        
        mod_path = None
        for path in search_paths:
            if path.exists():
                mod_path = path
                break
        
        if not mod_path:
            raise FileNotFoundError(
                f"OTFlex module '{module_file}' not found in:\n  " + 
                "\n  ".join(str(p) for p in search_paths)
            )
        
        self.mod = _load_module(mod_path)
        print(f"[OTFlex] Loaded module: {mod_path}")

        # 规范化并缓存甲板布局，便于在 connect() 时核对
        self.deck_norm = self._normalize_deck(self.device_cfg.get("deck", {}))

    # -------- Param normalization helpers --------
    def _norm_num(self, v: Optional[Any], default: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            return float(default)

    def _normalize_transfer(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Canvas JSON 的转移参数规范化为通用键，以便底层真实脚本消费。
        输入示例:
          {
            "from": {"labware": "source_plate", "well": "A1", "offsetX": 0, "offsetY": 0, "offsetZ": 2},
            "to": {"labware": "reactor_plate", "well": "A1", "offsetZ": -2},
            "volume_uL": 100,
            "move_speed": 150,
            "pipette": "flex_1channel_50",
            "tiprack": "tiprack_200ul"
          }
        产出示例（通用）:
          {
            "from_labware": "source_plate", "from_well": "A1",
            "from_dX": 0.0, "from_dY": 0.0, "from_dZ": 2.0,
            "to_labware": "reactor_plate", "to_well": "A1",
            "to_dX": 0.0, "to_dY": 0.0, "to_dZ": -2.0,
            "volume_uL": 100, "move_speed": 150,
            "pipette": "flex_1channel_50", "tiprack": "tiprack_200ul"
          }
        """
        src = p.get("from", {}) or {}
        dst = p.get("to", {}) or {}
        out = {
            "from_labware": src.get("labware"),
            "from_well": src.get("well"),
            "from_dX": self._norm_num(src.get("offsetX", 0)),
            "from_dY": self._norm_num(src.get("offsetY", 0)),
            "from_dZ": self._norm_num(src.get("offsetZ", 0)),
            "to_labware": dst.get("labware"),
            "to_well": dst.get("well"),
            "to_dX": self._norm_num(dst.get("offsetX", 0)),
            "to_dY": self._norm_num(dst.get("offsetY", 0)),
            "to_dZ": self._norm_num(dst.get("offsetZ", 0)),
            "volume_uL": int(p.get("volume_uL", 0) or 0),
            "move_speed": self._norm_num(p.get("move_speed", 100)),
            "pipette": p.get("pipette"),
            "tiprack": p.get("tiprack"),
            "safe_height": float(p.get("safe_height", 20.0)),  # Configurable safe height
        }
        # 便于排查首个位置偏移问题，打印解析后的关键位置信息
        print(
            "[OTFlex] Resolved transfer: "
            f"{out['from_labware']}.{out['from_well']} (dX={out['from_dX']}, dY={out['from_dY']}, dZ={out['from_dZ']}) -> "
            f"{out['to_labware']}.{out['to_well']} (dX={out['to_dX']}, dY={out['to_dY']}, dZ={out['to_dZ']}); "
            f"vol={out['volume_uL']}uL speed={out['move_speed']}"
        )
        return out
    
    def _normalize_toolTransfer(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Canvas JSON 的转移参数规范化为通用键，以便底层真实脚本消费。
        输入示例:
          {
            "from": {"labware": "source_plate", "well": "A1", "offsetX": 0, "offsetY": 0, "offsetZ": 2},
            "to": {"labware": "reactor_plate", "well": "A1", "offsetZ": -2},
            "move_speed": 150,
            "pipette": "flex_1channel_50",
          }
        产出示例（通用）:
          {
            "from_labware": "source_plate", "from_well": "A1",
            "to_labware": "reactor_plate", "to_well": "A1",
            "move_speed": 150,"pipette": "flex_1channel_50"
          }
        """
        src = p.get("from", {}) or {}
        dst = p.get("to", {}) or {}
        out = {
            "from_labware": src.get("labware"),
            "from_well": src.get("well"),
            "from_dX": self._norm_num(src.get("offsetX", 0.5)),
            "from_dY": self._norm_num(src.get("offsetY", 1.0)),
            "from_dZ": self._norm_num(src.get("offsetZ", 0.0)),
            "to_labware": dst.get("labware"),
            "to_well": dst.get("well"),
            "to_dX": self._norm_num(dst.get("offsetX", -3.5)),
            "to_dY": self._norm_num(dst.get("offsetY", -34.5)),
            "to_dZ": self._norm_num(dst.get("offsetZ", 0.0)),
            "move_speed": self._norm_num(p.get("move_speed", 100)),
            "pipette": p.get("pipette"),
            "approach_offset_z": self._norm_num(p.get("approach_offset_z", 0.0)),
            "insert_pause_s": self._norm_num(p.get("insert_pause_s", 2.0)),
            "return_dZ": self._norm_num(p.get("return_dZ", 12.0)),
        }
        # 便于排查首个位置偏移问题，打印解析后的关键位置信息
        print(
            "[OTFlex] Resolved transfer: "
            f"{out['from_labware']}.{out['from_well']} -> "
            f"{out['to_labware']}.{out['to_well']}; "
            f"speed={out['move_speed']}"
        )
        return out

    def _normalize_toolTransfer(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Canvas JSON 的转移参数规范化为通用键，以便底层真实脚本消费。
        输入示例:
          {
            "from": {"labware": "source_plate", "well": "A1", "offsetX": 0, "offsetY": 0, "offsetZ": 2},
            "to": {"labware": "reactor_plate", "well": "A1", "offsetZ": -2},
            "move_speed": 150,
            "pipette": "flex_1channel_50",
          }
        产出示例（通用）:
          {
            "from_labware": "source_plate", "from_well": "A1",
            "to_labware": "reactor_plate", "to_well": "A1",
            "move_speed": 150,"pipette": "flex_1channel_50"
          }
        """
        src = p.get("from", {}) or {}
        dst = p.get("to", {}) or {}
        out = {
            "from_labware": src.get("labware"),
            "from_well": src.get("well"),
            "from_dX": self._norm_num(src.get("offsetX", 0.5)),
            "from_dY": self._norm_num(src.get("offsetY", 1.0)),
            "from_dZ": self._norm_num(src.get("offsetZ", 0.0)),
            "to_labware": dst.get("labware"),
            "to_well": dst.get("well"),
            "to_dX": self._norm_num(dst.get("offsetX", -3.5)),
            "to_dY": self._norm_num(dst.get("offsetY", -34.5)),
            "to_dZ": self._norm_num(dst.get("offsetZ", 0.0)),
            "move_speed": self._norm_num(p.get("move_speed", 100)),
            "pipette": p.get("pipette"),
            "approach_offset_z": self._norm_num(p.get("approach_offset_z", 0.0)),
            "insert_pause_s": self._norm_num(p.get("insert_pause_s", 2.0)),
            "return_dZ": self._norm_num(p.get("return_dZ", 12.0)),
        }
        # 便于排查首个位置偏移问题，打印解析后的关键位置信息
        print(
            "[OTFlex] Resolved transfer: "
            f"{out['from_labware']}.{out['from_well']} -> "
            f"{out['to_labware']}.{out['to_well']}; "
            f"speed={out['move_speed']}"
        )
        return out
    
    def _normalize_potentExperiment(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Canvas JSON 的 potentiostat 实验参数规范化为通用键，以便底层真实脚本消费。
        输入示例:
          {
            "from": {"labware": "electrode_station", "well": "A1", "offsetX": 0.5, "offsetY": 1.0, "offsetZ": 0.0}, 
            "to": {"labware": "actuated_reactor", "well": "A2", "offsetX": -3.5, "offsetY": -34.5, "offsetZ": 0.0},
            "pipette": "p1000_single_flex",
            "data_folder": "C:\\Users\\sdl1_\\OneDrive\\Documents\\Echem",
            "potentiostat_configs": [
              {
                "com_port": "COM10",
                "row": "A",
                "file_name": "A1_mp_np"
              },
              {
                "com_port": "COM12",
                "row": "B",
                "file_name": "B1_mp_np"
              },
              {
                "com_port": "COM11",
                "row": "C",
                "file_name": "C1_mp_np"
              },
              {
                "com_port": "COM7",
                "row": "D",
                "file_name": "D1_mp_np"
              }
            ]
          }
        产出示例（通用）:
          {
            "from_labware": "electrode_station", "from_well": "A1",
            "from_dX": 0.5, "from_dY": 1.0, "from_dZ": 0.0,
            "to_labware": "actuated_reactor", "to_well": "A2",
            "to_dX": -3.5, "to_dY": -34.5, "to_dZ": 0.0,
            "data_folder": "C:\\Users\\sdl1_\\OneDrive\\Documents\\Echem",
            "potentiostat_configs": [
              {
                "com_port": "COM10",
                "row": "A",
                "file_name": "A1_mp_np"
              },
              {
                "com_port": "COM12",
                "row": "B",
                "file_name": "B1_mp_np"
              },
              {
                "com_port": "COM11",
                "row": "C",
                "file_name": "C1_mp_np"
              },
              {
                "com_port": "COM7",
                "row": "D",
                "file_name": "D1_mp_np"
              }
            ]
          }
        """
        src = p.get("from", {}) or {}
        dst = p.get("to", {}) or {}
        out = {
            "from_labware": src.get("labware"),
            "from_well": src.get("well"),
            "from_dX": self._norm_num(src.get("offsetX", 0)),
            "from_dY": self._norm_num(src.get("offsetY", 0)),
            "from_dZ": self._norm_num(src.get("offsetZ", 0)),
            "to_labware": dst.get("labware"),
            "to_well": dst.get("well"),
            "to_dX": self._norm_num(dst.get("offsetX", 0)),
            "to_dY": self._norm_num(dst.get("offsetY", 0)),
            "to_dZ": self._norm_num(dst.get("offsetZ", 0)),
            "pipette": p.get("pipette"),
            "data_folder": p.get("data_folder", r"C:\Users\sdl1_\OneDrive\Documents\Echem"),
            "potentiostat_configs": p.get("potentiostat_configs", []),
        }
        return out

    def _normalize_flushWell(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Canvas JSON 的 flush well 参数规范化为通用键，以便底层真实脚本消费。
        """
        src = p.get("from", {}) or {}
        dst = p.get("to", {}) or {}
        out = {
            "from_labware": src.get("labware"),
            "from_well": src.get("well"),
            "from_dX": self._norm_num(src.get("offsetX", 0)),
            "from_dY": self._norm_num(src.get("offsetY", 0)),
            "from_dZ": self._norm_num(src.get("offsetZ", 0)),
            "to_labware": dst.get("labware"),
            "to_well": dst.get("well"),
            "to_dX": self._norm_num(dst.get("offsetX", 0)),
            "to_dY": self._norm_num(dst.get("offsetY", 0)),
            "to_dZ": self._norm_num(dst.get("offsetZ", 0)),
            "pipette": p.get("pipette"),
            "pump_id": p.get("pump_id"),
            "in_pump_id": p.get("in_pump_id"),
            "out_pump_id": p.get("out_pump_id"),
            "time_ms": p.get("time_ms"),
            "in_time_ms": p.get("in_time_ms"),
            "out_time_ms": p.get("out_time_ms"),
            "repeats": p.get("repeats"),
            "purge_ms": p.get("purge_ms"),
            "return_dZ": self._norm_num(p.get("return_dZ", 12.0)),
            "home_after": p.get("home_after", False),
        }
        return out

    async def connect(self):
        # 可选：在你的脚本里暴露 otflex_connect(cfg)
        fn = getattr(self.mod, "otflex_connect", None)
        if callable(fn):
            # 将规范化后的 deck 信息一并传递，便于底层加载对应 labware 到正确插槽
            dev_cfg = dict(self.device_cfg)
            dev_cfg["deck_norm"] = self.deck_norm
            # 传递工作目录，便于运行期管理状态文件（如 tip tracker）
            dev_cfg["_root_dir"] = str(self.root_dir)
            print("[OTFlex] Deck layout (normalized):")
            for slot_key, rec in self.deck_norm.get("slots", {}).items():
                print(f"  slot {slot_key:>2} -> {rec['slot_label']:<2} : {rec.get('labware')} ({rec.get('name','')})")
            await asyncio.to_thread(fn, dev_cfg)

    async def disconnect(self):
        fn = getattr(self.mod, "otflex_disconnect", None)
        if callable(fn):
            await asyncio.to_thread(fn)

    async def transfer(self, p: Dict[str, Any]):
        # 期望你的脚本暴露：otflex_transfer(params: dict)
        fn = getattr(self.mod, "otflex_transfer", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_transfer(params) in OTFLEX_WORKFLOW_Iliya.")
        # 预处理/规范化参数，避免坐标/偏移映射错误
        norm = self._normalize_transfer(p)
        await asyncio.to_thread(fn, norm)

    async def toolTransfer(self, p: Dict[str, Any]):
        # 期望你的脚本暴露：otflex_toolTransfer(params: dict)
        fn = getattr(self.mod, "otflex_toolTransfer", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_toolTransfer(params) in OTFLEX_WORKFLOW_Iliya.")
        # 预处理/规范化参数，避免坐标/偏移映射错误
        norm = self._normalize_toolTransfer(p)
        await asyncio.to_thread(fn, norm)

    async def potentExperiment(self, p: Dict[str, Any]):
        # 期望你的脚本暴露：otflex_toolTransfer(params: dict)
        fn = getattr(self.mod, "otflex_potentExperiment", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_potentExperiment(params) in OTFLEX_WORKFLOW_Iliya.")
        # 预处理/规范化参数，避免坐标/偏移映射错误
        norm = self._normalize_potentExperiment(p)
        await asyncio.to_thread(fn, norm)

    async def flushWell(self, p: Dict[str, Any]):
        # 期望你的脚本暴露：otflex_flushWell(params: dict)
        fn = getattr(self.mod, "otflex_flushWell", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_flushWell(params) in OTFLEX_WORKFLOW_Iliya.")
        # 预处理/规范化参数，使用与potentExperiment相同的规范化
        norm = self._normalize_flushWell(p)
        await asyncio.to_thread(fn, norm)

    # -------- Deck normalization --------
    def _normalize_deck(self, deck_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize deck slot keys to Flex A1..C3 labels.

        Accepts devices.otflex.deck like:
          { "slots": { "1": {"labware": "...", "name": "..."}, ... } }

        Produces:
          {
            "slots": {
               "1": {"slot_label": "A1", "labware": "...", "name": "..."},
               ...
            }
          }

        Mapping policy:
        - If key already looks like a Flex label (e.g. A1/B2/C3), keep as-is.
        - If key is numeric 1..9, map by column-major order:
            1->A1, 2->B1, 3->C1, 4->A2, 5->B2, 6->C2, 7->A3, 8->B3, 9->C3
        - Otherwise, leave slot_label=None and print a warning at connect.
        """
        slots = (deck_cfg or {}).get("slots", {}) or {}
        out = {"slots": {}}

        num_to_flex = {
            1: "A1", 2: "B1", 3: "C1",
            4: "A2", 5: "B2", 6: "C2",
            7: "A3", 8: "B3", 9: "C3",
        }

        def is_flex_label(s: str) -> bool:
            if not isinstance(s, str) or len(s) != 2:
                return False
            row, col = s[0].upper(), s[1]
            return row in ("A", "B", "C", "D") and col in ("1", "2", "3", "4")

        # Provide a 1..16 -> A1..D4 column-major mapping (prefer using A1..D4 directly in JSON)
        num_to_flex16 = {
            1: "A1", 2: "B1", 3: "C1", 4: "D1",
            5: "A2", 6: "B2", 7: "C2", 8: "D2",
            9: "A3", 10: "B3", 11: "C3", 12: "D3",
            13: "A4", 14: "B4", 15: "C4", 16: "D4",
        }

        for k, rec in slots.items():
            lbl = None
            if is_flex_label(k):
                lbl = k.upper()
            else:
                try:
                    n = int(k)
                    # backward-compat: support 1..9 mapping as well
                    lbl = num_to_flex.get(n) or num_to_flex16.get(n)
                except Exception:
                    lbl = None
            out["slots"][str(k)] = {
                **(rec or {}),
                "slot_label": lbl,
            }

        # Warn about unknown mapping so user can fix JSON or mapping table
        unknown = [sk for sk, r in out["slots"].items() if not r.get("slot_label")]
        if unknown:
            print("[OTFlex][WARN] Unknown slot mapping for:", ", ".join(unknown))
        return out

    async def gripper(self, p: Dict[str, Any]):
        fn = getattr(self.mod, "otflex_gripper", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_gripper(params) in OTFLEX_WORKFLOW_Iliya.")
        await asyncio.to_thread(fn, p)

    async def wash(self, p: Dict[str, Any]):
        fn = getattr(self.mod, "otflex_wash", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_wash(params) in OTFLEX_WORKFLOW_Iliya.")
        await asyncio.to_thread(fn, p)

    async def furnace(self, p: Dict[str, Any]):
        fn = getattr(self.mod, "otflex_furnace", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_furnace(params) in OTFLEX_WORKFLOW_Iliya.")
        await asyncio.to_thread(fn, p)

    async def pump(self, p: Dict[str, Any]):
        fn = getattr(self.mod, "otflex_pump", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_pump(params) in OTFLEX_WORKFLOW_Iliya.")
        await asyncio.to_thread(fn, p)

    async def electrode(self, p: Dict[str, Any]):
        fn = getattr(self.mod, "otflex_electrode", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_electrode(params) in OTFLEX_WORKFLOW_Iliya.")
        await asyncio.to_thread(fn, p)

    async def reactor(self, p: Dict[str, Any]):
        fn = getattr(self.mod, "otflex_reactor", None)
        if not callable(fn):
            raise RuntimeError("Please implement otflex_reactor(params) in OTFLEX_WORKFLOW_Iliya.")
        await asyncio.to_thread(fn, p)

    async def echem_measure(self, p: Dict[str, Any]):
        # 可选：若电化学测量由此脚本完成
        fn = getattr(self.mod, "otflex_echem_measure", None)
        if callable(fn):
            await asyncio.to_thread(fn, p)
        else:
            print("[OTFlex] echem_measure no-op (implement otflex_echem_measure if needed)")
