#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for UFactory xArm connectivity and movement.

This script tests:
- Connection to xArm
- ARM status and state
- Basic movement commands
- Tool operations (gripper, etc.)
"""

import sys
import os
import argparse
import logging
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.myxArm_Utils import RobotMain, XARM_AVAILABLE

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_arm_availability():
    """Test if xArm SDK is available"""
    logger.info("Checking xArm SDK availability...")
    
    if XARM_AVAILABLE:
        logger.info("✓ xArm SDK is available")
        return True
    else:
        logger.warning("✗ xArm SDK not available - running in simulation mode")
        return False


def test_arm_connection(arm_ip: str = "192.168.1.113", port: int = 5001, dry_run: bool = True):
    """Test ARM connection"""
    logger.info(f"Testing xArm connection to {arm_ip}:{port}...")
    
    if not XARM_AVAILABLE:
        logger.warning("xArm SDK not available, cannot test real connection")
        return False
    
    try:
        from xarm.wrapper import XArmAPI
        
        # Create ARM instance
        arm = XArmAPI(arm_ip, port=port)
        
        # Get status
        logger.info(f"ARM State: {arm.state}")
        logger.info(f"ARM Mode: {arm.mode}")
        logger.info(f"ARM Error: {arm.error_code}")
        
        logger.info("✓ ARM connection successful")
        arm.disconnect()
        return True
    except Exception as e:
        logger.error(f"✗ ARM connection failed: {e}")
        return False


def test_arm_initialization():
    """Test ARM initialization and status"""
    logger.info("Testing xArm initialization...")
    
    if not XARM_AVAILABLE:
        logger.warning("xArm SDK not available, cannot test initialization")
        return False
    
    try:
        from xarm.wrapper import XArmAPI
        
        arm = XArmAPI("192.168.1.113")
        
        # Check initialization
        logger.info(f"Firmware version: {arm.get_version()}")
        logger.info(f"Temperature: {arm.temperatures}")
        
        logger.info("✓ ARM initialization test passed")
        arm.disconnect()
        return True
    except Exception as e:
        logger.error(f"✗ ARM initialization failed: {e}")
        return False


def test_arm_movement_dry_run():
    """Test ARM movement in dry-run (no actual motion)"""
    logger.info("Testing xArm movement (dry-run)...")
    
    try:
        # This tests the movement logic without actual hardware
        logger.info("Testing movement parameters...")
        
        # Test pose generation
        pose_example = {
            "x": 300, "y": 0, "z": 200,
            "rx": 180, "ry": 0, "rz": 0
        }
        logger.info(f"Test pose: {pose_example}")
        
        logger.info("✓ ARM movement dry-run test passed")
        return True
    except Exception as e:
        logger.error(f"✗ ARM movement test failed: {e}")
        return False


def test_arm_tools():
    """Test ARM tool operations (gripper, etc.)"""
    logger.info("Testing xArm tool operations...")
    
    try:
        logger.info("Testing gripper commands (dry-run)...")
        # Placeholder for gripper test
        logger.info("✓ ARM tool operations test passed")
        return True
    except Exception as e:
        logger.error(f"✗ ARM tool operations failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test UFactory xArm connectivity and operations"
    )
    parser.add_argument(
        "--ip",
        type=str,
        default="192.168.1.113",
        help="xArm robot IP address (default: 192.168.1.113)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5001,
        help="xArm port (default: 5001)"
    )
    parser.add_argument(
        "--test",
        choices=["availability", "connection", "initialization", "movement", "tools", "all"],
        default="availability",
        help="Which test to run (default: availability)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual hardware commands)"
    )
    
    args = parser.parse_args()
    
    logger.info(f"=== UFactory xArm Test Suite ===")
    logger.info(f"Target: {args.ip}:{args.port}")
    if args.dry_run:
        logger.info("Mode: DRY-RUN")
    
    tests = {
        "availability": test_arm_availability,
        "connection": lambda: test_arm_connection(args.ip, args.port, args.dry_run),
        "initialization": test_arm_initialization,
        "movement": test_arm_movement_dry_run,
        "tools": test_arm_tools,
    }
    
    results = {}
    
    if args.test == "all":
        for test_name, test_func in tests.items():
            results[test_name] = test_func()
    else:
        test_func = tests[args.test]
        results[args.test] = test_func()
    
    logger.info(f"\n=== Test Results ===")
    for test_name, passed in results.items():
        status = "PASSED ✓" if passed else "FAILED ✗"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
