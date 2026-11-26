"""Runs camera -> detector -> tracker in a background thread and publishes the newest result.

The app's main loop (30 Hz) reads `latest()` and checks `frame_stamp`: it must never steer the robot
from an old result. If this thread stalls, the result simply gets old and the app stops auto-motion.
"""
from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass

import numpy as np

from .detector import PoseDetector
from .source import FrameSource
from .tracker import PersonTracker, Track


@dataclass
class VisionResult:
    image: np.ndarray        # the frame the tracks belong to (BGR, not drawn on)
    frame_index: int
    frame_stamp: float       # time.monotonic() when the camera frame arrived
    tracks: list[Track]      # snapshots, safe to read from another thread
    detect_ms: float
    fps: float

    @property
    def age(self) -> float:
        return time.monotonic() - self.frame_stamp


class VisionWorker:
    def __init__(self, source: FrameSource, detector: PoseDetector):
        self.source, self.detector = source, detector
        self.tracker = PersonTracker()
        self._lock = threading.Lock()
        self._result: VisionResult | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> "VisionWorker":
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="vision", daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        last_index, fps, t_prev = -1, 0.0, time.perf_counter()
        while self._running:
            frame = self.source.latest()
            if frame is None or frame.index == last_index:
                time.sleep(0.003)
                continue
            last_index = frame.index
            t0 = time.perf_counter()
            tracks = self.tracker.update(self.detector.detect(frame.image))
            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-3)
            t_prev = now
            snap = [copy.copy(t) for t in tracks]          # tracker replaces box arrays, never edits them
            with self._lock:
                self._result = VisionResult(frame.image, frame.index, frame.stamp, snap, (now - t0) * 1000, fps)

    def latest(self) -> VisionResult | None:
        with self._lock:
            return self._result

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
