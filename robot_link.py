"""Serial link to the Uno (firmware agv_drive.ino). Never blocks the caller's loop.

The firmware makes every safety decision; this class only sends what the app asks for and reports
what the Uno says. Opening the port resets the Uno, which boots e-stopped, so a reconnect is safe.
The Uno must be ARMED explicitly (arm()); this class never arms on its own.
"""
from __future__ import annotations

import time

import serial

BOOT_WAIT_S = 2.2          # Uno resets when the port opens; ignore it until the bootloader is done
RECONNECT_S = 2.0
STATUS_TIMEOUT_S = 1.0     # firmware sends ST at 10 Hz; silence longer than this = link problem


def checksummed(body: str) -> str:
    acc = 0
    for ch in body:
        acc ^= ord(ch)
    return f"{body}*{acc:02X}"


class RobotLink:
    def __init__(self, port: str | None, baud: int = 115200):
        self.port, self.baud = port, baud
        self.ser: serial.Serial | None = None
        self.opened_at = 0.0
        self.last_attempt = -RECONNECT_S
        self.last_rx = 0.0
        self._pending = ""
        self.armed = False
        self._arm_sent = 0.0
        self.speed_l = self.speed_r = 0
        self.boot_line = ""
        self.last_reply = ""
        self.last_error = ""
        self.problem = "" if port else "no --port given (vision only)"

    # ---------------------------------------------------------------- state
    @property
    def ready(self) -> bool:
        return self.ser is not None and time.monotonic() - self.opened_at >= BOOT_WAIT_S

    @property
    def alive(self) -> bool:
        return self.ready and time.monotonic() - self.last_rx < STATUS_TIMEOUT_S

    # ---------------------------------------------------------------- io
    def _connect(self) -> None:
        self.last_attempt = time.monotonic()
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0, write_timeout=0.05)
            self.opened_at = time.monotonic()
            self._pending, self.armed, self.problem = "", False, ""
        except (serial.SerialException, OSError) as exc:
            self.ser = None
            self.problem = f"cannot open {self.port}: {exc.__class__.__name__}"

    def _drop(self, why: str) -> None:
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser, self.armed, self.problem = None, False, why

    def _send(self, text: str) -> None:
        if not self.ready:
            return
        try:
            self.ser.write((text + "\n").encode("ascii"))
        except serial.SerialTimeoutException:
            pass                                    # skip this one; the next loop sends again
        except (serial.SerialException, OSError):
            self._drop("cable unplugged? reconnecting")

    def poll(self) -> None:
        """Call every loop: reconnects, reads replies and status frames."""
        if not self.port:
            return
        if self.ser is None:
            if time.monotonic() - self.last_attempt >= RECONNECT_S:
                self._connect()
            return
        try:
            data = self.ser.read(self.ser.in_waiting or 1)
        except (serial.SerialException, OSError):
            self._drop("cable unplugged? reconnecting")
            return
        if not data:
            return
        self._pending += data.decode("ascii", "replace")
        *lines, self._pending = self._pending.split("\n")
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            self.last_rx = time.monotonic()
            if line.startswith("ST "):
                parts = line[3:].split(",")
                if len(parts) >= 3:
                    try:
                        self.speed_l, self.speed_r = int(parts[0]), int(parts[1])
                        self.armed = parts[2] == "1"
                    except ValueError:
                        pass
            elif line.startswith("OK BOOT"):
                self.boot_line = line
            elif line.startswith("ERR"):
                self.last_error = line
            elif line != "OK V":                    # OK V arrives 30x/s; not worth showing
                self.last_reply = line

    # ---------------------------------------------------------------- commands
    def arm(self) -> None:
        self.last_error = ""
        self._arm_sent = time.monotonic()
        self._send(checksummed("M1"))

    def estop(self) -> None:
        self.armed = False
        self._arm_sent = 0.0
        self._send("Z")

    def drive(self, left: float, right: float) -> None:
        """Send V only while armed (or just after arm(), before the next ST frame confirms it).
        Disarmed, V would only earn ERR E04/E08 thirty times a second."""
        if self.armed or time.monotonic() - self._arm_sent < 0.5:
            self._send(f"V{left:.0f},{right:.0f}")

    def close(self) -> None:
        if self.ser is not None:
            try:
                self.ser.write(b"V0,0\nM0\n")
                self.ser.flush()
            except Exception:
                pass
            self._drop("closed")
