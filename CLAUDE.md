# Scout AGV — project memory for Claude Code

## What this is
A small remote-controlled scout robot for a school hide-and-seek game. A teacher drives it into a room from a laptop.
Computer vision finds hiding students, draws a GREEN box around the head with a confidence %, and tracks the person
until the teacher clicks "Student caught". Startup MVP; user is a student founder, hardware beginner.

## Hardware (see docs/wiring_diagram.png)
- Arduino Uno R3 (5V logic, 115200 baud) -> PCA9685 over I2C (A4 SDA, A5 SCL, addr 0x40, 50 Hz).
- Two continuous-rotation MG996R servos as wheels: CH0 = left, CH1 = right. Open loop, no encoders.
- D8 -> PCA9685 OE (HIGH = all motor outputs off) with a 10k pull-up to VCC. Optional HC-SR04: D9 TRIG, D10 ECHO.
- Motor power: 5V >=3A battery -> power switch -> PCA9685 V+ terminal. Uno 5V only feeds logic. Grounds common.
- Camera node (separate, Wi-Fi only): ESP32-S3 OV5640 streaming MJPEG now; ESP32-P4-EYE planned later.

## Firmware (firmware/agv_drive/agv_drive.ino) — Phase 1 DONE on the bench
Serial ASCII, newline-terminated: `M1*7C` arm (XOR checksum), `M0` disarm, `Z` e-stop, `V<l>,<r>` speed % (-100..100),
`P` ping, `S` status. Replies `OK ..`, `ERR Exx ..`, status frames `ST <l>,<r>,<armed>,<dist>,<uptime>`.
Boots e-stopped. 250 ms deadman (ERR E07). Speed hard-capped at MAX_SPEED_PCT 30. Accel-limited.
Calibrated: NEUTRAL_US_LEFT 1586, NEUTRAL_US_RIGHT 1586 (stop points were far from 1500; re-trim at V0,0 if a wheel creeps).
Dead-zone compensation: DEADBAND_US_LEFT 60, DEADBAND_US_RIGHT 56 (half-width of the still band); 1 % = just moving,
30 % = same top pulse as without it. Set both to 0 before re-running trim.py.
Straight-line trim: GAIN_LEFT 0.90, GAIN_RIGHT 1.00 (scale the part past the dead band; never above 1.0). Fw v1.2-gain.
Left servo is stronger on the floor; 0.90 is a first guess, tune on the floor.
INVERT_LEFT / INVERT_RIGHT: confirm on the real robot (forward = both wheels push robot forward).
Compiled, uploaded and bench_test.py 4/4 PASS on 2026-11-26 (deadman 250 ms, e-stop latch, checksum arm, 30 % cap).
Teleop (wheels up, levels 1-3), USB-unplug stop and dead-zone compensation (fw v1.1-deadband) OK 2026-11-26.
Not yet verified: floor drive, drift
(left servo slightly stronger on the bench).

## Rules — do not break these
- Never raise MAX_SPEED_PCT, remove/lengthen the deadman (keep 250 ms), or bypass the checksummed arm without asking me.
- The host proposes, the firmware decides: all safety lives in the Uno, not in Python.
- Robot operates near children: slow, soft, e-stop always reachable. No weapon-like features. No video recording by default;
  video stays on the local network. No face identification — only "a person is here".
- Show detection "confidence", not a calibrated probability. Use multi-frame persistence to cut false positives.
- Python 3.12 venv (3.15 lacks onnxruntime wheels). Windows + PowerShell. Keep dependencies minimal.
- Tell me what you changed and how to test it on hardware; I run hardware tests and report back.

## Roadmap
1. Phase 1 drive + safety (bench done; floor test pending)
2. Camera + vision on laptop: stream -> YOLO11-pose -> green head box + confidence -> state machine
   SEARCH -> DETECTED -> TRACKING -> CAUGHT; teacher UI with drive keys and a "Student caught" button
3. Reliability: lighting, clutter, false positives, battery life, IMU (MPU6050) optional
4. Pilot with real teachers, then startup validation

## Run
    py -3.12 -m venv .venv ; .venv\Scripts\activate ; pip install -r requirements.txt
    .venv\Scripts\python.exe teleop.py --port COM57      (R arm, WASD drive, 1/2/3 speed, SPACE e-stop, ESC quit)
