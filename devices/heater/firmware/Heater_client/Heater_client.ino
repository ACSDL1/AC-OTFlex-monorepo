/*
  ESP32-POE-ISO (Olimex) — Two Heaters via SparkFun Qwiic Dual Solid State Relay
  PID + Thermistor (ADS1015) + MQTT + Safety (rate-of-rise brake)

  Commands (MQTT, heat/01/cmd/<1|2>):
    "ON" | "OFF" | "ON:<ms>" | "PWM:<0-100>" | "SET:<tempC>" | "PID:ON" | "PID:OFF"

  Telemetry:
    heat/01/state/<n>   : retained "ON"/"OFF"
    heat/01/target/<n>  : retained setpoint (float)
    heat/01/temp/<n>    : current temperature (float)
    heat/01/status      : retained "ONLINE"/"OFFLINE"
    heat/01/heartbeat   : "1" every 15s
*/

#include <Wire.h>
#include <WiFi.h>
#include <ETH.h>
#include <WiFiClient.h>
#include <PubSubClient.h>

#include "SparkFun_Qwiic_Relay.h"   // Dual SSR (I2C)
#include <SerLCD.h>  // LCD over qwiic via I2C
#include <Adafruit_ADS1X15.h>       // ADS1015/1115
#include <AutoPID.h>                // https://github.com/r-downing/AutoPID

/************ Your config constants (from prior code) ************/
#define HEATER_MAX 100    // PID output upper limit (as % slow-PWM)
#define HEATER_MIN 0      // PID output lower limit

// Thermistor decoding constants
#define RC     10000.0    // Fixed resistor in divider (ohms)
#define VCC    3.3        // Reference (for divider math)
#define R25    10000.0    // Thermistor nominal @25°C (ohms)
#define B2585  3977.0     // Beta (25/85°C), Kelvin

/************ MQTT broker config ************/
const char* MQTT_BROKER_IP = "192.168.0.100";
const uint16_t MQTT_PORT   = 1883;
const char* MQTT_USER      = "heat1";
const char* MQTT_PASS      = "heat";
const char* DEV_BASE       = "heat/01";

/************ Ethernet (Olimex ESP32-POE-ISO) ************/
#define ETH_PHY_TYPE   ETH_PHY_LAN8720
#define ETH_PHY_ADDR   0
#define ETH_PHY_MDC    23
#define ETH_PHY_MDIO   18
#define ETH_POWER_PIN  12
#define ETH_CLK_MODE   ETH_CLOCK_GPIO17_OUT

/************ Hardware mapping ************/
#define RELAY_ADDR   0x0A     // Verify with I2C scanner
#define HEATER_COUNT 2        // channels 1..2
#define HEARTBEAT_MS 15000
#define TIMED_SLOTS  4

// Thermistor channels on ADS1015
#define TH_CH_1  0           // A0
#define TH_CH_2  3           // A1

/************ Safety / filtering ************/
// EMA filter (slightly slower to suppress jitter)
static inline float ema(float prev, float cur, float alpha = 0.15f) {
  if (!isfinite(prev)) return cur;
  return prev + alpha * (cur - prev);
}

// Safety thresholds
const float    DT_MAX_C_PER_S       = 1.5f;     // max allowed dT/dt when heating
const uint32_t IGNORE_AFTER_BOOT_MS = 3000;     // grace period for filters
const float    MIN_DT_FOR_SLOPE_S   = 0.25f;    // require ≥250 ms window
const uint32_t PWM_MEMORY_MS        = 3000;     // consider heating if PWM>0 in last 3s
const uint32_t BRAKE_LOG_DEBOUNCE   = 500;      // min ms between safety logs

/************ Globals ************/
WiFiClient   netClient;
PubSubClient mqtt(netClient);
static bool  eth_ready = false;
char clientId[40];

Qwiic_Relay relay(RELAY_ADDR);
bool relay_ok = false;

SerLCD lcd;

Adafruit_ADS1015 ads;

// Cached heater state / PWM (1-based indexing)
bool  heaterIsOn[HEATER_COUNT + 1] = {false};
int   heaterPWM[HEATER_COUNT + 1]  = {0};

