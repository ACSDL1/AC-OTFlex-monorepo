#include <Wire.h>
#include "SparkFun_Qwiic_Relay.h"

Qwiic_Relay relay1(0x18);
Qwiic_Relay relay2(0x19);
Qwiic_Relay relay3(0x09);

bool relay1_ok = false;
bool relay2_ok = false;
bool relay3_ok = false;

// I2C scanner function
void scanI2C() {
  Serial.println("\n[I2C SCAN] Scanning for I2C devices...");
  int count = 0;
  
  for (uint8_t addr = 8; addr < 120; addr++) {
    Wire.beginTransmission(addr);
    uint8_t error = Wire.endTransmission();
    
    if (error == 0) {
      Serial.printf("  Device found at address 0x%02X (%d)\n", addr, addr);
      count++;
    }
  }
  
  if (count == 0) {
    Serial.println("  No I2C devices found!");
  } else {
    Serial.printf("[I2C SCAN] Total devices found: %d\n\n", count);
  }
}

// Initialize and display relay status
void initializeRelays() {
  Serial.println("[RELAY INIT] Attempting to initialize relays...\n");
  
  relay1_ok = relay1.begin();
  Serial.printf("  Relay 1 @ 0x18: %s\n", relay1_ok ? "OK" : "NOT FOUND");
  
  relay2_ok = relay2.begin();
  Serial.printf("  Relay 2 @ 0x19: %s\n", relay2_ok ? "OK" : "NOT FOUND");
  
  relay3_ok = relay3.begin();
  Serial.printf("  Relay 3 @ 0x09: %s\n\n", relay3_ok ? "OK" : "NOT FOUND");
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n[BOOT] Relay Test starting...");
    
    Wire.begin();
    Wire.setClock(400000);
    Serial.println("[I2C] Initialized");
    
    // Scan for all I2C devices
    scanI2C();
    
    // Initialize relays
    initializeRelays();
    
    // Ensure all relays are OFF at boot
    if (relay1_ok) relay1.turnRelayOff();
    if (relay2_ok) relay2.turnRelayOff();
    if (relay3_ok) relay3.turnRelayOff();
    
    Serial.println("[SETUP] Ready. Send commands:");
    Serial.println("  '1' = Relay 1 ON,  '2' = Relay 2 ON,  '3' = Relay 3 ON");
    Serial.println("  '4' = Relay 1 OFF, '5' = Relay 2 OFF, '6' = Relay 3 OFF");
    Serial.println("  'r' = Rescan I2C,  's' = Show status\n");
}

void loop() {
    if (Serial.available()) {
        char command = Serial.read();
        
        switch (command) {
            case '1':
                if (relay1_ok) {
                    relay1.turnRelayOn();
                    Serial.println("[CMD] Relay 1 turned ON");
                } else {
                    Serial.println("[ERROR] Relay 1 not available");
                }
                break;
            case '2':
                if (relay2_ok) {
                    relay2.turnRelayOn();
                    Serial.println("[CMD] Relay 2 turned ON");
                } else {
                    Serial.println("[ERROR] Relay 2 not available");
                }
                break;
            case '3':
                if (relay3_ok) {
                    relay3.turnRelayOn();
                    Serial.println("[CMD] Relay 3 turned ON");
                } else {
                    Serial.println("[ERROR] Relay 3 not available");
                }
                break;
            case '4':
                if (relay1_ok) {
                    relay1.turnRelayOff();
                    Serial.println("[CMD] Relay 1 turned OFF");
                } else {
                    Serial.println("[ERROR] Relay 1 not available");
                }
                break;
            case '5':
                if (relay2_ok) {
                    relay2.turnRelayOff();
                    Serial.println("[CMD] Relay 2 turned OFF");
                } else {
                    Serial.println("[ERROR] Relay 2 not available");
                }
                break;
            case '6':
                if (relay3_ok) {
                    relay3.turnRelayOff();
                    Serial.println("[CMD] Relay 3 turned OFF");
                } else {
                    Serial.println("[ERROR] Relay 3 not available");
                }
                break;
            case 'r':
                scanI2C();
                break;
            case 's':
                Serial.printf("  Relay 1: %s\n", relay1_ok ? "OK" : "NOT FOUND");
                Serial.printf("  Relay 2: %s\n", relay2_ok ? "OK" : "NOT FOUND");
                Serial.printf("  Relay 3: %s\n\n", relay3_ok ? "OK" : "NOT FOUND");
                break;
            case '\r':
            case '\n':
                break;
            default:
                if (command != ' ') {
                    Serial.printf("[UNKNOWN] Command '%c' - enter 1-6, r, or s\n", command);
                }
        }
    }
}