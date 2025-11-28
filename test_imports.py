#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify imports work correctly
"""

import sys
import os
from pathlib import Path

# Add root directory to path
root_dir = Path(__file__).parent.parent.parent
sys.path.append(str(root_dir))

print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print(f"Root directory: {root_dir}")
print(f"Python path: {sys.path}")

try:
    from opentrons import opentronsClient
    print("✅ Successfully imported opentronsClient")
except Exception as e:
    print(f"❌ Failed to import opentronsClient: {e}")

try:
    import serial
    print("✅ Successfully imported serial")
except Exception as e:
    print(f"❌ Failed to import serial: {e}")

try:
    from xarm.wrapper import XArmAPI
    print("✅ Successfully imported XArmAPI")
except Exception as e:
    print(f"❌ Failed to import XArmAPI: {e}")

print("\nTesting adapter imports...")

try:
    from adapters.otflex_adapter import OTFlex
    print("✅ Successfully imported OTFlex adapter")
except Exception as e:
    print(f"❌ Failed to import OTFlex adapter: {e}")

try:
    from adapters.arm_adapter import MyxArm
    print("✅ Successfully imported MyxArm adapter")
except Exception as e:
    print(f"❌ Failed to import MyxArm adapter: {e}")

print("\nTest completed!")
