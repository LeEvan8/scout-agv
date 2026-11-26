"""Multi-frame persistence: a person only counts once seen in CONFIRM_HITS of the last WINDOW frames.

Cuts one-frame false positives (a coat on a chair, a poster). Tracks are matched frame to frame by
box overlap (IoU); IDs are only "track 1, track 2" in this session, never a student's identity.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .detector import Detection
from .head import head_box

WINDOW = 5           # look at the last 5 processed frames
CONFIRM_HITS = 3     # ... and need a hit in 3 of them
MAX_MISSES = 6       # drop a track after this many frames in a row without a match
MATCH_IOU = 0.3
SCORE_SMOOTHING = 0.5   # 0 = no smoothing, closer to 1 = steadier but slower


def iou(a: np.ndarray, b: np.ndarray) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    id: int
    box: np.ndarray
    head: np.ndarray
    head_from_face: bool
    score: float                                   # smoothed model confidence
    hits: deque = field(default_factory=lambda: deque(maxlen=WINDOW))
    misses: int = 0

    @property
    def confirmed(self) -> bool:
        return sum(self.hits) >= CONFIRM_HITS

    @property
    def visible(self) -> bool:
        """Confirmed and seen in this frame or the one before (avoids flicker on a single miss)."""
        return self.confirmed and self.misses <= 1


class PersonTracker:
    def __init__(self):
        self.tracks: list[Track] = []
        self._next_id = 1

    def update(self, detections: list[Detection]) -> list[Track]:
        unmatched = list(range(len(detections)))
        for track in sorted(self.tracks, key=lambda t: -t.score):
            best, best_iou = None, MATCH_IOU
            for j in unmatched:
                v = iou(track.box, detections[j].box)
                if v > best_iou:
                    best, best_iou = j, v
            if best is None:
                track.hits.append(0)
                track.misses += 1
                continue
            unmatched.remove(best)
            d = detections[best]
            track.box = d.box
            track.head, track.head_from_face = head_box(d.box, d.keypoints)
            track.score = SCORE_SMOOTHING * track.score + (1 - SCORE_SMOOTHING) * d.score
            track.hits.append(1)
            track.misses = 0

        for j in unmatched:
            d = detections[j]
            head, from_face = head_box(d.box, d.keypoints)
            t = Track(self._next_id, d.box, head, from_face, d.score)
            t.hits.append(1)
            self.tracks.append(t)
            self._next_id += 1

        self.tracks = [t for t in self.tracks if t.misses < MAX_MISSES]
        return [t for t in self.tracks if t.visible]

    def reset(self) -> None:
        self.tracks.clear()
