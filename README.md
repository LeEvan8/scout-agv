# Scout AGV (Phase 1 complete)

## 1. Upload the firmware
Open `firmware/agv_drive/agv_drive.ino` in the Arduino IDE (needs the Adafruit PWM Servo Driver library),
choose Board = Arduino Uno and your port, then Upload.
Already set for this robot (firmware v1.4-dither): neutral 1586 / 1586 us, dead-zone compensation 60 / 56 us,
straight-line trim GAIN_LEFT 1.00, speed cap 30 %, deadman 250 ms. Every servo is different: re-measure yours
with `trim.py` (see PHASE1.md) before trusting these numbers.
Close the Serial Monitor afterwards (only one program can use the port).

Speed levels in teleop: 1 = slow, 2 = medium, 3 = fast (the 30 % cap).

## Bench checks
    python bench_test.py --port COM5    (wheels off the ground: deadman, e-stop, speed cap -> PASS/FAIL)
    python trim.py --port COM5 --wheel left --range 30   (find a wheel's neutral; set DEADBAND_US_* to 0 first)

## 2. Set up Python (Windows PowerShell, once)
    cd scout-agv
    py -3.12 -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

(Mac/Linux: `python3 -m venv .venv && source .venv/bin/activate`)

## 3. Drive
    python teleop.py --port COM5      (use your Uno's port; Mac: /dev/cu.usbmodem..., Linux: /dev/ttyUSB0)

A small window opens. Click it so it has focus, then:
R = arm, W/S = forward/back, A/D = turn, 1/2/3 = speed, SPACE = e-stop, ESC = quit.
Keep the wheels off the ground for the first run.

Find your port number: Arduino IDE > Tools > Port, or Windows Device Manager > Ports.
