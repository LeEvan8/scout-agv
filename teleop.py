"""Scout AGV phase 1 — keyboard teleop with heartbeat.

Controls (window must be focused):  W/S forward/back, A/D turn, 1/2/3 speed, SPACE e-stop, R re-arm, ESC quit.
The script sends a drive command 20 times a second; if it dies or you unplug the cable, the Uno
stops the robot within 250 ms on its own (deadman).

    pip install pyserial pygame
    python teleop.py --port COM5
"""
import argparse
import sys
import time

import pygame
import serial


def checksum(body: str) -> str:
    acc = 0
    for ch in body:
        acc ^= ord(ch)
    return f"{acc:02X}"


def send(ser: serial.Serial, body: str, hazard: bool = False) -> None:
    text = f"{body}*{checksum(body)}" if hazard else body
    ser.write((text + "\n").encode("ascii"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.01)
    print("Opening port resets the Uno; waiting for boot...")
    time.sleep(2.5)
    boot = ser.read_all().decode("ascii", "replace")
    print(boot.strip() or "(no boot text yet)")

    pygame.init()
    screen = pygame.display.set_mode((520, 240))
    pygame.display.set_caption("Scout AGV teleop")
    font = pygame.font.SysFont("consolas", 18)

    speed_levels = {pygame.K_1: 10, pygame.K_2: 20, pygame.K_3: 30}
    speed = 10
    status = "no status yet"
    last_reply = ""
    send(ser, "M1", hazard=True)          # arm (checksummed)

    clock = pygame.time.Clock()
    running = True
    try:
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        running = False
                    elif ev.key == pygame.K_SPACE:
                        send(ser, "Z")
                    elif ev.key == pygame.K_r:
                        send(ser, "M1", hazard=True)
                    elif ev.key in speed_levels:
                        speed = speed_levels[ev.key]

            keys = pygame.key.get_pressed()
            fwd = (keys[pygame.K_w] or keys[pygame.K_UP]) - (keys[pygame.K_s] or keys[pygame.K_DOWN])
            turn = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
            left = max(-1.0, min(1.0, fwd + turn)) * speed
            right = max(-1.0, min(1.0, fwd - turn)) * speed
            send(ser, f"V{left:.0f},{right:.0f}")

            for line in ser.read_all().decode("ascii", "replace").splitlines():
                if line.startswith("ST "):
                    status = line
                elif line.strip():
                    last_reply = line.strip()

            screen.fill((24, 28, 34))
            rows = [
                f"speed cap on host: {speed}%   (firmware cap applies too)",
                f"cmd: L={left:.0f}  R={right:.0f}",
                status,
                f"last: {last_reply}",
                "W/S fwd/back  A/D turn  1/2/3 speed",
                "SPACE e-stop   R re-arm   ESC quit",
            ]
            for i, row in enumerate(rows):
                screen.blit(font.render(row, True, (230, 230, 230)), (12, 12 + i * 32))
            pygame.display.flip()
            clock.tick(20)
    finally:
        try:
            send(ser, "V0,0")
            send(ser, "M0")
        finally:
            ser.close()
            pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
