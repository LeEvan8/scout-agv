/*
 * Scout AGV — Phase 1 drive firmware (Arduino Uno + PCA9685 + 2 continuous-rotation servos)
 *
 * The laptop PROPOSES speeds; THIS FIRMWARE DECIDES. It enforces, independently of the host:
 *   - boot e-stop latch (nothing moves until an explicit checksummed arm)
 *   - 250 ms deadman: no valid command -> stop, outputs off, disarmed
 *   - speed cap (MAX_SPEED_PCT) and acceleration limit
 *   - optional ultrasonic stop for forward motion (USE_ULTRASONIC)
 * Same newline-terminated ASCII style and XOR checksum as the Killswitch actuator protocol.
 *
 * Wiring: A4 SDA, A5 SCL, 5V -> PCA9685 VCC, GND common; PCA9685 CH0 = LEFT wheel, CH1 = RIGHT wheel;
 *         motor 5V ONLY on the PCA9685 V+ terminal; D8 -> PCA9685 OE (REQUIRED here: hardware output cut);
 *         optional HC-SR04: TRIG D9, ECHO D10 (set USE_ULTRASONIC 1).
 * Serial: 115200 baud, "Newline".   Library: Adafruit PWM Servo Driver Library.
 *
 * Commands:                                   Replies
 *   M1*7C   arm (checksum REQUIRED)           OK M1
 *   M0      disarm + stop                     OK M0
 *   Z       e-stop (latched until M1*7C)      OK Z
 *   V<l>,<r>  speeds in percent, -100..100    OK V     (clamped to +/-MAX_SPEED_PCT; needs armed)
 *   P       heartbeat                         OK P
 *   S       force a status frame
 *   Status 10 Hz: ST <left%>,<right%>,<armed>,<dist_cm or -1>,<uptime_ms>
 * Errors: ERR E01 unknown verb, E02 bad format, E04 not armed, E05 bad checksum, E07 deadman, E08 e-stop latched.
 */

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>

#define USE_ULTRASONIC 0          // set to 1 once an HC-SR04 is wired (front, facing forward)

// ---------------------------------------------------------------- pins ----
static const uint8_t PIN_OE   = 8;
static const uint8_t PIN_TRIG = 9;
static const uint8_t PIN_ECHO = 10;
static const uint8_t PCA_ADDR = 0x40;
static const uint8_t CH_LEFT  = 0;
static const uint8_t CH_RIGHT = 1;

// ---------------------------------------------------------- tuning knobs ----
static const bool INVERT_LEFT  = false;   // flip if a wheel drives backwards for +speed
static const bool INVERT_RIGHT = true;    // wheels face opposite ways, so one is usually inverted
static const int  NEUTRAL_US_LEFT  = 1586;  // trim until the wheel is perfectly still at 0%
static const int  NEUTRAL_US_RIGHT = 1586;
// Dead-zone compensation: half-width of each servo's "still" band around its neutral, measured
// with trim.py (left 1527..1647, right 1530..1642). Any non-zero speed starts just past this edge,
// so 1 % = barely moving. Top speed is unchanged: MAX_SPEED_PCT still gives the same pulse as
// before (neutral +/- MAX_SPEED_PCT/100 * FULL_SCALE_US). Set both to 0 before re-running trim.py.
static const int  DEADBAND_US_LEFT  = 60;
static const int  DEADBAND_US_RIGHT = 56;
// Straight-line trim: scales the part of each wheel's pulse past its dead band. 1.0 = untouched.
// Only ever LOWER the stronger wheel (max 1.0), so the 30 % cap can never be exceeded.
// Robot curves RIGHT -> left is stronger -> lower GAIN_LEFT. Curves LEFT -> lower GAIN_RIGHT.
static constexpr float GAIN_LEFT  = 0.90f;
static constexpr float GAIN_RIGHT = 1.00f;
static_assert(GAIN_LEFT  > 0.0f && GAIN_LEFT  <= 1.0f, "GAIN_LEFT must be 0..1");
static_assert(GAIN_RIGHT > 0.0f && GAIN_RIGHT <= 1.0f, "GAIN_RIGHT must be 0..1");
static const int  FULL_SCALE_US    = 400;   // pulse swing at 100% (1100..1900 us)
static const int  MAX_SPEED_PCT    = 30;    // HARD cap. Slow on purpose: robot works near people.
static const float ACCEL_PCT_PER_UPDATE = 4.0f;   // per 20 ms = 200 %/s
static const int  STOP_CM          = 25;    // ultrasonic: block pure-forward motion under this

static const unsigned long BAUD               = 115200UL;
static const unsigned long DEADMAN_TIMEOUT_MS = 250UL;
static const unsigned long STATUS_INTERVAL_MS = 100UL;
static const unsigned long DRIVE_UPDATE_MS    = 20UL;
static const size_t RX_BUFFER_SIZE = 40;

// --------------------------------------------------------------- state ----
Adafruit_PWMServoDriver pwm(PCA_ADDR);

