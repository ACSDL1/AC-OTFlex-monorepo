#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_workflow.py
- 读取 Canvas 导出的 JSON（含你补齐的 FILLED 版本字段）
- 解析 nodes/edges + executionMetadata
- 并行/串行调度执行各节点
- 通过 adapters/otflex_adapter.py 与 adapters/arm_adapter.py 调用你的设备脚本
使用:
    python run_workflow.py --json /path/to/completeflexelectrodep_workflow-FILLED.json
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set, Optional
from contextlib import asynccontextmanager

# === 设备适配层 ===
from ..adapters.otflex_adapter import OTFlex
from ..adapters.arm_adapter import MyxArm
from ..adapters.potentiostat_adapter import PotentiostatAdapter

# ================ 工具 ================
class ResourceLocks:
    """最小资源锁实现：并行时避免占同一工位/资源"""
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}

    def get(self, name: str) -> asyncio.Lock:
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]

    @asynccontextmanager
    async def acquire_many(self, names: List[str]):
        locks = [self.get(n) for n in sorted(set([n for n in names if n]))]
        # 依次拿锁，防死锁
        for lk in locks:
            await lk.acquire()
        try:
            yield
        finally:
            for lk in reversed(locks):
                lk.release()

class RetryError(Exception):
    pass

async def with_retry(coro_func, *, retries=0, timeout=None, retry_delay=0.5, desc=""):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            if timeout:
                return await asyncio.wait_for(coro_func(), timeout=timeout)
            else:
                return await coro_func()
        except Exception as e:
            last_exc = e
            if attempt < retries:
                await asyncio.sleep(retry_delay)
            else:
                raise RetryError(f"[FAILED after {retries+1} attempt(s)] {desc}: {e}") from e

