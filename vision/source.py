"""Frame source: laptop webcam now, ESP32 MJPEG URL later. Same interface for both.

A background thread keeps grabbing so we always process the NEWEST frame (no queue building up
behind a slow detector). Each frame carries the time it arrived, so callers can refuse to act on
stale images (Wi-Fi lag). Nothing is ever written to disk.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Frame:
    image: np.ndarray       # BGR
    stamp: float            # time.monotonic() when it arrived
    index: int              # increases by 1 per new frame

    @property
    def age(self) -> float:
        return time.monotonic() - self.stamp


class FrameSource:
    """`FrameSource("0")` = webcam 0, `FrameSource("http://cam.local/stream")` = MJPEG stream."""

    def __init__(self, source: str, width: int = 640, height: int = 480):
        self.source = source
        self.width, self.height = width, height
        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._latest: Frame | None = None
        self._count = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self.status = "starting"

    def _open(self) -> cv2.VideoCapture:
        if self.source.isdigit():
            cap = cv2.VideoCapture(int(self.source), cv2.CAP_DSHOW)   # DirectShow opens fast on Windows
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        else:
            cap = cv2.VideoCapture(self.source)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def start(self) -> "FrameSource":
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="frame-source", daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                self.status = f"connecting to {self.source}"
                self._cap = self._open()
                if not self._cap.isOpened():
                    time.sleep(1.0)        # camera busy / stream down: retry
                    continue
            ok, image = self._cap.read()
            if not ok or image is None:
                self.status = "no frames, reconnecting"
                self._cap.release()
                self._cap = None
                time.sleep(0.5)
                continue
            self.status = "ok"
            with self._lock:
                self._count += 1
                self._latest = Frame(image, time.monotonic(), self._count)

    def latest(self) -> Frame | None:
        with self._lock:
            return self._latest

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap is not None:
            self._cap.release()