static float targetL = 0, targetR = 0, currentL = 0, currentR = 0;
static bool armed = false;
static bool estopLatched = true;     // boot latched
static bool deadmanFired = false;
static bool pcaOk = false;
static int  distanceCm = -1;

static unsigned long lastCommandMs = 0, lastStatusMs = 0, lastDriveMs = 0, lastRangeMs = 0;
static char rxBuffer[RX_BUFFER_SIZE];
static size_t rxLength = 0;

// ---------------------------------------------------------------- drive ----
static uint16_t usToTicks(int us) { return (uint16_t)(((long)us * 4096L) / 20000L); }   // 50 Hz

static float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

// pct in -MAX_SPEED_PCT..MAX_SPEED_PCT -> pulse. 0 -> neutral; otherwise jump past the dead band,
// then scale linearly so |pct| == MAX_SPEED_PCT lands on the same top pulse as without compensation.
static void writeWheel(uint8_t ch, float pct, bool invert, int neutral, int deadband, float gain) {
  if (invert) pct = -pct;
  pct = clampf(pct, -MAX_SPEED_PCT, MAX_SPEED_PCT);
  const float topUs = (MAX_SPEED_PCT / 100.0f) * FULL_SCALE_US;      // 120 us at 30 %
  const float mag = pct < 0 ? -pct : pct;
  int offset = 0;
  if (mag >= 0.5f) {
    offset = (int)(deadband + gain * (mag / MAX_SPEED_PCT) * (topUs - deadband));
    if (pct < 0) offset = -offset;
  }
  pwm.setPWM(ch, 0, usToTicks(neutral + offset));
}

static void writeNeutral() {
  writeWheel(CH_LEFT, 0, INVERT_LEFT, NEUTRAL_US_LEFT, DEADBAND_US_LEFT, GAIN_LEFT);
  writeWheel(CH_RIGHT, 0, INVERT_RIGHT, NEUTRAL_US_RIGHT, DEADBAND_US_RIGHT, GAIN_RIGHT);
}

/* Stop everything NOW: neutral pulses, then cut the PCA9685 outputs in hardware (OE high). */
static void safeState() {
  targetL = targetR = currentL = currentR = 0;
  if (pcaOk) writeNeutral();
  digitalWrite(PIN_OE, HIGH);
  armed = false;
}

static void emitError(const char* code, const char* detail) {
  Serial.print(F("ERR ")); Serial.print(code); Serial.print(' '); Serial.println(detail);
}

// ------------------------------------------------------------- checksum ----
static uint8_t computeChecksum(const char* body, size_t length) {
  uint8_t acc = 0;
  for (size_t i = 0; i < length; i++) acc ^= (uint8_t)body[i];
  return acc;
}

static bool verifyChecksum(char* line, size_t length, size_t* bodyLength) {
  char* star = nullptr;
  for (size_t i = 0; i < length; i++) if (line[i] == '*') { star = &line[i]; break; }
  if (star == nullptr) return false;
  *bodyLength = (size_t)(star - line);
  if (length - *bodyLength - 1 < 2) return false;
  char hex[3] = { star[1], star[2], '\0' };
  return (uint8_t)strtoul(hex, nullptr, 16) == computeChecksum(line, *bodyLength);
}

static bool parseSpeeds(const char* body, size_t length, float* l, float* r) {
  char work[RX_BUFFER_SIZE];
  if (length >= RX_BUFFER_SIZE) return false;
  memcpy(work, body, length);
  work[length] = '\0';
  char* comma = strchr(work + 1, ',');
  if (comma == nullptr) return false;
  *comma = '\0';
  char* e1 = nullptr; char* e2 = nullptr;
  float a = (float)strtod(work + 1, &e1);
  float b = (float)strtod(comma + 1, &e2);
  if (e1 == work + 1 || e2 == comma + 1) return false;
  if (isnan(a) || isnan(b) || isinf(a) || isinf(b)) return false;
  *l = a; *r = b;
  return true;
}

static void handleCommand(char* line, size_t length) {
  if (length == 0) return;
  const char verb = line[0];

  if (verb == 'Z') {                 // e-stop first, no validation
    safeState();
    estopLatched = true;
    lastCommandMs = millis();
    Serial.println(F("OK Z"));
    return;
  }

  size_t bodyLength = length;
  const bool checksummed = verifyChecksum(line, length, &bodyLength);

  switch (verb) {
    case 'P':
      lastCommandMs = millis();
      deadmanFired = false;
      Serial.println(F("OK P"));
      return;
    case 'S':
      lastCommandMs = millis();
      lastStatusMs = 0;
      return;
    case 'M': {
      if (bodyLength < 2) { emitError("E02", "M needs 0 or 1"); return; }
      if (line[1] != '1') {            // disarm always honoured
        safeState();
        lastCommandMs = millis();
        Serial.println(F("OK M0"));
        return;
      }
      if (!checksummed) { emitError("E05", "M1 requires checksum"); return; }
      if (!pcaOk)       { emitError("E02", "PCA9685 not found"); return; }
      estopLatched = false;
      armed = true;
      targetL = targetR = currentL = currentR = 0;
      writeNeutral();
      digitalWrite(PIN_OE, LOW);       // outputs enabled only while armed
      lastCommandMs = millis();
      deadmanFired = false;
      Serial.println(F("OK M1"));
      return;
    }
    case 'V': {
      float l, r;
      if (!parseSpeeds(line, bodyLength, &l, &r)) { emitError("E02", "speed parse failed"); return; }
      if (estopLatched) { emitError("E08", "e-stop latched"); return; }
      if (!armed)       { emitError("E04", "not armed; send M1*7C first"); return; }
      targetL = clampf(l, -MAX_SPEED_PCT, MAX_SPEED_PCT);
      targetR = clampf(r, -MAX_SPEED_PCT, MAX_SPEED_PCT);
      lastCommandMs = millis();
      deadmanFired = false;
      Serial.println(F("OK V"));
      return;
    }
    default:
      emitError("E01", "unknown verb");
      return;
  }
}

