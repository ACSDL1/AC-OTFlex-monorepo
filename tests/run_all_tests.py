#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Master test runner - Runs all component tests.

This script provides a unified interface to run all tests for:
- Opentrons Flex
- UFactory xArm
- Arduino Furnace
- Workflow Execution
"""

import sys
import os
import argparse
import logging
import subprocess
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_test(test_script: str, args: list = None):
    """Run a test script and return results"""
    args = args or []
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_script)] + args,
            capture_output=False,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to run {test_script.name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Master test runner for all components"
    )
    parser.add_argument(
        "--test",
        choices=["opentrons", "arm", "furnace", "workflows", "all"],
        default="all",
        help="Which test suite to run (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual hardware commands)"
    )
    
    args = parser.parse_args()
    
    test_dir = Path(__file__).parent
    
    test_scripts = {
        "opentrons": test_dir / "test_opentrons.py",
        "arm": test_dir / "test_arm.py",
        "furnace": test_dir / "test_furnace.py",
        "workflows": test_dir / "test_workflows.py",
    }
    
    logger.info("="*50)
    logger.info("AC_OTFlex_Workflow - Master Test Runner")
    logger.info("="*50)
    
    results = {}
    
    test_suites = [args.test] if args.test != "all" else list(test_scripts.keys())
    
    for suite_name in test_suites:
        if suite_name not in test_scripts:
            logger.warning(f"Unknown test suite: {suite_name}")
            continue
        
        script = test_scripts[suite_name]
        
        if not script.exists():
            logger.error(f"Test script not found: {script}")
            results[suite_name] = False
            continue
        
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {suite_name}")
        logger.info(f"{'='*50}")
        
        test_args = []
        if args.dry_run:
            test_args.append("--dry-run")
        
        results[suite_name] = run_test(script, test_args)
    
    logger.info(f"\n{'='*50}")
    logger.info("=== Overall Results ===")
    logger.info(f"{'='*50}")
    
    for suite_name, passed in results.items():
        status = "PASSED ✓" if passed else "FAILED ✗"
        logger.info(f"{suite_name:20} : {status}")
    
    all_passed = all(results.values())
    
    logger.info(f"{'='*50}")
    if all_passed:
        logger.info("✓ All tests PASSED")
    else:
        logger.info("✗ Some tests FAILED")
    logger.info(f"{'='*50}\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
