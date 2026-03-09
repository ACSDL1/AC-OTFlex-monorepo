/*
  ESP32-POE-ISO — Reactor Actuator controller using SparkFun Qwiic Quad Relay
  Linear actuator with forward/reverse motion control
  
  Relay mapping:
    ch 1 (FORWARD_1) + ch 3 (FORWARD_2) = FORWARD motion
    ch 2 (REVERSE_1) + ch 4 (REVERSE_2) = REVERSE motion

  MQTT topics:
    reactor/01/cmd/1    : "FORWARD" | "REVERSE" | "STOP" | "FORWARD:<ms>" | "REVERSE:<ms>"
    reactor/01/state/1  : retained "FORWARD"/"REVERSE"/"STOP"
    reactor/01/status   : retained "ONLINE"/"OFFLINE"
    reactor/01/heartbeat: "1" every 15s

  Controller supervision (subscribe):
    pyctl/status   : retained "ONLINE"/"OFFLINE" (controller's LWT)
    pyctl/heartbeat: "1" periodically
*/

#include <Wire.h>
#include <ETH.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include "SparkFun_Qwiic_Relay.h"

/************ MQTT broker config ************/
const char* MQTT_BROKER_IP   = "192.168.0.100";
const uint16_t MQTT_PORT     = 1883;
const char* MQTT_USER        = "reactor1";
const char* MQTT_PASS        = "controller";
const char* DEV_BASE         = "reactor/01";

/************ Supervision topics (from Python controller) ************/
const char* CTRL_STATUS_TOPIC    = "pyctl/status";
const char* CTRL_HEARTBEAT_TOPIC = "pyctl/heartbeat";

/************ Safety timeouts ************/
const uint32_t CTRL_TIMEOUT_MS     = 25000;  // 25s
const uint32_t MQTT_DOWN_OFF_MS    = 20000;  // 20s
const uint32_t MAX_MOTION_LEASE_MS = 60000;  // 60s cap for manual motion commands

/************ Ethernet (Olimex ESP32-POE-ISO) ************/
#define ETH_PHY_TYPE   ETH_PHY_LAN8720
#define ETH_PHY_ADDR   0
#define ETH_PHY_MDC    23
#define ETH_PHY_MDIO   18
#define ETH_POWER_PIN  12
#define ETH_CLK_MODE   ETH_CLOCK_GPIO17_OUT

/************ Relay config ************/
#define RELAY_ADDR      0x3D
#define RELAY_FORWARD_1 1
#define RELAY_FORWARD_2 3
#define RELAY_REVERSE_1 2
#define RELAY_REVERSE_2 4
#define HEARTBEAT_MS    15000
#define TIMED_SLOTS     2

/************ Globals ************/
WiFiClient   netClient;
PubSubClient mqtt(netClient);
static bool  eth_ready = false;
char clientId[40];

Qwiic_Relay relay(RELAY_ADDR);
bool relay_ok = false;

enum MotionState { STOPPED, FORWARD, REVERSE };
MotionState currentState = STOPPED;
uint32_t leaseUntil = 0;  // for manual commands

struct Timed {
  MotionState motion;
  uint32_t endMs;
  bool active;
} slots[TIMED_SLOTS];

unsigned long lastBeat = 0;
unsigned long lastCtrlBeat = 0;
bool ctrlSeen = false;
unsigned long lastMqttHealthy = 0;

/************ Actuator control ************/
void stopActuator() {
  if (!relay_ok && !relay.begin()) {
    Serial.println("[ERROR] Relay not available!");
    return;
  }
  relay_ok = true;
  
  relay.turnRelayOff(RELAY_FORWARD_1);
  relay.turnRelayOff(RELAY_FORWARD_2);
  relay.turnRelayOff(RELAY_REVERSE_1);
  relay.turnRelayOff(RELAY_REVERSE_2);
  currentState = STOPPED;
  leaseUntil = 0;
  Serial.println("[STOP] All relays OFF");
  
  char topic[48];
  snprintf(topic, sizeof(topic), "%s/state/1", DEV_BASE);
  mqtt.publish(topic, "STOP", true);
}

void moveForward() {
  if (!relay_ok && !relay.begin()) {
    Serial.println("[ERROR] Relay not available!");
    return;
  }
  relay_ok = true;

  relay.turnRelayOff(RELAY_REVERSE_1);
  relay.turnRelayOff(RELAY_REVERSE_2);
  delay(50); // Safety delay between direction changes
  relay.turnRelayOn(RELAY_FORWARD_1);
  relay.turnRelayOn(RELAY_FORWARD_2);
  currentState = FORWARD;
  Serial.println("[FORWARD] Relays 1 & 3 ON, Relays 2 & 4 OFF");
  
  char topic[48];
  snprintf(topic, sizeof(topic), "%s/state/1", DEV_BASE);
  mqtt.publish(topic, "FORWARD", true);
}

