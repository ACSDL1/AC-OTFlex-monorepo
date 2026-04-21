"""
Serial interface for controlling the ESP32 Quad Relay Pump Controller.

Usage:
    pump = PumpSerial("/dev/ttyUSB0")
    pump.on(1, 3000)  # Turn pump 1 on for 3000 ms
    pump.off(1)       # Turn pump 1 off
    pump.status()     # Get current pump states
"""

import serial
import time
from typing import Optional


class PumpSerial:
    """Control two pumps via ESP32 Serial interface."""
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        Initialize pump controller.
        
        Args:
            port: Serial port (e.g., "/dev/ttyUSB0", "COM3")
            baudrate: Baud rate (default 115200)
            timeout: Read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self._connect()
    
    def _connect(self):
        """Open serial connection."""
        try:
            self.serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout
            )
            time.sleep(0.5)  # Wait for ESP32 to initialize
            # Clear any startup messages
            self.serial.reset_input_buffer()
            print(f"[PUMP] Connected to {self.port} at {self.baudrate} baud")
        except serial.SerialException as e:
            raise RuntimeError(f"Failed to connect to {self.port}: {e}")
    
    def _send_command(self, cmd: str) -> str:
        """
        Send command and read response.
        
        Args:
            cmd: Command string (e.g., "PUMP1:ON")
            
        Returns:
            Response from ESP32
        """
        if not self.serial or not self.serial.is_open:
            raise RuntimeError("Serial port not open")
        
        # Send command
        self.serial.write((cmd + "\n").encode('utf-8'))
        print(f"[PUMP] Sent: {cmd}")
        
        # Read response
        response = []
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self.serial.in_waiting:
                line = self.serial.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    response.append(line)
                    print(f"[PUMP] Recv: {line}")
            else:
                time.sleep(0.01)
        
        return "\n".join(response)
    
    def on(self, pump: int, duration_ms: int = 0) -> bool:
        """
        Turn pump on.
        
        Args:
            pump: Pump number (1 or 2)
            duration_ms: Duration in milliseconds (0 = indefinite)
        
        Returns:
            True if successful
        """
        if pump not in [1, 2]:
            raise ValueError("Pump must be 1 or 2")
        
        if duration_ms > 0:
            cmd = f"PUMP{pump}:ON:{duration_ms}"
        else:
            cmd = f"PUMP{pump}:ON"
        
        self._send_command(cmd)
        return True
    
    def off(self, pump: int) -> bool:
        """
        Turn pump off.
        
        Args:
            pump: Pump number (1 or 2)
            
        Returns:
            True if successful
        """
        if pump not in [1, 2]:
            raise ValueError("Pump must be 1 or 2")
        self._send_command(f"PUMP{pump}:OFF")
        return True
    
    def status(self) -> str:
        """Get pump status."""
        return self._send_command("STATUS")
    
    def close(self):
        """Close serial connection."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("[PUMP] Serial connection closed")
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


if __name__ == "__main__":
    # Example usage
    import sys
    
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    
    with PumpSerial(port) as pump:
        print("\n=== Testing Pump Controller ===\n")
        
        print("1. Check status:")
        pump.status()
        
        print("\n2. Turn pump 1 on for 3000 ms:")
        pump.on(1, 3000)
        time.sleep(4)
        
        print("\n3. Turn pump 2 on for 2000 ms:")
        pump.on(2, 2000)
        time.sleep(3)
        
        print("\n4. Final status:")
        pump.status()
        
        print("\n=== Test complete ===\n")
