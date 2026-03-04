/*
  ESP32-POE-ISO — Pumps controller using THREE SparkFun Qwiic Single Relays
  Map:
    pump 1 -> relay @ 0x18
    pump 2 -> relay @ 0x19
    pump 3 -> relay @ 0x09

  MQTT:
    pumps/01/cmd/<n>    : "ON" | "OFF" | "ON:<ms>"
    pumps/01/state/<n>  : retained "ON"/"OFF"
    pumps/01/status     : retained "ONLINE"/"OFFLINE"
    pumps/01/heartbeat  : "1" every 15s
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
const char* MQTT_USER        = "pump1";
const char* MQTT_PASS        = "pump";
const char* DEV_BASE         = "pumps/01";

/************ Ethernet (Olimex ESP32-POE-ISO) ************/
#define ETH_PHY_TYPE   ETH_PHY_LAN8720
#define ETH_PHY_ADDR   0
#define ETH_PHY_MDC    23
#define ETH_PHY_MDIO   18
#define ETH_POWER_PIN  12
#define ETH_CLK_MODE   ETH_CLOCK_GPIO17_OUT

/************ Relays: three single boards ************/
#define RELAY_ADDR_P1  0x18
#define RELAY_ADDR_P2  0x19
#define RELAY_ADDR_P3  0x09
#define PUMP_COUNT     3
#define HEARTBEAT_MS   15000
#define TIMED_SLOTS    3

/************ Globals ************/
WiFiClient   netClient;
PubSubClient mqtt(netClient);
static bool  eth_ready = false;
char clientId[40];

Qwiic_Relay r1(RELAY_ADDR_P1);
Qwiic_Relay r2(RELAY_ADDR_P2);
Qwiic_Relay r3(RELAY_ADDR_P3);
bool r1_ok = false, r2_ok = false, r3_ok = false;

bool pumpIsOn[PUMP_COUNT + 1] = {false}; // 1-based

struct Timed {
  uint8_t pump;
  uint32_t endMs;
  bool active;
} slots[TIMED_SLOTS];

unsigned long lastBeat = 0;

/************ Helpers ************/
static inline Qwiic_Relay* relayForPump(uint8_t p) {
  if (p == 1) return &r1;
  if (p == 2) return &r2;
  if (p == 3) return &r3;
  return nullptr;
}
static inline bool& relayOkForPump(uint8_t p) {
  if (p == 1) return r1_ok;
  if (p == 2) return r2_ok;
  return r3_ok;
}

bool setPump(uint8_t p, bool on) {
  if (p < 1 || p > PUMP_COUNT) {
    Serial.printf("[WARN] Invalid pump: %u\n", p);
    return false;
  }
  Qwiic_Relay* r = relayForPump(p);
  bool& rok = relayOkForPump(p);

  if (!rok) {
    Serial.printf("[INFO] Relay for pump %u not initialized, begin()...\n", p);
    rok = r->begin();
    if (!rok) {
      uint8_t addr = (p==1? RELAY_ADDR_P1 : (p==2? RELAY_ADDR_P2 : RELAY_ADDR_P3));
      Serial.printf("[ERROR] Qwiic Single Relay (pump %u) not found @ 0x%02X\n", p, addr);
      return false;
    }
  }

  Serial.printf("[ACTION] Pump %u -> %s\n", p, on ? "ON" : "OFF");
  if (on) r->turnRelayOn(); else r->turnRelayOff();

  // verify & publish retained state
  delay(10);
  uint8_t s = r->getState();        // 0=off, 1=on
  pumpIsOn[p] = (s == 1);
  Serial.printf("[VERIFY] Pump %u state: %u\n", p, s);

  char topic[48];
  snprintf(topic, sizeof(topic), "%s/state/%u", DEV_BASE, p);
  mqtt.publish(topic, pumpIsOn[p] ? "ON" : "OFF", true);
  return true;
}

bool getPumpStateFromHW(uint8_t p, bool& on) {
  if (p < 1 || p > PUMP_COUNT) return false;
  Qwiic_Relay* r = relayForPump(p);
  bool& rok = relayOkForPump(p);
  if (!rok) rok = r->begin();
  if (!rok) return false;

  uint8_t s = r->getState();
  on = (s == 1);
  Serial.printf("[STATE] Pump %u -> %s\n", p, on ? "ON" : "OFF");
  return true;
}

/************ MQTT ************/
void publishStatus(const char* s) {
  char t[48];
  snprintf(t, sizeof(t), "%s/status", DEV_BASE);
  mqtt.publish(t, s, true);
  Serial.printf("[MQTT] Status: %s\n", s);
}

