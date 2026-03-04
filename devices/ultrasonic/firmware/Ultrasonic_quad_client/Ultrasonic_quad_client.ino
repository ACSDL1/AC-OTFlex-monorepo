/*
  ESP32-POE-ISO (Olimex) — Ultrasonic Controller via 2x SparkFun Qwiic Single Relay
  MQTT control of two ultrasonic drivers (relays at I²C 0x18 → ch1, 0x09 → ch2)

  Commands (MQTT, ultra/01/cmd/<1|2>):
    "ON"            — turn channel ON
    "OFF"           — turn channel OFF
    "ON:<ms>"       — turn ON for <ms> milliseconds (auto-OFF)

  Telemetry (ESP → broker):
    ultra/01/state/<n>   : retained "ON"/"OFF"
    ultra/01/status      : retained "ONLINE"/"OFFLINE"
    ultra/01/heartbeat   : "1" every 15s
*/


#include <Wire.h>
#include <ETH.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include "SparkFun_Qwiic_Relay.h"

/************ MQTT broker config ************/
const char* MQTT_BROKER_IP   = "192.168.0.100";   // your broker (PC) IP
const uint16_t MQTT_PORT     = 1883;
const char* MQTT_USER        = "ultra1";
const char* MQTT_PASS        = "ultra";
const char* DEV_BASE         = "ultra/01";

/************ Ethernet (Olimex ESP32-POE-ISO) ************/
#define ETH_PHY_TYPE   ETH_PHY_LAN8720
#define ETH_PHY_ADDR   0
#define ETH_PHY_MDC    23
#define ETH_PHY_MDIO   18
#define ETH_POWER_PIN  12
#define ETH_CLK_MODE   ETH_CLOCK_GPIO17_OUT

/************ Relay config: two Single-Relay boards ************/
#define RELAY_ADDR_CH1   0x18     // Single Relay #1 (Ultrasonic CH1)
#define RELAY_ADDR_CH2   0x09     // Single Relay #2 (Ultrasonic CH2)

#define ULTRA_COUNT      2        // exactly two channels: 1..2
#define HEARTBEAT_MS     15000
#define TIMED_SLOTS      4

/************ Globals ************/
WiFiClient   netClient;
PubSubClient mqtt(netClient);
static bool  eth_ready = false;
char clientId[40];

// Two single-relay boards (one channel each)
Qwiic_Relay relayA(RELAY_ADDR_CH1);
Qwiic_Relay relayB(RELAY_ADDR_CH2);
bool relayA_ok = false;
bool relayB_ok = false;

// Cached states for retained publishes (1-based)
bool ultraIsOn[ULTRA_COUNT + 1] = {false, false, false};

// Timed ON slots (for "ON:<ms>")
struct TimeRun {
  uint8_t  ch;
  uint32_t endMs;
  bool     active;
} slots[TIMED_SLOTS];

unsigned long lastBeat = 0;

/************ Helpers ************/

// Map logical channel -> board pointer and its ok-flag reference
static bool* boardOkRefFor(Qwiic_Relay* b) {
  if (b == &relayA) return &relayA_ok;
  if (b == &relayB) return &relayB_ok;
  return nullptr;
}

bool chanToRelay(uint8_t ch, Qwiic_Relay*& board, uint8_t& relayCh) {
  if (ch == 1) { board = &relayA; relayCh = 1; return true; }
  if (ch == 2) { board = &relayB; relayCh = 1; return true; }
  return false;
}

bool ensureBoard(Qwiic_Relay* b) {
  bool* ok = boardOkRefFor(b);
  if (!ok) return false;
  if (!*ok) {
    *ok = b->begin();
    if (!*ok) return false;
  }
  return true;
}

void publishState(uint8_t ch) {
  char topic[48];
  snprintf(topic, sizeof(topic), "%s/state/%u", DEV_BASE, ch);
  mqtt.publish(topic, ultraIsOn[ch] ? "ON" : "OFF", true); // retained
}

// Force an ultrasonic channel ON/OFF and publish retained state
bool setUltra(uint8_t ch, bool on) {
  Qwiic_Relay* b = nullptr; uint8_t rch = 0;
  if (!chanToRelay(ch, b, rch)) {
    Serial.printf("[WARN] Invalid ultrasonic channel: %u\n", ch);
    return false;
  }
  if (!ensureBoard(b)) {
    Serial.printf("[ERROR] Relay (ch%u) not detected on I2C!\n", ch);
    return false;
  }

  Serial.printf("[ACTION] Ultrasonic %u -> %s\n", ch, on ? "ON" : "OFF");
  if (on) b->turnRelayOn(rch);
  else    b->turnRelayOff(rch);

  ultraIsOn[ch] = on;
  publishState(ch);
  return true;
}

// Read current hardware state from the relay
bool getUltraStateFromHW(uint8_t ch, bool& on) {
  Qwiic_Relay* b = nullptr; uint8_t rch = 0;
  if (!chanToRelay(ch, b, rch)) return false;
  if (!ensureBoard(b)) return false;

  uint8_t s = b->getState(rch); // 0 = off, 1 = on
  on = (s == 1);
  Serial.printf("[STATE] Ultra %u is %s\n", ch, on ? "ON" : "OFF");
  return true;
}

