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

## Firmware (firmware/agv_drive/agv_drive.ino) — Phase 1 COMPLETE (v1.4-dither, 2026-11-26)
Serial ASCII, newline-terminated: `M1*7C` arm (XOR checksum), `M0` disarm, `Z` e-stop, `V<l>,<r>` speed % (-100..100),
`P` ping, `S` status. Replies `OK ..`, `ERR Exx ..`, status frames `ST <l>,<r>,<armed>,<dist>,<uptime>`.
Boots e-stopped. 250 ms deadman (ERR E07). Speed hard-capped at MAX_SPEED_PCT 30. Accel-limited.
**Only V (and M1 arming) feed the deadman; P and S do NOT.** Any host app must stream V (teleop does, 20 Hz).
Over-long serial lines (>39 chars) are dropped up to their newline.
Calibrated: NEUTRAL_US_LEFT 1586, NEUTRAL_US_RIGHT 1586 (stop points were far from 1500; re-trim at V0,0 if a wheel creeps).
Dead-zone compensation: DEADBAND_US_LEFT 60, DEADBAND_US_RIGHT 56 (half-width of the still band); 1 % = just moving.
Set both to 0 before re-running trim.py.
Straight-line trim: GAIN_LEFT 1.00, GAIN_RIGHT 1.00 (scale the part past the dead band; never above 1.0, static_assert).
Sub-step dithering makes 0.01 gain steps real (without it 0.90-0.97 gave identical pulses). Offset clamped to 24 PCA9685
ticks (= 30 % cap), so at level 3 both wheels sit on the ceiling and gain has no effect; tune at levels 1-2.
Right servo is very slightly stronger; residual drift accepted (teacher steers; Phase 2 tracking corrects).
If needed later: GAIN_RIGHT 0.99 / 0.98.
Verified on hardware 2026-11-26: bench_test.py 4/4, V0,0 still, directions, teleop levels 1-3, USB-unplug stop,
P does not keep it driving (E07), overflow line ignored, floor drive.

## Phase 2 notes
- Uno is on COM57 (CH340 clone). Python: `.venv\Scripts\python.exe` (3.12).
- The app's drive loop must send V at >= 10 Hz from the SAME loop that decides motion, never from a separate
  keep-alive thread, so a frozen vision/control loop stops the robot.
- Laptop: i7-8550U, Intel UHD 620 (no CUDA) -> CPU inference. Webcam 0 = Integrated (25 fps), 1 = AX USB2.0 (10 fps).
- vision/ (2a, built 2026-11-26): source.py (threaded newest-frame grabber, frame age), detector.py (YOLO11n-pose ONNX,
  letterbox + NMS; matches ultralytics output within 0.05 px), head.py (face kpts -> weak face + shoulders ->
  shoulders -> box top; non-face = "est."), tracker.py (IoU tracks, confirm 3 of 5 frames), overlay.py.
  Speed: 640 model ~66 ms (15 fps), 416 model ~24 ms (41 fps). Demo: vision_demo.py --source 0|URL.
- models/*.onnx are git-ignored; recreate with tools/export_model.py in a throwaway venv (needs torch).
- LICENSE RISK: YOLO11 weights/code are AGPL-3.0. Fine for a public AGPL repo / testing; commercial product needs an
  Ultralytics license or a permissively licensed model (decide before pilot/sales).
- Auto-tracking decision (2026-11-26): turn in place only, level-1 speed, only while teacher holds T; stop on target
  lost, stale frame, or SPACE.

## Rules — do not break these
- Never raise MAX_SPEED_PCT, remove/lengthen the deadman (keep 250 ms), or bypass the checksummed arm without asking me.
- The host proposes, the firmware decides: all safety lives in the Uno, not in Python.
- Robot operates near children: slow, soft, e-stop always reachable. No weapon-like features. No video recording by default;
  video stays on the local network. No face identification — only "a person is here".
- Show detection "confidence", not a calibrated probability. Use multi-frame persistence to cut false positives.
- Python 3.12 venv (3.15 lacks onnxruntime wheels). Windows + PowerShell. Keep dependencies minimal.
- Tell me what you changed and how to test it on hardware; I run hardware tests and report back.

## Roadmap
1. Phase 1 drive + safety — COMPLETE 2026-11-26 (fw v1.4-dither)
2. Camera + vision on laptop: stream -> YOLO11-pose -> green head box + confidence -> state machine
   SEARCH -> DETECTED -> TRACKING -> CAUGHT; teacher UI with drive keys and a "Student caught" button
3. Reliability: lighting, clutter, false positives, battery life, IMU (MPU6050) optional
4. Pilot with real teachers, then startup validation

## Run
    py -3.12 -m venv .venv ; .venv\Scripts\activate ; pip install -r requirements.txt
    .venv\Scripts\python.exe teleop.py --port COM57      (R arm, WASD drive, 1/2/3 speed, SPACE e-stop, ESC quit)