void ensureMqtt() {
  if (!eth_ready) return;

  while (!mqtt.connected()) {
    uint32_t id = (uint32_t)ESP.getEfuseMac();
    snprintf(clientId, sizeof(clientId), "pumps01-%08X", id);

    Serial.printf("[MQTT] Connecting %s:%u as %s...\n", MQTT_BROKER_IP, MQTT_PORT, clientId);
    if (mqtt.connect(clientId, MQTT_USER, MQTT_PASS,
                     (String(DEV_BASE) + "/status").c_str(), 1, true, "OFFLINE")) {
      Serial.println("[MQTT] Connected");
      publishStatus("ONLINE");

      char filter[48];
      snprintf(filter, sizeof(filter), "%s/cmd/#", DEV_BASE);
      mqtt.subscribe(filter, 0);
      Serial.printf("[MQTT] Subscribed: %s\n", filter);

      // Republish retained state from hardware
      for (uint8_t p = 1; p <= PUMP_COUNT; p++) {
        bool on = false;
        if (getPumpStateFromHW(p, on)) {
          char t[48];
          snprintf(t, sizeof(t), "%s/state/%u", DEV_BASE, p);
          mqtt.publish(t, on ? "ON" : "OFF", true);
        }
      }
    } else {
      Serial.printf("[MQTT] Failed (rc=%d). Retry...\n", mqtt.state());
      delay(1500);
    }
  }
}

void handleCmd(const char* topic, const char* payload) {
  int p = -1;
  const char* tail = strrchr(topic, '/');
  if (tail) p = atoi(tail + 1);
  if (p < 1 || p > PUMP_COUNT) {
    Serial.printf("[WARN] Invalid topic: %s\n", topic);
    return;
  }
  Serial.printf("[MQTT] cmd: pump %d <- %s\n", p, payload);

  if (strncasecmp(payload, "ON:", 3) == 0) {
    uint32_t ms = atoi(payload + 3);
    if (ms == 0) return;
    if (!setPump(p, true)) return;

    for (int i = 0; i < TIMED_SLOTS; i++) {
      if (!slots[i].active) {
        slots[i].active = true;
        slots[i].pump   = p;
        slots[i].endMs  = millis() + ms;
        Serial.printf("[TIMER] Pump %d OFF in %lu ms\n", p, ms);
        break;
      }
    }
    return;
  }

  if (strcasecmp(payload, "ON") == 0)  setPump(p, true);
  else if (strcasecmp(payload, "OFF") == 0) setPump(p, false);
}

void onMqtt(char* topic, byte* payload, unsigned int len) {
  char msg[48];
  len = (len < sizeof(msg)-1) ? len : sizeof(msg)-1;
  memcpy(msg, payload, len); msg[len] = '\0';
  handleCmd(topic, msg);
}

/************ Ethernet events ************/
void onNetEvent(WiFiEvent_t event) {
  switch (event) {
    case ARDUINO_EVENT_ETH_START:
      ETH.setHostname("esp32-pumps");
      Serial.println("[ETH] Started");
      break;
    case ARDUINO_EVENT_ETH_CONNECTED:
      Serial.println("[ETH] Link up");
      break;
    case ARDUINO_EVENT_ETH_GOT_IP:
      eth_ready = true;
      Serial.print("[ETH] IP: "); Serial.println(ETH.localIP());
      break;
    case ARDUINO_EVENT_ETH_DISCONNECTED:
      Serial.println("[ETH] Link down");
      eth_ready = false;
      break;
    case ARDUINO_EVENT_ETH_STOP:
      Serial.println("[ETH] Stopped");
      eth_ready = false;
      break;
    default: break;
  }
}

/************ Setup / Loop ************/
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n[BOOT] ESP32 Pumps (3x single relays) starting...");

  Wire.begin();
  Wire.setClock(400000);  // use 100k if your bus/wiring is long

  WiFi.onEvent(onNetEvent);
  Serial.println("[ETH] Init...");
  ETH.begin(ETH_PHY_TYPE, ETH_PHY_ADDR, ETH_PHY_MDC, ETH_PHY_MDIO, ETH_POWER_PIN, ETH_CLK_MODE);

  // Try once (lazy-init still happens inside setPump/getPumpStateFromHW)
  r1_ok = r1.begin();
  r2_ok = r2.begin();
  r3_ok = r3.begin();
  Serial.printf("[I2C] 0x%02X: %s\n", RELAY_ADDR_P1, r1_ok ? "OK" : "NOT FOUND");
  Serial.printf("[I2C] 0x%02X: %s\n", RELAY_ADDR_P2, r2_ok ? "OK" : "NOT FOUND");
  Serial.printf("[I2C] 0x%02X: %s\n", RELAY_ADDR_P3, r3_ok ? "OK" : "NOT FOUND");

  // Ensure OFF at boot (and publish retained states)
  for (uint8_t p = 1; p <= PUMP_COUNT; p++) setPump(p, false);

  mqtt.setServer(MQTT_BROKER_IP, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setKeepAlive(30);

  Serial.println("[BOOT] Setup done.\n");
}

void loop() {
  if (eth_ready && !mqtt.connected()) ensureMqtt();

  if (mqtt.connected()) {
    mqtt.loop();

    unsigned long now = millis();
    if (now - lastBeat > HEARTBEAT_MS) {
      lastBeat = now;
      String t = String(DEV_BASE) + "/heartbeat";
      mqtt.publish(t.c_str(), "1");
      Serial.println("[HEARTBEAT] Sent");
    }

    for (int i = 0; i < TIMED_SLOTS; i++) {
      if (slots[i].active && millis() >= slots[i].endMs) {
        setPump(slots[i].pump, false);
        slots[i].active = false;
        Serial.printf("[TIMER] Pump %u OFF (expired)\n", slots[i].pump);
      }
    }
  }
}
