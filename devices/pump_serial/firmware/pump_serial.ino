/*
  ESP32 — Serial-controlled Pump Driver using SparkFun Qwiic Quad Relay
  
  Pump Configuration:
  - Pump 1: negative on relay 1, positive on relay 2
  - Pump 2: negative on relay 3, positive on relay 4
  
  Relay Wiring:
  - All NO (normally open) contacts → +12V
  - All NC (normally closed) contacts → -12V (connected together)
  
  Pump Control Logic:
  - Pump ON: Opposite relay states (one ON, one OFF) → 24V potential difference
  - Pump OFF: Same relay states (both ON or both OFF) → 0V
  
  Serial Commands (115200 baud):
    PUMP1:ON              - Turn pump 1 on indefinitely
    PUMP1:OFF             - Turn pump 1 off
    PUMP1:ON:3000         - Turn pump 1 on for 3000 ms
    PUMP2:ON              - Turn pump 2 on indefinitely
    PUMP2:OFF             - Turn pump 2 off
    PUMP2:ON:3000         - Turn pump 2 on for 3000 ms
    STATUS                - Print current pump states
*/

#include <Wire.h>
#include <SparkFun_Qwiic_Relay.h>

/************ Relay config ************/
#define RELAY_ADDR_1   0x7F
#define PUMP_COUNT     2

/************ Globals ************/
Qwiic_Relay relay1(RELAY_ADDR_1);
bool relay1_ok = false;

// Pump states
bool pump1_on = false;
bool pump2_on = false;

// Timed pump off tracking
struct TimedPump {
  uint8_t pump;
  uint32_t endMs;
  bool active;
} timedPumps[2] = {
  {1, 0, false},
  {2, 0, false}
};

// Serial buffer
char serialBuffer[32] = {0};
uint8_t serialIdx = 0;

/************ Relay control ************/
// Pump 1: relay 1 (negative), relay 2 (positive)
// Pump 2: relay 3 (negative), relay 4 (positive)
// 
// To turn pump ON, relays must be in OPPOSITE states (one ON, one OFF)
// To turn pump OFF, relays must be in SAME state (both ON or both OFF)
bool setPump(uint8_t pump, bool on, uint32_t durationMs = 0) {
  if (pump < 1 || pump > PUMP_COUNT) {
    Serial.printf("[ERROR] Invalid pump number: %d\n", pump);
    return false;
  }

  if (!relay1_ok) {
    Serial.println("[INFO] Relay not initialized, trying to begin()...");
    relay1_ok = relay1.begin();
    if (!relay1_ok) {
      Serial.println("[ERROR] Qwiic Relay not detected on I2C!");
      return false;
    }
  }

  if (on) {
    Serial.printf("[ACTION] Pump %d -> ON", pump);
    if (durationMs > 0) {
      Serial.printf(" for %lu ms\n", durationMs);
      timedPumps[pump - 1].active = true;
      timedPumps[pump - 1].endMs = millis() + durationMs;
    } else {
      Serial.println();
    }
    
    if (pump == 1) {
      relay1.turnRelayOn(1);    // pump1neg to +12V
      relay1.turnRelayOff(2);   // pump1pos to -12V (opposite state)
      pump1_on = true;
    } else if (pump == 2) {
      relay1.turnRelayOn(3);    // pump2neg to +12V
      relay1.turnRelayOff(4);   // pump2pos to -12V (opposite state)
      pump2_on = true;
    }
  } else {
    Serial.printf("[ACTION] Pump %d -> OFF\n", pump);
    
    if (pump == 1) {
      relay1.turnRelayOff(1);   // pump1neg to -12V
      relay1.turnRelayOff(2);   // pump1pos to -12V (same state = no current)
      pump1_on = false;
    } else if (pump == 2) {
      relay1.turnRelayOff(3);   // pump2neg to -12V
      relay1.turnRelayOff(4);   // pump2pos to -12V (same state = no current)
      pump2_on = false;
    }
    
    timedPumps[pump - 1].active = false;
  }

  return true;
}

void printStatus() {
  Serial.printf("[STATUS] Pump 1: %s\n", pump1_on ? "ON" : "OFF");
  Serial.printf("[STATUS] Pump 2: %s\n", pump2_on ? "ON" : "OFF");
}

/************ Serial command parsing ************/
void handleSerialCommand(const char* cmd) {
  Serial.printf("[CMD] Received: %s\n", cmd);

  // Parse PUMP<n>:ON or PUMP<n>:ON:<ms> or PUMP<n>:OFF
  uint8_t pump = 0;
  bool on = false;
  uint32_t durationMs = 0;
  
  if (strncasecmp(cmd, "PUMP1:", 6) == 0) {
    pump = 1;
    const char* action = cmd + 6;
    
    if (strncasecmp(action, "ON", 2) == 0) {
      on = true;
      if (action[2] == ':') {
        durationMs = atoi(action + 3);
      }
    } else if (strcasecmp(action, "OFF") == 0) {
      on = false;
    }
  } else if (strncasecmp(cmd, "PUMP2:", 6) == 0) {
    pump = 2;
    const char* action = cmd + 6;
    
    if (strncasecmp(action, "ON", 2) == 0) {
      on = true;
      if (action[2] == ':') {
        durationMs = atoi(action + 3);
      }
    } else if (strcasecmp(action, "OFF") == 0) {
      on = false;
    }
  } else if (strcasecmp(cmd, "STATUS") == 0) {
    printStatus();
    return;
  } else {
    Serial.println("[ERROR] Unknown command");
    Serial.println("Valid: PUMP1:ON, PUMP1:ON:<ms>, PUMP1:OFF, PUMP2:ON, PUMP2:ON:<ms>, PUMP2:OFF, STATUS");
    return;
  }
  
  if (pump > 0) {
    setPump(pump, on, durationMs);
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    
    if (c == '\n' || c == '\r') {
      if (serialIdx > 0) {
        serialBuffer[serialIdx] = '\0';
        handleSerialCommand(serialBuffer);
        serialIdx = 0;
      }
    } else if (serialIdx < sizeof(serialBuffer) - 1) {
      serialBuffer[serialIdx++] = c;
    }
  }
}

/************ Setup / Loop ************/
void setup() {
  Serial.begin(115200);
  delay(500);
  
  Serial.println("\n[BOOT] ESP32 Serial Pump Controller starting...");
  Serial.println("[BOOT] Commands: PUMP1:ON, PUMP1:ON:3000, PUMP1:OFF, PUMP2:ON, PUMP2:ON:3000, PUMP2:OFF, STATUS");

  Wire.begin();
  Wire.setClock(400000);
  Serial.println("[I2C] Initialized for Qwiic bus");

  relay1_ok = relay1.begin();
  if (relay1_ok) {
    Serial.println("[I2C] Qwiic Relay detected");
  } else {
    Serial.println("[ERROR] Qwiic Relay NOT found!");
  }

  // Initialize all pumps to OFF
  setPump(1, false);
  setPump(2, false);

  Serial.println("[BOOT] Setup complete. Ready for serial commands.\n");
}

void loop() {
  readSerial();
  
  // Check for timed pump expirations
  for (int i = 0; i < 2; i++) {
    if (timedPumps[i].active && millis() >= timedPumps[i].endMs) {
      Serial.printf("[TIMER] Pump %d timer expired, turning OFF\n", timedPumps[i].pump);
      setPump(timedPumps[i].pump, false);
    }
  }
  
  delay(10);
}
