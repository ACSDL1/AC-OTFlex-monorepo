#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple tip usage tracker for 96-well tipracks.
Stores state in a JSON file: {"next": 1, "used": [ids...]}
Mapping 1..96 -> A1..H12 using row-major order (12 columns per row).
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Tuple


def id_to_well(idx: int) -> str:
    if idx < 1 or idx > 96:
        raise ValueError('tip id out of range 1..96')
    row = (idx - 1) // 12  # 0..7
    col = (idx - 1) % 12 + 1
    return chr(ord('A') + row) + str(col)


class TipTracker:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"next": 1, "used": []})

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding='utf-8'))
        except Exception:
            return {"next": 1, "used": []}

    def _save(self, data: dict):
        self.path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    def reset(self):
        self._save({"next": 1, "used": []})

    def next_tip(self) -> Tuple[int, str]:
        data = self._load()
        n = int(data.get('next', 1))
        used = set(data.get('used', []))
        # find next available
        while n in used and n <= 96:
            n += 1
        if n > 96:
            raise RuntimeError('No tips left in rack')
        # reserve
        used.add(n)
        data['used'] = sorted(list(used))
        data['next'] = n + 1
        self._save(data)
        return n, id_to_well(n)