// PID / temperatures
float setTarget[HEATER_COUNT + 1]    = {0};
float tempC[HEATER_COUNT + 1]        = {NAN, NAN, NAN};
bool  pidEnabled[HEATER_COUNT + 1]   = {false};

double pidInput[HEATER_COUNT + 1]    = {0};
double pidOutput[HEATER_COUNT + 1]   = {0};
double pidSetpoint[HEATER_COUNT + 1] = {0};
double Kp = 4.0, Ki = 0.8, Kd = 0.0;
AutoPID* pid[HEATER_COUNT + 1]       = {nullptr, nullptr, nullptr};

// Timed ON slots
struct Timed {
  uint8_t  ch;
  uint32_t endMs;
  bool     active;
} slots[TIMED_SLOTS];

// Telemetry / boot timing
unsigned long lastBeat = 0;
unsigned long lastTelem = 0;
unsigned long bootMs = 0;

// For safety slope calculation
float    filtTemp[HEATER_COUNT + 1]   = {NAN, NAN, NAN};
float    lastTempVal[HEATER_COUNT + 1]= {NAN, NAN, NAN};
uint32_t lastTempMs[HEATER_COUNT + 1] = {0};
uint32_t lastPwmTime[HEATER_COUNT + 1]= {0};
uint32_t lastBrakeLog[HEATER_COUNT + 1]= {0};

/************ Helpers ************/
bool validCh(uint8_t ch) { return (ch >= 1 && ch <= HEATER_COUNT); }

void write_to_lcd() {
  for (int i = 0; i < 2; i++) {
    lcd.setCursor((byte)(i * 8), 0);
    lcd.print(String(i) + ":");
    lcd.print(tempC[i+1]);
    lcd.print(" ");

    lcd.setCursor((byte)(i * 8), 1);
    lcd.print("T:");
    lcd.print(setTarget[i+1]);
    lcd.print(" ");
  }
}

bool ensureRelay() {
  if (!relay_ok) {
    relay_ok = relay.begin();
    if (!relay_ok) {
      Serial.println("[ERROR] Qwiic Dual SSR not detected!");
      return false;
    }
    Serial.println("[I2C] Dual SSR ready.");
  }
  return true;
}

// Read thermistor degC from ADS1015 channel
bool readThermC(uint8_t adsChannel, float &outC) {
  int16_t raw = ads.readADC_SingleEnded(adsChannel);
  float vNode = ads.computeVolts(raw);         // ADS lib returns measured volts
  if (vNode < 0.0f) vNode = 0.0f;
  if (vNode > VCC)  vNode = VCC;

  // Divider: Vnode = VCC * (Rntc / (RC + Rntc)) → Rntc = RC * Vnode / (VCC - Vnode)
  if (fabs(VCC - vNode) < 1e-6) return false;
  double Rntc = RC * (double)vNode / (double)(VCC - vNode);
  if (Rntc <= 0.0) return false;

  // Beta equation
  double invT = (1.0 / 298.15) + (log(Rntc / R25) / B2585);
  double Tk   = 1.0 / invT;
  outC        = (float)(Tk - 273.15);

  if (!isfinite(outC) || outC < -40.0f || outC > 200.0f) return false;
  return true;
}

// --- Internal setters that DO NOT toggle pidEnabled ---
// (used by PID loop and safety brake so we don't disable PID inadvertently)
void _publishState(uint8_t ch) {
  char t[48];
  snprintf(t, sizeof(t), "%s/state/%u", DEV_BASE, ch);
  mqtt.publish(t, heaterIsOn[ch] ? "ON" : "OFF", true);
}

void _setOnOff(uint8_t ch, bool on) {
  if (!ensureRelay()) return;
  if (on) relay.turnRelayOn(ch); else relay.turnRelayOff(ch);
  if (heaterIsOn[ch] != on) {
    heaterIsOn[ch] = on;
    _publishState(ch);
  }
}

void _setPWM(uint8_t ch, int dutyPercent) {
  if (!ensureRelay()) return;
  if (dutyPercent < 0) dutyPercent = 0;
  if (dutyPercent > 100) dutyPercent = 100;
  relay.setSlowPWM(ch, dutyPercent);
  heaterPWM[ch] = dutyPercent;

  // reflect to state: >0% = ON
  bool on = (dutyPercent > 0);
  if (heaterIsOn[ch] != on) {
    heaterIsOn[ch] = on;
    _publishState(ch);
  }
}

