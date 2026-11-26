"""Scout AGV — find a wheel's dead zone and the neutral (stop) pulse to put in agv_drive.ino.

WHEELS OFF THE GROUND. Close the Arduino Serial Monitor first.
BEFORE RUNNING: set DEADBAND_US_LEFT and DEADBAND_US_RIGHT to 0 in agv_drive.ino and upload,
otherwise the pulses printed here are wrong. Put the measured values back afterwards.

    python trim.py --port COM5 --wheel right

Steps one wheel through -12..+12 % (the other wheel stays at 0), holding each step 1.5 s.
Watch the wheel and write down the FIRST % where it starts turning on each side.
Then enter those two numbers and the script prints the new NEUTRAL_US value.
"""
import argparse
import sys
import time

import serial

# Mirror of the values in firmware/agv_drive/agv_drive.ino. Keep in sync if you change them there.
NEUTRAL_US = {"left": 1586, "right": 1586}
INVERT = {"left": False, "right": True}
US_PER_PCT = 400 / 100          # FULL_SCALE_US / 100


def pulse_us(wheel: str, pct: int) -> int:
    signed = -pct if INVERT[wheel] else pct
    return round(NEUTRAL_US[wheel] + signed * US_PER_PCT)


def send(ser: serial.Serial, text: str) -> None:
    ser.write((text + "\n").encode("ascii"))


def command(wheel: str, pct: int) -> str:
    return f"V{pct},0" if wheel == "left" else f"V0,{pct}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="e.g. COM5")
    ap.add_argument("--wheel", choices=["left", "right"], required=True)
    ap.add_argument("--range", type=int, default=12, help="sweep from -N to +N percent (max 30)")
    ap.add_argument("--hold", type=float, default=1.5, help="seconds per step")
    args = ap.parse_args()
    span = max(1, min(args.range, 30))

    ser = serial.Serial(args.port, 115200, timeout=0.02)
    print("Opening port resets the Uno; waiting for boot...")
    time.sleep(2.5)
    ser.reset_input_buffer()
    send(ser, "M1*7C")
    time.sleep(0.2)
    if b"OK M1" not in ser.read_all():
        print("Could not arm (no OK M1). Is the Serial Monitor still open? Is the PCA9685 powered?")
        ser.close()
        return 1

    steps = list(range(0, -span - 1, -1)) + list(range(0, span + 1))
    print(f"\nSweeping the {args.wheel} wheel. Watch it and note where it STARTS turning on each side.\n")
    try:
        for pct in steps:
            print(f"  {pct:+4d} %   pulse {pulse_us(args.wheel, pct)} us", flush=True)
            end = time.monotonic() + args.hold
            while time.monotonic() < end:          # resend every 50 ms to keep the deadman fed
                send(ser, command(args.wheel, pct))
                time.sleep(0.05)
                ser.read_all()
            if pct == -span:
                print("  (back to 0, now the other direction)")
    finally:
        send(ser, "V0,0")
        send(ser, "M0")
        time.sleep(0.1)
        ser.close()

    try:
        neg = int(input("\nFirst NEGATIVE % where it turned (e.g. -9): "))
        pos = int(input("First POSITIVE % where it turned (e.g. 2):  "))
    except (ValueError, EOFError):
        print("No numbers entered. Re-run when ready.")
        return 0
    middle_us = round((pulse_us(args.wheel, neg) + pulse_us(args.wheel, pos)) / 2)
    print(f"\nDead zone: {pulse_us(args.wheel, neg)} .. {pulse_us(args.wheel, pos)} us")
    print(f"Set in agv_drive.ino:  NEUTRAL_US_{args.wheel.upper()} = {middle_us};  (was {NEUTRAL_US[args.wheel]})")
    print("Then update NEUTRAL_US in trim.py too, re-upload, and check V0,0 is still and V15,-15 turns both wheels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
