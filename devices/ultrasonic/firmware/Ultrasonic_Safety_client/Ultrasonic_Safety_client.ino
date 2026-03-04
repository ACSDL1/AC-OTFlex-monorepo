/*
  ESP32-POE-ISO — Ultrasonic controller using TWO SparkFun Qwiic Single Relays
  Channels:
    ch 1 -> relay @ 0x18
    ch 2 -> relay @ 0x09

  MQTT topics:
    ultra/01/cmd/<ch>    : "ON" | "OFF" | "ON:<ms>"
    ultra/01/state/<ch>  : retained "ON"/"OFF"
    ultra/01/status      : retained "ONLINE"/"OFFLINE"
    ultra/01/heartbeat   : "1" every 15s

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
const char* MQTT_BROKER_IP   = "192.168.0.100";   // your laptop/broker IP
const uint16_t MQTT_PORT     = 1883;
const char* MQTT_USER        = "ultra1";
const char* MQTT_PASS        = "controller";
const char* DEV_BASE         = "ultra/01";

/************ Controller supervision ************/
const char* CTRL_STATUS_TOPIC    = "pyctl/status";     // retained ONLINE/OFFLINE (LWT)
const char* CTRL_HEARTBEAT_TOPIC = "pyctl/heartbeat";  // "1" every few seconds

// Timeouts / leases
const uint32_t CTRL_TIMEOUT_MS   = 25000;  // if no controller beat for this long -> ALL OFF
const uint32_t MQTT_DOWN_OFF_MS  = 20000;  // if reconnect takes longer than this -> ALL OFF
const uint32_t MAX_ON_LEASE_MS   = 60000;  // plain "ON" max lease (0 disables)

/************ Ethernet (Olimex ESP32-POE-ISO) ************/
#define ETH_PHY_TYPE   ETH_PHY_LAN8720
#define ETH_PHY_ADDR   0
#define ETH_PHY_MDC    23
#define ETH_PHY_MDIO   18
#define ETH_POWER_PIN  12
#define ETH_CLK_MODE   ETH_CLOCK_GPIO17_OUT

/************ Relay config ************/
#define RELAY_ADDR_CH1   0x18   // CH1 relay I2C address
#define RELAY_ADDR_CH2   0x09   // CH2 relay I2C address
#define ULTRA_COUNT      2
#define HEARTBEAT_MS     15000
#define TIMED_SLOTS      4

/************ Globals ************/
WiFiClient   netClient;
PubSubClient mqtt(netClient);
static bool eth_ready = false;
char clientId[40];

// Two single-relay instances
Qwiic_Relay relay1(RELAY_ADDR_CH1);
Qwiic_Relay relay2(RELAY_ADDR_CH2);
bool relay1_ok = false, relay2_ok = false;

bool ultraIsOn[ULTRA_COUNT + 1] = {false}; // 1-based 
// Lease deadlines for plain ON (0 means no lease active)
uint32_t leaseUntil[ULTRA_COUNT + 1] = {0};

struct Timed {
  uint8_t ch;
  uint32_t endMs;
  bool active;
} slots[TIMED_SLOTS];

unsigned long lastBeat = 0;         // our heartbeat to the broker
unsigned long lastCtrlBeat = 0;     // last controller heartbeat seen
bool ctrlSeen = false;              // have we seen ONLINE/heartbeat?
unsigned long lastMqttHealthy = 0;  // last time we were connected/looping OK

/************ Safety: ALL OFF ************/
void allOff(const char* reason) {
  Serial.printf("[SAFETY] ALL OFF (%s)\n", reason ? reason : "unspecified");
  for (uint8_t ch = 1; ch <= ULTRA_COUNT; ch++) {
    // best-effort; ignore errors
    Qwiic_Relay* r = (ch==1? &relay1 : &relay2);
    bool& rok = (ch==1? relay1_ok : relay2_ok);
    if (!rok) rok = r->begin();
    if (rok) r->turnRelayOff();
    ultraIsOn[ch] = false;
    leaseUntil[ch] = 0;

    char topic[48];
    snprintf(topic, sizeof(topic), "%s/state/%u", DEV_BASE, ch);
    mqtt.publish(topic, "OFF", true);
  }
}