// --- Public setters for manual commands (these disable PID) ---
bool setHeater(uint8_t ch, bool on) {
  if (!validCh(ch)) return false;
  pidEnabled[ch] = false;                 // manual overrides PID
  _setOnOff(ch, on);
  Serial.printf("[ACTION] Heater %u -> %s\n", ch, on ? "ON" : "OFF");
  return true;
}

bool setHeaterPWM(uint8_t ch, int dutyPercent) {
  if (!validCh(ch)) return false;
  pidEnabled[ch] = false;                 // manual overrides PID
  _setPWM(ch, dutyPercent);
  Serial.printf("[ACTION] Heater %u PWM -> %d%%\n", ch, dutyPercent);
  return true;
}

bool timedOn(uint8_t ch, uint32_t ms) {
  if (!setHeater(ch, true)) return false;
  for (int i = 0; i < TIMED_SLOTS; i++) {
    if (!slots[i].active) {
      slots[i].active = true;
      slots[i].ch     = ch;
      slots[i].endMs  = millis() + ms;
      Serial.printf("[TIMER] Heater %u OFF in %lu ms\n", ch, ms);
      return true;
    }
  }
  Serial.println("[WARN] No free timer slots");
  return false;
}

bool enablePID(uint8_t ch) {
  if (!validCh(ch)) return false;
  pidEnabled[ch]  = true;
  pidSetpoint[ch] = setTarget[ch];
  // publish target retained
  char t[48], p[16];
  snprintf(t, sizeof(t), "%s/target/%u", DEV_BASE, ch);
  dtostrf(setTarget[ch], 0, 1, p);
  mqtt.publish(t, p, true);
  Serial.printf("[PID] Enabled on heater %u (target=%.1f°C)\n", ch, setTarget[ch]);
  return true;
}

bool disablePID(uint8_t ch) {
  if (!validCh(ch)) return false;
  pidEnabled[ch] = false;
  _setPWM(ch, 0);   // force off immediately
  Serial.printf("[PID] Disabled on heater %u\n", ch);
  return true;
}

// MQTT helpers
void publishStatus(const char* s) {
  char t[48];
  snprintf(t, sizeof(t), "%s/status", DEV_BASE);
  mqtt.publish(t, s, true);
}

void publishTemp(uint8_t ch) {
  char t[48], p[16];
  snprintf(t, sizeof(t), "%s/temp/%u", DEV_BASE, ch);
  dtostrf(tempC[ch], 0, 1, p);
  mqtt.publish(t, p, false);
}

void publishTarget(uint8_t ch) {
  char t[48], p[16];
  snprintf(t, sizeof(t), "%s/target/%u", DEV_BASE, ch);
  dtostrf(setTarget[ch], 0, 1, p);
  mqtt.publish(t, p, true);
}

/************ MQTT connect / callback ************/
void ensureMqtt() {
  if (!eth_ready) return;
  while (!mqtt.connected()) {
    uint32_t id = (uint32_t)ESP.getEfuseMac();
    snprintf(clientId, sizeof(clientId), "heat01-%08X", id);

    Serial.printf("[MQTT] Connecting to %s:%d as %s...\n", MQTT_BROKER_IP, MQTT_PORT, clientId);
    if (mqtt.connect(clientId, MQTT_USER, MQTT_PASS,
                     (String(DEV_BASE) + "/status").c_str(), 1, true, "OFFLINE")) {
      Serial.println("[MQTT] Connected");
      publishStatus("ONLINE");

      char filter[48];
      snprintf(filter, sizeof(filter), "%s/cmd/#", DEV_BASE);
      mqtt.subscribe(filter, 0);
      Serial.printf("[MQTT] Subscribed: %s\n", filter);

      // republish retained state/target on connect
      for (uint8_t i = 1; i <= HEATER_COUNT; i++) {
        _publishState(i);
        if (pidEnabled[i]) publishTarget(i);
      }
    } else {
      Serial.printf("[MQTT] Failed (rc=%d). Retrying...\n", mqtt.state());
      delay(1500);
    }
  }
}

