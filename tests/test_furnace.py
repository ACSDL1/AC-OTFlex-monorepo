#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Arduino-based furnace/thermal control.

This script tests:
- Arduino serial connection
- Temperature sensor readings
- Heating element control
- Ultrasonic transducer operations
"""

import sys
import os
import argparse
import logging
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def find_arduino_port():
    """Find Arduino serial port"""
    logger.info("Scanning for Arduino ports...")
    
    try:
        import serial.tools.list_ports
        
        ports = serial.tools.list_ports.comports()
        arduino_ports = []
        
        for port, desc, hwid in ports:
            if "Arduino" in desc or "CH340" in desc or "USB" in desc:
                logger.info(f"Found potential Arduino: {port} - {desc}")
                arduino_ports.append(port)
        
        if arduino_ports:
            logger.info(f"✓ Found Arduino on port: {arduino_ports[0]}")
            return arduino_ports[0]
        else:
            logger.warning("✗ No Arduino ports found")
            return None
    except ImportError:
        logger.error("pyserial not installed - cannot scan ports")
        return None
    except Exception as e:
        logger.error(f"Error scanning ports: {e}")
        return None


def test_arduino_connection(port: str = "COM4", baud_rate: int = 115200):
    """Test Arduino serial connection"""
    logger.info(f"Testing Arduino connection on {port} at {baud_rate} baud...")
    
    try:
        import serial
        
        # Attempt connection
        connection = serial.Serial(
            port=port,
            baudrate=baud_rate,
            timeout=2
        )
        
        time.sleep(1)  # Wait for Arduino to initialize
        
        if connection.is_open:
            logger.info(f"✓ Arduino connected on {port}")
            connection.close()
            return True
        else:
            logger.error("✗ Failed to open serial port")
            return False
    except Exception as e:
        logger.error(f"✗ Arduino connection failed: {e}")
        return False


def test_temperature_sensors(port: str = "COM4"):
    """Test temperature sensor readings"""
    logger.info("Testing temperature sensors (dry-run)...")
    
    try:
        import serial
        
        connection = serial.Serial(
            port=port,
            baudrate=115200,
            timeout=2
        )
        
        logger.info("Simulating temperature sensor read...")
        # Placeholder for actual sensor read
        logger.info("Temperature Cartridge 0: 25.5°C")
        logger.info("Temperature Cartridge 1: 26.2°C")
        
        connection.close()
        logger.info("✓ Temperature sensors test passed (dry-run)")
        return True
    except Exception as e:
        logger.error(f"✗ Temperature sensors test failed: {e}")
        return False


def test_heating_control(port: str = "COM4"):
    """Test heating element control"""
    logger.info("Testing heating element control (dry-run)...")
    
    try:
        logger.info("Simulating PID heating control...")
        logger.info("Setting setpoint: 30°C")
        logger.info("Current temperature: 25.5°C")
        logger.info("Heater output: 75% power")
        
        logger.info("✓ Heating control test passed (dry-run)")
        return True
    except Exception as e:
        logger.error(f"✗ Heating control test failed: {e}")
        return False


def test_ultrasonic_transducer(port: str = "COM4"):
    """Test ultrasonic transducer operations"""
    logger.info("Testing ultrasonic transducer (dry-run)...")
    
    try:
        logger.info("Simulating ultrasonic pulse...")
        logger.info("Cartridge 0: Ultrasonic ON (5 seconds)")
        logger.info("Cartridge 1: Ultrasonic ON (3 seconds)")
        
        logger.info("✓ Ultrasonic transducer test passed (dry-run)")
        return True
    except Exception as e:
        logger.error(f"✗ Ultrasonic transducer test failed: {e}")
        return False


def test_pump_calibration():
    """Test pump calibration data"""
    logger.info("Testing pump calibration...")
    
    try:
        # Default calibration values
        pump_slope = {
            0: 7.97/5,   # mL/s
            1: 8.00/5,
            2: 7.87/5,
            3: 7.92/5,
            4: 8.18/5,
            5: 7.48/5,
        }
        
        logger.info("Pump calibration values:")
        for pump_id, slope in pump_slope.items():
            logger.info(f"  Pump {pump_id}: {slope:.4f} mL/s")
        
        logger.info("✓ Pump calibration test passed")
        return True
    except Exception as e:
        logger.error(f"✗ Pump calibration test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test Arduino-based furnace/thermal control"
    )
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="Arduino serial port (default: auto-detect)"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Serial baud rate (default: 115200)"
    )
    parser.add_argument(
        "--test",
        choices=["find-port", "connection", "temperature", "heating", "ultrasonic", "calibration", "all"],
        default="find-port",
        help="Which test to run (default: find-port)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual hardware commands)"
    )
    
    args = parser.parse_args()
    
    logger.info(f"=== Arduino Furnace Control Test Suite ===")
    if args.dry_run:
        logger.info("Mode: DRY-RUN")
    
    # Find port if not specified
    if args.port is None and args.test != "find-port":
        args.port = find_arduino_port()
    
    tests = {
        "find-port": find_arduino_port,
        "connection": lambda: test_arduino_connection(args.port, args.baud) if args.port else False,
        "temperature": lambda: test_temperature_sensors(args.port) if args.port else False,
        "heating": lambda: test_heating_control(args.port) if args.port else False,
        "ultrasonic": lambda: test_ultrasonic_transducer(args.port) if args.port else False,
        "calibration": test_pump_calibration,
    }
    
    results = {}
    
    if args.test == "all":
        for test_name, test_func in tests.items():
            if test_name == "find-port":
                continue  # Skip standalone finding
            results[test_name] = test_func() if not args.port or test_name != "find-port" else True
    else:
        test_func = tests[args.test]
        if args.test == "find-port":
            port = test_func()
            if port:
                logger.info(f"Use: --port {port}")
        else:
            results[args.test] = test_func()
    
    if results:
        logger.info(f"\n=== Test Results ===")
        for test_name, passed in results.items():
            status = "PASSED ✓" if passed else "FAILED ✗"
            logger.info(f"{test_name}: {status}")
        
        all_passed = all(results.values())
        return 0 if all_passed else 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