/************ Helpers ************/

// Map channel -> relay pointer
static inline Qwiic_Relay* relayForChannel(uint8_t ch) {
  if (ch == 1) return &relay1;
  if (ch == 2) return &relay2;
  return nullptr;
}

static inline bool& relayOkForChannel(uint8_t ch) {
  if (ch == 1) return relay1_ok;
  return relay2_ok; // ch==2
}

// Force ON/OFF for given channel, publish retained state
bool setUltra(uint8_t ch, bool on) {
  if (ch < 1 || ch > ULTRA_COUNT) {
    Serial.printf("[WARN] Invalid ultrasonic channel: %d\n", ch);
    return false;
  }
  Qwiic_Relay* r = relayForChannel(ch);
  bool& rok = relayOkForChannel(ch);

  if (!rok) {
    Serial.printf("[INFO] Relay ch%u not initialized, trying begin()...\n", ch);
    rok = r->begin();
    if (!rok) {
      Serial.printf("[ERROR] Qwiic Single Relay (ch%u) not detected on I2C (addr 0x%02X)!\n",
                    ch, (ch==1? RELAY_ADDR_CH1 : RELAY_ADDR_CH2));
      return false;
    }
  }

  Serial.printf("[ACTION] Ultrasonic %d -> %s\n", ch, on ? "ON" : "OFF");
  if (on) r->turnRelayOn(); else r->turnRelayOff();

  delay(8); // small settle
  uint8_t s = r->getState();        // 0=off, 1=on
  ultraIsOn[ch] = (s == 1);
  if (!on) leaseUntil[ch] = 0;       // clear lease when turning OFF

  char topic[48];
  snprintf(topic, sizeof(topic), "%s/state/%u", DEV_BASE, ch);
  mqtt.publish(topic, on ? "ON" : "OFF", true);
  return true;
}

// Read current HW state for channel
bool getUltraStateFromHW(uint8_t ch, bool& on) {
  if (ch < 1 || ch > ULTRA_COUNT) return false;
  Qwiic_Relay* r = relayForChannel(ch);
  bool& rok = relayOkForChannel(ch);

  if (!rok) rok = r->begin();
  if (!rok) return false;

  uint8_t s = r->getState(); // single relay: 0=off, 1=on
  on = (s == 1);
  Serial.printf("[STATE] Ultrasonic %d current state: %s\n", ch, on ? "ON" : "OFF");
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
    snprintf(clientId, sizeof(clientId), "ultra01-%08X", id);

    Serial.printf("[MQTT] Connecting to %s:%d as %s...\n", MQTT_BROKER_IP, MQTT_PORT, clientId);
    if (mqtt.connect(clientId, MQTT_USER, MQTT_PASS,
                     (String(DEV_BASE) + "/status").c_str(), 1, true, "OFFLINE")) {
      Serial.println("[MQTT] Connected successfully!");
      lastMqttHealthy = millis();

      publishStatus("ONLINE");

      // Device command subscription
      char filter[48];
      snprintf(filter, sizeof(filter), "%s/cmd/#", DEV_BASE);
      mqtt.subscribe(filter, 0);
      Serial.printf("[MQTT] Subscribed to: %s\n", filter);

      // Supervision subscriptions
      mqtt.subscribe(CTRL_STATUS_TOPIC, 1);
      mqtt.subscribe(CTRL_HEARTBEAT_TOPIC, 0);
      Serial.printf("[MQTT] Subscribed: %s, %s\n", CTRL_STATUS_TOPIC, CTRL_HEARTBEAT_TOPIC);

      lastCtrlBeat = millis();
      ctrlSeen = false;

      // Republish retained states from hardware
      for (uint8_t ch = 1; ch <= ULTRA_COUNT; ch++) {
        bool on = false;
        if (getUltraStateFromHW(ch, on)) {
          char topic[48];
          snprintf(topic, sizeof(topic), "%s/state/%u", DEV_BASE, ch);
          mqtt.publish(topic, on ? "ON" : "OFF", true);
        }
      }
    } else {
      Serial.printf("[MQTT] Failed (rc=%d). Retrying...\n", mqtt.state());
      delay(1200);
      // If we can't reconnect for long enough, fail-safe OFF
      if (millis() - lastMqttHealthy > MQTT_DOWN_OFF_MS) {
        allOff("MQTT reconnect timeout");
      }
    }
  }
}