void moveReverse() {
  if (!relay_ok && !relay.begin()) {
    Serial.println("[ERROR] Relay not available!");
    return;
  }
  relay_ok = true;

  relay.turnRelayOff(RELAY_FORWARD_1);
  relay.turnRelayOff(RELAY_FORWARD_2);
  delay(50); // Safety delay between direction changes
  relay.turnRelayOn(RELAY_REVERSE_1);
  relay.turnRelayOn(RELAY_REVERSE_2);
  currentState = REVERSE;
  Serial.println("[REVERSE] Relays 2 & 4 ON, Relays 1 & 3 OFF");
  
  char topic[48];
  snprintf(topic, sizeof(topic), "%s/state/1", DEV_BASE);
  mqtt.publish(topic, "REVERSE", true);
}

/************ Safety ************/
void allOff(const char* reason) {
  Serial.printf("[SAFETY] ALL OFF (%s)\n", reason ? reason : "unspecified");
  stopActuator();
}

/************ MQTT ************/
void publishStatus(const char* s) {
  char topic[48];
  snprintf(topic, sizeof(topic), "%s/status", DEV_BASE);
  mqtt.publish(topic, s, true);
  Serial.printf("[MQTT] Status published: %s\n", s);
}

void ensureMqtt() {
  if (!eth_ready) return;

  while (!mqtt.connected()) {
    uint32_t id = (uint32_t)ESP.getEfuseMac();
    snprintf(clientId, sizeof(clientId), "reactor01-%08X", id);

    Serial.printf("[MQTT] Connecting to %s:%d as %s...\n", MQTT_BROKER_IP, MQTT_PORT, clientId);
    if (mqtt.connect(clientId, MQTT_USER, MQTT_PASS,
                     (String(DEV_BASE) + "/status").c_str(), 1, true, "OFFLINE")) {
      Serial.println("[MQTT] Connected successfully!");
      lastMqttHealthy = millis();
      publishStatus("ONLINE");

      char filter[48];
      snprintf(filter, sizeof(filter), "%s/cmd/#", DEV_BASE);
      mqtt.subscribe(filter, 0);
      Serial.printf("[MQTT] Subscribed to: %s\n", filter);

      mqtt.subscribe(CTRL_STATUS_TOPIC, 1);
      mqtt.subscribe(CTRL_HEARTBEAT_TOPIC, 0);
      Serial.printf("[MQTT] Subscribed: %s, %s\n", CTRL_STATUS_TOPIC, CTRL_HEARTBEAT_TOPIC);

      lastCtrlBeat = millis();
      ctrlSeen = false;

      // Republish current state
      char topic[48];
      snprintf(topic, sizeof(topic), "%s/state/1", DEV_BASE);
      const char* state = (currentState == FORWARD ? "FORWARD" : (currentState == REVERSE ? "REVERSE" : "STOP"));
      mqtt.publish(topic, state, true);
    } else {
      Serial.printf("[MQTT] Failed (rc=%d). Retrying...\n", mqtt.state());
      delay(1200);
      if (millis() - lastMqttHealthy > MQTT_DOWN_OFF_MS) {
        allOff("MQTT reconnect timeout");
      }
    }
  }
}

void handleCmd(const char* topic, const char* payload) {
  Serial.printf("[MQTT] Command received: %s\n", payload);

  if (strncasecmp(payload, "FORWARD:", 8) == 0) {
    uint32_t ms = atoi(payload + 8);
    if (ms == 0) return;
    moveForward();
    leaseUntil = 0;  // timed motion, no lease

    for (int i = 0; i < TIMED_SLOTS; i++) {
      if (!slots[i].active) {
        slots[i].active = true;
        slots[i].motion = FORWARD;
        slots[i].endMs  = millis() + ms;
        Serial.printf("[TIMER] FORWARD scheduled STOP in %lu ms\n", ms);
        break;
      }
    }
    return;
  }

  if (strncasecmp(payload, "REVERSE:", 8) == 0) {
    uint32_t ms = atoi(payload + 8);
    if (ms == 0) return;
    moveReverse();
    leaseUntil = 0;

    for (int i = 0; i < TIMED_SLOTS; i++) {
      if (!slots[i].active) {
        slots[i].active = true;
        slots[i].motion = REVERSE;
        slots[i].endMs  = millis() + ms;
        Serial.printf("[TIMER] REVERSE scheduled STOP in %lu ms\n", ms);
        break;
      }
    }
    return;
  }

  if (strcasecmp(payload, "FORWARD") == 0) {
    moveForward();
    if (MAX_MOTION_LEASE_MS > 0) {
      leaseUntil = millis() + MAX_MOTION_LEASE_MS;
      Serial.printf("[LEASE] FORWARD lease until +%lums\n", (unsigned long)MAX_MOTION_LEASE_MS);
    }
  }
  else if (strcasecmp(payload, "REVERSE") == 0) {
    moveReverse();
    if (MAX_MOTION_LEASE_MS > 0) {
      leaseUntil = millis() + MAX_MOTION_LEASE_MS;
      Serial.printf("[LEASE] REVERSE lease until +%lums\n", (unsigned long)MAX_MOTION_LEASE_MS);
    }
  }
  else if (strcasecmp(payload, "STOP") == 0) {
    stopActuator();
  }
}