void handleCmd(const char* topic, const char* payload) {
  const char* p = strrchr(topic, '/');
  int ch = (p ? atoi(p + 1) : -1);
  if (!validCh(ch)) {
    Serial.printf("[WARN] Invalid topic: %s\n", topic);
    return;
  }
  Serial.printf("[CMD] ch=%d <- %s\n", ch, payload);

  if (strncasecmp(payload, "PWM:", 4) == 0) {
    int duty = atoi(payload + 4);
    setHeaterPWM(ch, duty);
    return;
  }
  if (strncasecmp(payload, "ON:", 3) == 0) {
    uint32_t ms = atoi(payload + 3);
    if (ms) timedOn(ch, ms);
    return;
  }
  if (strncasecmp(payload, "SET:", 4) == 0) {
    float t = atof(payload + 4);
    setTarget[ch]  = t;
    pidSetpoint[ch]= t;
    publishTarget(ch);
    Serial.printf("[SET] target[%d] = %.1f°C\n", ch, t);
    return;
  }
  if (strcasecmp(payload, "PID:ON") == 0)  { enablePID(ch);  return; }
  if (strcasecmp(payload, "PID:OFF") == 0) { disablePID(ch); return; }
  if (strcasecmp(payload, "ON") == 0)      { setHeater(ch, true);  return; }
  if (strcasecmp(payload, "OFF") == 0)     { setHeater(ch, false); return; }
}

void onMqtt(char* topic, byte* payload, unsigned int len) {
  char msg[64];
  len = (len < sizeof(msg)-1) ? len : sizeof(msg)-1;
  memcpy(msg, payload, len); msg[len] = '\0';
  handleCmd(topic, msg);
}

