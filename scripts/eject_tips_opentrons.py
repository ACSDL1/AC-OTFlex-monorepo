#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Force-eject tips on all mounted Opentrons pipettes.

This script intentionally attempts `dropTip` for each mounted pipette
without checking current tip presence first.

Usage:
  python scripts/eject_tips_opentrons.py --ip 169.254.179.32 --robot flex
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.opentrons import opentronsClient


def _discover_mounted_pipettes(ip: str) -> List[Tuple[str, str]]:
    url = f"http://{ip}:31950/instruments"
    response = requests.get(url, headers={"opentrons-version": "*"}, timeout=5)
    response.raise_for_status()

    payload = response.json()
    data = payload.get("data", []) if isinstance(payload, dict) else []

    mounted: List[Tuple[str, str]] = []

    # Shape A: list of instrument records
    if isinstance(data, list):
        for record in data:
            if not isinstance(record, dict):
                continue
            mount = record.get("mount")
            pipette_name = record.get("pipetteName") or record.get("name") or record.get("model")
            if mount and pipette_name:
                mounted.append((str(pipette_name), str(mount)))

    # Shape B: dict keyed by mount (e.g., {"left": {...}, "right": {...}})
    elif isinstance(data, dict):
        for mount, record in data.items():
            if not isinstance(record, dict):
                continue
            pipette_name = (
                record.get("pipetteName")
                or record.get("name")
                or record.get("model")
                or (record.get("data") or {}).get("pipetteName") if isinstance(record.get("data"), dict) else None
            )
            if pipette_name:
                mounted.append((str(pipette_name), str(mount)))

    return mounted


def _unique_pairs(pairs: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen = set()
    out: List[Tuple[str, str]] = []
    for pipette_name, mount in pairs:
        key = (str(pipette_name), str(mount))
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _prioritize_pairs(pairs: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    def priority(item: Tuple[str, str]) -> Tuple[int, str, str]:
        pipette_name, mount = item
        name = pipette_name.lower()
        # Run 1000uL family first, then everything else.
        is_1000 = ("1000" in name) or ("1k" in name)
        return (0 if is_1000 else 1, mount, name)

    return sorted(_unique_pairs(pairs), key=priority)


def _drop_tip_in_place(client: opentronsClient, pipette_name: str) -> None:
    # Explicitly use dropTipInPlace so the robot does not move toward trash.
    cmd = {
        "data": {
            "commandType": "dropTipInPlace",
            "params": {
                "pipetteId": client.pipettes[pipette_name]["id"],
                "homeAfter": False,
            },
            "intent": "setup",
        }
    }
    response = requests.post(
        url=client.commandURL,
        headers=client.headers,
        params={"waitUntilComplete": True},
        data=json.dumps(cmd),
    )
    if response.status_code != 201:
        raise RuntimeError(f"dropTipInPlace failed ({response.status_code}): {response.text}")


def _probe_candidates(robot: str) -> List[Tuple[str, str]]:
    mounts = ["left", "right"]
    if robot == "flex":
        names = [
            "p1000_single_flex",
            "p50_single_flex",
            "p1000_8channel_flex",
            "p50_8channel_flex",
        ]
    else:
        names = [
            "p1000_single_gen2",
            "p300_single_gen2",
            "p20_single_gen2",
            "p300_multi_gen2",
            "p20_multi_gen2",
        ]
    return [(name, mount) for mount in mounts for name in names]


def _force_eject(client: opentronsClient, pairs: Iterable[Tuple[str, str]]) -> Tuple[int, int]:
    issued = 0
    failed = 0
    for pipette_name, mount in _prioritize_pairs(pairs):
        try:
            client.loadPipette(strPipetteName=pipette_name, strMount=mount)
            _drop_tip_in_place(client, pipette_name)
            issued += 1
            print(f"Issued in-place tip-eject for {pipette_name} ({mount}).")
        except Exception as exc:
            failed += 1
            print(f"Warning: could not eject tip from {pipette_name} ({mount}): {exc}")
    return issued, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Force-eject tips from mounted Opentrons pipettes")
    parser.add_argument("--ip", required=True, help="Robot IP address")
    parser.add_argument(
        "--robot",
        default="flex",
        choices=["flex", "ot2"],
        help="Robot type (default: flex)",
    )
    args = parser.parse_args()

    client = opentronsClient(strRobotIP=args.ip, strRobot=args.robot)

    try:
        mounted = _discover_mounted_pipettes(args.ip)
    except Exception as exc:
        raise SystemExit(f"Failed to discover mounted pipettes: {exc}")

    issued = 0
    failed = 0

    if mounted:
        issued, failed = _force_eject(client, mounted)
    else:
        print("No mounted pipettes detected via /instruments. Probing common pipettes on both mounts...")
        issued, failed = _force_eject(client, _probe_candidates(args.robot))

    print(f"Done. Eject commands issued: {issued}; failures: {failed}.")


if __name__ == "__main__":
    main()