void handleCmd(const char* topic, const char* payload) {
  // topic: ultra/01/cmd/<ch> ; payload: "ON" | "OFF" | "ON:<ms>"
  int ch = -1;
  const char* tail = strrchr(topic, '/');
  if (tail) ch = atoi(tail + 1);
  if (ch < 1 || ch > ULTRA_COUNT) {
    Serial.printf("[WARN] Invalid topic: %s\n", topic);
    return;
  }

  Serial.printf("[MQTT] Command received: ultra %d <- %s\n", ch, payload);

  if (strncasecmp(payload, "ON:", 3) == 0) {
    uint32_t ms = atoi(payload + 3);
    if (ms == 0) return;
    if (!setUltra(ch, true)) return;

    // This is a timed ON; do not start a lease (timer will turn off)
    leaseUntil[ch] = 0;

    for (int i = 0; i < TIMED_SLOTS; i++) {
      if (!slots[i].active) {
        slots[i].active = true;
        slots[i].ch     = ch;
        slots[i].endMs  = millis() + ms;
        Serial.printf("[TIMER] Ultra %d scheduled OFF in %lu ms\n", ch, ms);
        break;
      }
    }
    return;
  }

  if (strcasecmp(payload, "ON") == 0)  {
    if (setUltra(ch, true) && MAX_ON_LEASE_MS > 0) {
      leaseUntil[ch] = millis() + MAX_ON_LEASE_MS;  // start lease
      Serial.printf("[LEASE] Ultra %d lease until +%lums\n", ch, (unsigned long)MAX_ON_LEASE_MS);
    }
  }
  else if (strcasecmp(payload, "OFF") == 0) {
    setUltra(ch, false);
  }
}