void onMqtt(char* topic, byte* payload, unsigned int len) {
  char msg[64];
  len = (len < sizeof(msg)-1) ? len : sizeof(msg)-1;
  memcpy(msg, payload, len); msg[len] = '\0';

  Serial.printf("[MQTT] RX topic='%s' payload='%s'\n", topic, msg);

  if (strcmp(topic, CTRL_HEARTBEAT_TOPIC) == 0) {
    lastCtrlBeat = millis();
    ctrlSeen = true;
    return;
  }
  if (strcmp(topic, CTRL_STATUS_TOPIC) == 0) {
    if (strcasecmp(msg, "OFFLINE") == 0) {
      ctrlSeen = false;
      allOff("controller LWT OFFLINE");
    } else if (strcasecmp(msg, "ONLINE") == 0) {
      lastCtrlBeat = millis();
      ctrlSeen = true;
    }
    return;
  }

  if (strncmp(topic, DEV_BASE, strlen(DEV_BASE)) == 0) {
    handleCmd(topic, msg);
  }
}

/************ Ethernet events ************/
void onNetEvent(WiFiEvent_t event) {
  switch (event) {
    case ARDUINO_EVENT_ETH_START:
      ETH.setHostname("esp32-reactor");
      Serial.println("[ETH] Started");
      break;
    case ARDUINO_EVENT_ETH_CONNECTED:
      Serial.println("[ETH] Connected (link up)");
      break;
    case ARDUINO_EVENT_ETH_GOT_IP:
      eth_ready = true;
      Serial.print("[ETH] IP obtained: ");
      Serial.println(ETH.localIP());
      break;
    case ARDUINO_EVENT_ETH_DISCONNECTED:
      Serial.println("[ETH] Disconnected (link down)");
      eth_ready = false;
      allOff("Ethernet link down");
      break;
    case ARDUINO_EVENT_ETH_STOP:
      Serial.println("[ETH] Stopped");
      eth_ready = false;
      allOff("Ethernet stopped");
      break;
    default: break;
  }
}

/************ Setup / Loop ************/
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n[BOOT] ESP32 Reactor Controller starting...");

  Wire.begin();
  Wire.setClock(100000);
  Serial.println("[I2C] Initialized for Qwiic bus");

  WiFi.onEvent(onNetEvent);
  Serial.println("[ETH] Initializing Ethernet...");
  ETH.begin(ETH_PHY_TYPE, ETH_PHY_ADDR, ETH_PHY_MDC, ETH_PHY_MDIO, ETH_POWER_PIN, ETH_CLK_MODE);

  // Static IP
  ETH.config(
    IPAddress(192,168,0,53),   // ESP32 IP
    IPAddress(192,168,0,1),    // Gateway
    IPAddress(255,255,255,0),  // Netmask
    IPAddress(192,168,0,1),    // DNS1
    IPAddress(8,8,8,8)         // DNS2
  );

  relay_ok = relay.begin();
  Serial.printf("[I2C] Relay 0x%02X: %s\n", RELAY_ADDR, relay_ok ? "OK" : "NOT FOUND");

  stopActuator();

  mqtt.setServer(MQTT_BROKER_IP, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setKeepAlive(30);

  lastCtrlBeat = millis();
  ctrlSeen = false;
  lastMqttHealthy = millis();

  Serial.println("[BOOT] Setup complete.\n");
}

void loop() {
  uint32_t now = millis();

  if (eth_ready && !mqtt.connected()) {
    ensureMqtt();
  }
  if (mqtt.connected()) {
    mqtt.loop();
    lastMqttHealthy = now;
  }

  now = millis();

  // Controller heartbeat timeout
  if (mqtt.connected() && ctrlSeen) {
    int32_t dt = (int32_t)(now - lastCtrlBeat);
    if (dt >= 0 && (uint32_t)dt > CTRL_TIMEOUT_MS) {
      static uint32_t lastTimeoutLog = 0;
      if (now - lastTimeoutLog > 2000) {
        Serial.printf("[SAFETY] CTRL timeout: delta=%ldms (> %lums)\n",
                      (long)dt, (unsigned long)CTRL_TIMEOUT_MS);
        lastTimeoutLog = now;
      }
      allOff("controller heartbeat timeout");
      ctrlSeen = false;
    }
  }

  // Heartbeat
  if (mqtt.connected()) {
    if (now - lastBeat > HEARTBEAT_MS) {
      lastBeat = now;
      String topic = String(DEV_BASE) + "/heartbeat";
      mqtt.publish(topic.c_str(), "1");
      Serial.println("[HEARTBEAT] Sent");
    }
  }

  // Timed STOP handling
  for (int i = 0; i < TIMED_SLOTS; i++) {
    if (slots[i].active && now >= slots[i].endMs) {
      stopActuator();
      slots[i].active = false;
      Serial.printf("[TIMER] Motion stopped (expired)\n");
    }
  }

  // Lease STOP handling
  if (MAX_MOTION_LEASE_MS > 0 && leaseUntil > 0 && now >= leaseUntil) {
    Serial.printf("[LEASE] Motion lease expired -> STOP\n");
    stopActuator();
    leaseUntil = 0;
  }

  delay(10);
}
