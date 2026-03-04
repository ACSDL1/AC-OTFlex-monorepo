/*
  ESP32-POE-ISO (Olimex) — Pumps-only MQTT controller using ONE SparkFun Qwiic Quad Relay
  With serial debug output for troubleshooting

  - MQTT topics:
      pumps/01/cmd/<n>      : "ON" | "OFF" | "ON:<ms>"
      pumps/01/state/<n>    : retained "ON"/"OFF"
      pumps/01/status       : retained "ONLINE"/"OFFLINE"
      pumps/01/heartbeat    : "1" every 15s
*/

#include <Wire.h>
#include <WiFi.h>
#include <ETH.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <SparkFun_Qwiic_Relay.h>

/************ MQTT broker config ************/
const char* MQTT_BROKER_IP   = "192.168.0.100";   // your laptop/broker IP
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

/************ Relay config ************/
#define RELAY_ADDR_1   0x6D
#define PUMP_COUNT     4
#define HEARTBEAT_MS   15000
#define TIMED_SLOTS    4

/************ Globals ************/
WiFiClient   netClient;
PubSubClient mqtt(netClient);
static bool eth_ready = false;
char clientId[40];

Qwiic_Relay relay1(RELAY_ADDR_1);
bool relay1_ok = false;
bool pumpIsOn[PUMP_COUNT + 1] = {false};

struct TimedRun {
  uint8_t pump;
  uint32_t endMs;
  bool active;
} slots[TIMED_SLOTS];

unsigned long lastBeat = 0;

/************ Helpers ************/
bool pumpToBoardChannel(uint8_t pump, Qwiic_Relay*& board, uint8_t& chan) {
  if (pump < 1 || pump > PUMP_COUNT) return false;
  board = &relay1;
  chan = pump;
  return true;
}

/************ Relay control ************/
bool setPump(uint8_t pump, bool on) {
  Qwiic_Relay* b = nullptr; uint8_t ch = 0;
  if (!pumpToBoardChannel(pump, b, ch)) {
    Serial.printf("[WARN] Invalid pump number: %d\n", pump);
    return false;
  }

  if (!relay1_ok) {
    Serial.println("[INFO] Relay not initialized, trying to begin()...");
    relay1_ok = b->begin();
    if (!relay1_ok) {
      Serial.println("[ERROR] Qwiic Relay not detected on I2C!");
      return false;
    }
  }

  Serial.printf("[ACTION] Pump %d -> %s\n", pump, on ? "ON" : "OFF");
  if (on) b->turnRelayOn(ch);
  else    b->turnRelayOff(ch);

  pumpIsOn[pump] = on;

  // publish retained state
  char topic[48];
  snprintf(topic, sizeof(topic), "%s/state/%u", DEV_BASE, pump);
  mqtt.publish(topic, on ? "ON" : "OFF", true);

  return true;
}

bool getPumpStateFromHW(uint8_t pump, bool& on) {
  Qwiic_Relay* b = nullptr; uint8_t ch = 0;
  if (!pumpToBoardChannel(pump, b, ch)) return false;
  if (!relay1_ok) relay1_ok = b->begin();
  if (!relay1_ok) return false;

  uint8_t s = b->getState(ch);
  on = (s == 1);
  Serial.printf("[STATE] Pump %d current state: %s\n", pump, on ? "ON" : "OFF");
  return true;
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
    snprintf(clientId, sizeof(clientId), "pumps01-%08X", id);

    Serial.printf("[MQTT] Connecting to %s:%d as %s...\n", MQTT_BROKER_IP, MQTT_PORT, clientId);
    if (mqtt.connect(clientId, MQTT_USER, MQTT_PASS,
                     (String(DEV_BASE) + "/status").c_str(), 1, true, "OFFLINE")) {
      Serial.println("[MQTT] Connected successfully!");
      publishStatus("ONLINE");

      // Subscribe
      char filter[48];
      snprintf(filter, sizeof(filter), "%s/cmd/#", DEV_BASE);
      mqtt.subscribe(filter, 0);
      Serial.printf("[MQTT] Subscribed to: %s\n", filter);

      // Republish states
      for (uint8_t i = 1; i <= PUMP_COUNT; i++) {
        bool on = false;
        if (getPumpStateFromHW(i, on)) {
          char t[48];
          snprintf(t, sizeof(t), "%s/state/%u", DEV_BASE, i);
          mqtt.publish(t, on ? "ON" : "OFF", true);
        }
      }
    } else {
      Serial.printf("[MQTT] Failed (rc=%d). Retrying...\n", mqtt.state());
      delay(1500);
    }
  }
}

void handleCmd(const char* topic, const char* payload) {
  int pump = -1;
  const char* p = strrchr(topic, '/');
  if (p) pump = atoi(p + 1);
  if (pump < 1 || pump > PUMP_COUNT) {
    Serial.printf("[WARN] Invalid topic: %s\n", topic);
    return;
  }

  Serial.printf("[MQTT] Command received: pump %d <- %s\n", pump, payload);

  if (strncasecmp(payload, "ON:", 3) == 0) {
    uint32_t ms = atoi(payload + 3);
    if (ms == 0) return;
    if (!setPump(pump, true)) return;

    for (int i = 0; i < TIMED_SLOTS; i++) {
      if (!slots[i].active) {
        slots[i].active = true;
        slots[i].pump   = pump;
        slots[i].endMs  = millis() + ms;
        Serial.printf("[TIMER] Pump %d scheduled OFF in %lu ms\n", pump, ms);
        break;
      }
    }
    return;
  }

  if (strcasecmp(payload, "ON") == 0) setPump(pump, true);
  else if (strcasecmp(payload, "OFF") == 0) setPump(pump, false);
}

void onMqtt(char* topic, byte* payload, unsigned int len) {
  char msg[40];
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
      Serial.println("[ETH] Connected (link up)");
      break;
    case ARDUINO_EVENT_ETH_GOT_IP:
      eth_ready = true;
      Serial.print("[ETH] IP obtained: ");
      Serial.println(ETH.localIP());
      break;
    case ARDUINO_EVENT_ETH_DISCONNECTED:
      Serial.println("[ETH] Disconnected");
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
  Serial.println("\n[BOOT] ESP32 Pump Controller starting...");

  Wire.begin();
  Wire.setClock(400000);
  Serial.println("[I2C] Initialized for Qwiic bus");

  WiFi.onEvent(onNetEvent);
  Serial.println("[ETH] Initializing Ethernet...");
  ETH.begin(ETH_PHY_TYPE, ETH_PHY_ADDR, ETH_PHY_MDC, ETH_PHY_MDIO, ETH_POWER_PIN, ETH_CLK_MODE);

  relay1_ok = relay1.begin();
  if (relay1_ok) Serial.println("[I2C] Qwiic Relay detected.");
  else Serial.println("[I2C] Qwiic Relay NOT found!");

  for (uint8_t i = 1; i <= PUMP_COUNT; i++) setPump(i, false);

  mqtt.setServer(MQTT_BROKER_IP, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setKeepAlive(30);

  Serial.println("[BOOT] Setup complete.\n");
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
        Serial.printf("[TIMER] Pump %d OFF (timer expired)\n", slots[i].pump);
      }
    }
  }
}