void onMqtt(char* topic, byte* payload, unsigned int len) {
  char msg[64];
  len = (len < sizeof(msg)-1) ? len : sizeof(msg)-1;
  memcpy(msg, payload, len); msg[len] = '\0';

  // DEBUG: show what we actually receive
  Serial.printf("[MQTT] RX topic='%s' payload='%s'\n", topic, msg);

  if (strcmp(topic, CTRL_HEARTBEAT_TOPIC) == 0) {
    lastCtrlBeat = millis();
    ctrlSeen = true;
    Serial.printf("[CTRL] heartbeat seen, lastCtrlBeat=%lu\n", lastCtrlBeat);
    return;
  }
  if (strcmp(topic, CTRL_STATUS_TOPIC) == 0) {
    Serial.printf("[CTRL] status='%s'\n", msg);
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
      ETH.setHostname("esp32-ultra");
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
  Serial.println("\n[BOOT] ESP32 Ultrasonic Controller starting...");

  Wire.begin();
  Wire.setClock(400000);  // you can drop to 100k if your bus is long
  Serial.println("[I2C] Initialized for Qwiic bus");

  WiFi.onEvent(onNetEvent);
  Serial.println("[ETH] Initializing Ethernet...");
  ETH.begin(ETH_PHY_TYPE, ETH_PHY_ADDR, ETH_PHY_MDC, ETH_PHY_MDIO, ETH_POWER_PIN, ETH_CLK_MODE);

  // Static IP (same subnet as broker)
  ETH.config(
    IPAddress(192,168,0,51),   // ESP32 IP
    IPAddress(192,168,0,1),    // Gateway (optional if no router)
    IPAddress(255,255,255,0),  // Netmask
    IPAddress(192,168,0,1),    // DNS1 
    IPAddress(8,8,8,8)         // DNS2
  );

  // Try to initialize relays (won’t fail boot if one is missing)
  relay1_ok = relay1.begin();
  relay2_ok = relay2.begin();
  Serial.printf("[I2C] Relay @0x%02X: %s\n", RELAY_ADDR_CH1, relay1_ok ? "OK" : "NOT FOUND");
  Serial.printf("[I2C] Relay @0x%02X: %s\n", RELAY_ADDR_CH2, relay2_ok ? "OK" : "NOT FOUND");

  // Ensure OFF at boot and publish retained states
  for (uint8_t ch = 1; ch <= ULTRA_COUNT; ch++) setUltra(ch, false);

  mqtt.setServer(MQTT_BROKER_IP, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setKeepAlive(30);

  lastCtrlBeat = millis();      // start with “recent” so we don’t trip immediately
  lastMqttHealthy = millis();
  ctrlSeen = false;

  Serial.println("[BOOT] Setup complete.\n");
}

void loop() {
  uint32_t now = millis();  

  // Maintain MQTT, and fail-safe if reconnect takes too long
  if (eth_ready && !mqtt.connected()) {
    ensureMqtt();
  }
  if (mqtt.connected()) {
    mqtt.loop();
    lastMqttHealthy = now;
  }

  // Refresh 'now' AFTER mqtt.loop() so comparisons use a time >= lastCtrlBeat
  now = millis();

  // Controller heartbeat timeout -> OFF (use signed delta to avoid underflow)
  if (mqtt.connected() && ctrlSeen) {
    int32_t dt = (int32_t)(now - lastCtrlBeat);  // signed
    if (dt >= 0 && (uint32_t)dt > CTRL_TIMEOUT_MS) {
      static uint32_t lastTimeoutLog = 0;
      if (now - lastTimeoutLog > 2000) {
        Serial.printf("[SAFETY] CTRL timeout: delta=%ldms (> %lums)\n",
                      (long)dt, (unsigned long)CTRL_TIMEOUT_MS);
        lastTimeoutLog = now;
      }
      allOff("controller heartbeat timeout");
      // Do NOT fake the beat by writing lastCtrlBeat=now; just wait for a real heartbeat.
      ctrlSeen = false;  // require a fresh ONLINE/heartbeat before enforcing again
    }
  }

  // Our own heartbeat (nice to have for dashboards)
  if (mqtt.connected()) {
    if (now - lastBeat > HEARTBEAT_MS) {
      lastBeat = now;
      String topic = String(DEV_BASE) + "/heartbeat";
      mqtt.publish(topic.c_str(), "1");
      Serial.println("[HEARTBEAT] Sent");
    }
  }

  // Timed OFF handling
  for (int i = 0; i < TIMED_SLOTS; i++) {
    if (slots[i].active && now >= slots[i].endMs) {
      setUltra(slots[i].ch, false);
      slots[i].active = false;
      Serial.printf("[TIMER] Ultra %u OFF (expired)\n", slots[i].ch);
    }
  }

  // Lease OFF handling for plain ON
  if (MAX_ON_LEASE_MS > 0) {
    for (uint8_t ch = 1; ch <= ULTRA_COUNT; ch++) {
      if (leaseUntil[ch] && now >= leaseUntil[ch]) {
        Serial.printf("[LEASE] Ultra %u lease expired -> OFF\n", ch);
        setUltra(ch, false);
        leaseUntil[ch] = 0;
      }
    }
  }

  delay(10);
}