# ================ 调度器 ================
class WorkflowRunner:
    def __init__(self, wf: Dict[str, Any], root_dir: Path, use_arm: bool = True):
        self.wf = wf
        self.root_dir = root_dir
        self.nodes_by_id = {n["id"]: n for n in wf["workflow"]["nodes"]}
        self.edges = wf["workflow"]["edges"]
        self.metadata = wf["workflow"].get("executionMetadata", {})
        self.resources = ResourceLocks()
        self.use_arm = use_arm

        # 设备实例（根据 JSON metadata.devices 初始化）
        devices_meta = wf.get("devices", {})
        # 支持从外部文件引用 otflex 配置（便于多工作流复用）
        otflex_cfg = devices_meta.get("otflex", {})
        otflex_ref = devices_meta.get("otflex_file")
        if otflex_ref:
            try:
                ref_path = (root_dir / otflex_ref).resolve()
                import json as _json
                otflex_cfg = _json.loads(ref_path.read_text(encoding="utf-8"))
                print(f"[Workflow] Loaded otflex config from {otflex_ref}")
            except Exception as e:
                print(f"[Workflow][WARN] failed to load otflex_file {otflex_ref}: {e}")
        self.otflex = OTFlex(otflex_cfg, root_dir=root_dir)
        potentiostat_cfg = devices_meta.get("potentiostat", {}) or {}
        self.potentiostat = PotentiostatAdapter(potentiostat_cfg, root_dir=root_dir)

        arm_cfg = devices_meta.get("arm", {}) or {}
        arm_enabled_in_cfg = arm_cfg.get("enabled", True)
        self.use_arm = bool(self.use_arm and arm_enabled_in_cfg)
        self.arm: Optional[MyxArm] = None
        if self.use_arm:
            self.arm = MyxArm(arm_cfg, root_dir=root_dir)
        else:
            print("[Workflow] Arm disabled (CLI or config).")

    # 拓扑 + 并行执行
    def _build_graph(self):
        parents = {nid: set() for nid in self.nodes_by_id}
        children = {nid: [] for nid in self.nodes_by_id}
        edge_props = {}  # (src,dst) -> dict

        for e in self.edges:
            s = e["source"]; t = e["target"]
            children[s].append(t)
            parents[t].add(s)
            edge_props[(s, t)] = e
        return parents, children, edge_props

    def _roots(self, parents):
        return [nid for nid, p in parents.items() if len(p) == 0]

    async def run(self):
        # 连接设备（如需要）
        await self.otflex.connect()
        await self.potentiostat.connect()
        if self.use_arm and self.arm is not None:
            await self.arm.connect()

        parents, children, edge_props = self._build_graph()
        ready: Set[str] = set(self._roots(parents))
        done: Set[str] = set()
        running: Set[str] = set()

        # 建立每条边的执行模式（sequential / parallel）
        def edge_mode(src, dst):
            e = edge_props.get((src, dst), {})
            # 支持在 edge.data.mode 中声明并行/串行
            return (e.get("data", {}) or {}).get("mode") or e.get("mode", "sequential")

        # 哪些子节点与同一父节点在 parallel 组
        def parallel_groups(curr: str) -> List[List[str]]:
            # 找到以 curr 为父的所有子节点，按 edge.mode 分组
            seq_grp, par_grp = [], []
            for ch in children.get(curr, []):
                if edge_mode(curr, ch) == "parallel":
                    par_grp.append(ch)
                else:
                    seq_grp.append(ch)
            groups = []
            if par_grp:
                groups.append(par_grp)  # 并行组
            # sequential 的我们逐个发
            for s in seq_grp:
                groups.append([s])
            return groups

        # Kahn-like 调度，但遇到 parallel 组时并发执行
        while ready:
            # 按顺序取一个 ready 节点执行
            curr = ready.pop()
            if curr in done:
                continue
            if curr in running:
                continue

            # 执行 curr
            await self._run_node(curr)
            done.add(curr)

            # 释放后继
            for grp in parallel_groups(curr):
                # 检查组内每个节点的所有父亲是否都完成
                can_run = [n for n in grp if parents[n].issubset(done)]
                if len(grp) == 1:
                    # 串行: 直接加入 ready
                    if can_run:
                        ready.add(can_run[0])
                else:
                    # 并行：全部能跑才一起跑
                    if set(can_run) == set(grp):
                        # 同发
                        await asyncio.gather(*(self._run_node(n) for n in grp))
                        done.update(grp)

            # 同步更新：某些节点可能因上面并行组直接跑掉
            # 将那些已满足父依赖但未执行的节点补进 ready
            for nid, parents_set in parents.items():
                if nid not in done and parents_set.issubset(done):
                    ready.add(nid)

        # 断开设备
        if self.use_arm and self.arm is not None:
            await self.arm.disconnect()
        await self.potentiostat.disconnect()
        await self.otflex.disconnect()
        print("[Workflow] All done.")

    # ========== 节点执行 ==========
    async def _run_node(self, nid: str):
        node = self.nodes_by_id[nid]
        ntype = node["type"]
        name = node.get("data", {}).get("label", ntype)
        params = node.get("params") or node.get("data", {}).get("params") or {}
        locks = params.get("resourceLocks") or node.get("resourceLocks") or []
        retries = params.get("retries", 0)
        timeout = params.get("timeout", None)

        async def _do():
            print(f"[Node {nid}] {name} :: {ntype}")
            # 简单路由
            if ntype in ("input", "output"):
                return

            # Arm: position / gripper (check before otflex to catch otflexmyxarm)
            if ntype.lower().startswith("otflexmyxarm") or ntype.lower().startswith("myxarm"):
                await self._run_arm(ntype, params, locks)
                return

            # OT-Flex: transfer / gripper / wash / furnace / pump / electrode / reactor
            if ntype.lower().startswith("otflex"):
                await self._run_otflex(ntype, params, locks)
                return

            # sdl1 * 测量等
            if ntype.lower().startswith("sdl1"):
                await self._run_sdl1(ntype, params, locks)
                return

            # 默认：忽略
            print(f"[Node {nid}] (no-op)")

        await with_retry(_do, retries=retries, timeout=timeout, desc=f"node {nid}")

    async def _run_otflex(self, ntype: str, p: Dict[str, Any], locks: List[str]):
        async with self.resources.acquire_many(locks):
            # 根据 ntype 分发
            key = ntype.lower()
            if "tooltransfer" in key:
                await self.otflex.toolTransfer(p)
            elif "potentexperiment" in key:
                await self.otflex.potentExperiment(p)
            elif "flushwell" in key:
                await self.otflex.flushWell(p)
            elif "transfer" in key:
                await self.otflex.transfer(p)
            elif "gripper" in key:
                await self.otflex.gripper(p)
            elif "wash" in key:
                await self.otflex.wash(p)
            elif "furnace" in key:
                await self.otflex.furnace(p)
            elif "pump" in key:
                await self.otflex.pump(p)
            elif "electrode" in key:
                await self.otflex.electrode(p)
            elif "reactor" in key:
                await self.otflex.reactor(p)
            else:
                print(f"[OTFlex] Unknown type: {ntype}")

    async def _run_arm(self, ntype: str, p: Dict[str, Any], locks: List[str]):
        if not self.use_arm or self.arm is None:
            print(f"[Arm] Skipped node {ntype} because arm is disabled.")
            return
        async with self.resources.acquire_many(locks):
            key = ntype.lower()
            if "run" in key or "sequence" in key:
                await self.arm.run_sequence(p)
            elif "position" in key or "move" in key:
                await self.arm.move(p)
            elif "gripper" in key:
                await self.arm.gripper(p)
            else:
                print(f"[Arm] Unknown type: {ntype}")

    async def _run_sdl1(self, ntype: str, p: Dict[str, Any], locks: List[str]):
        async with self.resources.acquire_many(locks):
            key = ntype.lower()
            if "electrochemicalmeasurement" in key or "echem" in key or "potent" in key:
                await self.potentiostat.echem_measure(p)
            else:
                await self.otflex.echem_measure(p)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="Path to Canvas FILLED JSON")
    ap.add_argument("--no-arm", action="store_true", help="Disable arm initialization and arm nodes")
    args = ap.parse_args()

    wf = json.loads(Path(args.json).read_text(encoding="utf-8"))
    runner = WorkflowRunner(wf, root_dir=Path(args.json).parent, use_arm=(not args.no_arm))

    asyncio.run(runner.run())

if __name__ == "__main__":
    main()


# python OER_module\OER_Flex\run_workflow.py --json  OER_module\OER_Flex\simple_test_workflow.json
