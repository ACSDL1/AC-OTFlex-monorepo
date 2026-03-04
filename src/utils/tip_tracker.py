"""
tip_tracker.py - Minimal stub for tip tracking

Provides basic TipTracker functionality for tracking pipette tip positions
across multiple trays and wells.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import json


def id_to_well(well_id: int) -> str:
    """Convert numeric well ID to letter-number notation (e.g., 0 -> 'A1')"""
    if not isinstance(well_id, int) or well_id < 0:
        return "A1"
    row = well_id // 12
    col = well_id % 12
    return f"{chr(65 + row)}{col + 1}"


class TipTracker:
    """Tracks tip availability across tipracks"""
    
    def __init__(self, config_path: Path):
        """Initialize tip tracker from config file"""
        self.config_path = Path(config_path)
        self.trays: Dict[str, Dict[str, Any]] = {}
        self.next_index: int = 0
        self._load_config()
    
    def _load_config(self):
        """Load tip configuration from file"""
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text())
                self.trays = data.get("trays", {})
                self.next_index = int(data.get("next_index", 0))
        except Exception as e:
            print(f"[TipTracker] Could not load config: {e}")

    def next_tip(self):
        """Return next tip as (index, well), scanning A1..H12."""
        idx = int(self.next_index)
        well = id_to_well(idx)
        self.next_index = idx + 1
        self.save()
        return idx, well
    
    def get_available_tip(self, tray_id: str) -> Optional[str]:
        """Get next available tip from tray"""
        if tray_id not in self.trays:
            return None
        tray = self.trays[tray_id]
        return tray.get("next_well", "A1")
    
    def mark_tip_used(self, tray_id: str, well: str) -> None:
        """Mark a tip as used in a tray"""
        if tray_id not in self.trays:
            self.trays[tray_id] = {}
        self.trays[tray_id]["used_wells"] = \
            self.trays[tray_id].get("used_wells", []) + [well]
    
    def save(self) -> None:
        """Save tip state to file"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(
                {"trays": self.trays, "next_index": self.next_index},
                indent=2
            ))
        except Exception as e:
            print(f"[TipTracker] Could not save state: {e}")
