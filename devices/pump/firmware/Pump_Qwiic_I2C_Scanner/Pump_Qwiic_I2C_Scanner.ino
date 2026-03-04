/*
  Qwiic I2C Address Scanner
  
  Scans the I2C bus for all connected SparkFun Qwiic devices and prints
  their I2C addresses. Useful for diagnosing connection issues and verifying
  relay address configuration.
  
  Upload to ESP32-POE-ISO and monitor serial output at 115200 baud.
*/

#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(300);
  
  Wire.begin();
  Wire.setClock(400000);  // Same clock speed as main controller
  
  Serial.println("\n========================================");
  Serial.println("  Qwiic I2C Address Scanner");
  Serial.println("  Scanning for devices...");
  Serial.println("========================================\n");
}

void loop() {
  int devicesFound = 0;
  
  Serial.println("Scanning I2C bus (0x00-0x7F - all addresses)...\n");
  
  for (uint8_t addr = 0x00; addr <= 0x7F; addr++) {
    Wire.beginTransmission(addr);
    byte error = Wire.endTransmission();
    
    if (error == 0) {
      Serial.printf("  [FOUND] Device at address 0x%02X", addr);
      
      // Note expected addresses
      if (addr == 0x18) Serial.print(" (Expected: Pump 1)");
      else if (addr == 0x19) Serial.print(" (Expected: Pump 2)");
      else if (addr == 0x09) Serial.print(" (Expected: Pump 3)");
      else Serial.print(" (Unexpected address!)");
      
      Serial.println();
      devicesFound++;
    }
  }
  
  Serial.printf("\nTotal devices found: %d\n", devicesFound);
  
  if (devicesFound == 0) {
    Serial.println("WARNING: No I2C devices detected!");
    Serial.println("  - Check Qwiic cable connections");
    Serial.println("  - Verify power to relay boards");
    Serial.println("  - Try lowering I2C clock speed (100kHz)");
  }
  
  Serial.println("\n----------------------------------------");
  Serial.println("Scanning again in 5 seconds...\n");
  delay(5000);
}
