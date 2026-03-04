#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Home an Opentrons robot from CLI.

Usage:
  python scripts/home_opentrons.py --ip 169.254.179.32 --robot flex
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.opentrons import opentronsClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Home Opentrons robot")
    parser.add_argument("--ip", required=True, help="Robot IP address")
    parser.add_argument(
        "--robot",
        default="flex",
        choices=["flex", "ot2"],
        help="Robot type (default: flex)",
    )
    args = parser.parse_args()

    client = opentronsClient(strRobotIP=args.ip, strRobot=args.robot)
    client.homeRobot()
    print(f"Homed {args.robot} at {args.ip}")


if __name__ == "__main__":
    main()
