#include <Wire.h>
#include "SparkFun_Qwiic_Relay.h"

#define RELAY_ADDR 0x3D
#define RELAY_FORWARD_1 1
#define RELAY_FORWARD_2 3
#define RELAY_REVERSE_1 2
#define RELAY_REVERSE_2 4

Qwiic_Relay relay(RELAY_ADDR);

void scanI2C() {
    Serial.println("[I2C] Scanning...");
    uint8_t count = 0;
    for (uint8_t addr = 0x07; addr <= 0x77; addr++) {
        Wire.beginTransmission(addr);
        uint8_t err = Wire.endTransmission();
        if (err == 0) {
            Serial.print("[I2C] Found device at 0x");
            if (addr < 16) Serial.print("0");
            Serial.println(addr, HEX);
            count++;
        }
    }
    if (count == 0) {
        Serial.println("[I2C] No devices found");
    }
    if (count > 0) {
        Serial.print("[I2C] Total devices: ");
        Serial.println(count);
    }
    Serial.println("[I2C] Scan complete");
}

void stopActuator() {
    relay.turnRelayOff(RELAY_FORWARD_1);
    relay.turnRelayOff(RELAY_FORWARD_2);
    relay.turnRelayOff(RELAY_REVERSE_1);
    relay.turnRelayOff(RELAY_REVERSE_2);
    Serial.println("[STOP] All relays OFF");
}

void moveForward() {
    relay.turnRelayOff(RELAY_REVERSE_1);
    relay.turnRelayOff(RELAY_REVERSE_2);
    delay(50); // Safety delay
    relay.turnRelayOn(RELAY_FORWARD_1);
    relay.turnRelayOn(RELAY_FORWARD_2);
    Serial.println("[FORWARD] Relays 1 & 3 ON, Relays 2 & 4 OFF");
}

void moveReverse() {
    relay.turnRelayOff(RELAY_FORWARD_1);
    relay.turnRelayOff(RELAY_FORWARD_2);
    delay(50); // Safety delay
    relay.turnRelayOn(RELAY_REVERSE_1);
    relay.turnRelayOn(RELAY_REVERSE_2);
    Serial.println("[REVERSE] Relays 2 & 4 ON, Relays 1 & 3 OFF");
}

void setup() {
    Serial.begin(115200);
    delay(300);
    Serial.println("\n[TEST] SparkFun Quad Relay Actuator Test");
    Serial.println("[INFO] Commands: 0=Forward, 1=Reverse, S=Stop");
    
    Wire.begin();
    Wire.setClock(100000);

    scanI2C();
    
    // Initialize relay
    if (!relay.begin()) {
        Serial.println("[ERROR] Qwiic Quad Relay not detected at 0x6D!");
        while(1) delay(1000);
    }
    
    Serial.println("[OK] Relay detected");
    
    // Ensure stopped at startup
    stopActuator();
}

void loop() {
    if (Serial.available() > 0) {
        char cmd = Serial.read();
        
        switch(cmd) {
            case '0':
            case 'f':
            case 'F':
                moveForward();
                break;
                
            case '1':
            case 'r':
            case 'R':
                moveReverse();
                break;
                
            case 's':
            case 'S':
            case ' ':
            case '\n':
            case '\r':
                stopActuator();
                break;
                
            default:
                // Ignore other characters
                break;
        }
    }
    
    delay(10);
}