/************ Ethernet events ************/
void onNetEvent(WiFiEvent_t event) {
  switch (event) {
    case ARDUINO_EVENT_ETH_START:
      ETH.setHostname("esp32-heat");
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
  Serial.println("\n[BOOT] ESP32-POE-ISO heaters (Dual SSR) + PID + thermistor + safety");

  bootMs = millis();

  Wire.begin();
  Wire.setClock(400000);

  // ADS1015
  if (!ads.begin()) {
    Serial.println("[ERROR] ADS1015 not found!");
    lcd.print("Error: ADS1015 not found.");
  } else {
    Serial.println("[I2C] ADS1015 ready");
  }

  // Initialize the LCD
  lcd.begin(Wire);                  // Set up the LCD for I2C communication
  lcd.setBacklight(255, 255, 255);  // Set backlight to bright white
  lcd.setContrast(5);               // Set contrast. Lower to 0 for higher contrast.
  lcd.disableSplash();              // Disables the splash screen
  lcd.clear();                      // Clear the display - this moves the cursor to home position as well
  lcd.print("Booting!");
  Serial.println("[I2C] LCD ready");

  relay_ok = relay.begin();
  if (relay_ok) Serial.println("[I2C] Qwiic Dual SSR ready");
  else          Serial.println("[I2C] Qwiic Dual SSR NOT detected");

  WiFi.onEvent(onNetEvent);
  Serial.println("[ETH] Bringing up Ethernet...");
  ETH.begin(ETH_PHY_TYPE, ETH_PHY_ADDR, ETH_PHY_MDC, ETH_PHY_MDIO, ETH_POWER_PIN, ETH_CLK_MODE);

  // Start OFF
  for (uint8_t i = 1; i <= HEATER_COUNT; i++) {
    heaterIsOn[i] = false;
    _setPWM(i, 0);
    pidEnabled[i] = false;
    setTarget[i]  = 0;
    tempC[i]      = NAN;
    filtTemp[i]   = NAN;
    lastTempVal[i]= NAN;
    lastTempMs[i] = millis();
  }

  // PID controllers
  for (uint8_t i = 1; i <= HEATER_COUNT; i++) {
    pid[i] = new AutoPID(&pidInput[i], &pidSetpoint[i], &pidOutput[i],
                         HEATER_MIN, HEATER_MAX, Kp, Ki, Kd);
    pid[i]->setBangBang(2);     // ±2°C bang-bang assist
    pid[i]->setTimeStep(1000);  // 1 s time step
  }

  mqtt.setServer(MQTT_BROKER_IP, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setKeepAlive(30);

  Serial.println("[BOOT] Setup complete\n");
  lcd.clear();
}

void loop() {
  const uint32_t now = millis();

  write_to_lcd();

  if (eth_ready && !mqtt.connected()) ensureMqtt();
  if (mqtt.connected()) mqtt.loop();

  // --- Read thermistors and filter ---
  float t1, t2;
  bool ok1 = readThermC(TH_CH_1, t1);
  bool ok2 = readThermC(TH_CH_2, t2);
  if (ok1) tempC[1] = t1; else tempC[1] = NAN;
  if (ok2) tempC[2] = t2; else tempC[2] = NAN;

  for (uint8_t ch = 1; ch <= HEATER_COUNT; ch++) {
    if (isfinite(tempC[ch])) {
      filtTemp[ch] = ema(filtTemp[ch], tempC[ch]);  // EMA smoothing
    }
  }

  // --- PID control if enabled ---
  for (uint8_t ch = 1; ch <= HEATER_COUNT; ch++) {
    if (pidEnabled[ch]) {
      if (isfinite(filtTemp[ch])) {
        pidInput[ch] = filtTemp[ch];
        pidSetpoint[ch] = setTarget[ch];
        pid[ch]->run();                       // updates pidOutput[ch]
        _setPWM(ch, (int)pidOutput[ch]);     // use internal setter (doesn't disable PID)
        if (heaterPWM[ch] > 0) lastPwmTime[ch] = now;
      } else {
        _setPWM(ch, 0);                       // sensor bad -> off
      }
    }
  }

  // --- Safety: rate-of-rise brake ---
  for (uint8_t ch = 1; ch <= HEATER_COUNT; ch++) {
    if (!isfinite(filtTemp[ch])) continue;

    // initial settle
    if (now - bootMs < IGNORE_AFTER_BOOT_MS) continue;

    // compute dt
    float dt_s = (now - lastTempMs[ch]) / 1000.0f;
    if (dt_s < MIN_DT_FOR_SLOPE_S) continue;

    bool activelyHeating = pidEnabled[ch] || (now - lastPwmTime[ch] < PWM_MEMORY_MS);
    if (!activelyHeating) {                   // don't brake when idle
      lastTempVal[ch] = filtTemp[ch];
      lastTempMs[ch]  = now;
      continue;
    }

    if (isfinite(lastTempVal[ch])) {
      float dT = (filtTemp[ch] - lastTempVal[ch]) / dt_s;
      if (dT > DT_MAX_C_PER_S) {
        // Brake: cut PWM and open relay
        _setPWM(ch, 0);
        _setOnOff(ch, false);

        if (now - lastBrakeLog[ch] > BRAKE_LOG_DEBOUNCE) {
          lastBrakeLog[ch] = now;
          Serial.printf("[SAFETY] CH%u dT/dt=%.2f C/s too high -> brake\n", ch, dT);
        }
      }
    }
    lastTempVal[ch] = filtTemp[ch];
    lastTempMs[ch]  = now;
  }

  // --- Heartbeat + telemetry ---
  if (mqtt.connected()) {
    if (now - lastBeat > HEARTBEAT_MS) {
      lastBeat = now;
      String tb = String(DEV_BASE) + "/heartbeat";
      mqtt.publish(tb.c_str(), "1");  
    }
    if (now - lastTelem > 3000) {
      lastTelem = now;
      for (uint8_t ch = 1; ch <= HEATER_COUNT; ch++) {
        if (isfinite(filtTemp[ch])) publishTemp(ch);
        if (pidEnabled[ch])        publishTarget(ch);
      }
    }
  }

  // --- Timed OFF handling ---
  for (int i = 0; i < TIMED_SLOTS; i++) {
    if (slots[i].active && now >= slots[i].endMs) {
      setHeater(slots[i].ch, false);   // manual path is fine here
      slots[i].active = false;
      Serial.printf("[TIMER] Heater %u OFF (expired)\n", slots[i].ch);
    }
  }

  // Slight delay to keep dt sane and reduce noise amplification
  delay(20);
}
