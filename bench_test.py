"""Scout AGV phase 1 — automatic bench test for PHASE1.md steps 4-6 (deadman, e-stop, speed cap).

WHEELS OFF THE GROUND. Close the Arduino Serial Monitor first (only one program can use the port).

    python bench_test.py --port COM5

Prints PASS/FAIL per test. The wheels will spin briefly at low speed and at the 30 % cap.
"""
import argparse
import sys
import time

import serial

ARM = "M1*7C"


def send(ser: serial.Serial, text: str) -> None:
    ser.write((text + "\n").encode("ascii"))


_pending = ""


def next_line(ser: serial.Serial) -> str | None:
    """Return one complete line from the Uno, or None if none has fully arrived yet."""
    global _pending
    if "\n" not in _pending:
        _pending += ser.read(max(1, ser.in_waiting)).decode("ascii", "replace")
    if "\n" not in _pending:
        return None
    line, _pending = _pending.split("\n", 1)
    return line.strip() or None


def flush_input(ser: serial.Serial) -> None:
    global _pending
    ser.reset_input_buffer()
    _pending = ""


def read_lines(ser: serial.Serial, seconds: float) -> list[str]:
    """Collect every line the Uno sends during `seconds`."""
    lines = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        line = next_line(ser)
        if line:
            lines.append(line)
    return lines


def wait_for(ser: serial.Serial, prefix: str, timeout: float) -> tuple[str | None, float]:
    """Wait for a line starting with `prefix`. Returns (line, seconds waited) or (None, timeout)."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        line = next_line(ser)
        if line and line.startswith(prefix):
            return line, time.monotonic() - start
    return None, timeout


def arm(ser: serial.Serial) -> bool:
    flush_input(ser)
    send(ser, ARM)
    line, _ = wait_for(ser, "OK M1", 1.0)
    return line is not None


def stop(ser: serial.Serial) -> None:
    send(ser, "V0,0")
    send(ser, "M0")
    read_lines(ser, 0.3)


def report(name: str, ok: bool, detail: str) -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def test_arm_needs_checksum(ser: serial.Serial) -> bool:
    flush_input(ser)
    send(ser, "M1")
    line, _ = wait_for(ser, "ERR", 1.0)
    ok = line is not None and "E05" in line
    return report("arm without checksum is refused", ok, line or "no reply")


def test_deadman(ser: serial.Serial) -> bool:
    if not arm(ser):
        return report("deadman", False, "could not arm (no OK M1)")
    send(ser, "V15,15")
    line, waited = wait_for(ser, "ERR E07", 2.0)
    ms = waited * 1000
    ok = line is not None and 200 <= ms <= 450
    detail = f"stopped after {ms:.0f} ms (expect ~250)" if line else "no ERR E07 within 2 s"
    return report("deadman stops the wheels", ok, detail)


def test_estop(ser: serial.Serial) -> bool:
    if not arm(ser):
        return report("e-stop", False, "could not arm (no OK M1)")
    for _ in range(10):                      # drive 0.5 s, keeping the deadman fed
        send(ser, "V15,15")
        time.sleep(0.05)
    flush_input(ser)
    send(ser, "Z")
    got_z, _ = wait_for(ser, "OK Z", 1.0)
    send(ser, "V15,15")
    latched, _ = wait_for(ser, "ERR E08", 1.0)
    rearmed = arm(ser)
    stop(ser)
    ok = bool(got_z and latched and rearmed)
    detail = f"OK Z={'yes' if got_z else 'no'}, latched E08={'yes' if latched else 'no'}, re-arm={'yes' if rearmed else 'no'}"
    return report("e-stop stops and latches", ok, detail)


def test_speed_cap(ser: serial.Serial) -> bool:
    if not arm(ser):
        return report("speed cap", False, "could not arm (no OK M1)")
    speeds = []
    end = time.monotonic() + 1.5
    while time.monotonic() < end:            # ask for 100 %, 20 times a second
        send(ser, "V100,100")
        for line in read_lines(ser, 0.05):
            if line.startswith("ST "):
                left, right = line[3:].split(",")[:2]
                speeds += [abs(int(left)), abs(int(right))]
    stop(ser)
    top = max(speeds, default=0)
    ok = top == 30
    return report("speed cap holds at 30 %", ok, f"highest reported speed {top} % from {len(speeds) // 2} status frames")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="e.g. COM5")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.02)
    print("Opening port resets the Uno; waiting for boot...")
    time.sleep(2.5)
    boot = " ".join(read_lines(ser, 0.3))
    print(boot or "(no boot text)")
    if "pwm=ok" not in boot:
        print("PCA9685 not reported OK. Check wiring and power, then retry.")
        ser.close()
        return 1

    results = []
    try:
        results.append(test_arm_needs_checksum(ser))
        results.append(test_deadman(ser))
        results.append(test_estop(ser))
        results.append(test_speed_cap(ser))
    finally:
        stop(ser)
        ser.close()

    print(f"\n{sum(results)}/{len(results)} passed.")
    if all(results):
        print("Next: python teleop.py --port", args.port, "(PHASE1.md step 7), then the USB-unplug test (step 8).")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