/************ MQTT ************/
void publishStatus(const char* s) {
  char topic[48];
  snprintf(topic, sizeof(topic), "%s/status", DEV_BASE);
  mqtt.publish(topic, s, true);
  Serial.printf("[MQTT] Status: %s\n", s);
}

void ensureMqtt() {
  if (!eth_ready) return;

  while (!mqtt.connected()) {
    uint32_t id = (uint32_t)ESP.getEfuseMac();
    snprintf(clientId, sizeof(clientId), "ultra01-%08X", id);

    Serial.printf("[MQTT] Connecting to %s:%d as %s...\n", MQTT_BROKER_IP, MQTT_PORT, clientId);
    if (mqtt.connect(clientId, MQTT_USER, MQTT_PASS,
                     (String(DEV_BASE) + "/status").c_str(), 1, true, "OFFLINE")) {
      Serial.println("[MQTT] Connected");
      publishStatus("ONLINE");

      char filter[48];
      snprintf(filter, sizeof(filter), "%s/cmd/#", DEV_BASE);
      mqtt.subscribe(filter, 0);
      Serial.printf("[MQTT] Subscribed: %s\n", filter);

      // Republish retained states
      for (uint8_t i = 1; i <= ULTRA_COUNT; i++) {
        bool on = false;
        if (getUltraStateFromHW(i, on)) {
          ultraIsOn[i] = on;
          publishState(i);
        }
      }
    } else {
      Serial.printf("[MQTT] Failed (rc=%d). Retrying...\n", mqtt.state());
      delay(1500);
    }
  }
}

void handleCmd(const char* topic, const char* payload) {
  // topic: ultra/01/cmd/<n>
  // payload: "ON" | "OFF" | "ON:<ms>"
  const char* p = strrchr(topic, '/');
  int ch = (p ? atoi(p + 1) : -1);
  if (ch < 1 || ch > ULTRA_COUNT) {
    Serial.printf("[WARN] Invalid topic: %s\n", topic);
    return;
  }

  Serial.printf("[MQTT] Cmd ultra %d <- %s\n", ch, payload);

  if (strncasecmp(payload, "ON:", 3) == 0) {
    uint32_t ms = atoi(payload + 3);
    if (ms == 0) return;
    if (!setUltra(ch, true)) return;

    for (int i = 0; i < TIMED_SLOTS; i++) {
      if (!slots[i].active) {
        slots[i].active = true;
        slots[i].ch     = ch;
        slots[i].endMs  = millis() + ms;
        Serial.printf("[TIMER] Ultra %d OFF in %lu ms\n", ch, ms);
        break;
      }
    }
    return;
  }

  if (strcasecmp(payload, "ON") == 0)  setUltra(ch, true);
  else if (strcasecmp(payload, "OFF") == 0) setUltra(ch, false);
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
      ETH.setHostname("esp32-ultra");
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
  Serial.println("\n[BOOT] ESP32 Ultrasonic Controller (2x Qwiic Single Relay)");

  Wire.begin();
  Wire.setClock(400000);
  Serial.println("[I2C] Qwiic bus ready");

  WiFi.onEvent(onNetEvent);
  Serial.println("[ETH] Init Ethernet...");
  ETH.begin(ETH_PHY_TYPE, ETH_PHY_ADDR, ETH_PHY_MDC, ETH_PHY_MDIO, ETH_POWER_PIN, ETH_CLK_MODE);

  // Try bringing up both relays once (optional warm-up)
  relayA_ok = relayA.begin();
  relayB_ok = relayB.begin();
  Serial.printf("[I2C] RelayA(0x%02X): %s\n", RELAY_ADDR_CH1, relayA_ok ? "OK" : "NOT FOUND");
  Serial.printf("[I2C] RelayB(0x%02X): %s\n", RELAY_ADDR_CH2, relayB_ok ? "OK" : "NOT FOUND");

  // Ensure OFF at boot + publish retained state
  setUltra(1, false);
  setUltra(2, false);

  mqtt.setServer(MQTT_BROKER_IP, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setKeepAlive(30);

  Serial.println("[BOOT] Setup complete.\n");
}

void loop() {
  if (eth_ready && !mqtt.connected()) ensureMqtt();

  if (mqtt.connected()) {
    mqtt.loop();

    // Heartbeat
    unsigned long now = millis();
    if (now - lastBeat > HEARTBEAT_MS) {
      lastBeat = now;
      String t = String(DEV_BASE) + "/heartbeat";
      mqtt.publish(t.c_str(), "1");
      Serial.println("[HEARTBEAT] Sent");
    }

    // Timed OFFs
    for (int i = 0; i < TIMED_SLOTS; i++) {
      if (slots[i].active && millis() >= slots[i].endMs) {
        setUltra(slots[i].ch, false);
        slots[i].active = false;
        Serial.printf("[TIMER] Ultra %u OFF (expired)\n", slots[i].ch);
      }
    }
  }
}