// --------------------------------------------------------------- safety ----
static void checkDeadman() {
  if (!armed) return;
  if (millis() - lastCommandMs <= DEADMAN_TIMEOUT_MS) return;
  safeState();
  if (!deadmanFired) { emitError("E07", "deadman timeout: stopped, disarmed"); deadmanFired = true; }
}

#if USE_ULTRASONIC
static void readRange() {
  if (millis() - lastRangeMs < 100) return;
  lastRangeMs = millis();
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  const unsigned long us = pulseIn(PIN_ECHO, HIGH, 6000UL);   // <= ~1 m, blocks max 6 ms
  distanceCm = (us == 0) ? 999 : (int)(us / 58UL);            // 999 = nothing within range
}
#endif

static void updateDrive() {
  const unsigned long now = millis();
  if (now - lastDriveMs < DRIVE_UPDATE_MS) return;
  lastDriveMs = now;
  if (!armed) return;

  float tL = targetL, tR = targetR;
#if USE_ULTRASONIC
  if (distanceCm > 0 && distanceCm < STOP_CM && tL > 0 && tR > 0) { tL = 0; tR = 0; }  // pure-forward block
#endif
  currentL += clampf(tL - currentL, -ACCEL_PCT_PER_UPDATE, ACCEL_PCT_PER_UPDATE);
  currentR += clampf(tR - currentR, -ACCEL_PCT_PER_UPDATE, ACCEL_PCT_PER_UPDATE);
  writeWheel(CH_LEFT,  currentL, INVERT_LEFT,  NEUTRAL_US_LEFT,  DEADBAND_US_LEFT,  GAIN_LEFT);
  writeWheel(CH_RIGHT, currentR, INVERT_RIGHT, NEUTRAL_US_RIGHT, DEADBAND_US_RIGHT, GAIN_RIGHT);
}

static void sendStatus() {
  const unsigned long now = millis();
  if (now - lastStatusMs < STATUS_INTERVAL_MS) return;
  lastStatusMs = now;
  Serial.print(F("ST "));
  Serial.print((int)lroundf(currentL)); Serial.print(',');
  Serial.print((int)lroundf(currentR)); Serial.print(',');
  Serial.print(armed ? '1' : '0');      Serial.print(',');
  Serial.print(distanceCm);             Serial.print(',');
  Serial.println(now);
}

static void pumpSerial() {
  while (Serial.available() > 0) {
    const char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxLength > 0) { rxBuffer[rxLength] = '\0'; handleCommand(rxBuffer, rxLength); rxLength = 0; }
      continue;
    }
    if (rxLength < RX_BUFFER_SIZE - 1) rxBuffer[rxLength++] = c;
    else { rxLength = 0; emitError("E02", "rx overflow, line discarded"); }
  }
}

// ---------------------------------------------------------------- setup ----
void setup() {
  pinMode(PIN_OE, OUTPUT);
  digitalWrite(PIN_OE, HIGH);        // outputs OFF until armed
#if USE_ULTRASONIC
  pinMode(PIN_TRIG, OUTPUT); digitalWrite(PIN_TRIG, LOW);
  pinMode(PIN_ECHO, INPUT);
#endif
  Serial.begin(BAUD);
  Wire.begin();
#ifdef WIRE_HAS_TIMEOUT
  Wire.setWireTimeout(3000, true);
#endif
  Wire.beginTransmission(PCA_ADDR);
  pcaOk = (Wire.endTransmission() == 0);
  if (pcaOk) {
    pwm.begin();
    pwm.setOscillatorFrequency(27000000);
    pwm.setPWMFreq(50);
    delay(10);
    writeNeutral();
  }
  lastCommandMs = millis();
  Serial.print(F("OK BOOT killswitch-agv-drive v1.2-gain"));
  Serial.println(pcaOk ? F(" pwm=ok") : F(" PCA9685 NOT FOUND"));
}

void loop() {
  pumpSerial();
  checkDeadman();       // safety decisions before actuation
#if USE_ULTRASONIC
  readRange();
#endif
  updateDrive();
  sendStatus();
}
